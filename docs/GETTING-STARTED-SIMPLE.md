# WIRE — the simple guide

*Written for a non-technical owner. No jargon, no assumed knowledge. Follow
top to bottom. Anything not in this guide, you don't need to touch.*

WIRE is your app that reads the news, shows you 50 short briefings a day to
swipe through, lets you add your opinion to the ones you keep, and turns
those opinions into social-media posts written in your voice.

Everything below happens in three stages:

- **Stage 1 — Run it on your computer** (today, ~30 minutes, free)
- **Stage 2 — Connect the AI** (get 2 keys, ~15 minutes, a few dollars/month)
- **Stage 3 — Put it on the internet** (~1 hour, ~₹800–2000/month)

---

## Stage 1 — Run it on your computer

### Step 1.1 — Install Docker Desktop (one time)

Docker is a free program that runs WIRE's database for you.

1. Go to **docker.com/products/docker-desktop** and click **Download for
   Windows**.
2. Run the downloaded file. Accept everything it suggests (it will mention
   "WSL 2" — say yes). If it asks to restart the computer, restart.
3. After restart, open **Docker Desktop** from the Start menu. Wait until
   the little whale icon at the bottom-left of its window stops moving.
   That's it — you can minimise it. (Docker Desktop must be open whenever
   you use WIRE.)

### Step 1.2 — Double-click `SETUP-WIRE.bat` (one time)

In the WIRE folder (`D:\Satish\AI\Self_AI\Projects\EngagementEnhancer`),
double-click **SETUP-WIRE.bat**. If Windows shows a blue "protected your
PC" box, click *More info → Run anyway* (it's your own file).

A black window will:
1. check Docker,
2. start the database,
3. open **Notepad** with a settings file — for now just close Notepad
   (you'll fill keys in Stage 2),
4. build the database tables,
5. add demo users and demo news.

When it says **Setup complete**, close it.

### Step 1.3 — Double-click `START-WIRE.bat` (every time you want WIRE)

Three small black windows open (the app's engine — keep them open, minimise
them), and after ~15 seconds your browser opens **http://localhost:3000**.

Sign in with the demo account:

> **Email:** `pro@wire.dev`  **Password:** `wire-dev-password`

Now play with it: swipe the deck (drag cards right to keep, left to toss —
or use the arrow keys), open the **Darkroom** to write takes, and look at
the **Wire Room** and the **Lattice** from the top-right menu.

When you're done for the day, double-click **STOP-WIRE.bat**.

> **Something broke?** Close everything, open Docker Desktop, wait for the
> whale, then run START-WIRE.bat again. That fixes 90% of problems.

---

## Stage 2 — Connect the AI (real news, real writing)

The demo news is fake. To get real briefings and real AI-written posts, WIRE
needs two keys (a key is just a long password that lets WIRE use an AI
service; you pay that service only for what you use — a few dollars a month
at personal scale).

### Step 2.1 — Get the two required keys

**Anthropic key** (writes the briefings and posts):
1. Go to **console.anthropic.com** → sign up with your email.
2. Add a payment card under *Billing* and buy $5 of credit.
3. Click *API Keys* → *Create Key* → name it `wire` → **copy** the long
   text starting `sk-ant-...` somewhere safe (Notepad).

**OpenAI key** (helps WIRE group similar news together — costs pennies):
1. Go to **platform.openai.com** → sign up.
2. Add $5 under *Billing*.
3. *API keys* → *Create new secret key* → copy the `sk-...` text.

*(Optional extras, skip for now: fal.ai key = AI images; newsdata.io free
key = extra news sources; deepgram.com key = speak your takes aloud.)*

### Step 2.2 — Put the keys into WIRE

1. Open the folder `services\api` inside the WIRE folder.
2. Right-click the file called **.env** → *Open with* → *Notepad*.
3. Find the line `ANTHROPIC_API_KEY=` and paste your key right after the
   `=` sign (no spaces). Do the same for `OPENAI_API_KEY=`.
4. Save (Ctrl+S) and close Notepad.
5. If WIRE is running, stop it (STOP-WIRE.bat) and start it again.

### Step 2.3 — Pull real news

Double-click **GET-REAL-NEWS.bat**. It fetches from your sources, groups
the stories, and writes fresh briefings. Refresh the website — the deck is
now real. (After this, it happens automatically every few minutes while
WIRE is running.)

To choose *which* news you get: open **Studio** in the app and add any
website or RSS feed under "protocol — your sources".

---

## Stage 3 — Put it on the internet

This makes WIRE a real website anyone can visit. Two things cost money:
a **domain name** (your web address, ~₹800/year) and a **server** (a small
computer that runs 24/7 in a data centre, ~₹800–2000/month).

### Step 3.1 — Put the code on GitHub (free, one time)

GitHub is a safe online copy of your code that the server will download from.

1. Go to **github.com** → sign up → click **+** (top right) → *New
   repository* → name it `wire` → keep it **Private** → *Create*.
2. Tell Claude (me) "push the project to my GitHub" and paste the page URL
   it shows you — I'll walk you through the two commands, or do it with you
   in the next session. (This is the one step that needs your GitHub login,
   which I can't and shouldn't have.)

### Step 3.2 — Buy a domain and a server

1. **Domain**: at **namecheap.com** (or GoDaddy), search a name you like —
   e.g. `mywire.app` — and buy it.
2. **Server**: at **hetzner.com** (cheapest good option) or
   **digitalocean.com**, create an account, then create a server
   ("CX32" on Hetzner / the $24 "4GB" droplet on DigitalOcean), choosing
   **Ubuntu 24.04** as its system. It will show you an **IP address**
   (four numbers like `65.108.xx.xx`) and give you login access.
3. **Connect them**: in your domain company's control panel, find *DNS*
   and add two "A records": one named `app` and one named `api`, both
   pointing at that IP address. (Every registrar has a help page titled
   "how to add an A record" — it's two small forms.)

### Step 3.3 — Launch

The exact commands are in **docs/DEPLOYMENT.md** (section "Path A"). It is
genuinely five commands pasted one by one into the server's console:
install Docker, download your code from GitHub, copy the settings file,
fill in the same two keys from Stage 2, and run one long
`docker compose ... up -d --build` command. Fifteen minutes later
`https://app.yourdomain.com` is live with a padlock, automatically.

If you'd rather not touch a server console at all, ask me in a session to
walk it with you step by step — or use the "Path B" managed option in
DEPLOYMENT.md (Railway + Vercel websites, all point-and-click).

### Step 3.4 — Later, when you want to charge money / auto-post

- **Stripe** (stripe.com) — lets users pay you. Needed only for the Pro tier.
- **Ayrshare** (ayrshare.com) — posts to X/LinkedIn/Instagram for your
  users. Without it, WIRE still gives everyone a perfect "copy to
  clipboard" flow, which is the honest free tier anyway.
- Both are "create account → copy one key → paste into the settings file"
  — same pattern as Stage 2, instructions in DEPLOYMENT.md.

---

## Checking that things work (simple tests)

| What to check | How | What you should see |
|---|---|---|
| Engine is alive | visit `localhost:8000/health` | a line containing `"status":"ok"` |
| Deck works | swipe 5 cards right | Darkroom shows 5 keeps |
| AI works (after Stage 2) | write a take in the Darkroom | "Develop the prints" produces text variants on the contact sheet in ~30s |
| Transparency | open **Wire Room** while GET-REAL-NEWS runs | counters tick, events appear with real costs |
| Learning | keep only AI stories for a day | tomorrow's deck leans AI; Dashboard voice-match appears after a week |

## If something goes wrong

1. Docker Desktop open? (whale icon steady)
2. Did you STOP and START WIRE after changing the .env file?
3. Read the black windows — the last red line usually says what's missing
   (most often: a key is empty or pasted with a space).
4. Still stuck: copy that red line and paste it to me in a Claude session —
   with it I can almost always tell you the one-line fix.
