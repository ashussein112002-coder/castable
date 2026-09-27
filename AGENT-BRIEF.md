# AGENT BRIEF — Castable (Oriane × Replit hackathon, Dubai, 27 Sep 2026)

You are the senior full-stack engineer finishing **Castable** on Replit today. Read this file first,
then `README.md`, `docs/sample-creator-run.json`, `app/main.py`, and the docstrings of `scout/creator.py`,
`scout/oriane.py`, `scout/pipeline.py`. Everything below is binding.

## 1. What Castable is

**Castable — Get cast. With receipts.** A standalone product for content creators (and, secondarily,
for brands/agencies) built on Oriane's video-intelligence API (Instagram + TikTok: transcripts, keyframes,
comments, audio rights, visual similarity, profiles).

- **Creator mode (primary):** a creator types their `@handle` → *Brand-Readiness Report*: what they
  actually say on camera (topics from transcripts), brand-safety self-audit (verbatim quotes with
  timestamps), hooks that worked, sponsor history, cadence and languages, benchmark vs peers the index
  puts next to them (transcript intent + visual similarity from their own best thumbnail), **brands buying
  from creators like them** with receipts (peer handle, sponsored caption, link), a readiness score
  0–100 with four transparent components (consistency 20 / engagement 30 / safety 30 / market fit 20)
  and named caps, and a pitch plan (niche, positioning, fix-before-pitching, up to 3 pitches with
  subject line + opener, a media-kit line, a rate hint).
- **Brand mode (secondary):** a brand brief → vetted creator shortlist with video evidence and a
  client dossier (already built: `POST /api/scout`, `/dossier/{id}`, `/dossier/{id}.csv`).

Judging criteria (verbatim from the organizers): 01 Problem and value (real pain for creators, brands or
agencies; would someone pay?) · 02 Video intelligence (how deeply it uses Oriane; is video understanding
core or decoration?) · 03 Execution (does it actually work; how complete and stable on Replit?) ·
04 Design (intuitive, clean, easy for a non-technical creator) · 05 Demo. Entry rules: built with Oriane
AND Replit; built today; a new standalone product. **Never write "VYRAL" or "Scout" in anything user-facing.**

## 2. What already works (do not rewrite)

The engine is verified and tested (`pytest -q tests` → green):

| Module | Role |
|---|---|
| `scout/oriane.py` | Oriane Connect client: auth-style auto-detect (bearer → x-api-key → api-key → raw), on-disk cache, per-run result budget, credit ledger, 402/416/206 handling |
| `scout/discover.py` | brief → contents/search (transcript + caption + hashtags intent, geo box, follower band) + visual similarity via `/rest/assets` → candidates per creator |
| `scout/vetting.py` | recent videos in full projection → flags (quote + timestamp), hooks, sponsors, languages, cadence, authenticity |
| `scout/creator.py` | `@handle` → the whole Brand-Readiness Report (see §1) |
| `scout/scoring.py`, `scout/brief.py`, `scout/geo.py`, `scout/llm.py` | score, brief parsing/enrichment, region boxes, LLM with graceful degradation (anthropic → `claude` CLI → ollama → deterministic) |
| `scout/pipeline.py` | run records under `data/runs/`, background threads, `POST /api/scout` and `POST /api/creator` flows |
| `scout/mock_server.py` | an Oriane-shaped mock (`uvicorn scout.mock_server:app --port 8791`) for rehearsal without credits |
| `scripts/live_smoke.py` | 30-second live check of the real API (spends ~5 results) |
| `scripts/oriane_openapi.json` | the OpenAPI document this client was written against |

API (FastAPI, `app/main.py`): `GET /api/health`, `GET /api/regions`, `POST /api/scout`, `POST /api/creator
{handle, platforms[], region, niche?, use_llm}`, `GET /api/runs`, `GET /api/runs/{id}` (poll: status
queued|running|done|error, log[], summary, kind, report{...} for creator runs, shortlist[] for brand runs,
stats, error?), `GET /dossier/{id}`, `GET /dossier/{id}.csv`.

**Frozen (edit only to fix a proven bug, and say so):** `scout/oriane.py`, `scout/discover.py`,
`scout/vetting.py`, `scout/creator.py`, `scout/scoring.py`, `scout/brief.py`, `scout/geo.py`.
**Yours:** `app/` (routes, templates, static), `scout/dossier.py` (add `render_creator`), `scout/pipeline.py`
(only if persistence needs it), tests, deployment config.

## 3. Configuration and secrets

- Python 3.11+. `pip install -r requirements.txt`. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8080`.
- Secrets (Replit Secrets, never in code, never sent to the browser): `ORIANE_API_KEY` (required for live
  data), optional `ORIANE_AUTH_STYLE` (`auto` default), optional `ANTHROPIC_API_KEY` (AI plan; without it the
  LLM falls back and the report still completes deterministically), `SCOUT_PUBLIC_URL` (the deployment URL,
  used for links in exports).
- Credit discipline (Oriane charges per returned result; Free plan ≈ 250 credits/month ≈ 600–1,200 results):
  `SCOUT_DISCOVERY_LIMIT=40`, `SCOUT_VET_TOP_K=5`, `SCOUT_VET_VIDEOS_PER_CREATOR=8`,
  `SCOUT_MAX_RESULTS_PER_RUN=160`. Every call is cached on disk; never add uncached calls.
- No key present → run the mock server and set `ORIANE_BASE_URL=http://127.0.0.1:8791 ORIANE_API_KEY=demo
  ORIANE_AUTH_STYLE=bearer`; the UI must show MOCK, never LIVE, on mock data (`run.mode`).

## 4. What to build now (in this order, each with proof)

1. **Green baseline.** Install, `pytest -q tests` (6 green), start the app, `GET /api/health` 200.
2. **Live check.** If `ORIANE_API_KEY` exists: `python scripts/live_smoke.py`; report auth style and any
   MISSING fields verbatim. If it fails with 401 on every header style, read the header name from
   app.oriane.xyz → Billing → Subscription → API and set `ORIANE_AUTH_STYLE`. Otherwise mock mode.
3. **Creator report page** `GET /report/{id}` (template `app/templates/creator.html`, rendered by
   `render_creator(run, public_url)` in `scout/dossier.py`; 404 when missing or not a creator run).
   Sections: hero (avatar/initials, @handle, platform, followers, verified, readiness score + grade +
   four-segment bar + weights + caps, media-kit line as a pull quote) · What you actually make (topics as
   chips sized by video count, language mix, cadence, last post) · Fix before you pitch (plan fixes + each
   flag: severity badge, verbatim quote, mm:ss, link; a green state when clean) · Hooks that worked ·
   Brands buying from creators like you (brand, creators, sponsored posts, receipts with handle,
   followers, caption, date, link) · Your pitches (cards with brand, why it fits, angle, subject line,
   opener, a Copy button) · How you compare (ER percentile, peer median, views/follower percentile, peers,
   `peers_widened` note, top peers) · Evidence (videos: thumbnail with fallback, caption `dir="auto"`,
   views/ER, transcript excerpt, keyframes with mm:ss, audio © mark) · Audience voice (top comments) ·
   Method footer (videos checked, peers, sponsored posts scanned, Oriane calls from `run.stats.oriane`,
   LLM backend, seconds; "Every number links to a video · evidence from Oriane Connect"; MOCK/LIVE badge).
   Print stylesheet. Every field may be missing on live data — degrade, never crash.
4. **Two-mode home** (`/`): segmented control **For creators** (default) / **For brands**. Creator panel:
   one big `@handle` input, Instagram/TikTok toggles, region select (`/api/regions`), optional "your niche
   in five words", AI plan checkbox, button **Am I castable?**. While running, translate log lines into
   friendly steps ("Reading your last 12 videos…", "Finding creators the algorithm puts next to you…",
   "Scanning who sponsors them…", "Writing your pitches…"). When done: result card (score/grade, summary,
   three facts: brands buying, things to fix, ER percentile) + **Open my report** + Raw JSON. Brand panel
   = the existing form and cards (button: **Find castable creators**). Recent-runs dropdown routes by
   `kind`. Health strip (mode, LLM, credits used) stays.
5. **Quality bar.** Report page first paint < 1 s on the deployment; no external JS/CSS; images lazy with
   fallbacks; Arabic renders correctly; mobile layout at 390 px; keyboard-usable; copy buttons work.
   Security: input validation (`handle` regex `^@?[A-Za-z0-9._]{2,64}$`, platforms enum, region key),
   a simple per-IP rate limit on `/api/creator` and `/api/scout` (e.g. 6/min), Jinja autoescape on, no
   secrets in any response, security headers (`X-Content-Type-Options`, `Referrer-Policy`,
   `X-Frame-Options`). Performance: polling every 3 s with backoff; no blocking calls in request handlers.
6. **Deploy.** Reserved VM (always on, single instance) or Autoscale with min 1 instance; port 8080;
   secrets set; `SCOUT_PUBLIC_URL` = the public URL. Prove: `GET <public>/api/health` 200, one creator
   report generated on the deployment, its `/report/{id}` URL in the final message, screenshots of `/` and
   `/report/{id}`.

## 5. Working rules

- Measure before claiming: every "done" carries the command and its output. A test is shown red before
  green or it does not count. Report failures with raw output; never round up.
- English everywhere on disk (code, comments, UI copy, commits). Plain language for creators in the UI.
- No new heavy dependencies; no framework rewrites; keep FastAPI + Jinja + vanilla JS.
- Do not spend Oriane credits in loops: one live smoke, then one live report per rehearsal; rely on cache.
- If something in the engine is wrong, fix the smallest thing and say exactly what changed and why.
- Status block after each step: **Works now (proof) · Failed (exact) · Next (one action) · Need from operator**.
