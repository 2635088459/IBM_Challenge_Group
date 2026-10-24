// lib/socket.ts — Socket.IO client (gracefully disabled when server is unavailable)
//
// The backend API is plain FastAPI — Socket.IO is not mounted in the Docker demo.
// This module provides the same subscription interface but silently no-ops so the
// console stays clean.  When a real Socket.IO server is added, remove the guard.

export interface AgentStateUpdate {
  shipment_id: string;
  from_state: string;
  to_state: string;
  event: string;
  reason: string;
  timestamp: string;
}

// Feature-flag: set NEXT_PUBLIC_ENABLE_SOCKETIO=true to attempt a real connection.
const ENABLED = process.env.NEXT_PUBLIC_ENABLE_SOCKETIO === "true";

type Handler = (update: AgentStateUpdate) => void;
const _listeners = new Map<string, Set<Handler>>();

/** Subscribe to agent_state_update events for a specific shipment.
 *  Returns an unsubscribe function (called on component unmount). */
export function subscribeAgentState(
  shipmentId: string,
  handler: Handler
): () => void {
  if (!ENABLED) {
    // No-op: Socket.IO server not running in this deployment.
    return () => {};
  }

  // Lazy-load socket.io-client only when the feature is enabled.
  import("socket.io-client").then(({ io }) => {
    const WS_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const socket = io(WS_URL, {
      path: "/ws/socket.io",
      transports: ["websocket"],
      reconnectionAttempts: 3,
      reconnectionDelay: 3000,
    });
    socket.on("agent_state_update", (update: AgentStateUpdate) => {
      if (update.shipment_id === shipmentId) handler(update);
    });
    if (!_listeners.has(shipmentId)) _listeners.set(shipmentId, new Set());
    _listeners.get(shipmentId)!.add(handler);
  });

  return () => {
    _listeners.get(shipmentId)?.delete(handler);
  };
}
