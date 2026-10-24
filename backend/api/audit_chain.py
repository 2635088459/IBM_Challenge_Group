"""
api/audit_chain.py — Tamper-evident hash chain over audit_logs (per shipment).

Every new AuditLog row gets
    prev_hash  = entry_hash of the shipment's previous entry (GENESIS for the first)
    entry_hash = sha256(prev_hash + canonical JSON of the row's content)

so editing a row breaks its own hash, and deleting or re-hashing a row breaks
the link from the next one.  Hashes are assigned in a before_flush listener,
so every code path that writes audit logs is covered without changes.

Limitation (demo): the chain head is not anchored outside the database, so an
attacker who rewrites every hash from the tampered row onwards would go unnoticed.
Publishing the head hash (shown in the UI) to an external store closes that gap.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session, aliased

from api.models.models import AuditLog

GENESIS = "0" * 64


def compute_hash(prev_hash: str, entry: AuditLog) -> str:
    body = json.dumps(
        {
            "id": str(entry.id),
            "shipment_id": str(entry.shipment_id),
            "actor": entry.actor,
            "event": entry.event,
            "details": entry.details,
            "timestamp": entry.timestamp.isoformat(timespec="microseconds"),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _current_head(session: Session, shipment_id: str) -> str:
    """entry_hash of the chained entry that no other entry points back to."""
    nxt = aliased(AuditLog)
    head = session.execute(
        select(AuditLog.entry_hash)
        .where(AuditLog.shipment_id == shipment_id, AuditLog.entry_hash.isnot(None))
        .where(~select(nxt.id).where(nxt.prev_hash == AuditLog.entry_hash).exists())
        .limit(1)
    ).scalar()
    return head or GENESIS


@event.listens_for(Session, "before_flush")
def _chain_new_entries(session: Session, _flush_context, _instances) -> None:
    new_entries = [o for o in session.new if isinstance(o, AuditLog)]
    if not new_entries:
        return
    heads: dict[str, str] = {}
    with session.no_autoflush:
        for entry in new_entries:
            # Content must be final before hashing — fill column defaults now
            if entry.id is None:
                entry.id = str(uuid.uuid4())
            if entry.timestamp is None:
                entry.timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
            sid = str(entry.shipment_id)
            if sid not in heads:
                heads[sid] = _current_head(session, sid)
            entry.prev_hash = heads[sid]
            entry.entry_hash = compute_hash(entry.prev_hash, entry)
            heads[sid] = entry.entry_hash


def verify_chain(entries: list[AuditLog]) -> dict[str, Any]:
    """
    Walk the chain from GENESIS and recompute every hash.
    Entry statuses: ok | modified (content changed) | after_break (follows a
    modified entry, cannot be trusted) | unlinked (not reachable — an earlier
    entry was deleted or its hash rewritten).
    """
    chained = [e for e in entries if e.entry_hash]
    by_prev = {e.prev_hash: e for e in chained}

    walked: list[tuple[AuditLog, str]] = []
    broken: dict[str, Any] | None = None
    cur, seen = GENESIS, set()
    while cur in by_prev and by_prev[cur].id not in seen:
        e = by_prev[cur]
        seen.add(e.id)
        if broken:
            status = "after_break"
        elif compute_hash(e.prev_hash, e) != e.entry_hash:
            status = "modified"
            broken = {"reason": "Entry content was changed after it was written"}
        else:
            status = "ok"
        if status == "modified":
            broken.update(_describe(e, len(walked)))
        walked.append((e, status))
        cur = e.entry_hash

    unlinked = sorted((e for e in chained if e.id not in seen), key=lambda e: e.timestamp)
    if unlinked and not broken:
        broken = {
            "reason": "Chain link missing — an earlier entry was deleted or its hash rewritten",
            **_describe(unlinked[0], len(walked)),
        }

    return {
        "valid": broken is None,
        "entries": len(chained),
        "legacy_unchained": len(entries) - len(chained),
        "head_hash": walked[-1][0].entry_hash if walked else None,
        "broken": broken,
        "chain": [_summary(e, s) for e, s in walked] + [_summary(e, "unlinked") for e in unlinked],
    }


def _describe(e: AuditLog, position: int) -> dict[str, Any]:
    return {"position": position + 1, "id": str(e.id), "event": e.event, "timestamp": e.timestamp}


def _summary(e: AuditLog, status: str) -> dict[str, Any]:
    return {"id": str(e.id), "event": e.event, "timestamp": e.timestamp, "status": status}
