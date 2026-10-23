"""
tests/test_hasher.py — Tests for SHA-256 hashing and deduplication logic.

Tests:
  1. sha256 returns correct hex digest
  2. sha256 is deterministic (same bytes → same hash)
  3. different bytes → different hash
  4. find_by_hash returns None when no match in DB
  5. find_by_hash returns existing record on hash match
  6. next_version returns 1 for a new shipment/doc_type
  7. next_version increments correctly on second upload
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_hasher.db"

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as _db_module
_db_module._engine = None
_db_module._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment, Document
from documents.hasher import sha256, find_by_hash, next_version

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_hasher.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _db():
    return TestingSessionLocal()


def _make_shipment(db):
    s = Shipment(id=str(uuid.uuid4()), reference_number=f"H-{uuid.uuid4().hex[:6]}", status="OBSERVE")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── SHA-256 ───────────────────────────────────────────────────────────────────

class TestSha256:

    def test_returns_64_char_hex_string(self):
        result = sha256(b"hello world")
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        data = b"customs clearance demo"
        assert sha256(data) == sha256(data)

    def test_different_bytes_different_hash(self):
        assert sha256(b"abc") != sha256(b"xyz")

    def test_known_value(self):
        # echo -n "" | sha256sum → e3b0c44298fc1c149afbf4c8996fb924…
        assert sha256(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ── find_by_hash ──────────────────────────────────────────────────────────────

class TestFindByHash:

    def test_returns_none_when_not_found(self):
        db = _db()
        result = find_by_hash(db, "nonexistent_hash_abc123")
        assert result is None
        db.close()

    def test_returns_existing_document_on_match(self):
        db = _db()
        shp = _make_shipment(db)
        doc = Document(
            id=str(uuid.uuid4()),
            shipment_id=shp.id,
            doc_type="INVOICE",
            file_hash="abc123def456",
            version=1,
            status="raw",
        )
        db.add(doc)
        db.commit()

        found = find_by_hash(db, "abc123def456")
        assert found is not None
        assert found.id == doc.id
        db.close()

    def test_different_hash_returns_none(self):
        db = _db()
        shp = _make_shipment(db)
        doc = Document(
            id=str(uuid.uuid4()),
            shipment_id=shp.id,
            doc_type="INVOICE",
            file_hash="hash_A",
            version=1,
            status="raw",
        )
        db.add(doc)
        db.commit()

        assert find_by_hash(db, "hash_B") is None
        db.close()


# ── next_version ──────────────────────────────────────────────────────────────

class TestNextVersion:

    def test_returns_1_for_new_doc_type(self):
        db = _db()
        shp = _make_shipment(db)
        version = next_version(db, shp.id, "INVOICE")
        assert version == 1
        db.close()

    def test_returns_2_after_first_upload(self):
        db = _db()
        shp = _make_shipment(db)
        doc = Document(
            id=str(uuid.uuid4()),
            shipment_id=shp.id,
            doc_type="INVOICE",
            file_hash="first_hash",
            version=1,
            status="raw",
        )
        db.add(doc)
        db.commit()

        version = next_version(db, shp.id, "INVOICE")
        assert version == 2
        db.close()

    def test_different_doc_type_starts_at_1(self):
        db = _db()
        shp = _make_shipment(db)
        doc = Document(
            id=str(uuid.uuid4()),
            shipment_id=shp.id,
            doc_type="INVOICE",
            file_hash="inv_hash",
            version=1,
            status="raw",
        )
        db.add(doc)
        db.commit()

        # PACKING_LIST should still start at version 1
        version = next_version(db, shp.id, "PACKING_LIST")
        assert version == 1
        db.close()

    def test_multiple_versions_increment_correctly(self):
        db = _db()
        shp = _make_shipment(db)
        for i in range(1, 4):
            doc = Document(
                id=str(uuid.uuid4()),
                shipment_id=shp.id,
                doc_type="BILL_OF_LADING",
                file_hash=f"hash_v{i}",
                version=i,
                status="raw",
            )
            db.add(doc)
        db.commit()

        assert next_version(db, shp.id, "BILL_OF_LADING") == 4
        db.close()
