"""
test_idempotency.py — Tests for agent_actions idempotency key enforcement.
Uses an in-memory SQLite database via FastAPI dependency override.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_idempotency.db"

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as _db_module
_db_module._engine = None
_db_module._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment, AgentTask

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_idempotency.db"
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


def _seed_task():
    db = TestingSessionLocal()
    shp = Shipment(id=str(uuid.uuid4()), reference_number=f"I-{uuid.uuid4().hex[:6]}", status="OBSERVE")
    db.add(shp)
    db.flush()
    task = AgentTask(id=str(uuid.uuid4()), shipment_id=shp.id, state="ACT")
    db.add(task)
    db.commit()
    tid = task.id
    db.close()
    return tid


def test_first_action_created():
    task_id = _seed_task()
    response = client.post("/api/agent-actions", json={
        "task_id": task_id,
        "action_type": "SUBMIT_ENTRY",
        "idempotency_key": "idem-key-001",
        "payload": {"entry_number": "ENT-001"},
    })
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["idempotency_key"] == "idem-key-001"
    assert data["action_type"] == "SUBMIT_ENTRY"


def test_duplicate_key_returns_200_with_same_record():
    task_id = _seed_task()
    payload = {
        "task_id": task_id,
        "action_type": "SUBMIT_ENTRY",
        "idempotency_key": "idem-key-dup",
        "payload": {"entry_number": "ENT-002"},
    }
    r1 = client.post("/api/agent-actions", json=payload)
    r2 = client.post("/api/agent-actions", json=payload)

    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["idempotency_key"] == r2.json()["idempotency_key"]


def test_different_keys_create_different_records():
    task_id = _seed_task()
    r1 = client.post("/api/agent-actions", json={
        "task_id": task_id,
        "action_type": "COLLECT_DATA",
        "idempotency_key": "idem-key-A",
    })
    r2 = client.post("/api/agent-actions", json={
        "task_id": task_id,
        "action_type": "COLLECT_DATA",
        "idempotency_key": "idem-key-B",
    })
    assert r1.json()["id"] != r2.json()["id"]


def test_missing_idempotency_key_returns_422():
    task_id = _seed_task()
    response = client.post("/api/agent-actions", json={
        "task_id": task_id,
        "action_type": "SUBMIT_ENTRY",
    })
    assert response.status_code == 422
