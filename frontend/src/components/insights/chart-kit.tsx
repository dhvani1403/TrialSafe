"use client";

import { useEffect, useState, type ReactNode } from "react";

const VARS = ["viz-a", "viz-b", "viz-muted", "viz-grid", "viz-flag", "ink", "ink-2", "ink-3", "surface", "rule"] as const;
export type VizColors = Record<(typeof VARS)[number], string>;

/** Recharts writes colors as SVG attributes, where CSS variables aren't reliable, so resolve them. */
export function useVizColors(): VizColors | null {
  const [c, setC] = useState<VizColors | null>(null);
  useEffect(() => {
    const read = () => {
      const s = getComputedStyle(document.documentElement);
      setC(Object.fromEntries(VARS.map((v) => [v, s.getPropertyValue(`--${v}`).trim()])) as VizColors);
    };
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);
  return c;
}

export function ChartFrame({
  title,
  sub,
  legend,
  table,
  children,
}: {
  title: string;
  sub?: string;
  legend?: { label: string; color: string }[];
  table?: { head: string[]; rows: (string | number)[][] };
  children: ReactNode;
}) {
  return (
    <figure className="min-w-0">
      <figcaption>
        <h3 className="font-semibold">{title}</h3>
        {sub && <p className="mt-0.5 text-sm text-ink-2">{sub}</p>}
        {legend && (
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
            {legend.map((l) => (
              <li key={l.label} className="inline-flex items-center gap-1.5">
                <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>
        )}
      </figcaption>
      <div className="mt-4">{children}</div>
      {table && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-ink-3 hover:text-ink">View as table</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left tabular-nums">
              <thead>
                <tr className="border-b border-rule text-ink-2">
                  {table.head.map((h) => (
                    <th key={h} className="py-1.5 pr-4 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i} className="border-b border-rule/60">
                    {r.map((v, j) => (
                      <td key={j} className="py-1.5 pr-4">
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}

export function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-md border border-rule bg-surface px-3 py-2 text-sm shadow-lg">
      <p className="font-semibold">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="mt-0.5 flex items-center gap-2 text-ink-2">
          {r.color && <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: r.color }} />}
          <span>{r.label}</span>
          <span className="ml-auto pl-3 font-semibold tabular-nums text-ink">{r.value}</span>
        </p>
      ))}
    </div>
  );
}
