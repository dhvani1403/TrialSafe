"""Free-text profile extraction (needs the trial corpus for condition names)."""
import pytest

from app.db import fetch_one
from app.profile_extract import extract


def _has_data() -> bool:
    try:
        row = fetch_one("SELECT count(*) AS n FROM trials")
        return bool(row and row["n"])
    except Exception:
        return False


def test_demographics_and_history_without_corpus():
    p = extract("I'm a 62 year old woman. I had chemotherapy last year. I don't smoke.")["profile"]
    assert p["age"] == 62 and p["sex"] == "female"
    assert p["treatments"] == ["chemotherapy"]
    assert p["smoker"] is False


def test_male_never_pregnant():
    p = extract("He is a 40 year old man, not pregnant.")["profile"]
    assert p["sex"] == "male" and "pregnant" not in p


@pytest.mark.skipif(not _has_data(), reason="no ingested trials")
def test_condition_lookup_prefers_specific_terms():
    p = extract("My dad is 71, he has type 2 diabetes and heart failure.")["profile"]
    assert p["age"] == 71
    assert any("diabetes" in c.lower() for c in p["conditions"])
