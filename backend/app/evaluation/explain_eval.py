"""Faithfulness and safety of plain-language explanations.

For a fixed set of synthetic patients we take real search results (the best matches plus one
"probably not" study, so there are conflicts to report), generate an AI explanation, and audit it
against the rule check before and after the guardrail, with the template explanation as baseline.
Each case costs one LLM call, so `limit` keeps it inside the free-tier budget.
"""
from __future__ import annotations

import copy
import logging
from typing import Dict, List

import numpy as np

from .. import guardrails
from ..db import execute, fetch_one, jsonb
from ..explain import generate, template
from ..llm import LLMUnavailable, budget_remaining
from ..matching import PatientProfile, evaluate_trial
from ..parsing.service import best_parse
from ..ranking import features as F
from ..search import search

log = logging.getLogger(__name__)

PATIENTS = [
    dict(conditions=["breast cancer"], age=54, sex="female", ecog=1, metastatic=True, pregnant=False,
         breastfeeding=False, comorbidities=[], treatments=["chemotherapy", "surgery"], medications=[]),
    dict(conditions=["type 2 diabetes"], age=63, sex="male", comorbidities=["heart_disease"],
         medications=["insulin"], smoker=False),
    dict(conditions=["lung cancer"], age=71, sex="male", ecog=2, smoker=True, treatments=["radiation"],
         comorbidities=["kidney_disease"], brain_metastases=True),
    dict(conditions=["asthma"], age=29, sex="female", pregnant=True, smoker=False, comorbidities=[]),
]


def _cases(per_patient: int) -> List[Dict]:
    cases = []
    for p in PATIENTS:
        profile = PatientProfile(**p, max_distance_mi=3000)
        res = search(profile, limit=60)["results"]
        picks = res[: per_patient - 1] + [r for r in res if r["verdict"] == "likely_ineligible"][:1]
        for r in picks:
            t = fetch_one("SELECT nct_id, title, summary, eligibility_text, criteria_hash, conditions, mesh_terms, "
                          "mesh_ancestors, min_age_years, max_age_years FROM trials WHERE nct_id = %s", (r["nct_id"],))
            parsed = best_parse(t["nct_id"], t["eligibility_text"], t["criteria_hash"])
            cond = F.condition_match(profile.conditions, t)
            ev = evaluate_trial(parsed, profile, cond["condition_score"], t["min_age_years"] is not None)
            cases.append({"trial": t, "profile": profile, "criteria": ev["criteria"]})
    return cases


def _summary(audits, bodies) -> Dict:
    audits, bodies = list(audits), list(bodies)
    n = max(1, len(audits))
    rate = lambda k: round(sum(1 for a in audits if a[k]) / n, 3)  # noqa: E731
    text = lambda b: " ".join([b.get("summary", "")] + [t for k in guardrails.LIST_KEYS for t in b.get(k, [])])  # noqa: E731
    return {
        "unsafe_rate": rate("unsafe"),
        "contradiction_rate": rate("contradiction"),
        "false_unknown_rate": rate("false_unknown"),
        "missed_conflict_rate": rate("missed_conflict"),
        "reading_grade": round(float(np.mean([guardrails.reading_grade(text(b)) for b in bodies])), 1) if bodies else None,
        "avg_items": round(float(np.mean([sum(len(b.get(k, [])) for k in guardrails.LIST_KEYS) for b in bodies])), 1)
        if bodies else None,
    }


def reaudit() -> Dict:
    """Re-score the stored outputs of the last run with the current guardrail code."""
    row = fetch_one("SELECT report FROM eval_reports WHERE kind = 'explanations'")
    if not row or not row["report"].get("raw_outputs"):
        raise SystemExit("no stored outputs; run eval-explain first")
    report = row["report"]
    raw, guarded, templ = [], [], []
    for o in report["raw_outputs"]:
        raw.append((guardrails.audit(o["body"], o["criteria"]), o["body"]))
        fixed = guardrails.apply(copy.deepcopy(o["body"]), o["criteria"])
        guarded.append((guardrails.audit(fixed, o["criteria"]), fixed))
        templ.append((guardrails.audit(o["template"], o["criteria"]), o["template"]))
    report.update({"llm_raw": _summary(*zip(*raw)), "llm_guarded": _summary(*zip(*guarded)),
                   "template": _summary(*zip(*templ)), "template_cases": len(templ)})
    execute("UPDATE eval_reports SET report = %s, created_at = now() WHERE kind = 'explanations'", (jsonb(report),))
    return report


def run_explain_eval(limit: int = 10) -> Dict:
    cases = _cases(per_patient=3)
    raw, guarded, templ, examples, stored = [], [], [], [], []
    model = None
    for case in cases:
        if len(raw) >= limit or budget_remaining() <= 1:
            break
        tb = template(case["trial"], case["criteria"])
        try:
            body = generate(case["trial"], case["criteria"], case["profile"])
        except LLMUnavailable as exc:
            log.warning("explanation failed: %s", exc)
            continue
        model = body.get("model")
        stored.append({"nct_id": case["trial"]["nct_id"], "criteria": case["criteria"], "body": body,
                       "template": tb})
        a = guardrails.audit(body, case["criteria"])
        raw.append((a, body))
        templ.append((guardrails.audit(tb, case["criteria"]), tb))
        fixed = guardrails.apply(copy.deepcopy(body), case["criteria"])
        guarded.append((guardrails.audit(fixed, case["criteria"]), fixed))
        if any(a[k] for k in ("unsafe", "contradiction", "false_unknown", "missed_conflict")) and len(examples) < 6:
            examples.append({"nct_id": case["trial"]["nct_id"], "issues": a, "changes": fixed.get("guardrail")})

    report = {
        "cases": len(raw), "model": model,
        "llm_raw": _summary([a for a, _ in raw], [b for _, b in raw]),
        "llm_guarded": _summary([a for a, _ in guarded], [b for _, b in guarded]),
        "template": _summary([a for a, _ in templ], [b for _, b in templ]),
        "template_cases": len(templ),
        "examples": examples,
        "raw_outputs": stored,  # lets `--reaudit` re-score after guardrail changes without new LLM calls
        "method": "Automatic audit against the rule check: unsafe phrasing, contradictions, answered items "
                  "called unclear, and conflicts left out. Reading grade is Flesch-Kincaid.",
    }
    execute(
        """INSERT INTO eval_reports (kind, report) VALUES ('explanations', %s)
           ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
        (jsonb(report),),
    )
    return report
