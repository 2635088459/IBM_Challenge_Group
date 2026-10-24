"""
documents/router.py — FastAPI routes for M4 document processing.

Routes:
  POST /api/documents/upload               — ingest + hash a file
  POST /api/documents/{doc_id}/extract     — run OCR / load fixture
  POST /api/documents/consistency-check    — D2 field compare
  GET  /api/evidence/{shipment_id}         — full evidence chain
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from db.database import get_db
from api.models.models import Document, Shipment, AuditLog
from documents import hasher, ocr, evidence_store
from documents.consistency import run_consistency_check

router = APIRouter(tags=["documents"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── POST /api/documents/upload ────────────────────────────────────────────────

@router.post("/api/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    shipment_id: Annotated[str, Form()],
    doc_type: Annotated[str, Form()],
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Accept a multipart upload, hash the file, deduplicate, persist to evidence_store.
    """
    valid_types = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING"}
    if doc_type not in valid_types:
        raise HTTPException(400, f"doc_type must be one of {valid_types}")

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    file_bytes = await file.read()
    file_hash = hasher.sha256(file_bytes)

    # Deduplication: same hash → return existing record
    existing = hasher.find_by_hash(db, file_hash)
    if existing:
        return {
            "doc_id": existing.id,
            "file_hash": existing.file_hash,
            "doc_type": existing.doc_type,
            "version": existing.version,
            "status": existing.status,
            "deduplicated": True,
        }

    # Versioning: next version for this doc_type on this shipment
    version = hasher.next_version(db, shipment_id, doc_type)

    # Persist raw bytes to evidence_store
    raw_path = evidence_store.save_raw(
        file_bytes=file_bytes,
        shipment_id=shipment_id,
        doc_type=doc_type,
        file_hash=file_hash,
        original_filename=file.filename or f"{doc_type}.pdf",
    )

    # Insert DB record
    doc = Document(
        id=str(uuid.uuid4()),
        shipment_id=shipment_id,
        doc_type=doc_type,
        file_hash=file_hash,
        version=version,
        status="raw",
        uploaded_at=_now(),
    )
    db.add(doc)
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        shipment_id=shipment_id,
        actor="system",
        event="DOCUMENT_UPLOADED",
        details={"doc_type": doc_type, "version": version, "file_hash": file_hash},
    ))
    db.commit()
    db.refresh(doc)

    return {
        "doc_id": doc.id,
        "file_hash": doc.file_hash,
        "doc_type": doc.doc_type,
        "version": doc.version,
        "status": doc.status,
        "raw_path": raw_path,
        "deduplicated": False,
    }


# ── POST /api/documents/{doc_id}/extract ─────────────────────────────────────

@router.post("/api/documents/{doc_id}/extract")
def extract_document(
    doc_id: str,
    use_fixture: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Run OCR extraction on a previously uploaded document.
    Pass ?use_fixture=true for demo mode (no Tesseract needed).
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Resolve raw file path
    raw_file_path = evidence_store.raw_path(
        shipment_id=doc.shipment_id,
        doc_type=doc.doc_type,
        file_hash=doc.file_hash or "",
    )

    # Extract
    result = ocr.extract_fields(
        file_path=raw_file_path,
        doc_type=doc.doc_type,
        doc_id=doc_id,
        use_fixture=use_fixture,
    )

    # Persist to evidence_store/extracted/
    evidence_store.save_extracted(doc_id, result)

    # Update DB status
    doc.status = "extracted"
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        shipment_id=doc.shipment_id,
        actor="system",
        event="DOCUMENT_EXTRACTED",
        details={"doc_id": doc_id, "doc_type": doc.doc_type, "field_count": len(result.get("fields", {}))},
    ))
    db.commit()

    return {
        "doc_id": doc_id,
        "doc_type": doc.doc_type,
        "extracted_fields": result.get("fields", {}),
        "confidence_scores": result.get("confidence_scores", {}),
    }


# ── POST /api/documents/consistency-check ────────────────────────────────────

@router.post("/api/documents/consistency-check")
def consistency_check(
    body: dict[str, Any],
    use_fixture: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Compare Invoice vs Packing List fields for a shipment (D2 check).

    Body: { shipment_id, invoice_doc_id, packing_list_doc_id }
    Pass ?use_fixture=true to use pre-extracted JSON fixtures (demo mode).
    """
    shipment_id = body.get("shipment_id")
    invoice_id = body.get("invoice_doc_id")
    pl_id = body.get("packing_list_doc_id")

    if not all([shipment_id, invoice_id, pl_id]):
        raise HTTPException(400, "shipment_id, invoice_doc_id, and packing_list_doc_id are required")

    # Verify docs exist
    invoice_doc = db.query(Document).filter(Document.id == invoice_id).first()
    pl_doc = db.query(Document).filter(Document.id == pl_id).first()
    if not invoice_doc:
        raise HTTPException(404, f"Invoice document {invoice_id} not found")
    if not pl_doc:
        raise HTTPException(404, f"Packing list document {pl_id} not found")

    # Load extracted fields — from evidence_store or fixture
    def _get_fields(doc: Document) -> dict[str, Any]:
        stored = evidence_store.load_extracted(doc.id)
        if stored:
            return stored.get("fields", {})
        # Try fixture
        fixture = ocr._load_fixture(doc.id, doc.doc_type)
        if fixture:
            return fixture.get("fields", {})
        return {}

    invoice_fields = _get_fields(invoice_doc)
    pl_fields = _get_fields(pl_doc)

    # If use_fixture is set and fields are still empty, load named fixtures directly
    if use_fixture and (not invoice_fields or not pl_fields):
        from pathlib import Path
        import json
        fixture_dir = Path(__file__).parent.parent / "test_data"
        inv_fixture = fixture_dir / "SHP-002" / "invoice_extracted.json"
        pl_fixture = fixture_dir / "SHP-002" / "packing_list_extracted.json"
        if inv_fixture.exists() and not invoice_fields:
            invoice_fields = json.loads(inv_fixture.read_text()).get("fields", {})
        if pl_fixture.exists() and not pl_fields:
            pl_fields = json.loads(pl_fixture.read_text()).get("fields", {})

    result = run_consistency_check(
        shipment_id=shipment_id,
        invoice_fields=invoice_fields,
        packing_list_fields=pl_fields,
        emit_event=True,
    )

    # Documents count as verified only when they agree with each other
    if result["overall_status"] == "PASS":
        for doc in [invoice_doc, pl_doc]:
            doc.status = "verified"
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        shipment_id=shipment_id,
        actor="system",
        event="CONSISTENCY_CHECK_COMPLETED",
        details={"overall_status": result["overall_status"], "mismatch_count": len(result["mismatches"])},
    ))
    db.commit()

    # Save report
    evidence_store.save_consistency_report(shipment_id, result)

    return result


# ── GET /api/evidence/{shipment_id} ──────────────────────────────────────────

@router.get("/api/evidence/{shipment_id}")
def get_evidence(shipment_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Return the full evidence chain (raw → extracted → verified) for all
    documents belonging to *shipment_id*. Used by M3's Evidence Trail panel.
    """
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(404, "Shipment not found")

    docs = (
        db.query(Document)
        .filter(Document.shipment_id == shipment_id)
        .order_by(Document.uploaded_at.asc())
        .all()
    )

    document_chains = []
    for doc in docs:
        chain = evidence_store.build_evidence_chain(
            doc_id=doc.id,
            doc_type=doc.doc_type,
            file_hash=doc.file_hash,
            db_status=doc.status,
            shipment_id=shipment_id,
            uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else "",
        )
        document_chains.append({
            "doc_id": doc.id,
            "doc_type": doc.doc_type,
            "version": doc.version,
            "chain": chain,
        })

    return {
        "shipment_id": shipment_id,
        "reference_number": shipment.reference_number,
        "documents": document_chains,
    }
