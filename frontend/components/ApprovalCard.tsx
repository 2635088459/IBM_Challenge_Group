// components/ApprovalCard.tsx — HITL approval card with Approve/Reject buttons

"use client";

import { useState } from "react";
import { Approval, updateApproval } from "@/lib/api";
import StatusBadge from "./StatusBadge";

const ROLE_LABELS: Record<string, string> = {
  R2: "Warehouse Manager",
  R3: "Supplier / Exporter",
  R4: "Trade Compliance Officer",
  R5: "Customs Broker",
  R6: "CBP Official",
  R7: "Finance Controller",
  R9: "Legal / Compliance",
};

interface Props {
  approval: Approval;
  shipmentRef?: string;
  onResolved: (updated: Approval) => void;
}

function ageMinutes(isoDate: string): number {
  return Math.floor((Date.now() - new Date(isoDate).getTime()) / 60000);
}

function formatAge(mins: number): string {
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m ago`;
}

export default function ApprovalCard({ approval, shipmentRef, onResolved }: Props) {
  const [loading, setLoading] = useState<"APPROVED" | "REJECTED" | null>(null);
  const [localApproval, setLocalApproval] = useState<Approval>(approval);

  const age = ageMinutes(localApproval.requested_at);
  const isStale = age > 30;
  const isPending = localApproval.status === "PENDING";

  async function handleAction(status: "APPROVED" | "REJECTED") {
    setLoading(status);
    try {
      // Optimistic update
      setLocalApproval((prev) => ({ ...prev, status }));
      const updated = await updateApproval(localApproval.id, status);
      setLocalApproval(updated);
      onResolved(updated);
    } catch (err: unknown) {
      // Revert optimistic update on error
      setLocalApproval((prev) => ({ ...prev, status: "PENDING" }));
      const message = err instanceof Error ? err.message : String(err);
      alert(`Failed to ${status.toLowerCase()} approval: ${message}`);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div
      className={`rounded-lg border p-4 space-y-3 ${
        isStale && isPending ? "border-red-300 bg-red-50" : "border-gray-200 bg-white"
      }`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-gray-900 text-sm">
            {shipmentRef ?? localApproval.shipment_id?.slice(0, 8) ?? "—"}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            Role required:{" "}
            <span className="font-medium text-gray-700">
              {ROLE_LABELS[localApproval.role] ?? localApproval.role}
            </span>
          </p>
        </div>
        <StatusBadge status={localApproval.status} size="sm" />
      </div>

      {/* Payload hash fingerprint */}
      {localApproval.payload_hash && (
        <p className="text-xs font-mono text-gray-400 truncate">
          hash: {localApproval.payload_hash.slice(0, 16)}…
        </p>
      )}

      {/* Age */}
      <p className={`text-xs ${isStale && isPending ? "text-red-600 font-semibold" : "text-gray-400"}`}>
        Requested {formatAge(age)}
        {isStale && isPending && " — expires soon!"}
      </p>

      {/* Expired warning */}
      {localApproval.status === "EXPIRED" && (
        <p className="text-xs text-gray-500 italic">
          Approval expired — re-submit required
        </p>
      )}

      {/* Action buttons — only shown for PENDING */}
      {isPending && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => handleAction("APPROVED")}
            disabled={loading !== null}
            className="flex-1 rounded-md bg-green-600 px-3 py-1.5 text-xs font-semibold text-white
                       hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading === "APPROVED" ? "Approving…" : "Approve"}
          </button>
          <button
            onClick={() => handleAction("REJECTED")}
            disabled={loading !== null}
            className="flex-1 rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white
                       hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading === "REJECTED" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      )}
    </div>
  );
}
