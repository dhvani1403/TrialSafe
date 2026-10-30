import type { Status, Verdict } from "@/lib/api";
import { statusCopy, verdictCopy } from "@/lib/format";

export function VerdictLabel({ verdict, className = "" }: { verdict: Verdict; className?: string }) {
  const v = verdictCopy[verdict];
  return <span className={`mark ${v.mark} font-semibold ${className}`}>{v.label}</span>;
}

/** Compact tally of how each checked rule came out. */
export function RuleTally({ counts }: { counts: Record<Status, number> }) {
  const parts: { s: Status; n: number; label: string }[] = [
    { s: "met", n: counts.met, label: "met" },
    { s: "not_met", n: counts.not_met, label: counts.not_met === 1 ? "conflict" : "conflicts" },
    { s: "caution", n: counts.caution + counts.unknown, label: "to check" },
  ];
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
      {parts
        .filter((p) => p.n > 0)
        .map((p) => (
          <span key={p.s} className="inline-flex items-center gap-1.5 tabular-nums">
            <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--${statusCopy[p.s].mark})` }} />
            {p.n} {p.label}
          </span>
        ))}
    </span>
  );
}

/** Match score as a thin ring; the number carries the meaning, the ring is the glance. */
export function ScoreRing({ score, size = 52 }: { score: number; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} title="Match score">
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--rule)" strokeWidth={4} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--pine)"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">
        <span>
          {Math.round(pct)}
          <span className="sr-only"> out of 100 match score</span>
        </span>
      </span>
    </div>
  );
}
