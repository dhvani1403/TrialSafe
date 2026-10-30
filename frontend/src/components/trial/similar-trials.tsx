"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type SimilarTrial } from "@/lib/api";
import { phaseLabel, statusLabel } from "@/lib/format";

export function SimilarTrials({ id }: { id: string }) {
  const [rows, setRows] = useState<SimilarTrial[] | null>(null);
  useEffect(() => {
    api.similar(id).then(setRows).catch(() => setRows([]));
  }, [id]);
  if (!rows?.length) return null;
  return (
    <section className="mx-auto mt-20 max-w-6xl px-4 sm:px-6" aria-labelledby="similar-h">
      <h2 id="similar-h" className="text-xl font-semibold tracking-tight">
        Studies like this one
      </h2>
      <p className="mt-1 text-sm text-ink-2">Closest in meaning: condition, treatment and design.</p>
      <ul className="mt-6 grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => (
          <li key={r.nct_id} className="border-t border-rule py-4">
            <Link href={`/trials/${r.nct_id}`} className="group block">
              <span className="flex gap-3 text-xs text-ink-3">
                <span>{phaseLabel(r.phase)}</span>
                <span>{statusLabel(r.status)}</span>
              </span>
              <span className="mt-1 block font-medium leading-snug group-hover:underline group-hover:underline-offset-4">{r.title}</span>
              <span className="mt-1 block text-sm text-ink-2">{r.conditions.join(", ")}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
