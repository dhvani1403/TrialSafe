"""TREC 2021 Clinical Trials track benchmark: real patients, expert relevance judgements.

75 topics (free-text patient notes) with ~35k judgements over ~26k ClinicalTrials.gov trials:
0 = not relevant, 1 = excluded (relevant but ineligible), 2 = eligible.

Run against a SEPARATE database so closed, historical trials never reach patient searches:
    DATABASE_URL=postgresql://localhost:5432/trialmatch_bench ARTIFACTS_DIR=artifacts/bench \\
        python -m scripts.cli trec
The report is written into the main database (PROD_DATABASE_URL) for the insights page.

Setting: re-rank each topic's judged pool (the standard re-ranking protocol), with the patient
profile extracted from the note by app.profile_extract (no LLM, no human input).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List

import httpx
import numpy as np

from .. import ctgov, embeddings
from ..config import BACKEND_DIR, settings
from ..db import connect, fetch_all, jsonb
from ..ingest import _store
from ..matching import PatientProfile
from ..ranking import features as F
from ..ranking.train import ndcg_at_k
from ..search import score_candidates

log = logging.getLogger(__name__)
DATA = BACKEND_DIR / "data" / "trec"
BASE = "https://trec.nist.gov/data/trials"
FIELDS = ",".join([
    "protocolSection.identificationModule", "protocolSection.statusModule.overallStatus",
    "protocolSection.conditionsModule", "protocolSection.eligibilityModule", "protocolSection.designModule",
    "protocolSection.descriptionModule.briefSummary", "protocolSection.armsInterventionsModule.interventions",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor", "derivedSection.conditionBrowseModule",
])


def _guard_bench_db() -> None:
    if "bench" not in settings.database_url:
        raise SystemExit("Refusing to load TREC trials into the patient-facing database. "
                         "Set DATABASE_URL to the benchmark database (see module docstring).")


def download(year: int = 2021) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in (f"topics{year}.xml", f"qrels{year}.txt"):
        path = DATA / name
        if not path.exists():
            resp = httpx.get(f"{BASE}/{name}", timeout=60)
            resp.raise_for_status()
            path.write_bytes(resp.content)


def load_topics(year: int = 2021) -> Dict[str, str]:
    root = ET.parse(DATA / f"topics{year}.xml").getroot()
    return {t.attrib["number"]: (t.text or "").strip() for t in root.iter("topic")}


def load_qrels(year: int = 2021) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = defaultdict(dict)
    for line in (DATA / f"qrels{year}.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) == 4:
            out[parts[0]][parts[2]] = int(parts[3])
    return out


def ingest_judged(year: int = 2021, batch: int = 300) -> Dict:
    _guard_bench_db()
    qrels = load_qrels(year)
    ids = sorted({nct for judged in qrels.values() for nct in judged})
    have = {r["nct_id"] for r in fetch_all("SELECT nct_id FROM trials")}
    todo = [i for i in ids if i not in have]
    stored = 0
    with httpx.Client(headers={"User-Agent": "TrialMatch/1.0 (research benchmark)"}) as client:
        for start in range(0, len(todo), batch):
            chunk = todo[start:start + batch]
            for attempt in range(4):
                try:
                    resp = client.get(ctgov.API, params={"filter.ids": ",".join(chunk), "pageSize": 1000,
                                                         "fields": FIELDS}, timeout=60)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            with connect() as conn, conn.cursor() as cur:
                for study in resp.json().get("studies", []):
                    record = ctgov.normalise(study)
                    if record["nct_id"]:
                        _store(cur, record, {}, f"trec{year}")
                        stored += 1
            log.info("bench ingest %d/%d", min(start + batch, len(todo)), len(todo))
    return {"judged_trials": len(ids), "already_present": len(have), "fetched": stored}


def _retrieval_scores(text: str, ids: List[str]) -> Dict[str, Dict[str, float]]:
    """BM25-style and embedding scores for every judged trial, plus RRF of the two rankings."""
    words = sorted({w for w in re.findall(r"[a-z][a-z0-9]{2,}", text.lower())})
    lexemes = fetch_all("SELECT unnest(tsvector_to_array(to_tsvector('english', %s))) AS l", (" ".join(words),))
    query = " | ".join(f"'{r['l']}'" for r in lexemes if re.fullmatch(r"[a-z0-9]+", r["l"]))
    fts = fetch_all(
        """SELECT nct_id, ts_rank_cd(search_tsv, to_tsquery('simple', %s), 32) AS r
           FROM trials WHERE nct_id = ANY(%s)""", (query or "''", ids)) if query else []
    qvec = embeddings.encode([text])[0]
    vec = fetch_all("SELECT nct_id, 1 - (embedding <=> %s) AS s FROM trials WHERE nct_id = ANY(%s)", (qvec, ids))
    out = {i: {"rrf": 0.0, "fts": 0.0, "vec": 0.0} for i in ids}
    for key, rows, col in (("fts", fts, "r"), ("vec", vec, "s")):
        for rank, r in enumerate(sorted(rows, key=lambda r: -float(r[col] or 0))):
            out[r["nct_id"]][key] = float(r[col] or 0)
            out[r["nct_id"]]["rrf"] += 1.0 / (60 + rank + 1)
    return out


def _profile(note: str) -> PatientProfile:
    from ..profile_extract import extract
    p = extract(note)["profile"]
    return PatientProfile(
        conditions=p.get("conditions", []), age=p.get("age", 50), sex=p.get("sex", "female"),
        **{k: v for k, v in p.items() if k not in ("conditions", "age", "sex")},
    )


def _metrics(labels_in_order: List[int]) -> Dict[str, float]:
    top = labels_in_order[:10]
    first = next((i for i, l in enumerate(labels_in_order) if l == 2), None)
    return {"ndcg@10": ndcg_at_k(labels_in_order, 10), "p@10": sum(1 for l in top if l == 2) / 10,
            "mrr": 0.0 if first is None else 1.0 / (first + 1)}


PAIRS_PATH = BACKEND_DIR / "artifacts" / "trec_pairs.json"
SYNTH_PATH = BACKEND_DIR / "artifacts" / "synthetic_pairs.json"


def _score_groups(year: int):
    topics, qrels = load_topics(year), load_qrels(year)
    groups, no_condition = [], 0
    for tid, note in topics.items():
        judged = qrels.get(tid, {})
        present = [r["nct_id"] for r in fetch_all("SELECT nct_id FROM trials WHERE nct_id = ANY(%s)", (list(judged),))]
        if not present:
            continue
        profile = _profile(note)
        no_condition += not profile.conditions
        cands = score_candidates(profile, _retrieval_scores(note, present))
        rows = [{"nct": c["trial"]["nct_id"], "label": judged[c["trial"]["nct_id"]], "features": c["features"],
                 "heuristic": F.heuristic(c["features"], profile.max_distance_mi),
                 "elig": c["eval"]["eligibility_score"], "verdict": c["verdict"]} for c in cands]
        groups.append({"topic": tid, "rows": rows})
        log.info("topic %s: %d judged trials scored", tid, len(rows))
    return groups, no_condition


def evaluate(year: int = 2021, reuse: bool = False) -> Dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import roc_auc_score

    from ..ranking.model import matrix

    if reuse and PAIRS_PATH.exists():
        saved = json.loads(PAIRS_PATH.read_text())
        groups, no_condition = saved["groups"], saved["no_condition"]
    else:
        groups, no_condition = _score_groups(year)
        PAIRS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PAIRS_PATH.write_text(json.dumps({"groups": groups, "no_condition": no_condition}))
    synth_ranker_path = BACKEND_DIR / "artifacts" / "ranker_synthetic.joblib"
    synth_ranker = joblib.load(synth_ranker_path if synth_ranker_path.exists()
                               else BACKEND_DIR / "artifacts" / "ranker.joblib")["model"]
    synthetic = json.loads(SYNTH_PATH.read_text())["groups"] if SYNTH_PATH.exists() else []
    rng = np.random.default_rng(7)

    def run(score_fn, gs) -> Dict[str, float]:
        per = []
        for g in gs:
            scores = np.asarray(score_fn(g["rows"]), dtype=float)
            order = np.argsort(-scores, kind="stable")
            per.append(_metrics([g["rows"][i]["label"] for i in order]))
        return {k: round(float(np.mean([p[k] for p in per])), 4) for k in per[0]}

    col = lambda name: (lambda rows: [r["features"][name] for r in rows])  # noqa: E731
    methods = {
        "Random": lambda rows: rng.random(len(rows)),
        "BM25 (Postgres full-text)": col("fts_rank"),
        "Semantic (embeddings)": col("vec_sim"),
        "Hybrid RRF": col("rrf"),
        "Heuristic (condition × eligibility)": lambda rows: [r["heuristic"] for r in rows],
        "GBDT, synthetic labels only": lambda rows: synth_ranker.predict(matrix([r["features"] for r in rows])),
    }
    results = {name: run(fn, groups) for name, fn in methods.items()}

    # supervised on the expert labels: 5-fold cross-validation split by topic
    folds = np.array_split(np.arange(len(groups)), 5)

    def cv(extra: List[Dict]) -> Dict[str, float]:
        scores = []
        for k, test_idx in enumerate(folds):
            held = set(test_idx.tolist())
            train = [groups[i] for i in range(len(groups)) if i not in held] + extra
            X = matrix([r["features"] for g in train for r in g["rows"]])
            y = np.array([r["label"] for g in train for r in g["rows"]], dtype=float)
            m = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, min_samples_leaf=30,
                                              l2_regularization=1.0, random_state=k).fit(X, y)
            scores.append(run(lambda rows, m=m: m.predict(matrix([r["features"] for r in rows])),
                              [groups[i] for i in test_idx]))
        return {key: round(float(np.mean([s[key] for s in scores])), 4) for key in scores[0]}

    results["GBDT, trained on TREC (5-fold CV)"] = cv([])
    if synthetic:
        # this is how the production ranker is trained (synthetic + all TREC), scored without leakage
        results["GBDT, synthetic + TREC (production, 5-fold CV)"] = cv(synthetic)

    # Does the eligibility checker separate "eligible" (2) from "excluded" (1)?
    pairs = [r for g in groups for r in g["rows"] if r["label"] in (1, 2)]
    y_true = np.array([r["label"] == 2 for r in pairs])
    elig_auc = float(roc_auc_score(y_true, [r["elig"] for r in pairs])) if len(set(y_true)) == 2 else None
    flagged = np.array([r["verdict"] in ("ineligible", "likely_ineligible") for r in pairs])
    excluded = ~y_true
    eligibility = {
        "pairs": len(pairs),
        "auc_eligibility_score": None if elig_auc is None else round(elig_auc, 4),
        "flag_precision": round(float((flagged & excluded).sum() / max(1, flagged.sum())), 4),
        "flag_recall": round(float((flagged & excluded).sum() / max(1, excluded.sum())), 4),
        "base_rate_excluded": round(float(excluded.mean()), 4),
    }
    label_counts = defaultdict(int)
    for g in groups:
        for r in g["rows"]:
            label_counts[str(r["label"])] += 1
    report = {
        "year": year, "topics": len(groups), "pairs": sum(len(g["rows"]) for g in groups),
        "label_distribution": dict(label_counts), "topics_without_condition_match": no_condition,
        "results": results, "eligibility": eligibility,
        "protocol": "Re-rank each topic's judged pool. Profiles extracted from the notes without an LLM. "
                    "NDCG@10 uses gains 0/1/2; P@10 and MRR count only 'eligible' (2).",
    }
    _publish(report)
    (DATA / f"report{year}.json").write_text(json.dumps(report, indent=2))
    return report


def _publish(report: Dict) -> None:
    import psycopg2
    url = os.environ.get("PROD_DATABASE_URL", "postgresql://localhost:5432/trialmatch")
    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO eval_reports (kind, report) VALUES ('trec', %s)
                   ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
                (jsonb(report),),
            )
    finally:
        conn.close()


def run_all(year: int = 2021, reuse: bool = False) -> Dict:
    if reuse:
        return evaluate(year, reuse=True)
    _guard_bench_db()
    from ..parsing.service import parse_all_rules
    from ..profile_extract import reset_vocab_cache
    download(year)
    info = ingest_judged(year)
    log.info("ingest: %s", info)
    log.info("rules-parsed %d", parse_all_rules())
    log.info("embedded %d", embeddings.embed_all_trials())
    reset_vocab_cache()
    return evaluate(year)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_all(), indent=2)[:3000])

