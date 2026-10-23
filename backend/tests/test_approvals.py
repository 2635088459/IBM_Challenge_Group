"""
test_approvals.py — Tests for the approval lifecycle.
Uses an in-memory SQLite database via FastAPI dependency override.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_approvals.db"

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as _db_module
_db_module._engine = None
_db_module._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment, AgentTask, AgentAction, Approval

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_approvals.db"
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


def _seed_shipment_with_task():
    db = TestingSessionLocal()
    shp = Shipment(id=str(uuid.uuid4()), reference_number=f"T-{uuid.uuid4().hex[:6]}", status="ESCALATE")
    db.add(shp)
    db.flush()
    task = AgentTask(id=str(uuid.uuid4()), shipment_id=shp.id, state="ESCALATE")
    db.add(task)
    db.flush()
    action = AgentAction(
        id=str(uuid.uuid4()),
        task_id=task.id,
        action_type="REQUEST_APPROVAL",
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        status="PENDING",
    )
    db.add(action)
    db.commit()
    result = {"shipment_id": shp.id, "task_id": task.id, "action_id": action.id}
    db.close()
    return result


def test_create_approval():
    ids = _seed_shipment_with_task()
    response = client.post("/api/approvals", json={
        "action_id": ids["action_id"],
        "shipment_id": ids["shipment_id"],
        "role": "R2",
        "payload_hash": "abc123",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["role"] == "R2"


def test_approve_approval():
    ids = _seed_shipment_with_task()
    create_r = client.post("/api/approvals", json={
        "action_id": ids["action_id"],
        "shipment_id": ids["shipment_id"],
        "role": "R2",
    })
    approval_id = create_r.json()["id"]

    patch_r = client.patch(f"/api/approvals/{approval_id}", json={"status": "APPROVED"})
    assert patch_r.status_code == 200
    assert patch_r.json()["status"] == "APPROVED"
    assert patch_r.json()["resolved_at"] is not None


def test_reject_approval():
    ids = _seed_shipment_with_task()
    create_r = client.post("/api/approvals", json={
        "action_id": ids["action_id"],
        "shipment_id": ids["shipment_id"],
        "role": "R3",
    })
    approval_id = create_r.json()["id"]

    patch_r = client.patch(f"/api/approvals/{approval_id}", json={"status": "REJECTED"})
    assert patch_r.status_code == 200
    assert patch_r.json()["status"] == "REJECTED"


def test_double_resolve_returns_409():
    ids = _seed_shipment_with_task()
    create_r = client.post("/api/approvals", json={
        "action_id": ids["action_id"],
        "shipment_id": ids["shipment_id"],
        "role": "R4",
    })
    approval_id = create_r.json()["id"]

    client.patch(f"/api/approvals/{approval_id}", json={"status": "APPROVED"})
    second = client.patch(f"/api/approvals/{approval_id}", json={"status": "APPROVED"})
    assert second.status_code == 409


def test_stale_approval_returns_expired():
    """Approval older than 30 minutes should return 409 approval_expired."""
    ids = _seed_shipment_with_task()
    db = TestingSessionLocal()
    old_approval = Approval(
        id=str(uuid.uuid4()),
        action_id=ids["action_id"],
        shipment_id=ids["shipment_id"],
        role="R5",
        status="PENDING",
        requested_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
    )
    db.add(old_approval)
    db.commit()
    aid = old_approval.id
    db.close()

    response = client.patch(f"/api/approvals/{aid}", json={"status": "APPROVED"})
    assert response.status_code == 409
    assert response.json()["detail"] == "approval_expired"


def test_list_approvals_by_shipment():
    ids = _seed_shipment_with_task()
    client.post("/api/approvals", json={
        "action_id": ids["action_id"],
        "shipment_id": ids["shipment_id"],
        "role": "R2",
    })
    response = client.get(f"/api/approvals?shipment_id={ids['shipment_id']}&status=PENDING")
    assert response.status_code == 200
    assert len(response.json()) >= 1
