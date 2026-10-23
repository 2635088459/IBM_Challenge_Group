// app/page.tsx — Shipment List (Home)

import ShipmentTable from "@/components/ShipmentTable";
import Link from "next/link";

export const metadata = { title: "Customs Clearance — Shipments" };

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-50">
      {/* Nav */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">AI Customs Clearance</h1>
          <p className="text-xs text-gray-400">Autonomous agent — synthetic demo data only</p>
        </div>
        <nav className="flex gap-4 text-sm">
          <Link href="/" className="font-semibold text-blue-600">Shipments</Link>
          <Link href="/approvals" className="text-gray-600 hover:text-blue-600">Approvals</Link>
        </nav>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
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
            ["OBSERVE", "bg-gray-100 text-gray-600"],
            ["ESCALATE", "bg-orange-100 text-orange-700"],
            ["CUSTOMS_HOLD", "bg-red-100 text-red-700"],
            ["CLEARANCE_VERIFIED", "bg-green-100 text-green-700"],
          ].map(([label, cls]) => (
            <span key={label} className={`rounded-full px-2 py-0.5 font-medium ${cls}`}>
              {label}
            </span>
          ))}
        </div>
      </div>
    </main>
  );
}
