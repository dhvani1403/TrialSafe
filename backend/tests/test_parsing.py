from app.ctgov import age_to_years, normalise
from app.parsing import rules
from app.parsing.schema import CriterionLine

TEXT = """Inclusion Criteria:

* Age \\>= 18 years
* ECOG performance status 0 or 1
* Must not be pregnant or breastfeeding
* HbA1c 7.0% to 10.5%

Exclusion Criteria:

* Known HIV or active hepatitis B or C
* Prior chemotherapy within 4 weeks
* Physiological replacement doses of steroids are permitted
"""


def _by_concept(text, kind="inclusion"):
    return {c.concept: c for c in rules.parse_line(CriterionLine(index=0, kind=kind, text=text))}


def test_split_lines_tracks_sections():
    lines = rules.split_lines(TEXT)
    assert [l.kind for l in lines] == ["inclusion"] * 4 + ["exclusion"] * 3
    assert lines[0].text == "Age >= 18 years"  # markdown escapes removed


def test_numeric_thresholds():
    assert _by_concept("Age >= 18 years")["age"].value == 18
    ecog = _by_concept("ECOG performance status 0 or 1")["ecog"]
    assert (ecog.operator, ecog.value, ecog.value_max) == ("between", 0, 1)
    a1c = _by_concept("HbA1c 7.0% to 10.5%")["hba1c"]
    assert (a1c.operator, a1c.value, a1c.value_max) == ("between", 7.0, 10.5)
    assert _by_concept("Male or female ≥ 18 years of age")["age"].value == 18


def test_negation_and_pseudo_negation():
    c = _by_concept("Must not be pregnant or breastfeeding")
    assert c["pregnancy"].operator == "absent"
    assert _by_concept("No more than 2 prior chemotherapy regimens")["prior_chemotherapy"].operator == "present"


def test_exclusion_concepts_and_timeframe():
    c = _by_concept("Known HIV or active hepatitis B or C", "exclusion")
    assert {"hiv", "hepatitis"} <= set(c)
    chemo = _by_concept("Prior chemotherapy within 4 weeks", "exclusion")["prior_chemotherapy"]
    assert chemo.timeframe == "within 4 weeks"


def test_egfr_mutation_is_not_kidney_function():
    assert "egfr_lab" not in _by_concept("Known EGFR activating mutation")


def test_parse_extracts_age_bounds():
    parsed = rules.parse("Inclusion Criteria:\n* Aged 45 to 75 years\n")
    assert (parsed.min_age, parsed.max_age) == (45, 75)


def test_age_units():
    assert age_to_years("18 Years") == 18
    assert age_to_years("6 Months") == 0.5
    assert age_to_years(None) is None


def test_normalise_minimal_record():
    rec = normalise({"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "T"},
        "eligibilityModule": {"sex": "FEMALE", "minimumAge": "18 Years", "eligibilityCriteria": "x"},
        "designModule": {"phases": ["PHASE2", "PHASE3"]},
        "contactsLocationsModule": {"locations": [{"facility": "F", "geoPoint": {"lat": 1.0, "lon": 2.0}}]},
    }})
    assert rec["phase"] == "PHASE2/PHASE3"
    assert rec["min_age_years"] == 18 and rec["max_age_years"] is None
    assert rec["sites"][0]["lat"] == 1.0


def test_contraction_negation():
    assert _by_concept("I don't smoke")["smoking"].operator == "absent"
    assert _by_concept("Patient hasn't had chemotherapy")["prior_chemotherapy"].operator == "absent"
