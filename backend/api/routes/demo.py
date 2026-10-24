"""
api/routes/demo.py — Demo-only tools (synthetic data).  Disabled when ENABLE_DEMO_TOOLS=0.

POST /api/demo/tamper-audit/{shipment_id}
    Simulates someone with direct database access rewriting an audit entry,
    bypassing the application (raw UPDATE, no new hash).  Used to show that
    GET /api/audit-logs/{id}/verify detects it.

POST /api/demo/reset                  — restore all three demo shipments
POST /api/demo/reset/{shipment_id}    — restore one (keeps its id, so open pages stay valid)
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from db.database import get_db
from db.demo_data import DEMO_SHIPMENTS, reset_all, reset_shipment
from api.models.models import AuditLog, Shipment

router = APIRouter(prefix="/api/demo", tags=["demo"])

# Rewrites ordered by how damaging they would be if undetected
_TAMPER_PRIORITY = ["APPROVAL_REJECTED", "APPROVAL_APPROVED", "POLICY_DENIED", "AGENT_TRANSITION"]


def _rewrite(entry: AuditLog) -> dict:
    """The forged values for one entry — a plausible cover-up, not random noise."""
    if entry.event == "APPROVAL_REJECTED":
        return {"event": "APPROVAL_APPROVED"}
    if entry.event == "APPROVAL_APPROVED":
        return {"event": "APPROVAL_REJECTED"}
    details = dict(entry.details or {})
    if entry.event == "POLICY_DENIED":
        details["reason"] = "G7: ALLOW — low-risk action approved"
    else:
        details["reason"] = "Approved by system administrator"
    return {"details": details}


def _require_demo_tools() -> None:
    if os.getenv("ENABLE_DEMO_TOOLS", "1") == "0":
        raise HTTPException(status_code=404, detail="Demo tools are disabled")


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db)):
    _require_demo_tools()
    return {"reset": reset_all(db)}


@router.post("/reset/{shipment_id}")
def reset_demo_shipment(shipment_id: str, db: Session = Depends(get_db)):
    _require_demo_tools()
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None or shipment.reference_number not in DEMO_SHIPMENTS:
        raise HTTPException(status_code=404, detail="Not a demo shipment")
    return {"reset": {shipment.reference_number: reset_shipment(db, shipment.reference_number)}}


@router.post("/tamper-audit/{shipment_id}")
def tamper_audit(shipment_id: str, db: Session = Depends(get_db)):
    _require_demo_tools()

    entries = db.query(AuditLog).filter(
        AuditLog.shipment_id == shipment_id, AuditLog.entry_hash.isnot(None)
    ).all()
    target = next(
        (e for kind in _TAMPER_PRIORITY for e in sorted(entries, key=lambda e: e.timestamp) if e.event == kind),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="No chained audit entries to tamper with — run the agent first")

    # Capture before the UPDATE — commit expires `target`, so later reads return forged values
    target_id, original_event = str(target.id), target.event
    forged = _rewrite(target)
    before = {k: getattr(target, k) for k in forged}
    db.execute(update(AuditLog).where(AuditLog.id == target_id).values(**forged))
    db.commit()
    return {"id": target_id, "event": original_event, "before": before, "after": forged}
