import Link from "next/link";
import { FinePrintDemo } from "@/components/fine-print-demo";
import { LiveStats, AccessGap } from "@/components/home-live";

export default function Home() {
  return (
    <>
      <section className="mx-auto grid max-w-6xl gap-12 px-4 pb-16 pt-12 sm:px-6 md:pt-20 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <div className="flex flex-col justify-center">
          <h1 className="text-[2.6rem] font-semibold leading-[1.05] tracking-[-0.025em] text-balance sm:text-5xl">
            Clinical trial fine print, read line by line for you.
          </h1>
          <p className="mt-6 max-w-[34rem] text-lg leading-relaxed text-ink-2">
            Tell us a little about your health. We check every eligibility rule of open studies near you and show,
            in plain words, which ones you meet, which ones conflict, and what to ask your doctor.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link
              href="/match"
              className="rounded-lg bg-pine px-5 py-3 text-base font-semibold text-on-pine shadow-sm hover:bg-pine-hover"
            >
              Find trials for me
            </Link>
            <span className="text-sm text-ink-2">About 2 minutes. Nothing is saved.</span>
          </div>
          <LiveStats />
        </div>
        <FinePrintDemo />
      </section>

      <section className="border-y border-rule bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">What happens when you search</h2>
          <ol className="mt-10 grid gap-10 md:grid-cols-3">
            {[
              {
                t: "Find studies about your condition",
                d: "We search 2,600+ open US studies by keyword and by meaning, so “heart attack” also finds “myocardial infarction”.",
              },
              {
                t: "Read every eligibility rule",
                d: "Each rule is turned into a checkable statement, like “excludes HIV” or “activity level 0–1”, then compared with what you told us.",
              },
              {
                t: "Rank and explain",
                d: "A ranking model, tested on 75 real patient cases judged by experts, orders the studies. Every match lists its reasons, and its conflicts.",
              },
            ].map((s, i) => (
              <li key={s.t} className="relative pl-12">
                <span
                  aria-hidden
                  className="absolute left-0 top-0 grid h-8 w-8 place-items-center rounded-full border border-ink/25 text-sm font-semibold tabular-nums"
                >
                  {i + 1}
                </span>
                <h3 className="font-semibold">{s.t}</h3>
                <p className="mt-2 text-ink-2">{s.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <AccessGap />
    </>
  );
}
