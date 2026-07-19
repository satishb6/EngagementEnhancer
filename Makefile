# WIRE — developer entrypoints.
# Windows users: run these under Git Bash, or use the equivalent commands inline.

.PHONY: dev api workers web db-up db-down migrate seed ingest-once lint test typecheck cost-model

db-up:
	docker compose up -d db redis

db-down:
	docker compose down

dev: db-up migrate
	@echo "→ API on :8000, web on :3000. Run 'make workers' in another terminal."
	cd services/api && uv run uvicorn wire_api.main:app --reload --port 8000

api:
	cd services/api && uv run uvicorn wire_api.main:app --reload --port 8000

workers:
	cd services/api && uv run celery -A wire_api.worker.celery_app worker --beat --loglevel=info --concurrency=4

web:
	pnpm --filter web dev

migrate:
	cd services/api && uv run alembic upgrade head

seed:
	cd services/api && uv run python -m wire_api.seed

ingest-once:
	cd services/api && uv run python -m wire_api.ingestion.run_once

lint:
	cd services/api && uv run ruff check . && uv run ruff format --check .
	pnpm lint

typecheck:
	cd services/api && uv run mypy wire_api
	pnpm typecheck

test:
	cd services/api && uv run pytest -q
	pnpm test

cost-model:
	cd services/api && uv run python ../../scripts/cost-model.py
