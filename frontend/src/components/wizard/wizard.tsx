"use client";

import { ArrowLeft, Loader2, LocateFixed, MapPin, Search, Wand2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, type Location, type Meta, type Profile } from "@/lib/api";
import { emptyProfile, saveProfile, useProfile } from "@/lib/profile";
import { ChoiceCard, Chip, MultiChips, Question, TriState } from "./controls";

const STEPS = ["Condition", "About you", "Location", "Health details", "Review"] as const;

const ECOG = [
  { v: 0, t: "Fully active", d: "I can do everything I did before getting sick." },
  { v: 1, t: "Active, but not strenuous work", d: "I can walk and do light work, like housework or an office job." },
  { v: 2, t: "Up and about most of the day", d: "I take care of myself but can't work. I'm up more than half the day." },
  { v: 3, t: "Resting much of the day", d: "I need rest in a bed or chair for more than half the day." },
  { v: 4, t: "Mostly in bed or a chair", d: "I need help with most self-care." },
];

const looksLikeCancer = (cs: string[]) =>
  cs.some((c) => /cancer|carcinoma|tumou?r|oma\b|leuk|melan|neoplas|metasta/i.test(c));

export function Wizard() {
  const stored = useProfile();
  // wait until sessionStorage is readable so an existing profile pre-fills the form
  if (stored === undefined) return null;
  return <WizardForm initial={stored ? { ...emptyProfile, ...stored } : emptyProfile} />;
}

function WizardForm({ initial }: { initial: Profile }) {
  const router = useRouter();
  const [p, setP] = useState<Profile>(initial);
  const [step, setStep] = useState(0);
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {});
  }, []);

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP((prev) => ({ ...prev, [k]: v }));

  const canContinue = [
    p.conditions.length > 0 || !!p.healthy_volunteer,
    p.age >= 0 && p.age <= 120 && !!p.sex,
    true,
    true,
    true,
  ][step];

  function next() {
    if (!canContinue) return;
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      window.scrollTo({ top: 0 });
    } else {
      saveProfile(p);
      router.push("/results");
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
      <ol className="mb-10 grid grid-cols-5 gap-1.5" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button
              type="button"
              disabled={i > step}
              onClick={() => setStep(i)}
              aria-current={i === step ? "step" : undefined}
              className="group block w-full text-left disabled:cursor-default"
            >
              <span className={`block h-1 rounded-full ${i <= step ? "bg-pine" : "bg-rule"}`} />
              <span
                className={`mt-2 hidden text-xs sm:block ${
                  i === step ? "font-semibold text-ink" : i < step ? "text-ink-2 group-hover:text-ink" : "text-ink-3"
                }`}
              >
                {s}
              </span>
            </button>
          </li>
        ))}
      </ol>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        {step === 0 && <ConditionStep p={p} set={set} merge={(patch) => setP((prev) => ({ ...prev, ...patch }))} />}
        {step === 1 && <AboutStep p={p} set={set} />}
        {step === 2 && <LocationStep p={p} set={set} />}
        {step === 3 && <HealthStep p={p} set={set} meta={meta} />}
        {step === 4 && <ReviewStep p={p} meta={meta} goTo={setStep} />}

        <div className="mt-12 flex items-center justify-between gap-4 border-t border-rule pt-6">
          {step > 0 ? (
            <button
              type="button"
              onClick={() => setStep(step - 1)}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-2 text-ink-2 hover:text-ink"
            >
              <ArrowLeft size={16} aria-hidden /> Back
            </button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-3">
            {step === 3 && (
              <button type="button" onClick={next} className="px-2 py-2 text-ink-2 hover:text-ink">
                Skip
              </button>
            )}
            <button
              type="submit"
              disabled={!canContinue}
              className="rounded-lg bg-pine px-5 py-2.5 font-semibold text-on-pine hover:bg-pine-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              {step === STEPS.length - 1 ? "Show my matches" : "Continue"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

type StepProps = { p: Profile; set: <K extends keyof Profile>(k: K, v: Profile[K]) => void };

function ConditionStep({ p, set, merge }: StepProps & { merge: (patch: Partial<Profile>) => void }) {
  const [q, setQ] = useState("");
  const [rawSugg, setSugg] = useState<{ term: string; n: number }[]>([]);
  const [popular, setPopular] = useState<{ term: string; n: number }[]>([]);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    api.suggest("").then(setPopular).catch(() => {});
  }, []);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => api.suggest(q).then(setSugg).catch(() => {}), 160);
    return () => clearTimeout(t);
  }, [q]);
  const sugg = q.trim().length < 2 ? [] : rawSugg;

  const add = (term: string) => {
    const clean = term.trim();
    if (clean && !p.conditions.some((c) => c.toLowerCase() === clean.toLowerCase())) {
      set("conditions", [...p.conditions, clean]);
    }
    setQ("");
    setActive(-1);
  };

  return (
    <Question
      title="What condition are you looking for a trial for?"
      hint="Use your own words, like “type 2 diabetes” or “stage 3 lung cancer”. You can add more than one."
    >
      <DescribeBox merge={merge} />
      <div className="relative">
        <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" size={20} aria-hidden />
        <input
          autoFocus
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(-1);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, sugg.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, -1));
            } else if (e.key === "Enter" && q.trim()) {
              e.preventDefault();
              add(active >= 0 ? sugg[active].term : q);
            }
          }}
          role="combobox"
          aria-expanded={sugg.length > 0}
          aria-controls="cond-suggestions"
          aria-activedescendant={active >= 0 ? `cond-${active}` : undefined}
          aria-label="Condition"
          placeholder="Start typing a condition"
          className="w-full rounded-xl border border-rule bg-surface py-4 pl-12 pr-4 text-lg shadow-sm placeholder:text-ink-3 focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/30"
        />
        {sugg.length > 0 && (
          <ul
            id="cond-suggestions"
            role="listbox"
            className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-rule bg-surface py-1 shadow-lg"
          >
            {sugg.map((s, i) => (
              <li
                id={`cond-${i}`}
                key={s.term}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  add(s.term);
                }}
                className="flex cursor-pointer items-center justify-between px-4 py-2.5 aria-selected:bg-paper-2 hover:bg-paper-2"
              >
                <span>{s.term}</span>
                <span className="text-sm text-ink-3">{s.n} {s.n === 1 ? "study" : "studies"}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {p.conditions.length > 0 && (
        <ul className="mt-5 flex flex-wrap gap-2" aria-label="Your conditions">
          {p.conditions.map((c) => (
            <li key={c} className="inline-flex items-center gap-1 rounded-full bg-ink py-1.5 pl-3.5 pr-1.5 text-sm text-paper">
              {c}
              <button
                type="button"
                aria-label={`Remove ${c}`}
                onClick={() => set("conditions", p.conditions.filter((x) => x !== c))}
                className="grid h-6 w-6 place-items-center rounded-full hover:bg-white/15"
              >
                <X size={14} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {popular.length > 0 && (
        <div className="mt-8">
          <p className="text-sm text-ink-2">Common searches</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {popular.map((s) => (
              <Chip key={s.term} selected={p.conditions.includes(s.term)} onClick={() => add(s.term)}>
                {s.term}
              </Chip>
            ))}
          </div>
        </div>
      )}

      <label className="mt-10 flex cursor-pointer items-start gap-3 rounded-lg border border-rule bg-surface p-4">
        <input
          type="checkbox"
          checked={!!p.healthy_volunteer}
          onChange={(e) => set("healthy_volunteer", e.target.checked)}
          className="mt-1 h-4 w-4 accent-[var(--pine)]"
        />
        <span>
          <span className="block font-medium">I’m a healthy volunteer</span>
          <span className="text-sm text-ink-2">Many studies need people without the condition, too.</span>
        </span>
      </label>
    </Question>
  );
}

function AboutStep({ p, set }: StepProps) {
  return (
    <Question title="A little about you" hint="Studies set age limits and sometimes enroll only women or only men.">
      <div className="grid gap-10">
        <label className="block">
          <span className="font-medium">Age</span>
          <div className="mt-3 flex items-center gap-4">
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={120}
              value={Number.isFinite(p.age) ? p.age : ""}
              onChange={(e) => set("age", Math.max(0, Math.min(120, parseInt(e.target.value || "0", 10))))}
              className="w-28 rounded-xl border border-rule bg-surface px-4 py-3 text-2xl font-semibold tabular-nums focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/30"
            />
            <input
              type="range"
              min={1}
              max={100}
              value={p.age}
              onChange={(e) => set("age", parseInt(e.target.value, 10))}
              aria-label="Age slider"
              className="flex-1"
            />
          </div>
        </label>
        <div>
          <span className="font-medium" id="sex-label">
            Sex assigned at birth
          </span>
          <p className="mt-1 text-sm text-ink-2">Trials list eligibility by biological sex.</p>
          <div role="radiogroup" aria-labelledby="sex-label" className="mt-3 grid gap-2 sm:grid-cols-2">
            <ChoiceCard selected={p.sex === "female"} onClick={() => set("sex", "female")} title="Female" />
            <ChoiceCard selected={p.sex === "male"} onClick={() => set("sex", "male")} title="Male" />
          </div>
        </div>
      </div>
    </Question>
  );
}

function LocationStep({ p, set }: StepProps) {
  const [q, setQ] = useState("");
  const [rawResults, setResults] = useState<(Location & { state?: string })[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const results = q.trim().length < 3 ? [] : rawResults;
  useEffect(() => {
    if (q.trim().length < 3) return;
    const t = setTimeout(() => {
      setBusy(true);
      api
        .geocode(q)
        .then((r) => {
          setResults(r);
          setError(r.length ? null : "No US place found. Try a city name or 5-digit ZIP code.");
        })
        .catch(() => setError("Location search is unavailable right now. Try “Use my location”."))
        .finally(() => setBusy(false));
    }, 400);
    return () => clearTimeout(t);
  }, [q]);

  function locate() {
    if (!navigator.geolocation) {
      setError("Your browser doesn't share location. Search for a city instead.");
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set("location", { lat: pos.coords.latitude, lon: pos.coords.longitude, label: "Your current location" });
        setBusy(false);
      },
      () => {
        setError("Location permission was denied. Search for a city instead.");
        setBusy(false);
      },
      { timeout: 10000 },
    );
  }

  return (
    <Question title="Where should the study be?" hint="We measure the distance to each study site. Your location stays in this browser tab.">
      {p.location ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-pine bg-surface px-4 py-3.5">
          <span className="flex items-center gap-2 font-medium">
            <MapPin size={18} className="text-pine" aria-hidden /> {p.location.label}
          </span>
          <button type="button" onClick={() => set("location", null)} className="text-sm text-ink-2 underline underline-offset-4">
            Change
          </button>
        </div>
      ) : (
        <>
          <div className="relative">
            <MapPin className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" size={20} aria-hidden />
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="City or ZIP code"
              placeholder="City or ZIP code"
              className="w-full rounded-xl border border-rule bg-surface py-4 pl-12 pr-12 text-lg shadow-sm placeholder:text-ink-3 focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/30"
            />
            {busy && <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 animate-spin text-ink-3" size={20} aria-hidden />}
          </div>
          {results.length > 0 && (
            <ul className="mt-2 overflow-hidden rounded-xl border border-rule bg-surface">
              {results.map((r) => (
                <li key={`${r.lat},${r.lon}`}>
                  <button
                    type="button"
                    onClick={() => set("location", { lat: r.lat, lon: r.lon, label: r.label })}
                    className="w-full px-4 py-2.5 text-left hover:bg-paper-2"
                  >
                    {r.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="mt-3 text-sm text-ink-2" role="status">{error}</p>}
          <button type="button" onClick={locate} className="mt-4 inline-flex items-center gap-2 font-medium text-pine">
            <LocateFixed size={18} aria-hidden /> Use my location
          </button>
        </>
      )}

      <div className={`mt-10 ${p.location ? "" : "opacity-50"}`}>
        <label className="flex items-baseline justify-between font-medium" htmlFor="radius">
          How far could you travel?
          <span className="text-xl font-semibold tabular-nums">{p.max_distance_mi} mi</span>
        </label>
        <input
          id="radius"
          type="range"
          min={10}
          max={500}
          step={10}
          disabled={!p.location}
          value={p.max_distance_mi}
          onChange={(e) => set("max_distance_mi", parseInt(e.target.value, 10))}
          className="mt-3 w-full"
        />
        <div className="mt-1 flex justify-between text-xs text-ink-3">
          <span>10 mi</span>
          <span>500 mi</span>
        </div>
      </div>
      {!p.location && <p className="mt-6 text-sm text-ink-2">No location? We’ll search the whole US and skip distance.</p>}
    </Question>
  );
}

function HealthStep({ p, set, meta }: StepProps & { meta: Meta | null }) {
  const cancer = looksLikeCancer(p.conditions);
  return (
    <Question
      title="A few health details"
      hint="Each answer lets us check more of a study’s rules. Skip anything you’re unsure about; we’ll mark it for your doctor instead of guessing."
    >
      <div className="space-y-10">
        <section>
          <h2 className="font-semibold">Which best describes your day-to-day?</h2>
          <p className="mt-1 text-sm text-ink-2">Doctors call this “performance status”. Many studies, especially cancer studies, set a limit.</p>
          <div role="radiogroup" aria-label="Activity level" className="mt-4 grid gap-2">
            {ECOG.map((e) => (
              <ChoiceCard
                key={e.v}
                selected={p.ecog === e.v}
                onClick={() => set("ecog", p.ecog === e.v ? null : e.v)}
                title={e.t}
                detail={e.d}
              />
            ))}
          </div>
        </section>

        <section className="space-y-4 rounded-xl border border-rule bg-surface p-5">
          {cancer && (
            <>
              <TriState label="Has the cancer spread (metastatic or stage 4)?" value={p.metastatic} onChange={(v) => set("metastatic", v)} />
              <TriState label="Has it spread to the brain?" value={p.brain_metastases} onChange={(v) => set("brain_metastases", v)} />
            </>
          )}
          {p.sex === "female" && (
            <>
              <TriState label="Are you pregnant?" value={p.pregnant} onChange={(v) => set("pregnant", v)} />
              <TriState label="Are you breastfeeding?" value={p.breastfeeding} onChange={(v) => set("breastfeeding", v)} />
            </>
          )}
          <TriState label="Do you currently smoke?" value={p.smoker} onChange={(v) => set("smoker", v)} />
          <TriState label="Are you in another clinical trial now?" value={p.in_other_trial} onChange={(v) => set("in_other_trial", v)} />
        </section>

        {meta && (
          <>
            <section>
              <h2 className="font-semibold">Do you have any of these other conditions?</h2>
              <div className="mt-4">
                <MultiChips options={meta.comorbidities} value={p.comorbidities} onChange={(v) => set("comorbidities", v)} />
              </div>
            </section>
            <section>
              <h2 className="font-semibold">Treatments you’ve had for this condition</h2>
              <div className="mt-4">
                <MultiChips options={meta.treatments} value={p.treatments} onChange={(v) => set("treatments", v)} />
              </div>
            </section>
            <section>
              <h2 className="font-semibold">Medicines you take now</h2>
              <div className="mt-4">
                <MultiChips options={meta.medications} value={p.medications} onChange={(v) => set("medications", v)} />
              </div>
            </section>
          </>
        )}
      </div>
    </Question>
  );
}

function ReviewStep({ p, meta, goTo }: { p: Profile; meta: Meta | null; goTo: (s: number) => void }) {
  const label = useMemo(() => {
    const all = [...(meta?.comorbidities ?? []), ...(meta?.treatments ?? []), ...(meta?.medications ?? [])];
    return (id: string) => all.find((o) => o.id === id)?.label ?? id;
  }, [meta]);
  const list = (v: string[] | null | undefined) => (v == null ? "Skipped" : v.length ? v.map(label).join(", ") : "None");
  const yn = (v: boolean | null | undefined) => (v == null ? "Skipped" : v ? "Yes" : "No");

  const rows: { k: string; v: string; step: number }[] = [
    { k: "Conditions", v: [...p.conditions, ...(p.healthy_volunteer ? ["Healthy volunteer"] : [])].join(", "), step: 0 },
    { k: "Age and sex", v: `${p.age}, ${p.sex}`, step: 1 },
    { k: "Location", v: p.location ? `${p.location.label}, within ${p.max_distance_mi} mi` : "Anywhere in the US", step: 2 },
    { k: "Day-to-day activity", v: p.ecog == null ? "Skipped" : ECOG[p.ecog].t, step: 3 },
    { k: "Other conditions", v: list(p.comorbidities), step: 3 },
    { k: "Past treatments", v: list(p.treatments), step: 3 },
    { k: "Current medicines", v: list(p.medications), step: 3 },
    { k: "Smoking", v: yn(p.smoker), step: 3 },
  ];
  if (p.sex === "female") rows.push({ k: "Pregnant", v: yn(p.pregnant), step: 3 });

  return (
    <Question title="Does this look right?" hint="We use this only to check study rules. It is kept in this browser tab and cleared when you close it.">
      <dl className="divide-y divide-rule rounded-xl border border-rule bg-surface">
        {rows.map((r) => (
          <div key={r.k} className="grid grid-cols-[9rem_1fr_auto] items-baseline gap-3 px-4 py-3 sm:grid-cols-[12rem_1fr_auto]">
            <dt className="text-sm text-ink-2">{r.k}</dt>
            <dd className={r.v === "Skipped" ? "text-ink-3" : ""}>{r.v}</dd>
            <button type="button" onClick={() => goTo(r.step)} className="text-sm text-pine underline-offset-4 hover:underline">
              Edit
            </button>
          </div>
        ))}
      </dl>
    </Question>
  );
}

const FIELD_NAMES: Record<string, string> = {
  age: "age", sex: "sex", conditions: "condition", ecog: "activity level", metastatic: "cancer spread",
  brain_metastases: "brain spread", pregnant: "pregnancy", breastfeeding: "breastfeeding", smoker: "smoking",
  comorbidities: "other conditions", treatments: "past treatments", medications: "medicines", bmi: "BMI", hba1c: "HbA1c",
};

/** Optional shortcut: describe your situation and we pre-fill the form. Nothing is stored. */
function DescribeBox({ merge }: { merge: (patch: Partial<Profile>) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [filled, setFilled] = useState<string[] | null>(null);

  async function run() {
    setBusy(true);
    try {
      const { profile } = await api.extractProfile(text);
      merge(profile);
      setFilled(Object.keys(profile).map((k) => FIELD_NAMES[k] ?? k));
    } catch {
      setFilled([]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-pine">
        <Wand2 size={16} aria-hidden /> Or describe your situation in your own words
      </button>
    );
  }
  return (
    <div className="mb-8 rounded-xl border border-rule bg-surface p-4">
      <label htmlFor="describe" className="font-medium">
        Describe your situation
      </label>
      <p className="mt-1 text-sm text-ink-2">
        For example: “I’m a 62-year-old woman with metastatic breast cancer. I’ve had chemotherapy and surgery. I don’t smoke.”
        We’ll fill in what we can; you can check every answer in the next steps.
      </p>
      <textarea
        id="describe"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        maxLength={4000}
        className="mt-3 w-full rounded-lg border border-rule bg-paper px-3 py-2 focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/30"
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={busy || text.trim().length < 3}
          className="inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-40"
        >
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Wand2 size={15} aria-hidden />}
          Fill in the form
        </button>
        {filled && (
          <p className="text-sm text-ink-2" role="status">
            {filled.length ? `Filled in: ${filled.join(", ")}. Please check each step.` : "We couldn’t find details to fill in. Try adding your age and condition."}
          </p>
        )}
      </div>
    </div>
  );
}
