import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "How it works" };

const STAGES = [
  {
    t: "Collect",
    d: "A scheduled worker pulls open, US-based studies for 26 conditions from the ClinicalTrials.gov API and stores them in Postgres, with each site’s coordinates.",
  },
  {
    t: "Read",
    d: "Each study’s eligibility text is split into lines. A rule-based reader tags every line with concepts from a shared list of about 40 (age, activity level, pregnancy, HIV, prior chemotherapy, HbA1c and so on), including direction and numbers. A free AI model re-reads the busiest studies with the same list, and its output replaces the rules where available.",
  },
  {
    t: "Retrieve",
    d: "Your condition is matched two ways: keyword search in Postgres, and meaning search with vector embeddings in pgvector. The two lists are merged with reciprocal rank fusion.",
  },
  {
    t: "Check",
    d: "Every rule is compared with your answers and marked met, conflicts, check, not answered, or study team checks. The registry’s official age and sex limits are applied exactly. Unanswered questions are never treated as “no”.",
  },
  {
    t: "Rank",
    d: "A gradient-boosted model scores each study from 23 signals: condition fit, eligibility results, distance and number of nearby sites, phase, recency and more. It learns from synthetic patients built from real trials and from 75 real patient cases judged by experts in the TREC 2021 Clinical Trials track.",
  },
  {
    t: "Explain",
    d: "On a study page you can ask for a plain-language summary. It is written by an AI model from the listing and the rule check, then checked against that rule check: claims of eligibility, contradictions, and answers wrongly called “unclear” are removed, and any conflict it left out is added back. It is labeled as AI-written.",
  },
];

export default function About() {
  return (
    <div className="mx-auto max-w-3xl px-4 pb-24 pt-12 sm:px-6">
      <h1 className="text-[2rem] font-semibold leading-tight tracking-[-0.02em] sm:text-[2.4rem]">How TrialMatch works</h1>
      <p className="mt-4 text-lg text-ink-2">
        TrialMatch turns the free-text eligibility rules of clinical trials into checks you can see. It is a research prototype,
        not a medical service.
      </p>

      <ol className="mt-12 space-y-8 border-l border-rule pl-8">
        {STAGES.map((s, i) => (
          <li key={s.t} className="relative">
            <span aria-hidden className="absolute -left-[2.6rem] grid h-6 w-6 place-items-center rounded-full bg-paper text-xs font-semibold ring-1 ring-ink/30">
              {i + 1}
            </span>
            <h2 className="font-semibold">{s.t}</h2>
            <p className="mt-1 text-ink-2">{s.d}</p>
          </li>
        ))}
      </ol>

      <section className="mt-16">
        <h2 className="text-xl font-semibold">Your privacy</h2>
        <p className="mt-3 text-ink-2">
          Your profile is kept in this browser tab only and is sent to our server just to run each search. We don’t store it, and
          we don’t log it. Cached AI explanations are keyed by a one-way hash and never include your location.
        </p>
      </section>

      <section className="mt-12">
        <h2 className="text-xl font-semibold">What it can get wrong</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-ink-2">
          <li>Readers miss or misread rules, especially exceptions (“unless…”) and rules that apply to only one group in the study.</li>
          <li>Many rules, like lab values, can only be checked by the study team. We mark those instead of guessing.</li>
          <li>Listings can be out of date. A study marked recruiting may have closed at a site.</li>
          <li>The ranking model learned from synthetic patients, not real enrollment outcomes.</li>
        </ul>
        <p className="mt-4 text-ink-2">
          We measure these errors openly on the{" "}
          <Link href="/insights" className="font-medium text-pine underline underline-offset-4">
            accuracy and fairness page
          </Link>
          .
        </p>
      </section>

      <section className="mt-12">
        <h2 className="text-xl font-semibold">How it is measured</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-ink-2">
          <li>Rule reading: a hand-labelled set of criterion lines, scored for precision, recall and operator accuracy.</li>
          <li>Ranking: synthetic patients, plus the TREC 2021 benchmark of real patient notes with expert eligibility judgements.</li>
          <li>Explanations: every AI summary audited for unsafe claims, contradictions and missed conflicts.</li>
          <li>Fairness: how many studies people can reach by age, sex, region and how rural they live.</li>
        </ul>
        <p className="mt-4 text-ink-2">
          The labelled set was drafted by an AI assistant and is being reviewed by people in the{" "}
          <Link href="/annotate" className="font-medium text-pine underline underline-offset-4">
            gold standard review tool
          </Link>
          .
        </p>
      </section>

      <section className="mt-12 rounded-xl border border-rule bg-surface p-6">
        <h2 className="font-semibold">Not medical advice</h2>
        <p className="mt-2 text-ink-2">
          Nothing here says you are eligible for a study or that a study is right for you. Use it to prepare questions for your doctor
          and for the study team, who make the final decision.
        </p>
      </section>
    </div>
  );
}
