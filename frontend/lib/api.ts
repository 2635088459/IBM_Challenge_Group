// lib/api.ts — Typed wrappers for all M2 REST API calls

// Same-origin by default: next.config.ts proxies /api/* to the backend
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DocumentRecord {
  id: string;
  doc_type: string;
  file_hash: string | null;
  version: number;
  status: "raw" | "extracted" | "verified";
  uploaded_at: string;
}

export interface Shipment {
  id: string;
  reference_number: string;
  status: string;
  created_at: string;
  documents: DocumentRecord[];
}

export interface ShipmentListItem {
  id: string;
  reference_number: string;
  status: string;
  created_at: string;
}

export interface Approval {
  id: string;
  action_id: string | null;
  shipment_id: string | null;
  role: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  payload_hash: string | null;
  requested_at: string;
  resolved_at: string | null;
}

export interface AuditLogEntry {
  id: string;
  shipment_id: string;
  actor: string;
  event: string;
  details: Record<string, unknown> | null;
  timestamp: string;
}

/**
 * The API stores UTC but sends timestamps without a zone ("2026-10-24T01:02:03").
 * `new Date()` would read those as the viewer's local time — e.g. "-420m ago" in
 * California — so treat any zone-less timestamp as UTC.
 */
export function parseApiDate(iso: string): Date {
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Shipments ─────────────────────────────────────────────────────────────────

export const getShipments = (): Promise<ShipmentListItem[]> =>
  apiFetch<ShipmentListItem[]>("/api/shipments");

export const getShipment = (id: string): Promise<Shipment> =>
  apiFetch<Shipment>(`/api/shipments/${id}`);

// ── Approvals ─────────────────────────────────────────────────────────────────

export const getApprovals = (params?: {
  shipment_id?: string;
  status?: string;
}): Promise<Approval[]> => {
  const qs = new URLSearchParams();
  if (params?.shipment_id) qs.set("shipment_id", params.shipment_id);
  if (params?.status) qs.set("status", params.status);
  const query = qs.toString() ? `?${qs}` : "";
  return apiFetch<Approval[]>(`/api/approvals${query}`);
};

export const updateApproval = (
  id: string,
  status: "APPROVED" | "REJECTED"
): Promise<Approval> =>
  apiFetch<Approval>(`/api/approvals/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

// ── Agent run ─────────────────────────────────────────────────────────────────

export interface AgentTransition {
  from_state: string;
  to_state: string;
  event: string;
  reason: string;
  timestamp: string;
}

export interface AgentRunResult {
  shipment_id: string;
  final_state: string;
  llm_analysis: string | null;
  proposed_actions: Array<{
    action_type: string;
    description: string;
    role_required: string | null;
    /** Added by the red-team scenario to model an LLM that obeyed the attacker */
    injected?: boolean;
  }> | null;
  transitions: AgentTransition[];
  policy_denials: Array<{ action_type: string; reason: string }>;
  attack_text: string | null;
  /** Which LLM produced the analysis/plan, and whether it fell back to offline mock output */
  llm_source: { provider: string; model: string | null; fallback: boolean; errors?: string[] } | null;
}

export const runAgent = (
  shipment_id: string,
  simulate_discrepancy = false,
  red_team = false
): Promise<AgentRunResult> =>
  apiFetch<AgentRunResult>("/api/agent/run", {
    method: "POST",
    body: JSON.stringify({ shipment_id, event_type: "START", simulate_discrepancy, red_team }),
  });

/** crypto.randomUUID only exists on HTTPS/localhost pages — fall back for plain-HTTP access */
function uniqueId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// ── Demo reset ────────────────────────────────────────────────────────────────

/** Restore one demo shipment (or all three) to its starting state; ids are kept */
export const resetDemo = (shipment_id?: string): Promise<{ reset: Record<string, string> }> =>
  apiFetch(shipment_id ? `/api/demo/reset/${shipment_id}` : "/api/demo/reset", { method: "POST" });

// ── Mock CBP channel (C09 demo) ───────────────────────────────────────────────

/** Emit a CBP event as the CBP feed would; verified=false simulates a forged message. */
export const emitCbpEvent = (
  shipment_id: string,
  event_type: "CBP_HOLD_RECEIVED" | "CBP_RELEASE_RECEIVED",
  source_verified: boolean
) =>
  apiFetch("/api/events", {
    method: "POST",
    body: JSON.stringify({
      event_id: `ui-${event_type.toLowerCase()}-${uniqueId()}`,
      event_type,
      shipment_id,
      source_verified,
      payload: { channel: source_verified ? "CBP (mock feed)" : "unverified sender" },
    }),
  });

// ── Audit hash chain ──────────────────────────────────────────────────────────

export interface AuditChainResult {
  valid: boolean;
  entries: number;
  legacy_unchained: number;
  head_hash: string | null;
  broken: { reason: string; position: number; id: string; event: string; timestamp: string } | null;
  chain: Array<{ id: string; event: string; timestamp: string; status: "ok" | "modified" | "after_break" | "unlinked" }>;
}

export const verifyAuditChain = (shipment_id: string): Promise<AuditChainResult> =>
  apiFetch<AuditChainResult>(`/api/audit-logs/${shipment_id}/verify`);

/** Demo only — rewrites a stored audit entry behind the application's back */
export const tamperAuditDemo = (
  shipment_id: string
): Promise<{ id: string; event: string; before: Record<string, unknown>; after: Record<string, unknown> }> =>
  apiFetch(`/api/demo/tamper-audit/${shipment_id}`, { method: "POST" });

// ── Audit logs ────────────────────────────────────────────────────────────────

export const getAuditLogs = (shipment_id: string): Promise<AuditLogEntry[]> =>
  apiFetch<AuditLogEntry[]>(`/api/audit-logs/${shipment_id}`);

// ── SWR fetcher ───────────────────────────────────────────────────────────────

/** Generic SWR fetcher — pass a full URL string. */
export const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });
