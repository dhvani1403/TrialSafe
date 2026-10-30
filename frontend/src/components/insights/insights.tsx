"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { ChartFrame, TooltipBox, useVizColors, type VizColors } from "./chart-kit";

const FEATURE_NAMES: Record<string, string> = {
  rrf: "Keyword + meaning search rank",
  fts_rank: "Keyword match strength",
  vec_sim: "Meaning similarity",
  cond_lex: "Condition name match",
  cond_anc: "Broader condition match",
  cond_title: "Condition in title",
  condition_score: "Overall condition fit",
  elig_score: "Eligibility score",
  n_met: "Rules met",
  n_not_met: "Rule conflicts",
  n_caution: "Rules to check",
  n_unknown: "Rules unanswered",
  coverage: "Share of rules checkable",
  structured_fail: "Age / sex excluded",
  has_location: "Location given",
  log_dist: "Distance to nearest site",
  log_sites_in_range: "Sites within range",
  phase_num: "Trial phase",
  interventional: "Interventional study",
  recruiting: "Recruiting now",
  log_enrollment: "Enrollment size",
  recency_years: "Time since update",
  industry: "Industry sponsor",
};

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function Insights() {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState(false);
  const c = useVizColors();
  useEffect(() => {
    api.insights().then(setD).catch(() => setError(true));
  }, []);

  if (error) return <p className="mx-auto max-w-6xl px-6 py-16 text-ink-2">The insights service isn&apos;t responding. Check that the API is running.</p>;
  if (!d || !c) return <p className="mx-auto max-w-6xl px-6 py-16 text-ink-2" aria-live="polite">Loading evaluation reports…</p>;

  const { parsing, ranking, fairness, trec, explanations } = d.reports;
  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 pt-10 sm:px-6">
      <header className="max-w-3xl">
        <h1 className="text-[2rem] font-semibold leading-tight tracking-[-0.02em] sm:text-[2.4rem]">How accurate and fair is TrialMatch?</h1>
        <p className="mt-4 text-lg text-ink-2">
          Three measurements we re-run whenever the data or models change: how well we read eligibility rules, how well we rank
          studies, and who ends up with fewer options.
        </p>
        <nav aria-label="Sections" className="mt-6 flex flex-wrap gap-2 text-sm">
          {[
            ["#parsing", "Reading rules"],
            ["#benchmark", "Real patients (TREC)"],
            ["#ranking", "Ranking"],
            ["#explanations", "AI explanations"],
            ["#fairness", "Fairness"],
            ["#data", "Data"],
          ].map(([h, l]) => (
            <a key={h} href={h} className="rounded-full border border-rule px-3 py-1 hover:border-ink-3">
              {l}
            </a>
          ))}
        </nav>
      </header>

      {parsing && <ParsingSection r={parsing} c={c} />}
      {trec && <TrecSection r={trec} c={c} />}
      {ranking && <RankingSection r={ranking} c={c} />}
      {explanations && <ExplanationSection r={explanations} />}
      {fairness && <FairnessSection r={fairness} c={c} />}
      <DataSection data={d.data} c={c} />
    </div>
  );
}

function Section({ id, title, intro, children, when }: { id: string; title: string; intro: React.ReactNode; children: React.ReactNode; when?: string }) {
  return (
    <section id={id} className="mt-20 scroll-mt-20 border-t border-rule pt-10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
        {when && <span className="text-sm text-ink-3">Last run {shortDate(when)}</span>}
      </div>
      <div className="mt-3 max-w-prose text-ink-2">{intro}</div>
      <div className="mt-8">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ parsing */

function ParsingSection({ r, c }: { r: any; c: VizColors }) {
  const rules = r.parsers.rules;
  const llm = r.parsers.llm;
  const cats = Object.keys(rules.by_category);
  const rows = cats.map((k) => ({
    label: rules.by_category[k].label.replace(" (needs your care team)", ""),
    rules: rules.by_category[k].f1,
    llm: llm?.by_category?.[k]?.f1 ?? null,
  }));
  const metrics: [string, string, (p: any) => string][] = [
    ["F1 (overall)", "Balance of finding rules and not inventing them", (p) => p.overall.f1.toFixed(2)],
    ["Precision", "Of the rules it found, share that were right", (p) => pct(p.overall.precision)],
    ["Recall", "Of the real rules, share it found", (p) => pct(p.overall.recall)],
    ["Operator accuracy", "Got the direction and numbers right", (p) => pct(p.operator_accuracy)],
    ["False alarms", "Lines with no rule where it still flagged one", (p) => pct(p.negative_line_fp_rate)],
  ];
  const errs = (llm?.errors ?? rules.errors).slice(0, 4);

  return (
    <Section
      id="parsing"
      title="Reading eligibility rules"
      when={r.generated_at}
      intro={
        <>
          We hand-labeled {rules.n_lines} real criterion lines ({rules.n_labels} rules) and compared what each reader extracted.
          The AI reader is a free model on OpenRouter; the rule-based reader is our deterministic baseline.
        </>
      }
    >
      <div className="grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div>
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-ink/30 text-sm">
                <th className="py-2 font-medium text-ink-2">Measure</th>
                <th className="py-2 text-right font-semibold">
                  <span className="inline-flex items-center gap-1.5"><Swatch color={c["viz-a"]} />Rules</span>
                </th>
                <th className="py-2 text-right font-semibold">
                  <span className="inline-flex items-center gap-1.5"><Swatch color={c["viz-b"]} />AI</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(([name, hint, f]) => (
                <tr key={name} className="border-b border-rule">
                  <td className="py-3">
                    <span className="block font-medium">{name}</span>
                    <span className="text-sm text-ink-3">{hint}</span>
                  </td>
                  <td className="py-3 text-right text-lg tabular-nums">{f(rules)}</td>
                  <td className="py-3 text-right text-lg font-semibold tabular-nums">{llm ? f(llm) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.gold_source && (
            <p className="mt-4 text-sm text-ink-2">
              Gold labels: {r.gold_source}.{" "}
              <a href="/annotate" className="font-medium text-pine underline underline-offset-4">
                Review them
              </a>
            </p>
          )}
          {r.age_agreement?.rules && (
            <p className="mt-4 text-sm text-ink-2">
              Across all {r.age_agreement.rules.trials.toLocaleString()} trials, the minimum age we read from the text matches the
              registry&apos;s structured field {pct(r.age_agreement.rules.min_age_agreement)} of the time.
            </p>
          )}
        </div>

        <ChartFrame
          title="F1 by kind of rule"
          sub="Higher is better. 1.0 means every rule found, none invented."
          legend={[
            { label: "Rule-based reader", color: c["viz-a"] },
            { label: "AI reader", color: c["viz-b"] },
          ]}
          table={{ head: ["Kind of rule", "Rules", "AI"], rows: rows.map((x) => [x.label, x.rules.toFixed(2), x.llm?.toFixed(2) ?? "—"]) }}
        >
          <ResponsiveContainer width="100%" height={rows.length * 46 + 30}>
            <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }} barGap={2} barCategoryGap="22%">
              <CartesianGrid horizontal={false} stroke={c["viz-grid"]} />
              <XAxis type="number" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={{ fill: c["ink-3"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={170} tick={{ fill: c["ink-2"], fontSize: 13 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: c["viz-grid"], opacity: 0.5 }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <TooltipBox
                      title={String(label)}
                      rows={[
                        { label: "Rules", value: Number(payload[0]?.value ?? 0).toFixed(2), color: c["viz-a"] },
                        { label: "AI", value: payload[1]?.value != null ? Number(payload[1].value).toFixed(2) : "—", color: c["viz-b"] },
                      ]}
                    />
                  ) : null
                }
              />
              <Bar dataKey="rules" fill={c["viz-a"]} barSize={12} radius={[0, 4, 4, 0]} isAnimationActive={false} />
              <Bar dataKey="llm" fill={c["viz-b"]} barSize={12} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="llm" position="right" formatter={(v: any) => (v == null ? "" : Number(v).toFixed(2))} style={{ fill: c["ink-2"], fontSize: 12 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </div>

      {errs.length > 0 && (
        <div className="mt-12">
          <h3 className="font-semibold">Where the {llm ? "AI" : "rule-based"} reader still slips</h3>
          <ul className="mt-4 grid gap-x-8 gap-y-5 md:grid-cols-2">
            {errs.map((e: any, i: number) => (
              <li key={i} className="border-l-2 border-rule pl-4">
                <p className="doc text-[0.95rem]">
                  <span className={`mark ${e.type === "missed" ? "mark-check" : "mark-no"}`}>{e.text}</span>
                </p>
                <p className="mt-1 text-sm text-ink-2">
                  {e.type === "missed" && <>Missed <strong>{e.concept.replace(/_/g, " ")}</strong>.</>}
                  {e.type === "false_positive" && <>Flagged <strong>{e.concept.replace(/_/g, " ")}</strong>, which isn&apos;t a rule here.</>}
                  {e.type === "operator" && <>Read <strong>{e.concept.replace(/_/g, " ")}</strong> as {opText(e.pred)}; should be {opText(e.gold)}.</>}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Caveats notes={r.notes} />
    </Section>
  );
}

/* ------------------------------------------------------------------ ranking */

function RankingSection({ r, c }: { r: any; c: VizColors }) {
  const methods = Object.entries(r.results).map(([name, m]: [string, any]) => ({
    name: name.replace(" (ours)", ""),
    ours: name.includes("ours"),
    ndcg: m["ndcg@10"],
    mrr: m.mrr_seed,
    recall: m["recall@10"],
  })).sort((a, b) => b.ndcg - a.ndcg); // JSONB doesn't keep key order
  const feats = (r.feature_importance ?? [])
    .filter((f: any) => f.importance > 0)
    .slice(0, 10)
    .map((f: any) => ({ name: FEATURE_NAMES[f.feature] ?? f.feature, v: f.importance }));
  return (
    <Section
      id="ranking"
      title="Ranking on synthetic patients"
      when={r.generated_at}
      intro={
        <>
          No public dataset says which trials suit which patient, so we built {r.train_queries + r.test_queries} synthetic patients
          from real trials and graded every candidate (the source trial is a 3, same disease and eligible nearby is a 2). Scores
          below are on {r.test_queries} held-out patients. Because the grades are synthetic, compare the methods rather than
          reading the numbers as real-world accuracy.
        </>
      }
    >
      <div className="grid gap-12 lg:grid-cols-2">
        <ChartFrame
          title="NDCG@10 by ranking method"
          sub="How close the top 10 is to the ideal order (1.0 = perfect)."
          table={{ head: ["Method", "NDCG@10", "Source trial MRR", "Recall@10"], rows: methods.map((m) => [m.name, m.ndcg.toFixed(3), m.mrr.toFixed(3), m.recall.toFixed(3)]) }}
        >
          <ResponsiveContainer width="100%" height={methods.length * 52 + 30}>
            <BarChart data={methods} layout="vertical" margin={{ left: 0, right: 44, top: 0, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke={c["viz-grid"]} />
              <XAxis type="number" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={{ fill: c["ink-3"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={190} tick={{ fill: c["ink-2"], fontSize: 13 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: c["viz-grid"], opacity: 0.5 }}
                content={({ active, payload }) => {
                  const m = payload?.[0]?.payload;
                  return active && m ? (
                    <TooltipBox
                      title={m.name}
                      rows={[
                        { label: "NDCG@10", value: m.ndcg.toFixed(3) },
                        { label: "Source trial MRR", value: m.mrr.toFixed(3) },
                        { label: "Recall@10", value: m.recall.toFixed(3) },
                      ]}
                    />
                  ) : null;
                }}
              />
              <Bar
                dataKey="ndcg"
                barSize={18}
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
                shape={(props: any) => <rect x={props.x} y={props.y} width={Math.max(0, props.width)} height={props.height} rx={4} fill={props.payload.ours ? c["viz-b"] : c["viz-muted"]} />}
              >
                <LabelList dataKey="ndcg" position="right" formatter={(v: any) => Number(v).toFixed(2)} style={{ fill: c["ink-2"], fontSize: 12 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-sm text-ink-2">
            <Swatch color={c["viz-b"]} /> Learned model (gradient-boosted trees), used in the app
          </p>
        </ChartFrame>

        <ChartFrame
          title="What the model pays attention to"
          sub="Drop in accuracy when each signal is scrambled (permutation importance)."
          table={{ head: ["Signal", "Importance"], rows: feats.map((f: any) => [f.name, f.v.toFixed(3)]) }}
        >
          <ResponsiveContainer width="100%" height={feats.length * 34 + 30}>
            <BarChart data={feats} layout="vertical" margin={{ left: 0, right: 44, top: 0, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke={c["viz-grid"]} />
              <XAxis type="number" tick={{ fill: c["ink-3"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={190} tick={{ fill: c["ink-2"], fontSize: 13 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: c["viz-grid"], opacity: 0.5 }}
                content={({ active, payload }) => {
                  const f = payload?.[0]?.payload;
                  return active && f ? <TooltipBox title={f.name} rows={[{ label: "Importance", value: f.v.toFixed(3) }]} /> : null;
                }}
              />
              <Bar dataKey="v" fill={c["viz-b"]} barSize={14} radius={[0, 4, 4, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </div>
    </Section>
  );
}

/* ----------------------------------------------------------------- fairness */

const SETTING_NAMES: Record<string, string> = { urban: "Large cities", "small city": "Small cities", rural: "Rural towns", female: "Women", male: "Men" };

function GroupBars({ title, rows, c, order }: { title: string; rows: any[]; c: VizColors; order?: string[] }) {
  const data = (order ? [...rows].sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group)) : rows).map((r) => ({
    ...r,
    name: SETTING_NAMES[r.group] ?? r.group,
  }));
  const max = Math.max(...data.map((d) => d.mean_matches));
  return (
    <ChartFrame title={title} table={{ head: ["Group", "Average matches", "vs best group"], rows: data.map((d) => [d.name, d.mean_matches.toFixed(1), pct(d.ratio)]) }}>
      <ul className="space-y-3">
        {data.map((d) => (
          <li key={d.group} className="grid grid-cols-[7.5rem_1fr_3rem] items-center gap-3 text-sm">
            <span className="text-ink-2">{d.name}</span>
            <span className="relative h-3 rounded-full bg-paper-2" title={`${d.mean_matches.toFixed(1)} matches, ${pct(d.ratio)} of best`}>
              <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(2, (100 * d.mean_matches) / max)}%`, background: d.flag ? c["viz-a"] : c["viz-b"] }} />
            </span>
            <span className="text-right font-semibold tabular-nums">{d.mean_matches.toFixed(1)}</span>
            {d.flag && (
              <span className="col-start-2 col-end-4 -mt-2 inline-flex items-center gap-1 text-xs text-ink-2">
                <AlertTriangle size={12} aria-hidden style={{ color: c["viz-flag"] }} /> {pct(d.ratio)} of the best-served group
              </span>
            )}
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}

function FairnessSection({ r, c }: { r: any; c: VizColors }) {
  const ages: string[] = r.params.ages;
  const conds = Object.keys(r.heatmap);
  const all = conds.flatMap((k) => ages.map((a) => r.heatmap[k][a] as number));
  const hi = Math.max(...all, 1);
  const step = (v: number) => (v <= 0 ? 0 : Math.min(6, 1 + Math.floor((5 * v) / hi)));
  return (
    <Section
      id="fairness"
      title="Who gets fewer options"
      when={r.generated_at}
      intro={
        <>
          We searched for {conds.length} common conditions as {ages.length} age groups, both sexes, from {r.params.locations} US towns and
          cities, counting studies open to that person with a site within {r.params.radius_mi} miles. Groups below 80% of the best-served
          group are flagged. This measures access to listed studies, not who would qualify medically.
        </>
      }
    >
      <ul className="grid gap-4 md:grid-cols-2">
        {r.headline.map((h: string) => (
          <li key={h} className="rounded-lg bg-surface px-5 py-4 text-[1.05rem] leading-snug shadow-[0_0_0_1px_var(--rule)]">
            {h}
          </li>
        ))}
      </ul>

      <div className="mt-12 grid gap-12 md:grid-cols-2">
        <GroupBars title="By where you live" rows={r.by_setting} c={c} order={["urban", "small city", "rural"]} />
        <GroupBars title="By region" rows={[...r.by_region].sort((a: any, b: any) => b.mean_matches - a.mean_matches)} c={c} />
        <GroupBars title="By age" rows={r.by_age} c={c} />
        <GroupBars title="By sex" rows={r.by_sex} c={c} />
      </div>

      <div className="mt-14">
        <ChartFrame
          title="Average reachable studies, by condition and age"
          sub="Darker means more studies. Older adults lose options as studies cap enrollment age."
          table={{ head: ["Condition", ...ages], rows: conds.map((k) => [k, ...ages.map((a) => r.heatmap[k][a])]) }}
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] border-separate border-spacing-[2px] text-sm">
              <thead>
                <tr>
                  <th className="w-44" />
                  {ages.map((a) => (
                    <th key={a} scope="col" className="pb-1 text-center font-medium text-ink-2">
                      {a}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {conds.map((k) => (
                  <tr key={k}>
                    <th scope="row" className="pr-3 text-left font-normal capitalize text-ink-2">
                      {k}
                    </th>
                    {ages.map((a) => {
                      const v = r.heatmap[k][a] as number;
                      const s = step(v);
                      return (
                        <td
                          key={a}
                          title={`${k}, ${a}: ${v} studies`}
                          className="h-10 rounded-[4px] text-center tabular-nums"
                          style={{ background: s ? `var(--seq-${s})` : "var(--paper-2)", color: s >= 4 ? "#ffffff" : c.ink }}
                        >
                          {v.toFixed(v < 10 ? 1 : 0)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ChartFrame>
      </div>

      <div className="mt-14 grid gap-12 md:grid-cols-2">
        <ChartFrame
          title="Studies that exclude people over 75"
          sub="Share of relevant studies with a maximum age under 75."
          table={{ head: ["Condition", "Studies", "Cap under 75", "Cap under 65", "One sex only"], rows: r.age_caps.map((x: any) => [x.condition, x.trials, `${x.pct_cap_under_75}%`, `${x.pct_cap_under_65}%`, `${x.pct_sex_restricted}%`]) }}
        >
          <ul className="space-y-2.5">
            {[...r.age_caps].sort((a: any, b: any) => b.pct_cap_under_75 - a.pct_cap_under_75).map((x: any) => (
              <li key={x.condition} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm">
                <span className="capitalize text-ink-2">{x.condition}</span>
                <span className="relative h-2.5 rounded-full bg-paper-2">
                  <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(1, x.pct_cap_under_75)}%`, background: c["viz-a"] }} />
                </span>
                <span className="text-right tabular-nums">{Math.round(x.pct_cap_under_75)}%</span>
              </li>
            ))}
          </ul>
        </ChartFrame>
        <ChartFrame title="Reference locations" sub="Average studies within reach, across all conditions and ages." table={{ head: ["Place", "Setting", "Region", "Average"], rows: r.locations.map((l: any) => [l.label, l.setting, l.region, l.mean_matches.toFixed(1)]) }}>
          <ol className="columns-1 gap-8 text-sm sm:columns-2">
            {r.locations.map((l: any) => (
              <li key={l.label} className="flex break-inside-avoid justify-between border-b border-rule/60 py-1.5">
                <span>
                  {l.label} <span className="text-ink-3">{l.setting}</span>
                </span>
                <span className="font-semibold tabular-nums">{l.mean_matches.toFixed(1)}</span>
              </li>
            ))}
          </ol>
        </ChartFrame>
      </div>
    </Section>
  );
}

/* --------------------------------------------------------------------- data */

function DataSection({ data, c }: { data: any; c: VizColors }) {
  const byCond = data.by_condition.filter((x: any) => x.label).slice(0, 26);
  return (
    <Section
      id="data"
      title="The data behind it"
      intro={<>Open US studies pulled from the ClinicalTrials.gov API on a schedule, one query per condition, stored in Postgres with vector search.</>}
    >
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <ChartFrame title="Studies per search condition" table={{ head: ["Condition", "Studies"], rows: byCond.map((x: any) => [x.label, x.n]) }}>
          <ResponsiveContainer width="100%" height={byCond.length * 24 + 30}>
            <BarChart data={byCond} layout="vertical" margin={{ left: 0, right: 40, top: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" width={160} interval={0} tick={{ fill: c["ink-2"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: c["viz-grid"], opacity: 0.5 }}
                content={({ active, payload }) => {
                  const x = payload?.[0]?.payload;
                  return active && x ? <TooltipBox title={x.label} rows={[{ label: "Studies", value: String(x.n) }]} /> : null;
                }}
              />
              <Bar dataKey="n" fill={c["viz-b"]} barSize={12} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="n" position="right" style={{ fill: c["ink-3"], fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>

        <div className="space-y-10">
          <div>
            <h3 className="font-semibold">Recent ingestion runs</h3>
            <table className="mt-3 w-full text-left text-sm tabular-nums">
              <thead>
                <tr className="border-b border-rule text-ink-2">
                  <th className="py-1.5 font-medium">Started</th>
                  <th className="py-1.5 font-medium">Status</th>
                  <th className="py-1.5 text-right font-medium">Studies</th>
                </tr>
              </thead>
              <tbody>
                {data.ingest_runs.map((r: any) => (
                  <tr key={r.id} className="border-b border-rule/60">
                    <td className="py-1.5">{new Date(r.started_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</td>
                    <td className="py-1.5">{r.status}</td>
                    <td className="py-1.5 text-right">{r.trials_upserted?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h3 className="font-semibold">AI model calls</h3>
            <p className="mt-1 text-sm text-ink-2">Free-tier models, capped per day. Every call is logged.</p>
            <table className="mt-3 w-full text-left text-sm tabular-nums">
              <thead>
                <tr className="border-b border-rule text-ink-2">
                  <th className="py-1.5 font-medium">Day</th>
                  <th className="py-1.5 font-medium">Purpose</th>
                  <th className="py-1.5 text-right font-medium">Calls</th>
                  <th className="py-1.5 text-right font-medium">Avg time</th>
                </tr>
              </thead>
              <tbody>
                {data.llm_usage.map((r: any, i: number) => (
                  <tr key={i} className="border-b border-rule/60">
                    <td className="py-1.5">{shortDay(r.day)}</td>
                    <td className="py-1.5">{r.purpose}</td>
                    <td className="py-1.5 text-right">
                      {r.ok}/{r.calls}
                    </td>
                    <td className="py-1.5 text-right">{(r.avg_ms / 1000).toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Section>
  );
}

/** "between 30.0 45.0" -> "30–45", ">= 18 None" -> "≥ 18", "absent None None" -> "absent" */
function opText(raw: string) {
  const [op, a, b] = raw.split(" ");
  const n = (x: string) => (x && x !== "None" ? String(Number(x)) : "");
  if (op === "between") return `${n(a)}–${n(b)}`;
  if (op === ">=") return `≥ ${n(a)}`;
  if (op === "<=") return `≤ ${n(a)}`;
  return op;
}

function shortDay(d: string) {
  return new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function Swatch({ color }: { color: string }) {
  return <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: color }} />;
}

function Caveats({ notes }: { notes?: string[] }) {
  if (!notes?.length) return null;
  return (
    <details className="mt-10 rounded-lg border border-rule px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">Caveats on this evaluation</summary>
      <ul className="mt-2 list-disc space-y-1.5 pl-5 text-ink-2">
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </details>
  );
}

/* -------------------------------------------------------------------- TREC */

function TrecSection({ r, c }: { r: any; c: VizColors }) {
  const methods = Object.entries(r.results)
    .map(([name, m]: [string, any]) => ({ name, ndcg: m["ndcg@10"], p10: m["p@10"], mrr: m.mrr }))
    .sort((a, b) => b.ndcg - a.ndcg);
  const ours = methods.find((m) => m.name.includes("production")) ?? methods[0];
  const e = r.eligibility;
  return (
    <Section
      id="benchmark"
      title="Tested on real patient cases"
      when={r.generated_at}
      intro={
        <>
          The TREC {r.year} Clinical Trials track gives {r.topics} real patient descriptions with expert judgements on{" "}
          {r.pairs.toLocaleString()} patient–trial pairs: eligible, excluded, or not relevant. We extract each patient&apos;s
          profile from the note automatically and re-rank the judged trials. Nothing here was tuned by hand.
        </>
      }
    >
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <ChartFrame
          title="NDCG@10 on TREC 2021"
          sub="Expert grades: eligible 2, excluded 1, not relevant 0."
          table={{ head: ["Method", "NDCG@10", "P@10 (eligible)", "MRR (eligible)"], rows: methods.map((m) => [m.name, m.ndcg.toFixed(3), m.p10.toFixed(3), m.mrr.toFixed(3)]) }}
        >
          <ResponsiveContainer width="100%" height={methods.length * 46 + 30}>
            <BarChart data={methods} layout="vertical" margin={{ left: 0, right: 44, top: 0, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke={c["viz-grid"]} />
              <XAxis type="number" domain={[0, "auto"]} tick={{ fill: c["ink-3"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={210} tick={{ fill: c["ink-2"], fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: c["viz-grid"], opacity: 0.5 }}
                content={({ active, payload }) => {
                  const m = payload?.[0]?.payload;
                  return active && m ? (
                    <TooltipBox title={m.name} rows={[{ label: "NDCG@10", value: m.ndcg.toFixed(3) }, { label: "P@10", value: m.p10.toFixed(3) }, { label: "MRR", value: m.mrr.toFixed(3) }]} />
                  ) : null;
                }}
              />
              <Bar
                dataKey="ndcg"
                barSize={16}
                isAnimationActive={false}
                shape={(props: any) => (
                  <rect x={props.x} y={props.y} width={Math.max(0, props.width)} height={props.height} rx={4} fill={props.payload.name === ours.name ? c["viz-b"] : c["viz-muted"]} />
                )}
              >
                <LabelList dataKey="ndcg" position="right" formatter={(v: any) => Number(v).toFixed(3)} style={{ fill: c["ink-2"], fontSize: 12 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>

        <div>
          <h3 className="font-semibold">Does the eligibility check tell “eligible” from “excluded”?</h3>
          <p className="mt-1 text-sm text-ink-2">
            Only the {e.pairs.toLocaleString()} pairs experts called relevant, so this isolates the rule check from topic matching.
          </p>
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-5">
            <div>
              <dt className="text-sm text-ink-3">AUC of eligibility score</dt>
              <dd className="text-2xl font-semibold tabular-nums">{e.auc_eligibility_score?.toFixed(2) ?? "—"}</dd>
              <dd className="text-xs text-ink-3">0.5 = chance</dd>
            </div>
            <div>
              <dt className="text-sm text-ink-3">Excluded share (base rate)</dt>
              <dd className="text-2xl font-semibold tabular-nums">{pct(e.base_rate_excluded)}</dd>
            </div>
            <div>
              <dt className="text-sm text-ink-3">“Probably not” flags that were truly excluded</dt>
              <dd className="text-2xl font-semibold tabular-nums">{pct(e.flag_precision)}</dd>
            </div>
            <div>
              <dt className="text-sm text-ink-3">Excluded pairs we flagged</dt>
              <dd className="text-2xl font-semibold tabular-nums">{pct(e.flag_recall)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-sm text-ink-2">
            <span aria-hidden className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: c["viz-b"] }} />
            The ranker used in the app, trained on synthetic patients plus these expert judgements.
          </p>
          <p className="mt-6 text-sm text-ink-2">
            Rows marked “5-fold CV” are scored on patients held out from training, so no model is graded on a case it learned
            from.{" "}
            {r.topics_without_condition_match > 0
              ? `${r.topics_without_condition_match} of ${r.topics} notes had no recognisable condition name and relied on text and meaning search alone.`
              : `A condition name was recognised in all ${r.topics} notes.`}
          </p>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------ explanations */

function ExplanationSection({ r }: { r: any }) {
  const rows: [string, string, boolean][] = [
    ["unsafe_rate", "Claims eligibility or advises enrolling", true],
    ["contradiction_rate", "Lists a conflict as a reason it fits", true],
    ["false_unknown_rate", "Calls something unclear that you answered", true],
    ["missed_conflict_rate", "Leaves out a detected conflict", true],
    ["reading_grade", "Reading grade (Flesch-Kincaid)", false],
  ];
  const fmt = (k: string, v: any) => (v == null ? "—" : k === "reading_grade" ? Number(v).toFixed(1) : pct(v));
  return (
    <Section
      id="explanations"
      title="Checking the AI explanations"
      when={r.generated_at}
      intro={
        <>
          Every “In plain language” summary is checked against the rule check it was written from. Problems are removed or
          filled in before you see them. These are the rates across {r.cases} test explanations, before and after that guardrail,
          with the automatic template as a baseline.
        </>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left">
          <thead>
            <tr className="border-b border-ink/30 text-sm">
              <th className="py-2 font-medium text-ink-2">Share of explanations that…</th>
              <th className="py-2 text-right font-medium text-ink-2">AI as written</th>
              <th className="py-2 text-right font-semibold">AI + guardrail</th>
              <th className="py-2 text-right font-medium text-ink-2">Template</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([k, label]) => (
              <tr key={k} className="border-b border-rule">
                <td className="py-3">{label}</td>
                <td className="py-3 text-right tabular-nums text-ink-2">{fmt(k, r.llm_raw?.[k])}</td>
                <td className="py-3 text-right text-lg font-semibold tabular-nums">{fmt(k, r.llm_guarded?.[k])}</td>
                <td className="py-3 text-right tabular-nums text-ink-2">{fmt(k, r.template?.[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 max-w-prose text-sm text-ink-3">
        Lower is better for every row. Small sample: the free model allows about 40 calls a day, so this set grows over time.
        Model: {r.model?.replace(/:free$/, "") ?? "—"}.
      </p>
    </Section>
  );
}
