"""Weakly supervised training + offline evaluation of the trial ranker.

There are no public patient-trial relevance judgements, so we synthesise them:
  1. pick a "seed" trial and build a plausible patient for it (its condition in everyday words,
     an age inside its range, a home near one of its sites, a random health history);
  2. retrieve candidates for that patient with the production pipeline;
  3. grade each candidate:  3 = the seed trial
                            2 = shares a specific MeSH condition with the seed, eligible and in range
                            1 = shares a MeSH condition but ineligible / far, or shares a specific ancestor
                            0 = otherwise.
Labels come from MeSH relations to the seed, which the features only see indirectly, but the
eligibility signal is shared, so treat absolute scores as optimistic; the comparison between
rankers on held-out seeds is the useful part.
"""
from __future__ import annotations

import json
import logging
import math
import random
from typing import Dict, List

import numpy as np

from ..db import execute, fetch_all, jsonb
from ..geo import AUDIT_LOCATIONS
from ..matching import Location, PatientProfile
from ..search import retrieve, score_candidates
from . import features as F
from .model import MODEL_PATH, reload

log = logging.getLogger(__name__)
rng = random.Random(13)

_COMORB = ["diabetes", "heart_disease", "kidney_disease", "hiv", "hepatitis", "autoimmune_disease", "other_malignancy"]
_TREAT = ["chemotherapy", "immunotherapy", "radiation", "surgery", "targeted_therapy", "hormone_therapy"]


def _synth_profile(seed: dict, sites: List[dict]) -> PatientProfile:
    lo = max(18.0, seed["min_age_years"] or 18.0)
    hi = min(85.0, seed["max_age_years"] or 85.0)
    if hi < lo:
        lo, hi = seed["min_age_years"] or 18.0, seed["max_age_years"] or 85.0
    condition = rng.choice(
        [seed["source_query"]] * 3 + [c.lower() for c in seed["conditions"][:2]] + [m.lower() for m in seed["mesh_terms"][:1]]
    )
    sex = seed["sex"].lower() if seed["sex"] in ("FEMALE", "MALE") else rng.choice(["female", "male"])
    if rng.random() < 0.75 and sites:
        s = rng.choice(sites)
        loc = Location(lat=s["lat"] + rng.uniform(-0.35, 0.35), lon=s["lon"] + rng.uniform(-0.35, 0.35))
    else:
        _, lat, lon, _, _ = rng.choice(AUDIT_LOCATIONS)
        loc = Location(lat=lat, lon=lon)
    answered = rng.random() < 0.7
    return PatientProfile(
        conditions=[condition], age=int(rng.uniform(lo, hi)), sex=sex, location=loc,
        max_distance_mi=rng.choice([50, 100, 250]),
        ecog=rng.choice([None, 0, 1, 1, 2]) if "cancer" in condition or "oma" in condition else None,
        comorbidities=[c for c in _COMORB if rng.random() < 0.08] if answered else None,
        treatments=[t for t in _TREAT if rng.random() < 0.15] if answered else None,
        pregnant=False if sex == "female" and rng.random() < 0.6 else None,
    )


def _label(cand: dict, seed: dict, profile: PatientProfile) -> int:
    t = cand["trial"]
    if t["nct_id"] == seed["nct_id"]:
        return 3
    seed_mesh = set(seed["mesh_terms"])
    seed_anc = {a for a in seed["mesh_ancestors"] if a.lower() not in F._GENERIC}
    shares = bool(seed_mesh & set(t["mesh_terms"] or []))
    near = cand["dist"].get("nearest_mi") is not None and cand["dist"]["nearest_mi"] <= profile.max_distance_mi
    eligible = cand["verdict"] in ("likely_eligible", "possible")
    if shares and eligible and near:
        return 2
    if shares or (seed_anc & set(t["mesh_terms"] or [])):
        return 1
    return 0


def build_dataset(n_queries: int = 260) -> List[Dict]:
    seeds = fetch_all(
        """SELECT nct_id, conditions, mesh_terms, mesh_ancestors, sex, min_age_years, max_age_years, source_query
           FROM trials WHERE cardinality(mesh_terms) > 0 AND status = 'RECRUITING' AND source_query IS NOT NULL
           ORDER BY md5(nct_id || 'seed') LIMIT %s""",
        (n_queries,),
    )
    groups = []
    for qi, seed in enumerate(seeds):
        sites = fetch_all("SELECT lat, lon FROM sites WHERE nct_id = %s AND lat IS NOT NULL AND country = 'United States'",
                          (seed["nct_id"],))
        profile = _synth_profile(seed, sites)
        retrieved = retrieve(profile, pool=120)
        cands = score_candidates(profile, retrieved)
        rows = []
        for c in cands:
            rows.append({"features": c["features"], "label": _label(c, seed, profile),
                         "heuristic": F.heuristic(c["features"], profile.max_distance_mi),
                         "is_seed": c["trial"]["nct_id"] == seed["nct_id"]})
        if any(r["label"] > 0 for r in rows):
            groups.append({"qid": qi, "seed": seed["nct_id"], "condition": profile.conditions[0], "rows": rows})
        if qi % 50 == 0:
            log.info("built %d/%d query groups", qi, len(seeds))
    return groups


def ndcg_at_k(labels: List[int], k: int = 10) -> float:
    dcg = sum((2 ** l - 1) / math.log2(i + 2) for i, l in enumerate(labels[:k]))
    ideal = sorted(labels, reverse=True)
    idcg = sum((2 ** l - 1) / math.log2(i + 2) for i, l in enumerate(ideal[:k]))
    return dcg / idcg if idcg else 0.0


def evaluate_ranker(groups: List[Dict], score_fn) -> Dict[str, float]:
    ndcgs, mrrs, recall = [], [], []
    for g in groups:
        scores = score_fn(g["rows"])
        order = np.argsort(-np.asarray(scores), kind="stable")
        labels = [g["rows"][i]["label"] for i in order]
        ndcgs.append(ndcg_at_k(labels, 10))
        seed_rank = next((r for r, i in enumerate(order) if g["rows"][i]["is_seed"]), None)
        mrrs.append(0.0 if seed_rank is None else 1.0 / (seed_rank + 1))
        rel = sum(1 for l in labels if l >= 2)
        recall.append(sum(1 for l in labels[:10] if l >= 2) / min(10, rel) if rel else 1.0)
    return {"ndcg@10": round(float(np.mean(ndcgs)), 4), "mrr_seed": round(float(np.mean(mrrs)), 4),
            "recall@10": round(float(np.mean(recall)), 4)}


def train_and_evaluate(n_queries: int = 260) -> Dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance

    from .model import matrix

    groups = build_dataset(n_queries)
    rng.shuffle(groups)
    cut = int(0.8 * len(groups))
    train, test = groups[:cut], groups[cut:]
    Xtr = matrix([r["features"] for g in train for r in g["rows"]])
    ytr = np.array([r["label"] for g in train for r in g["rows"]], dtype=np.float32)

    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                          min_samples_leaf=20, l2_regularization=1.0, random_state=7)
    model.fit(Xtr, ytr)

    def col(name):
        return lambda rows: [r["features"][name] for r in rows]

    baselines = {
        "BM25 (Postgres full-text)": col("fts_rank"),
        "Semantic (embeddings)": col("vec_sim"),
        "Hybrid RRF": col("rrf"),
        "Heuristic (condition × eligibility × distance)": lambda rows: [r["heuristic"] for r in rows],
        "Learned GBDT (ours)": lambda rows: model.predict(matrix([r["features"] for r in rows])),
    }
    results = {name: evaluate_ranker(test, fn) for name, fn in baselines.items()}

    Xte = matrix([r["features"] for g in test for r in g["rows"]])
    yte = np.array([r["label"] for g in test for r in g["rows"]], dtype=np.float32)
    imp = permutation_importance(model, Xte, yte, n_repeats=5, random_state=7)
    importances = sorted(
        [{"feature": f, "importance": round(float(m), 4)} for f, m in zip(F.FEATURES, imp.importances_mean)],
        key=lambda d: -d["importance"],
    )

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"model": model, "features": F.FEATURES}, MODEL_PATH.with_name("ranker_synthetic.joblib"))
    slim = [{"rows": [{"features": r["features"], "label": r["label"]} for r in g["rows"]]} for g in groups]
    MODEL_PATH.with_name("synthetic_pairs.json").write_text(json.dumps({"groups": slim}))

    # Production model: synthetic pairs (teach distance and eligibility) + TREC expert pairs if available
    trec_path = MODEL_PATH.with_name("trec_pairs.json")
    production, trained_on = model, "synthetic"
    if trec_path.exists():
        trec_groups = json.loads(trec_path.read_text())["groups"]
        X_all = np.vstack([Xtr, matrix([r["features"] for g in test for r in g["rows"]]),
                           matrix([r["features"] for g in trec_groups for r in g["rows"]])])
        y_all = np.concatenate([ytr, [r["label"] for g in test for r in g["rows"]],
                                [r["label"] for g in trec_groups for r in g["rows"]]]).astype(np.float32)
        production = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                                   min_samples_leaf=20, l2_regularization=1.0,
                                                   random_state=7).fit(X_all, y_all)
        trained_on = f"synthetic + TREC 2021 ({len(trec_groups)} expert-judged patients)"
    joblib.dump({"model": production, "features": F.FEATURES, "trained_on": trained_on}, MODEL_PATH)
    reload()

    label_dist = {str(k): int(v) for k, v in zip(*np.unique(np.concatenate([ytr, yte]), return_counts=True))}
    report = {
        "train_queries": len(train), "test_queries": len(test),
        "pairs": int(len(ytr) + len(yte)), "label_distribution": label_dist,
        "results": results, "feature_importance": importances[:14],
        "method": "Pointwise HistGradientBoostingRegressor on graded weak labels; held-out by seed trial.",
        "production_trained_on": trained_on,
    }
    execute(
        """INSERT INTO eval_reports (kind, report) VALUES ('ranking', %s)
           ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
        (jsonb(report),),
    )
    return {k: report[k] for k in ("train_queries", "test_queries", "pairs", "label_distribution", "results")}
