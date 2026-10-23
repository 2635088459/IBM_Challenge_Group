// app/approvals/page.tsx — HITL Approval Queue with role selector

"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, Approval, ShipmentListItem } from "@/lib/api";
import ApprovalCard from "@/components/ApprovalCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ROLES = [
  { value: "ALL",  label: "All Roles" },
  { value: "R2",   label: "R2 — Warehouse Manager" },
  { value: "R3",   label: "R3 — Supplier / Exporter" },
  { value: "R4",   label: "R4 — Trade Compliance Officer" },
  { value: "R5",   label: "R5 — Customs Broker" },
];

const STATUS_TABS = ["PENDING", "APPROVED", "REJECTED", "EXPIRED"] as const;
type StatusTab = (typeof STATUS_TABS)[number];

export default function ApprovalsPage() {
  const [activeStatus, setActiveStatus] = useState<StatusTab>("PENDING");
  const [roleFilter, setRoleFilter] = useState("ALL");

  // Fetch all approvals for the active status
  const { data: approvals, mutate, isLoading, error } = useSWR<Approval[]>(
    `${API_URL}/api/approvals?status=${activeStatus}`,
    fetcher,
    { refreshInterval: 5000 }
  );

  // Fetch shipments to resolve reference numbers
  const { data: shipments } = useSWR<ShipmentListItem[]>(
    `${API_URL}/api/shipments`,
    fetcher
  );
  const shipmentMap = useMemo(() => {
    const m: Record<string, string> = {};
    (shipments ?? []).forEach((s) => { m[s.id] = s.reference_number; });
    return m;
  }, [shipments]);

  const filtered = useMemo(() => {
    if (!approvals) return [];
    if (roleFilter === "ALL") return approvals;
    return approvals.filter((a) => a.role === roleFilter);
  }, [approvals, roleFilter]);

  function handleResolved(_updated: Approval) {
    mutate();
  }

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Nav */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">AI Customs Clearance</h1>
          <p className="text-xs text-gray-400">Autonomous agent — synthetic demo data only</p>
        </div>
        <nav className="flex gap-4 text-sm">
          <Link href="/" className="text-gray-600 hover:text-blue-600">Shipments</Link>
          <Link href="/approvals" className="font-semibold text-blue-600">Approvals</Link>
        </nav>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <h2 className="text-xl font-semibold text-gray-900">Approval Queue</h2>

          {/* Role selector (demo mode) */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 font-medium">Viewing as:</label>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white
                         focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <span className="text-xs text-orange-500 font-medium">[demo mode]</span>
          </div>
        </div>

        {/* Status tabs */}
        <div className="flex gap-1 mb-6 border-b border-gray-200">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveStatus(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeStatus === tab
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        {isLoading && (
          <p className="text-center py-12 text-gray-400 text-sm">Loading approvals…</p>
        )}

        {error && (
          <p className="text-center py-12 text-red-500 text-sm">
            Failed to load approvals. Is the API running?
          </p>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">
            No {activeStatus.toLowerCase()} approvals
            {roleFilter !== "ALL" ? ` for ${roleFilter}` : ""}.
          </div>
        )}

        {!isLoading && !error && filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {filtered.map((approval) => (
              <ApprovalCard
                key={approval.id}
                approval={approval}
                shipmentRef={
                  approval.shipment_id ? shipmentMap[approval.shipment_id] : undefined
                }
                onResolved={handleResolved}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
