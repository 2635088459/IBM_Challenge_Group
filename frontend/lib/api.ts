// lib/api.ts — Typed wrappers for all M2 REST API calls

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  }> | null;
  transitions: AgentTransition[];
}

export const runAgent = (
  shipment_id: string,
  simulate_discrepancy = false
): Promise<AgentRunResult> =>
  apiFetch<AgentRunResult>("/api/agent/run", {
    method: "POST",
    body: JSON.stringify({ shipment_id, event_type: "START", simulate_discrepancy }),
  });

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
