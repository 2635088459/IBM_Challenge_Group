"""
api/routes/agent_run.py — POST /api/agent/run

Triggers the AgentRunner for a given shipment.  The runner will:
  1. Load the shipment context from the DB
  2. Drive OBSERVE → REASON (LLM) → PLAN (LLM) → POLICY_CHECK → ESCALATE/ACT
  3. Return the final FSM state and the LLM analysis + proposed actions

This is the bridge between the REST API and the agent/llm_client.py layer.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from api.models.models import Shipment
from api.agent_store import cbp_hold_verified, make_runner, save_run
import agent.red_team as red_team

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Set only by the agent's own guards or trusted event channels — never by API callers.
# e.g. payload={"risk_score": 0} would otherwise make any plan auto-allowed.
PROTECTED_CONTEXT_KEYS = {
    "risk_score", "force_deny", "cbp_released", "source_verified",
    "approval_required", "approval_status", "approved_plan_hash", "plan_hash",
    "red_team", "policy_denials", "cbp_hold_verified", "hold_notify_roles", "llm_source",
}


class AgentRunRequest(BaseModel):
    shipment_id: str
    event_type: str = "START"          # "START" | "CBP_HOLD_RECEIVED" | "APPROVAL_RECEIVED" | …
    payload: dict[str, Any] | None = None
    # Set True to simulate a quantity mismatch discrepancy regardless of file state
    # Useful for demo when evidence store files are not present on disk
    simulate_discrepancy: bool = False
    # Prompt-injection demo: attacker instructions hidden in supplier invoice text
    red_team: bool = False


class AgentRunResponse(BaseModel):
    shipment_id: str
    final_state: str
    llm_analysis: str | None = None
    proposed_actions: list[dict[str, Any]] | None = None
    transitions: list[dict[str, Any]] = []
    policy_denials: list[dict[str, Any]] = []
    llm_source: dict[str, Any] | None = None
    attack_text: str | None = None


@router.post("/run", response_model=AgentRunResponse)
def run_agent(body: AgentRunRequest, db: Session = Depends(get_db)):
    """
    Trigger the AI agent for a shipment.  Returns the final FSM state
    plus the LLM analysis and proposed action list (if REASON/PLAN ran).
    """
    # Verify shipment exists
    shipment = db.query(Shipment).filter(Shipment.id == body.shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    protected = PROTECTED_CONTEXT_KEYS & set(body.payload or {})
    if protected:
        raise HTTPException(
            status_code=400,
            detail=f"payload may not set protected fields: {sorted(protected)}",
        )

    # Build initial context — optionally inject a synthetic discrepancy for demo
    initial_context: dict[str, Any] = dict(body.payload or {})
    initial_context["cbp_hold_verified"] = cbp_hold_verified(db, shipment.id)
    if body.red_team:
        initial_context.update(red_team.attack_context())
    if body.simulate_discrepancy or body.red_team:
        initial_context.update({
            "has_discrepancy": True,
            "discrepancy_detail": [{
                "field": "line_quantity",
                "invoice_value": 500,
                "packing_list_value": 480,
                "delta": 20,
                "severity": "HIGH",
            }],
        })

    try:
        runner, transitions = make_runner(body.shipment_id, initial_context)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Agent runner unavailable: {exc}")

    try:
        if body.event_type == "START":
            final_state = runner.start()
        else:
            final_state = runner.handle_event(body.event_type, body.payload)
    except Exception as exc:
        logger.exception("AgentRunner failed for shipment %s", body.shipment_id)
        raise HTTPException(status_code=500, detail=str(exc))

    save_run(db, shipment, runner, transitions)

    return AgentRunResponse(
        shipment_id=body.shipment_id,
        final_state=final_state.value if hasattr(final_state, "value") else str(final_state),
        llm_analysis=runner.fsm.context.get("llm_analysis"),
        proposed_actions=runner.fsm.context.get("proposed_actions"),
        transitions=transitions,
        policy_denials=runner.fsm.context.get("policy_denials") or [],
        attack_text=red_team.INVOICE_REMARKS if body.red_team else None,
        llm_source=runner.fsm.context.get("llm_source"),
    )
