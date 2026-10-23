"""
documents/ocr.py — OCR field extraction using Tesseract (with fixture fallback).

Strategy
--------
1. If *use_fixture=True* (demo mode) or Tesseract is not installed, load
   pre-extracted JSON from test_data/ and return it directly.
2. Otherwise: convert the PDF to images with pdf2image, run pytesseract on
   each page, then parse the raw text into structured fields.

Supported doc_types and their extracted fields
-----------------------------------------------
INVOICE        : line_sku, line_quantity, unit_price, total_amount,
                 invoice_number, shipper_name
PACKING_LIST   : line_sku, line_quantity, package_count, gross_weight
BILL_OF_LADING : bl_number, vessel_name, port_of_loading,
                 port_of_discharge, shipper_name
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Tesseract availability check ──────────────────────────────────────────────

_TESSERACT_AVAILABLE: bool | None = None


def _tesseract_available() -> bool:
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            _TESSERACT_AVAILABLE = True
        except Exception:
            _TESSERACT_AVAILABLE = False
            logger.info("Tesseract not available — OCR will use fixture fallback")
    return _TESSERACT_AVAILABLE


# ── Field extraction via Tesseract ────────────────────────────────────────────

def _extract_with_tesseract(file_path: str, doc_type: str) -> dict[str, Any]:
    """Run pdf2image + pytesseract on *file_path* and parse fields for *doc_type*."""
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image

    pages = convert_from_path(file_path, dpi=200)
    full_text = ""
    for page in pages:
        full_text += pytesseract.image_to_string(page) + "\n"

    logger.debug("OCR raw text for %s:\n%s", file_path, full_text[:400])
    return _parse_text(full_text, doc_type)


def _parse_text(text: str, doc_type: str) -> dict[str, Any]:
    """
    Regex-based parser that pulls structured fields from OCR'd text.
    Returns a dict of field → value (string or number) plus a
    'confidence_scores' sub-dict where each field gets 0.0–1.0.
    """
    text_lower = text.lower()
    fields: dict[str, Any] = {}
    confidence: dict[str, float] = {}

    def find_number(patterns: list[str]) -> tuple[float | None, float]:
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                try:
                    return float(m.group(1).replace(",", "")), 0.85
                except ValueError:
                    pass
        return None, 0.0

    def find_text(patterns: list[str]) -> tuple[str | None, float]:
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip(), 0.80
        return None, 0.0

    if doc_type == "INVOICE":
        fields["line_quantity"], confidence["line_quantity"] = find_number(
            [r"quantity[:\s]+(\d[\d,]*)", r"qty[:\s]+(\d[\d,]*)"]
        )
        fields["unit_price"], confidence["unit_price"] = find_number(
            [r"unit\s*price[:\s]+\$?([\d,]+\.?\d*)", r"price[:\s]+\$?([\d,]+\.?\d*)"]
        )
        fields["total_amount"], confidence["total_amount"] = find_number(
            [r"total[:\s]+\$?([\d,]+\.?\d*)", r"amount[:\s]+\$?([\d,]+\.?\d*)"]
        )
        fields["invoice_number"], confidence["invoice_number"] = find_text(
            [r"invoice\s*(?:no|number|#)[:\s]+([A-Z0-9\-]+)"]
        )
        fields["shipper_name"], confidence["shipper_name"] = find_text(
            [r"shipper[:\s]+([^\n]+)", r"seller[:\s]+([^\n]+)"]
        )
        fields["line_sku"], confidence["line_sku"] = find_text(
            [r"sku[:\s]+([A-Z0-9\-]+)", r"item[:\s]+([A-Z0-9\-]+)"]
        )

    elif doc_type == "PACKING_LIST":
        fields["line_quantity"], confidence["line_quantity"] = find_number(
            [r"quantity[:\s]+(\d[\d,]*)", r"qty[:\s]+(\d[\d,]*)"]
        )
        fields["package_count"], confidence["package_count"] = find_number(
            [r"packages?[:\s]+(\d+)", r"cartons?[:\s]+(\d+)", r"boxes?[:\s]+(\d+)"]
        )
        fields["gross_weight"], confidence["gross_weight"] = find_number(
            [r"gross\s*weight[:\s]+([\d,]+\.?\d*)", r"weight[:\s]+([\d,]+\.?\d*)"]
        )
        fields["line_sku"], confidence["line_sku"] = find_text(
            [r"sku[:\s]+([A-Z0-9\-]+)", r"item[:\s]+([A-Z0-9\-]+)"]
        )

    elif doc_type == "BILL_OF_LADING":
        fields["bl_number"], confidence["bl_number"] = find_text(
            [r"b/l\s*(?:no|number|#)?[:\s]+([A-Z0-9\-]+)", r"bill\s*of\s*lading[:\s]+([A-Z0-9\-]+)"]
        )
        fields["vessel_name"], confidence["vessel_name"] = find_text(
            [r"vessel[:\s]+([^\n]+)", r"ship\s*name[:\s]+([^\n]+)"]
        )
        fields["port_of_loading"], confidence["port_of_loading"] = find_text(
            [r"port\s*of\s*loading[:\s]+([^\n]+)", r"loading\s*port[:\s]+([^\n]+)"]
        )
        fields["port_of_discharge"], confidence["port_of_discharge"] = find_text(
            [r"port\s*of\s*discharge[:\s]+([^\n]+)", r"discharge\s*port[:\s]+([^\n]+)"]
        )
        fields["shipper_name"], confidence["shipper_name"] = find_text(
            [r"shipper[:\s]+([^\n]+)"]
        )

    # Remove None-valued fields for cleanliness
    fields = {k: v for k, v in fields.items() if v is not None}
    confidence = {k: v for k, v in confidence.items() if k in fields}

    return {"fields": fields, "confidence_scores": confidence}


# ── Fixture loader ────────────────────────────────────────────────────────────

_FIXTURE_DIR = Path(__file__).parent.parent / "test_data"


def _load_fixture(doc_id: str, doc_type: str) -> dict[str, Any] | None:
    """
    Look for a pre-extracted JSON fixture.
    Search order:
      1. test_data/**/{doc_id}.json          (exact match by ID)
      2. test_data/**/{doc_type.lower()}_extracted.json  (type-based match)
    """
    # Try exact doc_id match first
    for p in _FIXTURE_DIR.rglob(f"{doc_id}.json"):
        with open(p) as f:
            data = json.load(f)
            logger.info("Loaded fixture by doc_id from %s", p)
            return data

    # Fall back to doc_type-based fixture
    name = f"{doc_type.lower()}_extracted.json"
    for p in _FIXTURE_DIR.rglob(name):
        with open(p) as f:
            data = json.load(f)
            logger.info("Loaded fixture by doc_type from %s", p)
            return data

    return None


# ── Public API ────────────────────────────────────────────────────────────────

def extract_fields(
    file_path: str,
    doc_type: str,
    doc_id: str,
    use_fixture: bool = False,
) -> dict[str, Any]:
    """
    Extract structured fields from a document file.

    Args:
        file_path:   Path to the raw file in evidence_store/raw/
        doc_type:    INVOICE | PACKING_LIST | BILL_OF_LADING
        doc_id:      DB document ID (used to find fixtures)
        use_fixture: If True, skip OCR and load pre-extracted JSON instead

    Returns:
        { "fields": {...}, "confidence_scores": {...} }
    """
    # 1. Fixture mode (demo / CI)
    if use_fixture or not _tesseract_available():
        fixture = _load_fixture(doc_id, doc_type)
        if fixture:
            return fixture
        logger.warning(
            "No fixture found for doc_id=%s doc_type=%s — returning empty fields",
            doc_id, doc_type,
        )
        return {"fields": {}, "confidence_scores": {}}

    # 2. Real OCR
    try:
        return _extract_with_tesseract(file_path, doc_type)
    except Exception as exc:
        logger.error("OCR failed for %s: %s — falling back to fixture", file_path, exc)
        fixture = _load_fixture(doc_id, doc_type)
        return fixture if fixture else {"fields": {}, "confidence_scores": {}}
