# Member 1 Spec — AI Agent & State Machine Lead
**Timeline: 8 hours | Demo: 10:00 AM**

---

## Your Goal
Deliver a working FSM agent that can autonomously process customs events, call LLM tools for reasoning, enforce hard guards, and hand off to humans when required — demonstrated live in scenarios C02 and C09.

---

## Hour-by-Hour Tasks

### Hour 0–1 — Setup
- [ ] Clone repo, confirm Python 3.12 + virtual env works
- [ ] Install: `fastapi`, `langchain`, `ibm-watsonx-ai`, `pydantic`
- [ ] Review and agree on API contract (OpenAPI YAML) with M2 and M3

### Hour 1–3 — FSM Skeleton
- [ ] Create `agent/fsm.py` — define the `AgentState` enum with all states:
  ```
  INITIALIZE, OBSERVE, REASON, PLAN, POLICY_CHECK,
  ACT, VERIFY, WAIT_EVENT, COLLECT_DATA, ESCALATE,
  CUSTOMS_HOLD, CLEARANCE_VERIFIED, RECOVER
  ```
- [ ] Create `AgentFSM` class with:
  - `current_state: AgentState`
  - `transition(event)` method with guard checks
  - `context: dict` for shipment + evidence data
- [ ] Wire first transition: `INITIALIZE → OBSERVE` with **Guard G1** (shipment record exists)
- [ ] Create `agent/tools.py` with stubs for:
  - `get_shipment_status(shipment_id)`
  - `compare_documents(doc_a_id, doc_b_id)`
  - `check_compliance_rules(shipment_id)`

### Hour 3–6 — Scenario Implementation
#### C02 — Quantity Mismatch
- [ ] In `OBSERVE` state: call `compare_documents()` — detect Invoice qty=500 vs Packing List qty=480
- [ ] Transition: `OBSERVE → REASON` → LLM analyses discrepancy
- [ ] Transition: `REASON → PLAN` → LLM proposes ESCALATE action
- [ ] Transition: `PLAN → POLICY_CHECK` → enforce **G8: APPROVAL_REQUIRED**
- [ ] Transition: `POLICY_CHECK → ESCALATE` → create approval request for R2 (Warehouse) + R3 (Supplier)
- [ ] **Hard guard:** agent CANNOT change any document field values autonomously

#### C09 — CBP Hold
- [ ] On `CBP_HOLD_RECEIVED` event (from M5 mock feed): transition to `CUSTOMS_HOLD`
- [ ] In `CUSTOMS_HOLD`: create evidence-backed task, notify R4/R5
- [ ] Implement **Authority Invariant Guard**: `cbp_released=true` can ONLY be set when event `source_verified=true` arrives from the official CBP channel — agent is blocked from setting it autonomously
- [ ] Transition path: `CUSTOMS_HOLD → WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED`

### Hour 6–7.5 — Guards & Negative Tests
- [ ] Implement `PolicyCheckEngine` with:
  - `G7: ALLOW` — low-risk, proceed
  - `G8: APPROVAL_REQUIRED` — create HITL request
  - `G9: DENY` — hard block
- [ ] Write `tests/test_guards.py`:
  - Test: AI attempts to set `cbp_released=true` → assert `PermissionDeniedError` is raised
  - Test: approval missing → ACT is blocked
  - Test: duplicate event submission → idempotency key rejects second call
- [ ] Run all guard tests; all must pass

### Hour 7.5–8 — Demo Rehearsal
- [ ] Walk through C02 flow with M3's UI live
- [ ] Walk through C09 flow with M5's mock CBP feed
- [ ] Know your lines for the presentation: explain the FSM and the `cbp_released` guard

---

## Key Files to Create

```
agent/
  fsm.py          # AgentFSM class + AgentState enum
  tools.py        # Tool stubs: get_shipment_status, compare_documents, check_compliance_rules
  policy.py       # PolicyCheckEngine: G7/G8/G9 logic
  guards.py       # All guard condition functions G1–G9 (priority guards for demo)
  llm_client.py   # watsonx.ai wrapper for REASON and PLAN states
tests/
  test_guards.py  # Negative tests for cbp_released, stale approval, wrong role
```

---

## Interfaces You Depend On (from M2)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/agent-tasks` | POST | Create a new agent task |
| `GET /api/shipments/{id}` | GET | Fetch shipment + document list |
| `POST /api/approvals` | POST | Create HITL approval request |
| `POST /api/events` | POST | Ingest normalised event envelope |

---

## Interfaces You Expose (to M3)

- Agent pushes state change events over **Socket.IO** channel `agent_state_update`
- Payload: `{ shipment_id, from_state, to_state, reason, timestamp }`

---

## LLM Integration (watsonx.ai)

Used only in `REASON` and `PLAN` states.

```python
# llm_client.py skeleton
from ibm_watsonx_ai import APIClient
from ibm_watsonx_ai.foundation_models import ModelInference

def reason(context: dict) -> str:
    """Returns LLM analysis of current shipment context."""
    ...

def plan(context: dict, analysis: str) -> list[dict]:
    """Returns ordered list of proposed actions."""
    ...
```

> **Important:** LLM output is advisory only. All ACT-state actions must pass `PolicyCheckEngine` before execution.

---

## Guard Summary (Priority Guards for Demo)

| Guard | Condition | Effect |
|-------|-----------|--------|
| G1 | Shipment record exists | INITIALIZE → OBSERVE allowed |
| G7 | Risk score low | POLICY_CHECK → ACT (ALLOW) |
| G8 | Risk score medium | POLICY_CHECK → ESCALATE (APPROVAL_REQUIRED) |
| G9 | Risk score high / authority breach | Hard block (DENY) |
| G-cbp | `cbp_released` flag | ONLY set via `source_verified=true` official event |

---

## Definition of Done
- [ ] FSM transitions work for C02 and C09 flows
- [ ] `cbp_released=true` guard test passes (negative test)
- [ ] LLM is called in REASON and PLAN states and returns structured output
- [ ] Approval request is created and visible in M3's dashboard for C02
