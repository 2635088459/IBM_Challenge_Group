// components/HelpTip.tsx — “?” button that explains what a section is for

"use client";

import { useEffect, useRef, useState } from "react";
import { HELP } from "@/lib/guide-content";

export default function HelpTip({ topic }: { topic: keyof typeof HELP }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const help = HELP[topic];

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex normal-case tracking-normal font-normal">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`What is ${help.title}?`}
        aria-expanded={open}
        className="w-4 h-4 rounded-full border border-gray-300 text-[10px] leading-none text-gray-500
                   hover:border-blue-400 hover:text-blue-600 flex items-center justify-center"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-6 z-30 w-72 max-w-[80vw] rounded-md border border-gray-200 bg-white
                     p-3 text-xs text-gray-600 shadow-lg leading-relaxed"
        >
          <span className="block font-semibold text-gray-900 mb-1">{help.title}</span>
          {help.body}
        </span>
      )}
    </span>
  );
}
