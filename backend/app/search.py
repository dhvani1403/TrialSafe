"""Hybrid retrieval + eligibility evaluation + ranking for a patient profile."""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import embeddings
from .db import fetch_all
from .matching import PatientProfile, check_structured, evaluate_trial, verdict
from .parsing.service import load_parses
from .parsing import rules
from .ranking import features as F
from .ranking import model as ranker

log = logging.getLogger(__name__)
RRF_K = 60
POOL = 300

TRIAL_COLS = """nct_id, title, summary, status, phase, study_type, sponsor, sponsor_class, conditions,
    mesh_terms, mesh_ancestors, keywords, interventions, sex, min_age_years, max_age_years,
    healthy_volunteers, eligibility_text, criteria_hash, enrollment, start_date, last_update"""

_DIST_SQL = """
WITH d AS (
  SELECT s.nct_id, s.facility, s.city, s.state, s.lat, s.lon,
         3958.8 * 2 * asin(sqrt(power(sin(radians(s.lat - %(lat)s) / 2), 2) +
           cos(radians(%(lat)s)) * cos(radians(s.lat)) * power(sin(radians(s.lon - %(lon)s) / 2), 2))) AS mi
  FROM sites s WHERE s.nct_id = ANY(%(ids)s) AND s.lat IS NOT NULL
)
SELECT DISTINCT ON (nct_id) nct_id, facility, city, state, lat, lon, mi AS nearest_mi,
       count(*) FILTER (WHERE mi <= %(radius)s) OVER (PARTITION BY nct_id) AS sites_in_range,
       count(*) OVER (PARTITION BY nct_id) AS total_sites
FROM d ORDER BY nct_id, mi
"""


def query_text(profile: PatientProfile) -> str:
    if profile.conditions:
        return " ".join(profile.conditions)
    return "healthy volunteers"


def retrieve(profile: PatientProfile, pool: int = POOL) -> Dict[str, Dict[str, float]]:
    """Reciprocal-rank fusion of Postgres full-text search and pgvector cosine search."""
    conds = profile.conditions or ["healthy volunteers"]
    tsq = " or ".join(c.replace('"', " ") for c in conds)
    fts = fetch_all(
        """SELECT nct_id, ts_rank_cd(search_tsv, q, 32) AS r
           FROM trials, websearch_to_tsquery('english', %s) q
           WHERE search_tsv @@ q ORDER BY r DESC LIMIT %s""",
        (tsq, pool),
    )
    out: Dict[str, Dict[str, float]] = {}
    for rank, row in enumerate(fts):
        out.setdefault(row["nct_id"], {"rrf": 0.0, "fts": 0.0, "vec": 0.0})
        out[row["nct_id"]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        out[row["nct_id"]]["fts"] = float(row["r"])
    try:
        if embeddings.stored_provider() not in ("", embeddings.provider().name):
            raise RuntimeError("trial vectors were built by a different embedding model; run `embed`")
        qvec = embeddings.encode([query_text(profile)])[0]
        vec = fetch_all(
            """SELECT nct_id, 1 - (embedding <=> %s) AS sim FROM trials
               WHERE embedding IS NOT NULL ORDER BY embedding <=> %s LIMIT %s""",
            (qvec, qvec, pool),
        )
    except RuntimeError as exc:  # not fitted yet, or model mismatch: fall back to keyword search
        log.warning("vector search skipped: %s", exc)
        vec = []
    for rank, row in enumerate(vec):
        out.setdefault(row["nct_id"], {"rrf": 0.0, "fts": 0.0, "vec": 0.0})
        out[row["nct_id"]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        out[row["nct_id"]]["vec"] = float(row["sim"])
    return out


def distances(ids: List[str], profile: PatientProfile) -> Dict[str, dict]:
    if not profile.location or not ids:
        rows = fetch_all("SELECT nct_id, count(*) AS total_sites FROM sites WHERE nct_id = ANY(%s) GROUP BY 1", (ids,))
        return {r["nct_id"]: {"nearest_mi": None, "sites_in_range": 0, "total_sites": r["total_sites"]} for r in rows}
    rows = fetch_all(_DIST_SQL, {"lat": profile.location.lat, "lon": profile.location.lon, "ids": ids,
                                 "radius": profile.max_distance_mi})
    return {r["nct_id"]: r for r in rows}


def score_candidates(profile: PatientProfile, retrieved: Dict[str, Dict[str, float]]) -> List[dict]:
    ids = list(retrieved)
    if not ids:
        return []
    trials = fetch_all(f"SELECT {TRIAL_COLS} FROM trials WHERE nct_id = ANY(%s)", (ids,))
    parses = load_parses(ids)
    dist = distances(ids, profile)
    out = []
    for t in trials:
        nct = t["nct_id"]
        cond = F.condition_match(profile.conditions, t) if profile.conditions else \
            {"cond_lex": 0.0, "cond_anc": 0.0, "cond_title": 0.0, "condition_score": 0.0, "matched": None}
        if profile.healthy_volunteer and t.get("healthy_volunteers"):
            cond["condition_score"] = max(cond["condition_score"], 0.7)
        parsed = parses.get(nct) or rules.parse(t["eligibility_text"] or "")
        structured_age = t.get("min_age_years") is not None or t.get("max_age_years") is not None
        ev = evaluate_trial(parsed, profile, cond["condition_score"], structured_age)
        fails = check_structured(t, profile)
        d = dist.get(nct, {"nearest_mi": None, "sites_in_range": 0, "total_sites": 0})
        feats = F.build(t, cond, ev, retrieved[nct], d, fails, profile.location is not None)
        out.append({"trial": t, "cond": cond, "eval": ev, "fails": fails, "dist": d, "features": feats,
                    "verdict": verdict(fails, ev, cond["condition_score"])})
    return out


def rank(profile: PatientProfile, cands: List[dict]) -> Tuple[List[dict], str]:
    rows = [c["features"] for c in cands]
    learned = ranker.predict(rows)
    for i, c in enumerate(cands):
        h = F.heuristic(c["features"], profile.max_distance_mi)
        c["heuristic"] = h
        if learned is not None:
            # learned relevance is on a 0-3 scale; keep hard fails at the bottom
            rel = float(np.clip(learned[i] / 3.0, 0, 1))
            c["score"] = 0.0 if c["fails"] else 0.8 * rel + 0.2 * h
        else:
            c["score"] = h
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands, ("gbdt" if learned is not None else "heuristic")


def _breakdown(c: dict, profile: PatientProfile) -> Dict[str, float]:
    f = c["features"]
    if f["has_location"]:
        prox = max(0.0, 1 - math.expm1(f["log_dist"]) / max(1.0, 2.5 * profile.max_distance_mi))
    else:
        prox = None
    return {
        "condition": round(c["cond"]["condition_score"], 3),
        "semantic": round(max(0.0, f["vec_sim"]), 3),
        "eligibility": round(c["eval"]["eligibility_score"], 3),
        "coverage": c["eval"]["coverage"],
        "proximity": None if prox is None else round(prox, 3),
    }


def summarise(c: dict, profile: PatientProfile, with_criteria: bool = False) -> dict:
    t, ev, d = c["trial"], c["eval"], c["dist"]
    reasons_for, reasons_against = [], []
    if c["cond"]["matched"]:
        reasons_for.append(f"Studies {c['cond']['matched']}")
    for item in ev["criteria"]:
        if item["status"] == "met" and item["concept"] not in ("diagnosis",) and len(reasons_for) < 4:
            reasons_for.append(item["reason"])
        if item["status"] in ("not_met", "caution"):
            reasons_against.append({"status": item["status"], "reason": item["reason"], "text": item["text"][:220]})
    for f in c["fails"]:
        reasons_against.insert(0, {"status": "not_met", "reason": f["reason"], "text": ""})
    nearest = None
    if d.get("nearest_mi") is not None:
        nearest = {"facility": d.get("facility"), "city": d.get("city"), "state": d.get("state"),
                   "lat": d.get("lat"), "lon": d.get("lon"), "distance_mi": round(float(d["nearest_mi"]), 1)}
    out = {
        "nct_id": t["nct_id"],
        "title": t["title"],
        "summary": (t.get("summary") or "")[:400],
        "status": t["status"],
        "phase": t["phase"],
        "study_type": t["study_type"],
        "sponsor": t["sponsor"],
        "conditions": t["conditions"][:6],
        "interventions": [i.get("name") for i in (t.get("interventions") or [])][:4],
        "enrollment": t.get("enrollment"),
        "last_update": t.get("last_update"),
        "sex": t.get("sex"),
        "min_age": t.get("min_age_years"),
        "max_age": t.get("max_age_years"),
        "score": round(100 * c["score"], 1),
        "verdict": c["verdict"],
        "breakdown": _breakdown(c, profile),
        "counts": ev["counts"],
        "parser": ev["parser"],
        "reasons_for": reasons_for[:4],
        "reasons_against": reasons_against[:4],
        "nearest_site": nearest,
        "sites_in_range": int(d.get("sites_in_range") or 0),
        "total_sites": int(d.get("total_sites") or 0),
    }
    if with_criteria:
        out["criteria"] = ev["criteria"]
    return out


def search(profile: PatientProfile, limit: int = 40) -> Dict:
    retrieved = retrieve(profile)
    cands = score_candidates(profile, retrieved)
    relevant = [c for c in cands if c["cond"]["condition_score"] >= 0.6
                or (c["cond"]["condition_score"] >= 0.35 and c["features"]["vec_sim"] >= 0.6)]
    hidden = {"age": 0, "sex": 0, "healthy_volunteers": 0, "distance": 0}
    shown = []
    for c in relevant:
        if c["fails"]:
            hidden[c["fails"][0]["field"]] += 1
            continue
        if profile.location and (c["dist"].get("nearest_mi") is None or c["dist"]["nearest_mi"] > profile.max_distance_mi):
            hidden["distance"] += 1
            continue
        shown.append(c)
    ranked, method = rank(profile, shown)
    results = [summarise(c, profile) for c in ranked[:limit]]
    verdicts = {v: sum(1 for c in ranked if c["verdict"] == v) for v in ("likely_eligible", "possible", "likely_ineligible")}
    return {
        "results": results,
        "total": len(ranked),
        "candidates_considered": len(cands),
        "hidden": hidden,
        "verdicts": verdicts,
        "ranking_method": method,
    }
