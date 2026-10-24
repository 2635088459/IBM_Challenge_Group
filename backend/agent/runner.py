"""
agent/runner.py — Event-driven run loop for the AgentFSM.

The runner:
  1. Accepts an incoming event (event_type + payload)
  2. Creates or loads an AgentFSM for the shipment
  3. Drives the FSM through its states, calling LLM tools as needed
  4. Emits state-change events over Socket.IO to M3's dashboard
  5. Calls M2's API to create agent tasks, approvals, and audit log entries

Usage (from a Celery task or FastAPI WebSocket handler):
    from agent.runner import AgentRunner
    runner = AgentRunner(shipment_id="SHP-002", socketio_emit=sio.emit)
    runner.handle_event("CBP_HOLD_RECEIVED", payload={"source_verified": True})
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from agent.fsm import AgentFSM, AgentState, TransitionRecord, GuardFailedError, PermissionDeniedError
from agent.guards import g_approval_exists
from agent.policy import PolicyDecision
import agent.llm_client as llm
import agent.red_team as red_team
import agent.tools as tools

logger = logging.getLogger(__name__)


def plan_hash(proposed_actions: list[dict]) -> str:
    """Fingerprint of a proposed plan — approvals are bound to this exact plan."""
    return hashlib.sha256(json.dumps(proposed_actions, sort_keys=True).encode()).hexdigest()


class AgentRunner:
    """
    High-level orchestrator that wraps AgentFSM with LLM calls,
    API interactions, and Socket.IO state-push.
    """

    def __init__(
        self,
        shipment_id: str,
        context: dict[str, Any] | None = None,
        socketio_emit: Callable | None = None,
    ):
        self.shipment_id = shipment_id
        self._emit = socketio_emit  # optional Socket.IO emit(event, data, room=...)

        # Build initial context from M2 API
        initial_context = self._load_shipment_context(shipment_id)
        if context:
            initial_context.update(context)

        self.fsm = AgentFSM(
            shipment_id=shipment_id,
            context=initial_context,
            on_transition=self._on_transition,
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def start(self) -> AgentState:
        """Boot the FSM (INITIALIZE → OBSERVE) and run the first OBSERVE cycle."""
        state = self.fsm.start()
        return self._run_observe_cycle()

    def handle_event(self, event_type: str, payload: dict[str, Any] | None = None) -> AgentState:
        """
        Inject an external event (e.g. CBP_HOLD_RECEIVED, APPROVAL_RECEIVED)
        into the FSM and drive the resulting state transitions.
        """
        if payload:
            self.fsm.context.update(payload)

        new_state = self.fsm.process_event(event_type, payload)

        # After certain events, run follow-up cycles
        if new_state == AgentState.OBSERVE:
            return self._run_observe_cycle()
        if new_state == AgentState.CUSTOMS_HOLD:
            return self._run_customs_hold_cycle()
        if new_state == AgentState.WAIT_EVENT:
            logger.info("[%s] Waiting for external event", self.shipment_id)
        return new_state

    def resume_after_approval(
        self,
        approved: bool,
        proposed_actions: list[dict],
        analysis: str | None,
        approved_hash: str,
        risk_context: dict[str, Any] | None = None,
    ) -> AgentState:
        """
        Wake the agent from WAIT_EVENT once every approval for its plan is resolved.
        Approved → re-run POLICY_CHECK on the same plan (no new LLM call) → ACT → VERIFY.
        Rejected → RECOVER.
        """
        self.fsm.resume_from(AgentState.WAIT_EVENT)
        self.fsm.context.update(risk_context or {})
        self.fsm.context.update({
            "llm_analysis": analysis,
            "proposed_actions": proposed_actions,
            "approval_required": True,
            "approval_status": "APPROVED" if approved else "REJECTED",
            "approved_plan_hash": approved_hash,
        })

        if not approved:
            self.fsm.process_event("APPROVAL_REJECTED")
            return self.fsm.current_state

        self.fsm.process_event("APPROVAL_RECEIVED")
        self.fsm.process_event("APPROVED_ANALYSIS_LOADED")
        self.fsm.process_event("APPROVED_PLAN_LOADED")
        self.fsm.process_event("PLAN_DONE")
        return self._run_policy_check(proposed_actions)

    # ── Observe cycle ─────────────────────────────────────────────────────────

    def _run_observe_cycle(self) -> AgentState:
        """
        OBSERVE: fetch shipment data, detect issues, trigger appropriate event.
        """
        shipment = self._load_shipment_context(self.shipment_id)
        # Merge API data but keep any pre-injected flags (e.g. has_discrepancy)
        pre_injected = {k: v for k, v in self.fsm.context.items()
                        if k in ("has_discrepancy", "discrepancy_detail", "red_team", "invoice_remarks")}
        self.fsm.context.update(shipment)
        self.fsm.context.update(pre_injected)  # restore injected flags

        docs = shipment.get("documents", [])
        doc_types = {d["doc_type"] for d in docs}

        # If discrepancy was pre-injected (e.g. simulate_discrepancy=true from API),
        # skip the missing-doc gate and go straight to REASON/PLAN.
        if self.fsm.context.get("has_discrepancy"):
            self.fsm.process_event("DISCREPANCY_DETECTED")
            return self._run_reason_plan_cycle()

        # C09: verified CBP hold — coordinate the response, never release it
        if self.fsm.context.get("status") == "CUSTOMS_HOLD" and self.fsm.context.get("cbp_hold_verified"):
            self.fsm.context["source_verified"] = True
            self.fsm.process_event("CBP_HOLD_RECEIVED")
            return self._run_customs_hold_cycle()

        # C01: Missing document
        required_docs = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING"}
        missing = list(required_docs - doc_types)
        if missing:
            self.fsm.context["missing_documents"] = missing
            self.fsm.process_event("MISSING_DOCUMENT")
            return self.fsm.current_state

        # C02: Compare Invoice vs Packing List for discrepancy
        invoice = next((d for d in docs if d["doc_type"] == "INVOICE"), None)
        packing_list = next((d for d in docs if d["doc_type"] == "PACKING_LIST"), None)
        if invoice and packing_list:
            try:
                result = tools.compare_documents(self.shipment_id, invoice["id"], packing_list["id"])
                if result.get("overall_status") == "FAIL":
                    self.fsm.context["has_discrepancy"] = True
                    self.fsm.context["discrepancy_detail"] = result.get("mismatches", [])
                    self.fsm.process_event("DISCREPANCY_DETECTED")
                    return self._run_reason_plan_cycle()
            except Exception:
                logger.exception("compare_documents failed — treating as no discrepancy")

        self.fsm.process_event("OBSERVE_DONE")
        return self.fsm.current_state

    # ── Reason → Plan cycle ───────────────────────────────────────────────────

    def _run_reason_plan_cycle(self) -> AgentState:
        """REASON → PLAN → POLICY_CHECK → ESCALATE/ACT."""
        # REASON: call LLM
        analysis = llm.reason(self.fsm.context)
        self.fsm.context["llm_analysis"] = analysis
        logger.info("[%s] LLM analysis: %s", self.shipment_id, analysis[:120])
        self.fsm.process_event("REASON_DONE")

        # PLAN: call LLM for action proposals
        proposed_actions = llm.plan(self.fsm.context, analysis)
        if self.fsm.context.get("red_team"):
            proposed_actions = red_team.compromise_plan(proposed_actions)
        self.fsm.context["proposed_actions"] = proposed_actions
        self.fsm.context["llm_source"] = llm.last_source()
        logger.info("[%s] LLM proposed %d actions", self.shipment_id, len(proposed_actions))
        self.fsm.process_event("PLAN_DONE")

        # POLICY_CHECK: evaluate each action
        return self._run_policy_check(proposed_actions)

    def _run_policy_check(self, proposed_actions: list[dict]) -> AgentState:
        """POLICY_CHECK: evaluate actions, ESCALATE or ACT accordingly."""
        needs_approval = False
        denials: list[dict] = []

        # Check every action — a DENY anywhere in the plan blocks the whole plan
        for action in proposed_actions:
            try:
                decision = self.fsm.propose_action(action)
            except PermissionDeniedError as e:
                logger.warning("[%s] Action denied: %s", self.shipment_id, e)
                denials.append({"action_type": e.action, "reason": e.reason})
                continue

            if decision == PolicyDecision.APPROVAL_REQUIRED:
                needs_approval = True

        if denials:
            self.fsm.context["policy_denials"] = denials
            self.fsm.process_event("POLICY_DENY")
            return self.fsm.current_state

        if needs_approval and self._plan_approved(proposed_actions):
            self.fsm.process_event("POLICY_APPROVED")
        elif needs_approval:
            self.fsm.process_event("POLICY_APPROVAL_REQUIRED")
            return self._run_escalate_cycle(proposed_actions)
        else:
            self.fsm.process_event("POLICY_ALLOW")

        # ACT: (for demo, log it; real impl would call filing APIs)
        logger.info("[%s] ACT: executing approved actions", self.shipment_id)
        self.fsm.process_event("ACT_DONE")
        self.fsm.process_event("VERIFY_PASS")
        return self.fsm.current_state

    def _plan_approved(self, proposed_actions: list[dict]) -> bool:
        """G-approval: a human approved this exact plan (hash unchanged since approval)."""
        return (
            g_approval_exists(self.fsm.context).passed
            and self.fsm.context.get("approved_plan_hash") == plan_hash(proposed_actions)
        )

    # ── Escalate cycle (HITL) ─────────────────────────────────────────────────

    def _run_escalate_cycle(self, proposed_actions: list[dict]) -> AgentState:
        """
        ESCALATE: record the plan fingerprint and the roles that must sign off,
        then move to WAIT_EVENT.  The API layer (api/agent_store.py) persists the
        agent_actions + approvals rows from this context.
        """
        roles_needed = sorted({
            a["role_required"]
            for a in proposed_actions
            if a.get("role_required")
        }) or ["R2"]  # default

        self.fsm.context["plan_hash"] = plan_hash(proposed_actions)
        self.fsm.context["approval_roles"] = roles_needed

        self.fsm.process_event("ESCALATE_DONE")
        return self.fsm.current_state

    # ── CBP Hold cycle ────────────────────────────────────────────────────────

    def _run_customs_hold_cycle(self) -> AgentState:
        """
        CUSTOMS_HOLD: create evidence tasks, notify R4/R5, move to WAIT_EVENT.
        Agent does NOT set cbp_released — it waits for the official CBP event.
        """
        logger.info("[%s] Handling CUSTOMS_HOLD — notifying compliance and broker", self.shipment_id)

        # Notify R4 (Trade Compliance Officer) and R5 (Customs Broker);
        # the API layer (api/agent_store.py) persists these as approval tasks
        self.fsm.context["hold_notify_roles"] = ["R4", "R5"]

        self.fsm.process_event("CBP_HOLD_ESCALATE")
        return self.fsm.current_state

    def handle_cbp_release(self, source_verified: bool) -> AgentState:
        """
        WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED on an official CBP release.
        set_cbp_released() raises PermissionDeniedError unless source_verified.
        """
        self.fsm.resume_from(AgentState.WAIT_EVENT)
        self.fsm.context["source_verified"] = source_verified
        self.fsm.process_event("CBP_RELEASE_RECEIVED")
        self.fsm.process_event("VERIFY_PASS")
        return self.fsm.current_state

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_shipment_context(self, shipment_id: str) -> dict[str, Any]:
        """Load shipment data from M2 API into a flat context dict."""
        try:
            data = tools.get_shipment_status(shipment_id)
            return {
                "shipment_id": shipment_id,
                "reference_number": data.get("reference_number"),
                "status": data.get("status"),
                "documents": data.get("documents", []),
            }
        except Exception:
            logger.warning("Could not load shipment %s from API — using bare context", shipment_id)
            return {"shipment_id": shipment_id}

    def _on_transition(self, record: TransitionRecord) -> None:
        """
        Callback fired on every FSM state transition.
        Pushes the event over Socket.IO to M3's dashboard.
        """
        payload = {
            "shipment_id": self.shipment_id,
            **record.to_dict(),
        }
        logger.debug("Transition: %s", payload)

        if self._emit:
            try:
                self._emit("agent_state_update", payload)
            except Exception:
                logger.exception("Socket.IO emit failed")
