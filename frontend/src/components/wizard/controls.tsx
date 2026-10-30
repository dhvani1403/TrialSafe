"use client";

import { Check } from "lucide-react";
import type { ReactNode } from "react";

export function Question({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="rise relative z-10">
      <h1 className="text-[1.9rem] font-semibold leading-tight tracking-[-0.02em] text-balance sm:text-[2.2rem]">
        {title}
      </h1>
      {hint && <p className="mt-3 max-w-prose text-ink-2">{hint}</p>}
      <div className="mt-8">{children}</div>
    </div>
  );
}

export function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
        selected ? "border-pine bg-pine text-on-pine" : "border-rule bg-surface text-ink hover:border-ink-3"
      }`}
    >
      {selected && <Check size={14} strokeWidth={2.5} aria-hidden />}
      {children}
    </button>
  );
}

/** Yes / No / skip, where skip means "unknown", never "no". */
export function TriState({
  label,
  value,
  onChange,
  yes = "Yes",
  no = "No",
}: {
  label: string;
  value: boolean | null | undefined;
  onChange: (v: boolean | null) => void;
  yes?: string;
  no?: string;
}) {
  const opts: { v: boolean | null; l: string }[] = [
    { v: true, l: yes },
    { v: false, l: no },
    { v: null, l: "Not sure" },
  ];
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <span aria-hidden className="font-medium">
        {label}
      </span>
      <div className="flex gap-1 rounded-lg bg-paper-2 p-1">
        {opts.map((o) => (
          <button
            key={String(o.v)}
            type="button"
            aria-pressed={(value ?? null) === o.v}
            onClick={() => onChange(o.v)}
            className="rounded-md px-3 py-1 text-sm text-ink-2 aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm"
          >
            {o.l}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChoiceCard({
  selected,
  onClick,
  title,
  detail,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  detail?: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onClick}
      className={`flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
        selected ? "border-pine bg-surface ring-1 ring-pine" : "border-rule bg-surface hover:border-ink-3"
      }`}
    >
      <span
        aria-hidden
        className={`mt-1 grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
          selected ? "border-pine" : "border-ink-3"
        }`}
      >
        {selected && <span className="h-2 w-2 rounded-full bg-pine" />}
      </span>
      <span>
        <span className="block font-medium">{title}</span>
        {detail && <span className="mt-0.5 block text-sm text-ink-2">{detail}</span>}
      </span>
    </button>
  );
}

export function MultiChips({
  options,
  value,
  onChange,
}: {
  options: { id: string; label: string }[];
  value: string[] | null | undefined;
  onChange: (v: string[] | null) => void;
}) {
  const sel = value ?? [];
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <Chip
          key={o.id}
          selected={sel.includes(o.id)}
          onClick={() => onChange(sel.includes(o.id) ? sel.filter((x) => x !== o.id) : [...sel, o.id])}
        >
          {o.label}
        </Chip>
      ))}
      <Chip selected={value != null && value.length === 0} onClick={() => onChange(value?.length === 0 ? null : [])}>
        None of these
      </Chip>
    </div>
  );
}
