"""
tests/integration/test_duplicate_event.py — Smoke test: duplicate event rejection.

Verifies that posting the same event_id twice returns 409 Conflict.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_integration_dup.db"

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as _db
_db._engine = None
_db._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment

ENGINE = create_engine("sqlite:///./test_integration_dup.db", connect_args={"check_same_thread": False})
Session = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup():
    Base.metadata.create_all(bind=ENGINE)
    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=ENGINE)


client = TestClient(app)


def _make_shipment() -> str:
    db = Session()
    s = Shipment(id=str(uuid.uuid4()), reference_number=f"DE-{uuid.uuid4().hex[:6]}", status="OBSERVE")
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    return sid


class TestDuplicateEventRejection:

    def test_first_event_accepted(self):
        sid = _make_shipment()
        r = client.post("/api/events", json={
            "event_id": "test-event-001",
            "event_type": "CARGO_ARRIVED",
            "source_verified": False,
            "shipment_id": sid,
        })
        assert r.status_code == 201

    def test_second_identical_event_id_returns_409(self):
        """Core smoke test: same event_id → 409 Conflict."""
        sid = _make_shipment()
        payload = {
            "event_id": "test-event-001-dup",
            "event_type": "CARGO_ARRIVED",
            "source_verified": False,
            "shipment_id": sid,
        }
        r1 = client.post("/api/events", json=payload)
        assert r1.status_code == 201

        r2 = client.post("/api/events", json=payload)
        assert r2.status_code == 409
        assert "already processed" in r2.json()["detail"]

    def test_cbp_hold_duplicate_rejected(self):
        """CBP hold event with source_verified=True is also deduplicated."""
        sid = _make_shipment()
        payload = {
            "event_id": "cbp-hold-smoke-001",
            "event_type": "CBP_HOLD_RECEIVED",
            "source_verified": True,
            "shipment_id": sid,
            "payload": {"hold_code": "TIB"},
        }
        r1 = client.post("/api/events", json=payload)
        assert r1.status_code == 201
        assert r1.json()["source_verified"] is True

        r2 = client.post("/api/events", json=payload)
        assert r2.status_code == 409

    def test_different_event_ids_are_accepted(self):
        """Different event_ids for the same type are all accepted."""
        sid = _make_shipment()
        for i in range(3):
            r = client.post("/api/events", json={
                "event_id": f"unique-event-{i}-{uuid.uuid4()}",
                "event_type": "CARGO_ARRIVED",
                "shipment_id": sid,
            })
            assert r.status_code == 201

    def test_missing_event_id_returns_422(self):
        """event_id is required — omitting it returns 422 Unprocessable."""
        r = client.post("/api/events", json={"event_type": "CARGO_ARRIVED"})
        assert r.status_code == 422
