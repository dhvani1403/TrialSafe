import type { Status, Verdict } from "./api";

export const verdictCopy: Record<Verdict, { label: string; mark: string; hint: string }> = {
  likely_eligible: {
    label: "Looks like a fit",
    mark: "mark-ok",
    hint: "Nothing we could check rules you out.",
  },
  possible: {
    label: "Worth asking about",
    mark: "mark-check",
    hint: "Some requirements need a closer look.",
  },
  likely_ineligible: {
    label: "Probably not a fit",
    mark: "mark-no",
    hint: "At least one requirement conflicts with what you told us.",
  },
  ineligible: {
    label: "Not open to you",
    mark: "mark-no",
    hint: "The study's age, sex or volunteer rules exclude you.",
  },
};

export const statusCopy: Record<Status, { label: string; mark: string }> = {
  met: { label: "Meets", mark: "mark-ok" },
  not_met: { label: "Conflicts", mark: "mark-no" },
  caution: { label: "Check", mark: "mark-check" },
  unknown: { label: "Not answered", mark: "mark-check" },
  review: { label: "Study team checks", mark: "mark-info" },
};

export function phaseLabel(phase: string | null | undefined): string {
  if (!phase || phase === "NA") return "No phase";
  return phase
    .split("/")
    .map((p) => (p === "EARLY_PHASE1" ? "Early phase 1" : p.replace("PHASE", "Phase ")))
    .join(" / ")
    .replace(/ \/ Phase /g, "/");
}

export function statusLabel(s: string): string {
  return (
    {
      RECRUITING: "Recruiting",
      NOT_YET_RECRUITING: "Opening soon",
      ENROLLING_BY_INVITATION: "By invitation",
    }[s] ?? s.toLowerCase().replace(/_/g, " ")
  );
}

export function ageRange(min: number | null | undefined, max: number | null | undefined): string {
  const f = (n: number) => (n < 1 ? `${Math.round(n * 12)} mo` : `${Math.round(n)}`);
  if (min == null && max == null) return "Any age";
  if (max == null) return `${f(min!)}+`;
  if (min == null) return `Up to ${f(max)}`;
  return `${f(min)}–${f(max)}`;
}

export function sexLabel(s: string): string {
  return s === "ALL" ? "All sexes" : s === "FEMALE" ? "Women only" : "Men only";
}

export function miles(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1) return "under a mile";
  return `${Math.round(n)} mi`;
}

export function shortDate(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}
