"""
agent/llm_client.py — Multi-provider LLM wrapper for REASON and PLAN states.

Supported providers (set LLM_PROVIDER env var):
  openai    — OpenAI Chat Completions API  (default: gpt-4o-mini)
  watsonx   — IBM watsonx.ai ModelInference (default: ibm/granite-13b-instruct-v2)
  mock      — deterministic offline fallback (no credentials needed)

If LLM_PROVIDER is not set, the client auto-detects:
  1. OPENAI_API_KEY present   → openai
  2. WATSONX_API_KEY present  → watsonx
  3. neither                  → mock

LLM output is advisory only — all proposed actions MUST pass PolicyCheckEngine
before the agent enters ACT state.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────

LLM_PROVIDER       = os.getenv("LLM_PROVIDER", "").lower()          # openai | watsonx | mock

# OpenAI
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o-mini")       # cheap + fast
OPENAI_MAX_TOKENS  = int(os.getenv("OPENAI_MAX_TOKENS", "512"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))

# watsonx.ai
WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_MODEL_ID   = os.getenv("WATSONX_MODEL_ID", "ibm/granite-13b-instruct-v2")


# ── Prompts (shared across providers) ────────────────────────────────────────

_REASON_SYSTEM = (
    "You are an AI customs clearance analyst. "
    "Analyse the shipment context and identify issues, discrepancies, or risks. "
    "Be concise. Focus on: document discrepancies, missing documents, "
    "compliance flags, and CBP hold status."
)

_REASON_USER = """\
Shipment context:
{context_json}

Respond with a concise plain-text analysis (3-6 bullet points max).
Analysis:"""

_PLAN_SYSTEM = (
    "You are an AI customs clearance planner. "
    "Given an analysis, propose an ordered list of actions to resolve the issues. "
    "Rules: you CANNOT modify document field values directly. "
    "Actions requiring human authority must use action_type REQUEST_HUMAN_APPROVAL. "
    "Return ONLY a valid JSON array — no prose before or after."
)

_PLAN_USER = """\
Analysis:
{analysis}

Shipment context:
{context_json}

Each action object must have: action_type (string), description (string), role_required (string or null).
Example:
[
  {{"action_type": "REQUEST_DOCUMENT", "description": "Request updated invoice from supplier", "role_required": "R3"}},
  {{"action_type": "REQUEST_HUMAN_APPROVAL", "description": "Warehouse manager to confirm quantity", "role_required": "R2"}}
]

Actions JSON:"""


# ── OpenAI provider ───────────────────────────────────────────────────────────

class _OpenAIProvider:
    """Uses openai>=1.0 Chat Completions — works with gpt-4o-mini, gpt-3.5-turbo, etc."""

    def __init__(self):
        from openai import OpenAI  # lazy import — only needed when provider=openai
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI LLM provider initialised (model=%s)", OPENAI_MODEL)

    def _chat(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
        )
        return response.choices[0].message.content.strip()

    def reason(self, context: dict[str, Any]) -> str:
        user = _REASON_USER.format(
            context_json=json.dumps(context, indent=2, default=str)
        )
        try:
            return self._chat(_REASON_SYSTEM, user)
        except Exception as exc:
            logger.error("OpenAI reason() failed: %s — using mock", exc)
            return _mock_reason(context)

    def plan(self, context: dict[str, Any], analysis: str) -> list[dict[str, Any]]:
        user = _PLAN_USER.format(
            analysis=analysis,
            context_json=json.dumps(context, indent=2, default=str),
        )
        try:
            raw = self._chat(_PLAN_SYSTEM, user)
            return _parse_json_array(raw) or _mock_plan(context, analysis)
        except Exception as exc:
            logger.error("OpenAI plan() failed: %s — using mock", exc)
            return _mock_plan(context, analysis)


# ── watsonx.ai provider ───────────────────────────────────────────────────────

class _WatsonxProvider:
    """Uses ibm-watsonx-ai ModelInference (completion-style)."""

    def __init__(self):
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
        creds = Credentials(api_key=WATSONX_API_KEY, url=WATSONX_URL)
        self._model = ModelInference(
            model_id=WATSONX_MODEL_ID,
            credentials=creds,
            project_id=WATSONX_PROJECT_ID,
            params={"max_new_tokens": 512, "temperature": 0.0},
        )
        logger.info("watsonx.ai provider initialised (model=%s)", WATSONX_MODEL_ID)

    def _complete(self, prompt: str) -> str:
        return self._model.generate_text(prompt=prompt).strip()

    def reason(self, context: dict[str, Any]) -> str:
        prompt = (
            _REASON_SYSTEM + "\n\n"
            + _REASON_USER.format(context_json=json.dumps(context, indent=2, default=str))
        )
        try:
            return self._complete(prompt)
        except Exception as exc:
            logger.error("watsonx reason() failed: %s — using mock", exc)
            return _mock_reason(context)

    def plan(self, context: dict[str, Any], analysis: str) -> list[dict[str, Any]]:
        prompt = (
            _PLAN_SYSTEM + "\n\n"
            + _PLAN_USER.format(
                analysis=analysis,
                context_json=json.dumps(context, indent=2, default=str),
            )
        )
        try:
            raw = self._complete(prompt)
            return _parse_json_array(raw) or _mock_plan(context, analysis)
        except Exception as exc:
            logger.error("watsonx plan() failed: %s — using mock", exc)
            return _mock_plan(context, analysis)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _parse_json_array(raw: str) -> list[dict] | None:
    """Extract and parse the first JSON array found in a string."""
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse JSON array from LLM response: %r", raw[:200])
    return None


def _mock_reason(context: dict[str, Any]) -> str:
    shipment_id = context.get("shipment_id", "UNKNOWN")
    has_discrepancy = context.get("has_discrepancy", False)
    missing_docs = context.get("missing_documents", [])
    status = context.get("status", "UNKNOWN")

    parts = [f"Shipment {shipment_id} analysis (mock LLM):"]
    if has_discrepancy:
        parts.append(
            "- DOCUMENT DISCREPANCY DETECTED: Invoice quantity (500) does not match "
            "Packing List quantity (480). Delta: 20 units. "
            "Human confirmation from Warehouse (R2) and Supplier (R3) is required."
        )
    if missing_docs:
        parts.append(
            f"- MISSING DOCUMENTS: {', '.join(missing_docs)}. "
            "Must be obtained before proceeding."
        )
    if status == "CUSTOMS_HOLD":
        parts.append(
            "- CBP HOLD ACTIVE: Shipment is under targeted inspection. "
            "Release requires official CBP channel confirmation (source_verified=True)."
        )
    if not has_discrepancy and not missing_docs and status != "CUSTOMS_HOLD":
        parts.append("- No issues detected. Shipment appears compliant.")
    return "\n".join(parts)


def _mock_plan(context: dict[str, Any], _analysis: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if context.get("has_discrepancy"):
        actions.append({
            "action_type": "REQUEST_HUMAN_APPROVAL",
            "description": "Warehouse manager (R2) must confirm actual quantity shipped",
            "role_required": "R2",
        })
        actions.append({
            "action_type": "REQUEST_HUMAN_APPROVAL",
            "description": "Supplier (R3) must confirm invoice quantity",
            "role_required": "R3",
        })
    if context.get("missing_documents"):
        actions.append({
            "action_type": "REQUEST_DOCUMENT",
            "description": "Request missing Commercial Invoice from supplier (R3)",
            "role_required": "R3",
        })
    if context.get("status") == "CUSTOMS_HOLD":
        actions.append({
            "action_type": "NOTIFY_COMPLIANCE",
            "description": "Notify Trade Compliance Officer (R4) of CBP hold",
            "role_required": "R4",
        })
        actions.append({
            "action_type": "NOTIFY_BROKER",
            "description": "Notify Customs Broker (R5) to coordinate with CBP",
            "role_required": "R5",
        })
    if not actions:
        actions.append({
            "action_type": "PROCEED_TO_VERIFY",
            "description": "No issues found — proceed to verification",
            "role_required": None,
        })
    return actions


# ── Top-level client (auto-detects provider) ─────────────────────────────────

class WatsonxClient:
    """
    Unified LLM client.  Provider is selected by LLM_PROVIDER env var:
      openai  → gpt-4o-mini (or OPENAI_MODEL)
      watsonx → ibm/granite-13b-instruct-v2 (or WATSONX_MODEL_ID)
      mock    → deterministic offline fallback

    Auto-detection order when LLM_PROVIDER is not set:
      OPENAI_API_KEY set    → openai
      WATSONX_API_KEY set   → watsonx
      neither               → mock
    """

    def __init__(self):
        self._provider = self._init_provider()

    @staticmethod
    def _init_provider():
        provider = LLM_PROVIDER

        # Auto-detect if not explicitly set
        if not provider:
            if OPENAI_API_KEY:
                provider = "openai"
            elif WATSONX_API_KEY and WATSONX_PROJECT_ID:
                provider = "watsonx"
            else:
                provider = "mock"

        if provider == "openai":
            try:
                return _OpenAIProvider()
            except Exception as exc:
                logger.warning("OpenAI init failed (%s) — falling back to mock", exc)

        if provider == "watsonx":
            try:
                return _WatsonxProvider()
            except Exception as exc:
                logger.warning("watsonx.ai init failed (%s) — falling back to mock", exc)

        logger.info("LLM running in mock mode (set OPENAI_API_KEY or WATSONX_API_KEY to use a live model)")
        return None  # mock path

    def reason(self, context: dict[str, Any]) -> str:
        if self._provider is not None:
            return self._provider.reason(context)
        return _mock_reason(context)

    def plan(self, context: dict[str, Any], analysis: str) -> list[dict[str, Any]]:
        if self._provider is not None:
            return self._provider.plan(context, analysis)
        return _mock_plan(context, analysis)


# ── Module-level singleton ────────────────────────────────────────────────────

_client: WatsonxClient | None = None


def get_client() -> WatsonxClient:
    global _client
    if _client is None:
        _client = WatsonxClient()
    return _client


def reason(context: dict[str, Any]) -> str:
    """Module-level shortcut — used by AgentRunner."""
    return get_client().reason(context)


def plan(context: dict[str, Any], analysis: str) -> list[dict[str, Any]]:
    """Module-level shortcut — used by AgentRunner."""
    return get_client().plan(context, analysis)
