"""
mocks/erp_emitter.py — Continuous ERP/TMS mock event emitter.

Emits CARGO_ARRIVED and INVOICE_RECEIVED events to the API every N seconds.
Shipment IDs are resolved by calling GET /api/shipments and matching
reference numbers SHP-001 and SHP-002.

Usage:
    # Emit once then exit
    python mocks/erp_emitter.py --once

    # Emit every 10 seconds (default) until Ctrl-C
    python mocks/erp_emitter.py

    # Custom interval
    python mocks/erp_emitter.py --interval 30

    # Target a different API
    API_BASE_URL=http://localhost:8000 python mocks/erp_emitter.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get(url: str) -> list | dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> int:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def _resolve_shipment_ids() -> dict[str, str]:
    """Return { reference_number: id } for all seeded shipments."""
    try:
        return {s["reference_number"]: s["id"] for s in _http_get(f"{API_BASE}/api/shipments")}
    except Exception as exc:
        print(f"[erp_emitter] Could not resolve shipment IDs: {exc}", file=sys.stderr)
        return {}


def _post_event(event: dict) -> bool:
    status = _http_post(f"{API_BASE}/api/events", event)
    if status == 409:
        print(f"[erp_emitter] Duplicate event skipped: {event['event_id']}")
        return True
    if status in (200, 201):
        print(f"[erp_emitter] ✓ {event['event_type']} → {event.get('shipment_id', '?')[:8]}…")
        return True
    print(f"[erp_emitter] ✗ Unexpected status {status} for {event['event_type']}", file=sys.stderr)
    return False


def emit_once(shipment_map: dict[str, str]) -> None:
    """Emit one round of CARGO_ARRIVED + INVOICE_RECEIVED events."""
    shp1_id = shipment_map.get("SHP-001")
    shp2_id = shipment_map.get("SHP-002")

    if shp1_id:
        _post_event({
            "event_id": f"erp-cargo-{uuid.uuid4()}",
            "event_type": "CARGO_ARRIVED",
            "source_verified": False,
            "shipment_id": shp1_id,
            "payload": {
                "carrier": "MOCK_CARRIER",
                "vessel": "MV DEMO VESSEL",
                "eta": "2026-10-21T08:00:00Z",
            },
            "occurred_at": _now_iso(),
        })
    else:
        print("[erp_emitter] SHP-001 not found — skipping CARGO_ARRIVED")

    if shp2_id:
        _post_event({
            "event_id": f"erp-invoice-{uuid.uuid4()}",
            "event_type": "INVOICE_RECEIVED",
            "source_verified": False,
            "shipment_id": shp2_id,
            "payload": {
                "invoice_number": "INV-2026-0042",
                "amount": 6250.00,
                "currency": "USD",
            },
            "occurred_at": _now_iso(),
        })
    else:
        print("[erp_emitter] SHP-002 not found — skipping INVOICE_RECEIVED")


def main() -> None:
    parser = argparse.ArgumentParser(description="ERP/TMS mock event emitter")
    parser.add_argument("--once", action="store_true", help="Emit once and exit")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between rounds (default 10)")
    args = parser.parse_args()

    print(f"[erp_emitter] Targeting API at {API_BASE}")
    shipment_map = _resolve_shipment_ids()

    if not shipment_map:
        print("[erp_emitter] No shipments found — run scripts/seed.py first", file=sys.stderr)
        sys.exit(1)

    print(f"[erp_emitter] Resolved shipments: {list(shipment_map.keys())}")

    if args.once:
        emit_once(shipment_map)
        return

    print(f"[erp_emitter] Emitting every {args.interval}s — press Ctrl-C to stop")
    try:
        while True:
            emit_once(shipment_map)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[erp_emitter] Stopped.")


if __name__ == "__main__":
    main()
