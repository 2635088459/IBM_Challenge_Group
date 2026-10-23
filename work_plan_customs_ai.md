# Autonomous AI Customs Clearance — 8-Hour Demo Work Plan
**Team: 5 Members | Deadline: 10:00 AM (8 hours from now)**

---

## Team Roles at a Glance

| Member | Role | Core Deliverable |
|--------|------|-----------------|
| **M1** | AI Agent Lead | FSM state machine + LLM integration |
| **M2** | Backend Lead | FastAPI + PostgreSQL + REST API |
| **M3** | Frontend Lead | Next.js dashboard + HITL approval UI |
| **M4** | Document Lead | OCR pipeline + document consistency check |
| **M5** | DevOps & Demo Lead | Docker Compose + mock feeds + demo script |

---

## 8-Hour Timeline

### Hour 0–1 — Kickoff & Environment *(All)*
- Clone repo, verify Docker / Node / Python run locally
- **M5:** Launch `docker compose up` (PostgreSQL + Redis + stub server)
- **M2:** Run DB migrations, confirm schema is live
- **M1:** Agree on API contract (OpenAPI YAML) with M2 & M3
- **M4:** Confirm OCR library (Tesseract) installs cleanly

### Hour 1–3 — Core Data + Agent Skeleton *(All parallel)*
- **M1:** Scaffold FSM class with states OBSERVE → REASON → PLAN → POLICY_CHECK → ACT → VERIFY; wire first guard G1
- **M2:** Create all 7 key DB tables (`shipments`, `documents`, `events`, `agent_tasks`, `approvals`, `audit_logs`, `agent_actions`); expose 4 REST endpoints
- **M3:** Bootstrap Next.js app; build shipment list page against stub API
- **M4:** Build document upload endpoint; add SHA-256 hashing + field extraction skeleton
- **M5:** Build mock event emitter producing `CARGO_ARRIVED` and `INVOICE_RECEIVED` events

### Hour 3–6 — MVP Scenarios C02 + C09 *(Core sprint)*
- **M1 + M4:** **Scenario C02** — agent detects Invoice 500 vs Packing List 480, triggers ESCALATE flow
- **M1 + M2:** **Scenario C09** — ingest CBP hold event, transition to `CUSTOMS_HOLD`, block autonomous `cbp_released=true` guard
- **M3:** Build approval queue UI (PENDING / APPROVED / REJECTED); wire to role routing R2/R3/R4
- **M2:** Add idempotency key enforcement + outbox pattern for durable dispatches
- **M5:** Mock CBP status feed with `CBP_HOLD_RECEIVED` / `CBP_RELEASE_RECEIVED` events

### Hour 6–7.5 — Integration & Polish *(All)*
- **M1:** Run all guard negative tests — confirm AI cannot set `cbp_released=true`
- **M2:** Seed DB with 3 synthetic shipments (C01, C02, C09)
- **M3:** Add evidence trail panel (raw → extracted → verified); add EXPIRED approval warnings
- **M4:** Implement D2 field-level compare (`line_sku`, `line_quantity`, `unit_price`)
- **M5:** Write 3 smoke tests; fix Docker Compose so all services start clean

### Hour 7.5–8 — Rehearsal *(All)*
- **M5:** Run full demo script (3 scenarios) end-to-end
- Fix blocking bugs only — no new features
- Confirm every team member knows their part of the live walkthrough
- **M5:** Take screenshots/recording as backup in case of live failure

---

## Technology Stack (Minimal Viable Set)

| Layer | Tech |
|-------|------|
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Realtime | Socket.IO (agent state push) |
| Backend | Python 3.12 + FastAPI |
| AI / LLM | IBM watsonx.ai + LangChain |
| OCR | Tesseract |
| Database | PostgreSQL 16 + SQLAlchemy 2 + Alembic |
| Queue | Redis 7 + Celery |
| Infra | Docker Compose |
| Testing | pytest + Vitest |

---

## 3 Demo Scenarios to Present

| Scenario | What It Shows |
|----------|--------------|
| **C01 — Missing Invoice** | Agent detects missing doc → ESCALATE → upload resolves hold |
| **C02 — Quantity Mismatch** | Agent finds Invoice 500 vs PL 480 → human confirmation required |
| **C09 — CBP Hold** | Trusted hold event → `cbp_released=true` guard blocks autonomous action |

---

## Pre-Demo Checklist

- [ ] `docker compose up` starts all services cleanly
- [ ] DB seeded with 3 synthetic shipments
- [ ] All 3 demo flows run end-to-end without errors
- [ ] AI **cannot** autonomously set `cbp_released=true` (negative test passes)
- [ ] Evidence trail shows raw → extracted → verified chain
- [ ] Each team member knows their segment of the walkthrough
- [ ] Screenshots / screen recording ready as backup

> **Note:** All demo data is synthetic. No live ACE filing or real CBP codes are used.
