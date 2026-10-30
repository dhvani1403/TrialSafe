"use client";

import { Loader2, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { api, ApiError, type CriterionResult, type Status, type TrialDetail } from "@/lib/api";
import { statusCopy } from "@/lib/format";

const SEVERITY: Status[] = ["not_met", "caution", "unknown", "met", "review"];

function fmt(n: number | null) {
  if (n == null) return "?";
  return Number.isInteger(n) ? `${n}` : n.toFixed(1);
}

const lc = (label: string) =>
  label
    .split(" ")
    .map((w) => (/[A-Z]/.test(w.slice(1)) ? w : w.toLowerCase()))
    .join(" ");

/** What the parser understood the rule to say, independent of any patient. */
function reading(c: CriterionResult): string {
  const num =
    c.operator === "between" ? ` ${fmt(c.value)}–${fmt(c.value_max)}` : c.operator === ">=" ? ` ${fmt(c.value)} or more` : c.operator === "<=" ? ` ${fmt(c.value)} or less` : "";
  const wants = (c.operator !== "absent") === (c.kind === "inclusion");
  if (num) return `${c.kind === "inclusion" ? "Requires" : "Excludes"} ${lc(c.label)}${num}`;
  return `${wants ? "Requires" : "Excludes"} ${lc(c.label)}${c.timeframe ? ` (${c.timeframe})` : ""}`;
}

export function AnnotatedCriteria({
  trial,
  hasProfile,
  onUpgraded,
}: {
  trial: TrialDetail;
  hasProfile: boolean;
  onUpgraded: () => void;
}) {
  const [focus, setFocus] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
  const [upgradeError, setUpgradeError] = useState<string | null>(null);

  const byLine = useMemo(() => {
    const m = new Map<number, CriterionResult[]>();
    for (const c of trial.criteria) m.set(c.line, [...(m.get(c.line) ?? []), c]);
    return m;
  }, [trial.criteria]);

  const groups = (["inclusion", "exclusion"] as const).map((kind) => ({
    kind,
    lines: trial.eligibility_lines.filter((l) => l.kind === kind),
  }));

  async function upgrade() {
    setUpgrading(true);
    setUpgradeError(null);
    try {
      await api.upgradeParse(trial.nct_id);
      onUpgraded();
    } catch (e) {
      setUpgradeError(e instanceof ApiError ? e.message : "The AI reader isn't available right now.");
    } finally {
      setUpgrading(false);
    }
  }

  const attention = (cs: CriterionResult[] | undefined) =>
    !!cs?.some((c) => c.status === "not_met" || c.status === "caution" || c.status === "unknown");

  return (
    <section className="mt-12" aria-labelledby="criteria-h">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="criteria-h" className="text-xl font-semibold tracking-tight">
            {hasProfile ? "How you compare, rule by rule" : "Who can join"}
          </h2>
          <p className="mt-1 max-w-prose text-sm text-ink-2">
            The study’s own wording, with our reading underneath.{" "}
            {trial.parser === "llm" ? "Read by an AI model and checked against our concept list." : "Read by our rule-based reader."}
          </p>
        </div>
        {hasProfile && (
          <div className="flex gap-1 rounded-lg bg-paper-2 p-1 text-sm" role="group" aria-label="Show">
            <button type="button" aria-pressed={!focus} onClick={() => setFocus(false)} className="rounded-md px-3 py-1 text-ink-2 aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm">
              Every rule
            </button>
            <button type="button" aria-pressed={focus} onClick={() => setFocus(true)} className="rounded-md px-3 py-1 text-ink-2 aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm">
              Needs attention
            </button>
          </div>
        )}
      </div>

      {trial.parser === "rules" && trial.llm_budget_remaining > 1 && (
        <div className="mt-5 flex flex-col gap-3 rounded-lg border border-dashed border-rule px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="text-ink-2">The AI reader catches more negations and exceptions than our rules (F1 0.93 vs 0.88 on our test set).</span>
          <button
            type="button"
            onClick={upgrade}
            disabled={upgrading}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-pine px-3 py-1.5 font-medium text-pine hover:bg-pine hover:text-on-pine disabled:opacity-60"
          >
            {upgrading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Sparkles size={15} aria-hidden />}
            {upgrading ? "Reading… about 20 seconds" : "Re-read with AI"}
          </button>
        </div>
      )}
      {upgradeError && <p className="mt-2 text-sm text-ink-2" role="status">{upgradeError}</p>}

      {groups.map(
        (g) =>
          g.lines.length > 0 && (
            <div key={g.kind} className="mt-8">
              <h3 className="border-b border-rule pb-2 font-semibold">
                {g.kind === "inclusion" ? "You need to" : "You can’t join if"}
                <span className="ml-2 text-sm font-normal text-ink-3">{g.kind === "inclusion" ? "Inclusion criteria" : "Exclusion criteria"}</span>
              </h3>
              <ol className="divide-y divide-rule/60">
                {g.lines.map((l) => {
                  const cs = byLine.get(l.index);
                  if (focus && !attention(cs)) return null;
                  const worst = cs ? SEVERITY.find((s) => cs.some((c) => c.status === s)) : undefined;
                  const markCls = worst && hasProfile ? `mark ${statusCopy[worst].mark}` : cs ? "mark mark-info" : "";
                  return (
                    <li key={l.index} className="grid gap-2 py-4 md:grid-cols-[minmax(0,1fr)_15rem] md:gap-6">
                      <p className={`doc text-[0.98rem] ${cs ? "text-ink" : "text-ink-3"}`}>
                        <span className={markCls}>{l.text}</span>
                      </p>
                      <div className="space-y-1.5 text-sm md:border-l md:border-rule md:pl-4">
                        {cs?.map((c, i) => (
                          <p key={i}>
                            {hasProfile && c.status !== "review" ? (
                              <>
                                <span className="font-semibold">{statusCopy[c.status].label}.</span>{" "}
                                <span className="text-ink-2">{c.reason}</span>
                              </>
                            ) : (
                              <span className="text-ink-2">{reading(c)}</span>
                            )}
                          </p>
                        ))}
                        {!cs && <p className="text-ink-3">Not something we can check.</p>}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          ),
      )}
      {trial.eligibility_lines.length === 0 && <p className="mt-6 text-ink-2">This listing has no eligibility text.</p>}
    </section>
  );
}
