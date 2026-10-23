"""
test_guards.py — Negative tests for the agent's guard layer.

Covers:
  1. cbp_released=True cannot be set autonomously (G-CBP authority invariant)
  2. ACT is blocked when approval is pending/missing (G-approval)
  3. MODIFY_DOCUMENT_FIELD action is always denied (G-doc-immutable)
  4. PolicyCheckEngine returns correct decisions across the risk spectrum
  5. FSM start() is blocked without a shipment in context (G1)
  6. FSM full flows: C02 (Quantity Mismatch) and C09 (CBP Hold)
"""
import pytest

from agent.fsm import AgentFSM, AgentState, GuardFailedError, PermissionDeniedError
from agent.guards import (
    GuardResult,
    g1_shipment_exists,
    g7_low_risk,
    g8_approval_required,
    g9_deny,
    g_cbp_release_authority,
    g_approval_exists,
    g_document_immutable,
)
from agent.policy import PolicyCheckEngine, PolicyDecision


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_fsm(extra_context: dict | None = None) -> AgentFSM:
    ctx = {"shipment_id": "SHP-TEST-001"}
    if extra_context:
        ctx.update(extra_context)
    return AgentFSM(shipment_id="SHP-TEST-001", context=ctx)


# ══════════════════════════════════════════════════════════════════════════════
# G-CBP: Authority Invariant
# ══════════════════════════════════════════════════════════════════════════════

class TestCbpReleaseGuard:

    def test_cbp_released_blocked_when_source_not_verified(self):
        """Agent CANNOT set cbp_released=True when source_verified=False."""
        result = g_cbp_release_authority(source_verified=False)
        assert result.passed is False
        assert "source_verified=False" in result.reason

    def test_cbp_released_allowed_when_source_verified(self):
        """cbp_released=True IS allowed when source_verified=True (official channel)."""
        result = g_cbp_release_authority(source_verified=True)
        assert result.passed is True

    def test_fsm_raises_permission_denied_on_autonomous_cbp_release(self):
        """FSM.set_cbp_released(False) must raise PermissionDeniedError."""
        fsm = make_fsm()
        with pytest.raises(PermissionDeniedError) as exc_info:
            fsm.set_cbp_released(source_verified=False)
        assert "cbp_released" in exc_info.value.action
        assert "source_verified=False" in str(exc_info.value)

    def test_fsm_allows_cbp_release_with_source_verified(self):
        """FSM.set_cbp_released(True) succeeds and sets context flag."""
        fsm = make_fsm()
        fsm.set_cbp_released(source_verified=True)
        assert fsm.context.get("cbp_released") is True

    def test_cbp_hold_event_ignored_without_source_verified(self):
        """CBP_HOLD_RECEIVED without source_verified stays in OBSERVE state."""
        fsm = make_fsm({"source_verified": False})
        fsm.start()  # INITIALIZE → OBSERVE
        # Manually place FSM in OBSERVE so we can inject the event
        state = fsm.process_event("CBP_HOLD_RECEIVED", {"source_verified": False})
        # Should stay in OBSERVE, not move to CUSTOMS_HOLD
        assert state == AgentState.OBSERVE

    def test_cbp_hold_event_accepted_with_source_verified(self):
        """CBP_HOLD_RECEIVED with source_verified=True transitions to CUSTOMS_HOLD."""
        fsm = make_fsm({"source_verified": True})
        fsm.start()  # INITIALIZE → OBSERVE
        state = fsm.process_event("CBP_HOLD_RECEIVED", {"source_verified": True})
        assert state == AgentState.CUSTOMS_HOLD


# ══════════════════════════════════════════════════════════════════════════════
# G-approval: ACT blocked without approval
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalGuard:

    def test_act_blocked_when_approval_pending(self):
        """g_approval_exists fails when approval_status is not APPROVED."""
        for bad_status in [None, "PENDING", "REJECTED"]:
            result = g_approval_exists({
                "approval_required": True,
                "approval_status": bad_status,
            })
            assert result.passed is False, f"Expected fail for status={bad_status}"

    def test_act_blocked_when_approval_expired(self):
        result = g_approval_exists({
            "approval_required": True,
            "approval_status": "EXPIRED",
        })
        assert result.passed is False
        assert "EXPIRED" in result.reason

    def test_act_allowed_when_approval_approved(self):
        result = g_approval_exists({
            "approval_required": True,
            "approval_status": "APPROVED",
        })
        assert result.passed is True

    def test_act_allowed_when_no_approval_required(self):
        """If approval_required is False, guard passes regardless."""
        result = g_approval_exists({"approval_required": False})
        assert result.passed is True


# ══════════════════════════════════════════════════════════════════════════════
# G-doc-immutable: Document field modification is always denied
# ══════════════════════════════════════════════════════════════════════════════

class TestDocumentImmutableGuard:

    def test_modify_document_field_is_denied(self):
        result = g_document_immutable({"action_type": "MODIFY_DOCUMENT_FIELD"})
        assert result.passed is False

    def test_other_action_types_pass(self):
        for action_type in ["REQUEST_DOCUMENT", "NOTIFY_COMPLIANCE", "SUBMIT_ENTRY"]:
            result = g_document_immutable({"action_type": action_type})
            assert result.passed is True, f"Expected pass for {action_type}"

    def test_fsm_propose_action_raises_on_modify_document(self):
        """AgentFSM.propose_action() raises PermissionDeniedError for MODIFY_DOCUMENT_FIELD."""
        fsm = make_fsm({"risk_score": 0.1})
        with pytest.raises(PermissionDeniedError) as exc_info:
            fsm.propose_action({"action_type": "MODIFY_DOCUMENT_FIELD"})
        assert "MODIFY_DOCUMENT_FIELD" in exc_info.value.action


# ══════════════════════════════════════════════════════════════════════════════
# PolicyCheckEngine: G7 / G8 / G9 decisions
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicyCheckEngine:
    engine = PolicyCheckEngine()

    def test_low_risk_returns_allow(self):
        decision = self.engine.evaluate(
            action={"action_type": "SEND_NOTIFICATION"},
            context={"risk_score": 0.1},
        )
        assert decision == PolicyDecision.ALLOW

    def test_medium_risk_returns_approval_required(self):
        decision = self.engine.evaluate(
            action={"action_type": "REQUEST_DOCUMENT"},
            context={"risk_score": 0.5},
        )
        assert decision == PolicyDecision.APPROVAL_REQUIRED

    def test_high_risk_returns_deny(self):
        decision = self.engine.evaluate(
            action={"action_type": "SUBMIT_ENTRY"},
            context={"risk_score": 0.9},
        )
        assert decision == PolicyDecision.DENY

    def test_force_deny_returns_deny(self):
        decision = self.engine.evaluate(
            action={"action_type": "ANYTHING"},
            context={"force_deny": True},
        )
        assert decision == PolicyDecision.DENY

    def test_document_modification_returns_deny(self):
        decision = self.engine.evaluate(
            action={"action_type": "MODIFY_DOCUMENT_FIELD"},
            context={"risk_score": 0.1},
        )
        assert decision == PolicyDecision.DENY

    def test_fsm_propose_action_deny_raises(self):
        """FSM.propose_action() raises PermissionDeniedError on DENY decision."""
        fsm = make_fsm({"risk_score": 0.95})
        with pytest.raises(PermissionDeniedError):
            fsm.propose_action({"action_type": "SUBMIT_ENTRY"})


# ══════════════════════════════════════════════════════════════════════════════
# G1: FSM cannot start without shipment_id
# ══════════════════════════════════════════════════════════════════════════════

class TestG1Guard:

    def test_g1_passes_with_shipment_id(self):
        result = g1_shipment_exists({"shipment_id": "SHP-001"})
        assert result.passed is True

    def test_g1_fails_without_shipment_id(self):
        result = g1_shipment_exists({})
        assert result.passed is False

    def test_fsm_start_blocked_without_shipment(self):
        fsm = AgentFSM(shipment_id="", context={})
        with pytest.raises(GuardFailedError) as exc_info:
            fsm.start()
        assert "G1" in exc_info.value.guard_name


# ══════════════════════════════════════════════════════════════════════════════
# Full FSM flows (no I/O — pure state machine)
# ══════════════════════════════════════════════════════════════════════════════

class TestFSMFlows:

    def test_c02_quantity_mismatch_flow(self):
        """
        C02: INITIALIZE → OBSERVE → REASON → PLAN → POLICY_CHECK → ESCALATE → WAIT_EVENT
        """
        transitions = []

        def record(t):
            transitions.append((t.from_state, t.to_state))

        fsm = AgentFSM(
            shipment_id="SHP-002",
            context={"shipment_id": "SHP-002", "has_discrepancy": True, "risk_score": 0.5},
            on_transition=record,
        )

        # Boot
        fsm.start()
        assert fsm.current_state == AgentState.OBSERVE

        # Discrepancy triggers REASON
        fsm.process_event("DISCREPANCY_DETECTED")
        assert fsm.current_state == AgentState.REASON

        fsm.process_event("REASON_DONE")
        assert fsm.current_state == AgentState.PLAN

        fsm.process_event("PLAN_DONE")
        assert fsm.current_state == AgentState.POLICY_CHECK

        # G8: APPROVAL_REQUIRED → ESCALATE
        fsm.process_event("POLICY_APPROVAL_REQUIRED")
        assert fsm.current_state == AgentState.ESCALATE

        fsm.process_event("ESCALATE_DONE")
        assert fsm.current_state == AgentState.WAIT_EVENT

        # After human approves
        fsm.process_event("APPROVAL_RECEIVED")
        assert fsm.current_state == AgentState.OBSERVE

        # Verify history was recorded
        assert len(transitions) >= 7

    def test_c09_cbp_hold_flow(self):
        """
        C09: INITIALIZE → OBSERVE → CUSTOMS_HOLD → WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED
        """
        fsm = AgentFSM(
            shipment_id="SHP-003",
            context={"shipment_id": "SHP-003", "source_verified": True},
        )

        fsm.start()
        assert fsm.current_state == AgentState.OBSERVE

        # CBP hold arrives with source_verified=True
        fsm.process_event("CBP_HOLD_RECEIVED", {"source_verified": True})
        assert fsm.current_state == AgentState.CUSTOMS_HOLD

        # Tasks created, move to wait
        fsm.process_event("CBP_HOLD_ESCALATE")
        assert fsm.current_state == AgentState.WAIT_EVENT

        # Official CBP release arrives
        fsm.process_event("CBP_RELEASE_RECEIVED", {"source_verified": True})
        assert fsm.current_state == AgentState.VERIFY
        assert fsm.context.get("cbp_released") is True

        # Verification passes
        fsm.process_event("VERIFY_PASS")
        assert fsm.current_state == AgentState.CLEARANCE_VERIFIED

    def test_c09_cbp_hold_agent_cannot_self_release(self):
        """
        Key negative test: agent in CUSTOMS_HOLD cannot set cbp_released autonomously.
        """
        fsm = AgentFSM(
            shipment_id="SHP-003",
            context={"shipment_id": "SHP-003", "source_verified": False},
        )
        fsm.start()
        fsm.process_event("CBP_HOLD_RECEIVED", {"source_verified": True})
        assert fsm.current_state == AgentState.CUSTOMS_HOLD

        # Attempt to release without source_verified
        with pytest.raises(PermissionDeniedError):
            fsm.set_cbp_released(source_verified=False)

        # cbp_released must NOT be set
        assert fsm.context.get("cbp_released") is not True

    def test_transition_history_recorded(self):
        """Every transition is stored in fsm.history."""
        fsm = make_fsm()
        fsm.start()
        fsm.process_event("OBSERVE_DONE")
        assert len(fsm.history) == 2
        assert fsm.history[0].from_state == AgentState.INITIALIZE
        assert fsm.history[0].to_state == AgentState.OBSERVE
        assert fsm.history[1].from_state == AgentState.OBSERVE
        assert fsm.history[1].to_state == AgentState.REASON
