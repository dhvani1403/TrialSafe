"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Health } from "@/lib/api";
import { shortDate } from "@/lib/format";

export function LiveStats() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    api.health().then(setH).catch(() => {});
  }, []);
  return (
    <p className="mt-10 min-h-[1.5em] border-t border-rule pt-5 text-sm text-ink-2">
      {h ? (
        <>
          <strong className="font-semibold text-ink tabular-nums">{h.trials.toLocaleString()}</strong> open studies at{" "}
          <strong className="font-semibold text-ink tabular-nums">{h.sites.toLocaleString()}</strong> sites, pulled
          from ClinicalTrials.gov{h.last_ingest ? `, last refreshed ${shortDate(h.last_ingest)}` : ""}.
        </>
      ) : (
        "Open studies from ClinicalTrials.gov, refreshed daily."
      )}
    </p>
  );
}

type Row = { group: string; mean_matches: number; ratio: number };

export function AccessGap() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [radius, setRadius] = useState(100);
  useEffect(() => {
    api
      .insights()
      .then((d) => {
        const f = d.reports?.fairness;
        if (f?.by_setting) {
          const order = ["urban", "small city", "rural"];
          setRows([...f.by_setting].sort((a: Row, b: Row) => order.indexOf(a.group) - order.indexOf(b.group)));
          setRadius(f.params?.radius_mi ?? 100);
        }
      })
      .catch(() => {});
  }, []);
  if (!rows) return null;
  const max = Math.max(...rows.map((r) => r.mean_matches));
  const names: Record<string, string> = { urban: "Large cities", "small city": "Small cities", rural: "Rural towns" };
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <div className="grid gap-10 md:grid-cols-[0.9fr_1.1fr] md:items-center">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-balance">
            Where you live changes how many trials you can reach.
          </h2>
          <p className="mt-4 max-w-prose text-ink-2">
            We ran the same searches for 10 common conditions from 19 US towns and cities. This is the average number
            of matching studies with a site within {radius} miles.
          </p>
          <Link href="/insights#fairness" className="mt-5 inline-block font-medium text-pine underline underline-offset-4">
            See the full fairness audit
          </Link>
        </div>
        <dl className="space-y-5">
          {rows.map((r) => (
            <div key={r.group}>
              <div className="flex items-baseline justify-between text-sm">
                <dt className="font-medium">{names[r.group] ?? r.group}</dt>
                <dd className="tabular-nums text-ink-2">
                  <span className="text-lg font-semibold text-ink">{r.mean_matches.toFixed(1)}</span> studies
                </dd>
              </div>
              <div className="mt-1.5 h-3 rounded-full bg-paper-2">
                <div
                  className="h-3 rounded-full bg-pine"
                  style={{ width: `${Math.max(2, (100 * r.mean_matches) / max)}%` }}
                />
              </div>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
