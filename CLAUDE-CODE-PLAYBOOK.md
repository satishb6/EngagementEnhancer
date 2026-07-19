# The Build Playbook
### A sequenced prompt script for Claude Code (Fable 5)

Working name used throughout: **WIRE**. Replace with your own name via find-and-replace before you start.

---

## How to use this document

Each numbered block is a prompt. Paste it into Claude Code as-is. Work top to bottom — the order encodes dependencies, and skipping ahead produces code that gets rewritten.

Three rules that matter more than any individual prompt:

1. **Never run two phases in one prompt.** Fable 5 will happily attempt it and you'll lose the ability to review anything.
2. **After every phase, run the verification prompt for that phase.** They're marked `✓`. Skipping them is how you get a codebase that compiles and doesn't work.
3. **Commit after every green verification.** `git commit -m "phase N: <thing>"`. You will want to roll back at some point.

A note on prompting a model this strong: don't write step-by-step instructions. Write **goal + constraints + acceptance criteria** and let it choose the implementation. The prompts below are written that way on purpose. If you find yourself adding "first do X, then do Y," you're under-using the model.

---

# PART 0 — Before you type a single prompt

## 0.1 Install these MCP servers

The single highest-value one is **Playwright**. Without it, Claude Code is writing UI blind — it cannot see what it built, so it cannot critique it. With it, the loop becomes: build → screenshot → critique → fix. That loop is the entire difference between "fine" and "beautiful."

```bash
# Playwright — visual feedback loop. Non-negotiable for the frontend work.
claude mcp add playwright -- npx -y @playwright/mcp@latest

# Postgres — lets Claude inspect your real schema instead of guessing
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres \
  postgresql://localhost/wire_dev

# Filesystem access to a scratch dir for design references
claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/wire-refs
```

Optional but useful:
- **Context7** or equivalent docs MCP — keeps library APIs current instead of hallucinated
- **Figma MCP** — only if you actually produce Figma files; otherwise skip

## 0.2 Enable the frontend-design skill

Claude Code ships with a `frontend-design` skill that pushes back against templated visual defaults. Confirm it loads before the frontend phases:

```
/skills
```

If it's not listed, the frontend prompts still work, but you'll need to lean harder on the critique prompts.

## 0.3 Scaffold

```bash
mkdir wire && cd wire && git init
mkdir -p .claude apps/mobile apps/web services/api services/workers packages/shared docs
```

## 0.4 Write `CLAUDE.md` at the repo root

This file is loaded into every Claude Code session. It is the highest-leverage text in your project. Paste this:

````markdown
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
   calls to fal/OpenAI/Anthropic/Ollama outside `services/api/providers/`.
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

## Conventions
- Python: ruff + mypy strict. No `Any` in function signatures.
- TS: strict mode. No `any`. Zod at every boundary.
- Tests colocated. Every provider adapter has a contract test.
- Migrations via Alembic, never auto-generated without review.

## Design
Read `docs/DESIGN.md` before writing any UI. It is binding, not advisory.
Do not introduce colours, typefaces, radii, or motion curves that aren't in it.
````

## 0.5 Get the fonts

```bash
# Redaction — display face. Free, OFL.
# https://github.com/ArrowType/redaction

# Instrument Sans + Martian Mono — Google Fonts
```

Redaction matters more than it looks. It ships in graded halftone cuts (10 / 20 / 35 / 50 / 70 / 100) that get progressively coarser, like a photograph reproduced through a screen. You're going to use that grade as **semantic information** — see the design doc.

---

# PART 1 — The art direction

Create `docs/DESIGN.md` and paste this whole section into it. Then give Claude Code prompt 1.1.

---

## docs/DESIGN.md

### The idea: a darkroom, not a dashboard

News arrives over **the wire** as raw signal. It gets **developed** into a print you can read. You mark up a **contact sheet** to choose which frames survive. Then you make the **final print** and put it on the wall.

That's the whole product, and it's also the whole visual system. Every screen is one of those four rooms. The interface is dark because darkrooms are dark — and the things you're actually reading are luminous prints suspended in that dark.

This is deliberately *not*: a cyberpunk neon grid, a cream-and-terracotta editorial site, or a broadsheet pastiche with hairline rules. Those are the three places this kind of brief usually lands. We're going somewhere else.

### Palette — six values, no more

| Token | Hex | Role |
|---|---|---|
| `graphite` | `#12161B` | The room. App ground, edge to edge. |
| `selenium` | `#1E262F` | Raised machine surfaces — nav, sheets, controls. |
| `silver` | `#DAD5C9` | **The print.** Every piece of readable content sits on this. Warm, slightly foxed, never pure white. |
| `safelight` | `#FF8A3D` | **You.** Every human action: swipe right, your opinion, publish, select. |
| `fixer` | `#6D64A3` | **The machine.** Extraction, generation, AI states, graph structure. Carried over from the reference portfolio's theme colour so the Lattice reads as continuous with your other work. |
| `fixer-hot` | `#9A8EE0` | Active machine state only — a job actually running, a node actually selected. Used sparingly enough that it always means *now*. |
| `spike` | `#C4453C` | Reject. Left-swipe, discard, destructive. Used sparingly — it should feel like a decision. |

The safelight/fixer split is the most important rule in this document. **Colour encodes agency.** A user should be able to glance at any screen and know instantly which parts of it they made and which parts the machine made. Never use them decoratively. Never mix them in a gradient.

Neutrals derive from `graphite` and `silver` only. No grey ramp from a framework default.

### Type — three faces, three jobs

**Redaction** — display. Briefing headlines, screen titles, the big moments.
The halftone grade carries meaning:
- `Redaction 100` (finest) — human-authored text. Your opinion, your edits.
- `Redaction 35` — briefings. Journalism, processed but faithful.
- `Redaction 10` (coarsest) — AI-generated copy, before you've touched it.

When a user edits AI text, the grade animates from 10 → 100 as they type. That single detail does more to communicate "this is yours now" than any label could.

**Instrument Sans** — interface. Buttons, labels, body, navigation. Set tight: `-0.011em` tracking at UI sizes.

**Martian Mono** — the wire. Timestamps, source counts, credit balances, cluster IDs, anything the machine measured. Always uppercase, always `0.08em` tracked, always small. It's instrument labelling, not text.

**Scale** (mobile / web):
```
display-xl   40 / 56   Redaction 35, -0.02em
display      30 / 40   Redaction 35
briefing     22 / 28   Redaction 35, 1.35 leading
body         16 / 17   Instrument Sans, 1.6 leading
label        13 / 14   Instrument Sans 500
wire         10 / 11   Martian Mono, 0.08em, uppercase
```

### Material

Prints are **objects**. They have edges, they cast shadows, they're not flat rectangles with `border-radius: 12px`.

- Print surfaces: `radius: 3px` (paper is cut, not rounded), a 1px inner highlight at 6% white on the top edge, and a real shadow — `0 24px 48px -12px rgba(0,0,0,0.7)`.
- Machine chrome: `radius: 10px`, no shadow, separated by tone not by border.
- Grain: a 2–3% opacity noise overlay across the entire app, always. It removes the flat-digital feeling in one line and unifies the 3D and 2D layers so they don't look bolted together.
- No glassmorphism. No frosted blur panels. That's a different decade's darkroom.

### Motion

Springs, not easings. Everything interruptible. Nothing over 400ms except the deliberate set-pieces.

```
snap     stiffness 400, damping 30    taps, toggles
settle   stiffness 220, damping 26    cards landing, sheets
develop  stiffness 90,  damping 20    the print-development reveal
```

**The develop transition** is the app's signature motion. When a briefing appears, it doesn't fade in — it *develops*: starts near-black with heavy grain, and over ~700ms the grain resolves and the silver surface emerges, exactly like watching a print come up in a tray. Used only for briefings and finished content. Never for UI chrome.

Respect `prefers-reduced-motion`: all springs collapse to 120ms opacity fades, the develop transition becomes a straight cut, 3D falls back to static composition.

### The three signatures

**1. The Contact Sheet** — the version picker, rendered as an actual photographic contact sheet. A grid of numbered frames on a single silver print. Frame numbers in Martian Mono down the left edge. Selecting a frame draws a **grease-pencil circle** around it, in safelight orange, stroked on with a hand-drawn wobble over 300ms — the gesture a photo editor has made for a hundred years.

**2. The Wire Room** — every backend process, visible and live. Not a log viewer: a signal-flow diagram where data physically moves between stages, every node inspectable, every cost accruing in real time. See its own section below.

**3. The Lattice** — the 3D knowledge graph. See its own section below.

Everything not on this list stays quiet. The restraint is what makes these three land.

---

### THE WIRE ROOM — transparent processing

*Mandatory build. This is not a debugging tool — it's a primary screen.*

The premise: nothing the machine does is hidden. A user in BYOK or local mode is spending their own money and their own GPU; a user on the paid tier is spending credits. In all three cases, opacity is a trust failure.

**What it shows.** A horizontal signal-flow diagram of the live pipeline:

```
SOURCES ──▶ FETCH ──▶ EMBED ──▶ CLUSTER ──▶ BRIEF ──▶ RANK ──▶ [you] ──▶ GENERATE ──▶ PUBLISH
```

Each stage is a node in `selenium` with a Martian Mono label and a live counter. Work in flight travels between nodes as small particles in `fixer-hot` — one particle per item, moving at a speed proportional to actual throughput. When a stage is idle the particles stop. The screen is genuinely dead when nothing is happening, and that honesty is the point.

**Inspection.** Tapping any stage opens a Print panel showing:
- The last 50 events through that stage, newest first
- For model calls: provider, model ID, token counts, latency, cost in cents, and the actual prompt and response
- For ingestion: source, HTTP status, items fetched vs. new, quota units consumed
- For generation: the full job record including estimate vs. actual

**Quota and budget meters** run along the top: YouTube API units consumed against the daily 10,000 ceiling, X API spend, credits burned today, and in local mode, GPU VRAM and queue depth. These are the numbers that break the product when nobody's watching them, so they're never more than one screen away.

**The architectural consequence:** this cannot be retrofitted. Every backend operation must emit a structured trace event from Phase 1. Build the event spine before the pipeline, not after.

---

### THE LATTICE — the 3D knowledge graph

*Mandatory build. Named for the silver halide crystal lattice in film emulsion — the structure on which an image develops when light hits it. Your interests are the lattice; the news is the light.*

**Why this graph earns its place.** It is not decoration and not a generic force-directed blob. Three reasons it belongs specifically in this product:

1. **The data already exists.** Every briefing has an embedding, computed for deduplication and ranking. The graph is a projection of a structure the app maintains anyway — nothing is fabricated to fill the screen.
2. **It's the proof the app is learning.** The single hardest thing to communicate about a personalisation system is that it's working. A map of your own taste, visibly densifying week over week, does it without a word of copy.
3. **It's a control surface, not a readout.** You act on it. Boost a region, mute a region, and your protocol changes.

**Structure.**

| Element | Meaning |
|---|---|
| Node (large) | A topic region — a cluster of semantically related news clusters |
| Node (small) | An individual briefing |
| Node (satellite) | A source domain |
| Node (bright, `safelight`) | A briefing you wrote a take on — these are *yours* |
| Edge | Real cosine similarity above threshold. Thickness = strength. |
| Node size | Engagement volume |
| Node luminance | Recency — old nodes darken but never vanish |

**Position is real.** Run UMAP on the briefing embeddings down to 3 dimensions, cache the projection, and use it to seed a force-directed layout. Regions of the graph correspond to actual regions of semantic space. Two nodes near each other are near each other in meaning. This is the difference between a knowledge graph and a screensaver.

**The exposure metaphor.** Unengaged nodes sit dim and cool in `fixer` — unexposed crystals. Nodes you've taken a position on are exposed: brighter, warmer, drawn in `safelight`, with a faint bloom. Watching your lattice expose over weeks is the retention mechanic.

**Interaction.**
- Orbit, pan, zoom. Momentum on release.
- Hover a node: it and its neighbours lift out; everything else drops to 15% opacity
- Tap a node: a Print panel slides in with the briefing, your take if you wrote one, what you published, and how it performed
- Tap a region label: boost, mute, or add to a protocol — the graph is how you edit your own feed
- **Timeline scrub** along the bottom: drag back through time and watch the lattice grow from nothing. This is the single most compelling thing in the app to show another person.
- Search: type, and matching nodes flare while the rest recede

**Performance.** Instanced meshes for nodes, a single merged `BufferGeometry` for edges, LOD by camera distance, frustum culling. Target 60fps at 2,000 nodes on desktop and 500 on mobile. Above the node budget, collapse the least-engaged nodes into region aggregates rather than dropping frames.

**Reduced motion / low power:** falls back to a static 2D projection with the same colour semantics and the same tap targets. Never a blank state.

### Voice

Interface copy is plain, active, and specific. Buttons say what happens: "Post it," not "Submit." Errors state what broke and the next move, without apologising. Empty states are invitations, not decorations.

The machine never speaks in first person. It doesn't say "I've generated 3 versions." It says "3 versions ready."

---

# PART 2 — Backend

### 1.1 — Ground the design system

```
Read docs/DESIGN.md end to end.

Produce two artefacts and nothing else this turn:

1. packages/shared/tokens.ts — every design token from that document as typed
   exports: colours, the type scale, spacing (4px base), radii, shadows, and
   the three spring configs. This file is the single source of truth; both apps
   import from it.

2. docs/DESIGN-CRITIQUE.md — your honest read on the direction. Specifically:
   which parts of it, if you were building this without the document, would you
   have produced by default anyway? Name them. Those are the parts that are
   probably weak. Propose one concrete change that would make the system more
   specific to a news-and-opinion product and less applicable to any dark-themed
   app.

Do not write any component code yet.
```

*Read the critique before continuing. If it identifies something as generic, decide whether to take the note. This is the cheapest design review you'll ever get.*

---

### 2.1 — Monorepo and tooling

```
Set up the monorepo per CLAUDE.md. pnpm workspaces + Turborepo for the TS side,
uv for Python.

Deliverables:
- Root turbo.json, pnpm-workspace.yaml, .gitignore, .env.example
- services/api: FastAPI app, health endpoint, structured JSON logging, settings
  via pydantic-settings, ruff + mypy strict configured and passing
- docker-compose.yml: Postgres 16 with pgvector, Redis 7
- Makefile: make dev, make test, make lint, make migrate
- .github/workflows/ci.yml running lint + typecheck + test on both stacks

Acceptance: `make dev` brings up the full stack, `curl localhost:8000/health`
returns 200, `make lint` and `make test` both exit 0.
```

---

### 2.2 — Data model

```
Design and implement the complete schema. Alembic migration + SQLAlchemy 2.0
async models + Pydantic schemas.

Model these domains:

SOURCES & PROTOCOLS
- source (rss | reddit | youtube | newsapi | web), with per-type config JSONB
- user_protocol: a user's named source set + topic interest vector + filters
- protocol_source join

CORPUS (shared — this is the cost-critical part)
- raw_item: fetched content, source ref, canonical URL, fetched_at, content_hash
- cluster: a deduplicated news event. Holds the centroid embedding.
- cluster_member: raw_item -> cluster, with similarity score
- briefing: ONE per cluster. 60-word body, headline, source links array,
  embedding, published_at, expires_at

PER-USER
- feed_item: briefing x user, with rank score and served_at
- swipe: feed_item, direction, swiped_at, dwell_ms
- take: the user's opinion on a kept briefing. Text + optional audio ref +
  detected stance + confidence

GENERATION
- generation_job: state machine (queued/running/succeeded/failed/cancelled),
  content_type, variant_index, provider_id, cost_estimate_cents,
  cost_actual_cents, idempotency_key
- artifact: the output. type, storage_uri, dimensions, duration_ms, metadata,
  parent job, TTL

PUBLISHING
- social_account: platform, external id, encrypted token ref, connected_at
- publication: artifact -> social_account, scheduled_for, posted_at,
  external_post_id, status

BILLING
- entitlement: user tier, credit balance, period reset
- credit_ledger: append-only. Every debit and credit with job reference.
  Balance is always derived by sum, never stored as a mutable column.
- byok_credential: provider, encrypted key ref, daily_cap_cents, spent_today

Requirements:
- pgvector indexes (HNSW) on cluster.centroid and briefing.embedding
- Partial indexes for the hot paths: unserved feed items per user, running jobs
- Every table has created_at/updated_at, UUIDv7 primary keys
- No cascading deletes on anything financial

Write the migration, the models, and a seed script that generates a realistic
dev dataset: 3 users, 200 raw items, ~60 clusters, ~60 briefings.
```

---

### ✓ 2.3 — Verify the model

```
Write integration tests against a real Postgres (testcontainers, not sqlite)
that prove:

1. Two users following overlapping protocols share the SAME briefing rows —
   assert the briefing count doesn't grow with user count
2. Credit balance derived from the ledger matches expected after a mixed
   sequence of debits, refunds, and period resets
3. Vector similarity search returns clusters in correct order and uses the HNSW
   index (assert on EXPLAIN output)
4. Deleting a user leaves the shared corpus intact

Then run them and fix what fails.
```

---

### 2.3b — The trace spine

*Build this before the pipeline. The Wire Room is unbuildable without it and impossible to retrofit cleanly.*

```
Build the observability spine that makes transparent processing possible.

Core model — pipeline_event, append-only:
  id, trace_id, span_id, parent_span_id
  stage        (fetch|embed|cluster|brief|rank|generate|publish)
  entity_type, entity_id
  user_id      (nullable — corpus stages aren't user-scoped)
  status       (started|progress|succeeded|failed)
  started_at, ended_at, duration_ms
  payload      JSONB — stage-specific, and for model calls it MUST include
               provider, model, prompt, response, input_tokens, output_tokens,
               cost_cents
  error        JSONB nullable

Requirements:

1. A @traced decorator/context manager that any pipeline function wraps in.
   Emitting an event must be one line at the call site, or people stop doing it.
2. Trace context propagates through Celery tasks — a briefing generated from an
   item fetched an hour ago shares a trace_id with that fetch.
3. Live streaming: GET /events/stream — Server-Sent Events, filterable by stage
   and user. Redis pub/sub behind it, so a worker on another machine still
   reaches the client.
4. Aggregates endpoint: GET /events/summary returning per-stage throughput,
   p50/p95 latency, error rate, and cost over a window. The Wire Room's meters
   read from here, not by scanning raw events.
5. Retention: full payloads 7 days, then drop prompt/response text and keep
   metrics indefinitely. Prompts and responses are the expensive part.
6. Redaction: API keys, tokens, and PII never enter a payload. Write a test
   that asserts a payload containing an API-key-shaped string is rejected.

Acceptance: run the full ingest → brief pipeline and reconstruct the complete
journey of one briefing — every stage, every model call, every cost — from
pipeline_event alone, with a single trace_id query.
```

---

### 2.4 — The provider abstraction

*This is the most important file in the codebase. It's what makes local GPU mode possible without touching business logic.*

```
Build services/api/providers/ — the abstraction every model call goes through.

Define these protocols (Python Protocol classes, structurally typed):

  TextProvider    .complete(messages, *, model, max_tokens) -> TextResult
  EmbeddingProvider .embed(texts) -> list[vector]
  ImageProvider   .generate(prompt, *, size, n, seed) -> list[ImageResult]
  VideoProvider   .generate(prompt, *, init_image, duration_s) -> VideoJob
  AudioProvider   .transcribe(audio) -> TranscriptResult

Every result type carries: cost_cents, latency_ms, provider_id, model_id.

Implement adapters:
  CLOUD   anthropic, openai, google, fal (image + video), deepgram
  LOCAL   ollama (text), llamacpp (text), comfyui (image + video),
          faster-whisper (audio), sentence-transformers (embeddings)

Then build the router on top:

  ProviderRouter.resolve(capability, user) -> Provider

Resolution order:
  1. If user is in local mode AND a healthy local provider offers the
     capability -> local
  2. If user has a BYOK credential for a cloud provider offering it -> that,
     billed to their key, checked against their daily cap
  3. Platform cloud provider, billed to platform credits
  4. Raise CapabilityUnavailable with a message naming what's missing and how
     to fix it

Also required:
- estimate_cost(capability, params) -> cents, callable WITHOUT running the job.
  Video estimation must be accurate to the second.
- Circuit breaker per provider: 5 failures in 60s opens for 5 minutes
- Every adapter has a contract test asserting it satisfies the protocol, using
  a recorded fixture so tests run offline

Acceptance: swapping a user from cloud to local mode changes zero lines outside
providers/. Prove it with a test that runs the same generation twice under both
configurations.
```

---

### 2.5 — Ingestion

```
Build the ingestion layer as Celery tasks.

Adapters, one module each, all implementing a common SourceAdapter interface:
- RSS/Atom (use feedparser, handle malformed feeds, respect etag/last-modified)
- Reddit (praw, respect rate limits, per-subreddit)
- YouTube (Data API — CRITICAL: track quota units consumed in Redis with a
  daily budget. search.list costs 100 units, the project cap is 10,000/day.
  Prefer playlistItems.list over search where possible. Refuse to run and log
  loudly at 80% consumption rather than getting a surprise 403.)
- News API (pluggable: NewsData / GNews / Mediastack behind one interface)
- Generic web (readability extraction, with robots.txt respected)

Scheduling:
- Celery beat, staggered by source to avoid thundering herd
- Per-source adaptive interval: sources that publish rarely get polled less
- Content-hash dedup at fetch time so unchanged items cost nothing downstream

Observability: every run emits items_fetched, items_new, quota_consumed,
duration, errors. Structured logs, not prints.

Acceptance: `make ingest-once` populates raw_item from at least three source
types against real endpoints, and running it twice adds zero duplicate rows.
```

---

### 2.6 — Dedup, cluster, brief

```
The corpus pipeline. This runs once per cycle for ALL users.

Stage 1 — Embed
  Batch-embed new raw_items via EmbeddingProvider. Batch size 64.

Stage 2 — Cluster
  Assign each item to an existing cluster if cosine similarity to its centroid
  exceeds 0.86, else open a new cluster. Update centroids incrementally.
  Time-window the candidate set to 72h so clustering stays O(recent), not O(all).

Stage 3 — Brief
  For each cluster with no briefing, or whose membership grew by >40% since its
  briefing was written, generate a briefing via TextProvider.

  The briefing prompt must produce:
  - A headline under 9 words, no clickbait constructions, no colons
  - Body of 50-60 words. Hard ceiling 60. Reject and retry once if over.
  - Strictly factual. No adjectives that imply judgement. This is the neutral
    substrate the user's opinion sits on top of — if the briefing has a slant,
    the product is broken.
  - Every claim traceable to a source in the cluster

  Attach ALL source URLs from the cluster, ranked by domain authority, deduped
  by domain.

Stage 4 — Expire
  Briefings older than 48h leave the active pool. Soft delete, keep for
  analytics.

Cost control: assert in code that briefing generation count per cycle equals
new-or-changed cluster count, and is completely independent of user count.
Write a test that adds 100 users and asserts generation count is unchanged.
```

---

### 2.7 — Ranking

```
Build per-user feed ranking over the shared briefing pool.

Score = weighted sum of:
  - cosine(briefing.embedding, user.interest_vector)        weight 0.45
  - protocol source match (did it come from their sources)  weight 0.25
  - recency decay, half-life 8 hours                        weight 0.20
  - diversity penalty against already-selected clusters      weight 0.10

Then:
- MMR re-rank so the user doesn't get 20 briefings about one story
- Cap at 3 briefings per source domain per day
- Take top N (50 paid / 20 free) into feed_item

Interest vector learning:
- Right swipe: move the vector toward the briefing embedding, lr 0.08
- Left swipe: away, lr 0.03 (asymmetric — dislike is weaker signal than like)
- Dwell time above 4s without a swipe: small positive nudge
- Normalise after every update

Expose GET /feed returning today's ranked items with a stable cursor so the
client can resume mid-deck.

Acceptance: a test where a synthetic user swipes right on 10 AI-related
briefings and their subsequent feed shows measurably higher AI-topic density.
```

---

### 2.7b — The learning system

*Four loops. Every human-in-the-loop moment is a training signal — nothing the user does is discarded.*

```
Build the personalisation engine. Four independent loops, each learning from a
different human decision.

LOOP 1 — TASTE (what to surface)
  Signal: swipes, dwell time, source taps
  Model:  the interest vector from prompt 2.7
  Effect: feed ranking
  Already partly built — extend with per-topic-region weights so the user can
  like AI news but dislike AI funding news, which a single global vector can't
  express.

LOOP 2 — VOICE (how to write as them)
  Signal: every authored take, and every edit made to a suggested take
  Model:  a retrieval-augmented style profile. Do NOT fine-tune.
    - Store each authored take with its embedding
    - Maintain a rolling style profile: mean sentence length, vocabulary
      distinctiveness vs. baseline, stance frequency, hedging ratio, humour
      markers, punctuation habits, emoji use
    - At generation time, retrieve the k=5 most semantically similar past takes
      and inject as few-shot examples, plus the style profile as constraints
  Effect: generated content and suggested takes read progressively more like
    the user wrote them
  This is cheap, works from take #3, and needs no training infrastructure.
  LoRA is an upgrade path, not a starting point.

LOOP 3 — FORMAT (what content works for their audience)
  Signal: contact-sheet picks + real engagement from published posts
  Model:  a per-user matrix of (topic_region x content_type x platform) ->
          success rate, Bayesian-smoothed so early data doesn't overfit
  Effect: variant generation biases toward formats that have worked. If memes
    land on tech news but explainers land on policy news for this specific
    user's audience, the contact sheet reflects that.

LOOP 4 — TIMING
  Signal: publish times vs. engagement
  Model:  per-platform, per-weekday hourly engagement curve
  Effect: scheduling suggestions

THE METRIC THAT MATTERS
  Track median edit distance between suggested takes and the user's final text.
  It should fall over weeks. That single number is the honest measure of
  whether the learning works, and it goes on the dashboard where the user can
  see it. Call it "voice match" and show it as a percentage.

Requirements:
- Every learning update is a discrete, logged event carrying which human action
  caused it. The user must be able to ask "why am I being shown this" and get a
  real answer.
- All four loops are resettable independently from settings.
- Cold start: fall back to protocol-based ranking and generic stance suggestions
  with no degradation in perceived quality. Never show an empty or obviously
  untrained experience.
- Write a simulation test: a synthetic user with a fixed hidden preference
  function, 200 swipes, asserting the ranker's agreement with that hidden
  function increases monotonically over the run.
```

---

### 2.8 — Swipe and take capture

```
Endpoints:

POST /swipe          batched — the client sends swipes in groups of 5 so a
                     50-card session is 10 requests, not 50. Idempotent on
                     (feed_item_id, client_event_id).
GET  /session/keeps  the right-swiped set, ordered for review
POST /take           the user's opinion on one keep

The take endpoint accepts either text or audio. If audio, transcribe via
AudioProvider, store both, return the transcript for confirmation.

Then the friction-killer — POST /take/suggest:
  Given a briefing, return 3 candidate takes the user can tap and edit rather
  than compose from scratch. Each is one or two sentences, first person, and
  they must be genuinely different stances — not three phrasings of the same
  opinion. Draw the stance set from the user's own swipe history where there's
  enough signal, generic otherwise.

  Mark every suggestion with source: "suggested". When a user edits one past a
  30% character-diff threshold, flip it to source: "authored". You need that
  distinction for the Redaction grade animation in the UI, and later for
  training a per-user voice model.

Acceptance: a 50-card session with 12 keeps and 12 takes completes in under 10
API round trips.
```

---

### 2.9 — Generation orchestration

*The lazy-generation rule lives here. Get this wrong and the business doesn't work.*

```
Build the generation orchestration layer. Celery canvas for now, with the
workflow logic isolated so it can move to Temporal later without a rewrite.

TIERS — enforce these in code, not convention:

  EAGER (auto, on take submission)
    3 text variants (long-form, short-form, punchy)
    3 still images
    GIFs synthesised locally from the stills (Ken Burns / crossfade via ffmpeg,
    zero model cost)
    Target: under $0.15 per briefing

  ON_DEMAND (explicit user action + entitlement check)
    Short video, up to 30s
    Target: ~$2

  GATED (explicit action + confirmation dialog showing the cost)
    Long-form video
    Storyboard generated first as a set of still frames the user approves,
    THEN image-to-video per frame, THEN ffmpeg concat
    Target: $18+

Hard requirements:
- A single `assert_tier_allowed(job, user)` gate that every job passes through.
  There must be no code path to a VIDEO job that isn't user-initiated. Write a
  test that greps the codebase for video provider calls and asserts each one is
  reachable only from a request handler.
- Cost estimated and persisted before the job runs. If actual exceeds estimate
  by >20%, log an alert.
- Idempotency keys on every job. A retried webhook never double-charges.
- Partial success is normal: if variant 2 of 3 fails, return 1 and 3 and mark
  the job partial. Never fail the whole set.
- Artifact TTL by tier: free 48h, paid 30d, then move to cold storage.

Free tier gets variant_count=1 and daily_selection_cap=3, enforced by
entitlement lookup, not by client.
```

---

### 2.10 — Credits and entitlements

```
Implement the billing layer.

Tiers:
  free   20 briefings/day, 3 selections/day, text + 1 image, no video,
         no publishing (copy to clipboard only)
  pro    50 briefings/day, credit-metered generation, publishing included
  byok   50 briefings/day, unlimited generation on user keys, platform fee,
         publishing as a paid add-on

Credit pricing table (cents of true COGS -> credits charged, ~2x markup):
  text variant       1
  image              2
  gif                2
  short video 20s    100
  long video 3min    900
  publish action     5

Rules:
- Balance is ALWAYS sum(credit_ledger). Never a mutable column.
- Debit happens at job start, refund on failure, within one transaction.
- Reserve-then-commit: a queued job holds a reservation so a user can't queue
  ten videos with credits for one.
- Stripe for subscription + credit top-ups. Webhook handler is idempotent.
- BYOK: envelope encryption via KMS. Keys never logged, never returned to the
  client, never sent to the frontend. Per-user daily spend cap enforced
  server-side independent of whatever cap they set at the provider.

Acceptance test: concurrent requests that would overdraw a balance — exactly
one succeeds, and the ledger sums correctly under load.
```

---

### 2.11 — Publishing

```
Build the publishing layer behind a PublishProvider interface so the vendor is
swappable — per-profile pricing on these services is the dominant cost at
scale and you will want to switch.

- Adapter for the chosen unified API (Ayrshare / bundle.social / Postiz)
- OAuth account linking flow, tokens encrypted at rest
- Scheduling with per-platform optimal-time defaults, user-overridable
- Per-account rate limiting — automated posting at volume gets accounts
  flagged. Default ceiling: 4 posts/account/day, hard cap 8.
- Retry with backoff on transient failures, dead-letter after 3
- Webhook receiver for post status, signature-verified

Free tier: publishing endpoints return 402 with an upgrade path. The client
gets a clipboard export instead. Publishing is the paywall.
```

---

### 2.12 — Local GPU mode

```
Make the app fully runnable against local models on the user's own GPU.

1. Hardware detection endpoint — GET /system/capabilities
   Reports: GPU model, VRAM total/free, CUDA/ROCm/Metal, whether Ollama is
   reachable, whether ComfyUI is reachable, which local models are pulled.

2. Capability tiers based on detected VRAM. Be honest about what won't run:
     <8GB   text only (7B quantised) + embeddings. No image, no video.
     8-16GB text + SDXL/Flux-schnell images. Video unrealistic.
     16-24GB text + Flux-dev images + short video (Wan / Hunyuan, ~5s clips,
            several minutes per generation)
     24GB+  everything, with long video as a background job measured in tens
            of minutes

3. Local adapters:
   - Ollama: text + embeddings. Auto-pull missing models with progress.
   - ComfyUI: image + video via the HTTP API. Ship workflow JSON templates in
     services/api/providers/local/workflows/ — parameterised, not hardcoded.
   - faster-whisper: local transcription for voice takes.

4. Docker compose profile `local-gpu` that brings up Ollama and ComfyUI with
   GPU passthrough, plus a first-run setup script that pulls required models
   and reports total disk needed before downloading anything.

5. Graceful degradation: if a local capability is unavailable mid-session,
   surface a clear choice — wait, fall back to cloud (with cost shown), or
   skip. Never silently bill someone who chose local mode to avoid billing.

6. The queue behaves differently locally: a single GPU means serial execution.
   Local jobs run with concurrency 1 and the UI shows honest queue position and
   ETA rather than a spinner that implies parallelism.

Acceptance: with LOCAL_MODE=1 and Ollama running, the full flow — ingest,
brief, take, generate text + images — completes end to end with zero outbound
API calls to any paid provider. Prove it with a test that fails if any request
leaves the machine.
```

---

# PART 3 — Frontend

*Run these against a working API. Building UI against mocks produces UI that breaks on contact with real data.*

### 3.1 — Design system implementation

```
Read docs/DESIGN.md again before starting.

Build packages/ui — the shared design system consumed by both apps.

- Token bridge from packages/shared/tokens.ts to Tailwind config (web) and a
  typed theme object (native)
- Font loading for Redaction, Instrument Sans, Martian Mono with correct
  fallback metrics so there's no layout shift
- Primitives: Print (the silver content surface, with its shadow and top
  highlight), Chrome (dark machine surface), Wire (the mono label component),
  Grain (the app-wide noise overlay)
- Motion: the three named springs as reusable hooks/variants, and a
  useReducedMotion that actually collapses them
- A Redaction component whose halftone grade is a prop, and can animate
  between grades

Then build a gallery route at /_dev/gallery showing every primitive in every
state, light on content and heavy on variation.

Use Playwright to screenshot the gallery. Look at it. Critique your own work
against DESIGN.md specifically: is the silver actually reading as a physical
print, or as a light-mode card? Is the grain visible without being noisy? Fix
what's wrong before moving on, and tell me what you changed.
```

---

### 3.2 — App shell

```
Build the mobile shell in apps/mobile.

- Expo Router with the four rooms as the navigation model: Wire (feed/deck),
  Darkroom (takes + generation), Prints (library + scheduled), Studio
  (protocols + settings)
- Tab bar in selenium, but the active tab is marked with a safelight underline
  that slides between positions using the settle spring — not a colour swap
- A persistent wire ticker along the top edge: source names and briefing counts
  in Martian Mono, scrolling slowly, pausing on tap to reveal the source list.
  It's ambient, it's honest data, and it makes the app feel alive when idle.
- App-wide Grain overlay
- Auth screens: sign in / sign up. Keep these unusually restrained — the
  contrast makes the deck land harder when it appears.

Screenshot every screen. Show me.
```

---

### 3.3 — The swipe deck

*This is the hero. Budget real time here.*

```
Build the swipe deck. This is the moment the app is judged on.

Structure:
- react-three-fiber scene via expo-gl. Perspective camera. The deck is real
  geometry in z-space — 5 cards visible, receding with scale and blur.
- Each card is a plane textured with the briefing content rendered to a
  drawing buffer, so the type is crisp Redaction, not a 3D font.
- Drag via Gesture Handler, driven by Reanimated shared values that feed the
  3D transform on the UI thread. It must not go through JS on every frame.

Interaction:
- Drag tilts the card on X and Y with subtle perspective, max 12°
- The lifted card casts a soft moving shadow onto the cards behind it — this
  single detail is what sells the physicality, get it right
- Past 30% threshold, an edge glow appears: safelight right, spike left, with
  opacity mapped to drag distance
- Release past threshold: the card flies off with velocity carried from the
  gesture, and the next card rises with the settle spring
- Release below: it springs back, no penalty, no bounce overshoot beyond 4%
- The wire particle field in the background thins as the stack depletes

Each card shows: headline in Redaction 35, 60-word body, source chips in
Martian Mono with domain names, relative time. Tapping a source chip opens the
original in a browser sheet without losing deck position.

Also required:
- Undo the last swipe (shake gesture or a small persistent control)
- Progress: "17 / 50" in Martian Mono, never a progress bar
- The end-of-deck state should feel like an achievement, not an empty list
- 60fps on a mid-range Android. Profile it. If the shadow costs too much,
  bake it rather than dropping it.

Screenshot mid-drag at several angles and show me. If it doesn't look physical,
iterate before moving on.
```

---

### 3.4 — Take capture

```
Build the opinion capture flow. This is where users quit — every interaction
here should cost them under 5 seconds.

Screen: one kept briefing at a time, on its Print surface.

Below it, three suggested takes as tappable cards, each labelled with its
stance in Martian Mono (SKEPTICAL / OPTIMISTIC / CONTRARIAN). Rendered in
Redaction 10 — coarse, obviously machine-made.

Tapping one moves it into an editor. As the user types, the Redaction grade
animates 10 -> 100. By the time they've meaningfully edited it, it visibly
belongs to them. No copy explains this. It just happens.

Also:
- Hold-to-record voice input, with a live waveform in safelight, transcribed
  on release into the same editor
- Skip — not every keep needs a take
- Swipe between keeps, position preserved
- A running count that reads as progress, not obligation

The develop transition plays as each briefing enters.
```

---

### 3.5 — The Contact Sheet

*The signature. Maximum craft here.*

```
Build the version picker as a photographic contact sheet.

Layout: a single silver Print surface holding a grid of frames. Frame numbers
run down the left edge in Martian Mono. Sprocket-hole marks along the top and
bottom edges, drawn — not an image asset.

Frames vary by content type:
- Text variants: the copy set in Redaction, scaled down, readable enough to
  judge
- Images: the render
- Video: first frame with a duration badge
- Not-yet-generated (video, gated): the frame is empty with a fine cross-hatch
  and a cost in credits. Tapping it opens the confirmation.

Selection:
- Tap draws a grease-pencil circle around the frame — safelight, 3px, with a
  hand-drawn wobble, stroked on over 300ms following the path like it's being
  drawn. Use Skia for the stroke, not an SVG animation.
- Selecting a second frame in the same content type moves the circle
- A rejected frame can be crossed out with a two-finger swipe — a single
  diagonal grease stroke in spike

Long-press any frame to open it full-bleed with the generation metadata:
which provider, what it cost, seed, prompt. Power users want this and it costs
you nothing to show.

Below the sheet: the selected set, and a single safelight action — "Make the
print."

Screenshot the sheet with a mixed set of frames and several selections drawn.
This is the screenshot that goes in your app store listing, so iterate until
it's genuinely beautiful.
```

---

### 3.6 — Generation states

```
Replace every spinner in the generation flow with the forge.

- A slow-rotating volumetric form in r3f. At 0% it's a diffuse cloud of fixer-
  tinted particles; as the job progresses, the particles converge into a
  defined solid. At 100% it resolves and the artifact develops in its place.
- Honest ETA in Martian Mono beneath it. If you don't know, say "estimating"
  rather than showing a fake percentage.
- Local mode shows queue position and a real per-job estimate, because a local
  GPU is serial and pretending otherwise is a lie the user will notice.
- Failure: the form collapses back to particles and disperses. Error copy
  states what failed and offers the specific next action — retry, switch to
  cloud with cost shown, or skip.
- Multi-variant jobs show three forges. Partial success is normal and must look
  normal, not broken.
```

---

### 3.6b — THE WIRE ROOM

*Signature build. Read the Wire Room section of docs/DESIGN.md first.*

```
Build the Wire Room — the live, inspectable view of every backend process.
Web-first (denser, better for inspection), with a simplified mobile version.

DATA
- Subscribe to GET /events/stream over SSE. Reconnect with exponential backoff
  and replay missed events from the last received id.
- Poll /events/summary every 5s for the meters.
- Never poll the raw event log. The stream is the source of truth.

THE DIAGRAM
- Horizontal flow: SOURCES → FETCH → EMBED → CLUSTER → BRIEF → RANK → [YOU] →
  GENERATE → PUBLISH
- Each stage is a selenium node with a Martian Mono label and live counter
- [YOU] is rendered in safelight and shaped differently from the machine stages
  — it is the one stage the machine cannot do, and the diagram should say so
  without a caption
- Items in flight travel between nodes as particles in fixer-hot. One particle
  per real item. Speed proportional to actual throughput. When nothing is
  happening, nothing moves. Do not add idle animation.
- Failing stages pulse in spike. Stalled stages desaturate.
- Use r3f for the particle layer, DOM for the nodes and labels — text stays
  crisp and accessible, particles stay cheap.

METERS (top strip, always visible)
- YouTube API units used / 10,000 — turns spike above 80%
- X API spend today
- Credits burned today, against balance
- In local mode: VRAM used/free, queue depth, current job ETA
Each meter is a thin horizontal bar in Martian Mono. No gauges, no dials.

INSPECTION
Tapping a stage opens a Print panel:
- Last 50 events, newest first, virtualised
- Model calls expand to show provider, model, tokens in/out, latency, cost, and
  the full prompt and response in a monospace block with copy buttons
- Ingestion events show source, status, fetched vs new, quota consumed
- Generation events show estimate vs actual cost, with the delta highlighted if
  it exceeds 20%
- A "follow this item" control that filters the whole diagram to one trace_id
  and replays its journey through the pipeline

Also required:
- Pause / resume the stream
- Filter by stage and by mine-only vs everything
- Export the visible window as JSON

Screenshot it under real load with jobs running and show me.
```

---

### 3.6c — THE LATTICE

*Signature build. Highest craft ceiling in the app. Read the Lattice section of docs/DESIGN.md first.*

```
STEP 1 — Study the reference implementation.

I have a previous project whose neural-map section defines the look and feel I
want carried into this app. It is on this machine. Before writing any code:

  1. Locate the repo (ask me for the path if you can't find it)
  2. Find the AI / neural-map section component and everything it imports
  3. Read the Three.js setup completely: geometry construction, materials,
     shaders, lighting rig, bloom/postprocessing chain, camera and controls
     config, the force layout or positioning maths, GSAP timelines, and the
     interaction handlers
  4. Write docs/LATTICE-REFERENCE.md documenting exactly what produces the
     feel: the specific material params, the bloom settings, the easing curves,
     the node and edge geometry, the colour treatment, the camera behaviour

Do not proceed until that document exists and I've confirmed it. Getting the
feel right matters more here than shipping fast — this is a signature element
across my products and it needs to be recognisably the same hand.

STEP 2 — Build the Lattice using those extracted parameters.

Reuse the reference's visual language exactly: same material approach, same
bloom character, same motion feel, same camera behaviour. Adapt the palette to
this app's tokens — fixer for unexposed nodes, safelight for exposed ones —
keeping the reference's luminance relationships intact.

DATA
- GET /graph returns nodes, edges, and a cached 3-D UMAP projection of briefing
  embeddings. Positions come from real semantic space, seeding a force layout
  for readability. Never random.
- Node types: region (large), briefing (small), source (satellite)
- Edges are cosine similarity above threshold, thickness by strength
- Every node carries: engagement count, has_take boolean, last_touched,
  published_count

VISUAL SEMANTICS
- Unexposed (no take): dim, cool, fixer
- Exposed (you wrote a take): brighter, warmer, safelight, faint bloom
- Size by engagement, luminance by recency — old nodes darken, never disappear
- Regions get Martian Mono labels that fade in above a zoom threshold and
  billboard toward the camera

INTERACTION
- Orbit / pan / zoom with momentum
- Hover: node and its neighbours lift, everything else drops to 15% opacity
- Tap: Print panel with the briefing, your take, what you published, how it did
- Region tap: boost / mute / add to protocol — this graph edits the feed
- Timeline scrub along the bottom: drag back through time and watch the lattice
  grow from nothing. Build this properly, it's the demo moment.
- Search: matching nodes flare, the rest recede

PERFORMANCE
- InstancedMesh for nodes, one merged BufferGeometry for edges
- LOD by camera distance, frustum culling
- 60fps at 2,000 nodes desktop / 500 mobile. Above budget, collapse
  least-engaged nodes into region aggregates — never drop frames.
- Profile it and report the numbers.

FALLBACK
- prefers-reduced-motion or low-power: static 2D projection, same colour
  semantics, same tap targets. Never a blank state.

Screenshot at three zoom levels and at two points on the timeline scrub. Put
them side by side with a screenshot of the reference implementation and tell me
honestly where they diverge.
```

---

### 3.7 — Publishing

```
Build the publish flow.

- Account picker: connected platforms as chips. Connected = full colour,
  available = outline. OAuth in a browser sheet.
- Per-platform preview rendered accurately — character limits, aspect ratio
  crops, link preview cards. Users need to see what actually posts.
- Schedule: a horizontal timeline rather than a date picker, with suggested
  slots marked. Drag a post onto a slot.
- The publish action is the largest safelight element in the app. It's the
  moment of user agency the whole product exists for.
- Free tier: publish is replaced by "Copy for [platform]" which copies text and
  saves media to the camera roll, plus one honest line about what upgrading
  changes. Do not nag. Do not use a modal.
```

---

### 3.8 — Dashboard

```
Build the web dashboard in apps/web — Next.js, same tokens, denser layout.

Views:
- Overview: posts published, engagement where the platform APIs expose it,
  credits consumed against balance, briefings processed
- Charts in a custom style, not a library default. Use Visx or hand-rolled SVG.
  Sparse gridlines in graphite, series in fixer, user-driven metrics in
  safelight — the colour semantics hold here too.
- Voice profile: which stances the user takes most, which topics they engage
  with, how their interest vector has drifted over time. This is genuinely
  interesting to the user and it's the strongest retention surface you have.
- Protocol editor: sources as a manageable list, live preview of what today's
  feed would look like given a change
- Cost transparency: every generation with its actual cost. Especially
  important in BYOK mode — trust is the entire product there.
```

---

### 3.9 — Onboarding

```
Build first-run. The whole job is getting someone to their first swipe fast.

- Interest selection as a swipe deck of topic cards — teaches the core gesture
  before it matters
- Source suggestions derived from those topics, pre-checked, editable, skippable
- Optional account connection, clearly skippable
- Mode choice for technical users: cloud (default), BYOK, or local. Run the
  capability probe for local and report honestly what their machine can do.
  Do not promise video on 8GB.
- First deck seeded and ready before onboarding ends, so the transition into
  the app is into content, not an empty state

Hard target: under 90 seconds from launch to first swipe on the cloud path.
Time it and tell me the number.
```

---

# PART 4 — Verification

### ✓ 4.1 — Visual QA

```
Using Playwright, screenshot every screen in the web app at 390px, 768px, and
1440px, in default and reduced-motion.

Produce docs/VISUAL-AUDIT.md with each screenshot and an honest critique
against docs/DESIGN.md. Flag specifically:
- Anywhere safelight and fixer are used in a way that breaks the agency
  semantics
- Anywhere the silver Print surface reads as a generic light card
- Type that isn't on the scale
- Motion that doesn't collapse properly under reduced-motion
- Anything that looks like a framework default rather than this design system

Then fix the top 10 issues and re-screenshot.
```

### ✓ 4.2 — Cost guardrails

```
Write the test suite that protects the unit economics:

1. No video generation is reachable from any background task or scheduler
2. Free tier cannot exceed 3 selections/day or 1 variant, enforced server-side
   even with a hostile client
3. Briefing generation count is independent of user count (add 1000 users,
   assert unchanged)
4. Concurrent credit spends cannot overdraw
5. BYOK daily caps hold under concurrency
6. Every generation path has a cost estimate before execution

Then write scripts/cost-model.py that simulates a month at 100 / 1k / 10k users
across a realistic tier mix and prints COGS per user per tier. Run it. Show me
the numbers.
```

### ✓ 4.3 — Load

```
k6 scenarios for the realistic peak: 8am, everyone opening the app at once.

- 1000 concurrent /feed requests
- 200 concurrent swipe batches
- 50 concurrent generation jobs

Targets: /feed p95 under 200ms, swipe under 100ms. Find the bottleneck, fix it,
re-run, report before and after.
```

---

# PART 5 — Prompting notes

**Give it the acceptance criteria, not the algorithm.** Fable 5 will pick a better implementation than you'd specify. "Assert briefing count doesn't grow with user count" is a better instruction than a description of how to cache.

**Make it critique its own work.** The prompts above ask for screenshots and self-critique repeatedly. This is the single highest-leverage prompting move for design work — a model that has looked at its output fixes things a model working blind never notices.

**When it goes wrong, don't patch — revert and re-prompt.** Once a session has produced a bad architectural decision, subsequent turns build on it. `git reset --hard`, improve the prompt, run again. Cheaper every time.

**Keep CLAUDE.md and DESIGN.md current.** When you make a decision in conversation, write it into the file. Otherwise it evaporates at the end of the session.

**Ask for the diff explanation on anything touching money.** "Explain what changed in the credit ledger logic and why it's still correct under concurrency" before you accept it.

---

## The phase gates

Do not let Claude Code run past a gate. Each one has a demonstrable outcome you can check with your own eyes. If you can't demo it, the phase isn't done, and building on top of it compounds the problem.

Open each phase with this framing prompt:

```
We're starting PHASE <N>: <name>.

Scope is strictly prompts <x> through <y>. Do not begin any later phase, do not
scaffold ahead, do not stub things "for later."

Before writing code: restate the phase goal, list what you'll build, and flag
anything in the spec that's ambiguous or that you think is wrong. Wait for my
answer.

When done: run the phase verification, show me the demo output, and stop.
```

| Phase | Prompts | Gate — you must be able to demo this |
|---|---|---|
| **0 — Foundation** | 0.1–0.5, 1.1, 2.1 | `make dev` runs. Design tokens exist. You've read and accepted the design critique. |
| **1 — Spine** | 2.2, 2.3, 2.3b | Seeded DB. One `trace_id` query reconstructs a full item journey. |
| **2 — Providers** | 2.4 | Same generation runs against cloud and against Ollama with zero changes outside `providers/`. |
| **3 — Corpus** | 2.5, 2.6 | Real briefings from real sources in your terminal. 1,000 synthetic users don't increase generation count. |
| **4 — Learning** | 2.7, 2.7b, 2.8 | Simulated user's ranking accuracy climbs monotonically over 200 swipes. |
| **5 — Generation** | 2.9, 2.10 | Take in, three text variants and three images out. Costs logged. Video provably unreachable from any background job. |
| **6 — Design system** | 3.1, 3.2 | Component gallery screenshot that looks like `DESIGN.md`, not like a framework default. |
| **7 — The loop** | 3.3, 3.4, 3.5 | **Ship to 50 users here.** Swipe 50 → write takes → pick from the contact sheet. Copy to clipboard. No publishing yet. |
| **8 — Signature I** | 3.6, 3.6b | Wire Room streaming live during a real generation run. |
| **9 — Signature II** | 3.6c | `LATTICE-REFERENCE.md` approved, then the graph, then the side-by-side comparison against your original. |
| **10 — Money** | 2.11, 3.7, 3.8 | Real post to a real account. Dashboard shows voice-match trending. |
| **11 — Local** | 2.12 | Full flow on your own GPU. A test fails if any request leaves the machine. |
| **12 — Harden** | 3.9, 4.1–4.3 | Visual audit clean, cost guardrails green, load targets met. |

**Phase 7 is the real milestone.** Everything before it is infrastructure; everything after it is amplification. Get fifty people swiping at the end of phase 7 and watch day-7 retention. If people don't come back to swipe, the Lattice and the Wire Room are beautiful things attached to a product nobody wants — and you'll have found that out ten weeks early instead of ten weeks late.
