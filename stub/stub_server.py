"""
stub/stub_server.py — Lightweight FastAPI stub for M3 frontend development.

Returns hardcoded fixture data so M3 can build the UI before M2's real API
is ready. Runs on port 8001 to avoid colliding with the real API on 8000.

Usage:
    cd stub
    pip install fastapi uvicorn
    uvicorn stub_server:app --port 8001 --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Customs Clearance — Stub API", version="stub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Fixture data ──────────────────────────────────────────────────────────────

SHIPMENTS = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "reference_number": "SHP-001",
        "status": "COLLECT_DATA",
        "created_at": "2026-10-20T08:00:00",
        "documents": [
            {
                "id": "doc-001-pl",
                "doc_type": "PACKING_LIST",
                "file_hash": "pl_hash_001",
                "version": 1,
                "status": "extracted",
                "uploaded_at": "2026-10-20T08:05:00",
            }
        ],
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "reference_number": "SHP-002",
        "status": "ESCALATE",
        "created_at": "2026-10-20T08:10:00",
        "documents": [
            {
                "id": "doc-002-inv",
                "doc_type": "INVOICE",
                "file_hash": "inv_hash_002",
                "version": 1,
                "status": "verified",
                "uploaded_at": "2026-10-20T08:12:00",
            },
            {
                "id": "doc-002-pl",
                "doc_type": "PACKING_LIST",
                "file_hash": "pl_hash_002",
                "version": 1,
                "status": "verified",
                "uploaded_at": "2026-10-20T08:13:00",
            },
        ],
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "reference_number": "SHP-003",
        "status": "CUSTOMS_HOLD",
        "created_at": "2026-10-20T07:30:00",
        "documents": [
            {
                "id": "doc-003-inv",
                "doc_type": "INVOICE",
                "file_hash": "inv_hash_003",
                "version": 1,
                "status": "extracted",
                "uploaded_at": "2026-10-20T07:35:00",
            },
            {
                "id": "doc-003-pl",
                "doc_type": "PACKING_LIST",
                "file_hash": "pl_hash_003",
                "version": 1,
                "status": "extracted",
                "uploaded_at": "2026-10-20T07:36:00",
            },
        ],
    },
]

APPROVALS = [
    {
        "id": "appr-0000-0001",
        "action_id": "action-0000-0001",
        "shipment_id": "00000000-0000-0000-0000-000000000002",
        "role": "R2",
        "status": "PENDING",
        "payload_hash": "sha256-stub-discrepancy-hash",
        "requested_at": "2026-10-20T08:20:00",
        "resolved_at": None,
    },
    {
        "id": "appr-0000-0002",
        "action_id": "action-0000-0001",
        "shipment_id": "00000000-0000-0000-0000-000000000002",
        "role": "R3",
        "status": "PENDING",
        "payload_hash": "sha256-stub-discrepancy-hash",
        "requested_at": "2026-10-20T08:20:00",
        "resolved_at": None,
    },
]

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/shipments")
def list_shipments():
    return [
        {k: v for k, v in s.items() if k != "documents"}
        for s in SHIPMENTS
    ]


@app.get("/api/shipments/{shipment_id}")
def get_shipment(shipment_id: str):
    for s in SHIPMENTS:
        if s["id"] == shipment_id or s["reference_number"] == shipment_id:
            return s
    return {"detail": "Not found"}, 404


@app.get("/api/approvals")
def list_approvals(status: str | None = None, shipment_id: str | None = None):
    result = list(APPROVALS)
    if status:
        result = [a for a in result if a["status"] == status]
    if shipment_id:
        result = [a for a in result if a["shipment_id"] == shipment_id]
    return result


@app.patch("/api/approvals/{approval_id}")
def update_approval(approval_id: str, body: dict):
    for a in APPROVALS:
        if a["id"] == approval_id:
            a["status"] = body.get("status", a["status"])
            a["resolved_at"] = "2026-10-20T09:00:00"
            return a
    return {"detail": "Not found"}, 404


@app.get("/api/audit-logs/{shipment_id}")
def get_audit_logs(shipment_id: str):
    return [
        {
            "id": "log-001",
            "shipment_id": shipment_id,
            "actor": "agent",
            "event": "DOCUMENT_DISCREPANCY_DETECTED",
            "details": {"field": "line_quantity", "invoice": 500, "packing_list": 480},
            "timestamp": "2026-10-20T08:15:00",
        }
    ]


@app.get("/api/evidence/{shipment_id}")
def get_evidence(shipment_id: str):
    ship = next((s for s in SHIPMENTS if s["id"] == shipment_id), None)
    if not ship:
        return {"shipment_id": shipment_id, "documents": []}
    chains = []
    for doc in ship.get("documents", []):
        chain = [{"stage": "raw", "file_hash": doc["file_hash"], "timestamp": doc["uploaded_at"]}]
        if doc["status"] in ("extracted", "verified"):
            chain.append({"stage": "extracted", "fields": {}, "timestamp": doc["uploaded_at"]})
        if doc["status"] == "verified":
            chain.append({"stage": "verified", "consistency": "FAIL", "timestamp": doc["uploaded_at"]})
        chains.append({"doc_id": doc["id"], "doc_type": doc["doc_type"], "version": doc["version"], "chain": chain})
    return {"shipment_id": shipment_id, "reference_number": ship["reference_number"], "documents": chains}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "stub"}
