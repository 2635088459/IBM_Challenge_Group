// app/shipments/[id]/ShipmentDetailClient.tsx — Client component for shipment detail

"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, Shipment, Approval, AgentRunResult, runAgent } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import EvidenceTrail from "@/components/EvidenceTrail";
import AgentStateTimeline from "@/components/AgentStateTimeline";
import ApprovalCard from "@/components/ApprovalCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Map FSM state names → friendly labels
const STATE_LABELS: Record<string, string> = {
  INITIALIZE: "Initialize",
  OBSERVE: "Observe",
  REASON: "Reason (LLM)",
  PLAN: "Plan (LLM)",
  POLICY_CHECK: "Policy Check",
  ACT: "Act",
  ESCALATE: "Escalate",
  WAIT_EVENT: "Wait for Human",
  COLLECT_DATA: "Collect Data",
  VERIFY: "Verify",
  CLEARANCE_VERIFIED: "Cleared ✓",
  CUSTOMS_HOLD: "CBP Hold",
  TERMINAL_DENIED: "Denied",
};

function StateStep({ from, to, event, reason }: {
  from: string; to: string; event: string; reason: string;
}) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-gray-100 last:border-0">
      <div className="flex flex-col items-center shrink-0 mt-0.5">
        <div className="w-2 h-2 rounded-full bg-blue-500 mt-1" />
        <div className="w-px flex-1 bg-gray-200 min-h-[12px]" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-gray-800">
          <span className="text-gray-400">{STATE_LABELS[from] ?? from}</span>
          <span className="mx-1 text-gray-300">→</span>
          <span className="text-blue-700">{STATE_LABELS[to] ?? to}</span>
        </p>
        <p className="text-xs text-gray-400 mt-0.5 truncate" title={reason}>{event}</p>
      </div>
    </div>
  );
}

export default function ShipmentDetailClient() {
  const { id } = useParams<{ id: string }>();

  const { data: shipment, error, isLoading, mutate: mutateShipment } = useSWR<Shipment>(
    id ? `${API_URL}/api/shipments/${id}` : null,
    fetcher,
    { refreshInterval: 5000 }
  );

  const { data: approvals, mutate: mutateApprovals } = useSWR<Approval[]>(
    id ? `${API_URL}/api/approvals?shipment_id=${id}` : null,
    fetcher,
    { refreshInterval: 3000 }
  );

  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());

  // Agent run state
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState<AgentRunResult | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [simulateDiscrepancy, setSimulateDiscrepancy] = useState(false);

  function handleResolved(updated: Approval) {
    setResolvedIds((prev) => new Set([...prev, updated.id]));
    mutateApprovals();
  }

  async function handleRunAgent() {
    if (!id) return;
    setAgentRunning(true);
    setAgentError(null);
    setAgentResult(null);
    try {
      const result = await runAgent(id, simulateDiscrepancy);
      setAgentResult(result);
      // Refresh shipment + approvals after agent run
      mutateShipment();
      mutateApprovals();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Agent run failed");
    } finally {
      setAgentRunning(false);
    }
  }

  const pendingApprovals = (approvals ?? []).filter(
    (a) => a.status === "PENDING" && !resolvedIds.has(a.id)
  );

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading shipment…</p>
      </main>
    );
  }

  if (error || !shipment) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 text-sm mb-2">Shipment not found or API unavailable.</p>
          <Link href="/" className="text-blue-600 text-sm hover:underline">← Back to list</Link>
        </div>
      </main>
    );
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
          <Link href="/approvals" className="text-gray-600 hover:text-blue-600">Approvals</Link>
        </nav>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Breadcrumb */}
        <div className="text-sm text-gray-500">
          <Link href="/" className="hover:underline">Shipments</Link>
          <span className="mx-1">›</span>
          <span className="text-gray-800 font-medium">{shipment.reference_number}</span>
        </div>

        {/* Header card */}
        <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 font-mono">
                {shipment.reference_number}
              </h2>
              <p className="text-xs text-gray-400 mt-1">ID: {shipment.id}</p>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-gray-500">Current state:</span>
              <StatusBadge status={shipment.status} />
            </div>
          </div>

          {/* ── Run Agent controls ── */}
          <div className="mt-5 pt-5 border-t border-gray-100 flex flex-wrap items-center gap-4">
            <button
              onClick={handleRunAgent}
              disabled={agentRunning}
              className={`px-4 py-2 rounded-md text-sm font-medium text-white transition-colors
                ${agentRunning
                  ? "bg-blue-300 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 active:bg-blue-800"
                }`}
            >
              {agentRunning ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Agent thinking…
                </span>
              ) : "▶ Run Agent"}
            </button>

            {/* Simulate discrepancy toggle — for C02 demo */}
            <label className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={simulateDiscrepancy}
                onChange={(e) => setSimulateDiscrepancy(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Simulate qty mismatch (C02 demo)
            </label>

            {agentResult && (
              <span className="text-xs text-gray-400">
                Final state:{" "}
                <span className="font-semibold text-gray-700">
                  {STATE_LABELS[agentResult.final_state] ?? agentResult.final_state}
                </span>
              </span>
            )}
          </div>

          {agentError && (
            <p className="mt-3 text-xs text-red-500 bg-red-50 rounded px-3 py-2">{agentError}</p>
          )}
        </div>

        {/* ── LLM Analysis + FSM trace (shown after a run) ── */}
        {agentResult && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* LLM Analysis */}
            {agentResult.llm_analysis && (
              <section className="bg-white rounded-lg border border-blue-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-blue-800 mb-3 uppercase tracking-wide">
                  🤖 GPT Analysis
                </h3>
                <ul className="space-y-2">
                  {agentResult.llm_analysis.split("\n").filter(Boolean).map((line, i) => (
                    <li key={i} className="text-xs text-gray-700 leading-relaxed">
                      {line}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Proposed Actions */}
            {agentResult.proposed_actions && agentResult.proposed_actions.length > 0 && (
              <section className="bg-white rounded-lg border border-purple-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-purple-800 mb-3 uppercase tracking-wide">
                  📋 Proposed Actions
                </h3>
                <div className="space-y-2">
                  {agentResult.proposed_actions.map((action, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-[10px]">
                        {i + 1}
                      </span>
                      <div>
                        <p className="font-medium text-gray-800">{action.action_type}</p>
                        <p className="text-gray-500">{action.description}</p>
                        {action.role_required && (
                          <span className="inline-block mt-0.5 px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-mono">
                            {action.role_required}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* FSM Transitions */}
            {agentResult.transitions.length > 0 && (
              <section className="lg:col-span-2 bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">
                  FSM State Transitions
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
                  {agentResult.transitions.map((t, i) => (
                    <StateStep
                      key={i}
                      from={t.from_state}
                      to={t.to_state}
                      event={t.event}
                      reason={t.reason}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main column: Evidence Trail + Documents */}
          <div className="lg:col-span-2 space-y-6">
            {/* Evidence trail */}
            <section className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">
                Evidence Trail
              </h3>
              <EvidenceTrail documents={shipment.documents} />
            </section>

            {/* Document list */}
            <section className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide">
                Documents ({shipment.documents.length})
              </h3>
              {shipment.documents.length === 0 ? (
                <p className="text-xs text-gray-400 italic">No documents uploaded.</p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {shipment.documents.map((doc) => (
                    <div key={doc.id} className="py-2.5 flex items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-gray-800">
                          {doc.doc_type.replace(/_/g, " ")}
                        </p>
                        <p className="text-xs font-mono text-gray-400 truncate max-w-xs">
                          {doc.file_hash ?? "no hash"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-gray-400">v{doc.version}</span>
                        <StatusBadge status={doc.status} size="sm" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Sidebar: Agent state + Approvals */}
          <div className="space-y-6">
            {/* Live agent state timeline */}
            <section className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">
                Agent State
                <span className="ml-2 inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              </h3>
              <AgentStateTimeline shipmentId={shipment.id} />
            </section>

            {/* Pending approvals */}
            {pendingApprovals.length > 0 && (
              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                  Pending Approvals ({pendingApprovals.length})
                </h3>
                {pendingApprovals.map((a) => (
                  <ApprovalCard
                    key={a.id}
                    approval={a}
                    shipmentRef={shipment.reference_number}
                    onResolved={handleResolved}
                  />
                ))}
              </section>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
