# Member 3 Spec — Frontend & HITL Dashboard Lead
**Timeline: 8 hours | Demo: 10:00 AM**

---

## Your Goal
Deliver a working Next.js dashboard that shows live shipment status, an approval queue with role-aware routing, real-time agent state updates, and an evidence trail panel — all connected to M2's API.

---

## Hour-by-Hour Tasks

### Hour 0–1 — Setup
- [ ] Clone repo, confirm Node 18+ and npm/pnpm work
- [ ] `npx create-next-app@latest frontend --typescript --tailwind --app`
- [ ] Install: `socket.io-client`, `swr`, `axios`
- [ ] Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`
- [ ] Confirm stub API (M5's server) is reachable at `localhost:8000`

### Hour 1–3 — Shipment Dashboard (Core Pages)

#### Page 1: `/` — Shipment List
- [ ] Fetch `GET /api/shipments` via SWR
- [ ] Table columns: **Reference #**, **Status**, **Last Updated**, **Pending Approvals**
- [ ] Status badge colours:
  - `OBSERVE` → grey
  - `ESCALATE` / `COLLECT_DATA` → orange
  - `CUSTOMS_HOLD` → red
  - `CLEARANCE_VERIFIED` → green
- [ ] Click a row → navigate to `/shipments/[id]`

#### Page 2: `/shipments/[id]` — Shipment Detail
- [ ] Fetch `GET /api/shipments/{id}`
- [ ] Show: reference number, current status, document list with doc_type + file_hash
- [ ] Show: live **Agent State** indicator (updates via Socket.IO)
- [ ] Sidebar: pending approval requests for this shipment

### Hour 3–6 — HITL Approval Queue

#### Page 3: `/approvals` — Approval Queue
- [ ] Fetch `GET /api/approvals?status=PENDING`
- [ ] Show each approval as a card:
  - Shipment reference, action type, **role required** (R2/R3/R4)
  - Payload summary (e.g. "Quantity discrepancy: Invoice 500 vs PL 480")
  - `payload_hash` shown as short fingerprint
  - Age timer — highlight red if > 30 minutes old
- [ ] Two buttons per card: **Approve** / **Reject**
  - On click: call `PATCH /api/approvals/{id}` with `{ status: "APPROVED" | "REJECTED" }`
  - Optimistic UI update; refresh queue on success

#### Role-Aware Routing Display
- [ ] Show role label on each approval card:
  - `R2` → "Warehouse Manager"
  - `R3` → "Supplier / Exporter"
  - `R4` → "Trade Compliance Officer"
  - `R5` → "Customs Broker"
- [ ] (For demo only) A simple role selector dropdown at top of page lets the presenter switch "current user" role to show role-filtering in action

#### Approval Status States
- `PENDING` → blue badge
- `APPROVED` → green badge
- `REJECTED` → red badge
- `EXPIRED` → grey badge + warning message "Approval expired — re-submit required"

### Hour 6–7.5 — Real-Time + Evidence Trail

#### Socket.IO — Live Agent State
- [ ] In `shipments/[id]` page, connect to `ws://localhost:8000/ws`
- [ ] Listen for `agent_state_update` events:
  ```json
  { "shipment_id": "...", "from_state": "REASON", "to_state": "PLAN", "reason": "...", "timestamp": "..." }
  ```
- [ ] Render a live **state timeline** showing each FSM transition with reason text

#### Evidence Trail Panel
- [ ] On shipment detail page, show evidence chain for each document:
  ```
  raw  →  extracted  →  verified
  ```
- [ ] Each step shows: file_hash, extracted fields (if any), verified_at timestamp
- [ ] Visual indicator: green checkmark = verified, amber clock = extracted, grey = raw only

### Hour 7.5–8 — Demo Rehearsal
- [ ] Confirm all 3 seeded shipments (SHP-001/002/003) display correctly
- [ ] Walk through C02: Approval card appears → presenter approves → status updates
- [ ] Walk through C09: Customs Hold status shown in red → evidence trail visible
- [ ] Know your demo segment: narrate the approval flow and evidence trail

---

## Key Files to Create

```
frontend/
  app/
    page.tsx                     # Shipment list page
    shipments/
      [id]/
        page.tsx                 # Shipment detail + live state + evidence
    approvals/
      page.tsx                   # Approval queue
  components/
    ShipmentTable.tsx            # Reusable table with status badges
    ApprovalCard.tsx             # Card with Approve/Reject buttons
    AgentStateTimeline.tsx       # Live FSM state transitions
    EvidenceTrail.tsx            # raw → extracted → verified display
    StatusBadge.tsx              # Colour-coded status pill
  lib/
    api.ts                       # Typed wrappers for all API calls
    socket.ts                    # Socket.IO client singleton
  .env.local                     # NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## API Calls You Need (from M2)

| What | Call |
|------|------|
| List shipments | `GET /api/shipments` |
| Shipment detail | `GET /api/shipments/{id}` |
| List pending approvals | `GET /api/approvals?status=PENDING` |
| Approve / Reject | `PATCH /api/approvals/{id}` |
| Audit log | `GET /api/audit-logs/{shipment_id}` |

---

## Real-Time (from M1)

- Socket.IO event: `agent_state_update` on channel `ws://localhost:8000/ws`
- Display each transition in the state timeline component

---

## Definition of Done
- [ ] Shipment list loads with all 3 seeded shipments + correct status badges
- [ ] Approval queue shows C02 pending approval with correct role label
- [ ] Approve button calls API and UI updates without page refresh
- [ ] Agent state timeline shows live FSM transitions during demo
- [ ] Evidence trail panel visible on SHP-002 showing at least 2 chain steps
- [ ] EXPIRED badge shown when approval card > 30 min old
