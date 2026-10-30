"""HTTP API. Patient profiles are only ever held in request bodies; nothing identifying is stored."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .. import annotations, embeddings, explain as explainer, geo
from ..config import settings
from ..db import fetch_all, fetch_one
from ..llm import LLMUnavailable, budget_remaining
from ..matching import PatientProfile, check_structured, evaluate_trial, verdict
from ..parsing.schema import OPERATORS
from ..parsing.service import best_parse, parse_one_llm
from ..profile_extract import extract as extract_profile
from ..ranking import features as F
from ..ranking import model as ranker
from ..search import TRIAL_COLS, search, summarise
from ..vocab import (CATEGORIES, COMORBIDITY_OPTIONS, CONCEPT_IDS, CONCEPTS, MEDICATION_OPTIONS,
                     TREATMENT_OPTIONS, concept_catalog)

router = APIRouter(prefix="/api")

_OPTION_LABELS = {
    "chemotherapy": "Chemotherapy", "immunotherapy": "Immunotherapy", "radiation": "Radiation therapy",
    "surgery": "Surgery", "targeted_therapy": "Targeted therapy", "hormone_therapy": "Hormone therapy",
}


def _opt(ids: List[str]) -> List[dict]:
    by_field = {c.profile_field: c.label for c in CONCEPTS.values() if c.profile_field}
    return [{"id": i, "label": _OPTION_LABELS.get(i) or by_field.get(i, i.replace("_", " ").title())} for i in ids]


@router.get("/health")
def health():
    stats = fetch_one(
        """SELECT (SELECT count(*) FROM trials) AS trials, (SELECT count(*) FROM sites) AS sites,
                  (SELECT count(*) FROM parsed_eligibility WHERE parser = 'llm') AS llm_parsed,
                  (SELECT max(finished_at) FROM ingest_runs WHERE status IN ('ok','partial')) AS last_ingest"""
    )
    return {
        "ok": True, **stats,
        "llm_budget_remaining": budget_remaining(),
        "embedding_provider": embeddings.provider().name,
        "ranker": "gbdt" if ranker.load() else "heuristic",
    }


@router.get("/meta")
def meta():
    return {
        "categories": CATEGORIES,
        "concepts": concept_catalog(),
        "comorbidities": _opt(COMORBIDITY_OPTIONS),
        "treatments": _opt(TREATMENT_OPTIONS),
        "medications": _opt(MEDICATION_OPTIONS),
    }


@router.get("/conditions/suggest")
def suggest_conditions(q: str = Query("", max_length=80), limit: int = 8):
    q = q.strip()
    if len(q) < 2:
        rows = fetch_all(
            """SELECT source_query AS term, count(*) AS n FROM trials WHERE source_query IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC LIMIT %s""", (limit,))
        return rows
    return fetch_all(
        """SELECT term, count(*) AS n FROM (
             SELECT unnest(conditions || mesh_terms) AS term FROM trials) x
           WHERE term ILIKE %s GROUP BY term
           ORDER BY (lower(term) LIKE lower(%s)) DESC, count(*) DESC, length(term) LIMIT %s""",
        (f"%{q}%", f"{q}%", limit),
    )


@router.get("/geocode")
def geocode(q: str = Query(..., min_length=2, max_length=120)):
    try:
        return geo.geocode(q)
    except Exception as exc:
        raise HTTPException(502, f"geocoding failed: {exc}")


@router.post("/match")
def match(profile: PatientProfile, limit: int = Query(40, le=100)):
    if not profile.conditions and not profile.healthy_volunteer:
        raise HTTPException(422, "Add at least one condition, or choose healthy volunteer.")
    return search(profile, limit=limit)


def _trial(nct_id: str) -> dict:
    t = fetch_one(f"SELECT {TRIAL_COLS}, official_title, central_contact FROM trials WHERE nct_id = %s", (nct_id,))
    if not t:
        raise HTTPException(404, "Trial not found")
    return t


def _sites(nct_id: str, profile: Optional[PatientProfile]) -> List[dict]:
    sites = fetch_all(
        "SELECT facility, city, state, zip, country, status, lat, lon, contact FROM sites WHERE nct_id = %s",
        (nct_id,))
    loc = profile.location if profile else None
    return geo.nearest(sites, loc.lat if loc else None, loc.lon if loc else None)


def _detail(nct_id: str, profile: Optional[PatientProfile]) -> dict:
    t = _trial(nct_id)
    parsed = best_parse(nct_id, t["eligibility_text"], t["criteria_hash"])
    sites = _sites(nct_id, profile)
    body = {
        **{k: t[k] for k in ("nct_id", "title", "official_title", "summary", "status", "phase", "study_type",
                             "sponsor", "sponsor_class", "conditions", "keywords", "interventions", "sex",
                             "min_age_years", "max_age_years", "healthy_volunteers", "enrollment", "start_date",
                             "last_update", "central_contact")},
        "eligibility_lines": [ln.model_dump() for ln in parsed.lines],
        "parser": parsed.parser,
        "parser_model": parsed.model,
        "sites": sites[:400],
        "total_sites": len(sites),
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "llm_budget_remaining": budget_remaining(),
    }
    if profile is None:
        body["criteria"] = [{**c.model_dump(), "label": CONCEPTS[c.concept].label if c.concept in CONCEPTS else c.concept,
                             "status": "review", "reason": ""} for c in parsed.criteria]
        return body
    cond = F.condition_match(profile.conditions, t) if profile.conditions else {"condition_score": 0.0, "matched": None}
    structured_age = t["min_age_years"] is not None or t["max_age_years"] is not None
    ev = evaluate_trial(parsed, profile, cond["condition_score"], structured_age)
    fails = check_structured(t, profile)
    nearest = next((s for s in sites if s["distance_mi"] is not None), None)
    body.update({
        "criteria": ev["criteria"], "counts": ev["counts"], "coverage": ev["coverage"],
        "eligibility_score": ev["eligibility_score"], "structured_fails": fails,
        "verdict": verdict(fails, ev, cond["condition_score"]), "matched_condition": cond.get("matched"),
        "condition_score": cond["condition_score"], "nearest_site": nearest,
    })
    return body


@router.get("/trials/{nct_id}")
def trial(nct_id: str):
    return _detail(nct_id, None)


@router.post("/trials/{nct_id}/evaluate")
def trial_for_profile(nct_id: str, profile: PatientProfile):
    return _detail(nct_id, profile)


@router.get("/trials/{nct_id}/similar")
def similar(nct_id: str, limit: int = Query(6, le=20)):
    rows = fetch_all(
        """SELECT o.nct_id, o.title, o.phase, o.status, o.conditions, o.sponsor,
                  1 - (o.embedding <=> t.embedding) AS similarity
           FROM trials t JOIN trials o ON o.nct_id <> t.nct_id AND o.embedding IS NOT NULL
           WHERE t.nct_id = %s AND t.embedding IS NOT NULL
           ORDER BY o.embedding <=> t.embedding LIMIT %s""",
        (nct_id, limit),
    )
    for r in rows:
        r["similarity"] = round(float(r["similarity"]), 3)
        r["conditions"] = r["conditions"][:3]
    return rows


@router.post("/trials/{nct_id}/explain")
def explain(nct_id: str, profile: PatientProfile):
    d = _detail(nct_id, profile)
    t = _trial(nct_id)
    return explainer.explain(t, d["criteria"], profile)


@router.post("/trials/{nct_id}/parse-llm")
def upgrade_parse(nct_id: str):
    _trial(nct_id)
    try:
        parsed = parse_one_llm(nct_id)
    except LLMUnavailable as exc:
        raise HTTPException(429, str(exc))
    return {"parser": parsed.parser, "model": parsed.model, "criteria": len(parsed.criteria),
            "llm_budget_remaining": budget_remaining()}


@router.get("/insights")
def insights():
    reports = {r["kind"]: {**r["report"], "generated_at": r["created_at"]}
               for r in fetch_all("SELECT kind, report, created_at FROM eval_reports")}
    data = {
        "by_condition": fetch_all(
            "SELECT source_query AS label, count(*) AS n FROM trials GROUP BY 1 ORDER BY 2 DESC LIMIT 30"),
        "by_phase": fetch_all("SELECT phase AS label, count(*) AS n FROM trials GROUP BY 1 ORDER BY 2 DESC LIMIT 8"),
        "by_status": fetch_all("SELECT status AS label, count(*) AS n FROM trials GROUP BY 1 ORDER BY 2 DESC"),
        "by_state": fetch_all(
            """SELECT state AS label, count(DISTINCT nct_id) AS n FROM sites
               WHERE country = 'United States' AND state IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""),
        "ingest_runs": fetch_all(
            """SELECT id, started_at, finished_at, status, trials_seen, trials_upserted
               FROM ingest_runs ORDER BY id DESC LIMIT 8"""),
        "llm_usage": fetch_all(
            """SELECT date_trunc('day', created_at)::date AS day, purpose, count(*) AS calls,
                      sum(ok::int) AS ok, round(avg(latency_ms)) AS avg_ms
               FROM llm_calls GROUP BY 1, 2 ORDER BY 1 DESC, 2 LIMIT 30"""),
    }
    return {"reports": reports, "data": data}


# ---------------------------------------------------------------- free-text intake

class DescribeIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)


@router.post("/profile/extract")
def profile_from_text(body: DescribeIn):
    """Pull age, sex, conditions and history out of a description. Nothing is stored."""
    return extract_profile(body.text)


# ---------------------------------------------------------------- gold-standard annotation

class Label(BaseModel):
    concept: str
    operator: Optional[str] = "present"
    value: Optional[float] = None
    value_max: Optional[float] = None


class AnnotationIn(BaseModel):
    labels: List[Label]
    status: str = Field("verified", pattern="^(draft|verified|skipped)$")
    annotator: Optional[str] = Field(None, max_length=60)


def _can_write(x_annotate_token: Optional[str] = Header(None)) -> None:
    if settings.annotate_token and x_annotate_token != settings.annotate_token:
        raise HTTPException(403, "Annotation token required to save.")


@router.get("/annotations/stats")
def annotation_stats():
    return {**annotations.stats(), "token_required": bool(settings.annotate_token)}


@router.get("/annotations")
def annotation_list(status: str = Query("draft", pattern="^(draft|verified|skipped|all)$"),
                    limit: int = Query(200, le=500), offset: int = 0):
    return annotations.list_items(status, limit, offset)


@router.put("/annotations/{item_id}", dependencies=[Depends(_can_write)])
def annotation_save(item_id: int, body: AnnotationIn):
    for lab in body.labels:
        if lab.concept not in CONCEPT_IDS:
            raise HTTPException(422, f"Unknown concept: {lab.concept}")
        if lab.operator is not None and lab.operator not in OPERATORS:
            raise HTTPException(422, f"Unknown operator: {lab.operator}")
    row = annotations.save(item_id, [lab.model_dump() for lab in body.labels], body.status, body.annotator)
    if not row:
        raise HTTPException(404, "No such line")
    return row


@router.post("/annotations/sample", dependencies=[Depends(_can_write)])
def annotation_sample(n: int = Query(25, ge=1, le=100)):
    return {"added": annotations.add_random(n)}


@router.get("/annotations/export", response_class=PlainTextResponse)
def annotation_export():
    import json as _json
    return "\n".join(_json.dumps(r, ensure_ascii=False) for r in annotations.verified_gold()) + "\n"
