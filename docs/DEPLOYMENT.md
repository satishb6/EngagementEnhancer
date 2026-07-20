# Deploying WIRE — from this repo to a live URL

Two paths. **Path A (one VPS, Docker Compose, ~$12–25/mo)** is what I
recommend to launch: everything on one machine, TLS automatic, one command to
deploy. **Path B (managed platforms)** costs more but removes server care.

Phase-7 wisdom applies: ship the loop (deck → take → contact sheet →
clipboard) to your first 50 users before you worry about scale.

---

## What you need before either path

| Thing | Where | Needed for |
|---|---|---|
| A domain | Namecheap/Cloudflare, ~$10/yr | everything |
| Anthropic API key | console.anthropic.com | briefings, suggestions, composition |
| OpenAI API key | platform.openai.com | embeddings (~$0.10/mo at small scale) |
| fal.ai key | fal.ai | images (and video when you enable it) |
| NewsData key | newsdata.io (free tier) | news ingestion |
| Reddit app (script) | reddit.com/prefs/apps | reddit ingestion (optional day 1) |
| YouTube Data API key | console.cloud.google.com | youtube ingestion (optional day 1) |
| Deepgram key | deepgram.com | voice takes (optional day 1) |
| Stripe account | stripe.com | paid tiers (optional day 1 — free tier works without) |
| Ayrshare account | ayrshare.com | auto-publishing (optional day 1 — clipboard works without) |
| Cloudflare R2 bucket | dash.cloudflare.com | artifact storage (optional day 1 — local disk works) |

Only the first four are required for launch day. Everything else degrades
gracefully: no Stripe = everyone is free tier; no Ayrshare = clipboard
export; no R2 = artifacts on the server disk.

---

## Path A — one VPS with Docker Compose (recommended)

### A1. Get a server

Hetzner CX32 (4 vCPU / 8GB, ~€8/mo) or DigitalOcean 4GB (~$24/mo).
Ubuntu 24.04. 8GB RAM is comfortable for API + workers + Postgres + Redis +
web at hundreds of users.

```bash
# on your new server
apt update && apt install -y docker.io docker-compose-v2 git
```

### A2. Point DNS

At your DNS provider create two **A records** to the server's IP:

```
app.yourdomain.com  →  <server ip>
api.yourdomain.com  →  <server ip>
```

Wait until `ping app.yourdomain.com` resolves. Caddy needs this before it
can issue certificates.

### A3. Push this repo to GitHub and pull it on the server

```bash
# on your Windows machine, in the project root
git remote add origin https://github.com/<you>/wire.git
git push -u origin main

# on the server
git clone https://github.com/<you>/wire.git && cd wire
```

### A4. Configure

```bash
cp .env.production.example .env.production
nano .env.production
```

Fill in: the two domains, a Postgres password (`openssl rand -hex 24`),
`SECRET_KEY` (`openssl rand -hex 32`), `BYOK_MASTER_KEY`
(`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` —
or run it inside the api container later), and your provider keys.

### A5. Launch

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build
```

First build takes a few minutes. The `migrate` service runs Alembic and
exits; Caddy fetches TLS certificates automatically.

Verify:

```bash
curl https://api.yourdomain.com/health     # {"status":"ok","db":"ok",...}
docker compose -f infra/docker-compose.prod.yml logs -f worker   # beat ticking
```

Open `https://app.yourdomain.com` — sign up, and you're the first user.

### A6. Seed sources so the wire has something to say

```bash
docker compose -f infra/docker-compose.prod.yml exec api python -m wire_api.seed
docker compose -f infra/docker-compose.prod.yml exec api python -m wire_api.ingestion.run_once
```

`seed` creates dev users + demo corpus; for production you'll instead add
real sources via the DB or a small script — the `source` table rows drive
ingestion (kind `rss` + `{"url": ...}` config is the easiest start). The
Celery beat then ingests every 5 minutes and runs the corpus cycle every 10.

### A7. Deploying updates

```bash
git pull && docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build
```

### A8. Backups (do this in week one, not month three)

```bash
# nightly Postgres dump to R2/S3 — put in cron
docker compose -f infra/docker-compose.prod.yml exec -T db \
  pg_dump -U wire wire | gzip > /root/backups/wire-$(date +%F).sql.gz
```

Hetzner/DO server snapshots (a few $/mo) cover the rest.

---

## Path B — managed platforms (no server to run)

- **API + worker + Postgres + Redis → Railway** (railway.app): create a
  project from your GitHub repo; add services from `infra/api.Dockerfile`
  (one with default CMD for the API, one with the Celery command for the
  worker), add the Postgres and Redis plugins, paste the env vars. Railway
  Postgres supports pgvector (`CREATE EXTENSION vector`). ~$20+/mo.
  Render works identically (use its pgvector-enabled Postgres).
- **Web → Vercel**: import the repo, set the root directory to `apps/web`,
  set `NEXT_PUBLIC_API_URL=https://<your railway api url>`. Free Hobby tier
  is fine to start.
- Point your domain's CNAMEs at Vercel and Railway per their dashboards.

This path skips Caddy entirely — both platforms terminate TLS for you.

---

## Wiring the money and the posting (when you're ready)

**Stripe** — create two products (Pro ~$29/mo, BYOK ~$15/mo), copy the price
ids into `STRIPE_PRICE_PRO/BYOK`, then add a webhook endpoint
`https://api.yourdomain.com/billing/stripe/webhook` sending
`checkout.session.completed`, `invoice.paid`,
`customer.subscription.deleted`. Copy its signing secret to
`STRIPE_WEBHOOK_SECRET`. Credit top-ups: create Checkout sessions with
`client_reference_id=<user_id>` and `metadata.credits=<n>` — the webhook
grants idempotently.

**Ayrshare** — Business plan gives per-user profiles; put the key in
`AYRSHARE_API_KEY`. Account linking flows through
`POST /publish/accounts/link` which returns their hosted OAuth URL. The
vendor sits behind `wire_api/publishing/provider.py`; swapping to Postiz or
bundle.social is one adapter file.

**YouTube quota** — the app refuses YouTube calls at 80% of the 10k daily
units by design. Apply for the quota increase in month one; the form takes
weeks.

## Local GPU mode (optional, per user)

Users run `docker compose --profile local-gpu up` on their own machine
(Ollama + ComfyUI with GPU passthrough), then
`python scripts/local-gpu-setup.py` pulls models with an honest disk/VRAM
report. `POST /system/mode {"mode":"local"}` flips them over; the provider
router then refuses to bill them silently — cloud fallback is always an
explicit choice.

## The ops surface you already have

- `GET /health` — liveness + DB round trip (point uptime monitoring here;
  UptimeRobot free tier is enough)
- The **Wire Room** at `/room` — live pipeline, per-stage p95s, error rates,
  cost meters. This is your ops dashboard as much as the user's.
- `GET /events/summary` — the same numbers, as JSON, for alerting
- Structured JSON logs on stdout — `docker compose logs` or ship to Axiom /
  Grafana Cloud free tier later
- k6 load check: `k6 run scripts/load/k6-peak.js -e BASE=https://api.yourdomain.com`
