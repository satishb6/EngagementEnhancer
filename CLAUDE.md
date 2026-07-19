# WIRE — project context

## What this is
A news-to-content engine. Users define source protocols, receive ~50 sixty-word
briefings a day, swipe to sort them, add their own take on the keepers, and get
AI-generated posts in their voice. Human-in-the-loop at two points: the swipe,
and the version pick.

## Non-negotiable architectural rules
1. **Shared corpus, personalised selection.** Ingestion, dedup, and summarisation
   happen ONCE per news cluster, never per user. Personalisation is a ranking
   step over a shared pool. Any code that summarises the same article twice for
   two users is a bug.
2. **Lazy generation.** Text and images generate eagerly. Video NEVER generates
   without an explicit user action that passes an entitlement check. There is no
   code path where a background job creates a video.
3. **Every generation call goes through the provider abstraction.** No direct SDK
   calls to fal/OpenAI/Anthropic/Ollama outside `services/api/wire_api/providers/`.
4. **Every generation is cost-estimated before it runs**, and the estimate is
   persisted alongside the result.
5. **Durable workflows only.** Generation is async, multi-minute, and fails.
   Nothing generation-related lives in a request handler.

## Stack
- API: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 async
- DB: Postgres 16 + pgvector
- Queue: Celery + Redis
- Mobile: Expo SDK 52, React Native, Reanimated 3, Gesture Handler, Skia,
  react-three-fiber
- Web: Next.js 15 App Router, Tailwind, Framer Motion, react-three-fiber
- Publishing: unified social API (adapter-wrapped, swappable)

## Layout
- `services/api/wire_api/` — FastAPI app, providers, corpus, ranking, learning,
  generation, billing, publishing, tracing
- `services/api/alembic/` — migrations (reviewed by hand, never blind autogen)
- `packages/shared/` — design tokens (single source of truth for both apps)
- `packages/ui/` — web design system (Print, Chrome, Wire, Grain, Redaction)
- `apps/web/` — Next.js 15 (deck, take capture, contact sheet, Wire Room, Lattice)
- `apps/mobile/` — Expo app (four rooms)
- `infra/` — Dockerfiles, Caddy, production compose

## Conventions
- Python: ruff + mypy strict. No `Any` in function signatures.
- TS: strict mode. No `any`. Zod at every boundary.
- Tests colocated under `tests/`. Every provider adapter has a contract test.
- Migrations via Alembic, never auto-generated without review.

## Design
Read `docs/DESIGN.md` before writing any UI. It is binding, not advisory.
Do not introduce colours, typefaces, radii, or motion curves that aren't in it.
