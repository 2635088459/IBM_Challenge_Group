// app/page.tsx — Shipment List (Home)

import ShipmentTable from "@/components/ShipmentTable";
import StatusBadge from "@/components/StatusBadge";
import SiteHeader from "@/components/SiteHeader";
import { ScenarioCards } from "@/components/ScenarioGuide";

export const metadata = { title: "Customs Clearance — Shipments" };

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <SiteHeader active="shipments" />

      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="mb-10">
          <ScenarioCards />
        </div>

        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-900">All Shipments</h2>
          <span className="text-xs text-gray-400">Auto-refreshes every 5 s</span>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
          <ShipmentTable />
        </div>

        {/* Legend */}
        <div className="mt-6 flex flex-wrap gap-3 text-xs text-gray-500">
          <span className="font-semibold">Status key:</span>
          {[
            ["OBSERVE", "not checked by the agent yet"],
            ["COLLECT_DATA", "a required document is missing"],
            ["WAIT_EVENT", "a person must approve the agent’s plan"],
            ["CUSTOMS_HOLD", "U.S. Customs stopped the shipment"],
            ["RECOVER", "the plan was blocked or rejected"],
            ["CLEARANCE_VERIFIED", "done"],
          ].map(([status, meaning]) => (
            <span key={status} className="inline-flex items-center gap-1">
              <StatusBadge status={status} size="sm" />
              <span>{meaning}</span>
            </span>
          ))}
        </div>
      </div>
    </main>
  );
}
