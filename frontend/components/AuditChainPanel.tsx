// components/AuditChainPanel.tsx — Verify the tamper-evident audit hash chain (and a demo tamper button)

"use client";

import { useState } from "react";
import { AuditChainResult, verifyAuditChain, tamperAuditDemo, parseApiDate } from "@/lib/api";

const BLOCK_STYLE: Record<string, string> = {
  ok:          "bg-green-500",
  modified:    "bg-red-600 ring-2 ring-red-300",
  after_break: "bg-gray-300",
  unlinked:    "bg-red-300",
};

const BLOCK_LABEL: Record<string, string> = {
  ok: "verified",
  modified: "content changed",
  after_break: "cannot be trusted (after the break)",
  unlinked: "unlinked",
};

function fmtTime(iso: string) {
  try {
    return parseApiDate(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

export default function AuditChainPanel({ shipmentId, onTampered }: { shipmentId: string; onTampered?: () => void }) {
  const [result, setResult] = useState<AuditChainResult | null>(null);
  const [tamperNote, setTamperNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<"verify" | "tamper" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setBusy("verify");
    setError(null);
    try {
      setResult(await verifyAuditChain(shipmentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(null);
    }
  }

  async function tamper() {
    setBusy("tamper");
    setError(null);
    try {
      const t = await tamperAuditDemo(shipmentId);
      setTamperNote(
        "event" in t.after
          ? `Rewrote an audit entry ${t.event} → ${String(t.after.event)}, directly in the database.`
          : `Rewrote the reason on a ${t.event} entry to "${(t.after.details as { reason?: string })?.reason}", directly in the database.`
      );
      setResult(null);
      onTampered?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tamper failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        Each entry stores the hash of the one before it. Changing or deleting any entry breaks the chain.
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={verify}
          disabled={busy !== null}
          className="px-3 py-1.5 rounded-md bg-gray-900 text-white text-xs font-medium hover:bg-gray-700 disabled:opacity-50"
        >
          {busy === "verify" ? "Verifying…" : "Verify integrity"}
        </button>
        <button
          onClick={tamper}
          disabled={busy !== null}
          className="px-3 py-1.5 rounded-md border border-red-300 text-red-700 text-xs font-medium hover:bg-red-50 disabled:opacity-50"
          title="Demo only: edits a stored audit entry with a raw SQL UPDATE. Undo with ↺ Reset this demo."
        >
          {busy === "tamper" ? "Tampering…" : "Simulate tampering (demo)"}
        </button>
      </div>

      {tamperNote && (
        <p className="text-xs text-red-800 bg-red-50 rounded px-3 py-2">
          {tamperNote} Now click <span className="font-semibold">Verify integrity</span>.
        </p>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}

      {result && (
        <div className="space-y-3">
          {result.valid ? (
            <div className="rounded-md bg-green-50 border border-green-200 px-3 py-2 text-xs text-green-800">
              <p className="font-semibold">✓ Chain intact — all {result.entries} entries verified</p>
              {result.head_hash && (
                <p className="font-mono text-green-700 mt-0.5 truncate" title={result.head_hash}>
                  head {result.head_hash.slice(0, 24)}…
                </p>
              )}
            </div>
          ) : (
            <div className="rounded-md bg-red-50 border border-red-300 px-3 py-2 text-xs text-red-800">
              <p className="font-semibold">✕ Chain broken at entry #{result.broken?.position}</p>
              <p className="mt-0.5">
                <span className="font-mono">{result.broken?.event}</span>
                {result.broken?.timestamp && <> · {fmtTime(result.broken.timestamp)}</>}
              </p>
              <p className="mt-0.5">{result.broken?.reason}</p>
            </div>
          )}

          {/* One block per entry, in chain order */}
          <div className="flex flex-wrap gap-1" aria-label="Audit chain blocks">
            {result.chain.map((c, i) => (
              <span
                key={c.id}
                className={`w-3.5 h-3.5 rounded-sm ${BLOCK_STYLE[c.status]}`}
                title={`#${i + 1} ${c.event} — ${BLOCK_LABEL[c.status]}`}
              />
            ))}
          </div>
          {result.legacy_unchained > 0 && (
            <p className="text-[11px] text-gray-400">
              {result.legacy_unchained} older entries predate the chain and are not covered.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
