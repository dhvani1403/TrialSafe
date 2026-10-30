"""API tests against a database populated by the pipeline (skipped if it's empty)."""
import pytest
from fastapi.testclient import TestClient

from app.db import fetch_one
from app.main import app


def _has_data() -> bool:
    try:
        row = fetch_one("SELECT count(*) AS n FROM trials")
        return bool(row and row["n"])
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_data(), reason="no ingested trials")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["trials"] > 0


def test_match_requires_condition(client):
    r = client.post("/api/match", json={"age": 40, "sex": "female"})
    assert r.status_code == 422


def test_match_respects_hard_filters(client):
    r = client.post("/api/match", json={"conditions": ["breast cancer"], "age": 30, "sex": "male",
                                        "location": {"lat": 39.95, "lon": -75.16}, "max_distance_mi": 150})
    assert r.status_code == 200
    body = r.json()
    for t in body["results"]:
        assert t["sex"] in ("ALL", "MALE")
        assert t["min_age"] is None or t["min_age"] <= 30
        assert t["nearest_site"]["distance_mi"] <= 150
    scores = [t["score"] for t in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_trial_detail_and_similar(client):
    nct = fetch_one("SELECT nct_id FROM trials WHERE embedding IS NOT NULL LIMIT 1")["nct_id"]
    d = client.post(f"/api/trials/{nct}/evaluate", json={"conditions": ["cancer"], "age": 50, "sex": "female"}).json()
    assert d["nct_id"] == nct and "criteria" in d and "verdict" in d
    assert client.get(f"/api/trials/{nct}/similar").status_code == 200
    assert client.get("/api/trials/NCT00000000").status_code == 404


def test_profile_extract_endpoint(client):
    body = client.post("/api/profile/extract", json={"text": "I am a 50 year old woman with asthma. I don't smoke."}).json()
    assert body["profile"]["age"] == 50 and body["profile"]["smoker"] is False


def test_annotation_roundtrip(client):
    stats = client.get("/api/annotations/stats").json()
    assert stats["total"] >= 139
    item = client.get("/api/annotations?status=all&limit=1").json()[0]
    bad = client.put(f"/api/annotations/{item['id']}", json={"labels": [{"concept": "nope"}], "status": "draft"})
    assert bad.status_code == 422
    ok = client.put(f"/api/annotations/{item['id']}", json={"labels": item["labels"], "status": item["status"]})
    assert ok.status_code == 200
