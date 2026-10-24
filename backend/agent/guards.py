"""
agent/guards.py — Guard condition functions for the FSM.

Every guard returns a GuardResult(passed, reason).
Guards are pure functions — no side effects, no I/O.

Priority guards for demo:
  G1  — Shipment record exists in context
  G7  — Risk score low  → ALLOW
  G8  — Risk score medium → APPROVAL_REQUIRED
  G9  — Risk score high / authority breach → DENY
  G-cbp — cbp_released authority invariant
"""
from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuardResult:
    passed: bool
    reason: str

    @classmethod
    def ok(cls, reason: str = "Guard passed") -> "GuardResult":
        return cls(passed=True, reason=reason)

    @classmethod
    def fail(cls, reason: str) -> "GuardResult":
        return cls(passed=False, reason=reason)


# ── G1: Shipment exists ───────────────────────────────────────────────────────

def g1_shipment_exists(context: dict[str, Any]) -> GuardResult:
    """
    G1: The agent may only start processing if a shipment record exists.
    Expects context to contain at least { "shipment_id": str }.
    """
    shipment_id = context.get("shipment_id")
    if not shipment_id:
        return GuardResult.fail("G1 failed: shipment_id not present in context")
    return GuardResult.ok(f"G1 passed: shipment {shipment_id} exists")


# ── G7: Low-risk ALLOW ────────────────────────────────────────────────────────

def g7_low_risk(context: dict[str, Any]) -> GuardResult:
    """
    G7: Risk score is low — agent may proceed autonomously (ALLOW).
    Risk score is expected in context["risk_score"] (0.0–1.0).
    Threshold: risk_score < 0.3 → ALLOW.
    """
    risk_score = context.get("risk_score", 1.0)
    if risk_score < 0.3:
        return GuardResult.ok(f"G7 passed: risk_score={risk_score:.2f} < 0.3 (ALLOW)")
    return GuardResult.fail(f"G7 failed: risk_score={risk_score:.2f} >= 0.3")


# ── G8: Medium-risk APPROVAL_REQUIRED ────────────────────────────────────────

def g8_approval_required(context: dict[str, Any]) -> GuardResult:
    """
    G8: Risk score is medium — human approval required before ACT.
    Threshold: 0.3 ≤ risk_score < 0.8 → APPROVAL_REQUIRED.
    """
    risk_score = context.get("risk_score", 1.0)
    if 0.3 <= risk_score < 0.8:
        return GuardResult.ok(f"G8 passed: risk_score={risk_score:.2f} in [0.3, 0.8) (APPROVAL_REQUIRED)")
    return GuardResult.fail(f"G8 failed: risk_score={risk_score:.2f} not in [0.3, 0.8)")


# ── G9: High-risk DENY ────────────────────────────────────────────────────────

def g9_deny(context: dict[str, Any]) -> GuardResult:
    """
    G9: Risk score is high or an authority invariant would be breached — DENY.
    Threshold: risk_score >= 0.8 → DENY.
    Also triggers if context["force_deny"] is True (for testing).
    """
    risk_score = context.get("risk_score", 0.0)
    if context.get("force_deny"):
        return GuardResult.ok("G9 triggered: force_deny=True (DENY)")
    if risk_score >= 0.8:
        return GuardResult.ok(f"G9 triggered: risk_score={risk_score:.2f} >= 0.8 (DENY)")
    return GuardResult.fail(f"G9 not triggered: risk_score={risk_score:.2f} < 0.8")


# ── G-cbp: CBP release authority invariant ───────────────────────────────────

def g_cbp_release_authority(source_verified: bool) -> GuardResult:
    """
    G-CBP (Authority Invariant):
    The cbp_released=true flag may ONLY be set when the triggering event
    has source_verified=True, meaning it originated from the official CBP channel.

    The agent is NEVER permitted to set this flag autonomously — it can only
    process the event when it arrives with source_verified=True.
    """
    if source_verified:
        return GuardResult.ok("G-CBP passed: source_verified=True (official CBP channel)")
    return GuardResult.fail(
        "G-CBP failed: source_verified=False — agent cannot set cbp_released=True autonomously. "
        "Only an official CBP channel event (source_verified=True) may trigger this transition."
    )


# ── G-approval: Approval must exist before ACT ───────────────────────────────

def g_approval_exists(context: dict[str, Any]) -> GuardResult:
    """
    When policy returned APPROVAL_REQUIRED, ACT is blocked until
    context["approval_status"] == "APPROVED".
    """
    required = context.get("approval_required", False)
    if not required:
        return GuardResult.ok("G-approval: no approval required for this action")

    status = context.get("approval_status")
    if status == "APPROVED":
        return GuardResult.ok("G-approval passed: approval status is APPROVED")
    if status == "EXPIRED":
        return GuardResult.fail("G-approval failed: approval has EXPIRED — re-submit required")
    if status == "REJECTED":
        return GuardResult.fail("G-approval failed: approval was REJECTED")
    return GuardResult.fail(
        f"G-approval failed: approval_status='{status}' — must be APPROVED before ACT"
    )


# ── G-cbp-action: Agent cannot propose releasing a CBP hold ──────────────────

CBP_RELEASE_ACTIONS = {"SET_CBP_RELEASED", "RELEASE_CBP_HOLD", "OVERRIDE_CBP_HOLD"}


def g_cbp_release_not_proposed(action: dict[str, Any]) -> GuardResult:
    """
    Hard guard: no proposed action may release a CBP hold or touch cbp_released,
    whatever the LLM was told (e.g. by text injected into a supplier document).
    The only path is AgentFSM.set_cbp_released() on a verified CBP event.
    """
    if action.get("action_type") in CBP_RELEASE_ACTIONS or "cbp_released" in json.dumps(action).lower():
        return GuardResult.fail(
            "G-cbp: only an official CBP release event may set cbp_released — agents cannot propose it"
        )
    return GuardResult.ok("G-cbp: action does not attempt a CBP release")


# ── G-doc-immutable: Agent cannot modify document field values ────────────────

def g_document_immutable(action: dict[str, Any]) -> GuardResult:
    """
    Hard guard: agent actions of type MODIFY_DOCUMENT_FIELD are always denied.
    Document field values may only be changed by authorised humans.
    """
    if action.get("action_type") == "MODIFY_DOCUMENT_FIELD":
        return GuardResult.fail(
            "G-doc-immutable: agents cannot autonomously modify document field values"
        )
    return GuardResult.ok("G-doc-immutable: action does not modify document fields")
