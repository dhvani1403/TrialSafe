"""Scheduled ingestion: ClinicalTrials.gov -> Postgres."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx

from . import ctgov
from .config import settings
from .db import connect, jsonb

log = logging.getLogger(__name__)

_UPSERT = """
INSERT INTO trials (nct_id, title, official_title, summary, status, phase, study_type, sponsor,
    sponsor_class, conditions, mesh_terms, mesh_ancestors, keywords, interventions, sex,
    min_age_years, max_age_years, healthy_volunteers, eligibility_text, criteria_hash,
    enrollment, start_date, last_update, central_contact, source_query, raw, search_tsv, ingested_at)
VALUES (%(nct_id)s, %(title)s, %(official_title)s, %(summary)s, %(status)s, %(phase)s,
    %(study_type)s, %(sponsor)s, %(sponsor_class)s, %(conditions)s::text[], %(mesh_terms)s::text[],
    %(mesh_ancestors)s::text[], %(keywords)s::text[], %(interventions)s, %(sex)s, %(min_age_years)s,
    %(max_age_years)s, %(healthy_volunteers)s, %(eligibility_text)s, %(criteria_hash)s,
    %(enrollment)s, %(start_date)s, %(last_update)s, %(central_contact)s, %(source_query)s,
    %(raw)s,
    setweight(to_tsvector('english', coalesce(%(title)s, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(%(conditions)s::text[] || %(mesh_terms)s::text[], ' ')), 'A') ||
    setweight(to_tsvector('english', array_to_string(%(keywords)s::text[], ' ')), 'B') ||
    setweight(to_tsvector('english', coalesce(%(summary)s, '')), 'C'),
    now())
ON CONFLICT (nct_id) DO UPDATE SET
    title = EXCLUDED.title, official_title = EXCLUDED.official_title, summary = EXCLUDED.summary,
    status = EXCLUDED.status, phase = EXCLUDED.phase, study_type = EXCLUDED.study_type,
    sponsor = EXCLUDED.sponsor, sponsor_class = EXCLUDED.sponsor_class,
    conditions = EXCLUDED.conditions, mesh_terms = EXCLUDED.mesh_terms,
    mesh_ancestors = EXCLUDED.mesh_ancestors, keywords = EXCLUDED.keywords,
    interventions = EXCLUDED.interventions, sex = EXCLUDED.sex,
    min_age_years = EXCLUDED.min_age_years, max_age_years = EXCLUDED.max_age_years,
    healthy_volunteers = EXCLUDED.healthy_volunteers, eligibility_text = EXCLUDED.eligibility_text,
    criteria_hash = EXCLUDED.criteria_hash, enrollment = EXCLUDED.enrollment,
    start_date = EXCLUDED.start_date, last_update = EXCLUDED.last_update,
    central_contact = EXCLUDED.central_contact, raw = EXCLUDED.raw,
    search_tsv = EXCLUDED.search_tsv, ingested_at = now(),
    -- a changed criteria text invalidates the embedding; parsers check criteria_hash themselves
    embedding = CASE WHEN trials.criteria_hash = EXCLUDED.criteria_hash THEN trials.embedding END
"""


def _store(cur, record: Dict, raw: Dict, source_query: str) -> None:
    row = dict(record)
    sites = row.pop("sites")
    row["interventions"] = jsonb(row["interventions"])
    row["central_contact"] = jsonb(row["central_contact"]) if row["central_contact"] else None
    row["raw"] = jsonb(raw)
    row["source_query"] = source_query
    cur.execute(_UPSERT, row)
    cur.execute("DELETE FROM sites WHERE nct_id = %s", (row["nct_id"],))
    for s in sites:
        cur.execute(
            """INSERT INTO sites (nct_id, facility, city, state, zip, country, status, lat, lon, contact)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (row["nct_id"], s["facility"], s["city"], s["state"], s["zip"], s["country"],
             s["status"], s["lat"], s["lon"], jsonb(s["contact"]) if s["contact"] else None),
        )


def run_ingest(conditions: Optional[List[str]] = None, per_condition: Optional[int] = None) -> Dict:
    conditions = conditions or settings.ingest_conditions
    per_condition = per_condition or settings.ingest_per_condition
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ingest_runs DEFAULT VALUES RETURNING id")
        run_id = cur.fetchone()[0]

    seen, upserted, per_query, errors = 0, set(), {}, {}
    with httpx.Client(headers={"User-Agent": "TrialMatch/1.0 (research prototype)"}) as client:
        for condition in conditions:
            count = 0
            try:
                with connect() as conn, conn.cursor() as cur:
                    for raw in ctgov.iter_studies(condition, per_condition, client):
                        seen += 1
                        record = ctgov.normalise(raw)
                        if not record["nct_id"]:
                            continue
                        _store(cur, record, raw, condition)
                        upserted.add(record["nct_id"])
                        count += 1
            except Exception as exc:  # keep going; one bad condition shouldn't sink the run
                log.exception("ingest failed for %s", condition)
                errors[condition] = str(exc)
            per_query[condition] = count
            log.info("ingested %-24s %d", condition, count)

    status = "ok" if not errors else ("partial" if upserted else "failed")
    detail = {"per_condition": per_query, "errors": errors}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE ingest_runs SET finished_at = now(), status = %s, trials_seen = %s,
               trials_upserted = %s, detail = %s WHERE id = %s""",
            (status, seen, len(upserted), jsonb(detail), run_id),
        )
    return {"run_id": run_id, "status": status, "seen": seen, "upserted": len(upserted), **detail}
