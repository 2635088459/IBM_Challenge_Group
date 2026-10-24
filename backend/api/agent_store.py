"""
api/agent_store.py — Persists agent runs and resumes the agent once its approvals are resolved.

The AgentRunner is stateless between requests; this module keeps its state in the DB:
  agent_tasks.state        — FSM state the agent stopped in
  shipments.status         — mirrors it (a CBP hold is kept until CBP releases it)
  audit_logs               — AGENT_TRANSITION per state change, AGENT_PLAN_PROPOSED per escalated plan
  agent_actions/approvals  — one action row per proposed step, one approval per required role

It also reacts to CBP events from the trusted CBP channel (C09): a verified hold
starts the agent's hold flow; a verified release lets it verify and clear.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from agent.fsm import PermissionDeniedError
from api.models.models import AgentAction, AgentTask, Approval, AuditLog, Event, Shipment

logger = logging.getLogger(__name__)

RISK_CONTEXT_KEYS = ("has_discrepancy", "discrepancy_detail", "missing_documents")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_runner(shipment_id: str, context: dict[str, Any] | None = None):
    """Build an AgentRunner whose state transitions are captured into a list."""
    from agent.runner import AgentRunner  # lazy — avoids loading LLM deps at startup

    transitions: list[dict] = []

    def _capture_emit(event: str, data: dict, **_kwargs):
        if event == "agent_state_update":
            transitions.append(data)

    runner = AgentRunner(shipment_id=shipment_id, context=context, socketio_emit=_capture_emit)
    return runner, transitions


def _latest_task(db: Session, shipment_id: str) -> AgentTask | None:
    return (
        db.query(AgentTask)
        .filter(AgentTask.shipment_id == shipment_id)
        .order_by(AgentTask.created_at.desc())
        .first()
    )


def _latest_plan_log(db: Session, shipment_id: str) -> AuditLog | None:
    return (
        db.query(AuditLog)
        .filter(AuditLog.shipment_id == shipment_id, AuditLog.event == "AGENT_PLAN_PROPOSED")
        .order_by(AuditLog.timestamp.desc())
        .first()
    )


def save_run(db: Session, shipment: Shipment, runner, transitions: list[dict]) -> None:
    """Persist the FSM state, transition history and (if escalated) the plan's approvals."""
    task = _latest_task(db, shipment.id)
    if task is None:
        task = AgentTask(shipment_id=shipment.id)
        db.add(task)

    final_state = runner.fsm.current_state.value
    task.state = final_state
    ctx = runner.fsm.context
    # A CBP hold is lifted only by an official CBP release (cbp_released is set
    # solely by AgentFSM.set_cbp_released on a verified event), never by the agent
    if shipment.status != "CUSTOMS_HOLD" or ctx.get("cbp_released"):
        shipment.status = final_state

    for t in transitions:
        db.add(AuditLog(
            shipment_id=shipment.id,
            actor="agent",
            event="AGENT_TRANSITION",
            details={k: t[k] for k in ("from_state", "to_state", "event", "reason", "timestamp")},
            timestamp=datetime.fromisoformat(t["timestamp"]).astimezone(timezone.utc).replace(tzinfo=None),
        ))

    for denial in ctx.get("policy_denials") or []:
        db.add(AuditLog(shipment_id=shipment.id, actor="policy", event="POLICY_DENIED", details=denial))

    if final_state == "WAIT_EVENT" and ctx.get("plan_hash"):
        db.flush()  # task.id needed for action rows
        _escalate_plan(db, task, shipment.id, ctx)

    for role in ctx.get("hold_notify_roles") or []:
        _request_hold_task(db, shipment.id, role)

    db.commit()


def _request_hold_task(db: Session, shipment_id: str, role: str) -> None:
    """CBP-hold task for a role (no plan attached); one open task per role."""
    open_task = db.query(Approval).filter(
        Approval.shipment_id == shipment_id,
        Approval.role == role,
        Approval.status == "PENDING",
        Approval.payload_hash.is_(None),
    ).first()
    if open_task:
        return
    db.add(Approval(shipment_id=shipment_id, role=role, status="PENDING"))
    db.add(AuditLog(
        shipment_id=shipment_id,
        actor="system",
        event="APPROVAL_REQUESTED",
        details={"role": role, "reason": "CBP hold — evidence and broker coordination"},
    ))


def cbp_hold_verified(db: Session, shipment_id: str) -> bool:
    """True when the latest verified CBP event for the shipment is a hold."""
    latest = (
        db.query(Event)
        .filter(
            Event.shipment_id == shipment_id,
            Event.source_verified.is_(True),
            Event.event_type.in_(("CBP_HOLD_RECEIVED", "CBP_RELEASE_RECEIVED")),
        )
        .order_by(Event.processed_at.desc())
        .first()
    )
    return latest is not None and latest.event_type == "CBP_HOLD_RECEIVED"


def handle_cbp_event(db: Session, event: Event) -> None:
    """React to an event ingested from the CBP channel (C09)."""
    if not event.shipment_id or event.event_type not in ("CBP_HOLD_RECEIVED", "CBP_RELEASE_RECEIVED"):
        return
    shipment = db.query(Shipment).filter(Shipment.id == event.shipment_id).first()

    if event.event_type == "CBP_HOLD_RECEIVED":
        if not event.source_verified:
            db.add(AuditLog(
                shipment_id=shipment.id, actor="agent", event="CBP_EVENT_IGNORED",
                details={"event_id": event.event_id, "reason": "CBP hold not from a verified CBP channel"},
            ))
            db.commit()
            return
        shipment.status = "CUSTOMS_HOLD"
        db.commit()
        runner, transitions = make_runner(shipment.id, {"cbp_hold_verified": True})
        runner.start()
        save_run(db, shipment, runner, transitions)
        return

    # CBP_RELEASE_RECEIVED
    if shipment.status != "CUSTOMS_HOLD":
        return

    task = _latest_task(db, shipment.id)
    open_plan = db.query(Approval).filter(
        Approval.shipment_id == shipment.id,
        Approval.status == "PENDING",
        Approval.payload_hash.isnot(None),
    ).first()
    waiting_on_cbp = (task is None or task.state in ("WAIT_EVENT", "CUSTOMS_HOLD")) and open_plan is None

    if not waiting_on_cbp and event.source_verified:
        # Hold lifted, but the agent still has other work (open approvals, a blocked plan)
        shipment.status = "WAIT_EVENT" if open_plan else (task.state if task else "OBSERVE")
        db.add(AuditLog(
            shipment_id=shipment.id, actor="cbp", event="CBP_HOLD_LIFTED",
            details={"event_id": event.event_id, "next": shipment.status},
        ))
        db.commit()
        return

    runner, transitions = make_runner(shipment.id)
    try:
        runner.handle_cbp_release(source_verified=event.source_verified)
    except PermissionDeniedError as e:
        db.add(AuditLog(
            shipment_id=shipment.id, actor="agent", event="CBP_RELEASE_REJECTED",
            details={"event_id": event.event_id, "reason": e.reason},
        ))
        db.commit()
        return
    save_run(db, shipment, runner, transitions)


def _escalate_plan(db: Session, task: AgentTask, shipment_id: str, ctx: dict[str, Any]) -> None:
    payload_hash = ctx["plan_hash"]
    actions = ctx.get("proposed_actions") or []
    now = _now()

    # A new plan supersedes approvals still pending for an older one
    stale = db.query(Approval).filter(
        Approval.shipment_id == shipment_id,
        Approval.status == "PENDING",
        Approval.payload_hash != payload_hash,
    ).all()
    for old in stale:
        old.status = "EXPIRED"
        old.resolved_at = now

    # Re-running the agent on an unchanged plan must not duplicate its approvals
    already_pending = db.query(Approval).filter(
        Approval.shipment_id == shipment_id,
        Approval.status == "PENDING",
        Approval.payload_hash == payload_hash,
    ).first()
    if already_pending:
        return

    rows: list[AgentAction] = []
    for i, action in enumerate(actions):
        key = f"{task.id}:{payload_hash}:{i}"
        row = db.query(AgentAction).filter(AgentAction.idempotency_key == key).first()
        if row is None:
            row = AgentAction(
                task_id=task.id,
                action_type=action.get("action_type", "UNKNOWN"),
                idempotency_key=key,
                payload=action,
                status="PENDING",
            )
            db.add(row)
        rows.append(row)
    db.flush()

    db.add(AuditLog(
        shipment_id=shipment_id,
        actor="agent",
        event="AGENT_PLAN_PROPOSED",
        details={
            "payload_hash": payload_hash,
            "analysis": ctx.get("llm_analysis"),
            "proposed_actions": actions,
            # Risk inputs, so the resumed POLICY_CHECK scores the plan as it was approved
            "risk_context": {k: ctx[k] for k in RISK_CONTEXT_KEYS if k in ctx},
        },
        timestamp=now,
    ))

    for role in ctx.get("approval_roles") or []:
        action = next((r for r in rows if (r.payload or {}).get("role_required") == role), rows[0] if rows else None)
        db.add(Approval(
            action_id=action.id if action else None,
            shipment_id=shipment_id,
            role=role,
            status="PENDING",
            payload_hash=payload_hash,
            requested_at=now,
        ))
        db.add(AuditLog(
            shipment_id=shipment_id,
            actor="system",
            event="APPROVAL_REQUESTED",
            details={"role": role, "payload_hash": payload_hash},
            timestamp=now,
        ))


def resume_if_ready(db: Session, approval: Approval) -> None:
    """
    Called after an approval is resolved.  Once every approval for the agent's
    current plan is resolved, wake the agent: all APPROVED → execute the plan,
    any REJECTED → RECOVER.  Approvals for superseded plans are ignored.
    """
    if not approval.shipment_id or not approval.payload_hash:
        return

    task = _latest_task(db, approval.shipment_id)
    plan_log = _latest_plan_log(db, approval.shipment_id)
    if task is None or task.state != "WAIT_EVENT" or plan_log is None:
        return
    plan = plan_log.details or {}
    if plan.get("payload_hash") != approval.payload_hash:
        return

    group = db.query(Approval).filter(
        Approval.shipment_id == approval.shipment_id,
        Approval.payload_hash == approval.payload_hash,
        Approval.requested_at >= plan_log.timestamp,
    ).all()
    statuses = {a.status for a in group}
    if "PENDING" in statuses:
        return
    if "REJECTED" in statuses:
        approved = False
    elif statuses == {"APPROVED"}:
        approved = True
    else:
        return  # an approval expired — the agent must be re-run

    shipment = db.query(Shipment).filter(Shipment.id == approval.shipment_id).first()
    if approved and shipment.status == "CUSTOMS_HOLD":
        db.add(AuditLog(
            shipment_id=shipment.id,
            actor="agent",
            event="AGENT_WAITING_CBP_RELEASE",
            details={"payload_hash": approval.payload_hash},
        ))
        db.commit()
        return

    runner, transitions = make_runner(shipment.id)
    runner.resume_after_approval(
        approved=approved,
        proposed_actions=plan.get("proposed_actions") or [],
        analysis=plan.get("analysis"),
        approved_hash=approval.payload_hash,
        risk_context=plan.get("risk_context"),
    )

    if not approved:
        action_status = "REJECTED"
    elif runner.fsm.current_state.value == "CLEARANCE_VERIFIED":
        action_status = "EXECUTED"
    else:
        action_status = None
    if action_status:
        for row in db.query(AgentAction).filter(
            AgentAction.task_id == task.id,
            AgentAction.idempotency_key.like(f"%:{approval.payload_hash}:%"),
        ):
            row.status = action_status

    save_run(db, shipment, runner, transitions)
