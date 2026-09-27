# Castable — get cast, with receipts

**Creators: type your @handle, get your Brand-Readiness Report. Brands: paste a brief, get a vetted shortlist. Every number links to a video.**

Start with `AGENT-BRIEF.md` — it is the binding spec for the Replit build.

Built in one day at the *Oriane × Replit — Build for the Video Economy* hackathon (Dubai, 27 Sep 2026),
with an AI engineering team: Jarvis (the operator's local agent, Telegram + Mac), Claude, and Oriane's
video-intelligence layer.

## The problem an agency actually pays for

Casting creators for a GCC campaign today means an intern scrolling for two days, screenshotting bios,
guessing engagement, and *never* watching the last 30 videos of each candidate. Then the brand asks
"has she ever promoted our competitor?", "does he say anything we can't be next to?", "is the audience
really in Riyadh?" — and nobody knows. Vetting fails after the contract is signed.

## What Scout does (6 hops, all auditable)

| # | Hop | What happens | Oriane surface used |
|---|-----|--------------|---------------------|
| 1 | **Brief** | English/Arabic brief → search intent (keywords, Arabic variants, hashtags, competitors, brand-safety topics, visual prompt). LLM-enriched, deterministic fallback. | — |
| 2 | **Discovery** | Semantic search over what creators *say on camera* (transcript) and write (caption), fused with a **visual-similarity** search from a text/image asset ("the ideal on-screen look"). Filtered by platform, recency, follower band and a **geo box** of where the creator is based. | `POST /rest/contents/search` (transcript · caption · visualSimilarity · geo · follower ranges · sort), `POST /rest/assets` |
| 3 | **Profiles** | Enrich every candidate: followers, verified, bio, public email, location. | `POST /rest/profiles/search` (projection=full) |
| 4 | **Vetting** | Pull each finalist's recent videos in **full projection**: timed transcript chunks, keyframes, audio rights, popular comments. Flag competitor mentions, brand-safety terms (verbatim quote + timestamp + link), sponsored cadence, language mix, posting cadence, authenticity signals. | `POST /rest/contents/search` (projection=full, sort=publishedAt) |
| 5 | **Score** | Transparent 0–100: relevance 35 · performance 25 · audience 15 · safety 25. Flags cap the grade; a competitor mention never yields an A. Every component is shown. | — |
| 6 | **Dossier** | Client-ready HTML/PDF dossier + CSV: quotes, keyframes, hooks, flags, sponsors, contact. Plus a Telegram card through Jarvis. | — |

Credits are treated as money: every call is cached on disk, `limit` is explicit, a per-run budget guard refuses
runaway fetches, and a ledger records what was spent (`data/credits.jsonl`).

## Jarvis: hands-free casting from the phone (optional)

`/scout Luxury skincare launch in Dubai, women 22-35, Arabic and English, avoid discount-code creators`
→ Jarvis (Telegram) starts Scout on the Mac if needed, streams the run log into one message, and replies
with the top-3 card + the dossier link. `jarvis/scout_door.py` is the door; it is pure HTTP to localhost.

## Run it

```bash
# Mac (double-click) — reads ORIANE_API_KEY from ~/jarvis-vault/.env.oriane
./ARRANCAR-SCOUT.command

# anywhere
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
ORIANE_API_KEY=... uvicorn app.main:app --port 8787

# rehearsal without credits: the bundled mock Oriane server
uvicorn scout.mock_server:app --port 8791 &
ORIANE_BASE_URL=http://127.0.0.1:8791 ORIANE_API_KEY=demo uvicorn app.main:app --port 8787
```

Environment (all optional except the key): `ORIANE_API_KEY`, `ORIANE_AUTH_STYLE` (auto|bearer|x-api-key|api-key),
`ANTHROPIC_API_KEY` (LLM judgment; falls back to `claude -p`, then Ollama, then deterministic),
`SCOUT_MAX_RESULTS_PER_RUN` (default 400), `SCOUT_PUBLIC_URL` (link base for phone cards).

## Replit

`.replit` runs the same app on port 8080 (Autoscale deployment). Add `ORIANE_API_KEY` (and optionally
`ANTHROPIC_API_KEY`) as Secrets.

## Layout

```
app/        FastAPI routes, UI (index) and the dossier template
scout/      brief · discover · vetting · scoring · pipeline · oriane client · llm · geo · mock_server
jarvis/     scout_door.py — the Telegram command for Jarvis
scripts/    oriane_openapi.json — the spec this client was written against
tests/      fail-first tests
```

## What is real and what is not

- Real: the Oriane Connect surface (spec in `scripts/`), the pipeline, the budget/cache/ledger, the dossier.
- Mock: `scout/mock_server.py` fabricates Oriane-shaped responses so the demo never depends on credits.
  Runs made against it are labelled **MOCK** in the UI and dossier.
- The score is a heuristic with explicit weights, not a trained model. The evidence is what matters.

Built by Abdulrahman with Claude and Jarvis.
