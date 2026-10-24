// app/shipments/[id]/ShipmentDetailClient.tsx — Client component for shipment detail

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, Shipment, Approval, AgentRunResult, AuditLogEntry, runAgent, emitCbpEvent, resetDemo } from "@/lib/api";
import { AgentStateUpdate } from "@/lib/socket";
import StatusBadge from "@/components/StatusBadge";
import EvidenceTrail from "@/components/EvidenceTrail";
import AgentStateTimeline from "@/components/AgentStateTimeline";
import FsmDiagram from "@/components/FsmDiagram";
import AuditChainPanel from "@/components/AuditChainPanel";
import SiteHeader from "@/components/SiteHeader";
import HelpTip from "@/components/HelpTip";
import GuidedTour from "@/components/GuidedTour";
import { ScenarioSteps } from "@/components/ScenarioGuide";

const TOUR_SEEN_KEY = "customs-demo-tour-seen";
import ApprovalCard from "@/components/ApprovalCard";

// Same-origin by default: next.config.ts proxies /api/* to the backend
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

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

/** Render **bold** spans the LLM may still emit, instead of showing raw asterisks */
function renderBold(line: string) {
  return line.split("**").map((part, i) =>
    i % 2 === 1 ? <strong key={i} className="font-semibold text-gray-900">{part}</strong> : part
  );
}

function LlmSourceBadge({ source }: { source: AgentRunResult["llm_source"] }) {
  if (!source) return null;
  if (source.provider === "mock") {
    return (
      <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-[10px] font-semibold normal-case">
        Demo mode — no API key
      </span>
    );
  }
  if (source.fallback) {
    return (
      <span
        className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-semibold normal-case"
        title={(source.errors ?? []).join("\n")}
      >
        Offline fallback — {source.provider} call failed
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-[10px] font-semibold normal-case">
      Live AI · {source.model ?? source.provider}
    </span>
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

  // Persisted agent history — survives refresh and shows the resume after an approval
  const { data: auditLogs, mutate: mutateAuditLogs } = useSWR<AuditLogEntry[]>(
    id ? `${API_URL}/api/audit-logs/${id}` : null,
    fetcher,
    { refreshInterval: 3000 }
  );
  const agentHistory: AgentStateUpdate[] = (auditLogs ?? [])
    .filter((e) => e.event === "AGENT_TRANSITION")
    .map((e) => ({ shipment_id: e.shipment_id, ...(e.details as Omit<AgentStateUpdate, "shipment_id">) }));
  const agentState = agentHistory.at(-1)?.to_state;

  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());

  // Agent run state
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState<AgentRunResult | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [simulateDiscrepancy, setSimulateDiscrepancy] = useState(false);
  const [redTeam, setRedTeam] = useState(false);
  const [cbpNotice, setCbpNotice] = useState<string | null>(null);
  const [tourOpen, setTourOpen] = useState(false);
  const [showTourPrompt, setShowTourPrompt] = useState(false);

  // Offer the tour on a first visit (per browser); storage may be unavailable
  useEffect(() => {
    try {
      setShowTourPrompt(!localStorage.getItem(TOUR_SEEN_KEY));
    } catch {
      setShowTourPrompt(true);
    }
  }, []);

  function startTour() {
    setTourOpen(true);
    dismissTourPrompt();
  }

  function dismissTourPrompt() {
    setShowTourPrompt(false);
    try {
      localStorage.setItem(TOUR_SEEN_KEY, "1");
    } catch {
      /* first-visit prompt will just show again */
    }
  }

  function handleResolved(updated: Approval) {
    setResolvedIds((prev) => new Set([...prev, updated.id]));
    // The last approval for a plan resumes the agent server-side
    mutateApprovals();
    mutateShipment();
    mutateAuditLogs();
  }

  async function handleRunAgent() {
    if (!id) return;
    setAgentRunning(true);
    setAgentError(null);
    setAgentResult(null);
    try {
      const result = await runAgent(id, simulateDiscrepancy, redTeam);
      setAgentResult(result);
      // Refresh shipment + approvals + agent history after agent run
      mutateShipment();
      mutateApprovals();
      mutateAuditLogs();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Agent run failed");
    } finally {
      setAgentRunning(false);
    }
  }

  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    if (!id || !shipment) return;
    if (!window.confirm(`Reset ${shipment.reference_number} to its starting state? Anyone else viewing it will see the reset too.`)) return;
    setResetting(true);
    try {
      await resetDemo(id);
      setAgentResult(null);
      setAgentError(null);
      setCbpNotice(null);
      setResolvedIds(new Set());
      await Promise.all([mutateShipment(), mutateApprovals(), mutateAuditLogs()]);
    } catch (err) {
      setAgentError(err instanceof Error ? `Reset failed: ${err.message}` : "Reset failed");
    } finally {
      setResetting(false);
    }
  }

  async function handleCbpRelease(verified: boolean) {
    if (!id) return;
    setCbpNotice(null);
    try {
      await emitCbpEvent(id, "CBP_RELEASE_RECEIVED", verified);
      const [updated] = await Promise.all([mutateShipment(), mutateAuditLogs(), mutateApprovals()]);
      if (updated?.status === "CUSTOMS_HOLD") {
        setCbpNotice(
          verified
            ? "Release recorded — the hold stays until the agent's open work is resolved."
            : "Rejected by guard G-cbp: the release did not come from a verified CBP channel. Hold stays in place."
        );
      } else {
        setCbpNotice(`Official CBP release accepted — shipment is now ${updated?.status ?? "updated"}.`);
      }
    } catch (err) {
      setCbpNotice(err instanceof Error ? err.message : "CBP event failed");
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
      <SiteHeader active="shipments" />
      <GuidedTour open={tourOpen} onClose={() => setTourOpen(false)} />

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Breadcrumb */}
        <div className="text-sm text-gray-500">
          <Link href="/" className="hover:underline">Shipments</Link>
          <span className="mx-1">›</span>
          <span className="text-gray-800 font-medium">{shipment.reference_number}</span>
        </div>

        {/* First-visit tour prompt */}
        {showTourPrompt && (
          <div className="flex items-center justify-between gap-3 flex-wrap rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm">
            <p className="text-blue-900">
              <span className="font-semibold">First time here?</span> A 1-minute tour explains every part of this page.
            </p>
            <div className="flex gap-2">
              <button onClick={startTour} className="px-3 py-1.5 rounded-md bg-blue-600 text-white text-xs font-medium hover:bg-blue-700">
                Take the tour
              </button>
              <button onClick={dismissTourPrompt} className="px-3 py-1.5 rounded-md text-xs text-blue-700 hover:bg-blue-100">
                No thanks
              </button>
            </div>
          </div>
        )}

        {/* Header card */}
        <div data-tour="header" className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
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
              <button
                onClick={startTour}
                className="px-2.5 py-1 rounded-md border border-gray-300 text-xs text-gray-600 hover:border-blue-400 hover:text-blue-700"
              >
                ? Take the tour
              </button>
              <button
                onClick={handleReset}
                disabled={resetting || agentRunning}
                title="Restore this shipment to its starting state so the demo can be run again"
                className="px-2.5 py-1 rounded-md border border-gray-300 text-xs text-gray-600 hover:border-amber-400 hover:text-amber-700 disabled:opacity-50"
              >
                {resetting ? "Resetting…" : "↺ Reset this demo"}
              </button>
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

            {/* Red-team toggle — prompt injection hidden in supplier invoice text */}
            <label className="flex items-center gap-2 text-xs text-red-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={redTeam}
                onChange={(e) => setRedTeam(e.target.checked)}
                className="rounded border-red-300 text-red-600 focus:ring-red-500"
              />
              Red-team: prompt-injection attack
            </label>
            <HelpTip topic="runControls" />

            {agentState && (
              <span className="text-xs text-gray-400">
                Agent state:{" "}
                <span className="font-semibold text-gray-700">
                  {STATE_LABELS[agentState] ?? agentState}
                </span>
              </span>
            )}
          </div>

          {/* Mock CBP channel — only an official, verified release can lift a hold */}
          {shipment.status === "CUSTOMS_HOLD" && (
            <div data-tour="cbp-feed" className="mt-4 flex flex-wrap items-center gap-3 text-xs">
              <span className="text-gray-500 flex items-center gap-1.5">Mock CBP feed <HelpTip topic="cbpFeed" /></span>
              <button
                onClick={() => handleCbpRelease(true)}
                className="px-3 py-1.5 rounded-md border border-green-300 text-green-700 hover:bg-green-50"
              >
                Send official CBP release
              </button>
              <button
                onClick={() => handleCbpRelease(false)}
                className="px-3 py-1.5 rounded-md border border-red-300 text-red-700 hover:bg-red-50"
              >
                Send forged release (unverified)
              </button>
            </div>
          )}
          {cbpNotice && (
            <p className="mt-3 text-xs text-gray-700 bg-gray-50 rounded px-3 py-2">{cbpNotice}</p>
          )}

          <ScenarioSteps reference={shipment.reference_number} />

          {agentError && (
            <p className="mt-3 text-xs text-red-500 bg-red-50 rounded px-3 py-2">{agentError}</p>
          )}
        </div>

        {/* ── Live state machine ── */}
        <section data-tour="fsm" className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide flex items-center gap-2">
            Agent State Machine <HelpTip topic="stateMachine" />
          </h3>
          <FsmDiagram history={agentHistory} running={agentRunning} />
        </section>

        {/* ── LLM Analysis + FSM trace (shown after a run) ── */}
        {agentResult && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Red-team: the attack, and what the guardrails did with it */}
            {agentResult.attack_text && (
              <section data-tour="attack" className="bg-white rounded-lg border border-red-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-red-700 mb-1 uppercase tracking-wide flex items-center gap-2">
                  Attack payload <HelpTip topic="attack" />
                </h3>
                <p className="text-xs text-gray-500 mb-3">
                  Hidden in the supplier&apos;s invoice remarks and sent to the AI as part of the shipment.
                </p>
                <p className="text-xs font-mono text-red-800 bg-red-50 rounded p-3 leading-relaxed">
                  {agentResult.attack_text}
                </p>
              </section>
            )}
            {agentResult.policy_denials.length > 0 && (
              <section data-tour="guardrails" className="bg-white rounded-lg border border-green-300 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-green-800 mb-1 uppercase tracking-wide flex items-center gap-2">
                  Blocked by guardrails <HelpTip topic="guardrails" />
                </h3>
                <p className="text-xs text-gray-500 mb-3">
                  Deterministic policy checks rejected the plan — nothing was executed and the
                  CBP hold was not released.
                </p>
                <ul className="space-y-2">
                  {agentResult.policy_denials.map((d, i) => (
                    <li key={i} className="text-xs">
                      <p className="font-mono font-semibold text-gray-800">✕ {d.action_type}</p>
                      <p className="text-gray-500">{d.reason}</p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* No-LLM path: agent resolved without needing GPT (e.g. C01 missing doc) */}
            {!agentResult.llm_analysis && (
              <section className="lg:col-span-2 bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-700 mb-1 uppercase tracking-wide">
                  Agent Analysis
                </h3>
                {agentResult.transitions.some((t) => t.to_state === "CUSTOMS_HOLD") ? (
                  <p className="text-xs text-gray-500">
                    A verified CBP hold is active. The agent notified Trade Compliance (R4) and the
                    Customs Broker (R5) and is waiting for the official CBP release — it has no
                    authority to release the hold itself. No AI reasoning was required.
                  </p>
                ) : (
                  <p className="text-xs text-gray-500">
                    The agent resolved this shipment without invoking the LLM —
                    a missing or incomplete document was detected during the{" "}
                    <span className="font-mono text-gray-700">OBSERVE</span> state
                    and the shipment was moved to{" "}
                    <span className="font-mono text-gray-700">
                      {agentResult.final_state}
                    </span>{" "}
                    automatically. No AI reasoning was required.
                  </p>
                )}
              </section>
            )}

            {/* LLM Analysis — only shown when GPT ran (discrepancy / CBP hold path) */}
            {agentResult.llm_analysis && (
              <section data-tour="analysis" className="bg-white rounded-lg border border-blue-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-blue-800 mb-3 uppercase tracking-wide flex items-center gap-2 flex-wrap">
                  Agent Analysis <HelpTip topic="analysis" />
                  <LlmSourceBadge source={agentResult.llm_source} />
                </h3>
                <ul className="space-y-2">
                  {agentResult.llm_analysis.split("\n").filter(Boolean).map((line, i) => (
                    <li key={i} className="text-xs text-gray-700 leading-relaxed">
                      {renderBold(line)}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Proposed Actions */}
            {agentResult.proposed_actions && agentResult.proposed_actions.length > 0 && (
              <section data-tour="actions" className="bg-white rounded-lg border border-purple-200 p-6 shadow-sm">
                <h3 className="text-sm font-semibold text-purple-800 mb-3 uppercase tracking-wide flex items-center gap-2">
                  Proposed Actions <HelpTip topic="proposedActions" />
                </h3>
                <div className="space-y-2">
                  {agentResult.proposed_actions.map((action, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-[10px]">
                        {i + 1}
                      </span>
                      <div>
                        <p className="font-medium text-gray-800">
                          {action.action_type}
                          {action.injected && (
                            <span className="ml-2 px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[10px] font-semibold">
                              INJECTED BY ATTACK
                            </span>
                          )}
                        </p>
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
                <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide flex items-center gap-2">
                  FSM State Transitions <HelpTip topic="transitions" />
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
            <section data-tour="evidence" className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide flex items-center gap-2">
                Evidence Trail <HelpTip topic="evidence" />
              </h3>
              <EvidenceTrail documents={shipment.documents} />
            </section>

            {/* Document list */}
            <section className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase tracking-wide flex items-center gap-2">
                Documents ({shipment.documents.length}) <HelpTip topic="documents" />
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
            <section data-tour="agent-state" className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide flex items-center gap-2">
                Agent State <HelpTip topic="agentState" />
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    agentRunning ? "bg-green-400 animate-pulse" : agentState ? "bg-green-400" : "bg-gray-300"
                  }`}
                />
              </h3>
              <AgentStateTimeline
                key={agentHistory.length}
                shipmentId={shipment.id}
                initialEvents={agentHistory}
              />
            </section>

            {/* Tamper-evident audit chain */}
            <section data-tour="audit-chain" className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide flex items-center gap-2">
                Audit Chain <HelpTip topic="auditChain" />
              </h3>
              <AuditChainPanel shipmentId={shipment.id} onTampered={() => mutateAuditLogs()} />
            </section>

            {/* Pending approvals */}
            {pendingApprovals.length > 0 && (
              <section data-tour="approvals" className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide flex items-center gap-2">
                  Pending Approvals ({pendingApprovals.length}) <HelpTip topic="approvals" />
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
