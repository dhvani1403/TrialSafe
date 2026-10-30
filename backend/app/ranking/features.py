"""Query-trial features for the learned ranker, plus the transparent heuristic baseline."""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

_STOP = {"of", "the", "and", "or", "with", "in", "a", "an", "for", "to", "disease", "disorder", "syndrome", "patients"}
_SYN = {
    "neoplasm": "cancer", "neoplasms": "cancer", "carcinoma": "cancer", "carcinomas": "cancer", "tumor": "cancer",
    "tumors": "cancer", "tumour": "cancer", "malignancy": "cancer", "malignant": "cancer", "cancers": "cancer",
    "adenocarcinoma": "cancer", "diabetic": "diabetes", "mellitus": "", "cardiac": "heart", "renal": "kidney",
    "hepatic": "liver", "pulmonary": "lung", "lungs": "lung", "alzheimer's": "alzheimer", "alzheimers": "alzheimer",
    "parkinson's": "parkinson", "parkinsons": "parkinson", "crohn's": "crohn", "crohns": "crohn", "t2d": "diabetes",
    "t1d": "diabetes", "copd": "copd", "depressive": "depression", "obese": "obesity", "hiv-1": "hiv",
    "leukaemia": "leukemia", "lymphomas": "lymphoma", "melanomas": "melanoma", "migraines": "migraine",
}
# Very generic MeSH ancestors carry no signal
_GENERIC = {"neoplasms", "diseases", "pathologic processes", "neoplasms by site", "neoplasms by histologic type",
            "signs and symptoms", "body weight", "nutrition disorders", "chronic disease", "disease attributes"}

FEATURES = [
    "rrf", "fts_rank", "vec_sim", "cond_lex", "cond_anc", "cond_title", "condition_score",
    "elig_score", "n_met", "n_not_met", "n_caution", "n_unknown", "coverage", "structured_fail",
    "has_location", "log_dist", "log_sites_in_range", "phase_num", "interventional", "recruiting",
    "log_enrollment", "recency_years", "industry",
]


def tokens(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9'\-]+", (text or "").lower()):
        w = _SYN.get(w, w)
        if w and w not in _STOP and len(w) > 1:
            out.add(w)
    return out


@lru_cache(maxsize=1)
def _idf() -> Dict[str, float]:
    """Inverse document frequency of condition tokens across the corpus, so that
    "breast" counts for more than "cancer" when matching "breast cancer"."""
    from ..db import fetch_all
    rows = fetch_all("SELECT conditions, mesh_terms FROM trials")
    df: Counter = Counter()
    for r in rows:
        df.update(set().union(*[tokens(t) for t in (r["conditions"] or []) + (r["mesh_terms"] or [])] or [set()]))
    n = max(1, len(rows))
    return {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}


def _w(words: Iterable[str]) -> float:
    idf = _idf()
    default = max(idf.values()) if idf else 1.0
    return sum(idf.get(w, default) for w in words)


def _coverage(query: set, terms: Iterable[str]) -> Tuple[float, Optional[str]]:
    best, best_term = 0.0, None
    if not query:
        return 0.0, None
    qw = _w(query)
    for t in terms:
        tt = tokens(t)
        if not tt:
            continue
        shared = query & tt
        cov = _w(shared) / qw
        # small penalty when the trial term is much more specific than the query
        prec = _w(shared) / _w(tt)
        s = 0.85 * cov + 0.15 * prec
        if s > best:
            best, best_term = s, t
    return best, best_term


def condition_match(conditions: List[str], trial: dict) -> Dict:
    """Lexical match of the patient's conditions against trial conditions, MeSH terms and title."""
    best = {"cond_lex": 0.0, "cond_anc": 0.0, "cond_title": 0.0, "matched": None}
    for c in conditions:
        q = tokens(c)
        lex, term = _coverage(q, (trial.get("conditions") or []) + (trial.get("mesh_terms") or []))
        anc, aterm = _coverage(q, [a for a in trial.get("mesh_ancestors") or [] if a.lower() not in _GENERIC])
        title, _ = _coverage(q, [trial.get("title") or ""])
        if lex > best["cond_lex"]:
            best["cond_lex"], best["matched"] = lex, term
        best["cond_anc"] = max(best["cond_anc"], anc)
        best["cond_title"] = max(best["cond_title"], title)
        if best["matched"] is None and aterm and anc > 0.5:
            best["matched"] = aterm
    best["condition_score"] = round(max(best["cond_lex"], 0.65 * best["cond_anc"], 0.8 * best["cond_title"]), 4)
    return best


def phase_num(phase: Optional[str]) -> float:
    if not phase or phase == "NA":
        return 0.0
    nums = [float(n) for n in re.findall(r"PHASE(\d)", phase)]
    if "EARLY_PHASE1" in phase:
        nums.append(0.5)
    return max(nums) if nums else 0.0


def build(trial: dict, cond: Dict, ev: Dict, retrieval: Dict, dist: Dict, structured_fails: List, has_location: bool) -> Dict[str, float]:
    today = date.today()
    lu = trial.get("last_update")
    nearest = dist.get("nearest_mi")
    return {
        "rrf": retrieval.get("rrf", 0.0),
        "fts_rank": retrieval.get("fts", 0.0),
        "vec_sim": retrieval.get("vec", 0.0),
        "cond_lex": cond["cond_lex"],
        "cond_anc": cond["cond_anc"],
        "cond_title": cond["cond_title"],
        "condition_score": cond["condition_score"],
        "elig_score": ev["eligibility_score"],
        "n_met": ev["counts"]["met"],
        "n_not_met": ev["counts"]["not_met"],
        "n_caution": ev["counts"]["caution"],
        "n_unknown": ev["counts"]["unknown"],
        "coverage": ev["coverage"],
        "structured_fail": float(bool(structured_fails)),
        "has_location": float(has_location),
        "log_dist": math.log1p(nearest) if nearest is not None else math.log1p(3000),
        "log_sites_in_range": math.log1p(dist.get("sites_in_range") or 0),
        "phase_num": phase_num(trial.get("phase")),
        "interventional": float(trial.get("study_type") == "INTERVENTIONAL"),
        "recruiting": float(trial.get("status") == "RECRUITING"),
        "log_enrollment": math.log1p(trial.get("enrollment") or 0),
        "recency_years": ((today - lu).days / 365.0) if lu else 5.0,
        "industry": float(trial.get("sponsor_class") == "INDUSTRY"),
    }


def heuristic(f: Dict[str, float], max_distance_mi: float) -> float:
    """Transparent baseline: condition fit x eligibility x proximity."""
    dist_mi = math.expm1(f["log_dist"])
    proximity = 1.0 if not f["has_location"] else max(0.15, 1 - dist_mi / max(1.0, 2.5 * max_distance_mi))
    semantic = max(0.0, min(1.0, f["vec_sim"]))
    fit = 0.75 * f["condition_score"] + 0.25 * semantic
    freshness = 1.0 if f["recency_years"] < 1 else 0.92
    return fit * (0.35 + 0.65 * f["elig_score"]) * (0.6 + 0.4 * proximity) * freshness * (0.0 if f["structured_fail"] else 1.0)
