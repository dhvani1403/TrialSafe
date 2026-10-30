"""TrialMatch command line: `python -m scripts.cli <command>` from backend/."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="trialmatch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="pull open trials from ClinicalTrials.gov")
    p.add_argument("--per-condition", type=int, default=None)
    p.add_argument("--conditions", nargs="*", default=None)

    p = sub.add_parser("parse-rules", help="run the rule-based eligibility parser on every trial")
    p.add_argument("--force", action="store_true", help="re-parse even if criteria text is unchanged")

    p = sub.add_parser("parse-llm", help="LLM-parse eligibility for a few trials (uses free-tier quota)")
    p.add_argument("--limit", type=int, default=10)

    sub.add_parser("embed", help="compute trial embeddings")
    sub.add_parser("train", help="train the learned ranker on weakly supervised pairs")

    p = sub.add_parser("eval-parsing", help="score parsers against the gold criteria set")
    p.add_argument("--with-llm", action="store_true", help="also score the LLM parser (uses quota)")

    sub.add_parser("fairness", help="run the match-disparity audit")
    p = sub.add_parser("trec", help="TREC 2021 Clinical Trials benchmark (needs DATABASE_URL=<bench db>)")
    p.add_argument("--reuse", action="store_true", help="re-score saved pairs (after retraining) without rebuilding")
    p = sub.add_parser("eval-explain", help="audit AI explanations for safety and faithfulness (uses quota)")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--reaudit", action="store_true", help="re-score stored outputs, no LLM calls")
    sub.add_parser("pipeline", help="ingest -> parse-rules -> embed -> train -> eval -> fairness")

    args = ap.parse_args()
    db.init_schema()

    if args.cmd in ("ingest", "pipeline"):
        from app.ingest import run_ingest
        kw = {}
        if args.cmd == "ingest":
            kw = {"conditions": args.conditions, "per_condition": args.per_condition}
        print(json.dumps(run_ingest(**kw), indent=2))
    if args.cmd in ("parse-rules", "pipeline"):
        from app.parsing.service import parse_all_rules
        print("rules-parsed", parse_all_rules(force=getattr(args, "force", False)))
    if args.cmd == "parse-llm":
        from app.parsing.service import parse_batch_llm
        print(json.dumps(parse_batch_llm(args.limit), indent=2))
    if args.cmd in ("embed", "pipeline"):
        from app.embeddings import embed_all_trials
        print("embedded", embed_all_trials())
    if args.cmd in ("train", "pipeline"):
        from app.ranking.train import train_and_evaluate
        print(json.dumps(train_and_evaluate(), indent=2))
    if args.cmd in ("eval-parsing", "pipeline"):
        from app.evaluation.parsing_eval import run_parsing_eval
        rep = run_parsing_eval(with_llm=getattr(args, "with_llm", False))
        print(json.dumps(rep["summary"], indent=2))
    if args.cmd == "eval-explain":
        from app.evaluation.explain_eval import reaudit, run_explain_eval
        rep = reaudit() if args.reaudit else run_explain_eval(args.limit)
        print(json.dumps({k: rep[k] for k in ("cases", "model", "llm_raw", "llm_guarded", "template")}, indent=2))
    if args.cmd == "trec":
        from app.evaluation.trec import run_all
        rep = run_all(reuse=args.reuse)
        print(json.dumps({"results": rep["results"], "eligibility": rep["eligibility"]}, indent=2))
    if args.cmd in ("fairness", "pipeline"):
        from app.evaluation.fairness import run_fairness_audit
        print(json.dumps(run_fairness_audit()["headline"], indent=2))


if __name__ == "__main__":
    main()
