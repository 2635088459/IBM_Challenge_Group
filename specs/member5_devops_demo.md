# Member 5 Spec — DevOps, Integration & Demo Coordinator
**Timeline: 8 hours | Demo: 10:00 AM**

---

## Your Goal
Make sure every service starts with a single command, mock feeds produce realistic events, 3 smoke tests pass, and the live demo runs cleanly for 3 scenarios at 10 AM.

---

## Hour-by-Hour Tasks

### Hour 0–1 — Docker Compose & Stub Server
- [ ] Create `docker-compose.yml` with these services:
  - `db` — PostgreSQL 16, port 5432
  - `redis` — Redis 7, port 6379
  - `api` — Python FastAPI server (M2), port 8000
  - `worker` — Celery worker (M2's outbox)
  - `frontend` — Next.js (M3), port 3000
- [ ] Create a **stub API server** (`stub/stub_server.py`) using FastAPI that returns hardcoded JSON for M3 to build against before M2 is ready
  - `GET /api/shipments` → returns 3 hardcoded shipments
  - `GET /api/approvals?status=PENDING` → returns 1 hardcoded pending approval
- [ ] Confirm `docker compose up` starts all 5 services without errors
- [ ] Share `.env.example` with all required env vars:
  ```
  DATABASE_URL=postgresql://customs:customs@db:5432/customs
  REDIS_URL=redis://redis:6379/0
  WATSONX_API_KEY=
  WATSONX_PROJECT_ID=
  ```

### Hour 1–3 — Mock Event Feeds

#### ERP/TMS Mock Emitter (`mocks/erp_emitter.py`)
- [ ] Emits these events every 10 seconds (configurable) via `POST /api/events`:
  - `CARGO_ARRIVED` — shipment SHP-001
  - `INVOICE_RECEIVED` — shipment SHP-002
- [ ] Each event uses the standard envelope:
  ```json
  {
    "event_id": "uuid-v4",
    "event_type": "CARGO_ARRIVED",
    "source_verified": false,
    "shipment_id": "SHP-001-uuid",
    "payload": { "carrier": "MOCK_CARRIER", "eta": "2026-10-21T08:00:00Z" },
    "occurred_at": "2026-10-20T12:00:00Z"
  }
  ```

#### CBP Status Feed Mock (`mocks/cbp_feed.py`)
- [ ] On demand (triggered by `python mocks/cbp_feed.py --scenario hold`):
  - Emits `CBP_HOLD_RECEIVED` for SHP-003 with `source_verified=true`
- [ ] On demand (triggered by `python mocks/cbp_feed.py --scenario release`):
  - Emits `CBP_RELEASE_RECEIVED` for SHP-003 with `source_verified=true`
- [ ] These must set `source_verified=true` — they simulate the official CBP channel

### Hour 3–6 — Integration Smoke Tests (`tests/integration/`)

Write these 3 tests using `pytest` + `httpx`:

#### Test 1 — Wrong-Role Approval Attempt
```
1. Create an approval with role = "R4" (Trade Compliance)
2. Attempt to approve it as role = "R2" (Warehouse)
3. Assert: API returns 403 Forbidden
```

#### Test 2 — Stale Approval Block
```
1. Create an approval
2. Manually set requested_at to 2 hours ago in DB
3. Attempt to approve it
4. Assert: API returns 409 with message "approval_expired"
```

#### Test 3 — Duplicate Event Rejection
```
1. POST /api/events with event_id = "test-event-001"
2. POST /api/events again with the same event_id = "test-event-001"
3. Assert: second call returns 409 Conflict
```

- [ ] All 3 tests pass: `pytest tests/integration/ -v`

### Hour 6–7.5 — Demo Script & Dry Run

Write `demo/demo_script.md` with step-by-step presenter notes:

#### Scenario C01 — Missing Commercial Invoice (3 minutes)
```
1. Open shipment SHP-001 on dashboard
2. Show status = COLLECT_DATA, document list shows no Invoice
3. Point out the pending ESCALATE approval in the queue for R3 (Supplier)
4. Upload a synthetic invoice document
5. Watch status update to VERIFY → CLEARANCE_VERIFIED
```

#### Scenario C02 — Quantity Mismatch (4 minutes)
```
1. Open shipment SHP-002
2. Show documents: Invoice (qty 500) + Packing List (qty 480)
3. Evidence trail shows: raw → extracted → verified (FAIL — discrepancy)
4. Show approval card in queue: role R2 (Warehouse) + R3 (Supplier) required
5. Approve as R2, then as R3
6. Watch agent transition: ESCALATE → ACT → VERIFY
7. Key point: AI could not change document values — human confirmed
```

#### Scenario C09 — CBP Hold Coordination (3 minutes)
```
1. Open shipment SHP-003, status = CUSTOMS_HOLD (shown in red)
2. Run: python mocks/cbp_feed.py --scenario hold (or already seeded)
3. Show event in audit log: CBP_HOLD_RECEIVED, source_verified=true
4. Show agent is blocked — cbp_released flag is NOT set
5. Run: python mocks/cbp_feed.py --scenario release
6. Watch status update: WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED
7. Key point: only official CBP channel (source_verified=true) can trigger release
```

- [ ] Run the full demo dry-run at hour 7.5 with all team members watching
- [ ] Fix any blocking issues (service fails to start, API timeout, etc.)

### Hour 7.5–8 — Final Checks
- [ ] `docker compose down && docker compose up` — confirm clean start from scratch
- [ ] Take screenshots of all 3 key demo moments as fallback
- [ ] (Optional) Record a 5-minute screen recording of the full demo as ultimate backup
- [ ] Brief the team: who presents which scenario, how to run the mock feeds

---

## Key Files to Create

```
docker-compose.yml
.env.example
stub/
  stub_server.py          # FastAPI stub for frontend development
mocks/
  erp_emitter.py          # Emits CARGO_ARRIVED, INVOICE_RECEIVED
  cbp_feed.py             # CLI: --scenario hold | --scenario release
tests/
  integration/
    test_wrong_role.py
    test_stale_approval.py
    test_duplicate_event.py
demo/
  demo_script.md          # Step-by-step presenter notes for C01, C02, C09
  screenshots/            # Fallback screenshots (captured at hour 7.5)
```

---

## Docker Compose Reference

```yaml
# docker-compose.yml skeleton
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: customs
      POSTGRES_PASSWORD: customs
      POSTGRES_DB: customs
    ports: ["5432:5432"]

  redis:
    image: redis:7
    ports: ["6379:6379"]

  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ports: ["8000:8000"]
    depends_on: [db, redis]
    env_file: .env

  worker:
    build: .
    command: celery -A tasks.outbox worker --loglevel=info
    depends_on: [db, redis]
    env_file: .env

  frontend:
    build: ./frontend
    command: npm run dev
    ports: ["3000:3000"]
    environment:
      NEXT_PUBLIC_API_URL: http://api:8000
```

---

## Definition of Done
- [ ] `docker compose up` starts all 5 services cleanly (green health)
- [ ] Stub server returns correct fixture data for M3 from hour 1
- [ ] `python mocks/erp_emitter.py` emits events and they appear in M2's DB
- [ ] `python mocks/cbp_feed.py --scenario hold` creates CBP_HOLD_RECEIVED event
- [ ] All 3 integration smoke tests pass: `pytest tests/integration/ -v`
- [ ] Full demo dry-run completed — all 3 scenarios run without errors
- [ ] Screenshots captured as fallback for each scenario
- [ ] `demo/demo_script.md` ready with presenter step-by-step notes
