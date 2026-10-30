export type Verdict = "likely_eligible" | "possible" | "likely_ineligible" | "ineligible";
export type Status = "met" | "not_met" | "caution" | "unknown" | "review";

export interface Location {
  lat: number;
  lon: number;
  label: string;
}

export interface Profile {
  conditions: string[];
  age: number;
  sex: "female" | "male";
  location?: Location | null;
  max_distance_mi: number;
  healthy_volunteer?: boolean;
  pregnant?: boolean | null;
  breastfeeding?: boolean | null;
  ecog?: number | null;
  metastatic?: boolean | null;
  brain_metastases?: boolean | null;
  smoker?: boolean | null;
  bmi?: number | null;
  hba1c?: number | null;
  in_other_trial?: boolean | null;
  comorbidities?: string[] | null;
  treatments?: string[] | null;
  medications?: string[] | null;
}

export interface NearestSite {
  facility: string | null;
  city: string | null;
  state: string | null;
  lat: number;
  lon: number;
  distance_mi: number;
}

export interface MatchResult {
  nct_id: string;
  title: string;
  summary: string;
  status: string;
  phase: string;
  study_type: string;
  sponsor: string;
  conditions: string[];
  interventions: string[];
  enrollment: number | null;
  last_update: string | null;
  sex: string;
  min_age: number | null;
  max_age: number | null;
  score: number;
  verdict: Verdict;
  breakdown: { condition: number; semantic: number; eligibility: number; coverage: number; proximity: number | null };
  counts: Record<Status, number>;
  parser: string;
  reasons_for: string[];
  reasons_against: { status: Status; reason: string; text: string }[];
  nearest_site: NearestSite | null;
  sites_in_range: number;
  total_sites: number;
}

export interface MatchResponse {
  results: MatchResult[];
  total: number;
  candidates_considered: number;
  hidden: Record<"age" | "sex" | "healthy_volunteers" | "distance", number>;
  verdicts: Record<string, number>;
  ranking_method: string;
}

export interface CriterionResult {
  line: number;
  text: string;
  kind: "inclusion" | "exclusion";
  concept: string;
  label: string;
  category: string;
  operator: string;
  value: number | null;
  value_max: number | null;
  timeframe: string | null;
  status: Status;
  reason: string;
}

export interface Site {
  facility: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  country: string | null;
  status: string | null;
  lat: number | null;
  lon: number | null;
  contact: { name?: string; phone?: string; email?: string } | null;
  distance_mi: number | null;
}

export interface TrialDetail {
  nct_id: string;
  title: string;
  official_title: string | null;
  summary: string | null;
  status: string;
  phase: string;
  study_type: string;
  sponsor: string;
  sponsor_class: string;
  conditions: string[];
  keywords: string[];
  interventions: { type: string; name: string }[];
  sex: string;
  min_age_years: number | null;
  max_age_years: number | null;
  healthy_volunteers: boolean | null;
  enrollment: number | null;
  start_date: string | null;
  last_update: string | null;
  central_contact: { name?: string; phone?: string; email?: string } | null;
  eligibility_lines: { index: number; kind: string; text: string }[];
  parser: string;
  parser_model: string | null;
  sites: Site[];
  total_sites: number;
  url: string;
  llm_budget_remaining: number;
  criteria: CriterionResult[];
  counts?: Record<Status, number>;
  coverage?: number;
  verdict?: Verdict;
  structured_fails?: { field: string; reason: string }[];
  matched_condition?: string | null;
  nearest_site?: Site | null;
}

export interface Explanation {
  summary: string;
  why_it_may_fit: string[];
  things_to_check: string[];
  questions_for_your_doctor: string[];
  source: "llm" | "template";
  model?: string;
  note?: string;
  cached?: boolean;
}

export interface SimilarTrial {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  conditions: string[];
  sponsor: string;
  similarity: number;
}

export interface Option {
  id: string;
  label: string;
}

export interface Meta {
  concepts: Concept[];
  comorbidities: Option[];
  treatments: Option[];
  medications: Option[];
  categories: Record<string, string>;
}

export interface Health {
  trials: number;
  sites: number;
  llm_parsed: number;
  last_ingest: string | null;
  llm_budget_remaining: number;
  embedding_provider: string;
  ranker: string;
}

export interface Extracted {
  profile: Partial<Profile>;
  evidence: { field: string; value: unknown; start: number; end: number }[];
}

export interface GoldLabel {
  concept: string;
  operator: string | null;
  value: number | null;
  value_max: number | null;
}

export interface Annotation {
  id: number;
  nct_id: string | null;
  kind: "inclusion" | "exclusion";
  text: string;
  labels: GoldLabel[];
  draft: GoldLabel[];
  status: "draft" | "verified" | "skipped";
  source: "stratified" | "random";
  annotator: string | null;
}

export interface AnnotationStats {
  draft: number;
  verified: number;
  skipped: number;
  total: number;
  min_verified_for_eval: number;
  token_required: boolean;
}

export interface Concept {
  id: string;
  label: string;
  category: string;
  kind: "bool" | "num";
  assessable: boolean;
  unit: string | null;
  description: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit, retries = 1): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    if (retries > 0) return call<T>(path, init, retries - 1);
    throw e;
  }
  // every endpoint is safe to repeat, so retry once on a gateway hiccup
  if (res.status >= 500 && retries > 0) return call<T>(path, init, retries - 1);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/health"),
  meta: () => call<Meta>("/meta"),
  suggest: (q: string) => call<{ term: string; n: number }[]>(`/conditions/suggest?q=${encodeURIComponent(q)}`),
  geocode: (q: string) => call<(Location & { state?: string })[]>(`/geocode?q=${encodeURIComponent(q)}`),
  match: (p: Profile) => call<MatchResponse>("/match", post(p)),
  trial: (id: string, p?: Profile | null) =>
    p ? call<TrialDetail>(`/trials/${id}/evaluate`, post(p)) : call<TrialDetail>(`/trials/${id}`),
  similar: (id: string) => call<SimilarTrial[]>(`/trials/${id}/similar`),
  // these two spend LLM quota, so never retry them automatically
  explain: (id: string, p: Profile) => call<Explanation>(`/trials/${id}/explain`, post(p), 0),
  upgradeParse: (id: string) =>
    call<{ criteria: number; llm_budget_remaining: number }>(`/trials/${id}/parse-llm`, { method: "POST" }, 0),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  insights: () => call<any>("/insights"),
  extractProfile: (text: string) => call<Extracted>("/profile/extract", post({ text })),
  annotationStats: () => call<AnnotationStats>("/annotations/stats"),
  annotations: (status: string) => call<Annotation[]>(`/annotations?status=${status}&limit=500`),
  saveAnnotation: (id: number, body: { labels: GoldLabel[]; status: string; annotator?: string }, token?: string) =>
    call<Annotation>(`/annotations/${id}`, { method: "PUT", body: JSON.stringify(body), headers: token ? { "x-annotate-token": token } : {} }, 0),
  sampleAnnotations: (n: number, token?: string) =>
    call<{ added: number }>(`/annotations/sample?n=${n}`, { method: "POST", headers: token ? { "x-annotate-token": token } : {} }, 0),
};
