"""Castable web app. Creator mode: @handle in, Brand-Readiness Report out.
Brand mode: brief in, evidence-backed creator shortlist out.

Endpoints
  GET  /                   UI
  GET  /api/health         mode, Oriane auth probe (cached), LLM backend, credit ledger
  POST /api/scout          start a brand run (JSON form) -> {id}
  POST /api/creator        start a creator run {handle, platforms, region, niche?, use_llm} -> {id}
  GET  /api/runs           recent runs
  GET  /api/runs/{id}      run record (status, log, shortlist)
  GET  /dossier/{id}       HTML dossier (brand runs)
  GET  /report/{id}        HTML Brand-Readiness Report (creator runs; auto-refreshing page while running)
  GET  /demo               most recent finished creator report (live preferred)
  GET  /demo/brand         most recent finished brand dossier
  GET  /dossier/{id}.csv   CSV export
  GET  /api/regions        region keys for the UI
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import deque
from html import escape as html_escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.gzip import GZipMiddleware

from scout import pipeline
from scout.brief import FOLLOWER_BANDS
from scout.config import RUNS_DIR, settings
from scout.dossier import render_creator, render_csv, render_dossier
from scout.geo import REGIONS
from scout.llm import LLM
from scout.oriane import OrianeClient, OrianeError, ledger_totals

logging.basicConfig(level=os.environ.get("SCOUT_LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("scout.app")

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Castable", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ---- security headers + a tiny in-memory per-IP rate limit on the run-starting endpoints
RATE_LIMIT_PER_MIN = int(os.environ.get("CASTABLE_RATE_LIMIT", "6"))
RATE_LIMITED_PATHS = {"/api/creator", "/api/scout"}
# Replit's workspace preview frames the app; set CASTABLE_FRAME_OPTIONS=off to allow that while rehearsing.
FRAME_OPTIONS = os.environ.get("CASTABLE_FRAME_OPTIONS", "off")  # "DENY" once the app is served outside a preview iframe
_rate_lock = threading.Lock()
_rate_hits: dict[str, deque] = {}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str, now: float) -> int:
    """0 when allowed (and the hit is recorded); otherwise seconds until the next slot frees up."""
    with _rate_lock:
        hits = _rate_hits.setdefault(ip, deque())
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_PER_MIN:
            return max(1, int(60 - (now - hits[0])) + 1)
        hits.append(now)
        if len(_rate_hits) > 5000:  # keep memory bounded
            for k in [k for k, v in _rate_hits.items() if not v or now - v[-1] >= 60]:
                _rate_hits.pop(k, None)
        return 0


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path in RATE_LIMITED_PATHS:
        wait = _rate_limited(_client_ip(request), time.time())
        if wait:
            response = JSONResponse({"detail": f"Too many checks from this connection: max {RATE_LIMIT_PER_MIN} per minute. Try again in {wait} s.", "retry_after": wait}, status_code=429, headers={"Retry-After": str(wait)})
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if FRAME_OPTIONS.lower() != "off":
        response.headers.setdefault("X-Frame-Options", FRAME_OPTIONS)
    return response

_health_cache: dict[str, Any] = {"at": 0.0, "value": None}


class ScoutForm(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)
    brand: str = ""
    category: str = ""
    region: str = "uae"
    platforms: list[str] = ["instagram", "tiktok"]
    follower_band: str = "micro"
    followers_min: int | None = None
    followers_max: int | None = None
    days_back: int = 90
    competitors: str = ""
    keywords: str = ""
    languages: str = ""
    image_url: str = ""
    visual_prompt: str = ""
    use_llm: bool = True
    vet_top_k: int | None = None
    videos_per_creator: int | None = None
    discovery_limit: int | None = None


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/regions")
async def regions() -> dict[str, Any]:
    return {"regions": [{"key": k, "label": v["label"]} for k, v in REGIONS.items()], "bands": {k: list(v) for k, v in FOLLOWER_BANDS.items()}}


@app.get("/api/health")
async def health(probe: bool = False) -> dict[str, Any]:
    mode = pipeline.run_mode()
    out: dict[str, Any] = {
        "mode": mode,
        "oriane_base_url": settings.ORIANE_BASE_URL,
        "oriane_key_present": bool(settings.ORIANE_API_KEY),
        "auth_style": settings.ORIANE_AUTH_STYLE,
        "llm": LLM().describe(),
        "ledger": ledger_totals(),
        "budget": {"max_results_per_run": settings.SCOUT_MAX_RESULTS_PER_RUN, "discovery_limit": settings.SCOUT_DISCOVERY_LIMIT, "vet_top_k": settings.SCOUT_VET_TOP_K, "videos_per_creator": settings.SCOUT_VET_VIDEOS_PER_CREATOR},
    }
    if probe and not settings.SCOUT_OFFLINE:
        if time.time() - _health_cache["at"] < 300 and _health_cache["value"]:
            out["probe"] = _health_cache["value"]
        else:
            try:
                out["probe"] = OrianeClient().probe()
            except OrianeError as exc:
                out["probe"] = {"ok": False, "error": str(exc), "status": exc.status}
            _health_cache.update(at=time.time(), value=out["probe"])
    return out


@app.post("/api/scout")
async def scout(form: ScoutForm) -> dict[str, Any]:
    run = pipeline.start_run(form.model_dump())
    return {"id": run["id"], "status": run["status"]}


HANDLE_RE = re.compile(r"^@?[A-Za-z0-9._]{2,64}$")
PLATFORMS = ("instagram", "tiktok")


class CreatorForm(BaseModel):
    handle: str = Field(..., max_length=80)
    platforms: list[str] = ["instagram", "tiktok"]
    region: str = "uae"
    niche: str = Field("", max_length=120)
    use_llm: bool = True

    @field_validator("handle")
    @classmethod
    def _handle(cls, v: str) -> str:
        v = (v or "").strip()
        if not HANDLE_RE.match(v):
            raise ValueError("handle must be 2-64 letters, digits, dots or underscores (an optional leading @)")
        return v.lstrip("@")

    @field_validator("platforms")
    @classmethod
    def _platforms(cls, v: list[str]) -> list[str]:
        out = [p for p in dict.fromkeys((x or "").strip().lower() for x in v) if p in PLATFORMS]
        if not out:
            raise ValueError("pick at least one platform: instagram or tiktok")
        return out

    @field_validator("region")
    @classmethod
    def _region(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in REGIONS:
            raise ValueError(f"unknown region; use one of: {', '.join(REGIONS)}")
        return v
    videos_n: int | None = None
    peers_n: int | None = None
    peer_videos_n: int | None = None
    discovery_limit: int | None = None


@app.post("/api/creator")
async def creator(form: CreatorForm) -> dict[str, Any]:
    payload = form.model_dump()
    payload["kind"] = "creator"
    run = pipeline.start_run(payload)
    return {"id": run["id"], "status": run["status"]}


@app.get("/api/runs")
async def runs() -> dict[str, Any]:
    return {"runs": pipeline.list_runs()}


@app.get("/api/runs/{run_id}")
async def run(run_id: str) -> dict[str, Any]:
    r = pipeline.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


# NOTE: the CSV route must be declared before /dossier/{run_id}; otherwise the
# HTML route captures "<id>.csv" as the run id and returns 404.
@app.get("/dossier/{run_id}.csv", response_class=PlainTextResponse)
async def dossier_csv(run_id: str) -> PlainTextResponse:
    r = pipeline.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return PlainTextResponse(render_csv(r), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="castable-{run_id}.csv"'})


@app.get("/dossier/{run_id}", response_class=HTMLResponse)
async def dossier(run_id: str) -> str:
    r = pipeline.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return render_dossier(r, public_url=settings.SCOUT_PUBLIC_URL)


def _is_creator(r: dict[str, Any] | None) -> bool:
    return bool(r) and (r.get("kind") or (r.get("form") or {}).get("kind")) == "creator"


def _friendly_404(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark"><title>{html_escape(title)} · Castable</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0B0D10;color:#EDEAE4;font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:24px}}
main{{max-width:520px}}.k{{color:#F5B84A;font-size:12px;letter-spacing:.18em;text-transform:uppercase}}h1{{font-family:Georgia,"Times New Roman",serif;font-weight:500;font-size:34px;line-height:1.15;margin:10px 0 12px}}
p{{color:#BDB9B1;margin:0 0 22px}}a{{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:999px;background:#F5B84A;color:#16120A;text-decoration:none;font-weight:600}}</style></head>
<body><main><div class="k">Castable</div><h1>{html_escape(title)}</h1><p>{html_escape(body)}</p><a href="/">Check a handle</a></main></body></html>"""
    return HTMLResponse(html, status_code=404)


def _finished_runs(kind: str) -> list[dict[str, Any]]:
    """Finished runs of one kind, newest first (run ids start with a UTC timestamp)."""
    out = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("status") != "done":
            continue
        if (kind == "creator") == _is_creator(r):
            out.append(r)
    return out


@app.get("/report/{run_id}", response_class=HTMLResponse)
async def creator_report_page(run_id: str) -> HTMLResponse:
    r = pipeline.get_run(run_id)
    if not _is_creator(r):
        return _friendly_404("Report not found", "This report link is wrong or has expired. Type your handle to get a fresh Brand-Readiness Report.")
    return HTMLResponse(render_creator(r, public_url=settings.SCOUT_PUBLIC_URL))


@app.get("/demo", response_class=HTMLResponse)
async def demo_creator() -> HTMLResponse:
    runs = _finished_runs("creator")
    pick = next((r for r in runs if r.get("mode") == "live"), None) or (runs[0] if runs else None)
    if not pick:
        return _friendly_404("No sample report yet", "Nobody has finished a Brand-Readiness Report on this server yet. Run the first one from the home page.")
    return HTMLResponse(render_creator(pick, public_url=settings.SCOUT_PUBLIC_URL))


@app.get("/demo/brand", response_class=HTMLResponse)
async def demo_brand() -> HTMLResponse:
    runs = _finished_runs("brand")
    pick = next((r for r in runs if r.get("shortlist") and r.get("mode") == "live"), None) or next((r for r in runs if r.get("shortlist")), None) or (runs[0] if runs else None)
    if not pick:
        return _friendly_404("No sample dossier yet", "No brand shortlist has finished on this server yet. Paste a brief on the home page to create one.")
    return HTMLResponse(render_dossier(pick, public_url=settings.SCOUT_PUBLIC_URL))
