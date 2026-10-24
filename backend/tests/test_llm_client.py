"""
tests/test_llm_client.py — LLM client fallback reporting and role validation (no network).
"""
from agent.llm_client import WatsonxClient


class _FakeProvider:
    name, model = "openai", "fake-model"

    def __init__(self, reason=None, plan=None, error=None):
        self._reason, self._plan, self._error = reason, plan, error

    def reason(self, context):
        if self._error:
            raise RuntimeError(self._error)
        return self._reason

    def plan(self, context, analysis):
        if self._error:
            raise RuntimeError(self._error)
        return self._plan


def _client(provider) -> WatsonxClient:
    client = WatsonxClient.__new__(WatsonxClient)
    client._provider = provider
    client.last_source = {}
    return client


CONTEXT = {"shipment_id": "SHP-002", "has_discrepancy": True}


def test_live_call_is_reported_as_live():
    client = _client(_FakeProvider(reason="- ok", plan=[{"action_type": "X", "role_required": "R2"}]))
    client.reason(CONTEXT)
    client.plan(CONTEXT, "- ok")
    assert client.last_source == {"provider": "openai", "model": "fake-model", "fallback": False}


def test_provider_error_falls_back_and_is_reported():
    client = _client(_FakeProvider(error="401 key invalidated"))
    analysis = client.reason(CONTEXT)
    actions = client.plan(CONTEXT, analysis)

    assert "mock LLM" in analysis
    assert actions  # mock plan still returned
    assert client.last_source["fallback"] is True
    assert any("401" in e for e in client.last_source["errors"])


def test_unparseable_plan_falls_back():
    client = _client(_FakeProvider(reason="- ok", plan=None))
    client.reason(CONTEXT)
    assert client.plan(CONTEXT, "- ok")
    assert client.last_source["fallback"] is True


def test_unknown_role_is_dropped():
    client = _client(_FakeProvider(reason="- ok", plan=[
        {"action_type": "REQUEST_HUMAN_APPROVAL", "role_required": "R1"},
        {"action_type": "REQUEST_DOCUMENT", "role_required": "R3"},
    ]))
    client.reason(CONTEXT)
    roles = [a["role_required"] for a in client.plan(CONTEXT, "- ok")]
    assert roles == [None, "R3"]
