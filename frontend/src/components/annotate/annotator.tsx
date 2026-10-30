"use client";

import { ArrowLeft, ArrowRight, Check, Download, Plus, Shuffle, SkipForward, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { api, ApiError, type Annotation, type AnnotationStats, type Concept, type GoldLabel } from "@/lib/api";

type Tab = "draft" | "verified" | "skipped" | "all";
const TABS: { id: Tab; label: string }[] = [
  { id: "draft", label: "To review" },
  { id: "verified", label: "Verified" },
  { id: "skipped", label: "Skipped" },
  { id: "all", label: "All" },
];
const OPS = [
  { v: "present", l: "refers to having it" },
  { v: "absent", l: "requires NOT having it" },
  { v: ">=", l: "at least" },
  { v: "<=", l: "at most" },
  { v: "between", l: "between" },
  { v: "", l: "don’t score the operator" },
];

const storeListeners = new Set<() => void>();

/** A string kept in localStorage (annotator name, token), readable without an effect. */
function useStored(key: string): [string, (v: string) => void] {
  const value = useSyncExternalStore(
    (l) => {
      storeListeners.add(l);
      return () => storeListeners.delete(l);
    },
    () => {
      try {
        return localStorage.getItem(key) ?? "";
      } catch {
        return "";
      }
    },
    () => "",
  );
  const set = (v: string) => {
    try {
      localStorage.setItem(key, v);
    } catch {}
    storeListeners.forEach((l) => l());
  };
  return [value, set];
}

const same = (a: GoldLabel[], b: GoldLabel[]) => JSON.stringify(a) === JSON.stringify(b);

export function Annotator() {
  const [tab, setTab] = useState<Tab>("draft");
  const [items, setItems] = useState<Annotation[] | null>(null);
  const [stats, setStats] = useState<AnnotationStats | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [idx, setIdx] = useState(0);
  // edits are keyed by line id, so moving to another line shows that line's saved labels
  const [edit, setEdit] = useState<{ id: number; labels: GoldLabel[] } | null>(null);
  const [annotator, setAnnotator] = useStored("trialmatch.annotator");
  const [token, setToken] = useStored("trialmatch.annotate-token");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.meta().then((m) => setConcepts(m.concepts)).catch(() => {});
  }, []);

  const refresh = useCallback(
    (keepIndex = false) => {
      api.annotationStats().then(setStats).catch(() => {});
      api
        .annotations(tab)
        .then((rows) => {
          setItems(rows);
          setIdx((i) => (keepIndex ? Math.min(i, Math.max(0, rows.length - 1)) : 0));
        })
        .catch(() => setMsg("Couldn’t load annotations. Is the API running?"));
    },
    [tab],
  );
  useEffect(() => refresh(), [refresh]);

  const item = items?.[idx];
  const labels = useMemo(() => (item && edit?.id === item.id ? edit.labels : item?.labels ?? []), [item, edit]);
  const setLabels = (fn: (ls: GoldLabel[]) => GoldLabel[]) => item && setEdit({ id: item.id, labels: fn(labels) });

  const byId = useMemo(() => Object.fromEntries(concepts.map((c) => [c.id, c])), [concepts]);
  const grouped = useMemo(() => {
    const g: Record<string, Concept[]> = {};
    concepts.forEach((c) => (g[c.category] ??= []).push(c));
    return g;
  }, [concepts]);

  const save = useCallback(
    async (status: "verified" | "skipped") => {
      if (!item) return;
      setBusy(true);
      setMsg(null);
      try {
        await api.saveAnnotation(item.id, { labels, status, annotator: annotator || undefined }, token || undefined);
        setMsg(status === "verified" ? `Line ${item.id} verified.` : `Line ${item.id} skipped.`);
        // in the review queue the saved line drops out, so the same index shows the next one
        refresh(tab === "draft");
        if (tab !== "draft") setIdx((i) => Math.min(i + 1, (items?.length ?? 1) - 1));
      } catch (e) {
        setMsg(e instanceof ApiError && e.status === 403 ? "Saving needs the annotation token (set it below)." : "Couldn’t save. Try again.");
      } finally {
        setBusy(false);
      }
    },
    [item, labels, annotator, token, refresh, tab, items],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      if (e.key === "v" || e.key === "V") save("verified");
      else if (e.key === "s" || e.key === "S") save("skipped");
      else if (e.key === "ArrowRight") setIdx((i) => Math.min(i + 1, (items?.length ?? 1) - 1));
      else if (e.key === "ArrowLeft") setIdx((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save, items]);

  const update = (i: number, patch: Partial<GoldLabel>) => setLabels((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  async function addRandom() {
    setBusy(true);
    try {
      const r = await api.sampleAnnotations(25, token || undefined);
      setMsg(`Added ${r.added} randomly sampled lines, pre-labelled by the rule parser.`);
      refresh();
    } catch (e) {
      setMsg(e instanceof ApiError && e.status === 403 ? "Adding lines needs the annotation token." : "Couldn’t add lines.");
    } finally {
      setBusy(false);
    }
  }

  const pct = stats ? Math.round((100 * stats.verified) / Math.max(1, stats.total)) : 0;

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 pt-10 sm:px-6">
      <header>
        <h1 className="text-[2rem] font-semibold leading-tight tracking-[-0.02em]">Gold standard review</h1>
        <p className="mt-3 max-w-prose text-ink-2">
          Each line below was labelled by an AI assistant. Check the labels against the guideline, fix anything wrong, and mark the
          line verified. Once {stats?.min_verified_for_eval ?? 30} lines are verified, the parsing evaluation switches to your labels.
        </p>
        {stats && (
          <div className="mt-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span>
                <strong className="text-lg tabular-nums">{stats.verified}</strong> of {stats.total} verified
                <span className="text-ink-3"> ({stats.skipped} skipped)</span>
              </span>
              <span className="text-ink-2">
                {stats.verified >= stats.min_verified_for_eval
                  ? "The evaluation now uses verified labels."
                  : `${stats.min_verified_for_eval - stats.verified} more until the evaluation uses your labels`}
              </span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-paper-2">
              <div className="h-2 rounded-full bg-pine" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <div className="flex gap-1 rounded-lg bg-paper-2 p-1 text-sm" role="group" aria-label="Show">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={tab === t.id}
                onClick={() => setTab(t.id)}
                className="rounded-md px-3 py-1 text-ink-2 aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm"
              >
                {t.label}
              </button>
            ))}
          </div>
          <button type="button" onClick={addRandom} disabled={busy} className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-rule bg-surface px-3 py-1.5 text-sm hover:border-ink-3">
            <Shuffle size={15} aria-hidden /> Add 25 random lines
          </button>
          <a href="/api/annotations/export" download="criteria_gold_verified.jsonl" className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-surface px-3 py-1.5 text-sm hover:border-ink-3">
            <Download size={15} aria-hidden /> Export verified
          </a>
        </div>
      </header>

      {msg && (
        <p className="mt-4 text-sm text-ink-2" role="status">
          {msg}
        </p>
      )}

      {items && items.length === 0 && <p className="mt-16 text-center text-ink-2">Nothing here. Switch tabs or add random lines.</p>}

      {item && (
        <section className="mt-8 rounded-xl border border-rule bg-surface" aria-label={`Line ${item.id}`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-3 text-sm">
            <span className="flex flex-wrap gap-x-3 text-ink-2">
              <span className="font-semibold text-ink">
                Line {idx + 1} of {items?.length}
              </span>
              <span className="capitalize">{item.kind}</span>
              <span>{item.source === "random" ? "Random sample" : "Stratified sample"}</span>
              {item.nct_id && (
                <a className="underline underline-offset-4" href={`https://clinicaltrials.gov/study/${item.nct_id}`} target="_blank" rel="noreferrer">
                  {item.nct_id}
                </a>
              )}
            </span>
            <span className={`mark ${item.status === "verified" ? "mark-ok" : item.status === "skipped" ? "mark-no" : "mark-check"}`}>
              {item.status === "draft" ? "AI draft" : item.status}
            </span>
          </div>

          <p className="doc px-5 pt-5 text-[1.05rem]">
            <span className="mark mark-info">{item.text}</span>
          </p>

          <div className="space-y-3 px-5 py-5">
            {labels.length === 0 && <p className="text-sm text-ink-2">No concepts: this line constrains nothing in the vocabulary.</p>}
            {labels.map((l, i) => {
              const c = byId[l.concept];
              return (
                <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg bg-paper px-3 py-2">
                  <select
                    value={l.concept}
                    onChange={(e) => update(i, { concept: e.target.value })}
                    aria-label="Concept"
                    className="rounded-md border border-rule bg-surface px-2 py-1 text-sm"
                  >
                    {Object.entries(grouped).map(([cat, cs]) => (
                      <optgroup key={cat} label={cat}>
                        {cs.map((cc) => (
                          <option key={cc.id} value={cc.id}>
                            {cc.label}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <select
                    value={l.operator ?? ""}
                    onChange={(e) => update(i, { operator: e.target.value || null })}
                    aria-label="Operator"
                    className="rounded-md border border-rule bg-surface px-2 py-1 text-sm"
                  >
                    {OPS.filter((o) => c?.kind === "num" || !["between", ">=", "<="].includes(o.v)).map((o) => (
                      <option key={o.v} value={o.v}>
                        {o.l}
                      </option>
                    ))}
                  </select>
                  {c?.kind === "num" && ["between", ">=", "<="].includes(l.operator ?? "") && (
                    <>
                      <input
                        type="number"
                        step="any"
                        aria-label="Value"
                        value={l.value ?? ""}
                        onChange={(e) => update(i, { value: e.target.value === "" ? null : Number(e.target.value) })}
                        className="w-20 rounded-md border border-rule bg-surface px-2 py-1 text-sm tabular-nums"
                      />
                      {l.operator === "between" && (
                        <>
                          <span className="text-sm text-ink-3">to</span>
                          <input
                            type="number"
                            step="any"
                            aria-label="Upper value"
                            value={l.value_max ?? ""}
                            onChange={(e) => update(i, { value_max: e.target.value === "" ? null : Number(e.target.value) })}
                            className="w-20 rounded-md border border-rule bg-surface px-2 py-1 text-sm tabular-nums"
                          />
                        </>
                      )}
                      {c.unit && <span className="text-sm text-ink-3">{c.unit}</span>}
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => setLabels((ls) => ls.filter((_, j) => j !== i))}
                    aria-label={`Remove ${c?.label ?? l.concept}`}
                    className="ml-auto rounded-md p-1 text-ink-3 hover:bg-paper-2 hover:text-ink"
                  >
                    <X size={16} aria-hidden />
                  </button>
                </div>
              );
            })}
            <label className="inline-flex items-center gap-2 text-sm">
              <Plus size={15} className="text-ink-3" aria-hidden />
              <select
                value=""
                onChange={(e) => e.target.value && setLabels((ls) => [...ls, { concept: e.target.value, operator: "present", value: null, value_max: null }])}
                className="rounded-md border border-dashed border-rule bg-surface px-2 py-1"
                aria-label="Add a concept"
              >
                <option value="">Add a concept</option>
                {Object.entries(grouped).map(([cat, cs]) => (
                  <optgroup key={cat} label={cat}>
                    {cs.map((cc) => (
                      <option key={cc.id} value={cc.id}>
                        {cc.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            {!same(labels, item.draft) && <p className="text-sm text-ink-3">Changed from the AI draft.</p>}
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-rule px-5 py-3">
            <button type="button" onClick={() => setIdx((i) => Math.max(i - 1, 0))} className="rounded-md p-2 text-ink-2 hover:bg-paper-2" aria-label="Previous line">
              <ArrowLeft size={17} aria-hidden />
            </button>
            <button type="button" onClick={() => setIdx((i) => Math.min(i + 1, (items?.length ?? 1) - 1))} className="rounded-md p-2 text-ink-2 hover:bg-paper-2" aria-label="Next line">
              <ArrowRight size={17} aria-hidden />
            </button>
            <span className="hidden text-xs text-ink-3 sm:inline">Keys: V verify, S skip, ← →</span>
            <button type="button" onClick={() => save("skipped")} disabled={busy} className="ml-auto inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-ink-2 hover:bg-paper-2">
              <SkipForward size={15} aria-hidden /> Skip (ambiguous)
            </button>
            <button type="button" onClick={() => save("verified")} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-pine px-4 py-2 text-sm font-semibold text-on-pine hover:bg-pine-hover disabled:opacity-60">
              <Check size={16} aria-hidden /> Labels are correct
            </button>
          </div>
        </section>
      )}

      <div className="mt-10 grid gap-8 md:grid-cols-2">
        <details className="rounded-lg border border-rule px-4 py-3 text-sm" open>
          <summary className="cursor-pointer font-semibold">Labelling guideline</summary>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-ink-2">
            <li>Label what the line literally says. Don’t flip polarity because it sits under “Exclusion”.</li>
            <li>“refers to having it”: the line is about the patient having the thing (“Known HIV”, “Prior anti-PD-1 therapy”).</li>
            <li>“requires NOT having it”: the line itself says no (“must not be pregnant”, “no prior chemotherapy”).</li>
            <li>Numbers: “ECOG 0–1” is between 0 and 1; “age ≥ 18” is at least 18.</li>
            <li>Lines that only say something is allowed (“steroids are permitted”) have no concept.</li>
            <li>Choose “don’t score the operator” when the direction is genuinely unclear; skip lines that are ambiguous overall.</li>
          </ul>
        </details>
        <div className="space-y-3 rounded-lg border border-rule px-4 py-3 text-sm">
          <label className="block">
            <span className="font-semibold">Your name or initials</span>
            <input
              value={annotator}
              onChange={(e) => setAnnotator(e.target.value)}
              className="mt-1 w-full rounded-md border border-rule bg-surface px-2 py-1.5"
            />
          </label>
          {stats?.token_required && (
            <label className="block">
              <span className="font-semibold">Annotation token</span>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="mt-1 w-full rounded-md border border-rule bg-surface px-2 py-1.5"
              />
            </label>
          )}
          <p className="text-ink-3">Saved with each line so you can tell who reviewed it.</p>
        </div>
      </div>
    </div>
  );
}
