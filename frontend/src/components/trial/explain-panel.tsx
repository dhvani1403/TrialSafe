"use client";

import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { api, type Explanation, type Profile } from "@/lib/api";

export function ExplainPanel({ id, profile }: { id: string; profile: Profile }) {
  const [e, setE] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setE(await api.explain(id, profile));
    } catch {
      setError("The explanation couldn't be generated. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-rule bg-surface p-5" aria-live="polite">
      <h2 className="flex items-center gap-2 font-semibold">
        <Sparkles size={17} className="text-pine" aria-hidden /> In plain language
      </h2>
      {!e && (
        <>
          <p className="mt-2 text-sm text-ink-2">A short summary of this study and how it lines up with what you told us.</p>
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-pine px-4 py-2.5 font-semibold text-on-pine hover:bg-pine-hover disabled:opacity-70"
          >
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden />}
            {busy ? "Writing your summary" : "Explain this study"}
          </button>
          {error && <p className="mt-3 text-sm text-ink-2">{error}</p>}
        </>
      )}
      {e && (
        <div className="mt-3 space-y-5 text-[0.95rem]">
          <p>{e.summary}</p>
          <List title="Why it may fit" items={e.why_it_may_fit} dot="var(--mark-ok)" />
          <List title="Things to check" items={e.things_to_check} dot="var(--mark-check)" />
          <List title="Questions for your doctor" items={e.questions_for_your_doctor} dot="var(--rule)" />
          <p className="border-t border-rule pt-3 text-xs text-ink-3">
            {e.source === "llm"
              ? `Written by an AI model${e.model ? ` (${e.model.replace(/:free$/, "")})` : ""} from the study listing and our rule check. It can make mistakes.`
              : e.note ?? "Automatic summary from our rule check."}
          </p>
        </div>
      )}
    </section>
  );
}

function List({ title, items, dot }: { title: string; items: string[]; dot: string }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-1.5 space-y-1.5">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: dot }} />
            <span className="text-ink-2">{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
