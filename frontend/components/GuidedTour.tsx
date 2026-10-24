// components/GuidedTour.tsx — Step-by-step spotlight tour of the shipment page.
// Targets elements by data-tour="…"; steps whose element is not on the page are skipped.

"use client";

import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { HELP } from "@/lib/guide-content";

interface Step {
  target: string;
  topic: keyof typeof HELP;
  tryIt?: string;
}

const STEPS: Step[] = [
  { target: "header", topic: "runControls", tryIt: "Start here: pick a demo situation, then click ▶ Run Agent." },
  { target: "cbp-feed", topic: "cbpFeed", tryIt: "Try the forged release first — then the official one." },
  { target: "fsm", topic: "stateMachine", tryIt: "After a run, the box that is lit tells you where the agent stopped. The note underneath says why." },
  { target: "attack", topic: "attack" },
  { target: "guardrails", topic: "guardrails" },
  { target: "analysis", topic: "analysis" },
  { target: "actions", topic: "proposedActions" },
  { target: "approvals", topic: "approvals", tryIt: "Approve every card to let the agent continue." },
  { target: "agent-state", topic: "agentState" },
  { target: "audit-chain", topic: "auditChain", tryIt: "Verify → Simulate tampering → Verify again." },
  { target: "evidence", topic: "evidence" },
];

const PAD = 8;
const CARD_W = 340;

function targetEl(step: Step) {
  return document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
}

export default function GuidedTour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // Decide which steps apply when the tour opens
  useEffect(() => {
    if (!open) return;
    setSteps(STEPS.filter((s) => targetEl(s)));
    setIndex(0);
  }, [open]);

  const step = steps[index];

  const measure = useCallback(() => {
    if (step) setRect(targetEl(step)?.getBoundingClientRect() ?? null);
  }, [step]);

  useLayoutEffect(() => {
    if (!open || !step) return;
    targetEl(step)?.scrollIntoView({ block: "center", behavior: "smooth" });
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [open, step, measure]);

  const next = useCallback(() => (index < steps.length - 1 ? setIndex(index + 1) : onClose()), [index, steps.length, onClose]);
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" || e.key === "Enter") next();
      if (e.key === "ArrowLeft") back();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, next, back, onClose]);

  if (!open || !step || !rect) return null;

  const help = HELP[step.topic];
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const cardW = Math.min(CARD_W, vw - 32);
  // Card below the target if it fits, otherwise above, otherwise pinned to the bottom
  const below = rect.bottom + PAD + 12;
  const top = below + 200 < vh ? below : rect.top - PAD - 12 - 200 > 0 ? rect.top - PAD - 12 - 200 : vh - 216;
  const left = Math.min(Math.max(16, rect.left), vw - cardW - 16);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`Tour step ${index + 1}: ${help.title}`}>
      {/* Click-catcher so the page can't be used mid-tour */}
      <div className="absolute inset-0" onClick={onClose} />
      {/* Spotlight: a transparent box whose huge shadow dims everything else */}
      <div
        className="absolute rounded-lg pointer-events-none transition-all duration-200"
        style={{
          top: rect.top - PAD,
          left: rect.left - PAD,
          width: rect.width + PAD * 2,
          height: rect.height + PAD * 2,
          boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.55)",
          outline: "2px solid #60a5fa",
        }}
      />
      <div
        className="absolute rounded-lg bg-white shadow-xl border border-gray-200 p-4 text-sm transition-all duration-200"
        style={{ top, left, width: cardW }}
      >
        <p className="text-[11px] font-semibold text-blue-600 uppercase tracking-wide">
          Step {index + 1} of {steps.length}
        </p>
        <h4 className="mt-1 font-semibold text-gray-900">{help.title}</h4>
        <p className="mt-1 text-xs text-gray-600 leading-relaxed">{help.body}</p>
        {step.tryIt && (
          <p className="mt-2 text-xs text-blue-800 bg-blue-50 rounded px-2 py-1.5">{step.tryIt}</p>
        )}
        <div className="mt-3 flex items-center justify-between">
          <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-600">
            Skip tour
          </button>
          <div className="flex gap-2">
            {index > 0 && (
              <button onClick={back} className="px-3 py-1 rounded-md border border-gray-300 text-xs text-gray-700 hover:bg-gray-50">
                Back
              </button>
            )}
            <button onClick={next} className="px-3 py-1 rounded-md bg-blue-600 text-xs font-medium text-white hover:bg-blue-700">
              {index === steps.length - 1 ? "Finish" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
