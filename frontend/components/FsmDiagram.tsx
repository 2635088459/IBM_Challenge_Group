// components/FsmDiagram.tsx — Live state-machine diagram: current state lit up, path taken highlighted

"use client";

import { AgentStateUpdate } from "@/lib/socket";

// Node layout — main happy path on top, waiting / exception states below
const NODES: Record<string, { x: number; y: number; label: string }> = {
  INITIALIZE:         { x: 70,  y: 60,  label: "Initialize" },
  OBSERVE:            { x: 200, y: 60,  label: "Observe" },
  REASON:             { x: 330, y: 60,  label: "Reason (LLM)" },
  PLAN:               { x: 460, y: 60,  label: "Plan (LLM)" },
  POLICY_CHECK:       { x: 590, y: 60,  label: "Policy Check" },
  ACT:                { x: 720, y: 60,  label: "Act" },
  VERIFY:             { x: 850, y: 60,  label: "Verify" },
  CLEARANCE_VERIFIED: { x: 980, y: 60,  label: "Cleared ✓" },
  COLLECT_DATA:       { x: 120, y: 200, label: "Collect Data" },
  CUSTOMS_HOLD:       { x: 270, y: 200, label: "CBP Hold" },
  RECOVER:            { x: 460, y: 200, label: "Recover" },
  ESCALATE:           { x: 620, y: 200, label: "Escalate" },
  WAIT_EVENT:         { x: 790, y: 200, label: "Wait for Human" },
};

// Mirrors AgentFSM.TRANSITIONS in backend/agent/fsm.py
const EDGES: [string, string][] = [
  ["INITIALIZE", "OBSERVE"],
  ["OBSERVE", "REASON"], ["OBSERVE", "COLLECT_DATA"], ["OBSERVE", "CUSTOMS_HOLD"],
  ["REASON", "PLAN"], ["REASON", "RECOVER"],
  ["PLAN", "POLICY_CHECK"], ["PLAN", "RECOVER"],
  ["POLICY_CHECK", "ACT"], ["POLICY_CHECK", "ESCALATE"], ["POLICY_CHECK", "RECOVER"],
  ["ACT", "VERIFY"], ["ACT", "RECOVER"],
  ["VERIFY", "CLEARANCE_VERIFIED"], ["VERIFY", "RECOVER"], ["VERIFY", "OBSERVE"],
  ["WAIT_EVENT", "OBSERVE"], ["WAIT_EVENT", "VERIFY"], ["WAIT_EVENT", "RECOVER"],
  ["COLLECT_DATA", "OBSERVE"], ["COLLECT_DATA", "ESCALATE"], ["COLLECT_DATA", "WAIT_EVENT"],
  ["ESCALATE", "WAIT_EVENT"], ["ESCALATE", "RECOVER"],
  ["CUSTOMS_HOLD", "WAIT_EVENT"], ["CUSTOMS_HOLD", "RECOVER"],
  ["RECOVER", "OBSERVE"], ["RECOVER", "ESCALATE"],
];

// Long edges that would run through other nodes get a stronger bend
const BEND: Record<string, number> = {
  "VERIFY>OBSERVE": 75,
  "WAIT_EVENT>OBSERVE": 70,
  "COLLECT_DATA>WAIT_EVENT": -70,
  "RECOVER>OBSERVE": 30,
  "CUSTOMS_HOLD>RECOVER": -18,
  "CUSTOMS_HOLD>WAIT_EVENT": 55,
};

const HALF_W = 54;
const HALF_H = 17;

// What the agent is waiting on when it stops in a state
const STOP_HINT: Record<string, string> = {
  WAIT_EVENT: "Waiting for a human approval or an official CBP event — the agent will not act until then.",
  CUSTOMS_HOLD: "Under CBP hold — only an official CBP release can lift it.",
  COLLECT_DATA: "Waiting for the missing documents to be uploaded.",
  RECOVER: "Plan blocked by guardrails or rejected — nothing was executed; a human must review.",
  CLEARANCE_VERIFIED: "Done — clearance verified.",
};

const CURRENT_STYLE: Record<string, { fill: string; text: string; ring: string }> = {
  CLEARANCE_VERIFIED: { fill: "#16a34a", text: "#ffffff", ring: "#86efac" },
  WAIT_EVENT:         { fill: "#d97706", text: "#ffffff", ring: "#fcd34d" },
  ESCALATE:           { fill: "#d97706", text: "#ffffff", ring: "#fcd34d" },
  COLLECT_DATA:       { fill: "#d97706", text: "#ffffff", ring: "#fcd34d" },
  CUSTOMS_HOLD:       { fill: "#dc2626", text: "#ffffff", ring: "#fca5a5" },
  RECOVER:            { fill: "#dc2626", text: "#ffffff", ring: "#fca5a5" },
};
const DEFAULT_CURRENT = { fill: "#2563eb", text: "#ffffff", ring: "#93c5fd" };

/** Point where the ray from the node centre towards (tx, ty) leaves the node box */
function boxExit(cx: number, cy: number, tx: number, ty: number) {
  const dx = tx - cx;
  const dy = ty - cy;
  const scale = Math.min(HALF_W / Math.abs(dx || 1e-6), HALF_H / Math.abs(dy || 1e-6));
  return { x: cx + dx * scale, y: cy + dy * scale };
}

function edgePath(from: string, to: string) {
  const a = NODES[from];
  const b = NODES[to];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  // Slight default bend keeps A→B and B→A edges apart
  const k = BEND[`${from}>${to}`] ?? 10;
  const cx = (a.x + b.x) / 2 + (-dy / len) * k;
  const cy = (a.y + b.y) / 2 + (dx / len) * k;
  const s = boxExit(a.x, a.y, cx, cy);
  const e = boxExit(b.x, b.y, cx, cy);
  return `M ${s.x} ${s.y} Q ${cx} ${cy} ${e.x} ${e.y}`;
}

interface Props {
  /** Persisted transitions, oldest first */
  history: AgentStateUpdate[];
  running?: boolean;
}

export default function FsmDiagram({ history, running = false }: Props) {
  // The latest episode: everything since the agent was last started (resumes included)
  const startIdx = history.map((t) => t.from_state).lastIndexOf("INITIALIZE");
  const episode = startIdx >= 0 ? history.slice(startIdx) : history;
  const last = episode.at(-1);
  const current = last?.to_state;

  const takenEdges = new Set(episode.map((t) => `${t.from_state}>${t.to_state}`));
  const visited = new Set(episode.flatMap((t) => [t.from_state, t.to_state]));
  const currentStyle = (current ? CURRENT_STYLE[current] : undefined) ?? DEFAULT_CURRENT;

  return (
    <div>
      <div className="overflow-x-auto -mx-2 px-2">
        <svg
          viewBox="0 12 1050 240"
          className="w-full min-w-[720px]"
          role="img"
          aria-label={current ? `Agent state machine — currently ${NODES[current]?.label ?? current}` : "Agent state machine"}
        >
          <defs>
            <marker id="fsm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#cbd5e1" />
            </marker>
            <marker id="fsm-arrow-taken" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb" />
            </marker>
          </defs>

          {/* Untaken edges first, so taken ones draw on top */}
          {[false, true].map((drawTaken) =>
            EDGES.filter(([f, t]) => takenEdges.has(`${f}>${t}`) === drawTaken).map(([f, t]) => (
              <path
                key={`${f}>${t}`}
                d={edgePath(f, t)}
                fill="none"
                stroke={drawTaken ? "#2563eb" : "#e2e8f0"}
                strokeWidth={drawTaken ? 2.5 : 1.2}
                markerEnd={`url(#${drawTaken ? "fsm-arrow-taken" : "fsm-arrow"})`}
              />
            ))
          )}

          {Object.entries(NODES).map(([state, n]) => {
            const isCurrent = state === current;
            const isVisited = visited.has(state);
            const fill = isCurrent ? currentStyle.fill : isVisited ? "#eff6ff" : "#ffffff";
            const stroke = isCurrent ? currentStyle.fill : isVisited ? "#2563eb" : "#cbd5e1";
            const textColor = isCurrent ? currentStyle.text : isVisited ? "#1e3a8a" : "#94a3b8";
            return (
              <g key={state}>
                {isCurrent && (
                  <rect
                    x={n.x - HALF_W - 5} y={n.y - HALF_H - 5}
                    width={HALF_W * 2 + 10} height={HALF_H * 2 + 10}
                    rx={12} fill="none" stroke={currentStyle.ring} strokeWidth={3}
                  >
                    <animate attributeName="opacity" values="1;0.25;1" dur={running ? "0.8s" : "1.8s"} repeatCount="indefinite" />
                  </rect>
                )}
                <rect
                  x={n.x - HALF_W} y={n.y - HALF_H}
                  width={HALF_W * 2} height={HALF_H * 2}
                  rx={9} fill={fill} stroke={stroke} strokeWidth={isCurrent || isVisited ? 1.8 : 1}
                />
                <text
                  x={n.x} y={n.y + 4} textAnchor="middle"
                  fontSize={12} fontWeight={isCurrent ? 700 : 500} fill={textColor}
                >
                  {n.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Why the agent is where it is */}
      {last ? (
        <div className="mt-3 rounded-md bg-gray-50 border border-gray-100 px-4 py-3 text-xs space-y-1">
          <p className="text-gray-800">
            <span className="text-gray-500">Stopped at </span>
            <span className="font-semibold">{NODES[last.to_state]?.label ?? last.to_state}</span>
            <span className="text-gray-500"> — {last.reason}</span>
          </p>
          {STOP_HINT[last.to_state] && <p className="text-gray-500">{STOP_HINT[last.to_state]}</p>}
        </div>
      ) : (
        <p className="mt-3 text-xs text-gray-400 italic">
          Run the agent to see its path through the state machine.
        </p>
      )}
    </div>
  );
}
