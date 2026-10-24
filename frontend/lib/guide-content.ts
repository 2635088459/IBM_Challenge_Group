// lib/guide-content.ts — All explanatory copy for the tour, help tips, scenario cards and /guide page.
// Kept in one place so the in-page help and the manual never disagree.

export interface Scenario {
  ref: string;
  code: string;
  title: string;
  shows: string;
  steps: string[];
}

export const SCENARIOS: Scenario[] = [
  {
    ref: "SHP-002",
    code: "C02",
    title: "Quantity mismatch → human approval",
    shows: "The AI finds the problem and proposes a fix, but a human must approve before anything happens.",
    steps: [
      "Click ▶ Run Agent. The agent compares the invoice with the packing list and spots the difference itself.",
      "Read the Agent Analysis (invoice says 500, packing list says 480) and the Proposed Actions.",
      "The state machine stops at “Wait for Human”. Approve every card under Pending Approvals.",
      "Watch the agent resume: Policy Check → Act → Verify → Cleared ✓.",
    ],
  },
  {
    ref: "SHP-003",
    code: "Red team",
    title: "Prompt-injection attack → blocked",
    shows: "Even if the AI is fully fooled by text hidden in a supplier document, the guardrails stop every unsafe action.",
    steps: [
      "On SHP-003 — do this before the CBP release below — tick “Red-team: prompt-injection attack” and click ▶ Run Agent.",
      "Attack payload shows the instruction hidden in the invoice.",
      "Proposed Actions marks the attacker’s actions INJECTED BY ATTACK.",
      "Blocked by guardrails lists what was stopped and why. The hold is untouched.",
    ],
  },
  {
    ref: "SHP-003",
    code: "C09",
    title: "CBP hold → only CBP can release",
    shows: "The agent coordinates a customs hold but has no authority to release it — not even if someone fakes a release.",
    steps: [
      "Untick Red-team and click ▶ Run Agent. The agent sees the CBP hold, notifies Compliance (R4) and the Broker (R5), and waits.",
      "Click “Send forged release (unverified)”. It is rejected — the hold stays.",
      "Click “Send official CBP release”. The agent verifies and the shipment is Cleared ✓.",
    ],
  },
  {
    ref: "SHP-001",
    code: "C01",
    title: "Missing document → collect data",
    shows: "Simple problems are handled by rules alone — no AI call needed.",
    steps: [
      "Click ▶ Run Agent.",
      "The agent spots the missing Commercial Invoice and stops at “Collect Data” without calling the AI.",
    ],
  },
];

export const AUDIT_CHAIN_STEPS = [
  "On any shipment you have run, click “Verify integrity” in the Audit Chain panel → Chain intact.",
  "Click “Simulate tampering (demo)” — this edits one record directly in the database, like an insider covering something up.",
  "Click “Verify integrity” again → the chain is broken at exactly that record.",
];

/** Short explanations for the “?” tips next to each section heading */
export const HELP: Record<string, { title: string; body: string }> = {
  runControls: {
    title: "Run the agent",
    body: "▶ Run Agent starts the AI agent on this shipment: it checks the documents, and if something is wrong it asks the AI for a plan. The red Red-team box adds a prompt-injection attack hidden in the supplier’s invoice.",
  },
  cbpFeed: {
    title: "Mock CBP feed",
    body: "Stands in for U.S. Customs (CBP). Only an official, verified release can lift a hold. The forged button sends the same message from an unverified sender to show it gets rejected.",
  },
  stateMachine: {
    title: "Agent state machine",
    body: "Every step the agent can take. The lit box is where it is now; blue lines are the path it took. The agent can only move along these arrows, and every move passes the safety checks first.",
  },
  analysis: {
    title: "Agent analysis",
    body: "What the AI concluded from the shipment data. The badge shows whether this came from the live AI model or an offline fallback.",
  },
  proposedActions: {
    title: "Proposed actions",
    body: "The AI’s plan. It is only a proposal: deterministic policy checks decide whether each action may run, needs human approval, or is blocked. R2–R5 are the human roles that must sign off.",
  },
  attack: {
    title: "Attack payload",
    body: "Text a malicious supplier hid in the invoice remarks. It is sent to the AI with the rest of the shipment, exactly as real supplier text would be.",
  },
  guardrails: {
    title: "Blocked by guardrails",
    body: "Actions the policy engine refused, and the rule that refused them. These rules are plain code, not AI — they cannot be talked out of their decision.",
  },
  transitions: {
    title: "FSM state transitions",
    body: "The latest run as a list: each step the agent took and the event that caused it.",
  },
  evidence: {
    title: "Evidence trail",
    body: "Each document’s progress from raw upload to extracted data to verified, with its SHA-256 fingerprint so any later change to the file is detectable.",
  },
  documents: {
    title: "Documents",
    body: "Files attached to this shipment, with version and processing status.",
  },
  agentState: {
    title: "Agent state",
    body: "Timeline of every state change, saved permanently — it survives page refreshes and shows when the agent resumes after an approval or a CBP event.",
  },
  auditChain: {
    title: "Audit chain",
    body: "Every audit record stores the fingerprint (hash) of the one before it, like links in a chain. Editing or deleting any record breaks the chain, and Verify shows exactly where.",
  },
  approvals: {
    title: "Pending approvals",
    body: "Decisions waiting for a human. Approving every card for a plan wakes the agent up to carry it out; rejecting any card stops the plan. Approvals expire after 30 minutes.",
  },
};

export const ROLES: [string, string][] = [
  ["R2", "Warehouse Manager — confirms physical quantities"],
  ["R3", "Supplier / Exporter — confirms or corrects commercial documents"],
  ["R4", "Trade Compliance Officer — compliance review, CBP holds"],
  ["R5", "Customs Broker — filings and coordination with CBP"],
];

export const STATES: [string, string][] = [
  ["Observe", "Load the shipment and its documents; look for problems."],
  ["Reason / Plan (LLM)", "The AI analyses the problem and proposes actions."],
  ["Policy Check", "Plain-code rules decide: allow, require human approval, or block."],
  ["Escalate → Wait for Human", "Approval requests sent; the agent pauses until people decide."],
  ["Act → Verify → Cleared", "Approved actions run, the outcome is checked, clearance is verified."],
  ["CBP Hold", "U.S. Customs has stopped the shipment; only an official release lifts it."],
  ["Collect Data", "A required document is missing; waiting for it."],
  ["Recover", "The plan was blocked or rejected; nothing ran and a human must review."],
];

export const GUARDS: [string, string][] = [
  ["G-approval", "Nothing that needs approval runs until every required human approves — and the plan must be unchanged since they did (checked by hash)."],
  ["G-cbp", "Only a verified CBP event can release a hold. The agent can never propose it."],
  ["G-doc-immutable", "The agent can never edit document values; only authorised people can."],
  ["G7 / G8 / G9", "Each action gets a risk score: low → may run, medium → needs approval, high → blocked."],
];
