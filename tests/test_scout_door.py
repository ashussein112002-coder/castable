"""Fail-first tests for the Jarvis door: parse() and card() over a real run record."""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis import scout_door  # noqa: E402


def _run():
    files = sorted(glob.glob(str(Path(__file__).resolve().parent.parent / "data" / "runs" / "*.json")))
    for f in reversed(files):
        r = json.loads(Path(f).read_text(encoding="utf-8"))
        if r.get("shortlist"):
            return r
    raise AssertionError("no brand run record with a shortlist to test against")


def test_parse_region_band_platforms():
    f = scout_door.parse("Modest fashion launch in Riyadh, micro creators, TikTok only")
    assert f["region"] == "riyadh" and f["follower_band"] == "micro" and f["platforms"] == ["tiktok"]
    f = scout_door.parse("Luxury skincare in Dubai, macro creators")
    assert f["region"] == "dubai" and f["follower_band"] == "macro" and f["platforms"] == ["instagram", "tiktok"]
    f = scout_door.parse("عطور فاخرة في دبي")
    assert f["region"] == "dubai"


def test_card_has_top3_and_dossier_link():
    run = _run()
    text = scout_door.card(run)
    assert "Client dossier" in text and f"/dossier/{run['id']}" in text
    assert text.count("\n<b>1. ") == 1 and "<b>2. " in text
    assert "<" not in text.replace("<b>", "").replace("</b>", "").replace("<a href=", "").replace("</a>", "").replace("<code>", "").replace("</code>", "").replace("\">", "")


def test_card_error_run():
    text = scout_door.card({"id": "x", "status": "error", "error": "Oriane API error: 401 <bad>", "brief": {"brand": "B", "region": "uae"}})
    assert "❌" in text and "&lt;bad&gt;" in text
