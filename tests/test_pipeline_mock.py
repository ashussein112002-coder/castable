"""End-to-end pipeline test against the bundled mock Oriane server (no credits, no network).
Fail-first: it asserts the shapes the dossier and the Jarvis card depend on."""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_base_url():
    import uvicorn

    from scout.mock_server import app as mock_app

    port = _free_port()
    config = uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(base + "/", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield base
    server.should_exit = True


@pytest.fixture()
def settings_env(mock_base_url, monkeypatch):
    tmp = tempfile.mkdtemp(prefix="scout-test-")
    monkeypatch.setenv("SCOUT_DATA_DIR", tmp)
    monkeypatch.setenv("ORIANE_BASE_URL", mock_base_url)
    monkeypatch.setenv("ORIANE_API_KEY", "demo")
    monkeypatch.setenv("ORIANE_AUTH_STYLE", "bearer")
    monkeypatch.setenv("SCOUT_LLM_BACKEND", "none")
    # settings are a snapshot at import time: rebuild them for this process
    import importlib

    import scout.config as cfg

    importlib.reload(cfg)
    for mod in ("scout.oriane", "scout.discover", "scout.vetting", "scout.brief", "scout.llm", "scout.scoring", "scout.pipeline"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    return cfg.settings


def test_run_end_to_end(settings_env):
    from scout import pipeline

    form = {"text": "Luxury skincare launch in Dubai. Women 22-35, Arabic and English. Competitors: La Mer.", "brand": "Test", "category": "skincare", "region": "dubai", "platforms": ["instagram", "tiktok"], "follower_band": "micro", "use_llm": False}
    run = pipeline.start_run(form, background=False)
    assert run["status"] == "done", run.get("error") or run["log"][-3:]
    assert run["mode"] == "mock"  # never labelled live when the base URL is not oriane.xyz
    assert run["discovery"]["videos"] > 0 and run["discovery"]["creators"] > 0
    assert run["shortlist"], "empty shortlist"
    top = run["shortlist"][0]
    for key in ("candidate", "profile", "vetting", "score"):
        assert key in top
    assert top["score"]["vetted"] is True
    assert set(top["score"]["components"]) == {"relevance", "performance", "audience", "safety"}
    assert 0 <= top["score"]["total"] <= 100 and top["score"]["grade"] in "ABCD"
    ev = top["vetting"]["evidence_videos"]
    assert ev and "transcript_excerpt" in ev[0] and "frames" in ev[0]
    assert run["stats"]["oriane"]["calls"] > 0


def test_flag_caps_grade(settings_env):
    from scout.brief import Brief
    from scout.scoring import score_creator

    brief = Brief.from_form({"text": "x", "region": "dubai", "follower_band": "micro"})
    cand = {"profileId": "prf_1", "handle": "h", "platform": "instagram", "followers": 50000, "matching_videos": 4, "matched_queries": {"a": 1, "b": 1}, "visual_best_rank": 1, "er_views_mean": 0.2, "views_max": 100000}
    vet_clean = {"flags": [], "language_mix": {"en": 5}, "authenticity_notes": []}
    vet_high = {"flags": [{"type": "hate", "severity": "high"}], "language_mix": {"en": 5}, "authenticity_notes": []}
    pool = [cand]
    clean = score_creator(cand, vet_clean, None, brief, pool)
    bad = score_creator(cand, vet_high, None, brief, pool)
    assert clean["grade"] in "AB" and clean["total"] > bad["total"]
    assert bad["total"] <= 59 and bad["grade"] in "CD" and bad["caps"]


def test_dossier_and_csv_render(settings_env):
    from scout import pipeline
    from scout.dossier import render_csv, render_dossier

    run = pipeline.start_run({"text": "Modest fashion in Riyadh, micro creators", "region": "riyadh", "follower_band": "micro", "use_llm": False}, background=False)
    html = render_dossier(run)
    assert "Creator Casting Dossier" in html and run["shortlist"][0]["candidate"]["handle"] in html
    csv = render_csv(run)
    assert csv.splitlines()[0].startswith("rank,handle,platform")
    assert len(csv.splitlines()) == len(run["shortlist"]) + 1
