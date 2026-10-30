// A real excerpt (NCT07631325) read against a sample patient, as the app does it.
const LINES: { kind: "Inclusion" | "Exclusion"; text: string; mark: string; note: string }[] = [
  {
    kind: "Inclusion",
    text: "Histologically confirmed, unresectable or metastatic cutaneous melanoma with documented PD-1-refractory disease.",
    mark: "mark-ok",
    note: "Melanoma that kept growing on anti-PD-1 treatment. Matches what you entered.",
  },
  {
    kind: "Inclusion",
    text: "Eastern Cooperative Oncology Group (ECOG) Performance Scale (PS) 0–2.",
    mark: "mark-ok",
    note: "Daily activity level 0 to 2. Yours is 1.",
  },
  {
    kind: "Exclusion",
    text: "Known HIV or active Hepatitis B or C.",
    mark: "mark-ok",
    note: "Rules out HIV and hepatitis. You reported neither.",
  },
  {
    kind: "Exclusion",
    text: "Prior malignancy within 2 years that in the investigator’s opinion would be likely to affect the outcomes.",
    mark: "mark-check",
    note: "Another cancer in the last 2 years? You didn’t say. Worth asking.",
  },
  {
    kind: "Inclusion",
    text: "Absolute neutrophil count ≥ 1,000/mcL.",
    mark: "mark-info",
    note: "A blood test the study team runs at screening.",
  },
];

export function FinePrintDemo() {
  return (
    <figure className="relative rounded-xl border border-rule bg-surface shadow-[0_1px_0_var(--rule),0_18px_40px_-24px_rgb(17_43_42/0.35)]">
      <div className="flex items-baseline justify-between gap-4 border-b border-rule px-5 py-3 text-sm">
        <span className="font-semibold">Eligibility criteria</span>
        <span className="text-ink-3">NCT07631325, melanoma</span>
      </div>
      <ul className="divide-y divide-rule/70">
        {LINES.map((l, i) => (
          <li key={i} className="grid gap-1.5 px-5 py-3.5 sm:grid-cols-[1fr_12.5rem] sm:gap-6">
            <p className="doc text-[0.98rem] text-ink">
              <span className="mr-2 font-sans text-xs text-ink-3">{l.kind}</span>
              <span className={`mark mark-sweep ${l.mark}`} style={{ animationDelay: `${450 + i * 380}ms` }}>
                {l.text}
              </span>
            </p>
            <p
              className="rise text-sm leading-snug text-ink-2 sm:border-l sm:border-rule sm:pl-4"
              style={{ animationDelay: `${650 + i * 380}ms` }}
            >
              {l.note}
            </p>
          </li>
        ))}
      </ul>
      <figcaption className="flex flex-wrap gap-x-5 gap-y-1 border-t border-rule px-5 py-3 text-xs text-ink-2">
        <span><span className="mark mark-ok">meets</span></span>
        <span><span className="mark mark-check">needs checking</span></span>
        <span><span className="mark mark-no">conflicts</span></span>
        <span><span className="mark mark-info">study team checks</span></span>
        <span className="ml-auto text-ink-3">Sample patient: 58, melanoma, activity level 1</span>
      </figcaption>
    </figure>
  );
}
