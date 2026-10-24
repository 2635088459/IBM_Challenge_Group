"""
db/demo_data.py — The three demo shipments, and resetting them in place.

  SHP-001 (C01): COLLECT_DATA  — missing Commercial Invoice
  SHP-002 (C02): ESCALATE      — Invoice qty=500 vs Packing List qty=480
  SHP-003 (C09): CUSTOMS_HOLD  — CBP hold event already ingested

A reset keeps each shipment's id (so open pages and shared links stay valid)
and replaces everything hanging off it with the initial demo state.
Used by scripts/seed.py and the "Reset demo" buttons (POST /api/demo/reset…).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from api.models.models import (
    AgentAction, AgentTask, Approval, AuditLog, Document, Event, OutboxEntry, Shipment,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_shp001(db: Session, sid: str) -> str:
    """C01 — only a Packing List and Bill of Lading; the Invoice is missing."""
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="PACKING_LIST",
                    file_hash="pl_hash_001", version=1, status="extracted"))
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="BILL_OF_LADING",
                    file_hash="bl_hash_001", version=1, status="raw"))
    db.add(AgentTask(id=_uid(), shipment_id=sid, state="COLLECT_DATA"))
    db.add(AuditLog(shipment_id=sid, actor="agent", event="MISSING_DOCUMENT_DETECTED",
                    details={"missing_doc_type": "INVOICE"}))
    return "COLLECT_DATA"


def _build_shp002(db: Session, sid: str) -> str:
    """C02 — Invoice 500 vs Packing List 480, approvals already requested."""
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="INVOICE",
                    file_hash="inv_hash_002", version=1, status="verified"))
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="PACKING_LIST",
                    file_hash="pl_hash_002", version=1, status="verified"))
    task_id = _uid()
    db.add(AgentTask(id=task_id, shipment_id=sid, state="ESCALATE"))
    db.flush()
    action_id = _uid()
    db.add(AgentAction(
        id=action_id, task_id=task_id, action_type="REQUEST_HUMAN_APPROVAL",
        idempotency_key=f"approval-shp002-{_uid()[:8]}",
        payload={"discrepancy": {"field": "line_quantity", "invoice_value": 500,
                                 "packing_list_value": 480, "delta": 20}},
        status="PENDING",
    ))
    db.flush()
    for role in ("R2", "R3"):
        db.add(Approval(id=_uid(), action_id=action_id, shipment_id=sid, role=role,
                        status="PENDING", payload_hash="sha256-shp002-discrepancy"))
    db.add(AuditLog(shipment_id=sid, actor="agent", event="DOCUMENT_DISCREPANCY_DETECTED",
                    details={"field": "line_quantity", "invoice": 500, "packing_list": 480}))
    db.add(AuditLog(shipment_id=sid, actor="agent", event="APPROVAL_REQUESTED",
                    details={"roles": ["R2", "R3"], "reason": "quantity_mismatch"}))
    return "ESCALATE"


def _build_shp003(db: Session, sid: str) -> str:
    """C09 — a verified CBP hold is in place."""
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="INVOICE",
                    file_hash="inv_hash_003", version=1, status="extracted"))
    db.add(Document(id=_uid(), shipment_id=sid, doc_type="PACKING_LIST",
                    file_hash="pl_hash_003", version=1, status="extracted"))
    an_hour_ago = _now() - timedelta(hours=1)
    db.add(Event(
        id=_uid(), event_id=f"cbp-hold-{_uid()[:8]}", event_type="CBP_HOLD_RECEIVED",
        source_verified=True, shipment_id=sid,
        payload={"hold_code": "TIB", "details": "Targeted Inspection — hold pending inspection"},
        occurred_at=an_hour_ago, processed_at=an_hour_ago,
    ))
    db.add(AgentTask(id=_uid(), shipment_id=sid, state="CUSTOMS_HOLD"))
    db.add(AuditLog(shipment_id=sid, actor="system", event="CBP_HOLD_RECEIVED",
                    details={"hold_code": "TIB", "source_verified": True}))
    db.add(AuditLog(shipment_id=sid, actor="agent", event="CBP_RELEASE_BLOCKED",
                    details={"reason": "cbp_released=true requires source_verified official channel"}))
    return "CUSTOMS_HOLD"


DEMO_SHIPMENTS: dict[str, Callable[[Session, str], str]] = {
    "SHP-001": _build_shp001,
    "SHP-002": _build_shp002,
    "SHP-003": _build_shp003,
}


def _clear_children(db: Session, sid: str) -> None:
    """Delete everything that hangs off a shipment, children before parents."""
    task_ids = db.query(AgentTask.id).filter(AgentTask.shipment_id == sid)
    action_ids = db.query(AgentAction.id).filter(AgentAction.task_id.in_(task_ids))
    db.query(Approval).filter(
        (Approval.shipment_id == sid) | Approval.action_id.in_(action_ids)
    ).delete(synchronize_session=False)
    db.query(OutboxEntry).filter(OutboxEntry.action_id.in_(action_ids)).delete(synchronize_session=False)
    db.query(AgentAction).filter(AgentAction.task_id.in_(task_ids)).delete(synchronize_session=False)
    db.query(AgentTask).filter(AgentTask.shipment_id == sid).delete(synchronize_session=False)
    db.query(Document).filter(Document.shipment_id == sid).delete(synchronize_session=False)
    db.query(Event).filter(Event.shipment_id == sid).delete(synchronize_session=False)
    # The audit chain restarts from GENESIS — the reset itself is the first new entry
    db.query(AuditLog).filter(AuditLog.shipment_id == sid).delete(synchronize_session=False)


def reset_shipment(db: Session, reference: str) -> str:
    """Restore one demo shipment to its initial state; returns its (unchanged) id."""
    build = DEMO_SHIPMENTS[reference]
    shipment = db.query(Shipment).filter(Shipment.reference_number == reference).first()
    if shipment is None:
        shipment = Shipment(id=_uid(), reference_number=reference, status="OBSERVE")
        db.add(shipment)
        db.flush()
    else:
        _clear_children(db, shipment.id)

    db.add(AuditLog(shipment_id=shipment.id, actor="system", event="DEMO_RESET",
                    details={"reference": reference}))
    shipment.status = build(db, shipment.id)
    db.commit()
    return shipment.id


def reset_all(db: Session) -> dict[str, str]:
    return {ref: reset_shipment(db, ref) for ref in DEMO_SHIPMENTS}
