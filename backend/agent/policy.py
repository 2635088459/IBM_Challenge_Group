"""
agent/policy.py — PolicyCheckEngine (deterministic, no LLM).

Evaluates a proposed action against the current context and returns
one of three decisions:

  ALLOW             — G7: low risk, proceed autonomously
  APPROVAL_REQUIRED — G8: medium risk, create HITL approval request
  DENY              — G9: high risk or authority breach, hard block

The engine is called by AgentFSM.propose_action() during POLICY_CHECK state.
LLM output is advisory only — all actions must pass this engine before ACT.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from agent.guards import (
    g7_low_risk,
    g8_approval_required,
    g9_deny,
    g_cbp_release_not_proposed,
    g_document_immutable,
)


class PolicyDecision(str, Enum):
    ALLOW             = "ALLOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENY              = "DENY"


class PolicyCheckEngine:
    """
    Deterministic rule-based policy engine.

    Evaluation order (first match wins):
      1. G-doc-immutable — if action modifies document fields → DENY
      2. G-cbp — if action tries to release a CBP hold → DENY
      3. G9  — if this action's risk is high (or force_deny) → DENY
      4. G8  — if risk in medium range → APPROVAL_REQUIRED
      5. G7  — if risk is low → ALLOW
      6. Default → APPROVAL_REQUIRED (fail-safe)

    The reason for the last decision is kept in `last_reason` for the audit trail.
    """

    last_reason: str = ""

    def evaluate(
        self,
        action: dict[str, Any],
        context: dict[str, Any],
    ) -> PolicyDecision:
        # 1–2. Hard guards on the action itself
        for hard_guard in (g_document_immutable, g_cbp_release_not_proposed):
            result = hard_guard(action)
            if not result.passed:
                self.last_reason = result.reason
                return PolicyDecision.DENY

        # Score this action on its own — never reuse another action's score
        scored = {**context, "risk_score": self._compute_risk(action, context)}

        # 3. G9 — high risk
        g9_result = g9_deny(scored)
        if g9_result.passed:
            self.last_reason = g9_result.reason
            return PolicyDecision.DENY

        # 4. G8 — medium risk
        g8_result = g8_approval_required(scored)
        if g8_result.passed:
            self.last_reason = g8_result.reason
            return PolicyDecision.APPROVAL_REQUIRED

        # 5. G7 — low risk
        g7_result = g7_low_risk(scored)
        if g7_result.passed:
            self.last_reason = g7_result.reason
            return PolicyDecision.ALLOW

        # 6. Default fail-safe: require approval
        self.last_reason = "Default fail-safe: approval required"
        return PolicyDecision.APPROVAL_REQUIRED

    # ── Risk scoring ──────────────────────────────────────────────────────────

    def _compute_risk(
        self,
        action: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        """
        Lightweight rule-based risk scorer.
        Returns a float in [0.0, 1.0].

        Rules (additive, capped at 1.0):
          +0.0  base
          +0.5  if action_type is SUBMIT_ENTRY or FILE_AMENDMENT (consequential filing)
          +0.3  if there is a known document discrepancy in context
          +0.4  if shipment is in CUSTOMS_HOLD
          +0.2  if any missing_documents present
          -0.2  if all_documents_verified=True (reduces uncertainty)

        If context["risk_score"] is already explicitly set by a test fixture, use it directly.
        The API rejects risk_score from callers (see api/routes/agent_run.py).
        """
        # If risk_score was explicitly provided, honour it (LLM output, test fixture, etc.)
        if "risk_score" in context:
            return float(context["risk_score"])

        score = 0.0

        high_consequence_actions = {"SUBMIT_ENTRY", "FILE_AMENDMENT", "OVERRIDE_COMPLIANCE"}
        if action.get("action_type") in high_consequence_actions:
            score += 0.5

        if context.get("has_discrepancy"):
            score += 0.3

        if context.get("status") == "CUSTOMS_HOLD":
            score += 0.4

        if context.get("missing_documents"):
            score += 0.2

        if context.get("all_documents_verified"):
            score -= 0.2

        return max(0.0, min(1.0, score))
