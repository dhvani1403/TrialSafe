import math

from app.matching import PatientProfile, check_structured, evaluate_criterion, evaluate_trial, verdict
from app.parsing.schema import Criterion, ParsedEligibility
from app.ranking.train import ndcg_at_k


def crit(concept, kind="exclusion", operator="present", category="comorbidity", value=None, value_max=None, timeframe=None):
    return Criterion(line=0, text="", kind=kind, concept=concept, category=category, operator=operator,
                     value=value, value_max=value_max, timeframe=timeframe)


def profile(**kw):
    base = {"conditions": ["breast cancer"], "age": 52, "sex": "female"}
    return PatientProfile(**{**base, **kw})


def test_exclusion_hit_is_not_met():
    status, reason = evaluate_criterion(crit("hiv"), profile(comorbidities=["hiv"]), 1.0)
    assert status == "not_met" and "excludes" in reason


def test_unanswered_is_unknown_but_empty_answer_is_met():
    assert evaluate_criterion(crit("hiv"), profile(), 1.0)[0] == "unknown"
    assert evaluate_criterion(crit("hiv"), profile(comorbidities=[]), 1.0)[0] == "met"


def test_condition_implies_comorbidity():
    p = profile(conditions=["type 2 diabetes"], comorbidities=[])
    assert evaluate_criterion(crit("diabetes"), p, 1.0)[0] == "not_met"


def test_men_are_never_pregnant():
    c = crit("pregnancy", category="reproductive")
    assert evaluate_criterion(c, profile(sex="male"), 1.0)[0] == "met"


def test_numeric_ecog_range():
    c = crit("ecog", kind="inclusion", operator="between", category="performance", value=0, value_max=1)
    assert evaluate_criterion(c, profile(ecog=1), 1.0)[0] == "met"
    assert evaluate_criterion(c, profile(ecog=2), 1.0)[0] == "not_met"


def test_timeframed_history_is_only_a_caution():
    c = crit("prior_chemotherapy", category="prior_therapy", timeframe="within 4 weeks")
    assert evaluate_criterion(c, profile(treatments=["chemotherapy"]), 1.0)[0] == "caution"


def test_structured_age_is_authoritative_over_text():
    c = crit("age", kind="inclusion", operator="<=", category="demographic", value=18)
    assert evaluate_criterion(c, profile(), 1.0, structured_age=True)[0] == "review"


def test_structured_filters():
    fails = check_structured({"min_age_years": 18, "max_age_years": 40, "sex": "MALE"}, profile())
    assert {f["field"] for f in fails} == {"age", "sex"}


def test_verdicts():
    parsed = ParsedEligibility(parser="rules", lines=[], criteria=[crit("hiv")])
    ev = evaluate_trial(parsed, profile(comorbidities=["hiv"]), 1.0)
    assert verdict([], ev, 1.0) == "likely_ineligible"
    ev = evaluate_trial(parsed, profile(comorbidities=[]), 1.0)
    assert verdict([], ev, 1.0) == "likely_eligible"
    assert verdict([{"field": "age"}], ev, 1.0) == "ineligible"


def test_ndcg():
    assert ndcg_at_k([3, 2, 1, 0]) == 1.0
    assert math.isclose(ndcg_at_k([0, 0, 0]), 0.0)
    assert ndcg_at_k([0, 3]) < 1.0


def test_reason_wording_distinguishes_no_from_unanswered():
    _, reason = evaluate_criterion(crit("hiv"), profile(comorbidities=[]), 1.0)
    assert reason.endswith("you said no.")
    _, reason = evaluate_criterion(crit("hiv"), profile(), 1.0)
    assert reason.startswith("You didn't tell us")
