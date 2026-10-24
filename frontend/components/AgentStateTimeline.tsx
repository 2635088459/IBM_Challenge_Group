// components/AgentStateTimeline.tsx — Live FSM state transition list via Socket.IO

"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeAgentState, AgentStateUpdate } from "@/lib/socket";

interface Props {
  shipmentId: string;
  /** Initial transitions from the audit log (pre-loaded server-side) */
  initialEvents?: AgentStateUpdate[];
}

const STATE_COLOR: Record<string, string> = {
  CLEARANCE_VERIFIED: "bg-green-500",
  CUSTOMS_HOLD:       "bg-red-500",
  ESCALATE:           "bg-orange-400",
  COLLECT_DATA:       "bg-orange-400",
  WAIT_EVENT:         "bg-yellow-400",
  RECOVER:            "bg-red-400",
};

function dot(state: string) {
  return STATE_COLOR[state] ?? "bg-gray-400";
}

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

export default function AgentStateTimeline({ shipmentId, initialEvents = [] }: Props) {
  const [events, setEvents] = useState<AgentStateUpdate[]>(initialEvents);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsub = subscribeAgentState(shipmentId, (update) => {
      setEvents((prev) => [...prev, update]);
    });
    return unsub;
  }, [shipmentId]);

  // Auto-scroll to bottom on new event
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  if (!events.length) {
    return (
      <p className="text-xs text-gray-400 italic py-2">
        Click <span className="font-medium text-gray-500">▶ Run Agent</span> above to start the agent.
        Its state transitions will appear here after the run.
      </p>
    );
  }

  return (
    <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
      {events.map((ev, i) => (
        <div key={i} className="flex items-start gap-3">
          {/* Dot */}
          <div className="mt-1 flex-shrink-0">
            <span className={`block w-2.5 h-2.5 rounded-full ${dot(ev.to_state)}`} />
          </div>
          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-800">
              <span className="text-gray-400">{ev.from_state}</span>
              {" → "}
              <span className="font-semibold text-gray-900">{ev.to_state}</span>
            </p>
            <p className="text-xs text-gray-500 truncate">{ev.reason}</p>
            <p className="text-xs text-gray-400">{fmtTime(ev.timestamp)}</p>
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
