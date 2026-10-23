# Member 2 Spec — Backend & Data Pipeline Lead
**Timeline: 8 hours | Demo: 10:00 AM**

---

## Your Goal
Deliver a running FastAPI server with a PostgreSQL schema, 4+ REST endpoints, event ingestion, idempotency enforcement, and a DB seeded with 3 synthetic shipments for the demo.

---

## Hour-by-Hour Tasks

### Hour 0–1 — Setup
- [ ] Clone repo, confirm Python 3.12 + PostgreSQL + Redis are reachable via Docker Compose (M5's setup)
- [ ] Install: `fastapi`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `celery`, `redis`, `pydantic`
- [ ] Confirm DB connection string: `postgresql://user:pass@localhost:5432/customs`
- [ ] Agree on OpenAPI YAML contract with M1 and M3

### Hour 1–3 — Database Schema + Migrations
Create SQLAlchemy models and Alembic migrations for these 7 tables:

#### `shipments`
```
id UUID PK, reference_number TEXT, status TEXT, created_at TIMESTAMP
```

#### `documents`
```
id UUID PK, shipment_id FK, doc_type TEXT, file_hash TEXT,
version INT, status TEXT, uploaded_at TIMESTAMP
```

#### `events`
```
id UUID PK, event_id TEXT UNIQUE, event_type TEXT, source_verified BOOL,
payload JSONB, processed_at TIMESTAMP
```

#### `agent_tasks`
```
id UUID PK, shipment_id FK, state TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
```

#### `agent_actions`
```
id UUID PK, task_id FK, action_type TEXT, idempotency_key TEXT UNIQUE,
payload JSONB, status TEXT, created_at TIMESTAMP
```

#### `approvals`
```
id UUID PK, action_id FK, role TEXT, status TEXT,
payload_hash TEXT, requested_at TIMESTAMP, resolved_at TIMESTAMP
```

#### `audit_logs`
```
id UUID PK, shipment_id FK, actor TEXT, event TEXT, details JSONB, timestamp TIMESTAMP
```

- [ ] Run `alembic upgrade head` — confirm all tables created
- [ ] Add `UNIQUE` constraint on `events.event_id` (deduplication)
- [ ] Add `UNIQUE` constraint on `agent_actions.idempotency_key`

### Hour 3–6 — REST API Endpoints

Implement these endpoints in `api/routes/`:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/shipments` | List all shipments with status |
| GET | `/api/shipments/{id}` | Get single shipment + document list |
| POST | `/api/events` | Ingest normalised event envelope |
| POST | `/api/agent-tasks` | Create new agent task |
| POST | `/api/approvals` | Create HITL approval request |
| PATCH | `/api/approvals/{id}` | Update approval status (approve/reject) |
| GET | `/api/approvals?shipment_id=` | List pending approvals for a shipment |
| GET | `/api/audit-logs/{shipment_id}` | Get audit trail for a shipment |

**Event ingestion rules:**
- Validate `event_id` is present; reject if missing
- Check `events` table for duplicate `event_id` — return `409 Conflict` if already processed
- Set `processed_at = now()` on success

**Idempotency enforcement:**
- `POST /api/agent-actions` must include `idempotency_key` in body
- Return `200 OK` with existing record if key already exists (do not re-execute)
- Return `409 Conflict` with message if concurrent duplicate detected

### Hour 3–6 — Outbox Pattern (for Celery)
- [ ] Create `outbox` table: `id`, `payload JSONB`, `status TEXT`, `created_at`
- [ ] On each `agent_actions` creation, also insert a row into `outbox`
- [ ] Create Celery task `dispatch_outbox_events` that polls outbox and publishes to Redis queue

### Hour 6–7.5 — Seed Data
- [ ] Create `scripts/seed.py` that inserts 3 synthetic shipments:
  - **SHP-001 (C01):** Status `COLLECT_DATA`, missing Commercial Invoice document
  - **SHP-002 (C02):** Status `ESCALATE`, Invoice qty=500, Packing List qty=480 already flagged
  - **SHP-003 (C09):** Status `CUSTOMS_HOLD`, CBP hold event already ingested
- [ ] Each shipment should have: at least 2 document records + 1 agent_task + 1 pending approval (C02)
- [ ] Run seed: `python scripts/seed.py`

### Hour 7.5–8 — Demo Rehearsal
- [ ] Confirm all endpoints respond correctly with seeded data
- [ ] Run `pytest tests/` — all tests pass
- [ ] Know your segment: explain the schema and idempotency enforcement if asked

---

## Key Files to Create

```
api/
  main.py                  # FastAPI app entry point
  routes/
    shipments.py           # GET /api/shipments, GET /api/shipments/{id}
    events.py              # POST /api/events
    agent_tasks.py         # POST /api/agent-tasks
    approvals.py           # POST/PATCH/GET /api/approvals
    audit_logs.py          # GET /api/audit-logs/{shipment_id}
  models/
    shipment.py            # SQLAlchemy models
    document.py
    event.py
    agent_task.py
    agent_action.py
    approval.py
    audit_log.py
  schemas/
    shipment.py            # Pydantic request/response schemas
    event.py
    approval.py
db/
  database.py              # Engine + session factory
  migrations/              # Alembic migration files
scripts/
  seed.py                  # Seed 3 synthetic shipments
tasks/
  outbox.py                # Celery outbox dispatch task
tests/
  test_events.py           # Duplicate event rejection test
  test_approvals.py        # Approval lifecycle tests
  test_idempotency.py      # Duplicate action key test
```

---

## Interfaces You Expose (consumed by M1 and M3)

See endpoint table above. All responses use JSON.

**Standard event envelope (ingest via `POST /api/events`):**
```json
{
  "event_id": "uuid-v4",
  "event_type": "CBP_HOLD_RECEIVED",
  "source_verified": true,
  "shipment_id": "uuid-v4",
  "payload": { "hold_code": "TIB", "details": "..." },
  "occurred_at": "2026-10-20T10:00:00Z"
}
```

---

## Definition of Done
- [ ] `alembic upgrade head` runs without error
- [ ] All 8 REST endpoints return correct responses with seeded data
- [ ] Duplicate event `event_id` returns `409 Conflict`
- [ ] Duplicate `idempotency_key` returns `200 OK` with original record
- [ ] DB seeded with SHP-001, SHP-002, SHP-003 ready for demo
- [ ] `pytest tests/` passes
