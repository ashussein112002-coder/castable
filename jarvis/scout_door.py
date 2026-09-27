# -*- coding: utf-8 -*-
"""scout_door — Jarvis's door into Castable (creator casting with video evidence).

Drop-in for jarvis-agent: copy to src/jarvis/tools/scout_door.py and register
`/scout` in bridge/commands.py -> handler "_cmd_scout" in bridge/bot.py:

    async def _cmd_scout(update, ctx):
        from jarvis.tools import scout_door
        await scout_door.cmd_scout(update, ctx)

What it does, in order (each hop fails loudly and by name):
  1. parse   — `/scout <brief>` (or a reply to a message/voice transcript). Region and
               follower band are inferred from the text; everything else is the brief.
  2. ensure  — GET /api/health on the local Scout app; if it is down, start it with
               ARRANCAR-SCOUT.command (non-interactive) and wait up to 40 s.
  3. run     — POST /api/scout, then poll /api/runs/{id} (edits ONE progress message).
  4. card    — top 3 creators with score/grade/flags + a link to the client dossier.

No exchange keys, no trading paths, no sudo. Pure HTTP to 127.0.0.1 and one
subprocess launch of a script that lives in the operator's own repo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("jarvis.scout_door")

SCOUT_URL = os.environ.get("SCOUT_URL", "http://127.0.0.1:8787")
SCOUT_PUBLIC_URL = os.environ.get("SCOUT_PUBLIC_URL", "")  # Replit / tunnel URL for phone-clickable links
SCOUT_REPO = Path(os.environ.get("SCOUT_REPO", str(Path.home() / "Documents" / "GitHub" / "vyral-scout")))
LAUNCHER = SCOUT_REPO / "ARRANCAR-SCOUT.command"
POLL_S = 3.0
TIMEOUT_S = float(os.environ.get("SCOUT_TIMEOUT_S", "420"))
# Hand-editable override, read on every command so the target can move (e.g. to the Replit
# deployment) without restarting the bot: ~/jarvis-vault/scout.env with SCOUT_URL=... / SCOUT_PUBLIC_URL=...
ENV_FILE = Path(os.environ.get("SCOUT_ENV_FILE", str(Path.home() / "jarvis-vault" / "scout.env")))


def _reload_env() -> None:
    global SCOUT_URL, SCOUT_PUBLIC_URL
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k == "SCOUT_URL" and v:
            SCOUT_URL = v.rstrip("/")
        elif k == "SCOUT_PUBLIC_URL":
            SCOUT_PUBLIC_URL = v.rstrip("/")

REGION_WORDS = {
    "dubai": "dubai", "دبي": "dubai", "abu dhabi": "abu-dhabi", "أبوظبي": "abu-dhabi", "uae": "uae", "emirates": "uae",
    "الإمارات": "uae", "riyadh": "riyadh", "الرياض": "riyadh", "jeddah": "jeddah", "جدة": "jeddah", "saudi": "saudi",
    "ksa": "saudi", "السعودية": "saudi", "qatar": "qatar", "doha": "qatar", "قطر": "qatar", "kuwait": "kuwait",
    "الكويت": "kuwait", "bahrain": "bahrain", "البحرين": "bahrain", "oman": "oman", "عمان": "oman", "gcc": "gcc",
    "gulf": "gcc", "الخليج": "gcc", "egypt": "egypt", "cairo": "egypt", "مصر": "egypt", "mena": "mena",
    "london": "london", "global": "global", "worldwide": "global",
}
BAND_WORDS = {"nano": "nano", "micro": "micro", "mid": "mid", "mid-tier": "mid", "macro": "macro", "mega": "macro", "any size": "any"}


HANDLE_RE = re.compile(r"^@([A-Za-z0-9._]{2,64})(?:\s+(.*))?$", re.S)


def parse_creator(text: str) -> dict[str, Any] | None:
    """`/scout @handle [tiktok|instagram] [region words] [niche...]` -> /api/creator form, or None."""
    m = HANDLE_RE.match((text or "").strip())
    if not m:
        return None
    handle, rest = m.group(1), (m.group(2) or "").strip()
    low = rest.lower()
    platforms = ["instagram", "tiktok"]
    if "tiktok" in low and "instagram" not in low:
        platforms = ["tiktok"]
    elif "instagram" in low and "tiktok" not in low:
        platforms = ["instagram"]
    region = "uae"
    for word, key in REGION_WORDS.items():
        if word in low:
            region = key
            break
    return {"handle": handle, "platforms": platforms, "region": region, "niche": rest[:200], "use_llm": True}


def parse(text: str) -> dict[str, Any]:
    """Turn free text into the /api/scout form. Everything is optional but the text."""
    t = (text or "").strip()
    low = t.lower()
    region = "uae"
    for word, key in REGION_WORDS.items():
        if word in low:
            region = key
            break
    band = "micro"
    for word, key in BAND_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            band = key
            break
    platforms = ["instagram", "tiktok"]
    if "tiktok" in low and "instagram" not in low and "ig " not in low:
        platforms = ["tiktok"]
    elif ("instagram" in low or "reels" in low) and "tiktok" not in low:
        platforms = ["instagram"]
    return {"text": t, "region": region, "follower_band": band, "platforms": platforms, "use_llm": True}


async def _get(client: httpx.AsyncClient, path: str, **kw: Any) -> dict[str, Any] | None:
    try:
        r = await client.get(SCOUT_URL + path, timeout=8, **kw)
        if r.status_code == 200:
            return r.json()
        log.warning("scout %s -> %s", path, r.status_code)
    except httpx.HTTPError as e:
        log.info("scout %s unreachable: %s", path, e)
    return None


async def ensure_up(client: httpx.AsyncClient, notify) -> dict[str, Any] | None:
    """Health or launch. Returns the health payload, or None when Scout never came up."""
    h = await _get(client, "/api/health")
    if h:
        return h
    if not LAUNCHER.exists():
        await notify(f"Scout is down and the launcher is missing: {LAUNCHER}")
        return None
    await notify("Scout is not running — starting it now.")
    try:
        subprocess.Popen(["/bin/bash", str(LAUNCHER)], cwd=str(SCOUT_REPO),
                         env={**os.environ, "SCOUT_NO_BROWSER": "1", "SCOUT_NO_TTY": "1"},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        await notify(f"Could not launch Scout: {e}")
        return None
    for _ in range(20):
        await asyncio.sleep(2)
        h = await _get(client, "/api/health")
        if h:
            return h
    await notify("Scout did not answer on /api/health within 40 s. Check ARRANCAR-SCOUT.command's log.")
    return None


def _fmt_int(v: Any) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _html(s: Any) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def creator_card(run: dict[str, Any]) -> str:
    """Telegram HTML card for a Brand-Readiness Report."""
    rep = run.get("report") or {}
    base = SCOUT_PUBLIC_URL or SCOUT_URL
    if run.get("status") == "error" or rep.get("error"):
        return f"<b>Castable</b>\n❌ {_html(run.get('error') or rep.get('error'))}"
    p, sc, me, bench = rep.get("profile") or {}, rep.get("score") or {}, rep.get("self_audit") or {}, rep.get("benchmark") or {}
    plan, market = rep.get("plan") or {}, rep.get("market") or []
    lines = [f"<b>Castable · @{_html(p.get('handle'))}</b> {(p.get('platform') or '')[:2].upper()} · {_fmt_int(p.get('followersCount'))} followers",
             f"Readiness <b>{sc.get('total')}</b> ({_html(sc.get('grade'))}) · " + " · ".join(f"{k} {int(v)}" for k, v in (sc.get("components") or {}).items())]
    if bench.get("er_percentile") is not None:
        lines.append(f"ER {((me.get('er_views_median') or 0) * 100):.1f}%/view · top {100 - int(bench['er_percentile'])}% of {bench.get('peers', 0)} peers")
    fixes = plan.get("fix_before_pitching") or []
    lines.append(f"\n<b>Fix before you pitch</b> ({len(fixes)})" if fixes else "\n<b>Clean</b> — nothing to fix in the last {} videos".format(rep.get("videos_checked", 0)))
    for f in fixes[:3]:
        lines.append(f"• {_html(str(f)[:140])}")
    if market:
        lines.append(f"\n<b>Brands buying from creators like you</b>: " + ", ".join(f"{_html(m['brand'])} ({m['creators']})" for m in market[:5]))
    for pt in (plan.get("pitches") or [])[:2]:
        lines.append(f"\n<b>Pitch → {_html(pt.get('brand'))}</b>\n   {_html(pt.get('angle'))}\n   <i>{_html(pt.get('subject_line'))}</i>")
    if plan.get("media_kit_line"):
        lines.append(f"\n“{_html(plan['media_kit_line'])}”")
    stats = (run.get("stats") or {}).get("oriane") or {}
    lines.append(f"\n📄 <a href=\"{base}/report/{run.get('id')}\">Open my report</a> · Oriane {stats.get('calls', 0)} calls / {stats.get('results_fetched_live', 0)} results · {(run.get('stats') or {}).get('seconds', 0)} s")
    return "\n".join(lines)


def card(run: dict[str, Any]) -> str:
    """Telegram HTML card: the three numbers an agency reads first, then evidence."""
    if run.get("kind") == "creator" or run.get("report"):
        return creator_card(run)
    brief = run.get("brief") or {}
    rows = run.get("shortlist") or []
    stats = (run.get("stats") or {}).get("oriane") or {}
    base = SCOUT_PUBLIC_URL or SCOUT_URL
    lines = [f"<b>Scout · {_html(brief.get('brand') or brief.get('category') or 'brief')} · {_html((brief.get('region') or '').upper())}</b>"]
    if run.get("status") == "error":
        lines.append(f"❌ {_html(run.get('error'))}")
        return "\n".join(lines)
    lines.append(_html(run.get("summary") or ""))
    for i, row in enumerate(rows[:3], 1):
        c, p, v, s = row.get("candidate") or {}, row.get("profile") or {}, row.get("vetting") or {}, row.get("score") or {}
        j = row.get("judgment") or {}
        handle = c.get("handle") or "?"
        plat = (c.get("platform") or "")[:2].upper()
        url = f"https://www.tiktok.com/@{handle}" if c.get("platform") == "tiktok" else f"https://www.instagram.com/{handle}/"
        flags = v.get("flags") or []
        flag_txt = "clean" if v and not flags else (f"{len(flags)} flag(s): " + ", ".join(sorted({f.get('type', '?') for f in flags})) if flags else "not vetted")
        er = c.get("er_views_mean")
        er_txt = f"{er * 100:.1f}% ER/view" if isinstance(er, (int, float)) else ""
        lines.append(f"\n<b>{i}. <a href=\"{url}\">@{_html(handle)}</a></b> {plat} · {_fmt_int(p.get('followersCount') or c.get('followers'))} followers · <b>{s.get('total')}</b> ({_html(s.get('grade'))})")
        lines.append(f"   {c.get('matching_videos') or 0} matching videos · {er_txt} · {_html(flag_txt)}")
        ev = (v.get("evidence_videos") or [{}])[0]
        quote = (ev.get("transcript_excerpt") or "").strip()
        if quote:
            lines.append(f"   “{_html(quote[:140])}{'…' if len(quote) > 140 else ''}”")
        if j.get("recommended_angle"):
            lines.append(f"   → {_html(j['recommended_angle'])}")
    lines.append(f"\n📄 <a href=\"{base}/dossier/{run.get('id')}\">Client dossier</a> · Oriane {stats.get('calls', 0)} calls / {stats.get('results_fetched_live', 0)} results · {(run.get('stats') or {}).get('seconds', 0)} s")
    return "\n".join(lines)


async def run_scout(text: str, notify, progress) -> dict[str, Any] | None:
    """The whole door, reusable from the bot handler or a test. `notify(msg)` sends a
    line, `progress(msg)` edits the single progress message."""
    _reload_env()
    creator = parse_creator(text)
    form = creator or parse(text)
    if not creator and len(form["text"]) < 3:
        await notify("Usage: /scout @handle (your Brand-Readiness Report) or /scout <brand brief>. Example: /scout @rania.skincare instagram dubai")
        return None
    async with httpx.AsyncClient() as client:
        health = await ensure_up(client, notify)
        if not health:
            return None
        mode = health.get("mode", "?")
        endpoint = "/api/creator" if creator else "/api/scout"
        try:
            r = await client.post(SCOUT_URL + endpoint, json=form, timeout=15)
            r.raise_for_status()
            run_id = r.json()["id"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            await notify(f"Castable refused the request: {e}")
            return None
        head = f"Castable · @{form['handle']} · {'/'.join(form['platforms'])} · {form['region']}" if creator else f"Castable run · region {form['region']} · band {form['follower_band']}"
        await progress(f"{head}\n<code>{run_id}</code> ({mode})\nreading Oriane…")
        t0 = time.monotonic()
        last_log = ""
        while time.monotonic() - t0 < TIMEOUT_S:
            await asyncio.sleep(POLL_S)
            run = await _get(client, f"/api/runs/{run_id}")
            if not run:
                continue
            log_lines = run.get("log") or []
            tail = "\n".join(_html(l) for l in log_lines[-4:])
            if tail != last_log:
                last_log = tail
                await progress(f"{head}\n<code>{run_id}</code> ({mode})\n<code>{tail}</code>")
            if run.get("status") in ("done", "error"):
                return run
        await notify(f"Castable is still running after {int(TIMEOUT_S)} s — open {SCOUT_PUBLIC_URL or SCOUT_URL}/?run={run_id}")
        return None


async def cmd_scout(update, ctx) -> None:
    """python-telegram-bot handler. Text comes from the command args or the replied message."""
    msg = update.effective_message
    text = " ".join(ctx.args or []).strip() if getattr(ctx, "args", None) else ""
    if not text and msg and msg.reply_to_message:
        text = (msg.reply_to_message.text or msg.reply_to_message.caption or "").strip()
    if not text and msg:
        text = re.sub(r"^/scout(@\w+)?\s*", "", msg.text or "", count=1).strip()
    state: dict[str, Any] = {"progress": None}

    async def notify(s: str) -> None:
        await msg.reply_text(s, parse_mode="HTML", disable_web_page_preview=True)

    async def progress(s: str) -> None:
        try:
            if state["progress"] is None:
                state["progress"] = await msg.reply_text(s, parse_mode="HTML", disable_web_page_preview=True)
            else:
                await state["progress"].edit_text(s, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001 — a failed edit must never kill the run
            log.info("progress edit skipped: %s", e)

    try:
        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:  # noqa: BLE001
        pass
    run = await run_scout(text, notify, progress)
    if run:
        await msg.reply_text(card(run), parse_mode="HTML", disable_web_page_preview=True)
