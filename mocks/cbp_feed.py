"""
mocks/cbp_feed.py — On-demand CBP status feed mock.

Simulates the official CBP channel for Scenario C09.
ALL events from this feed are emitted with source_verified=True —
this is the only channel that can trigger the cbp_released guard.

Usage:
    # Trigger a CBP hold on SHP-003
    python mocks/cbp_feed.py --scenario hold

    # Release the CBP hold on SHP-003
    python mocks/cbp_feed.py --scenario release

    # Target a different API
    API_BASE_URL=http://localhost:8000 python mocks/cbp_feed.py --scenario hold

    # Target a specific shipment
    python mocks/cbp_feed.py --scenario hold --ref SHP-003
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

SCENARIOS = {
    "hold": {
        "event_type": "CBP_HOLD_RECEIVED",
        "payload": {
            "hold_code": "TIB",
            "hold_reason": "Targeted Inspection — random examination",
            "issuing_officer": "CBP Officer Mock",
            "exam_location": "Port of Entry — Demo Terminal",
        },
    },
    "release": {
        "event_type": "CBP_RELEASE_RECEIVED",
        "payload": {
            "release_code": "REL-001",
            "release_reason": "Examination completed — no violations found",
            "issuing_officer": "CBP Officer Mock",
        },
    },
    "intensive": {
        "event_type": "CBP_INTENSIVE_EXAM_REQUESTED",
        "payload": {
            "exam_type": "CET",
            "exam_location": "Exam Station 7",
        },
    },
}


def _http_get(url: str) -> list | dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def _resolve_shipment_id(reference: str) -> str | None:
    try:
        for s in _http_get(f"{API_BASE}/api/shipments"):
            if s["reference_number"] == reference:
                return s["id"]
    except Exception as exc:
        print(f"[cbp_feed] Could not resolve {reference}: {exc}", file=sys.stderr)
    return None


def emit_cbp_event(scenario_name: str, shipment_ref: str) -> bool:
    scenario = SCENARIOS.get(scenario_name)
    if not scenario:
        print(f"[cbp_feed] Unknown scenario '{scenario_name}'. Choose: {list(SCENARIOS)}", file=sys.stderr)
        return False

    shipment_id = _resolve_shipment_id(shipment_ref)
    if not shipment_id:
        print(f"[cbp_feed] Shipment '{shipment_ref}' not found. Run scripts/seed.py first.", file=sys.stderr)
        return False

    event = {
        "event_id": f"cbp-{scenario_name}-{uuid.uuid4()}",
        "event_type": scenario["event_type"],
        "source_verified": True,          # ← CRITICAL: official CBP channel
        "shipment_id": shipment_id,
        "payload": scenario["payload"],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }

    status, _ = _http_post(f"{API_BASE}/api/events", event)
    if status == 409:
        print(f"[cbp_feed] Duplicate event — already emitted for this shipment")
        return True
    if status in (200, 201):
        print(
            f"[cbp_feed] ✓ {scenario['event_type']} emitted for {shipment_ref} "
            f"(source_verified=True, id={event['event_id'][:12]}…)"
        )
        return True
    print(f"[cbp_feed] ✗ Unexpected status {status}", file=sys.stderr)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CBP status feed mock — emits source_verified=True events"
    )
    parser.add_argument(
        "--scenario",
        required=True,
        choices=list(SCENARIOS),
        help="Scenario to emit: hold | release | intensive",
    )
    parser.add_argument(
        "--ref",
        default="SHP-003",
        help="Shipment reference number (default: SHP-003)",
    )
    args = parser.parse_args()

    print(f"[cbp_feed] Targeting API at {API_BASE}")
    success = emit_cbp_event(args.scenario, args.ref)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
