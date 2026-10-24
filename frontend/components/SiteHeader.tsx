// components/SiteHeader.tsx — Top bar shared by every page

import Link from "next/link";

const LINKS = [
  { href: "/", key: "shipments", label: "Shipments" },
  { href: "/approvals", key: "approvals", label: "Approvals" },
  { href: "/guide", key: "guide", label: "Guide" },
] as const;

export default function SiteHeader({ active }: { active?: (typeof LINKS)[number]["key"] }) {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-lg font-bold text-gray-900">AI Customs Clearance</h1>
        <p className="text-xs text-gray-400">Autonomous agent — synthetic demo data only</p>
      </div>
      <nav className="flex gap-4 text-sm">
        {LINKS.map((l) => (
          <Link
            key={l.key}
            href={l.href}
            className={l.key === active ? "font-semibold text-blue-600" : "text-gray-600 hover:text-blue-600"}
          >
            {l.key === "guide" ? "📖 Guide" : l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
