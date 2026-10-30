"use client";

import { MapPin } from "lucide-react";
import Link from "next/link";
import type { MatchResult } from "@/lib/api";
import { ageRange, miles, phaseLabel, statusCopy, statusLabel } from "@/lib/format";
import { SaveButton } from "@/components/save-button";
import { RuleTally, ScoreRing, VerdictLabel } from "@/components/verdict";

export function ResultRow({
  r,
  rank,
  active,
  onHover,
}: {
  r: MatchResult;
  rank: number;
  active: boolean;
  onHover: (id: string | null) => void;
}) {
  const site = r.nearest_site;
  return (
    <li
      id={`r-${r.nct_id}`}
      onMouseEnter={() => onHover(r.nct_id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(r.nct_id)}
      className={`group relative -mx-3 rounded-lg px-3 py-6 transition-colors ${active ? "bg-surface" : ""}`}
    >
      <div className="flex gap-4">
        <ScoreRing score={r.score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <VerdictLabel verdict={r.verdict} />
            <span className="text-ink-2">{phaseLabel(r.phase)}</span>
            <span className="text-ink-2">{statusLabel(r.status)}</span>
            <span className="text-ink-3">#{rank}</span>
            <span className="ml-auto">
              <SaveButton id={r.nct_id} title={r.title} compact />
            </span>
          </div>
          <h2 className="mt-2 text-lg font-semibold leading-snug">
            <Link href={`/trials/${r.nct_id}`} className="after:absolute after:inset-0 hover:underline hover:underline-offset-4 focus-visible:outline-none">
              {r.title}
            </Link>
          </h2>
          <p className="mt-1 flex flex-wrap gap-x-4 text-sm text-ink-2">
            <span>{r.sponsor}</span>
            <span>Ages {ageRange(r.min_age, r.max_age)}</span>
            {r.interventions.length > 0 && <span>Tests {r.interventions.slice(0, 2).join(", ")}</span>}
          </p>

          {(r.reasons_for.length > 0 || r.reasons_against.length > 0) && (
            <ul className="mt-3 space-y-1.5 text-[0.95rem]">
              {r.reasons_against.slice(0, 2).map((a, i) => (
                <li key={`a${i}`} className="flex gap-2">
                  <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: `var(--${statusCopy[a.status].mark})` }} />
                  <span>{a.reason}</span>
                </li>
              ))}
              {r.reasons_for.slice(0, r.reasons_against.length ? 1 : 2).map((f, i) => (
                <li key={`f${i}`} className="flex gap-2 text-ink-2">
                  <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full bg-mark-ok" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
            <RuleTally counts={r.counts} />
            {site && (
              <span className="inline-flex items-center gap-1 text-sm text-ink-2">
                <MapPin size={14} aria-hidden />
                {miles(site.distance_mi)} away in {site.city}
                {site.state ? `, ${site.state}` : ""}
                {r.sites_in_range > 1 && <span className="text-ink-3"> + {r.sites_in_range - 1} more nearby</span>}
              </span>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}
