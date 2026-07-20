---
title: WIRE Backend
emoji: 📡
colorFrom: gray
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# WIRE backend — FastAPI + embedded worker (lite mode)

The API half of WIRE (news → swipe → take → posts in your voice). Runs the
whole backend in one free-tier container: SQLite, background loops in-process,
zero-key demo engine, and per-request BYOK from the frontend.

- Health: `GET /health` · Docs: `/docs` · Live events: `GET /events/stream`
- Users' provider keys arrive as `X-Wire-Keys` headers per request and are
  never stored (a redaction guard rejects key-shaped strings from traces).
- Optional Space secrets to give everyone a default engine:
  `GROQ_API_KEY` and/or `GOOGLE_API_KEY` (both have free tiers).
- Optional: mount persistent storage at `/data` so history survives restarts.

Deployed from the monorepo with
`git subtree split --prefix services/api -b hf-space && git push space hf-space:main`.
