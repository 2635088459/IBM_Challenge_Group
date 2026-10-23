"""
documents/evidence_store.py — File I/O for the three evidence stages.

Directory layout inside EVIDENCE_STORE_ROOT:
  raw/       {shipment_id}/{doc_type}_{hash[:8]}{ext}   — original uploaded file
  extracted/ {doc_id}.json                               — OCR field output
  verified/  {shipment_id}_consistency.json              — D2 consistency report

All paths are relative to EVIDENCE_STORE_ROOT (env var, defaults to ./evidence_store).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVIDENCE_STORE_ROOT = Path(
    os.getenv("EVIDENCE_STORE_ROOT", str(Path(__file__).parent.parent / "evidence_store"))
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Raw stage ─────────────────────────────────────────────────────────────────

def save_raw(
    file_bytes: bytes,
    shipment_id: str,
    doc_type: str,
    file_hash: str,
    original_filename: str,
) -> str:
    """
    Persist raw uploaded bytes.

    Returns the absolute path string where the file was saved.
    """
    ext = Path(original_filename).suffix or ".bin"
    dest_dir = EVIDENCE_STORE_ROOT / "raw" / shipment_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{doc_type}_{file_hash[:8]}{ext}"
    dest.write_bytes(file_bytes)
    logger.debug("Saved raw file: %s", dest)
    return str(dest)


def raw_path(shipment_id: str, doc_type: str, file_hash: str, ext: str = ".pdf") -> str:
    """Reconstruct the expected raw path for an existing document."""
    return str(
        EVIDENCE_STORE_ROOT / "raw" / shipment_id / f"{doc_type}_{file_hash[:8]}{ext}"
    )


# ── Extracted stage ───────────────────────────────────────────────────────────

def save_extracted(doc_id: str, extracted: dict[str, Any]) -> str:
    """
    Persist OCR-extracted fields as JSON.

    Returns the absolute path string.
    """
    dest_dir = EVIDENCE_STORE_ROOT / "extracted"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{doc_id}.json"
    payload = {**extracted, "_saved_at": _now_iso()}
    dest.write_text(json.dumps(payload, indent=2))
    logger.debug("Saved extracted: %s", dest)
    return str(dest)


def load_extracted(doc_id: str) -> dict[str, Any] | None:
    """Load extracted fields for *doc_id*, or None if not yet extracted."""
    path = EVIDENCE_STORE_ROOT / "extracted" / f"{doc_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ── Verified stage ────────────────────────────────────────────────────────────

def save_consistency_report(shipment_id: str, report: dict[str, Any]) -> str:
    """
    Persist the D2 consistency report for a shipment.

    Returns the absolute path string.
    """
    dest_dir = EVIDENCE_STORE_ROOT / "verified"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{shipment_id}_consistency.json"
    payload = {**report, "_saved_at": _now_iso()}
    dest.write_text(json.dumps(payload, indent=2))
    logger.debug("Saved consistency report: %s", dest)
    return str(dest)


def load_consistency_report(shipment_id: str) -> dict[str, Any] | None:
    """Load the consistency report for *shipment_id*, or None."""
    path = EVIDENCE_STORE_ROOT / "verified" / f"{shipment_id}_consistency.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ── Evidence chain builder ────────────────────────────────────────────────────

def build_evidence_chain(
    doc_id: str,
    doc_type: str,
    file_hash: str | None,
    db_status: str,
    shipment_id: str,
    uploaded_at: str,
) -> list[dict[str, Any]]:
    """
    Build the raw → extracted → verified chain for one document.

    Each step is included only if that stage has been completed.
    """
    chain: list[dict[str, Any]] = []

    # Stage 1: raw (always present once uploaded)
    chain.append({
        "stage": "raw",
        "file_hash": file_hash,
        "timestamp": uploaded_at,
    })

    # Stage 2: extracted
    extracted = load_extracted(doc_id)
    if extracted or db_status in ("extracted", "verified"):
        entry: dict[str, Any] = {
            "stage": "extracted",
            "timestamp": extracted.get("_saved_at", uploaded_at) if extracted else uploaded_at,
        }
        if extracted:
            entry["fields"] = extracted.get("fields", {})
            entry["confidence_scores"] = extracted.get("confidence_scores", {})
        chain.append(entry)

    # Stage 3: verified
    if db_status == "verified":
        report = load_consistency_report(shipment_id)
        chain.append({
            "stage": "verified",
            "consistency": report.get("overall_status", "UNKNOWN") if report else "UNKNOWN",
            "timestamp": report.get("_saved_at", uploaded_at) if report else uploaded_at,
        })

    return chain
