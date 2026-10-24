"""
Seed script — restores the 3 synthetic demo shipments to their initial state.

  SHP-001 (C01): COLLECT_DATA  — missing Commercial Invoice
  SHP-002 (C02): ESCALATE      — Invoice qty=500 vs Packing List qty=480
  SHP-003 (C09): CUSTOMS_HOLD  — CBP hold event already ingested

Shipment ids are kept across runs (see db/demo_data.py), so open pages stay valid.

Run from backend/:
    DATABASE_URL=postgresql://customs:customs@localhost:5432/customs python scripts/seed.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import _get_session_local
from db.demo_data import reset_all


if __name__ == "__main__":
    db = _get_session_local()()
    try:
        ids = reset_all(db)
    finally:
        db.close()
    print("✅ Seeded: SHP-001 (C01), SHP-002 (C02), SHP-003 (C09)")
    for ref, sid in ids.items():
        print(f"   {ref} id: {sid}")
