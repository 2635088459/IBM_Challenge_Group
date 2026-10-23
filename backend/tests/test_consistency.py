"""
tests/test_consistency.py — Unit tests for D2 field-level consistency check.

Tests:
  1. qty_match          — identical quantities → PASS, no mismatches
  2. qty_mismatch       — Invoice 500 vs PL 480 → FAIL, one mismatch
  3. sku_mismatch       — different SKUs → FAIL
  4. both_mismatch      — qty AND sku differ → FAIL, two mismatches
  5. missing_field      — field absent on one side → no false positive
  6. severity_high      — large qty delta classifies as HIGH
  7. fixture_c02        — load real SHP-002 fixtures and confirm FAIL
  8. no_emit_on_pass    — emit_event=False on PASS doesn't raise
"""
import json
from pathlib import Path

import pytest

from documents.consistency import compare_fields, run_consistency_check, Discrepancy


# ── Helpers ───────────────────────────────────────────────────────────────────

INVOICE_500 = {
    "invoice_number": "INV-001",
    "line_sku": "SKU-ELEC-7788",
    "line_quantity": 500,
    "unit_price": 12.50,
    "total_amount": 6250.00,
}

PL_480 = {
    "line_sku": "SKU-ELEC-7788",
    "line_quantity": 480,
    "package_count": 24,
    "gross_weight": 120.0,
}

PL_500 = {**PL_480, "line_quantity": 500}

PL_WRONG_SKU = {**PL_480, "line_sku": "SKU-ELEC-9999"}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCompareFields:

    def test_qty_match_returns_no_mismatches(self):
        mismatches = compare_fields(INVOICE_500, PL_500)
        assert mismatches == []

    def test_qty_mismatch_invoice_500_vs_pl_480(self):
        mismatches = compare_fields(INVOICE_500, PL_480)
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m.field == "line_quantity"
        assert m.invoice_value == 500.0
        assert m.packing_list_value == 480.0
        assert m.delta == 20.0

    def test_qty_mismatch_severity_is_high(self):
        mismatches = compare_fields(INVOICE_500, PL_480)
        assert mismatches[0].severity == "HIGH"

    def test_sku_mismatch_detected(self):
        mismatches = compare_fields(INVOICE_500, PL_WRONG_SKU)
        sku_mismatches = [m for m in mismatches if m.field == "line_sku"]
        assert len(sku_mismatches) == 1
        assert sku_mismatches[0].severity == "HIGH"

    def test_both_mismatch_returns_two_discrepancies(self):
        pl_both_wrong = {**PL_480, "line_sku": "SKU-WRONG"}
        mismatches = compare_fields(INVOICE_500, pl_both_wrong)
        fields = {m.field for m in mismatches}
        assert "line_quantity" in fields
        assert "line_sku" in fields

    def test_missing_qty_on_one_side_no_false_positive(self):
        """If a field is only present on one side, no mismatch is raised."""
        inv = {"line_sku": "SKU-A"}     # no line_quantity
        pl = {"line_quantity": 100}      # no line_sku
        mismatches = compare_fields(inv, pl)
        assert mismatches == []

    def test_exact_match_sku_and_qty(self):
        inv = {"line_sku": "SKU-X", "line_quantity": 200}
        pl = {"line_sku": "SKU-X", "line_quantity": 200}
        assert compare_fields(inv, pl) == []


class TestRunConsistencyCheck:

    def test_pass_result_has_correct_structure(self):
        result = run_consistency_check(
            shipment_id="SHP-TEST",
            invoice_fields=INVOICE_500,
            packing_list_fields=PL_500,
            emit_event=False,
        )
        assert result["overall_status"] == "PASS"
        assert result["mismatches"] == []
        assert result["shipment_id"] == "SHP-TEST"

    def test_fail_result_on_qty_mismatch(self):
        result = run_consistency_check(
            shipment_id="SHP-TEST",
            invoice_fields=INVOICE_500,
            packing_list_fields=PL_480,
            emit_event=False,
        )
        assert result["overall_status"] == "FAIL"
        assert len(result["mismatches"]) == 1
        m = result["mismatches"][0]
        assert m["field"] == "line_quantity"
        assert m["invoice_value"] == 500.0
        assert m["packing_list_value"] == 480.0
        assert m["delta"] == 20.0

    def test_fail_result_on_sku_mismatch(self):
        result = run_consistency_check(
            shipment_id="SHP-TEST",
            invoice_fields=INVOICE_500,
            packing_list_fields=PL_WRONG_SKU,
            emit_event=False,
        )
        assert result["overall_status"] == "FAIL"

    def test_c02_fixture_data_produces_fail(self):
        """End-to-end test using the real SHP-002 fixture files."""
        fixture_dir = Path(__file__).parent.parent / "test_data" / "SHP-002"
        inv_path = fixture_dir / "invoice_extracted.json"
        pl_path = fixture_dir / "packing_list_extracted.json"

        assert inv_path.exists(), "SHP-002 invoice fixture missing"
        assert pl_path.exists(), "SHP-002 packing list fixture missing"

        inv_fields = json.loads(inv_path.read_text())["fields"]
        pl_fields = json.loads(pl_path.read_text())["fields"]

        result = run_consistency_check(
            shipment_id="SHP-002",
            invoice_fields=inv_fields,
            packing_list_fields=pl_fields,
            emit_event=False,
        )
        assert result["overall_status"] == "FAIL"
        qty_mismatch = next(
            (m for m in result["mismatches"] if m["field"] == "line_quantity"), None
        )
        assert qty_mismatch is not None
        assert qty_mismatch["invoice_value"] == 500
        assert qty_mismatch["packing_list_value"] == 480
        assert qty_mismatch["delta"] == 20
