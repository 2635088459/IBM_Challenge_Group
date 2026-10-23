// lib/socket.ts — Socket.IO client singleton
// Connects to the backend WebSocket and exposes typed subscription helpers.

import { io, Socket } from "socket.io-client";

const WS_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AgentStateUpdate {
  shipment_id: string;
  from_state: string;
  to_state: string;
  event: string;
  reason: string;
  timestamp: string;
}

let socket: Socket | null = null;

/** Return the singleton Socket.IO client, creating it on first call. */
export function getSocket(): Socket {
  if (!socket) {
    socket = io(WS_URL, {
      path: "/ws/socket.io",
      transports: ["websocket"],
      autoConnect: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 2000,
    });
    socket.on("connect", () =>
      console.log("[Socket.IO] connected:", socket?.id)
    );
    socket.on("disconnect", (reason) =>
      console.warn("[Socket.IO] disconnected:", reason)
    );
    socket.on("connect_error", (err) =>
      console.error("[Socket.IO] connect_error:", err.message)
    );
  }
  return socket;
}

/** Subscribe to agent_state_update events for a specific shipment. */
export function subscribeAgentState(
  shipmentId: string,
  handler: (update: AgentStateUpdate) => void
): () => void {
  const s = getSocket();
  const wrapped = (update: AgentStateUpdate) => {
    if (update.shipment_id === shipmentId) handler(update);
  };
  s.on("agent_state_update", wrapped);
  // return unsubscribe function
  return () => s.off("agent_state_update", wrapped);
}
