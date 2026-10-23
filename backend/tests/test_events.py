"""
test_events.py — Tests for event ingestion and deduplication.
Uses an in-memory SQLite database via FastAPI dependency override.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_events.db"

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Reset lazy globals before importing app so our engine is used
import db.database as _db_module
_db_module._engine = None
_db_module._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_events.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def _create_shipment():
    db = TestingSessionLocal()
    s = Shipment(id=str(uuid.uuid4()), reference_number=f"T-{uuid.uuid4().hex[:6]}", status="OBSERVE")
    db.add(s)
    db.commit()
    db.refresh(s)
    sid = s.id
    db.close()
    return sid


def test_ingest_event_success():
    shipment_id = _create_shipment()
    response = client.post("/api/events", json={
        "event_id": "evt-001",
        "event_type": "CARGO_ARRIVED",
        "source_verified": False,
        "shipment_id": shipment_id,
        "payload": {"carrier": "MOCK"},
        "occurred_at": "2026-10-20T10:00:00Z",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["event_id"] == "evt-001"
    assert data["processed_at"] is not None


def test_duplicate_event_returns_409():
    shipment_id = _create_shipment()
    payload = {
        "event_id": "evt-duplicate",
        "event_type": "CARGO_ARRIVED",
        "source_verified": False,
        "shipment_id": shipment_id,
    }
    r1 = client.post("/api/events", json=payload)
    assert r1.status_code == 201

    r2 = client.post("/api/events", json=payload)
    assert r2.status_code == 409
    assert "already processed" in r2.json()["detail"]


def test_event_missing_event_id_returns_422():
    response = client.post("/api/events", json={
        "event_type": "CARGO_ARRIVED",
    })
    assert response.status_code == 422


def test_event_unknown_shipment_returns_404():
    response = client.post("/api/events", json={
        "event_id": "evt-no-ship",
        "event_type": "CARGO_ARRIVED",
        "shipment_id": "00000000-0000-0000-0000-000000000000",
    })
    assert response.status_code == 404
