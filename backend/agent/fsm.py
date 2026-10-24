"""
agent/fsm.py — Core Finite State Machine for the Autonomous Customs Clearance Agent.

States:
    INITIALIZE → OBSERVE → REASON → PLAN → POLICY_CHECK → ACT → VERIFY
                                                         ↘ ESCALATE
                              ↕                           ↕
                        COLLECT_DATA              WAIT_EVENT
                              ↕
                        CUSTOMS_HOLD → WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED
                              ↕
                           RECOVER

Guard layer sits between every transition — no state change can bypass it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from agent.guards import (
    GuardResult,
    g1_shipment_exists,
    g7_low_risk,
    g8_approval_required,
    g9_deny,
    g_cbp_release_authority,
)
from agent.policy import PolicyDecision, PolicyCheckEngine

logger = logging.getLogger(__name__)


# ── State Enum ────────────────────────────────────────────────────────────────

class AgentState(str, Enum):
    INITIALIZE         = "INITIALIZE"
    OBSERVE            = "OBSERVE"
    REASON             = "REASON"
    PLAN               = "PLAN"
    POLICY_CHECK       = "POLICY_CHECK"
    ACT                = "ACT"
    VERIFY             = "VERIFY"
    WAIT_EVENT         = "WAIT_EVENT"
    COLLECT_DATA       = "COLLECT_DATA"
    ESCALATE           = "ESCALATE"
    CUSTOMS_HOLD       = "CUSTOMS_HOLD"
    CLEARANCE_VERIFIED = "CLEARANCE_VERIFIED"
    RECOVER            = "RECOVER"


# ── Custom exceptions ─────────────────────────────────────────────────────────

class GuardFailedError(Exception):
    """Raised when a guard condition blocks a transition."""
    def __init__(self, guard_name: str, reason: str):
        self.guard_name = guard_name
        self.reason = reason
        super().__init__(f"Guard {guard_name} failed: {reason}")


class PermissionDeniedError(Exception):
    """Raised when the agent attempts an action it is not authorised to perform."""
    def __init__(self, action: str, reason: str):
        self.action = action
        self.reason = reason
        super().__init__(f"Permission denied for '{action}': {reason}")


class InvalidTransitionError(Exception):
    """Raised when a requested transition is not valid from the current state."""


# ── Transition log entry ──────────────────────────────────────────────────────

@dataclass
class TransitionRecord:
    from_state: AgentState
    to_state: AgentState
    event: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "event": self.event,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


# ── FSM ───────────────────────────────────────────────────────────────────────

class AgentFSM:
    """
    Deterministic Finite State Machine for a single shipment's clearance lifecycle.

    Usage:
        fsm = AgentFSM(shipment_id="SHP-002", context={...})
        fsm.start()                          # INITIALIZE → OBSERVE (via G1)
        fsm.process_event("OBSERVE_DONE")    # drive the machine forward
    """

    # Valid transitions: {from_state: [allowed_to_states]}
    TRANSITIONS: dict[AgentState, list[AgentState]] = {
        AgentState.INITIALIZE:         [AgentState.OBSERVE],
        AgentState.OBSERVE:            [AgentState.REASON, AgentState.COLLECT_DATA, AgentState.CUSTOMS_HOLD],
        AgentState.REASON:             [AgentState.PLAN, AgentState.RECOVER],
        AgentState.PLAN:               [AgentState.POLICY_CHECK, AgentState.RECOVER],
        AgentState.POLICY_CHECK:       [AgentState.ACT, AgentState.ESCALATE, AgentState.RECOVER],
        AgentState.ACT:                [AgentState.VERIFY, AgentState.RECOVER],
        AgentState.VERIFY:             [AgentState.CLEARANCE_VERIFIED, AgentState.RECOVER, AgentState.OBSERVE],
        AgentState.WAIT_EVENT:         [AgentState.OBSERVE, AgentState.VERIFY, AgentState.RECOVER],
        AgentState.COLLECT_DATA:       [AgentState.OBSERVE, AgentState.ESCALATE, AgentState.WAIT_EVENT],
        AgentState.ESCALATE:           [AgentState.WAIT_EVENT, AgentState.RECOVER],
        AgentState.CUSTOMS_HOLD:       [AgentState.WAIT_EVENT, AgentState.RECOVER],
        AgentState.CLEARANCE_VERIFIED: [],  # terminal
        AgentState.RECOVER:            [AgentState.OBSERVE, AgentState.ESCALATE],
    }

    def __init__(
        self,
        shipment_id: str,
        context: dict[str, Any] | None = None,
        on_transition: Callable[[TransitionRecord], None] | None = None,
    ):
        self.shipment_id = shipment_id
        self.context: dict[str, Any] = context or {}
        self.current_state: AgentState = AgentState.INITIALIZE
        self.history: list[TransitionRecord] = []
        self._on_transition = on_transition  # callback for Socket.IO / test hooks
        self._policy = PolicyCheckEngine()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> AgentState:
        """
        Boot the FSM: INITIALIZE → OBSERVE.
        Guard G1: shipment record must exist in context.
        """
        result = g1_shipment_exists(self.context)
        if not result.passed:
            raise GuardFailedError("G1", result.reason)
        return self._do_transition(AgentState.OBSERVE, event="AGENT_STARTED", reason=result.reason)

    def resume_from(self, state: AgentState) -> None:
        """
        Restore the state a previous run stopped in (loaded from agent_tasks.state).
        Used when an external event, e.g. a resolved approval, wakes the agent up.
        """
        self.current_state = state

    def process_event(self, event: str, payload: dict[str, Any] | None = None) -> AgentState:
        """
        Drive the FSM forward based on an incoming event name.
        This is the primary entry point for the event-driven run loop.
        """
        if payload:
            self.context.update(payload)

        handler = self._event_handlers.get(event)
        if handler is None:
            logger.warning("No handler for event '%s' in state %s", event, self.current_state)
            return self.current_state

        return handler(self, event)

    def set_cbp_released(self, source_verified: bool) -> None:
        """
        The ONLY path to set cbp_released=true.
        Guard G-cbp: source_verified must be True — the agent cannot call this autonomously.
        Raises PermissionDeniedError if source_verified is False.
        """
        result = g_cbp_release_authority(source_verified)
        if not result.passed:
            raise PermissionDeniedError(
                action="set_cbp_released",
                reason=result.reason,
            )
        self.context["cbp_released"] = True
        logger.info("cbp_released set to True for shipment %s (source_verified=True)", self.shipment_id)

    def propose_action(self, action: dict[str, Any]) -> PolicyDecision:
        """
        Run a proposed action through the PolicyCheckEngine before ACT.
        Returns ALLOW, APPROVAL_REQUIRED, or DENY.
        Raises PermissionDeniedError on DENY.
        """
        # Hard guard: agent can NEVER directly modify document field values
        if action.get("action_type") == "MODIFY_DOCUMENT_FIELD":
            raise PermissionDeniedError(
                action="MODIFY_DOCUMENT_FIELD",
                reason="Agents cannot autonomously modify document field values (hard guard)",
            )

        decision = self._policy.evaluate(action, self.context)

        if decision == PolicyDecision.DENY:
            raise PermissionDeniedError(
                action=action.get("action_type", "UNKNOWN"),
                reason=self._policy.last_reason,
            )
        return decision

    # ── Internal transition engine ────────────────────────────────────────────

    def _do_transition(self, to_state: AgentState, event: str, reason: str) -> AgentState:
        allowed = self.TRANSITIONS.get(self.current_state, [])
        if to_state not in allowed:
            raise InvalidTransitionError(
                f"Transition {self.current_state} → {to_state} is not allowed"
            )

        record = TransitionRecord(
            from_state=self.current_state,
            to_state=to_state,
            event=event,
            reason=reason,
        )
        self.history.append(record)

        logger.info(
            "[%s] %s → %s  (event=%s, reason=%s)",
            self.shipment_id, self.current_state.value, to_state.value, event, reason,
        )

        self.current_state = to_state

        if self._on_transition:
            try:
                self._on_transition(record)
            except Exception:
                logger.exception("on_transition callback raised an exception")

        return self.current_state

    # ── Event handlers ────────────────────────────────────────────────────────
    # Each handler receives (self, event_name) and returns the new state.

    def _handle_observe_done(self, event: str) -> AgentState:
        """OBSERVE → REASON: observations collected, send to LLM for analysis."""
        return self._do_transition(AgentState.REASON, event=event, reason="Observations ready for LLM reasoning")

    def _handle_discrepancy_detected(self, event: str) -> AgentState:
        """OBSERVE → REASON: document discrepancy found (e.g. C02 qty mismatch)."""
        return self._do_transition(AgentState.REASON, event=event, reason="Document discrepancy detected, escalating to LLM")

    def _handle_reason_done(self, event: str) -> AgentState:
        """REASON → PLAN: LLM analysis complete."""
        return self._do_transition(AgentState.PLAN, event=event, reason="LLM analysis complete")

    def _handle_plan_done(self, event: str) -> AgentState:
        """PLAN → POLICY_CHECK: action plan proposed, run through policy engine."""
        return self._do_transition(AgentState.POLICY_CHECK, event=event, reason="Action plan ready for policy check")

    def _handle_policy_allow(self, event: str) -> AgentState:
        """POLICY_CHECK → ACT: G7 low-risk, proceed autonomously."""
        return self._do_transition(AgentState.ACT, event=event, reason="G7: ALLOW — low-risk action approved")

    def _handle_policy_approval_required(self, event: str) -> AgentState:
        """POLICY_CHECK → ESCALATE: G8 medium-risk, human approval required."""
        return self._do_transition(AgentState.ESCALATE, event=event, reason="G8: APPROVAL_REQUIRED — human sign-off needed")

    def _handle_policy_deny(self, event: str) -> AgentState:
        """POLICY_CHECK → RECOVER: G9 hard block."""
        return self._do_transition(AgentState.RECOVER, event=event, reason="DENY — plan blocked by guardrails, nothing executed")

    def _handle_act_done(self, event: str) -> AgentState:
        """ACT → VERIFY: action executed, verify outcome."""
        return self._do_transition(AgentState.VERIFY, event=event, reason="Action executed, verifying outcome")

    def _handle_verify_pass(self, event: str) -> AgentState:
        """VERIFY → CLEARANCE_VERIFIED: all checks passed."""
        return self._do_transition(AgentState.CLEARANCE_VERIFIED, event=event, reason="All checks passed — clearance verified")

    def _handle_verify_fail(self, event: str) -> AgentState:
        """VERIFY → OBSERVE: verification failed, re-observe."""
        return self._do_transition(AgentState.OBSERVE, event=event, reason="Verification failed — re-observing")

    def _handle_escalate_done(self, event: str) -> AgentState:
        """ESCALATE → WAIT_EVENT: approval request sent, waiting for human response."""
        return self._do_transition(AgentState.WAIT_EVENT, event=event, reason="Approval request sent — waiting for human decision")

    def _handle_approval_received(self, event: str) -> AgentState:
        """WAIT_EVENT → OBSERVE: human approved, resume processing."""
        return self._do_transition(AgentState.OBSERVE, event=event, reason="Human approval received — resuming")

    def _handle_approval_rejected(self, event: str) -> AgentState:
        """WAIT_EVENT → RECOVER: human rejected the proposed plan."""
        return self._do_transition(AgentState.RECOVER, event=event, reason="Human rejected the proposed plan")

    def _handle_approved_analysis_loaded(self, event: str) -> AgentState:
        """OBSERVE → REASON: reuse the analysis the human reviewed instead of calling the LLM again."""
        return self._do_transition(AgentState.REASON, event=event, reason="Reusing the analysis the human reviewed — no new LLM call")

    def _handle_approved_plan_loaded(self, event: str) -> AgentState:
        """REASON → PLAN: reuse the plan the human approved."""
        return self._do_transition(AgentState.PLAN, event=event, reason="Reusing the human-approved plan")

    def _handle_policy_approved(self, event: str) -> AgentState:
        """POLICY_CHECK → ACT: G-approval passed — plan approved by a human and unchanged since."""
        return self._do_transition(AgentState.ACT, event=event, reason="G-approval: plan approved by human, payload hash verified")

    def _handle_missing_document(self, event: str) -> AgentState:
        """OBSERVE → COLLECT_DATA: required document missing."""
        return self._do_transition(AgentState.COLLECT_DATA, event=event, reason="Required document missing")

    def _handle_collect_done(self, event: str) -> AgentState:
        """COLLECT_DATA → OBSERVE: data collected, re-observe."""
        return self._do_transition(AgentState.OBSERVE, event=event, reason="Data collected — re-observing")

    def _handle_cbp_hold_received(self, event: str) -> AgentState:
        """OBSERVE → CUSTOMS_HOLD: CBP hold event ingested (source_verified required)."""
        source_verified = self.context.get("source_verified", False)
        if not source_verified:
            logger.warning("CBP_HOLD_RECEIVED without source_verified=true — ignoring")
            return self.current_state
        return self._do_transition(
            AgentState.CUSTOMS_HOLD, event=event,
            reason="CBP hold event received (source_verified=True)",
        )

    def _handle_cbp_hold_escalate(self, event: str) -> AgentState:
        """CUSTOMS_HOLD → WAIT_EVENT: evidence tasks created, notified R4/R5."""
        return self._do_transition(AgentState.WAIT_EVENT, event=event, reason="CBP hold tasks created — waiting for resolution")

    def _handle_cbp_release_received(self, event: str) -> AgentState:
        """WAIT_EVENT → VERIFY: official CBP release received, verify clearance."""
        # set_cbp_released enforces the authority guard — will raise if not source_verified
        source_verified = self.context.get("source_verified", False)
        self.set_cbp_released(source_verified)
        return self._do_transition(AgentState.VERIFY, event=event, reason="CBP release received (source_verified=True) — verifying")

    def _handle_error(self, event: str) -> AgentState:
        """Any state → RECOVER on unhandled error."""
        current_allowed = self.TRANSITIONS.get(self.current_state, [])
        if AgentState.RECOVER in current_allowed:
            return self._do_transition(AgentState.RECOVER, event=event, reason="Error encountered — entering recovery")
        return self.current_state

    # ── Event → handler dispatch table ───────────────────────────────────────

    _event_handlers: dict[str, Callable[["AgentFSM", str], AgentState]] = {
        "OBSERVE_DONE":              _handle_observe_done,
        "DISCREPANCY_DETECTED":      _handle_discrepancy_detected,
        "REASON_DONE":               _handle_reason_done,
        "PLAN_DONE":                 _handle_plan_done,
        "POLICY_ALLOW":              _handle_policy_allow,
        "POLICY_APPROVAL_REQUIRED":  _handle_policy_approval_required,
        "POLICY_DENY":               _handle_policy_deny,
        "POLICY_APPROVED":           _handle_policy_approved,
        "ACT_DONE":                  _handle_act_done,
        "VERIFY_PASS":               _handle_verify_pass,
        "VERIFY_FAIL":               _handle_verify_fail,
        "ESCALATE_DONE":             _handle_escalate_done,
        "APPROVAL_RECEIVED":         _handle_approval_received,
        "APPROVAL_REJECTED":         _handle_approval_rejected,
        "APPROVED_ANALYSIS_LOADED":  _handle_approved_analysis_loaded,
        "APPROVED_PLAN_LOADED":      _handle_approved_plan_loaded,
        "MISSING_DOCUMENT":          _handle_missing_document,
        "COLLECT_DONE":              _handle_collect_done,
        "CBP_HOLD_RECEIVED":         _handle_cbp_hold_received,
        "CBP_HOLD_ESCALATE":         _handle_cbp_hold_escalate,
        "CBP_RELEASE_RECEIVED":      _handle_cbp_release_received,
        "ERROR":                     _handle_error,
    }
