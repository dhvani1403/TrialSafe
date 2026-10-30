"""Parsing accuracy against the hand-labelled gold criterion set.

Metrics
  - concept detection: micro precision / recall / F1 over (line, concept) pairs, overall and per category
  - operator accuracy: on correctly detected concepts whose gold operator is scored
  - threshold accuracy: numeric bounds within tolerance, for numeric concepts
  - negative-line false-positive rate: lines that constrain nothing in the vocabulary
  - age agreement (corpus-wide): free-text age bounds vs ClinicalTrials.gov structured age fields
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..db import execute, fetch_all, jsonb
from ..parsing import rules
from ..parsing.schema import Criterion, CriterionLine
from ..vocab import CATEGORIES, CONCEPTS

log = logging.getLogger(__name__)
GOLD_PATH = settings.gold_dir / "criteria_gold.jsonl"


def load_gold() -> Tuple[List[dict], str]:
    """Human-verified lines once there are enough of them, else the AI-drafted file."""
    from ..annotations import MIN_VERIFIED, verified_gold
    try:
        verified = verified_gold()
    except Exception:  # table missing in a fresh database
        verified = []
    if len(verified) >= MIN_VERIFIED:
        return verified, f"human-verified ({len(verified)} lines)"
    drafted = [json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()]
    return drafted, f"AI-drafted, unverified ({len(verified)} of {MIN_VERIFIED} needed lines verified so far)"


def _prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def _close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(0.01, 0.02 * abs(b))


def score(gold: List[dict], predicted: Dict[int, List[Criterion]]) -> Dict:
    tp = fp = fn = 0
    cat = defaultdict(lambda: [0, 0, 0])
    op_total = op_ok = num_total = num_ok = 0
    neg_lines = neg_fp = 0
    errors: List[dict] = []

    for g in gold:
        gold_by = {lab["concept"]: lab for lab in g["labels"]}
        pred_by = {c.concept: c for c in predicted.get(g["id"], [])}
        if not gold_by:
            neg_lines += 1
            neg_fp += bool(pred_by)
        for concept in set(gold_by) | set(pred_by):
            category = CONCEPTS[concept].category if concept in CONCEPTS else "other"
            if concept in gold_by and concept in pred_by:
                tp += 1
                cat[category][0] += 1
                gl, pr = gold_by[concept], pred_by[concept]
                if gl["operator"] is not None:
                    op_total += 1
                    ok = gl["operator"] == pr.operator
                    if ok and gl["operator"] in (">=", "<=", "between"):
                        num_total += 1
                        lo_ok = _close(pr.value, gl["value"])
                        hi_ok = gl["operator"] != "between" or _close(pr.value_max, gl["value_max"])
                        num_ok += lo_ok and hi_ok
                        ok = ok and lo_ok and hi_ok
                    op_ok += ok
                    if not ok:
                        errors.append({"id": g["id"], "text": g["text"], "type": "operator", "concept": concept,
                                       "gold": f'{gl["operator"]} {gl["value"]} {gl["value_max"]}',
                                       "pred": f"{pr.operator} {pr.value} {pr.value_max}"})
            elif concept in pred_by:
                fp += 1
                cat[category][1] += 1
                errors.append({"id": g["id"], "text": g["text"], "type": "false_positive", "concept": concept})
            else:
                fn += 1
                cat[category][2] += 1
                errors.append({"id": g["id"], "text": g["text"], "type": "missed", "concept": concept})

    return {
        "overall": _prf(tp, fp, fn),
        "by_category": {k: {"label": CATEGORIES.get(k, k), **_prf(*v)} for k, v in sorted(cat.items())},
        "operator_accuracy": round(op_ok / op_total, 3) if op_total else None,
        "threshold_accuracy": round(num_ok / num_total, 3) if num_total else None,
        "negative_line_fp_rate": round(neg_fp / neg_lines, 3) if neg_lines else None,
        "n_lines": len(gold),
        "n_labels": sum(len(g["labels"]) for g in gold),
        "errors": errors[:60],
    }


def _as_lines(gold: List[dict]) -> List[CriterionLine]:
    return [CriterionLine(index=g["id"], kind=g["kind"], text=g["text"]) for g in gold]


def predict_rules(gold: List[dict]) -> Dict[int, List[Criterion]]:
    return {ln.index: rules.parse_line(ln) for ln in _as_lines(gold)}


def predict_llm(gold: List[dict]) -> Tuple[Dict[int, List[Criterion]], str]:
    from ..parsing.llm_parser import annotate_lines
    criteria, model = annotate_lines(_as_lines(gold), purpose="eval")
    out: Dict[int, List[Criterion]] = defaultdict(list)
    for c in criteria:
        out[c.line].append(c)
    return out, model


def age_agreement() -> Dict:
    """How often free-text age bounds agree with the structured min/max age fields."""
    rows = fetch_all(
        """SELECT p.parser, p.parsed->>'min_age' AS pmin, p.parsed->>'max_age' AS pmax,
                  t.min_age_years AS smin, t.max_age_years AS smax
           FROM parsed_eligibility p JOIN trials t USING (nct_id)
           WHERE p.criteria_hash = t.criteria_hash"""
    )
    out: Dict[str, Dict] = {}
    for parser in sorted({r["parser"] for r in rows}):
        rs = [r for r in rows if r["parser"] == parser]
        found = [r for r in rs if r["pmin"] is not None and r["smin"] is not None]
        agree = sum(1 for r in found if abs(float(r["pmin"]) - float(r["smin"])) < 1)
        out[parser] = {"trials": len(rs), "min_age_found": len(found),
                       "min_age_agreement": round(agree / len(found), 3) if found else None}
    return out


def run_parsing_eval(with_llm: bool = False) -> Dict:
    gold, gold_source = load_gold()
    report: Dict = {
        "gold_path": str(GOLD_PATH.name),
        "gold_source": gold_source,
        "notes": [
            "Gold lines: 121 sampled stratified on concepts the rules parser detected (<=3 per concept) plus 25 "
            "random lines; 7 ambiguous lines dropped. Stratifying on rule detections biases rules recall upward.",
            "Labels were drafted by an AI assistant following the literal-polarity guideline; have a clinician "
            "spot-check them before citing these numbers.",
            "Rules parser v1.2: 'or' ranges, numbers written before the keyword, contractions (\"don't\") and the "
            "phrase 'heart disease' were fixed after evaluation runs, so its score is slightly optimistic.",
        ],
        "parsers": {},
    }
    report["parsers"]["rules"] = score(gold, predict_rules(gold))

    previous = fetch_all("SELECT report FROM eval_reports WHERE kind = 'parsing'")
    if with_llm:
        try:
            pred, model = predict_llm(gold)
            report["parsers"]["llm"] = {**score(gold, pred), "model": model}
        except Exception as exc:
            log.warning("LLM eval skipped: %s", exc)
            report["llm_error"] = str(exc)
    if "llm" not in report["parsers"] and previous and "llm" in previous[0]["report"].get("parsers", {}):
        # keep the last LLM score rather than spending quota on every run
        report["parsers"]["llm"] = previous[0]["report"]["parsers"]["llm"]

    report["age_agreement"] = age_agreement()
    report["summary"] = {
        name: {"f1": r["overall"]["f1"], "precision": r["overall"]["precision"], "recall": r["overall"]["recall"],
               "operator_accuracy": r["operator_accuracy"], "negative_line_fp_rate": r["negative_line_fp_rate"]}
        for name, r in report["parsers"].items()
    }
    execute(
        """INSERT INTO eval_reports (kind, report) VALUES ('parsing', %s)
           ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
        (jsonb(report),),
    )
    return report
