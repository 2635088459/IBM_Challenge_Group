# Autonomous AI Customs Clearance — Team Work Plan & Demo Setup
**Version 3.0 | Presentation Target: Tomorrow 10:00 AM**

---

## 1. Team Roles & Ownership (5 Members)

### Member 1 — AI Agent & State Machine Lead
- Build the FSM core: OBSERVE → REASON → PLAN → POLICY_CHECK → ACT → VERIFY → RECOVER
- Implement guard conditions G1–G28
- LLM integration (watsonx / OpenAI) for REASON & PLAN states
- Agent tool contract: `get_shipment_status`, `compare_documents`, `check_compliance_rules`
- Exception recovery flows (RETRY / REPLAN / ESCALATE)

### Member 2 — Backend & Data Pipeline Lead
- PostgreSQL schema: `shipments`, `documents`, `agent_tasks`, `agent_actions`, `approvals`, `events`, `audit_logs`
- Event ingestion + deduplication + outbox pattern
- Normalized event envelope (`event_id`, `source_verified`, `evidence_id`)
- REST / GraphQL API endpoints for frontend & agent
- Idempotency key enforcement for write tools

### Member 3 — Frontend & HITL Dashboard Lead
- Human-in-the-Loop approval UI (role-aware routing: R2/R3/R4/R5/R7/R9)
- Shipment status dashboard: PRE_ARRIVAL → CLEARANCE_VERIFIED
- Document upload & discrepancy view
- Approval queue: PENDING / APPROVED / REJECTED / EXPIRED
- Evidence trail & audit log view

### Member 4 — Document Processing & OCR Lead
- OCR extraction pipeline for Invoice, Packing List, Bill of Lading
- Document consistency check (D2 field-level compare)
- SHA-256 document hashing + versioning
- Evidence store: raw / extracted / verified classification
- Synthetic test document generation for MVP scenarios C02, C04, C07, C09

### Member 5 — DevOps, Integration & Demo Coordinator
- Docker Compose setup (API server, agent worker, PostgreSQL, Redis, frontend)
- Environment config & secrets management
- Mock external adapters: ERP / TMS / Broker / CBP status feeds
- CI pipeline (lint, test, build)
- Demo script and live walkthrough preparation for 3 MVP scenarios
- Slide deck summary of system architecture & research questions RQ1–RQ4

---

## 2. Work Plan — Phases to Demo

### Phase 0 — Kickoff & Environment Setup *(Hours 0–2)*
- All members: clone repo, confirm local Docker + Node + Python environments
- Member 5: spin up Docker Compose with PostgreSQL + Redis + stub API server
- Member 2: run initial DB migrations, verify schema from Section 20.1
- Confirm shared Git branch strategy (feature branches → main)
- Agree on API contract (OpenAPI YAML) between frontend and backend

### Phase 1 — Core Data Layer & Agent Skeleton *(Hours 2–5)*
- **Member 2:** Implement all 12 PostgreSQL entities (shipments, documents, events, agent_tasks, agent_actions, approvals, field_observations, entries, agency_dispositions, recovery_attempts, audit_logs, shipment_lines)
- **Member 1:** Scaffold state machine class with all 13 agent states; wire INITIALIZE → OBSERVE transition with G1 guard
- **Member 4:** Set up document ingestion endpoint; implement SHA-256 hash + version tracking
- **Member 3:** Bootstrap frontend project (Next.js); create shipment list page pulling from stub API
- **Member 5:** Build mock ERP/TMS event emitter producing CARGO_ARRIVED, INVOICE_RECEIVED events

### Phase 2 — MVP Scenario Implementation (C02 + C09) *(Hours 5–9)*
- **Member 1 + 4:** C02 Quantity Mismatch — agent detects Invoice 500 vs Packing List 480, triggers COLLECT_DATA → ESCALATE flow
- **Member 1 + 2:** C09 CBP Hold — ingest trusted hold event, transition to CUSTOMS_HOLD state, block `cbp_released=true` guard
- **Member 3:** Build approval queue UI; wire ESCALATE events to role-aware routing (R2/R3 for doc facts, R4/R5 for compliance)
- **Member 2:** Implement outbox pattern for durable action dispatch; add `idempotency_key` UNIQUE constraint enforcement
- **Member 5:** Mock CBP status feed emitting CBP_HOLD_RECEIVED and CBP_RELEASE_RECEIVED events with `source_verified=true`

### Phase 3 — HITL Approval Lifecycle + Policy Engine *(Hours 9–12)*
- **Member 1:** Implement deterministic POLICY_CHECK engine (G7 ALLOW / G8 APPROVAL_REQUIRED / G9 DENY); enforce G25–G28 approval guards
- **Member 3:** Approval UI: bind approval to `action_id` + `payload_hash` + version; show EXPIRED warnings; invalidate on draft change
- **Member 2:** Approval lifecycle API: requested → assigned → approved/rejected/expired transitions
- **Member 4:** Implement document consistency check for D2 fields (`line_sku`, `line_quantity`, `unit_price` cross-compare)
- **Member 5:** Write integration smoke tests: wrong-role approval, stale approval, duplicate submission after timeout

### Phase 4 — Demo Polish & Rehearsal *(Hours 12–14, final push before 10 AM)*
- **Member 5:** Finalize demo script covering 3 scenarios: Missing Document, Quantity Mismatch, CBP Hold Coordination
- **Member 3:** Add evidence trail panel showing raw → extracted → verified evidence chain
- **Member 1:** Confirm all negative-test guards pass: AI cannot set `cbp_released=true` autonomously
- **All:** End-to-end walkthrough rehearsal; fix blocking bugs only
- **Member 5:** Prepare architecture diagram slide aligned with Section 14 system diagram

---

## 3. Full-Stack Technology Choices

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 14 + TypeScript | App framework, type-safe UI |
| **Frontend** | Tailwind CSS | Rapid styling |
| **Frontend** | SWR / React Query | Data fetching |
| **Frontend** | Socket.IO | Real-time agent state push |
| **Frontend** | React Flow | FSM visualisation |
| **Backend** | Python 3.12 + FastAPI | Agent runtime + REST/WebSocket API |
| **Backend** | Pydantic v2 | Typed data contracts (per §17) |
| **Backend** | SQLAlchemy 2 + Alembic | ORM + DB migrations |
| **Backend** | Celery + Redis | Async task queue / outbox pattern |
| **AI / LLM** | IBM watsonx.ai | Primary LLM for REASON & PLAN states |
| **AI / LLM** | LangChain | Tool/chain orchestration |
| **AI / LLM** | Tesseract / AWS Textract | OCR document extraction |
| **AI / LLM** | Custom FSM engine | Deterministic guard layer |
| **Database** | PostgreSQL 16 | Primary store (12 entities per §20.1) |
| **Database** | Redis 7 | Event queue + idempotency cache |
| **DevOps** | Docker + Docker Compose | Local dev & demo environment |
| **DevOps** | GitHub Actions | CI/CD |
| **DevOps** | pytest + Vitest + Playwright | Backend & frontend testing |
| **Integrations** | Mock ERP/TMS/Broker/ACE adapters | Simulated external feeds (no live filing) |

---

## 4. Demo — 3 MVP Scenarios to Present

### C01 — Missing Commercial Invoice
Agent detects missing document in D2 group.
**Flow:** OBSERVE → REASON → COLLECT_DATA → WAIT_EVENT → ESCALATE to R3 (Supplier).
Show approval request + document upload resolving the hold.

### C02 — Quantity Mismatch (Invoice 500 vs Packing List 480)
Core showcase of HYBRID mode.
**Flow:** Agent detects discrepancy → requests confirmation from R2 (Warehouse) + R3 (Supplier) → persists evidence.
**Key guard:** AI cannot change filing values from OCR alone (hard guard demonstration).

### C09 — CBP Customs Hold Coordination
Trusted hold event ingested. Agent triages, creates evidence-backed tasks.
**Flow:** OBSERVE → PLAN → COLLECT_DATA / ESCALATE → WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED.
**Key demo point:** `cbp_released=true` authority invariant — only R6 official channel can set this flag. AI is blocked.

---

## 5. System Architecture Summary

| Layer | Component | Owner |
|-------|-----------|-------|
| External Sources | ERP / TMS / Carrier / Broker / CBP feed (all mocked) | Member 5 |
| Ingestion | Event envelope validation, deduplication, source verification | Member 2 |
| Document Processing | OCR extraction, field normalization, SHA-256 hashing, evidence classification | Member 4 |
| Agent Runtime | FSM (13 states), LLM REASON/PLAN, tool executor, guard engine | Member 1 |
| Policy Engine | Deterministic POLICY_CHECK, RBAC, approval lifecycle, G1–G28 guards | Member 1 + 2 |
| HITL Approval UI | Role-aware dashboard, approval queue, evidence trail, shipment timeline | Member 3 |
| Persistence | PostgreSQL (12 entities) + Redis (queue + idempotency) | Member 2 |
| Infra / Demo | Docker Compose, CI, mock adapters, demo script, slides | Member 5 |

---

## 6. Pre-Presentation Checklist

- [ ] Docker Compose starts cleanly: API, worker, DB, Redis, frontend all green
- [ ] Database seeded with at least 3 synthetic shipments covering C01, C02, C09
- [ ] All 3 demo flows run end-to-end without errors
- [ ] HITL approval panel shows pending approvals with correct role routing
- [ ] **Negative test:** confirm AI cannot autonomously set `cbp_released=true`
- [ ] Evidence trail panel shows raw → extracted → verified chain for at least one document
- [ ] Architecture slide prepared referencing Section 14 system diagram
- [ ] Research questions RQ1–RQ4 mapped to demo scenarios in slide deck
- [ ] All team members know which scenario they are presenting
- [ ] Backup: screenshots / screen recording in case of live demo failure

---

> **⚠ Regulatory Reminder (per V3.0 spec):** All demo data must be clearly labeled as **synthetic**.
> No live ACE filing, no real CBP status codes. `CLEARANCE_VERIFIED` in the demo is a research
> predicate, not an official customs release. Ensure all slides and the UI carry appropriate disclaimers.
