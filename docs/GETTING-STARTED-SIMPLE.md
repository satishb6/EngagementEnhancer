# WIRE — the simple guide (100% free edition)

*Written for a non-technical owner. Everything in this guide is free: no
Docker, no server rental, no paid API keys. Same pattern as your EIP and
Helix apps — frontend on Vercel, backend on Hugging Face Spaces, keys pasted
in the app itself.*

Three stages:
- **Stage 1 — Run it on your computer** (today, ~10 minutes, nothing to install except once)
- **Stage 2 — Free AI keys** (optional but recommended, ~5 minutes, ₹0)
- **Stage 3 — Put it online free** (GitHub + Vercel + Hugging Face, ~45 minutes, ₹0)

---

## Stage 1 — Run it on your computer (no Docker!)

WIRE now runs in "lite mode": the database is a simple file (`wire.db`) and
the background worker lives inside the app. Nothing to install besides
Python parts it sets up itself.

1. Double-click **SETUP-WIRE.bat** (one time). Wait for "Setup complete".
2. Double-click **START-WIRE.bat** (every time). Two black windows open —
   minimise them. Your browser opens the app after ~15 seconds.
3. Sign in with the demo account: **pro@wire.dev** / **wire-dev-password**
   — or create your own account and do the 60-second onboarding.
4. Swipe the deck (drag right = keep, left = toss). Open the **Darkroom**,
   tap a suggested take, bend it into your words, press "Develop the
   prints". In a few seconds the contact sheet shows your text versions.
   Everything works with **zero keys** — that's Demo mode, honest and free.
5. Done? **STOP-WIRE.bat**.

> Demo mode writes with templates (labelled "demo" everywhere — no faking).
> The swiping, learning, ranking, Wire Room, and Lattice are all fully real.

## Stage 2 — Free AI keys (better writing, still ₹0)

Open the app → **Studio** → the **Engine** panel at the top. You'll see all
the providers with FREE badges. Recommended:

1. **Groq** (free, fast): click "get key ↗" next to Groq → sign up with
   Google → *Create API Key* → copy the `gsk_...` text → paste it into the
   Groq box in Studio. That's it — no restart, next take uses it.
2. **Google Gemini** (free): "get key ↗" → *Get API key* in AI Studio →
   paste into the Google box. This also upgrades the app's "understanding"
   (embeddings) so grouping and ranking get smarter.

Also available in the panel: **OpenRouter** (free models), **Ollama** (your
own GPU, fully private), and paid options (OpenAI, Claude, DeepSeek,
Mistral, fal.ai for real images) whenever you want them.

**Your keys never leave your browser** except inside your own requests —
the server doesn't store them, and every user of your app manages their own
keys the same way. This is exactly how your EIP engine panel works.

To pull real news right now instead of demo news: double-click
**GET-REAL-NEWS.bat** (RSS sources are free; add more in Studio → protocol).

## Stage 3 — Put it online, free

Same recipe as EIP/Helix: **backend → Hugging Face Space (Docker, free)**,
**frontend → Vercel (free)**. No Docker on your machine — Hugging Face
builds the container in their cloud.

### 3.1 GitHub (the code's online home)

1. github.com → sign up → **New repository** → name `wire`, Private → Create.
2. Tell me "push to my GitHub" in a session and I'll run it with you, or:
   in a terminal in the project folder:
   `git remote add origin https://github.com/YOURNAME/wire.git` then
   `git push -u origin main` (it will ask you to log in once).

### 3.2 Backend → Hugging Face Space

1. huggingface.co → sign up → your profile → **New Space**.
2. Name: `wire-backend` · License: any · SDK: **Docker** → Create Space.
3. Push the backend folder to the Space (from the project folder):
   ```
   git remote add space https://huggingface.co/spaces/YOURNAME/wire-backend
   git subtree split --prefix services/api -b hf-space
   git push space hf-space:main --force
   ```
   (It asks for your HF username + an access token from
   Settings → Access Tokens → "Write".)
4. The Space builds for a few minutes, then shows
   `https://YOURNAME-wire-backend.hf.space`. Open
   `.../health` — you should see `"status":"ok"`.
5. Optional (recommended): in Space **Settings → Variables & secrets**, add
   `GROQ_API_KEY` with your free Groq key — then even visitors who paste no
   key get real AI writing. Also optional: Settings → enable **Persistent
   storage** and it keeps history between restarts.

Free Spaces sleep when idle — the first visit of the day takes ~30–60s to
wake. That's the free-tier trade you already know from EIP.

### 3.3 Frontend → Vercel

1. vercel.com → sign up **with GitHub** → **Add New → Project** → pick your
   `wire` repo.
2. Set **Root Directory** to `apps/web`.
3. Add one Environment Variable:
   `NEXT_PUBLIC_API_URL` = `https://YOURNAME-wire-backend.hf.space`
4. Deploy. Two minutes later you have `https://wire-yourname.vercel.app` —
   share it with anyone; they bring their own free keys in Studio → Engine.

### Updating later
Push to GitHub (`git push`) → Vercel redeploys the site automatically.
For the backend, repeat the two subtree commands from 3.2.

---

## Quick tests that everything works

| Check | How | Expect |
|---|---|---|
| Engine alive | open `localhost:8000/health` (or your HF `/health`) | `"status":"ok"` |
| Zero-key loop | Demo engine, swipe 5 → take → sheet | text versions appear, labelled demo |
| Free key works | paste Groq key in Studio → new take | suggestions/posts read genuinely well |
| Transparency | Wire Room while generating | events with provider + cost (0.0 on free tiers) |
| Keys are safe | Wire Room → any model call → prompt/response | your key never appears anywhere |

## When something breaks
Read the last red line in the black window (or the HF Space "Logs" tab) and
paste it to me — that line is usually the whole diagnosis.

*The paid-scale path (Postgres + Redis + Celery + VPS, docs/DEPLOYMENT.md)
still exists untouched — flip `DATABASE_URL`/`REDIS_URL` when WIRE outgrows
the free tier.*
