"""Scheduled ingestion worker: `python -m app.worker`.

Every INGEST_INTERVAL_HOURS: pull ClinicalTrials.gov -> rule-parse changed trials -> refresh
embeddings -> spend a little of the day's LLM budget upgrading high-traffic trials.
"""
from __future__ import annotations

import logging
import signal
import sys
import time

from . import db
from .config import settings

log = logging.getLogger("worker")
_stop = False


def _handle(signum, _frame) -> None:
    global _stop
    log.info("signal %s received; stopping after this cycle", signum)
    _stop = True


def cycle() -> None:
    from .embeddings import embed_all_trials
    from .ingest import run_ingest
    from .parsing.service import parse_all_rules, parse_batch_llm

    result = run_ingest()
    log.info("ingest: %s upserted (%s)", result["upserted"], result["status"])
    log.info("rules-parsed %d", parse_all_rules())
    log.info("embedded %d", embed_all_trials())
    llm = parse_batch_llm(limit=5)
    log.info("llm-parsed %d (budget left %d)", len(llm["parsed"]), llm["budget_remaining"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    db.init_schema()
    interval = settings.ingest_interval_hours * 3600
    # --delay-first: the bootstrap pipeline just ran, so wait a full interval before re-ingesting
    started = time.time() if "--delay-first" in sys.argv else 0.0
    while not _stop:
        while not _stop and time.time() - started < interval:
            time.sleep(5)
        if _stop:
            break
        started = time.time()
        try:
            cycle()
        except Exception:
            log.exception("cycle failed; will retry next interval")


if __name__ == "__main__":
    main()
