from app import guardrails


CRITERIA = [
    {"concept": "hiv", "status": "not_met", "reason": "Study excludes HIV; you said yes."},
    {"concept": "pregnancy", "status": "met", "reason": "Study excludes pregnancy; you said no."},
    {"concept": "ecog", "status": "unknown", "reason": "You didn't tell us about: ECOG performance status."},
]


def test_audit_finds_each_problem_type():
    body = {
        "summary": "You are eligible for this study. It tests a new drug.",
        "why_it_may_fit": ["Your HIV status fits the study."],
        "things_to_check": ["It is unclear whether you are pregnant.", "Your activity level is unclear (ECOG)."],
        "questions_for_your_doctor": [],
    }
    issues = guardrails.audit(body, CRITERIA)
    assert issues["unsafe"]
    assert issues["contradiction"][0]["concepts"] == ["hiv"]
    assert issues["false_unknown"][0]["concepts"] == ["pregnancy"]  # ECOG really is unknown, so it stays
    assert issues["missed_conflict"] == []  # HIV is mentioned (wrongly), so not "missed"


def test_apply_repairs_and_reports():
    body = {"summary": "You should enroll now. It tests a drug.", "why_it_may_fit": ["Matches your condition."],
            "things_to_check": ["It is unclear whether you are pregnant."], "questions_for_your_doctor": []}
    out = guardrails.apply(body, CRITERIA)
    assert out["summary"] == "It tests a drug."
    assert out["things_to_check"][0].startswith("Study excludes HIV")  # missed conflict added back
    assert all("pregnant" not in t for t in out["things_to_check"])
    assert out["guardrail"] == {"removed": 2, "added": 1}
    assert guardrails.audit(out, CRITERIA) == {"unsafe": [], "contradiction": [], "false_unknown": [], "missed_conflict": []}


def test_reading_grade_orders_texts():
    easy = "The study tests a new pill. You take it once a day."
    hard = "Participants will receive investigational immunomodulatory pharmacotherapy administered intravenously."
    assert guardrails.reading_grade(easy) < guardrails.reading_grade(hard)


def test_hedged_eligibility_mentions_are_safe():
    assert not guardrails.is_unsafe("Only the study team can confirm whether you are eligible.")
    assert guardrails.is_unsafe("Good news: you are eligible for this trial.")
