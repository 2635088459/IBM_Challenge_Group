// components/ScenarioGuide.tsx — “Start here” scenario cards (home) and “Try this” steps (shipment page)

"use client";

import Link from "next/link";
import useSWR from "swr";
import { useState } from "react";
import { fetcher, ShipmentListItem, resetDemo } from "@/lib/api";
import { SCENARIOS } from "@/lib/guide-content";

// Same-origin by default: next.config.ts proxies /api/* to the backend
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Home page: one card per demo scenario, linking to its shipment */
export function ScenarioCards() {
  const { data: shipments, mutate } = useSWR<ShipmentListItem[]>(`${API_URL}/api/shipments`, fetcher);
  const idByRef = new Map((shipments ?? []).map((s) => [s.reference_number, s.id]));
  const [resetState, setResetState] = useState<"idle" | "busy" | "done">("idle");

  async function resetAll() {
    if (!window.confirm("Reset all three demo shipments to their starting state? This affects everyone using the site.")) return;
    setResetState("busy");
    try {
      await resetDemo();
      await mutate();
      setResetState("done");
    } catch {
      setResetState("idle");
      window.alert("Reset failed — is the API running?");
    }
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
        <h2 className="text-xl font-semibold text-gray-900">Start here</h2>
        <div className="flex items-center gap-4">
          <Link href="/guide" className="text-xs text-blue-600 hover:underline">
            New to this? Read the 3-minute guide →
          </Link>
          <button
            onClick={resetAll}
            disabled={resetState === "busy"}
            className="px-2.5 py-1 rounded-md border border-gray-300 text-xs text-gray-600 hover:border-amber-400 hover:text-amber-700 disabled:opacity-50"
          >
            {resetState === "busy" ? "Resetting…" : resetState === "done" ? "✓ All demos reset" : "↺ Reset all demos"}
          </button>
        </div>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Each card is a short demo. Open the shipment and follow the steps — a guided tour is available on every shipment page.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {SCENARIOS.map((sc) => {
          const id = idByRef.get(sc.ref);
          return (
            <div key={sc.code} className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm flex flex-col">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-blue-600">
                {sc.code} · {sc.ref}
              </p>
              <h3 className="mt-1 font-semibold text-gray-900">{sc.title}</h3>
              <p className="mt-1 text-xs text-gray-500 leading-relaxed flex-1">{sc.shows}</p>
              {id ? (
                <Link
                  href={`/shipments/${id}`}
                  className="mt-3 self-start px-3 py-1.5 rounded-md bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
                >
                  Open {sc.ref} →
                </Link>
              ) : (
                <p className="mt-3 text-xs text-gray-400">{sc.ref} not found — run `make seed`.</p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Shipment page: the steps for the scenario(s) this shipment demonstrates */
export function ScenarioSteps({ reference }: { reference: string }) {
  const scenarios = SCENARIOS.filter((s) => s.ref === reference);
  if (!scenarios.length) return null;

  return (
    <details open className="mt-5 rounded-md border border-blue-100 bg-blue-50/60 px-4 py-3 text-xs">
      <summary className="cursor-pointer font-semibold text-blue-900 select-none">
        What to try on {reference}
      </summary>
      <div className="mt-2 space-y-3">
        {scenarios.map((sc) => (
          <div key={sc.code}>
            <p className="font-semibold text-gray-800">
              {sc.code} — {sc.title}
            </p>
            <p className="text-gray-500 mb-1">{sc.shows}</p>
            <ol className="list-decimal pl-5 space-y-0.5 text-gray-700">
              {sc.steps.map((st, i) => (
                <li key={i}>{st}</li>
              ))}
            </ol>
          </div>
        ))}
        <p className="text-gray-500">
          Finished? Click <span className="font-semibold">↺ Reset this demo</span> (top right) to run it again.
        </p>
      </div>
    </details>
  );
}
