"""
tests/integration/test_stale_approval.py — Smoke test: stale approval expiry.

Verifies that approvals older than 30 minutes return 409 approval_expired.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_integration_stale.db"

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as _db
_db._engine = None
_db._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment, AgentTask, AgentAction, Approval

ENGINE = create_engine("sqlite:///./test_integration_stale.db", connect_args={"check_same_thread": False})
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


def _seed_stale_approval(age_hours: float = 2.0) -> str:
    """Insert an approval with requested_at set back *age_hours* hours."""
    db = Session()
    shp = Shipment(id=str(uuid.uuid4()), reference_number=f"SA-{uuid.uuid4().hex[:6]}", status="ESCALATE")
    db.add(shp)
    db.flush()
    task = AgentTask(id=str(uuid.uuid4()), shipment_id=shp.id, state="ESCALATE")
    db.add(task)
    db.flush()
    action = AgentAction(
        id=str(uuid.uuid4()), task_id=task.id,
        action_type="REQUEST_APPROVAL", idempotency_key=f"sa-{uuid.uuid4().hex}",
    )
    db.add(action)
    db.flush()
    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=age_hours)
    approval = Approval(
        id=str(uuid.uuid4()),
        action_id=action.id,
        shipment_id=shp.id,
        role="R2",
        status="PENDING",
        requested_at=old_time,
    )
    db.add(approval)
    db.commit()
    aid = approval.id
    db.close()
    return aid


class TestStaleApproval:

    def test_2_hour_old_approval_returns_409_expired(self):
        """Approval 2 hours old → 409 approval_expired."""
        aid = _seed_stale_approval(age_hours=2.0)
        r = client.patch(f"/api/approvals/{aid}", json={"status": "APPROVED"})
        assert r.status_code == 409
        assert r.json()["detail"] == "approval_expired"

    def test_31_minute_old_approval_returns_expired(self):
        """Just over the 30-minute threshold → expired."""
        aid = _seed_stale_approval(age_hours=31 / 60)
        r = client.patch(f"/api/approvals/{aid}", json={"status": "APPROVED"})
        assert r.status_code == 409
        assert r.json()["detail"] == "approval_expired"

    def test_fresh_approval_can_be_approved(self):
        """A just-created approval (< 1 minute old) should succeed."""
        db = Session()
        shp = Shipment(id=str(uuid.uuid4()), reference_number=f"FR-{uuid.uuid4().hex[:6]}", status="ESCALATE")
        db.add(shp)
        db.flush()
        task = AgentTask(id=str(uuid.uuid4()), shipment_id=shp.id, state="ESCALATE")
        db.add(task)
        db.flush()
        action = AgentAction(
            id=str(uuid.uuid4()), task_id=task.id,
            action_type="REQUEST_APPROVAL", idempotency_key=f"fr-{uuid.uuid4().hex}",
        )
        db.add(action)
        db.commit()
        action_id = action.id
        shp_id = shp.id
        db.close()

        create_r = client.post("/api/approvals", json={
            "action_id": action_id,
            "shipment_id": shp_id,
            "role": "R3",
        })
        assert create_r.status_code == 201
        aid = create_r.json()["id"]

        patch_r = client.patch(f"/api/approvals/{aid}", json={"status": "APPROVED"})
        assert patch_r.status_code == 200
        assert patch_r.json()["status"] == "APPROVED"

    def test_expired_approval_status_updated_to_expired_in_db(self):
        """After a 409 expiry, the DB record should show status=EXPIRED."""
        aid = _seed_stale_approval(age_hours=2.0)
        client.patch(f"/api/approvals/{aid}", json={"status": "APPROVED"})

        # Fetch it — it should now be EXPIRED
        get_r = client.get(f"/api/approvals?status=EXPIRED")
        ids = [a["id"] for a in get_r.json()]
        assert aid in ids
