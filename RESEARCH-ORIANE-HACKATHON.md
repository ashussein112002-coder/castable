# Oriane x Replit "Build for the Video Economy" — Dubai Hackathon, 27 Sep 2026
## Reconnaissance report (primary sources only; INFERRED / UNKNOWN marked)

Compiled 2026-09-27 ~08:00 GST. Method: WebSearch + WebFetch on official pages; the Oriane
docs are a JS-only Scalar app (WebFetch/curl see an empty shell), so the OpenAPI spec, the
pricing table and the auth/MCP probes were done in the user's desktop-app browser pane
(read-only, no credentials entered). A copy of the extracted spec is at
`scripts/oriane_openapi.json` (OpenAPI 3.0.0, title `>_ Oriane - Integration connect`,
version 0.0.1, 3 paths, 39 schemas, no securitySchemes — re-validated against this file).

---

## 1. Oriane — what it is (3–6 lines, cited)

- Oriane (oriane.xyz; LinkedIn `orianexyz`; CEO Julien Rosilio, CPO Yuri Mihaileanu, CTO
  Thibaut Hadjean) is an AI video-intelligence / video search engine over social video. It
  "watches millions of videos posted on social media everyday" and indexes what is on screen,
  what is said (full transcript), captions, hashtags, audio, comments and engagement, for
  creator discovery, brand safety, trend detection, IP/remix tracking and campaign ROI.
  [oriane.xyz, oriane.xyz/enterprise]
- Positioning: "The perception layer for Marketers and their AIs" (Product Hunt). Funding:
  $1.5M (Sep 2025) + $2M (Mar 2026; Antler US, Clint Capital, Hartmann Capital). Named
  customers: Dior, Hennessy, Estée Lauder. Claims "48-hour video freshness" and "1,000x
  reduction in video ingestion cost". [press release via webanditnews; gen.xyz blog]
- Marketing lists TikTok / Instagram / YouTube. **The public API enum is only
  `instagram` | `tiktok`** (VERIFIED in spec). Press release: "Instagram and TikTok live at
  launch; additional platforms planned for 2026".
- Developer surface = REST API + MCP server at `connect.oriane.xyz` (API status "LIVE" on
  /enterprise). No SDKs. Free tools on the site (Video Analyzer, Creator Checker, Influencer
  Finder, Account Benchmark, Shadow Reach Analyzer, …) are product demos, not API.

---

## 2. Oriane API — verified surface

**Base URL:** `https://connect.oriane.xyz` (spec `servers[0].url`).
**Docs:** https://connect.oriane.xyz/rest/docs (Scalar; "Download OpenAPI Document" button;
no standalone spec URL — `/rest/openapi.json`, `/rest/docs-json`, `/openapi.json` all 404).
**Get an API key:** https://app.oriane.xyz/billing/subscription?tab=api (login required; the
app login is email-first at app.oriane.xyz/hello).

### Auth — header name UNKNOWN (the #1 open item)
- The spec has **no `securitySchemes`** and no per-path `security`; the docs' curl sample
  sends only `Content-Type`.
- Unauthenticated `POST /rest/contents/search` →
  `401 {"error":{"id":"err_…","operation":"AUTHENTICATION","code":"UNAUTHORIZED","message":"Authorization failed.","context":{}},"metadata":{…}}`
- Bogus `Authorization: Bearer x`, `x-api-key: x`, `api-key: x` all return the *identical*
  generic 401 → the header name cannot be inferred from the outside. **Read it from the app's
  API tab the moment a key exists**, then set `ORIANE_AUTH_STYLE` accordingly (the scaffold's
  auto-detect probes bearer → x-api-key → api-key → raw Authorization).
- No OAuth: `/.well-known/oauth-protected-resource` → 404.

### Endpoints (all three; verbatim from the spec)

| Method + path | operationId | Purpose (verbatim) | Query params |
|---|---|---|---|
| `POST /rest/contents/search` | `searchContents` | "Search, filter and retrieve indexed social contents across platforms." | `sort` (default `publishedAt`; fields: visualSimilarity, transcriptRelevance, viewsCount, likesCount, sharesCount, commentsCount, interactionsCount, engagementRatePerViews, engagementRatePerFollowers, profileFollowersCount, publishedAt; `:asc`/`:desc`, comma-separated, e.g. `publishedAt:desc,viewsCount`) · `offset` (≥0) · `limit` (1–100, default 20) · `projection` = `basic`\|`default`\|`full` · `aiSearchAnchor` (echo back on later pages of a visual-similarity search) |
| `POST /rest/profiles/search` | `searchProfiles` | "Search, filter and retrieve indexed social profiles across platforms." | `sort` (followersCount, createdAt, updatedAt) · `offset` · `limit` (≤100) · `projection` |
| `POST /rest/assets` | `createAsset` | "Create a reusable text or image asset for visual search." → `201 {"data":{"id":"ast_<32 chars>"},"metadata":{…}}` | — |

### Request body (both searches)
```json
{ "name": "query1", "operator": "and", "filters": { ... }, "queries": [ { "operator": "or", "filters": { ... } } ] }
```
- `operator` required (`and`|`or`). "Maximum nesting depth is two levels." "The total number
  of filter values cannot exceed 500 across all query levels." Results carry `matchedQueries`
  (names of the named sub-queries that matched).
- Operand grammar (VERIFIED):
  - text fields: `{"exactMatch"|"includesExactly"|"includesFuzzy"|"excludesExactly"|"excludesFuzzy": {"values":[...],"operator":"or"}, "operator":"and"}`
  - enum / id fields: `{"includes":[...],"excludes":[...],"operator":"and"}`
  - ranges: `{"min":n,"max":n}` · dates: `{"after":"2026-08-26","before":"2026-09-25"}` · booleans plain.
- **Contents filters (38):** id, platform, platformId, format (`image`|`video`|`carousel`),
  profileId, profilePlatformId, profileHandle, caption, captionLanguage, profileBio,
  viewsCount, interactionsCount, engagementRatePerViews, engagementRatePerFollowers,
  profileFollowersCount, publishedAt, audioPlatformId, audioTitle, audioAuthor,
  audioCopyrighted, transcript, transcriptLanguage, coAuthorIds / coAuthorPlatformIds /
  coAuthorHandles, hasCoAuthors, mentionIds / mentionPlatformIds / mentionHandles,
  hasMentions, hashtags, locationPlatformId, locationCompleteAddress, locationCoordinates
  (lat/lng bounding boxes), profileLocationPlatformId, profileLocationCompleteAddress,
  profileLocationCoordinates, visualSimilarity
  (`{"includes":{"values":[{"assetId":"ast_…","minScore":0.3,"maxScore":0.9}],"operator":"or"}}`,
  ≤10 values per request).
- **Profiles filters:** id, platform, platformId, handle, displayName, bio, language,
  isPrivate, isVerified, postsCount, likesCount, followersCount, followingCount,
  locationPlatformId, locationCompleteAddress, locationCoordinates, createdAt, updatedAt.
- **Assets body:** `{"type":"text","text":"a man looking at his reflection in water"}` (≤300 chars)
  | `{"type":"image","image":{"type":"url","url":"https://…"}}` (public HTTPS jpeg/png/webp ≤20 MiB)
  | `{"type":"image","image":{"type":"base64","mediaType":"image/webp","base64":"…","filename":"x.webp"}}`
  | multipart `type=image` + `file`.

### Minimal request (from the docs' curl, trimmed)
```bash
curl 'https://connect.oriane.xyz/rest/contents/search?sort=viewsCount:desc&offset=0&limit=20&projection=default' \
  --request POST \
  --header 'Content-Type: application/json' \
  --header '<AUTH HEADER — read from app.oriane.xyz → Billing → Subscription → API>' \
  --data '{"operator":"and","filters":{
    "platform":{"includes":["tiktok","instagram"]},
    "transcript":{"includesFuzzy":{"values":["skincare routine"]}},
    "publishedAt":{"after":"2026-08-27"},
    "profileFollowersCount":{"min":10000,"max":500000}}}'
```

### Response envelope
```json
{ "data": { "aggregations": { "totalViewsCount": 12000, "totalInteractionsCount": 1332 },
            "results": [ ... ] },
  "metadata": { "requestId": "req_…", "executionTime": 17, "timestamp": 1790298683388,
                "pagination": { "offset": 0, "limit": 20, "totalCount": 2000, "aiSearchAnchor": "…" } } }
```
(`full` aggregations add `totalEngagementRatePerViews`, `totalEngagementRatePerFollowers`;
profiles/search returns `data` as an array.)

**Content result fields — `default`:** id (`cnt_…`), matchedQueries, platform, profileHandle,
profileDisplayName, format, caption, captionLanguage, thumbnailMediaId, thumbnailMediaUrl
(S3 URL), publishedAt, profileId, viewsCount, likesCount, sharesCount, commentsCount,
interactionsCount, engagementRatePerViews, engagementRatePerFollowers,
profileFollowersCount / profileFollowingCount / profilePostsCount, mediaCount, duration,
hashtags[], coAuthors[{id,platformId,profileHandle}], mentions[…].
**`full` adds:** platformId, profilePlatformId, profilePictureUrl, profileBio,
profileVerified, location* / profileLocation* (address + lat/lng), **transcript**,
transcriptLanguage, **transcriptChunks[{startSeconds,endSeconds,text}]**,
**frames[{id,position,timestampSeconds,visualSimilarityScore,url}]** (keyframe S3 URLs),
audioPlatformId / audioTitle / audioAuthor / audioType / audioCopyrighted,
**popularComments[{platformId,profilePlatformId,profileHandle,content,likesCount,repliesCount,publishedAt,…}]**,
createdAt, updatedAt. `basic` = id, matchedQueries, platform, profileHandle,
profileDisplayName, format, caption, captionLanguage, thumbnailMediaId, publishedAt.
**Profile result — `default`:** id (`prf_…`), platform, handle, displayName, bio, bioLink,
language, isPrivate, isVerified, postsCount, likesCount, followersCount, followingCount;
`full` adds platformId, profilePictureUrl, publicEmail, location*, createdAt, updatedAt.

**Status codes:** 200 · 206 (partial content) · 400 validation · **402** (Payment Required →
INFERRED: credits exhausted) · 404 · **416** (offset beyond totalCount; the MCP instructions
say "Always stop before offset exceeds totalCount") · 500. Error shape
`{"error":{"id","operation","code","message","context"},"metadata":{…}}`.
**Rate limits / latency:** UNKNOWN — nothing documented, no rate-limit headers observed on
the 401s. `metadata.executionTime` is ms server-side (example 17 ms).

### Credits (VERIFIED from the rendered pricing table, app.oriane.xyz/embed/pricing-table)
| Plan | Price | Credits / month | "video results / month" | Extra credits |
|---|---|---|---|---|
| Free | $0, no card | **250** | **600–1.2K** | upgrade to buy |
| Plus | $49 ($25 annual) | 700 | 1.7K–3.5K | $41 / 1,000 |
| Pro | $499 ($249 annual) | 8,000 | 20K–40K | $36 / 1,000 ($0.0311/credit) |
| Enterprise | $237→$75 /seat | 8,333–25,000 /seat | 20.8K–125K /seat | $33→$4 / 1,000 |

Free tier: "Try Oriane's full search stack", "All 15 search filters", "CSV exports".
INFERRED: **a credit buys ~2.4–4.8 returned video results** (i.e. ~0.2–0.4 credit per
result; the range presumably depends on projection). $2,000 of credits ≈ 55–64K credits ≈
150K+ results. **Whether a Free account can mint an API key: UNKNOWN** (the key page sits
under Billing → Subscription). "Create your Oriane account with the same Luma email" is not
on the Luma page (organizer message; consistent with credits granted per matching email).

### MCP server (VERIFIED live)
- `POST https://connect.oriane.xyz/mcp` — MCP Streamable HTTP (GET → 405; no session id).
- `initialize` succeeds unauthenticated: `serverInfo.name = "oriane_integration_connect"`,
  version 0.0.1, capabilities: tools only. Instructions tell the client to never return raw
  JSON, to paginate via totalCount/offset/limit and to raise `limit` to cut iterations.
- Tools are exactly **`search_contents`, `search_profiles`, `create_asset`**
  (unauthenticated `tools/list` → `[]`; `tools/call` on those → "Access denied: insufficient
  permissions"; any other name → "Unknown tool"). Auth header for MCP also UNKNOWN.
- No SDKs, no playground beyond Scalar's "Try it" and the app UI.

---

## 3. Capabilities matrix

| Capability | Status |
|---|---|
| Ingest an arbitrary TikTok / IG URL via API | **VERIFIED NO** — no ingest endpoint. You can only look up already-indexed items by `platformId` (external content id) or by `profileHandle` + dates. The free Video Analyzer accepts a pasted URL but requires a "20,000+ view threshold" (index skews to popular content — INFERRED). |
| Platforms | VERIFIED `instagram`, `tiktok` only. YouTube: marketing only. |
| Transcript (timed) | VERIFIED — `transcript` + `transcriptChunks` in `full`; filterable exact/fuzzy; sort `transcriptRelevance`. |
| Visual / scene understanding | VERIFIED as keyframes (`frames[]`) + visual similarity to a text or image asset (`visualSimilarityScore`). No explicit object/logo tag list in the API (the app's "AI Vision" filter maps to text-asset similarity — INFERRED). |
| Semantic search | VERIFIED via `create_asset` (text/image → embedding) + `visualSimilarity` filter + `aiSearchAnchor` paging. Text filters themselves are exact/fuzzy keyword, not semantic. |
| Embeddings exposed | VERIFIED NO (only similarity scores). |
| Creator-level analytics | PARTIAL — profile stats (followers, posts, verified, bio, location, publicEmail) + aggregations over any filtered content set (totalViews / interactions / ER). No time series, no audience demographics. |
| Product / brand detection | UNKNOWN in the API (marketing claims logos/products; API offers only caption/transcript/hashtag text + visual similarity). |
| Hooks / retention analysis | VERIFIED NO — must be built on top of transcriptChunks + frames + popularComments. |
| Audio / music | VERIFIED — audioTitle / audioAuthor / audioType / audioCopyrighted / audioPlatformId; no music-discovery tool despite the MCP blurb. |
| Comments | VERIFIED — `popularComments[]` in `full`. |
| Geo | VERIFIED — bounding-box filters on content and profile location (UAE/GCC framing works). |
| Bulk export | App CSV "up to 10,000 rows per search"; API 100 per page. |

---

## 4. Hackathon rules & judging (Luma https://luma.com/kbk3wqgu — VERIFIED verbatim)

- Title "Oriane x Replit: Build for the Video Economy — Dubai Hackathon"; status "Sold Out";
  Dubai (address behind registration). Hosts: Hamzeh Abu Qamar, Julien Rosilio, Abdul
  Aldhalaan, Oriane.xyz Video Intelligence, Thibaut Hadjean.
- Agenda: 11:00 Introduction · 12:00 Hack · 4:00 Submission · 4:30 Demos · 5:30 Winners.
  "Doors at 10:30 AM". "Bring your laptop, ID, and curiosity". "Food & AI credits on the house".
- Prizes: 🥇 $500 cash + Replit Pro + $2,000 Oriane credits · 🥈 $300 + Replit Pro + $1,500
  Oriane credits · 🥉 $200 + Replit Pro + $1,000 Oriane credits.
- Jury (the only criteria-like text on the page):
  - Amal Jeljeli, GCC Business Director at YKONE — "sees every day what brands actually pay
    for in the creator economy. If your tool solves a real problem, she will know."
  - Abdulrahman Aldhalaan, Growth Lead at Replit — "has watched hundreds of hackathon
    projects get built on Replit, and a handful become real products. He knows what
    separates the two."
  - Thibaut Hadjean, founding member and CTO at Oriane — "will look at how far you pushed
    the video intelligence layer."
  → INFERRED rubric: real brand/agency problem × shippable product × depth of Oriane usage.
- **Not on the page:** team-size rule, submission format/link, whether Oriane API or Replit
  are mandatory, Discord/Slack/WhatsApp, starter kit or template repo. No Oriane or Replit
  blog/social starter material found (X/LinkedIn not fetchable; web search found none).
  Only third-party repo: github.com/jasonmunguia/oriane-system (prompt pack over CSV
  exports; no API code).

---

## 5. Replit — fastest deploy path (≤8 lines)

- Workspace → **Publish** icon → Publishing tab → choose type → "Add a payment method if
  prompted". Types: Autoscale (web apps/APIs, scales to zero), Static (front-end only),
  Reserved VM, Scheduled. [docs.replit.com/cloud-services/deployments/about-deployments]
- Plans: Starter (free) — "Published apps: 1 (30-day)"; Core $20/mo → "$20 towards most
  powerful models", unlimited published apps; Pro $100/mo → $100 credits, 10 parallel
  agents. Credits "cover Agent and other Replit cloud services like published apps, storage,
  and databases"; Agent billed "effort-based pricing" per checkpoint. [replit.com/pricing,
  docs.replit.com/billing/ai-billing]
- "AI credits on the house": Luma does not say whose — INFERRED Replit Agent credits and/or
  Oriane credits. No Replit × Oriane template exists (none found).
- Keep the Oriane key server-side (Replit Secrets) and proxy `/rest/*` through the backend;
  CORS behaviour of connect.oriane.xyz is UNKNOWN.

---

## 6. What agencies pay for (≤6 lines, cited)

- YKONE sells "Data curation, Influencer casting, Forecast, Competitive benchmark, Campaign
  Reporting" plus brand safety, and runs its own analytics platform "Campaygn" (find/qualify
  creators, ROI, competitor benchmarks); Dubai + Abu Dhabi offices; luxury/beauty/fashion
  clients. [ykone.com]
- Vetting is the documented gap: "96.6% of brands want documentation on influencer vetting,
  but only 25.6% consistently receive it"; "Over 50% of marketers spend 30 minutes or less
  vetting a single influencer"; 53% of US media experts worry about ad adjacency to genAI
  content. [eMarketer 2026 brand-safety FAQ]
- Benchmark 2026: 36.67% prioritise AI-driven creator matching; creator discovery is the most
  outsourced function (19.44%); fake/bot followers are the top fraud concern (56.5%); rising
  creator costs the top challenge (35.4%); 80% rate short-form video highly effective.
  [influencermarketinghub.com benchmark report]
- Oriane's own enterprise pitch mirrors this: creator vetting from "actual content",
  brand-safety archive scans ("bad language, competitor mentions, or off-brand behavior"),
  competitor benchmarks, IP/remix tracking, spend-vs-revenue per creator. [oriane.xyz/enterprise]
- Jury-recognisable framings: (a) evidence-backed creator vetting / brand-safety dossier
  from transcripts + frames + comments, geo-filtered to the GCC; (b) competitor/trend
  benchmark for a luxury/beauty brand; (c) hook/script intelligence from transcriptChunks
  of top-performing videos.

---

## 7. Top 3 integration risks for a 4-hour build

1. **Auth header undocumented; Free-tier key eligibility unknown.** First 10 minutes: log in,
   open app.oriane.xyz/billing/subscription?tab=api, copy the exact header name from the app,
   fire one `limit=1&projection=basic` call, confirm 200. If Free has no key, escalate to
   Julien/Thibaut on site immediately (credits are granted per Luma email).
2. **No on-demand ingestion + IG/TikTok only.** A "paste a video link" demo works only if
   that video is already indexed. Design search-the-index flows (creator/brand/topic/geo
   queries), not uploads; pre-verify demo queries return results. Visual queries are two
   calls (POST /rest/assets → visualSimilarity filter) and need `aiSearchAnchor` on page 2+.
3. **Credit burn, unknown limits and latency.** Credits appear to be charged per returned
   result; `projection=full` × `limit=100` on a 250-credit Free account can hit 402 within
   minutes. Use `basic`/`default` for lists, `full` only for the selected creator's videos,
   cache every response, handle 402/416/206 explicitly. Measure latency on the first real
   call before wiring UI loops.

---

## 8. Sources

- https://www.oriane.xyz/ · https://www.oriane.xyz/enterprise · https://www.oriane.xyz/api ·
  https://www.oriane.xyz/free-tools · https://www.oriane.xyz/free-tools/video-analyzer ·
  https://www.oriane.xyz/text-to-videos-search · https://www.oriane.xyz/video-to-videos-search ·
  https://www.oriane.xyz/for-developers · https://www.oriane.xyz/partners
- https://connect.oriane.xyz/rest/docs (inline OpenAPI 3.0.0 spec, rendered in browser; copy in
  `scripts/oriane_openapi.json`) · https://connect.oriane.xyz/mcp (live probes) ·
  https://app.oriane.xyz/embed/pricing-table (rendered) ·
  https://app.oriane.xyz/billing/subscription?tab=api
- https://luma.com/kbk3wqgu · https://luma.com/discover/dubai/tech
- https://www.producthunt.com/products/oriane · https://gen.xyz/blog/oriane-xyz ·
  https://www.webanditnews.com/2026/03/21/oriane-raises-2m-and-launches-the-ai-video-intelligence-platform-that-replaces-legacy-brand-monitoring-tools/ ·
  https://markets.financialcontent.com/bpas/article/accwirecq-2026-3-23-oriane-announces-public-release-of-video-analysis-platform ·
  https://github.com/jasonmunguia/oriane-system
- https://docs.replit.com/cloud-services/deployments/about-deployments ·
  https://docs.replit.com/billing/ai-billing · https://replit.com/pricing
- https://ykone.com/home-2-2/ ·
  https://www.emarketer.com/content/faq-on-brand-safety--how-ai-content-creator-marketing-reshaping-risk-2026 ·
  https://influencermarketinghub.com/influencer-marketing-benchmark-report/

---

## What I scaffolded in /home/claude/vyral-scout and why

**Honesty note:** this research agent did *not* write the scaffold. `/home/claude/vyral-scout`
already existed (created by another session in this workspace: git repo with zero commits,
files dated 27 Sep 00:56–01:04). What follows is an audit of that code as it stands, so the
description matches reality.

**Product concept — "Scout by VYRAL":** brief in, evidence-backed creator shortlist out. A
brand manager types a brief (brand, category, region, follower band, competitors, keywords,
languages, optional image/visual prompt); the pipeline discovers creators from the Oriane
index, pulls their profiles, vets their recent videos (transcript/caption flags with verbatim
quotes and timestamps, sponsored-partner detection, language mix, cadence), scores them with
a transparent 0–100 composite (relevance 35 / performance 25 / audience 15 / safety 25), asks
an LLM for a per-creator judgment, and renders an HTML dossier + CSV. Aimed squarely at the
YKONE-style "documented vetting" gap in section 6.

**Layout:** `app/main.py` (FastAPI: `GET /`, `GET /api/health[?probe=1]`, `POST /api/scout`,
`GET /api/runs`, `GET /api/runs/{id}`, `GET /dossier/{id}`, `GET /dossier/{id}.csv`,
`GET /api/regions`) · `scout/oriane.py` (client) · `scout/brief.py`, `discover.py`,
`vetting.py`, `scoring.py`, `pipeline.py`, `dossier.py`, `geo.py`, `llm.py`,
`mock_server.py` · `app/templates/index.html`, `app/static/app.js|style.css` ·
`scripts/oriane_openapi.json` · `data/{cache,runs}` (empty) · `tests/`, `jarvis/` (empty).

**Oriane endpoints it calls (all three, matching the spec):**
- `POST /rest/contents/search` — discovery (`projection=default`, sort
  `engagementRatePerViews:desc,viewsCount:desc`, geo + keyword + date + follower filters);
  visual discovery (sort `visualSimilarity:desc`, honours `aiSearchAnchor`); vetting
  (`projection=full`, sort `publishedAt:desc`, per-creator `profileId` filter).
- `POST /rest/profiles/search` — `projection=full`, `id.includes` chunks for the candidate pool.
- `POST /rest/assets` — text asset from a visual prompt, or image asset from a URL.
Client behaviour: auth-style auto-detect (bearer → x-api-key → api-key → raw), persisted in
`data/auth_style.txt`; SHA-256 disk cache with 3-day TTL; per-run budget cap
(`SCOUT_MAX_RESULTS_PER_RUN`, default 400); explicit handling of 401/403, 402, 416, 206;
append-only credit ledger `data/credits.jsonl`.

**Mock vs real:** `SCOUT_MOCK=1` (or pointing `ORIANE_BASE_URL` at the bundled mock) uses
`scout/mock_server.py`, a synthetic Oriane over ~44 fake GCC/EU creators (handles end in
`.demo`) implementing the same three routes, filter grammar, sort, pagination and
projections. `SCOUT_OFFLINE=1` serves only from the disk cache. Live mode needs
`ORIANE_API_KEY` (+ `ORIANE_AUTH_STYLE` once known). LLM: `SCOUT_LLM_BACKEND=auto` tries
Anthropic API → `claude` CLI → Ollama → none; every LLM step degrades to heuristics.

**Untested / known gaps (found during this audit):**
- Nothing has been run: `tests/` is empty, no git commit, and the Python deps are not
  installed in this sandbox (`import fastapi` fails). `py_compile` passes for all modules.
- **`scout/dossier.py` renders `app/templates/dossier.html`, which does not exist** (only
  `index.html`). `GET /dossier/{id}` and the CSV path will fail until that template is added.
- Never exercised against the real API: auth header, real filter acceptance, latency, credit
  burn per projection, CORS. The mock has not been run either (needs `pip install -r
  requirements.txt`).
- `SCOUT_ANTHROPIC_MODEL` defaults to `claude-sonnet-5` and Ollama to `qwen3.5:9b` — verify
  those model ids exist where you run it.
- `jarvis/` is an empty placeholder (Telegram dependency listed, no handler written).

**Run it:**
```bash
cd /home/claude/vyral-scout
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# rehearsal (mock Oriane) — terminal 1:
uvicorn scout.mock_server:app --port 8791
# app — terminal 2:
ORIANE_BASE_URL=http://127.0.0.1:8791 ORIANE_API_KEY=demo ORIANE_AUTH_STYLE=bearer \
  uvicorn app.main:app --host 127.0.0.1 --port 8787
# live: put ORIANE_API_KEY=... (and ORIANE_AUTH_STYLE=<header style from the app>) in .env, then:
uvicorn app.main:app --host 0.0.0.0 --port 8787
# open http://127.0.0.1:8787  — check http://127.0.0.1:8787/api/health?probe=1 first
```
