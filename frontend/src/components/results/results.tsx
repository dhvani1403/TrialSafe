"use client";

import { Loader2, MapPin, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type MatchResponse, type MatchResult, type Verdict } from "@/lib/api";
import { miles, phaseLabel, plural } from "@/lib/format";
import { saveProfile, useProfile } from "@/lib/profile";
import { TrialMap, type MapPoint } from "@/components/map-loader";
import { ResultRow } from "./result-row";

type Filter = "all" | Verdict;
type Sort = "match" | "distance" | "recent";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "likely_eligible", label: "Looks like a fit" },
  { id: "possible", label: "Worth asking" },
  { id: "likely_ineligible", label: "Probably not" },
];

export function Results() {
  const profile = useProfile();
  // results are keyed by the profile they were computed for, so a profile change shows loading state
  const key = profile ? JSON.stringify(profile) : "";
  const [res, setRes] = useState<{ key: string; data?: MatchResponse; error?: string }>({ key: "" });
  const data = res.key === key ? res.data ?? null : null;
  const error = res.key === key ? res.error ?? null : null;
  const [filter, setFilter] = useState<Filter>("all");
  const [phase, setPhase] = useState("any");
  const [sort, setSort] = useState<Sort>("match");
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    let live = true;
    api
      .match(profile)
      .then((d) => live && setRes({ key, data: d }))
      .catch((e) =>
        live &&
        setRes({ key, error: e instanceof ApiError ? e.message : "The matching service isn't responding. Check that the API is running." }),
      );
    return () => {
      live = false;
    };
  }, [profile, key]);

  const shown = useMemo(() => {
    if (!data) return [];
    let rows = data.results.filter((r) => filter === "all" || r.verdict === filter);
    if (phase !== "any") rows = rows.filter((r) => r.phase.includes(phase));
    if (sort === "distance") rows = [...rows].sort((a, b) => (a.nearest_site?.distance_mi ?? 1e9) - (b.nearest_site?.distance_mi ?? 1e9));
    if (sort === "recent") rows = [...rows].sort((a, b) => (b.last_update ?? "").localeCompare(a.last_update ?? ""));
    return rows;
  }, [data, filter, phase, sort]);

  const points: MapPoint[] = useMemo(
    () =>
      shown
        .filter((r) => r.nearest_site)
        .map((r) => ({
          id: r.nct_id,
          lat: r.nearest_site!.lat,
          lon: r.nearest_site!.lon,
          title: r.title,
          subtitle: [r.nearest_site!.facility, r.nearest_site!.city].filter(Boolean).join(", ") + ` (${miles(r.nearest_site!.distance_mi)})`,
          href: `/trials/${r.nct_id}`,
        })),
    [shown],
  );

  if (profile === undefined) return null;
  if (profile === null) {
    return (
      <Empty title="Start with a short health profile" body="We need a condition, your age and sex to find studies you could join.">
        <Link href="/match" className="rounded-lg bg-pine px-5 py-2.5 font-semibold text-on-pine hover:bg-pine-hover">
          Create profile
        </Link>
      </Empty>
    );
  }

  const where = profile.location ? `within ${profile.max_distance_mi} mi of ${profile.location.label}` : "across the US";
  const what = [...profile.conditions, ...(profile.healthy_volunteer ? ["healthy volunteers"] : [])].join(", ");

  return (
    <div className="mx-auto grid max-w-[90rem] lg:grid-cols-[minmax(0,1fr)_minmax(22rem,0.8fr)]">
      <section className="min-w-0 px-4 pb-20 pt-8 sm:px-6 lg:pl-8 lg:pr-10">
        <header>
          <p className="text-sm text-ink-2">
            For a {profile.age}-year-old {profile.sex === "female" ? "woman" : "man"}.{" "}
            <Link href="/match" className="underline underline-offset-4 hover:text-ink">
              Edit profile
            </Link>
          </p>
          <h1 className="mt-2 text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-balance sm:text-[2rem]">
            {data ? (
              <>
                {plural(data.total, "open study", "open studies")} for {what} {where}
              </>
            ) : (
              <>Reading studies for {what}…</>
            )}
          </h1>
          {data && <HiddenNote data={data} radius={profile.max_distance_mi} onWiden={() => saveProfile({ ...profile, max_distance_mi: Math.min(500, profile.max_distance_mi * 2) })} hasLocation={!!profile.location} />}
        </header>

        {data && data.total > 0 && (
          <div className="mt-6 flex flex-wrap items-center gap-3 border-y border-rule py-3">
            <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by fit">
              {FILTERS.map((f) => {
                const n = f.id === "all" ? data.results.length : data.results.filter((r) => r.verdict === f.id).length;
                return (
                  <button
                    key={f.id}
                    type="button"
                    aria-pressed={filter === f.id}
                    onClick={() => setFilter(f.id)}
                    className="rounded-full px-3 py-1 text-sm text-ink-2 hover:text-ink aria-pressed:bg-ink aria-pressed:text-paper"
                  >
                    {f.label} <span className="tabular-nums opacity-70">{n}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex w-full min-w-0 items-center gap-2 text-sm sm:ml-auto sm:w-auto">
              <SlidersHorizontal size={16} className="shrink-0 text-ink-3" aria-hidden />
              <select value={phase} onChange={(e) => setPhase(e.target.value)} aria-label="Phase" className="min-w-0 flex-1 rounded-md border border-rule bg-surface px-2 py-1 sm:flex-none">
                <option value="any">Any phase</option>
                {["PHASE1", "PHASE2", "PHASE3", "PHASE4"].map((p) => (
                  <option key={p} value={p}>
                    {phaseLabel(p)}
                  </option>
                ))}
                <option value="NA">No phase (observational)</option>
              </select>
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort" className="min-w-0 flex-1 rounded-md border border-rule bg-surface px-2 py-1 sm:flex-none">
                <option value="match">Best match</option>
                {profile.location && <option value="distance">Nearest</option>}
                <option value="recent">Recently updated</option>
              </select>
            </div>
          </div>
        )}

        {data && points.length > 0 && (
          <details className="mt-4 overflow-hidden rounded-xl border border-rule lg:hidden">
            <summary className="flex cursor-pointer items-center gap-2 px-4 py-2.5 text-sm font-medium">
              <MapPin size={15} aria-hidden /> Show map of nearest sites
            </summary>
            <div className="h-72 border-t border-rule">
              <TrialMap points={points} home={profile.location} activeId={active} />
            </div>
          </details>
        )}

        {error && (
          <Empty title="We couldn't load matches" body={error}>
            <button onClick={() => window.location.reload()} className="rounded-lg border border-rule bg-surface px-4 py-2 font-medium">
              Try again
            </button>
          </Empty>
        )}
        {!data && !error && <LoadingRows />}
        {data && shown.length === 0 && !error && (
          <Empty
            title={data.total === 0 ? "No open studies matched" : "Nothing under this filter"}
            body={
              data.total === 0
                ? "Try a broader condition name, a larger travel distance, or remove the location."
                : "Choose “All” to see every match."
            }
          >
            {data.total === 0 && (
              <Link href="/match" className="rounded-lg bg-pine px-4 py-2 font-semibold text-on-pine">
                Edit profile
              </Link>
            )}
          </Empty>
        )}

        <ol className="divide-y divide-rule">
          {shown.map((r: MatchResult, i) => (
            <ResultRow key={r.nct_id} r={r} rank={i + 1} active={active === r.nct_id} onHover={setActive} />
          ))}
        </ol>

        {data && data.total > 0 && (
          <p className="mt-8 text-sm text-ink-3">
            Ranked by {data.ranking_method === "gbdt" ? "a learned ranking model" : "a transparent scoring formula"} from{" "}
            {data.candidates_considered} candidate studies.{" "}
            <Link href="/insights#ranking" className="underline underline-offset-4">
              How well does it rank?
            </Link>
          </p>
        )}
      </section>

      <aside className="hidden border-l border-rule lg:block" aria-label="Map of nearest study sites">
        <div className="sticky top-14 h-[calc(100dvh-3.5rem)]">
          <TrialMap points={points} home={profile.location} activeId={active} onSelect={(id) => {
            setActive(id);
            document.getElementById(`r-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          }} />
          {profile.location && (
            <div className="pointer-events-none absolute bottom-4 left-4 z-[500] flex items-center gap-2 rounded-md bg-surface/95 px-3 py-1.5 text-xs shadow">
              <MapPin size={14} aria-hidden /> Nearest site for each study
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function HiddenNote({ data, radius, onWiden, hasLocation }: { data: MatchResponse; radius: number; onWiden: () => void; hasLocation: boolean }) {
  const parts: string[] = [];
  if (data.hidden.distance) parts.push(`${data.hidden.distance} farther than ${radius} mi`);
  if (data.hidden.age) parts.push(`${data.hidden.age} outside your age range`);
  if (data.hidden.sex) parts.push(`${data.hidden.sex} for the other sex only`);
  if (data.hidden.healthy_volunteers) parts.push(`${data.hidden.healthy_volunteers} not taking healthy volunteers`);
  if (!parts.length) return null;
  return (
    <p className="mt-3 max-w-prose text-ink-2">
      We left out {parts.join(", ")}.{" "}
      {hasLocation && data.hidden.distance > 0 && radius < 500 && (
        <button onClick={onWiden} className="font-medium text-pine underline underline-offset-4">
          Search up to {Math.min(500, radius * 2)} mi
        </button>
      )}
    </p>
  );
}

function LoadingRows() {
  return (
    <div className="mt-6" aria-live="polite">
      <p className="flex items-center gap-2 text-sm text-ink-2">
        <Loader2 size={16} className="animate-spin" aria-hidden /> Checking eligibility rules against your profile
      </p>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex gap-4 border-b border-rule py-6">
          <div className="h-12 w-12 animate-pulse rounded-full bg-paper-2" />
          <div className="flex-1 space-y-3">
            <div className="h-4 w-3/4 animate-pulse rounded bg-paper-2" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-paper-2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function Empty({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) {
  return (
    <div className="mx-auto my-16 max-w-md text-center">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-2 text-ink-2">{body}</p>
      <div className="mt-6 flex justify-center">{children}</div>
    </div>
  );
}
