"""Gold-standard annotation store backing the /annotate review tool."""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

from .db import connect, execute, fetch_all, fetch_one, jsonb
from .parsing import rules
from .parsing.schema import CriterionLine

MIN_VERIFIED = 30  # below this the evaluation keeps using the drafted file


def seed_from_file(path) -> int:
    """Load the drafted gold file once; existing rows (and any human edits) are left alone."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    with connect() as conn, conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """INSERT INTO gold_annotations (id, nct_id, kind, text, labels, draft, source)
                   VALUES (%s,%s,%s,%s,%s,%s,'stratified') ON CONFLICT (id) DO NOTHING""",
                (r["id"], r["nct_id"], r["kind"], r["text"], jsonb(r["labels"]), jsonb(r["labels"])),
            )
    return len(rows)


def _prelabel(kind: str, text: str) -> List[Dict]:
    return [{"concept": c.concept, "operator": c.operator, "value": c.value, "value_max": c.value_max}
            for c in rules.parse_line(CriterionLine(index=0, kind=kind, text=text))]


def add_random(n: int = 25, seed: Optional[int] = None) -> int:
    """Uniformly random criterion lines (no stratification), pre-labelled by the rule parser."""
    rng = random.Random(seed)
    trials = fetch_all("SELECT nct_id, eligibility_text FROM trials WHERE length(eligibility_text) > 200 "
                       "ORDER BY random() LIMIT %s", (n * 3,))
    existing = {r["text"] for r in fetch_all("SELECT text FROM gold_annotations")}
    start = (fetch_one("SELECT coalesce(max(id), 0) AS m FROM gold_annotations")["m"] or 0) + 1
    added = 0
    with connect() as conn, conn.cursor() as cur:
        for t in trials:
            lines = [ln for ln in rules.split_lines(t["eligibility_text"]) if 15 < len(ln.text) < 300]
            if not lines:
                continue
            ln = rng.choice(lines)
            if ln.text in existing:
                continue
            labels = _prelabel(ln.kind, ln.text)
            cur.execute(
                """INSERT INTO gold_annotations (id, nct_id, kind, text, labels, draft, source)
                   VALUES (%s,%s,%s,%s,%s,%s,'random')""",
                (start + added, t["nct_id"], ln.kind, ln.text, jsonb(labels), jsonb(labels)),
            )
            existing.add(ln.text)
            added += 1
            if added >= n:
                break
    return added


def stats() -> Dict:
    rows = fetch_all("SELECT status, source, count(*) AS n FROM gold_annotations GROUP BY 1, 2")
    out: Dict = {"draft": 0, "verified": 0, "skipped": 0, "by_source": {}}
    for r in rows:
        out[r["status"]] += r["n"]
        out["by_source"].setdefault(r["source"], {})[r["status"]] = r["n"]
    out["total"] = out["draft"] + out["verified"] + out["skipped"]
    out["min_verified_for_eval"] = MIN_VERIFIED
    return out


def list_items(status: str, limit: int, offset: int) -> List[Dict]:
    return fetch_all(
        """SELECT id, nct_id, kind, text, labels, draft, status, source, annotator, updated_at
           FROM gold_annotations WHERE (%s = 'all' OR status = %s) ORDER BY id LIMIT %s OFFSET %s""",
        (status, status, limit, offset),
    )


def save(item_id: int, labels: List[Dict], status: str, annotator: Optional[str]) -> Optional[Dict]:
    execute(
        """UPDATE gold_annotations SET labels = %s, status = %s, annotator = %s, updated_at = now()
           WHERE id = %s""",
        (jsonb(labels), status, annotator, item_id),
    )
    return fetch_one("SELECT id, labels, status FROM gold_annotations WHERE id = %s", (item_id,))


def verified_gold() -> List[Dict]:
    return fetch_all("SELECT id, nct_id, kind, text, labels FROM gold_annotations WHERE status = 'verified' ORDER BY id")
