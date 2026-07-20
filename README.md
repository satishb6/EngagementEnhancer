# WIRE

Your take on the news, at the speed of a swipe.

> **Not technical?** Read **[docs/GETTING-STARTED-SIMPLE.md](docs/GETTING-STARTED-SIMPLE.md)**
> instead of this file. Short version: install Docker Desktop, double-click
> `SETUP-WIRE.bat` once, then `START-WIRE.bat` whenever you want the app.

The machine reads everything you nominate, deduplicates it into ~500 shared
sixty-word briefings a day, and ranks 50 for you. You swipe. On the keepers
you add your take — typed, spoken, or tapped from three suggested stances and
bent into your own words. The machine turns take + briefing into posts,
images, and (only when you ask and pay) video, in your voice, on your
schedule. Human-in-the-loop at exactly two points: the swipe and the pick.

## Architecture in five lines

- **Shared corpus**: ingestion → embed → cluster → brief runs once per news
  event, never per user. 1,000 extra users add zero model calls (tested).
- **Lazy generation**: text + images eager (~$0.13/selection), video only via
  an explicit, entitlement-checked user action (tested by codebase grep).
- **Provider router**: cloud / BYOK / local-GPU are the same code path —
  `resolve(capability, user)`; swapping modes touches zero business logic.
- **Trace spine**: every operation emits `pipeline_event`; the Wire Room
  renders it live over SSE. Balance = `SUM(credit_ledger)`, never a column.
- **Four learning loops**: taste (swipes), voice (takes, RAG not fine-tuning),
  format (picks × engagement), timing (post performance). All resettable.

## Layout

```
services/api/wire_api/   FastAPI + Celery: providers, corpus, ranking,
                         learning, generation, billing, publishing, tracing
apps/web/                Next.js 15: deck, darkroom, contact sheet,
                         Wire Room, Lattice, dashboard, onboarding
apps/mobile/             Expo SDK 52: the four rooms, gesture deck
packages/shared/         design tokens — the single source of truth
infra/                   Dockerfiles, Caddy, production compose
docs/                    DESIGN.md (binding), DEPLOYMENT.md, critique
scripts/                 cost model, k6 load, local-GPU setup
```

## Run it locally

Prereqs: Docker, Python 3.12+ with [uv](https://docs.astral.sh/uv/) (or pip),
Node 22 + pnpm 9.

```bash
docker compose up -d db redis

cd services/api
uv sync --all-extras            # or: python -m venv .venv && pip install -e ".[dev]"
cp ../../.env.example .env      # add ANTHROPIC_API_KEY + OPENAI_API_KEY minimum
uv run alembic upgrade head
uv run python -m wire_api.seed
uv run uvicorn wire_api.main:app --reload --port 8000
# second terminal: uv run celery -A wire_api.worker.celery_app worker --beat -l info

# third terminal, repo root
pnpm install && pnpm --filter web dev     # http://localhost:3000
```

Sign in with `pro@wire.dev` / `wire-dev-password` (seeded), or sign up fresh.
`make ingest-once` pulls real sources and briefs them.

Tests: `cd services/api && uv run pytest -q` (37 unit tests run anywhere;
integration tests need Docker or `TEST_DATABASE_URL`).

## Deploy it

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — a single-VPS Docker
Compose path with automatic TLS (recommended), and a managed
Railway/Vercel path. Free tier runs on just an Anthropic + OpenAI + fal +
NewsData key; Stripe and Ayrshare switch on the paid tiers when you're ready.

## The rules that keep it alive

1. Any code that summarises the same article twice for two users is a bug.
2. There is no code path where a background job creates a video.
3. No SDK calls outside `wire_api/providers/`.
4. Every generation is cost-estimated before it runs, and the estimate is
   persisted next to the actual.
5. Balance is always derived from the append-only ledger.

`docs/DESIGN.md` is binding for anything visual. Read it before touching UI.
