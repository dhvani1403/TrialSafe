"""Patient profile model and criterion-level eligibility evaluation."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .parsing.schema import Criterion, ParsedEligibility
from .vocab import BOOL, CONCEPTS


class Location(BaseModel):
    lat: float
    lon: float
    label: str = ""


class PatientProfile(BaseModel):
    conditions: List[str] = Field(default_factory=list)
    age: int = Field(ge=0, le=120)
    sex: str = Field("female", pattern="^(female|male)$")
    location: Optional[Location] = None
    max_distance_mi: float = 100
    healthy_volunteer: bool = False
    pregnant: Optional[bool] = None
    breastfeeding: Optional[bool] = None
    ecog: Optional[int] = Field(None, ge=0, le=4)
    metastatic: Optional[bool] = None
    brain_metastases: Optional[bool] = None
    smoker: Optional[bool] = None
    bmi: Optional[float] = None
    hba1c: Optional[float] = None
    egfr: Optional[float] = None
    in_other_trial: Optional[bool] = None
    # None = question not answered; [] = answered "none of these"
    comorbidities: Optional[List[str]] = None
    treatments: Optional[List[str]] = None
    medications: Optional[List[str]] = None


# condition text -> comorbidity flags implied by having that condition
_IMPLIED = [
    (re.compile(r"diabet", re.I), "diabetes"),
    (re.compile(r"heart failure|coronary|cardiomyopathy|atrial fib|myocardial", re.I), "heart_disease"),
    (re.compile(r"\bhiv\b", re.I), "hiv"),
    (re.compile(r"hepatitis", re.I), "hepatitis"),
    (re.compile(r"kidney|renal", re.I), "kidney_disease"),
    (re.compile(r"cirrhosis|liver disease|hepatic", re.I), "liver_disease"),
    (re.compile(r"lupus|rheumatoid|crohn|colitis|multiple sclerosis|psoriasis", re.I), "autoimmune_disease"),
    (re.compile(r"epilep|seizure", re.I), "seizure"),
    (re.compile(r"schizo|bipolar", re.I), "psychiatric"),
    (re.compile(r"stroke", re.I), "stroke"),
]

_LIST_FIELDS = {
    "comorbidities": {"diabetes", "heart_disease", "stroke", "kidney_disease", "liver_disease", "hiv", "hepatitis",
                      "autoimmune_disease", "active_infection", "other_malignancy", "seizure", "psychiatric",
                      "substance_use", "transplant"},
    "treatments": {"chemotherapy", "immunotherapy", "radiation", "surgery", "targeted_therapy", "hormone_therapy"},
    "medications": {"insulin", "anticoagulant", "steroids"},
}
_ECOG_TO_KPS = {0: 100, 1: 80, 2: 60, 3: 40, 4: 20}


def patient_value(profile: PatientProfile, field: str):
    """The profile's value for a concept's field, or None when unknown."""
    implied = {flag for rx, flag in _IMPLIED for c in profile.conditions if rx.search(c)}
    if field in ("pregnant", "breastfeeding") and profile.sex == "male":
        return False
    for list_name, members in _LIST_FIELDS.items():
        if field in members:
            if field in implied:
                return True
            answered = getattr(profile, list_name)
            return None if answered is None else field in answered
    if field == "age":
        return float(profile.age)
    return getattr(profile, field, None)


def _compare(v: float, c: Criterion) -> Optional[bool]:
    if c.operator == ">=" and c.value is not None:
        return v >= c.value
    if c.operator == "<=" and c.value is not None:
        return v <= c.value
    if c.operator == "between" and c.value is not None and c.value_max is not None:
        return c.value <= v <= c.value_max
    return None


# Inclusion lines that *require* a history item are often cohort-specific ("Cohort B: must have
# received prior anti-PD-1"), so a mismatch there is a caution rather than a hard fail.
_SOFT_INCLUSION = {"prior_therapy", "medication", "reproductive", "comorbidity"}


def evaluate_criterion(c: Criterion, profile: PatientProfile, condition_score: float,
                       structured_age: bool = False) -> Tuple[str, str]:
    """Return (status, plain-language reason). Status is one of
    met | not_met | caution | unknown | review."""
    concept = CONCEPTS.get(c.concept)
    if concept is None or concept.profile_field is None:
        return "review", "Your care team would check this at screening."
    if c.concept == "age" and structured_age:
        return "review", "Age is checked against the study's official age range."

    if c.concept == "diagnosis":
        if c.kind == "inclusion" and c.operator == "present":
            if condition_score >= 0.6:
                return "met", "Your condition matches the study's condition."
            return "unknown", "Needs a confirmed diagnosis of the study condition."
        return "review", "Diagnosis details are confirmed by the study team."

    v = patient_value(profile, concept.profile_field)
    if c.concept == "karnofsky" and v is not None:
        v = _ECOG_TO_KPS.get(int(v))
    if v is None:
        return "unknown", f"You didn't tell us about: {_lc(concept.label)}."

    if concept.kind == BOOL:
        statement = bool(v) if c.operator != "absent" else not bool(v)
    else:
        statement = _compare(float(v), c)
        if statement is None:
            return "review", f"{concept.label} requirement needs clinical review."
    met = statement if c.kind == "inclusion" else not statement

    if met:
        return "met", _reason(c, concept.label, v, met=True)
    if c.timeframe and c.category in ("prior_therapy", "medication", "comorbidity"):
        return "caution", f"{concept.label}: only matters if {c.timeframe}."
    if c.kind == "inclusion" and c.operator == "present" and c.category in _SOFT_INCLUSION:
        return "caution", f"Part of this study requires: {_lc(concept.label)} (you didn't report it)."
    return "not_met", _reason(c, concept.label, v, met=False)


def _lc(label: str) -> str:
    """Lowercase a label for mid-sentence use without mangling acronyms (ECOG, HIV, BMI)."""
    return " ".join(w if any(ch.isupper() for ch in w[1:]) else w.lower() for w in label.split())


def _fmt(x: Optional[float]) -> str:
    if x is None:
        return "?"
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _reason(c: Criterion, label: str, v, met: bool) -> str:
    if CONCEPTS[c.concept].kind == BOOL:
        wants = (c.operator == "present") == (c.kind == "inclusion")
        need = f"requires {_lc(label)}" if wants else f"excludes {_lc(label)}"
        you = "you said yes" if bool(v) else "you said no"
        return f"Study {need}; {you}."
    rng = {">=": f"≥ {_fmt(c.value)}", "<=": f"≤ {_fmt(c.value)}",
           "between": f"{_fmt(c.value)}–{_fmt(c.value_max)}"}.get(c.operator, "")
    verb = "requires" if c.kind == "inclusion" else "excludes"
    return f"Study {verb} {_lc(label)} {rng}; yours is {_fmt(float(v))}."


def check_structured(trial: dict, profile: PatientProfile) -> List[Dict[str, str]]:
    """Hard filters from ClinicalTrials.gov structured fields. Returns failures."""
    fails = []
    lo, hi = trial.get("min_age_years"), trial.get("max_age_years")
    if lo is not None and profile.age < lo:
        fails.append({"field": "age", "reason": f"Minimum age is {_fmt(lo)}."})
    if hi is not None and profile.age > hi:
        fails.append({"field": "age", "reason": f"Maximum age is {_fmt(hi)}."})
    sex = (trial.get("sex") or "ALL").upper()
    if sex != "ALL" and sex.lower() != profile.sex:
        fails.append({"field": "sex", "reason": f"Open to {sex.lower()} participants only."})
    if profile.healthy_volunteer and trial.get("healthy_volunteers") is False:
        fails.append({"field": "healthy_volunteers", "reason": "Not recruiting healthy volunteers."})
    return fails


def evaluate_trial(parsed: ParsedEligibility, profile: PatientProfile, condition_score: float,
                   structured_age: bool = False) -> Dict:
    items = []
    for c in parsed.criteria:
        status, reason = evaluate_criterion(c, profile, condition_score, structured_age)
        items.append({
            "line": c.line, "text": c.text, "kind": c.kind, "concept": c.concept,
            "label": CONCEPTS[c.concept].label if c.concept in CONCEPTS else c.concept,
            "category": c.category, "operator": c.operator, "value": c.value, "value_max": c.value_max,
            "timeframe": c.timeframe, "status": status, "reason": reason,
        })
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("met", "not_met", "caution", "unknown", "review")}
    assessed = counts["met"] + counts["not_met"] + counts["caution"]
    score = 1.0
    score *= 0.35 ** counts["not_met"]
    score *= 0.85 ** counts["caution"]
    coverage = assessed / max(1, assessed + counts["unknown"])
    return {"criteria": items, "counts": counts, "eligibility_score": round(score, 4),
            "coverage": round(coverage, 3), "parser": parsed.parser, "model": parsed.model}


def verdict(structured_fails: List[dict], ev: Dict, condition_score: float) -> str:
    if structured_fails:
        return "ineligible"
    if ev["counts"]["not_met"] > 0:
        return "likely_ineligible"
    # only claim a likely fit when we could actually check most of what the study asks
    if condition_score >= 0.6 and ev["counts"]["caution"] == 0 and ev["counts"]["unknown"] <= 2 and ev["coverage"] >= 0.6:
        return "likely_eligible"
    return "possible"
