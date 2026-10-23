"""
documents/hasher.py — SHA-256 file hashing and document deduplication.

Responsibilities:
  - Compute a SHA-256 hex digest from raw file bytes
  - Check the documents table for an existing record with the same hash
    (deduplication: same bytes → same document, no re-insert)
  - Determine the next version number when the same doc_type is re-uploaded
    for the same shipment
"""
from __future__ import annotations

import hashlib
from sqlalchemy.orm import Session
from api.models.models import Document


def sha256(data: bytes) -> str:
    """Return the hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def find_by_hash(db: Session, file_hash: str) -> Document | None:
    """
    Return the existing Document record with *file_hash*, or None.
    Used for deduplication — same bytes should never produce a second record.
    """
    return db.query(Document).filter(Document.file_hash == file_hash).first()


def next_version(db: Session, shipment_id: str, doc_type: str) -> int:
    """
    Return the next version number for *doc_type* on *shipment_id*.
    If no prior version exists, returns 1.
    """
    latest = (
        db.query(Document)
        .filter(
            Document.shipment_id == shipment_id,
            Document.doc_type == doc_type,
        )
        .order_by(Document.version.desc())
        .first()
    )
    return (latest.version + 1) if latest else 1
