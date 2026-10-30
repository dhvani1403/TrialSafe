"""Persisting parser output and choosing the best available parse for a trial."""
from __future__ import annotations

import logging
from typing import Dict, Optional

from ..db import connect, fetch_all, fetch_one, jsonb
from ..llm import LLMUnavailable, budget_remaining
from . import llm_parser, rules
from .schema import ParsedEligibility

log = logging.getLogger(__name__)

_SAVE = """
INSERT INTO parsed_eligibility (nct_id, parser, model, criteria_hash, parsed)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (nct_id, parser) DO UPDATE SET model = EXCLUDED.model,
    criteria_hash = EXCLUDED.criteria_hash, parsed = EXCLUDED.parsed, created_at = now()
"""


def parse_all_rules(force: bool = False) -> int:
    rows = fetch_all(
        """SELECT t.nct_id, t.eligibility_text, t.criteria_hash FROM trials t
           LEFT JOIN parsed_eligibility p ON p.nct_id = t.nct_id AND p.parser = 'rules'
           WHERE %s OR p.nct_id IS NULL OR p.criteria_hash <> t.criteria_hash""",
        (force,),
    )
    with connect() as conn, conn.cursor() as cur:
        for r in rows:
            parsed = rules.parse(r["eligibility_text"] or "")
            cur.execute(_SAVE, (r["nct_id"], "rules", None, r["criteria_hash"], jsonb(parsed.model_dump())))
    return len(rows)


def parse_one_llm(nct_id: str) -> ParsedEligibility:
    row = fetch_one("SELECT eligibility_text, criteria_hash FROM trials WHERE nct_id = %s", (nct_id,))
    if not row:
        raise KeyError(nct_id)
    parsed = llm_parser.parse(row["eligibility_text"] or "")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_SAVE, (nct_id, "llm", parsed.model, row["criteria_hash"], jsonb(parsed.model_dump())))
    return parsed


def parse_batch_llm(limit: int) -> Dict:
    """LLM-parse the most-viewed-worthy trials first: open, interventional, many US sites."""
    rows = fetch_all(
        """SELECT t.nct_id FROM trials t
           LEFT JOIN parsed_eligibility p ON p.nct_id = t.nct_id AND p.parser = 'llm'
           WHERE (p.nct_id IS NULL OR p.criteria_hash <> t.criteria_hash) AND t.status = 'RECRUITING'
             AND length(t.eligibility_text) > 200
           ORDER BY (SELECT count(*) FROM sites s WHERE s.nct_id = t.nct_id) DESC
           LIMIT %s""",
        (limit,),
    )
    done, failed = [], {}
    for r in rows:
        if budget_remaining() <= 1:  # always leave one call for interactive use
            break
        try:
            p = parse_one_llm(r["nct_id"])
            done.append({"nct_id": r["nct_id"], "criteria": len(p.criteria), "model": p.model})
        except LLMUnavailable as exc:
            failed[r["nct_id"]] = str(exc)
            log.warning("LLM parse failed for %s: %s", r["nct_id"], exc)
    return {"parsed": done, "failed": failed, "budget_remaining": budget_remaining()}


def best_parse(nct_id: str, eligibility_text: str, criteria_hash: str) -> ParsedEligibility:
    """Prefer a current LLM parse, then the stored rule parse, else parse on the fly."""
    rows = fetch_all(
        "SELECT parser, criteria_hash, parsed FROM parsed_eligibility WHERE nct_id = %s", (nct_id,)
    )
    by: Dict[str, dict] = {r["parser"]: r for r in rows if r["criteria_hash"] == criteria_hash}
    for name in ("llm", "rules"):
        if name in by:
            return ParsedEligibility(**by[name]["parsed"])
    return rules.parse(eligibility_text or "")


def load_parses(nct_ids) -> Dict[str, ParsedEligibility]:
    """Bulk version of best_parse for search results."""
    if not nct_ids:
        return {}
    rows = fetch_all(
        """SELECT DISTINCT ON (p.nct_id) p.nct_id, p.parsed FROM parsed_eligibility p
           JOIN trials t ON t.nct_id = p.nct_id AND t.criteria_hash = p.criteria_hash
           WHERE p.nct_id = ANY(%s)
           ORDER BY p.nct_id, (p.parser = 'llm') DESC""",
        (list(nct_ids),),
    )
    return {r["nct_id"]: ParsedEligibility(**r["parsed"]) for r in rows}


def llm_status() -> Optional[dict]:
    return {"budget_remaining": budget_remaining()}
