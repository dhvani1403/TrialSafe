"use client";

import { ArrowLeft, ExternalLink, Mail, Phone } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type TrialDetail } from "@/lib/api";
import { ageRange, miles, phaseLabel, sexLabel, shortDate, statusLabel, verdictCopy } from "@/lib/format";
import { useProfile } from "@/lib/profile";
import { TrialMap, type MapPoint } from "@/components/map-loader";
import { SaveButton } from "@/components/save-button";
import { RuleTally, VerdictLabel } from "@/components/verdict";
import { AnnotatedCriteria } from "./annotated-criteria";
import { ExplainPanel } from "./explain-panel";
import { SimilarTrials } from "./similar-trials";

export function TrialView({ id }: { id: string }) {
  const profile = useProfile();
  const [t, setT] = useState<TrialDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (profile === undefined) return;
    api
      .trial(id, profile)
      .then(setT)
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? "We don't have this study. It may have closed or been removed." : "The study couldn't be loaded. Check that the API is running."));
  }, [id, profile]);

  useEffect(load, [load]);
  useEffect(() => {
    if (t) document.title = `${t.title} · TrialMatch`;
  }, [t]);

  const sitePoints: MapPoint[] = useMemo(
    () =>
      (t?.sites ?? [])
        .filter((s) => s.lat != null && s.lon != null)
        .slice(0, 150)
        .map((s, i) => ({
          id: `${i}`,
          lat: s.lat!,
          lon: s.lon!,
          title: s.facility ?? "Study site",
          subtitle: [s.city, s.state].filter(Boolean).join(", ") + (s.distance_mi != null ? ` (${miles(s.distance_mi)})` : ""),
        })),
    [t],
  );

  if (error) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="text-xl font-semibold">{error}</h1>
        <Link href="/results" className="mt-6 inline-block font-medium text-pine underline underline-offset-4">
          Back to your matches
        </Link>
      </div>
    );
  }
  if (!t) return <div className="mx-auto max-w-6xl px-6 py-16 text-ink-2" aria-live="polite">Loading study…</div>;

  const nearbySites = t.sites.filter((s) => s.distance_mi == null || !profile || s.distance_mi <= Math.max(profile.max_distance_mi, 50)).slice(0, 5);
  const facts: [string, string][] = [
    ["Ages", ageRange(t.min_age_years, t.max_age_years)],
    ["Sex", sexLabel(t.sex)],
    ["Healthy volunteers", t.healthy_volunteers ? "Accepted" : "Not accepted"],
    ["Phase", phaseLabel(t.phase)],
    ["Enrollment", t.enrollment ? `${t.enrollment.toLocaleString()} people` : "—"],
    ["Updated", shortDate(t.last_update)],
  ];

  return (
    <article className="pb-24">
      <header className="border-b border-rule bg-surface">
        <div className="mx-auto max-w-6xl px-4 pb-10 pt-6 sm:px-6">
          <Link href={profile ? "/results" : "/"} className="inline-flex items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
            <ArrowLeft size={15} aria-hidden /> {profile ? "Your matches" : "Home"}
          </Link>
          <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
            <span>{statusLabel(t.status)}</span>
            <span>{phaseLabel(t.phase)}</span>
            <a href={t.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink">
              {t.nct_id} on ClinicalTrials.gov <ExternalLink size={13} aria-hidden />
            </a>
          </div>
          <h1 className="mt-3 max-w-4xl text-[1.85rem] font-semibold leading-[1.15] tracking-[-0.02em] text-balance sm:text-[2.3rem]">
            {t.title}
          </h1>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-ink-2">Run by {t.sponsor}</p>
            <SaveButton id={t.nct_id} title={t.title} />
          </div>

          {t.verdict && t.counts && (
            <div className="mt-8 flex flex-col gap-3 rounded-xl border border-rule bg-paper px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-lg">
                <VerdictLabel verdict={t.verdict} />
                <span className="ml-2 text-ink-2">{verdictCopy[t.verdict].hint}</span>
              </p>
              <RuleTally counts={t.counts} />
            </div>
          )}
          {!profile && (
            <p className="mt-8 rounded-xl border border-rule bg-paper px-5 py-4">
              <Link href="/match" className="font-semibold text-pine underline underline-offset-4">
                Add your health profile
              </Link>{" "}
              to see which of these rules you meet.
            </p>
          )}
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-12 px-4 pt-10 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          {t.summary && (
            <section>
              <h2 className="text-xl font-semibold tracking-tight">What the study is testing</h2>
              <p className="doc mt-3 max-w-[68ch] text-ink-2">{t.summary}</p>
              {t.interventions.length > 0 && (
                <ul className="mt-4 flex flex-wrap gap-2">
                  {t.interventions.slice(0, 6).map((iv) => (
                    <li key={iv.name} className="rounded-full border border-rule px-3 py-1 text-sm">
                      {iv.name}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-rule py-5 sm:grid-cols-3">
            {facts.map(([k, v]) => (
              <div key={k}>
                <dt className="text-sm text-ink-3">{k}</dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>

          {t.structured_fails && t.structured_fails.length > 0 && (
            <p className="mt-8 rounded-lg bg-mark-no/50 px-4 py-3">
              <strong className="font-semibold">Not open to you:</strong> {t.structured_fails.map((f) => f.reason).join(" ")}
            </p>
          )}

          <AnnotatedCriteria trial={t} hasProfile={!!profile} onUpgraded={load} />
        </div>

        <aside className="space-y-10 lg:sticky lg:top-20 lg:self-start">
          {profile && <ExplainPanel id={t.nct_id} profile={profile} />}

          <section>
            <h2 className="font-semibold">Where it runs</h2>
            <p className="mt-1 text-sm text-ink-2">
              {t.total_sites === 1 ? "1 site" : `${t.total_sites.toLocaleString()} sites`}
              {t.nearest_site?.distance_mi != null && <>, nearest is {miles(t.nearest_site.distance_mi)} away</>}
            </p>
            {sitePoints.length > 0 && (
              <div className="mt-3 h-56 overflow-hidden rounded-xl border border-rule">
                <TrialMap points={sitePoints} home={profile?.location} />
              </div>
            )}
            <ul className="mt-4 divide-y divide-rule text-sm">
              {nearbySites.map((s, i) => (
                <li key={i} className="py-3">
                  <div className="flex justify-between gap-3">
                    <span className="font-medium">{s.facility ?? "Study site"}</span>
                    {s.distance_mi != null && <span className="shrink-0 tabular-nums text-ink-2">{miles(s.distance_mi)}</span>}
                  </div>
                  <div className="text-ink-2">{[s.city, s.state].filter(Boolean).join(", ")}</div>
                  <Contact c={s.contact} />
                </li>
              ))}
            </ul>
          </section>

          {t.central_contact && (t.central_contact.phone || t.central_contact.email) && (
            <section>
              <h2 className="font-semibold">Study contact</h2>
              <p className="mt-1 text-sm">{t.central_contact.name}</p>
              <Contact c={t.central_contact} />
            </section>
          )}
        </aside>
      </div>

      <SimilarTrials id={t.nct_id} />
    </article>
  );
}

function Contact({ c }: { c: { phone?: string; email?: string } | null }) {
  if (!c || (!c.phone && !c.email)) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
      {c.phone && (
        <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 text-pine hover:underline">
          <Phone size={13} aria-hidden /> {c.phone}
        </a>
      )}
      {c.email && (
        <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1 break-all text-pine hover:underline">
          <Mail size={13} aria-hidden /> {c.email}
        </a>
      )}
    </div>
  );
}
