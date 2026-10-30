"use client";

import { Bookmark, BookmarkCheck } from "lucide-react";
import { toggleSaved, useSaved } from "@/lib/shortlist";

export function SaveButton({ id, title, compact = false }: { id: string; title: string; compact?: boolean }) {
  const saved = useSaved().some((s) => s.nct_id === id);
  const Icon = saved ? BookmarkCheck : Bookmark;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleSaved({ nct_id: id, title });
      }}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${title} from saved studies` : `Save ${title}`}
      className={`relative z-10 inline-flex items-center gap-1.5 rounded-md text-sm font-medium transition-colors ${
        compact ? "p-1.5 text-ink-3 hover:bg-paper-2 hover:text-ink aria-pressed:text-pine" : "border border-rule bg-surface px-3 py-1.5 hover:border-ink-3 aria-pressed:border-pine aria-pressed:text-pine"
      }`}
    >
      <Icon size={compact ? 18 : 16} aria-hidden fill={saved ? "currentColor" : "none"} />
      {!compact && (saved ? "Saved" : "Save")}
    </button>
  );
}
