"""
tests/integration/test_approval_resume.py — Smoke test: HITL approval closes the loop.

Run agent (C02 discrepancy) → approvals created → resolve them → agent resumes:
  all APPROVED → CLEARANCE_VERIFIED
  any REJECTED → RECOVER
  shipment on CBP hold → hold is kept, agent keeps waiting for CBP
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_integration_resume.db"

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, update, delete
from sqlalchemy.orm import sessionmaker

import db.database as _db
_db._engine = None
_db._SessionLocal = None

from db.database import Base, get_db
from api.main import app
from api.models.models import Shipment, Document, AgentAction, AuditLog
import agent.llm_client as llm
import agent.tools as tools
import documents.consistency as consistency

ENGINE = create_engine("sqlite:///./test_integration_resume.db", connect_args={"check_same_thread": False})


# Enforce foreign keys like PostgreSQL does — the old runner's approvals failed exactly here
@event.listens_for(ENGINE, "connect")
def _fk_on(dbapi_conn, _record):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    Base.metadata.create_all(bind=ENGINE)
    app.dependency_overrides[get_db] = override
    # Offline: deterministic mock LLM, shipment context read straight from the test DB
    monkeypatch.setattr(llm, "reason", llm._mock_reason)
    monkeypatch.setattr(llm, "plan", llm._mock_plan)
    monkeypatch.setattr(tools, "get_shipment_status", _shipment_from_db)
    monkeypatch.setattr(tools, "compare_documents", _compare_via_test_client)
    monkeypatch.setattr(consistency, "emit_discrepancy_event", lambda *_a, **_k: None)
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=ENGINE)


client = TestClient(app)


def _shipment_from_db(shipment_id: str) -> dict:
    db = Session()
    shp = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    data = {
        "id": shp.id,
        "reference_number": shp.reference_number,
        "status": shp.status,
        "documents": [{"id": d.id, "doc_type": d.doc_type} for d in shp.documents],
    }
    db.close()
    return data


def _compare_via_test_client(shipment_id: str, invoice_id: str, packing_list_id: str) -> dict:
    return client.post("/api/documents/consistency-check", json={
        "shipment_id": shipment_id, "invoice_doc_id": invoice_id, "packing_list_doc_id": packing_list_id,
    }).json()


def _seed_shipment(status: str = "OBSERVE") -> str:
    db = Session()
    shp = Shipment(id=str(uuid.uuid4()), reference_number=f"RS-{uuid.uuid4().hex[:6]}", status=status)
    db.add(shp)
    db.flush()
    for doc_type in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING"):
        db.add(Document(shipment_id=shp.id, doc_type=doc_type, status="extracted"))
    db.commit()
    sid = shp.id
    db.close()
    return sid


def _run_agent(sid: str) -> dict:
    r = client.post("/api/agent/run", json={"shipment_id": sid, "simulate_discrepancy": True})
    assert r.status_code == 200, r.text
    return r.json()


def _pending(sid: str) -> list[dict]:
    return client.get(f"/api/approvals?shipment_id={sid}&status=PENDING").json()


def _shipment_status(sid: str) -> str:
    return client.get(f"/api/shipments/{sid}").json()["status"]


def _transitions(sid: str) -> list[dict]:
    logs = client.get(f"/api/audit-logs/{sid}").json()
    return [e["details"] for e in logs if e["event"] == "AGENT_TRANSITION"]


def _agent_states(sid: str) -> list[str]:
    return [t["to_state"] for t in _transitions(sid)]


def _cbp_event(sid: str, event_type: str, verified: bool = True):
    r = client.post("/api/events", json={
        "event_id": f"cbp-{uuid.uuid4().hex}",
        "event_type": event_type,
        "shipment_id": sid,
        "source_verified": verified,
        "payload": {},
    })
    assert r.status_code == 201, r.text


def _audit_events(sid: str) -> list[str]:
    return [e["event"] for e in client.get(f"/api/audit-logs/{sid}").json()]


class TestCBPHold:
    """C09 — the agent coordinates a CBP hold but only CBP can release it."""

    def test_hold_event_starts_hold_flow_and_notifies_r4_r5(self):
        sid = _seed_shipment()
        _cbp_event(sid, "CBP_HOLD_RECEIVED")

        assert _shipment_status(sid) == "CUSTOMS_HOLD"
        assert _agent_states(sid) == ["OBSERVE", "CUSTOMS_HOLD", "WAIT_EVENT"]
        assert sorted(a["role"] for a in _pending(sid)) == ["R4", "R5"]

    def test_unverified_hold_event_is_ignored(self):
        sid = _seed_shipment()
        _cbp_event(sid, "CBP_HOLD_RECEIVED", verified=False)
        assert _shipment_status(sid) == "OBSERVE"
        assert "CBP_EVENT_IGNORED" in _audit_events(sid)

    def test_run_agent_on_held_shipment_does_not_duplicate_tasks(self):
        sid = _seed_shipment()
        _cbp_event(sid, "CBP_HOLD_RECEIVED")
        r = client.post("/api/agent/run", json={"shipment_id": sid})
        assert r.json()["final_state"] == "WAIT_EVENT"
        assert len(_pending(sid)) == 2

    def test_unverified_release_is_rejected_by_guard(self):
        sid = _seed_shipment()
        _cbp_event(sid, "CBP_HOLD_RECEIVED")
        _cbp_event(sid, "CBP_RELEASE_RECEIVED", verified=False)

        assert _shipment_status(sid) == "CUSTOMS_HOLD"
        assert "CBP_RELEASE_REJECTED" in _audit_events(sid)
        assert "CLEARANCE_VERIFIED" not in _agent_states(sid)

    def test_verified_release_clears_shipment(self):
        sid = _seed_shipment()
        _cbp_event(sid, "CBP_HOLD_RECEIVED")
        _cbp_event(sid, "CBP_RELEASE_RECEIVED")

        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"
        assert _agent_states(sid)[-2:] == ["VERIFY", "CLEARANCE_VERIFIED"]

    def test_plan_approved_during_hold_clears_on_release(self):
        sid = _seed_shipment(status="CUSTOMS_HOLD")
        _run_agent(sid)
        for a in _pending(sid):
            client.patch(f"/api/approvals/{a['id']}", json={"status": "APPROVED"})
        assert _shipment_status(sid) == "CUSTOMS_HOLD"

        _cbp_event(sid, "CBP_RELEASE_RECEIVED")
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"

    def test_release_with_open_plan_approvals_lifts_hold_only(self):
        sid = _seed_shipment(status="CUSTOMS_HOLD")
        _run_agent(sid)
        _cbp_event(sid, "CBP_RELEASE_RECEIVED")
        assert _shipment_status(sid) == "WAIT_EVENT"

        for a in _pending(sid):
            client.patch(f"/api/approvals/{a['id']}", json={"status": "APPROVED"})
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"

    def test_release_after_blocked_attack_does_not_clear(self):
        sid = _seed_shipment(status="CUSTOMS_HOLD")
        client.post("/api/agent/run", json={"shipment_id": sid, "red_team": True})
        _cbp_event(sid, "CBP_RELEASE_RECEIVED")

        assert _shipment_status(sid) == "RECOVER"
        assert "CBP_HOLD_LIFTED" in _audit_events(sid)
        assert "CLEARANCE_VERIFIED" not in _agent_states(sid)


class TestAuditChain:

    def _verify(self, sid: str) -> dict:
        return client.get(f"/api/audit-logs/{sid}/verify").json()

    def _entry(self, sid: str, kind: str) -> str:
        return next(e["id"] for e in client.get(f"/api/audit-logs/{sid}").json() if e["event"] == kind)

    def test_entries_are_chained_and_verify(self):
        sid = _seed_shipment()
        _run_agent(sid)
        logs = client.get(f"/api/audit-logs/{sid}").json()
        assert all(e["entry_hash"] for e in logs)

        result = self._verify(sid)
        assert result["valid"] is True
        assert result["entries"] == len(logs)
        assert {c["status"] for c in result["chain"]} == {"ok"}

    def test_raw_sql_edit_is_detected(self):
        sid = _seed_shipment()
        _run_agent(sid)
        target = self._entry(sid, "AGENT_TRANSITION")
        db = Session()
        db.execute(update(AuditLog).where(AuditLog.id == target).values(actor="human"))
        db.commit()
        db.close()

        result = self._verify(sid)
        assert result["valid"] is False
        assert result["broken"]["id"] == target
        assert "changed" in result["broken"]["reason"]

    def test_deleted_entry_is_detected(self):
        sid = _seed_shipment()
        _run_agent(sid)
        db = Session()
        db.execute(delete(AuditLog).where(AuditLog.id == self._entry(sid, "AGENT_TRANSITION")))
        db.commit()
        db.close()

        result = self._verify(sid)
        assert result["valid"] is False
        assert "missing" in result["broken"]["reason"]

    def test_rehashed_forgery_is_detected(self):
        """Editing a row AND recomputing its own hash still breaks the next link."""
        from api.audit_chain import compute_hash
        sid = _seed_shipment()
        _run_agent(sid)
        db = Session()
        entry = db.query(AuditLog).filter(AuditLog.id == self._entry(sid, "AGENT_TRANSITION")).one()
        entry.actor = "human"
        entry.entry_hash = compute_hash(entry.prev_hash, entry)
        db.commit()
        db.close()

        assert self._verify(sid)["valid"] is False

    def test_demo_tamper_endpoint_breaks_chain(self):
        sid = _seed_shipment()
        _run_agent(sid)
        first, second = _pending(sid)
        client.patch(f"/api/approvals/{first['id']}", json={"status": "APPROVED"})
        client.patch(f"/api/approvals/{second['id']}", json={"status": "REJECTED"})

        r = client.post(f"/api/demo/tamper-audit/{sid}")
        assert r.status_code == 200
        assert r.json()["event"] == "APPROVAL_REJECTED"
        assert r.json()["after"] == {"event": "APPROVAL_APPROVED"}  # the rejection is hidden
        assert self._verify(sid)["valid"] is False


class TestRedTeam:

    def test_prompt_injection_is_blocked_and_nothing_executes(self):
        sid = _seed_shipment(status="CUSTOMS_HOLD")
        r = client.post("/api/agent/run", json={"shipment_id": sid, "red_team": True})
        assert r.status_code == 200, r.text
        result = r.json()

        assert result["final_state"] == "RECOVER"
        assert "ignore all previous rules" in result["attack_text"]
        blocked = {d["action_type"] for d in result["policy_denials"]}
        assert {"SET_CBP_RELEASED", "MODIFY_DOCUMENT_FIELD"} <= blocked
        assert "ACT" not in _agent_states(sid)
        assert _pending(sid) == []
        assert _shipment_status(sid) == "CUSTOMS_HOLD"

        db = Session()
        assert db.query(AuditLog).filter(AuditLog.event == "POLICY_DENIED").count() == len(blocked)
        db.close()

    @pytest.mark.parametrize("field", ["risk_score", "cbp_released", "source_verified", "force_deny"])
    def test_caller_cannot_set_protected_context(self, field):
        sid = _seed_shipment()
        r = client.post("/api/agent/run", json={"shipment_id": sid, "payload": {field: 0}})
        assert r.status_code == 400
        assert field in r.json()["detail"]


class TestApprovalResume:

    def test_run_creates_one_approval_per_role_linked_to_actions(self):
        sid = _seed_shipment()
        result = _run_agent(sid)
        assert result["final_state"] == "WAIT_EVENT"

        pending = _pending(sid)
        assert sorted(a["role"] for a in pending) == ["R2", "R3"]
        assert all(a["action_id"] for a in pending)
        assert len({a["payload_hash"] for a in pending}) == 1
        assert _shipment_status(sid) == "WAIT_EVENT"

    def test_rerun_with_same_plan_does_not_duplicate_approvals(self):
        sid = _seed_shipment()
        _run_agent(sid)
        _run_agent(sid)
        assert len(_pending(sid)) == 2

    def test_all_approved_resumes_to_clearance(self):
        sid = _seed_shipment()
        _run_agent(sid)
        first, second = _pending(sid)

        client.patch(f"/api/approvals/{first['id']}", json={"status": "APPROVED"})
        # One approval still open — agent keeps waiting
        assert _shipment_status(sid) == "WAIT_EVENT"

        r = client.patch(f"/api/approvals/{second['id']}", json={"status": "APPROVED"})
        assert r.status_code == 200
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"
        assert _agent_states(sid)[-3:] == ["ACT", "VERIFY", "CLEARANCE_VERIFIED"]
        # ACT was reached through the human approval, not auto-allowed as low risk
        events = [t["event"] for t in _transitions(sid)]
        assert "POLICY_APPROVED" in events
        assert "POLICY_ALLOW" not in events

        db = Session()
        assert {a.status for a in db.query(AgentAction).all()} == {"EXECUTED"}
        db.close()

    def test_rejection_moves_agent_to_recover(self):
        sid = _seed_shipment()
        _run_agent(sid)
        first, second = _pending(sid)

        client.patch(f"/api/approvals/{first['id']}", json={"status": "APPROVED"})
        client.patch(f"/api/approvals/{second['id']}", json={"status": "REJECTED"})
        assert _shipment_status(sid) == "RECOVER"
        assert _agent_states(sid)[-1] == "RECOVER"

    def test_cbp_hold_is_not_cleared_by_approval(self):
        sid = _seed_shipment(status="CUSTOMS_HOLD")
        _run_agent(sid)
        for a in _pending(sid):
            client.patch(f"/api/approvals/{a['id']}", json={"status": "APPROVED"})

        assert _shipment_status(sid) == "CUSTOMS_HOLD"
        assert "CLEARANCE_VERIFIED" not in _agent_states(sid)
        db = Session()
        assert db.query(AuditLog).filter(AuditLog.event == "AGENT_WAITING_CBP_RELEASE").count() == 1
        db.close()


class TestDemoReset:

    def test_reset_restores_initial_state_and_keeps_ids(self):
        from db.demo_data import reset_all
        db = Session()
        ids = reset_all(db)
        db.close()
        sid = ids["SHP-002"]

        # Play the C02 demo through to clearance
        _run_agent(sid)
        for a in _pending(sid):
            client.patch(f"/api/approvals/{a['id']}", json={"status": "APPROVED"})
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"

        r = client.post(f"/api/demo/reset/{sid}")
        assert r.status_code == 200
        assert r.json()["reset"] == {"SHP-002": sid}  # same id — open pages keep working
        assert _shipment_status(sid) == "OBSERVE"
        assert _agent_states(sid) == []
        assert _pending(sid) == []  # approvals only appear once the agent proposes a plan
        assert client.get(f"/api/audit-logs/{sid}/verify").json()["valid"] is True

        # …and the demo can be played again
        _run_agent(sid)
        assert _shipment_status(sid) == "WAIT_EVENT"

    def test_reset_all_and_cbp_demo_replays(self):
        sid = client.post("/api/demo/reset").json()["reset"]["SHP-003"]
        _cbp_event(sid, "CBP_RELEASE_RECEIVED")
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"

        assert client.post("/api/demo/reset").json()["reset"]["SHP-003"] == sid
        assert _shipment_status(sid) == "CUSTOMS_HOLD"
        _cbp_event(sid, "CBP_RELEASE_RECEIVED")
        assert _shipment_status(sid) == "CLEARANCE_VERIFIED"

    def test_reset_rejects_non_demo_shipment(self):
        assert client.post(f"/api/demo/reset/{_seed_shipment()}").status_code == 404

    def test_shp002_finds_the_mismatch_without_simulation(self):
        """The real C02 path: the agent compares the documents itself."""
        sid = client.post("/api/demo/reset").json()["reset"]["SHP-002"]
        r = client.post("/api/agent/run", json={"shipment_id": sid})
        assert r.status_code == 200, r.text

        assert r.json()["final_state"] == "WAIT_EVENT"
        assert "DISCREPANCY_DETECTED" in [t["event"] for t in r.json()["transitions"]]
        assert _pending(sid)  # the agent's own plan is waiting for approval
        docs = client.get(f"/api/shipments/{sid}").json()["documents"]
        # Mismatched documents are not marked verified
        assert {d["status"] for d in docs if d["doc_type"] != "BILL_OF_LADING"} == {"extracted"}
