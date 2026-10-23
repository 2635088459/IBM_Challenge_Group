// components/EvidenceTrail.tsx — raw → extracted → verified document chain

import { DocumentRecord } from "@/lib/api";

interface Props {
  documents: DocumentRecord[];
}

const STAGE_ORDER = ["raw", "extracted", "verified"] as const;
type Stage = (typeof STAGE_ORDER)[number];

const STAGE_ICON: Record<Stage, string> = {
  raw:       "○",
  extracted: "◑",
  verified:  "●",
};

const STAGE_LABEL: Record<Stage, string> = {
  raw:       "Raw",
  extracted: "Extracted",
  verified:  "Verified",
};

const STAGE_COLOR: Record<Stage, string> = {
  raw:       "text-gray-400",
  extracted: "text-yellow-600",
  verified:  "text-green-600",
};

const STAGE_BG: Record<Stage, string> = {
  raw:       "bg-gray-100 border-gray-200",
  extracted: "bg-yellow-50 border-yellow-200",
  verified:  "bg-green-50 border-green-200",
};

function stageReached(docStatus: string): Stage[] {
  const idx = STAGE_ORDER.indexOf(docStatus as Stage);
  if (idx < 0) return ["raw"];
  return STAGE_ORDER.slice(0, idx + 1) as Stage[];
}

export default function EvidenceTrail({ documents }: Props) {
  if (!documents.length) {
    return <p className="text-xs text-gray-400 italic">No documents uploaded yet.</p>;
  }

  return (
    <div className="space-y-4">
      {documents.map((doc) => {
        const reached = new Set(stageReached(doc.status));
        return (
          <div key={doc.id} className="space-y-2">
            {/* Doc header */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                {doc.doc_type.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-gray-400">v{doc.version}</span>
            </div>

            {/* Stage chain */}
            <div className="flex items-center gap-1">
              {STAGE_ORDER.map((stage, i) => {
                const active = reached.has(stage);
                return (
                  <div key={stage} className="flex items-center gap-1">
                    <div
                      className={`flex items-center gap-1 rounded border px-2 py-1 text-xs ${
                        active ? STAGE_BG[stage] : "bg-gray-50 border-gray-200 opacity-40"
                      }`}
                    >
                      <span className={`font-bold ${active ? STAGE_COLOR[stage] : "text-gray-300"}`}>
                        {STAGE_ICON[stage]}
                      </span>
                      <span className={active ? STAGE_COLOR[stage] : "text-gray-300"}>
                        {STAGE_LABEL[stage]}
                      </span>
                    </div>
                    {i < STAGE_ORDER.length - 1 && (
                      <span className={`text-xs ${active ? "text-gray-400" : "text-gray-200"}`}>
                        →
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* File hash */}
            {doc.file_hash && (
              <p className="text-xs font-mono text-gray-400 truncate">
                sha256: {doc.file_hash}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
