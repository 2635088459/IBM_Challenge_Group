"""
agent/tools.py — Agent tool implementations.

Each tool calls M2's REST API to fetch live data.
Tools are called by the FSM during OBSERVE and COLLECT_DATA states,
and their results are fed into the LLM during REASON/PLAN states.

All tools are synchronous (httpx blocking client) for simplicity in the demo.
"""
from __future__ import annotations

import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
_client = httpx.Client(base_url=API_BASE, timeout=10.0)


# ── Tool: get_shipment_status ─────────────────────────────────────────────────

def get_shipment_status(shipment_id: str) -> dict[str, Any]:
    """
    Fetch the current status and document list for a shipment.

    Returns:
        {
            "id": str,
            "reference_number": str,
            "status": str,
            "documents": [{ "id", "doc_type", "file_hash", "version", "status" }, ...]
        }
    """
    try:
        resp = _client.get(f"/api/shipments/{shipment_id}")
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("get_shipment_status failed for %s: %s", shipment_id, e)
        raise
    except httpx.RequestError as e:
        logger.error("get_shipment_status connection error: %s", e)
        raise


# ── Tool: compare_documents ───────────────────────────────────────────────────

def compare_documents(shipment_id: str, doc_a_id: str, doc_b_id: str) -> dict[str, Any]:
    """
    Call M4's document consistency-check endpoint to compare two documents.

    Returns:
        {
            "shipment_id": str,
            "mismatches": [
                {
                    "field": str,
                    "invoice_value": any,
                    "packing_list_value": any,
                    "delta": any,
                    "severity": "HIGH" | "MEDIUM" | "LOW"
                }, ...
            ],
            "overall_status": "PASS" | "FAIL"
        }
    """
    try:
        resp = _client.post(
            "/api/documents/consistency-check",
            json={"shipment_id": shipment_id, "invoice_doc_id": doc_a_id, "packing_list_doc_id": doc_b_id},
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("compare_documents failed (%s vs %s): %s", doc_a_id, doc_b_id, e)
        raise
    except httpx.RequestError as e:
        logger.error("compare_documents connection error: %s", e)
        raise


# ── Tool: check_compliance_rules ──────────────────────────────────────────────

def check_compliance_rules(shipment_id: str) -> dict[str, Any]:
    """
    Stub for compliance rule evaluation.
    In the demo this returns a hardcoded result; in production it would
    call a compliance engine or rules DB.

    Returns:
        {
            "shipment_id": str,
            "risk_score": float,       # 0.0–1.0
            "flags": [str],            # list of triggered rule IDs
            "recommendation": str      # "ALLOW" | "REVIEW" | "HOLD"
        }
    """
    # Demo stub — returns medium risk for any shipment to trigger G8 for demo
    logger.info("check_compliance_rules called for shipment %s (demo stub)", shipment_id)
    return {
        "shipment_id": shipment_id,
        "risk_score": 0.5,
        "flags": ["QUANTITY_DISCREPANCY"],
        "recommendation": "REVIEW",
    }


# ── Tool: create_approval_request ─────────────────────────────────────────────

def create_approval_request(
    shipment_id: str,
    action_id: str | None,
    role: str,
    payload_hash: str | None = None,
) -> dict[str, Any]:
    """
    Create a HITL approval request via M2's API.
    Called by the FSM when transitioning to ESCALATE state.
    """
    try:
        resp = _client.post(
            "/api/approvals",
            json={
                "shipment_id": shipment_id,
                "action_id": action_id,
                "role": role,
                "payload_hash": payload_hash,
            },
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("create_approval_request failed: %s", e)
        raise
    except httpx.RequestError as e:
        logger.error("create_approval_request connection error: %s", e)
        raise


# ── Tool: emit_event ──────────────────────────────────────────────────────────

def emit_event(
    event_id: str,
    event_type: str,
    shipment_id: str,
    payload: dict[str, Any],
    source_verified: bool = False,
) -> dict[str, Any]:
    """
    Post a normalised event envelope to M2's event ingestion endpoint.
    Used by the agent to record its own state transitions as auditable events.
    """
    try:
        resp = _client.post(
            "/api/events",
            json={
                "event_id": event_id,
                "event_type": event_type,
                "shipment_id": shipment_id,
                "source_verified": source_verified,
                "payload": payload,
            },
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("emit_event failed (%s): %s", event_type, e)
        raise
    except httpx.RequestError as e:
        logger.error("emit_event connection error: %s", e)
        raise
