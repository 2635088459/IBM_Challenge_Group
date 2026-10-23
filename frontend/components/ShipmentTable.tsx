// components/ShipmentTable.tsx — Shipment list with status badges and navigation

"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher, ShipmentListItem } from "@/lib/api";
import StatusBadge from "./StatusBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ShipmentTable() {
  const { data, error, isLoading } = useSWR<ShipmentListItem[]>(
    `${API_URL}/api/shipments`,
    fetcher,
    { refreshInterval: 5000 }
  );

  if (isLoading) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        Loading shipments…
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-red-500 text-sm">
        Failed to load shipments. Is the API running at{" "}
        <code>{API_URL}</code>?
      </div>
    );
  }

  if (!data?.length) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        No shipments found. Run <code>python scripts/seed.py</code> to seed demo data.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead>
          <tr className="bg-gray-50">
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Reference #</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Created</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {data.map((s) => (
            <tr key={s.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 font-mono font-medium text-gray-900">
                {s.reference_number}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={s.status} />
              </td>
              <td className="px-4 py-3 text-gray-500">{timeAgo(s.created_at)}</td>
              <td className="px-4 py-3">
                <Link
                  href={`/shipments/${s.id}`}
                  className="text-blue-600 hover:underline text-sm font-medium"
                >
                  View →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
