# Autonomous AI Customs Clearance — Live Demo Script
**Total runtime: ~10 minutes | Presenter: M5 coordinates, M1/M3/M4 explain their parts**

> ⚠️ All data is **synthetic**. No live ACE filing. No real CBP codes.
> `CLEARANCE_VERIFIED` is a research predicate — not an official customs release.

---

## Pre-Demo Checklist (complete before 10 AM)

```bash
# 1. Start all services
docker compose up -d

# 2. Run migrations + seed
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed.py

# 3. Confirm health
curl http://localhost:8000/health          # → {"status":"ok"}
curl http://localhost:3000                 # → Dashboard loads

# 4. Open browser tabs (pre-load before presenting)
#    Tab 1: http://localhost:3000                  ← Shipment List
#    Tab 2: http://localhost:3000/approvals         ← Approval Queue
#    Tab 3: http://localhost:3000/shipments/<SHP-002-id>  ← Detail pre-loaded
```

---

## Scenario C01 — Missing Commercial Invoice (~3 min)

**Presenter:** M3 drives the browser. M4 explains the document pipeline.

### Step 1 — Show the shipment list
- Open **Tab 1** (http://localhost:3000)
- Point out **SHP-001** with status badge `COLLECT_DATA` (orange)
- Say: *"The agent has already observed that a required document is missing."*

### Step 2 — Drill into the shipment
- Click **View →** on SHP-001
- Show the **Documents** panel — only a Packing List is present, no Invoice
- Show the **Evidence Trail** — Packing List is `extracted`, Invoice slot is empty
- Show the **Pending Approvals** sidebar — escalation to R3 (Supplier) already created

### Step 3 — Key point to make
> *"The AI agent detected the missing invoice during its OBSERVE state, transitioned to
> COLLECT_DATA, and created an approval request for the Supplier (R3) — all automatically,
> without human intervention up to this point."*

### Step 4 — Resolve (optional, if time permits)
- In the Approval Queue, approve the R3 request
- Explain that in production, the supplier would upload the document, triggering re-verification

---

## Scenario C02 — Quantity Mismatch (~4 min)

**Presenter:** M3 drives. M1 explains the FSM guard. M4 explains the D2 check.

### Step 1 — Open SHP-002 detail
- Navigate to **Tab 3** (SHP-002 detail page)
- Status badge shows `ESCALATE` (orange)
- Say: *"This shipment has an Invoice and a Packing List — but they disagree on quantity."*

### Step 2 — Show the Evidence Trail
- Point to the Evidence Trail panel:
  - Invoice: `raw → extracted → verified (FAIL)`
  - Packing List: `raw → extracted → verified (FAIL)`
- Say: *"M4's consistency check found Invoice qty=500 vs Packing List qty=480 — a delta of 20 units."*

### Step 3 — Show the Approval Queue
- Switch to **Tab 2** (Approvals page)
- Show two pending cards: `R2 — Warehouse Manager` and `R3 — Supplier / Exporter`
- Point out the payload hash fingerprint on each card

### Step 4 — Demonstrate the hard guard *(KEY DEMO POINT)*
> *"Notice: the AI agent did NOT change any document values. It cannot.
> The guard G-doc-immutable in the policy engine hard-blocks any
> MODIFY_DOCUMENT_FIELD action. Only the human can confirm the correct quantity."*

### Step 5 — Approve as Warehouse Manager (R2)
- In the Approval Queue, click **Approve** on the R2 card
- UI updates optimistically — badge changes to `APPROVED`

### Step 6 — Approve as Supplier (R3)
- Click **Approve** on the R3 card
- Say: *"Both required humans have confirmed. The agent can now resume."*

### Step 7 — Watch state transition
- Switch back to SHP-002 detail
- The **Agent State** sidebar shows the live FSM transitions:
  `ESCALATE → WAIT_EVENT → OBSERVE → VERIFY → CLEARANCE_VERIFIED`

---

## Scenario C09 — CBP Hold Coordination (~3 min)

**Presenter:** M5 runs the mock feed CLI. M1 explains the authority invariant.

### Step 1 — Open SHP-003
- Navigate to SHP-003 detail page
- Status badge shows `CUSTOMS_HOLD` (red)
- Say: *"An official CBP hold has been placed on this shipment."*

### Step 2 — Show the audit log evidence
- Point to the Agent State timeline — shows `CBP_HOLD_RECEIVED (source_verified=True)`
- Say: *"The hold arrived via the official CBP channel — source_verified=True."*

### Step 3 — Demonstrate the authority invariant *(KEY DEMO POINT)*
> *"The agent is currently blocked in WAIT_EVENT state. It CANNOT set
> `cbp_released=True` autonomously — even if the LLM recommends it.
> Only an event from the official CBP channel with source_verified=True
> can trigger the release. This is a hard cryptographic invariant in the guard layer."*

### Step 4 — Trigger mock CBP release
```bash
# Run in a terminal visible to the audience
python mocks/cbp_feed.py --scenario release
```
- Show output: `✓ CBP_RELEASE_RECEIVED emitted for SHP-003 (source_verified=True)`

### Step 5 — Watch the FSM progress
- Live state timeline in the browser updates in real-time:
  `WAIT_EVENT → VERIFY → CLEARANCE_VERIFIED`
- Status badge turns green: `CLEARANCE_VERIFIED`
- Say: *"The shipment is cleared — but only because the release came from the
  verified official channel. The AI never had the authority to do this alone."*

---

## Closing (30 seconds)

> *"What you just saw is a hybrid AI-human customs clearance system:
> - The AI observes, reasons with an LLM, and plans — autonomously.
> - Hard guards prevent it from taking consequential actions without authorisation.
> - Humans are brought in precisely when needed, with full evidence context.
> - The system is auditable end-to-end: every state transition, every document hash,
>   every approval decision is logged."*

---

## Emergency Fallback

If anything fails during the live demo:

```bash
# Quick restart
docker compose restart api

# Check logs
docker compose logs api --tail=50
docker compose logs frontend --tail=20

# Re-seed
docker compose exec api python scripts/seed.py
```

Screenshots of all 3 scenarios are in `demo/screenshots/` as a last resort.

---

## Team Segment Assignments

| Scenario | Presenter | Explains |
|----------|-----------|---------|
| C01 — Missing Invoice | M3 (browser) + M4 (document pipeline) | Evidence trail, document status |
| C02 — Qty Mismatch | M3 (browser) + M1 (FSM guard) | Hard guard, approval flow |
| C09 — CBP Hold | M5 (CLI) + M1 (authority invariant) | source_verified, cbp_released guard |
| Architecture Q&A | M2 | Schema, idempotency, outbox pattern |
