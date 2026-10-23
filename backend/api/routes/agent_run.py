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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    shipment_id: str
    event_type: str = "START"          # "START" | "CBP_HOLD_RECEIVED" | "APPROVAL_RECEIVED" | …
    payload: dict[str, Any] | None = None
    # Set True to simulate a quantity mismatch discrepancy regardless of file state
    # Useful for demo when evidence store files are not present on disk
    simulate_discrepancy: bool = False


class AgentRunResponse(BaseModel):
    shipment_id: str
    final_state: str
    llm_analysis: str | None = None
    proposed_actions: list[dict[str, Any]] | None = None
    transitions: list[dict[str, Any]] = []


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

    # Lazy import — avoids loading ibm_watsonx_ai at startup if not needed
    try:
        from agent.runner import AgentRunner
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Agent runner unavailable: {exc}")

    transitions: list[dict] = []

    def _capture_emit(event: str, data: dict, **_kwargs):
        if event == "agent_state_update":
            transitions.append(data)

    # Build initial context — optionally inject a synthetic discrepancy for demo
    initial_context: dict[str, Any] = body.payload or {}
    if body.simulate_discrepancy:
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

    runner = AgentRunner(
        shipment_id=body.shipment_id,
        context=initial_context,
        socketio_emit=_capture_emit,
    )

    try:
        if body.event_type == "START":
            final_state = runner.start()
        else:
            final_state = runner.handle_event(body.event_type, body.payload)
    except Exception as exc:
        logger.exception("AgentRunner failed for shipment %s", body.shipment_id)
        raise HTTPException(status_code=500, detail=str(exc))

    return AgentRunResponse(
        shipment_id=body.shipment_id,
        final_state=final_state.value if hasattr(final_state, "value") else str(final_state),
        llm_analysis=runner.fsm.context.get("llm_analysis"),
        proposed_actions=runner.fsm.context.get("proposed_actions"),
        transitions=transitions,
    )
