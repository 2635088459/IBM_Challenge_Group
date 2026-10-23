"""
Seed script — inserts 3 synthetic shipments for the demo.

  SHP-001 (C01): COLLECT_DATA  — missing Commercial Invoice
  SHP-002 (C02): ESCALATE      — Invoice qty=500 vs Packing List qty=480
  SHP-003 (C09): CUSTOMS_HOLD  — CBP hold event already ingested

Run from backend/:
    DATABASE_URL=postgresql://customs:customs@localhost:5432/customs python scripts/seed.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
import uuid
from db.database import _get_session_local
SessionLocal = _get_session_local()
from api.models.models import (
    Shipment, Document, Event, AgentTask, AgentAction, Approval, AuditLog, OutboxEntry
)

db = SessionLocal()


def uid():
    return str(uuid.uuid4())


def clear_existing():
    """Remove previously seeded data so the script is idempotent."""
    for ref in ["SHP-001", "SHP-002", "SHP-003"]:
        existing = db.query(Shipment).filter(Shipment.reference_number == ref).first()
        if existing:
            db.delete(existing)
    db.commit()


def seed():
    clear_existing()

    # ── SHP-001 (C01) — Missing Commercial Invoice ────────────────────────────
    shp1_id = uid()
    shp1 = Shipment(id=shp1_id, reference_number="SHP-001", status="COLLECT_DATA")
    db.add(shp1)
    db.flush()  # make shipment visible to FK checks before adding children

    # Only a Packing List — no Invoice
    db.add(Document(
        id=uid(), shipment_id=shp1_id,
        doc_type="PACKING_LIST", file_hash="pl_hash_001",
        version=1, status="extracted",
    ))
    db.add(Document(
        id=uid(), shipment_id=shp1_id,
        doc_type="BILL_OF_LADING", file_hash="bl_hash_001",
        version=1, status="raw",
    ))

    task1_id = uid()
    db.add(AgentTask(id=task1_id, shipment_id=shp1_id, state="COLLECT_DATA"))

    db.add(AuditLog(
        id=uid(), shipment_id=shp1_id,
        actor="agent", event="MISSING_DOCUMENT_DETECTED",
        details={"missing_doc_type": "INVOICE"},
    ))

    # ── SHP-002 (C02) — Quantity Mismatch ─────────────────────────────────────
    shp2_id = uid()
    shp2 = Shipment(id=shp2_id, reference_number="SHP-002", status="ESCALATE")
    db.add(shp2)
    db.flush()  # make shipment visible to FK checks before adding children

    db.add(Document(
        id=uid(), shipment_id=shp2_id,
        doc_type="INVOICE", file_hash="inv_hash_002",
        version=1, status="verified",
    ))
    db.add(Document(
        id=uid(), shipment_id=shp2_id,
        doc_type="PACKING_LIST", file_hash="pl_hash_002",
        version=1, status="verified",
    ))

    task2_id = uid()
    db.add(AgentTask(id=task2_id, shipment_id=shp2_id, state="ESCALATE"))

    action2_id = uid()
    action2 = AgentAction(
        id=action2_id,
        task_id=task2_id,
        action_type="REQUEST_HUMAN_APPROVAL",
        idempotency_key=f"approval-shp002-{shp2_id[:8]}",
        payload={
            "discrepancy": {
                "field": "line_quantity",
                "invoice_value": 500,
                "packing_list_value": 480,
                "delta": 20,
            }
        },
        status="PENDING",
    )
    db.add(action2)
    db.flush()

    db.add(Approval(
        id=uid(),
        action_id=action2_id,
        shipment_id=shp2_id,
        role="R2",
        status="PENDING",
        payload_hash="sha256-shp002-discrepancy",
    ))
    db.add(Approval(
        id=uid(),
        action_id=action2_id,
        shipment_id=shp2_id,
        role="R3",
        status="PENDING",
        payload_hash="sha256-shp002-discrepancy",
    ))

    db.add(AuditLog(
        id=uid(), shipment_id=shp2_id,
        actor="agent", event="DOCUMENT_DISCREPANCY_DETECTED",
        details={"field": "line_quantity", "invoice": 500, "packing_list": 480},
    ))
    db.add(AuditLog(
        id=uid(), shipment_id=shp2_id,
        actor="agent", event="APPROVAL_REQUESTED",
        details={"roles": ["R2", "R3"], "reason": "quantity_mismatch"},
    ))

    # ── SHP-003 (C09) — CBP Hold ──────────────────────────────────────────────
    shp3_id = uid()
    shp3 = Shipment(id=shp3_id, reference_number="SHP-003", status="CUSTOMS_HOLD")
    db.add(shp3)
    db.flush()  # make shipment visible to FK checks before adding children

    db.add(Document(
        id=uid(), shipment_id=shp3_id,
        doc_type="INVOICE", file_hash="inv_hash_003",
        version=1, status="extracted",
    ))
    db.add(Document(
        id=uid(), shipment_id=shp3_id,
        doc_type="PACKING_LIST", file_hash="pl_hash_003",
        version=1, status="extracted",
    ))

    cbp_event_id = f"cbp-hold-{shp3_id[:8]}"
    db.add(Event(
        id=uid(),
        event_id=cbp_event_id,
        event_type="CBP_HOLD_RECEIVED",
        source_verified=True,
        shipment_id=shp3_id,
        payload={"hold_code": "TIB", "details": "Targeted Inspection — hold pending inspection"},
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
        processed_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
    ))

    task3_id = uid()
    db.add(AgentTask(id=task3_id, shipment_id=shp3_id, state="CUSTOMS_HOLD"))

    db.add(AuditLog(
        id=uid(), shipment_id=shp3_id,
        actor="system", event="CBP_HOLD_RECEIVED",
        details={"hold_code": "TIB", "source_verified": True},
    ))
    db.add(AuditLog(
        id=uid(), shipment_id=shp3_id,
        actor="agent", event="CBP_RELEASE_BLOCKED",
        details={"reason": "cbp_released=true requires source_verified official channel"},
    ))

    db.commit()
    print("✅ Seeded: SHP-001 (C01), SHP-002 (C02), SHP-003 (C09)")
    print(f"   SHP-001 id: {shp1_id}")
    print(f"   SHP-002 id: {shp2_id}")
    print(f"   SHP-003 id: {shp3_id}")


if __name__ == "__main__":
    seed()
    db.close()
