// app/shipments/[id]/page.tsx — Shipment detail, evidence trail, agent state timeline

import { Suspense } from "react";
import ShipmentDetailClient from "./ShipmentDetailClient";

export default function ShipmentDetailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-gray-50 flex items-center justify-center">
          <p className="text-gray-400 text-sm">Loading shipment…</p>
        </main>
      }
    >
      <ShipmentDetailClient />
    </Suspense>
  );
}
