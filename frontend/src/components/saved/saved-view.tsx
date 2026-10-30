"use client";

import { Printer, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type TrialDetail } from "@/lib/api";
import { ageRange, miles, phaseLabel, statusCopy, statusLabel, verdictCopy } from "@/lib/format";
import { useProfile } from "@/lib/profile";
import { removeSaved, useSaved } from "@/lib/shortlist";

const QUESTIONS = [
  "Is any of these studies a reasonable option alongside my current care?",
  "Are there tests or records the study team would need from me?",
  "How often would I need to visit, and is travel covered?",
  "What happens to my current treatment if I join?",
];

export function SavedView() {
  const saved = useSaved();
  const profile = useProfile();
  const [details, setDetails] = useState<Record<string, TrialDetail>>({});
  const key = saved.map((s) => s.nct_id).join(",") + JSON.stringify(profile ?? null);

  useEffect(() => {
    if (profile === undefined) return;
    let live = true;
    saved.forEach((s) =>
      api
        .trial(s.nct_id, profile)
        .then((d) => live && setDetails((prev) => ({ ...prev, [s.nct_id]: d })))
        .catch(() => {}),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!saved.length) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="text-xl font-semibold">No saved studies yet</h1>
        <p className="mt-2 text-ink-2">Use the bookmark on any study to keep it here and print a summary for your doctor.</p>
        <Link href={profile ? "/results" : "/match"} className="mt-6 inline-block rounded-lg bg-pine px-5 py-2.5 font-semibold text-on-pine">
          {profile ? "Back to your matches" : "Find trials"}
        </Link>
      </div>
    );
  }

  const today = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  return (
    <div className="mx-auto max-w-4xl px-4 pb-24 pt-10 sm:px-6 print:max-w-none print:p-0">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-6">
        <div>
          <p className="text-sm text-ink-2 print:text-black">Prepared {today} with TrialMatch</p>
          <h1 className="mt-1 text-[2rem] font-semibold leading-tight tracking-[-0.02em]">Studies to discuss with my doctor</h1>
          {profile && (
            <p className="mt-2 text-ink-2">
              {profile.age}-year-old {profile.sex === "female" ? "woman" : "man"} with {profile.conditions.join(", ") || "no listed condition"}
              {profile.location ? `, near ${profile.location.label}` : ""}.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex items-center gap-2 rounded-lg bg-pine px-4 py-2.5 font-semibold text-on-pine hover:bg-pine-hover print:hidden"
        >
          <Printer size={17} aria-hidden /> Print or save as PDF
        </button>
      </header>

      <ol className="divide-y divide-rule">
        {saved.map((s, i) => {
          const d = details[s.nct_id];
          const attention = (d?.criteria ?? []).filter((c) => c.status === "not_met" || c.status === "caution" || c.status === "unknown");
          const site = d?.nearest_site ?? d?.sites?.[0];
          return (
            <li key={s.nct_id} className="break-inside-avoid py-8">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="flex flex-wrap gap-x-3 text-sm text-ink-3">
                    <span>
                      {i + 1}. {s.nct_id}
                    </span>
                    {d && <span>{phaseLabel(d.phase)}</span>}
                    {d && <span>{statusLabel(d.status)}</span>}
                  </p>
                  <h2 className="mt-1 text-lg font-semibold leading-snug">
                    <Link href={`/trials/${s.nct_id}`} className="hover:underline">
                      {s.title}
                    </Link>
                  </h2>
                  {d && <p className="text-sm text-ink-2">Run by {d.sponsor}. Ages {ageRange(d.min_age_years, d.max_age_years)}.</p>}
                </div>
                <button
                  type="button"
                  onClick={() => removeSaved(s.nct_id)}
                  aria-label={`Remove ${s.title}`}
                  className="rounded-md p-2 text-ink-3 hover:bg-paper-2 hover:text-ink print:hidden"
                >
                  <Trash2 size={17} aria-hidden />
                </button>
              </div>

              {!d && <p className="mt-3 text-sm text-ink-3">Loading…</p>}
              {d && (
                <div className="mt-4 grid gap-6 md:grid-cols-[1fr_16rem]">
                  <div>
                    {d.verdict && (
                      <p>
                        <span className={`mark ${verdictCopy[d.verdict].mark} font-semibold`}>{verdictCopy[d.verdict].label}</span>{" "}
                        <span className="text-ink-2">{verdictCopy[d.verdict].hint}</span>
                      </p>
                    )}
                    {attention.length > 0 && (
                      <>
                        <h3 className="mt-4 text-sm font-semibold">To check with the study team</h3>
                        <ul className="mt-1.5 space-y-1 text-sm">
                          {attention.slice(0, 6).map((c, j) => (
                            <li key={j} className="flex gap-2">
                              <span aria-hidden className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: `var(--${statusCopy[c.status].mark})` }} />
                              <span>
                                <span className="font-medium">{statusCopy[c.status].label}:</span> {c.reason}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                  <div className="text-sm">
                    <h3 className="font-semibold">Nearest site</h3>
                    {site ? (
                      <p className="mt-1 text-ink-2">
                        {site.facility}
                        <br />
                        {[site.city, site.state].filter(Boolean).join(", ")}
                        {site.distance_mi != null && <> ({miles(site.distance_mi)})</>}
                      </p>
                    ) : (
                      <p className="mt-1 text-ink-3">Not listed</p>
                    )}
                    {(d.central_contact?.phone || d.central_contact?.email) && (
                      <p className="mt-2 text-ink-2">
                        {d.central_contact.phone}
                        {d.central_contact.phone && d.central_contact.email && <br />}
                        {d.central_contact.email}
                      </p>
                    )}
                    <p className="mt-2 break-all text-ink-3">clinicaltrials.gov/study/{s.nct_id}</p>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <section className="break-inside-avoid border-t border-rule pt-8">
        <h2 className="text-lg font-semibold">Questions to ask</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-ink-2">
          {QUESTIONS.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
        <p className="mt-8 text-sm text-ink-3">
          This summary was generated automatically from public ClinicalTrials.gov listings and is not medical advice. Eligibility
          can only be confirmed by each study team.
        </p>
      </section>
    </div>
  );
}
