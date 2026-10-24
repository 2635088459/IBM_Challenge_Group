// app/guide/page.tsx — User guide: what the system does, how to run each demo, glossary

import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import { AUDIT_CHAIN_STEPS, GUARDS, HELP, ROLES, SCENARIOS, STATES } from "@/lib/guide-content";

export const metadata = { title: "Guide — AI Customs Clearance" };

const PAGE_SECTIONS: (keyof typeof HELP)[] = [
  "runControls", "stateMachine", "analysis", "proposedActions", "approvals",
  "agentState", "auditChain", "evidence", "cbpFeed",
];

function Card({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm scroll-mt-6">
      <h2 className="text-base font-semibold text-gray-900 mb-3">{title}</h2>
      {children}
    </section>
  );
}

function Table({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-gray-100 text-sm">
      {rows.map(([term, desc]) => (
        <div key={term} className="py-2 grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-1 sm:gap-4">
          <dt className="font-medium text-gray-800">{term}</dt>
          <dd className="text-gray-600">{desc}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function GuidePage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <SiteHeader active="guide" />

      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">How this works</h1>
          <p className="mt-2 text-sm text-gray-600 leading-relaxed">
            An AI agent clears shipments through customs on its own — and is <b>provably unable</b> to do
            the things only humans or U.S. Customs (CBP) may do. The AI reads the documents and proposes a
            plan; plain-code safety rules decide what may actually happen.
          </p>
          <nav className="mt-4 flex flex-wrap gap-2 text-xs">
            {[["#big-idea", "The big idea"], ["#demos", "Run the demos"], ["#page", "Reading a shipment page"], ["#glossary", "Glossary"]].map(([href, label]) => (
              <a key={href} href={href} className="px-2.5 py-1 rounded-full bg-white border border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-700">
                {label}
              </a>
            ))}
          </nav>
        </div>

        <Card id="big-idea" title="The big idea in 30 seconds">
          <ol className="space-y-3 text-sm text-gray-700">
            <li>
              <b>1. The AI does the work.</b> It reads each shipment, spots problems (a missing invoice,
              quantities that don&apos;t match) and writes a plan to fix them.
            </li>
            <li>
              <b>2. Rules, not the AI, decide.</b> Every proposed action passes a policy check written in
              plain code. Low-risk actions run; anything consequential waits for the right person; dangerous
              ones are blocked outright — however convincingly the AI asks.
            </li>
            <li>
              <b>3. Humans stay in charge.</b> Approvals go to named roles. The agent pauses until they decide,
              then carries out exactly the plan they approved — if the plan changed, the approval no longer counts.
            </li>
            <li>
              <b>4. Everything is provable.</b> Each step is written to an audit log whose records are chained
              together by hashes, so any later edit is detectable.
            </li>
          </ol>
        </Card>

        <Card id="demos" title="Run the demos (about 5 minutes)">
          <p className="text-sm text-gray-500 mb-4">
            Open a shipment from the <Link href="/" className="text-blue-600 hover:underline">Shipments</Link> page
            and follow its steps. Each shipment page also shows these steps and has a <b>Take the tour</b> button.
          </p>
          <div className="space-y-5">
            {SCENARIOS.map((sc) => (
              <div key={sc.code}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-blue-600">
                  {sc.code} · {sc.ref}
                </p>
                <h3 className="font-semibold text-gray-900">{sc.title}</h3>
                <p className="text-sm text-gray-500 mb-1">{sc.shows}</p>
                <ol className="list-decimal pl-5 space-y-0.5 text-sm text-gray-700">
                  {sc.steps.map((st, i) => <li key={i}>{st}</li>)}
                </ol>
              </div>
            ))}
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-blue-600">Audit · any shipment</p>
              <h3 className="font-semibold text-gray-900">Tamper with the audit log → caught</h3>
              <ol className="list-decimal pl-5 space-y-0.5 text-sm text-gray-700">
                {AUDIT_CHAIN_STEPS.map((st, i) => <li key={i}>{st}</li>)}
              </ol>
            </div>
          </div>
          <p className="mt-4 text-xs text-gray-400">
            Demos change the data. To run one again, click <b>↺ Reset this demo</b> on the shipment page,
            or <b>↺ Reset all demos</b> on the Shipments page.
          </p>
        </Card>

        <Card id="page" title="Reading a shipment page">
          <Table rows={PAGE_SECTIONS.map((k) => [HELP[k].title, HELP[k].body])} />
          <p className="mt-3 text-xs text-gray-400">Tip: every section heading has a small “?” with the same explanation.</p>
        </Card>

        <Card id="glossary" title="Glossary">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Agent states</h3>
          <Table rows={STATES} />
          <h3 className="text-sm font-semibold text-gray-700 mt-5 mb-1">Human roles</h3>
          <Table rows={ROLES} />
          <h3 className="text-sm font-semibold text-gray-700 mt-5 mb-1">Safety rules (guards)</h3>
          <Table rows={GUARDS} />
        </Card>
      </div>
    </main>
  );
}
