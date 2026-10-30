from app.explain import normalise


def test_normalise_splits_sections_packed_into_summary():
    body = {
        "summary": "Tests drug X. For adults.\\n\\nwhy_it_may_fit: Your condition matches.\\n\\n"
                   "things_to_check: Prior therapy unclear. Steroid use unclear.\\n\\n"
                   "questions_for_your_doctor: Is this safe for me? How many visits?",
        "why_it_may_fit": [], "things_to_check": [], "questions_for_your_doctor": [],
    }
    out = normalise(body)
    assert out["summary"] == "Tests drug X. For adults."
    assert out["why_it_may_fit"] == ["Your condition matches."]
    assert len(out["things_to_check"]) == 2
    assert out["questions_for_your_doctor"] == ["Is this safe for me?", "How many visits?"]


def test_normalise_accepts_string_lists():
    out = normalise({"summary": "S", "why_it_may_fit": "- a\n- b", "things_to_check": [], "questions_for_your_doctor": []})
    assert out["why_it_may_fit"] == ["a", "b"]
