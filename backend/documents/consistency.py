"""
documents/consistency.py — D2 field-level consistency check.

Compares Invoice vs Packing List on these fields (D2 spec):
  - line_sku       : must match exactly
  - line_quantity  : must match exactly (core C02 scenario)
  - unit_price     : Invoice only (no PL equivalent — informational)

Returns a list of Discrepancy objects and an overall PASS/FAIL status.
Also emits a DOCUMENT_DISCREPANCY_DETECTED event to M2 on any mismatch.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, asdict
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = __import__("os").getenv("API_BASE_URL", "http://localhost:8000")

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Discrepancy:
    field: str
    invoice_value: Any
    packing_list_value: Any
    delta: Any           # numeric diff for quantities; None for text fields
    severity: str        # HIGH | MEDIUM | LOW


def _severity(field: str, delta: Any) -> str:
    if field == "line_quantity":
        try:
            pct = abs(float(delta)) / max(abs(float(delta)), 1) * 100
            return "HIGH" if pct > 5 else "MEDIUM"
        except (TypeError, ZeroDivisionError):
            return "HIGH"
    if field == "line_sku":
        return "HIGH"
    return "MEDIUM"


# ── Core compare logic ────────────────────────────────────────────────────────

def compare_fields(
    invoice_fields: dict[str, Any],
    packing_list_fields: dict[str, Any],
) -> list[Discrepancy]:
    """
    Compare D2 fields between *invoice_fields* and *packing_list_fields*.

    Returns a list of Discrepancy objects (empty = PASS).
    """
    mismatches: list[Discrepancy] = []

    # line_sku
    inv_sku = invoice_fields.get("line_sku")
    pl_sku = packing_list_fields.get("line_sku")
    if inv_sku is not None and pl_sku is not None and str(inv_sku) != str(pl_sku):
        mismatches.append(Discrepancy(
            field="line_sku",
            invoice_value=inv_sku,
            packing_list_value=pl_sku,
            delta=None,
            severity=_severity("line_sku", None),
        ))

    # line_quantity
    inv_qty = invoice_fields.get("line_quantity")
    pl_qty = packing_list_fields.get("line_quantity")
    if inv_qty is not None and pl_qty is not None:
        try:
            inv_num = float(inv_qty)
            pl_num = float(pl_qty)
            if inv_num != pl_num:
                delta = inv_num - pl_num
                mismatches.append(Discrepancy(
                    field="line_quantity",
                    invoice_value=inv_num,
                    packing_list_value=pl_num,
                    delta=delta,
                    severity=_severity("line_quantity", delta),
                ))
        except (ValueError, TypeError):
            # Non-numeric quantities — treat as mismatch if different string
            if str(inv_qty) != str(pl_qty):
                mismatches.append(Discrepancy(
                    field="line_quantity",
                    invoice_value=inv_qty,
                    packing_list_value=pl_qty,
                    delta=None,
                    severity="HIGH",
                ))

    return mismatches


# ── Event emission ────────────────────────────────────────────────────────────

def emit_discrepancy_event(
    shipment_id: str,
    mismatches: list[Discrepancy],
) -> None:
    """
    POST a DOCUMENT_DISCREPANCY_DETECTED event to M2's /api/events endpoint.
    Fires only when there are actual mismatches.
    Best-effort — failures are logged but do not raise.
    """
    if not mismatches:
        return
    try:
        payload = {
            "event_id": f"disc-{uuid.uuid4()}",
            "event_type": "DOCUMENT_DISCREPANCY_DETECTED",
            "source_verified": False,
            "shipment_id": shipment_id,
            "payload": {
                "mismatches": [asdict(m) for m in mismatches],
                "mismatch_count": len(mismatches),
            },
        }
        resp = httpx.post(f"{API_BASE}/api/events", json=payload, timeout=5.0)
        resp.raise_for_status()
        logger.info(
            "Emitted DOCUMENT_DISCREPANCY_DETECTED for shipment %s (%d mismatches)",
            shipment_id, len(mismatches),
        )
    except Exception as exc:
        logger.warning(
            "Failed to emit DOCUMENT_DISCREPANCY_DETECTED for %s: %s",
            shipment_id, exc,
        )


# ── Public API ────────────────────────────────────────────────────────────────

def run_consistency_check(
    shipment_id: str,
    invoice_fields: dict[str, Any],
    packing_list_fields: dict[str, Any],
    emit_event: bool = True,
) -> dict[str, Any]:
    """
    Run the full D2 consistency check and optionally emit an event.

    Returns:
        {
            "shipment_id": str,
            "mismatches": [ {field, invoice_value, packing_list_value, delta, severity}, ... ],
            "overall_status": "PASS" | "FAIL",
        }
    """
    mismatches = compare_fields(invoice_fields, packing_list_fields)

    if mismatches and emit_event:
        emit_discrepancy_event(shipment_id, mismatches)

    return {
        "shipment_id": shipment_id,
        "mismatches": [asdict(m) for m in mismatches],
        "overall_status": "FAIL" if mismatches else "PASS",
    }
