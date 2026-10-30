PY ?= python3
BACKEND = cd backend &&

.PHONY: db pipeline api web worker test llm-parse eval docker trec

db:            ## create the local database with pgvector
	createdb trialmatch 2>/dev/null || true
	psql -d trialmatch -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"

pipeline:      ## ingest -> rule parse -> embed -> train ranker -> parsing eval -> fairness audit
	$(BACKEND) $(PY) -m scripts.cli pipeline

llm-parse:     ## spend some of today's free LLM quota upgrading the busiest trials
	$(BACKEND) $(PY) -m scripts.cli parse-llm --limit 5

eval:          ## re-score parsers on the gold set (includes ~10 LLM calls)
	$(BACKEND) $(PY) -m scripts.cli eval-parsing --with-llm

api:
	$(BACKEND) $(PY) -m uvicorn app.main:app --reload --port 8000 --timeout-keep-alive 75

worker:
	$(BACKEND) $(PY) -m app.worker

web:
	cd frontend && npm run dev

test:
	$(BACKEND) $(PY) -m pytest -q
	cd frontend && npx tsc --noEmit && npm run lint

docker:
	docker compose up --build

trec:          ## TREC 2021 Clinical Trials benchmark in a separate database (~26k judged trials)
	createdb trialmatch_bench 2>/dev/null || true
	psql -d trialmatch_bench -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
	$(BACKEND) DATABASE_URL=postgresql://localhost:5432/trialmatch_bench ARTIFACTS_DIR=artifacts/bench $(PY) -m scripts.cli trec
