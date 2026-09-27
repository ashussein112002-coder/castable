"""Render a run into a self-contained HTML dossier + CSV export."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .scoring import PENALTY, WEIGHTS
from .vetting import video_link

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
# keep Arabic readable in the JSON appendix (tojson escapes <, >, &, ' regardless)
_env.policies["json.dumps_kwargs"] = {"sort_keys": False, "ensure_ascii": False}


def _fmt_int(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except Exception:  # noqa: BLE001 - includes jinja2 Undefined
        return "-"


def _fmt_pct(v: Any, digits: int = 1) -> str:
    try:
        return f"{float(v) * 100:.{digits}f}%"
    except Exception:  # noqa: BLE001 - includes jinja2 Undefined
        return "-"


def _fmt_t(v: Any) -> str:
    try:
        s = float(v)
        return f"{int(s // 60):02d}:{int(s % 60):02d}"
    except Exception:  # noqa: BLE001 - includes jinja2 Undefined
        return ""


def _fmt_date(v: Any, fmt: str = "%d %b %Y") -> str:
    """ISO-8601 string -> '20 Jun 2026'. Unparseable values pass through (first 10 chars)."""
    if not v:
        return ""
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).strftime(fmt)
    except Exception:  # noqa: BLE001
        return str(v)[:10]


def _fmt_compact(v: Any) -> str:
    """268159 -> '268K', 1574092 -> '1.6M'."""
    try:
        n = float(v)
    except Exception:  # noqa: BLE001 - includes jinja2 Undefined
        return "-"
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            x = n / div
            return (f"{x:.1f}".rstrip("0").rstrip(".") if x < 100 else f"{x:.0f}") + suffix
    return f"{n:.0f}"


def _fmt_num(v: Any, digits: int = 2) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:  # noqa: BLE001 - includes jinja2 Undefined
        return "-"


def _video_url(v: Any) -> str | None:
    """Deep link for a raw Oriane content item (same rules as the vetting step)."""
    if not isinstance(v, dict):
        return None
    try:
        return video_link(v)
    except Exception:  # noqa: BLE001 - presentation only
        return None


_TAG = re.compile(r"(?<![&\w])([#@]\w+(?:\.\w+)*)")


def _bidi_tags(v: Any) -> Markup:
    """Escape, then isolate #hashtags / @mentions in <bdi> so they keep their
    shape inside right-to-left (Arabic) captions."""
    if not v:
        return Markup("")
    return Markup(_TAG.sub(r"<bdi>\1</bdi>", str(escape(str(v)))))


_env.filters["int"] = _fmt_int
_env.filters["pct"] = _fmt_pct
_env.filters["ts"] = _fmt_t
_env.filters["date"] = _fmt_date
_env.filters["compact"] = _fmt_compact
_env.filters["num"] = _fmt_num
_env.filters["video_url"] = _video_url
_env.filters["tags"] = _bidi_tags


def render_dossier(run: dict[str, Any], public_url: str | None = None) -> str:
    tpl = _env.get_template("dossier.html")
    return tpl.render(run=run, brief=run.get("brief") or {}, shortlist=run.get("shortlist") or [], public_url=public_url, weights=WEIGHTS, penalty=PENALTY)


def render_creator(run: dict[str, Any], public_url: str | None = None) -> str:
    """Creator-facing Brand-Readiness Report (kind == "creator" runs)."""
    tpl = _env.get_template("creator.html")
    report = run.get("report") or {}
    return tpl.render(run=run, report=report if isinstance(report, dict) else {}, public_url=public_url)


def render_csv(run: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "handle", "platform", "followers", "score", "grade", "relevance", "performance", "audience", "safety", "matching_videos", "er_views_mean", "flags", "sponsored_posts", "cadence_per_week", "language_mix", "public_email", "profile_url"])
    for i, row in enumerate(run.get("shortlist") or [], 1):
        c, p, v, s = row["candidate"], row.get("profile") or {}, row.get("vetting") or {}, row["score"]
        handle = c.get("handle")
        url = f"https://www.tiktok.com/@{handle}" if c.get("platform") == "tiktok" else f"https://www.instagram.com/{handle}/"
        w.writerow([i, handle, c.get("platform"), p.get("followersCount") or c.get("followers"), s["total"], s["grade"], s["components"]["relevance"], s["components"]["performance"], s["components"]["audience"], s["components"]["safety"], c.get("matching_videos"), c.get("er_views_mean"), "; ".join(f"{f['type']}:{f['term']}" for f in v.get("flags") or []), v.get("sponsored_posts"), v.get("cadence_per_week"), v.get("language_mix"), p.get("publicEmail"), url])
    return buf.getvalue()
