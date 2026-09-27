"""End-to-end run: brief -> discovery -> profiles -> vetting -> scoring ->
LLM judgment -> dossier. Each run is a JSON record under data/runs/ with a
line-by-line log, so a run can be replayed and audited."""
from __future__ import annotations

import datetime as dt
import json
import logging
import secrets
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .brief import Brief
from .creator import creator_report
from .config import RUNS_DIR, settings
from .discover import discover, fetch_profiles
from .llm import LLM
from .oriane import OrianeBudgetExceeded, OrianeClient, OrianeCreditsExhausted, OrianeError
from .scoring import score_creator
from .vetting import fetch_recent_videos, vet_creator

log = logging.getLogger("scout.pipeline")

_LOCK = threading.Lock()
_RUNS: dict[str, dict[str, Any]] = {}


def run_mode() -> str:
    """mock | offline | live — "live" only when the client really talks to oriane.xyz."""
    if settings.SCOUT_MOCK or "oriane.xyz" not in (settings.ORIANE_BASE_URL or ""):
        return "mock"
    return "offline" if settings.SCOUT_OFFLINE else "live"


def new_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _save(run: dict[str, Any]) -> None:
    try:
        (RUNS_DIR / f"{run['id']}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        log.warning("could not persist run %s: %s", run.get("id"), exc)


def get_run(run_id: str) -> dict[str, Any] | None:
    with _LOCK:
        run = _RUNS.get(run_id)
    if run:
        return run
    path = RUNS_DIR / f"{run_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
            rows.append({"id": r.get("id"), "kind": r.get("kind") or "brand", "status": r.get("status"), "started": r.get("started"), "brand": (r.get("brief") or {}).get("brand"), "handle": ((r.get("report") or {}).get("handle")), "category": (r.get("brief") or {}).get("category"), "region": (r.get("brief") or {}).get("region") or ((r.get("report") or {}).get("region")), "shortlist": len(r.get("shortlist") or []), "mode": r.get("mode")})
        except ValueError:
            continue
    return rows


def start_run(form: dict[str, Any], *, client: OrianeClient | None = None, llm: LLM | None = None, background: bool = True) -> dict[str, Any]:
    run_id = new_run_id()
    run: dict[str, Any] = {"id": run_id, "status": "queued", "started": dt.datetime.now(dt.timezone.utc).isoformat(), "log": [], "form": form, "mode": run_mode()}
    with _LOCK:
        _RUNS[run_id] = run
    if background:
        threading.Thread(target=execute, args=(run, form, client, llm), daemon=True).start()
    else:
        execute(run, form, client, llm)
    return run


def execute(run: dict[str, Any], form: dict[str, Any], client: OrianeClient | None = None, llm: LLM | None = None) -> dict[str, Any]:
    if form.get("kind") == "creator" or (form.get("handle") and not form.get("text")):
        return execute_creator(run, form, client, llm)
    t0 = time.perf_counter()

    def logline(msg: str) -> None:
        stamp = f"{time.perf_counter() - t0:6.1f}s"
        run["log"].append(f"[{stamp}] {msg}")
        log.info("%s %s", run["id"], msg)

    client = client or OrianeClient()
    llm = llm or LLM()
    run["status"] = "running"
    try:
        # 1. brief
        brief = Brief.from_form(form)
        logline(f"brief parsed: category={brief.category or '-'} keywords={len(brief.keywords)} competitors={brief.competitors}")
        if form.get("use_llm", True):
            brief.enrich(llm)
            logline(f"brief enriched by LLM ({brief.llm_used}): {len(brief.keywords)} keywords, {len(brief.hashtags)} hashtags, competitors={brief.competitors}")
        run["brief"] = brief.as_dict()
        _save(run)

        # 2. discovery
        disc = discover(client, brief, limit=int(form.get("discovery_limit") or settings.SCOUT_DISCOVERY_LIMIT), log=logline)
        candidates = disc["candidates"]
        run["discovery"] = {"videos": len(disc["contents"]), "creators": len(candidates), "visual_asset": disc["visual_asset"], "query": disc["text_query"]}
        logline(f"discovery: {len(candidates)} creators from {len(disc['contents'])} videos")
        if not candidates:
            run["shortlist"] = []
            run["status"] = "done"
            run["summary"] = "No creators matched the brief. Widen the region, lower the follower floor, or simplify the keywords."
            _finish(run, client, llm, t0)
            return run
        _save(run)

        # 3. profiles (full) for the top pool
        top_k = int(form.get("vet_top_k") or settings.SCOUT_VET_TOP_K)
        pool = candidates[: max(top_k * 3, 12)]
        profiles = fetch_profiles(client, [c["profileId"] for c in pool], log=logline)

        # 4. vetting for the top K
        per_creator = int(form.get("videos_per_creator") or settings.SCOUT_VET_VIDEOS_PER_CREATOR)
        vetted: dict[str, dict[str, Any]] = {}
        for c in candidates[:top_k]:
            try:
                videos = fetch_recent_videos(client, c["profileId"], limit=per_creator, log=logline)
                vetted[c["profileId"]] = vet_creator(c, profiles.get(c["profileId"]), videos, brief)
                fl = vetted[c["profileId"]]["flag_counts"]
                logline(f"vetting @{c['handle']}: {len(videos)} videos, flags={fl or 'none'}, sponsored={vetted[c['profileId']]['sponsored_posts']}")
            except OrianeBudgetExceeded as exc:
                logline(f"vetting stopped: {exc}")
                break
            except OrianeCreditsExhausted as exc:
                logline(f"vetting stopped: {exc}")
                run["warnings"] = (run.get("warnings") or []) + ["Oriane credits exhausted during vetting (402)"]
                break

        # 5. scoring
        shortlist = []
        for c in pool:
            vet = vetted.get(c["profileId"])
            prof = profiles.get(c["profileId"])
            sc = score_creator(c, vet, prof, brief, pool)
            shortlist.append({"candidate": c, "profile": _slim_profile(prof), "vetting": vet, "score": sc})
        shortlist.sort(key=lambda r: (r["score"]["vetted"], r["score"]["total"]), reverse=True)
        run["shortlist"] = shortlist[: max(top_k, 8)]
        _save(run)

        # 6. LLM judgment on the vetted ones (optional, degrades gracefully)
        if form.get("use_llm", True):
            n_judged = 0
            rows = [row for row in run["shortlist"] if row["vetting"]]
            logline(f"LLM judgment: {len(rows)} vetted creators, in parallel")
            with ThreadPoolExecutor(max_workers=min(4, max(1, len(rows)))) as pool_exec:
                for row, j in zip(rows, pool_exec.map(lambda r: judge(llm, brief, r), rows)):
                    if j:
                        row["judgment"] = j
                        n_judged += 1
            logline(f"LLM judgment ({llm.describe()}): {n_judged}/{len(rows)} creators")
            if n_judged:
                blend_judgments(run["shortlist"])
                run["shortlist"].sort(key=lambda r: (r["score"]["vetted"], r["score"]["total"]), reverse=True)
                logline("ranking blended: 60% evidence score + 40% AI fit for judged creators")

        run["summary"] = summarize(brief, run["shortlist"])
        run["status"] = "done"
    except OrianeCreditsExhausted as exc:
        run["status"] = "error"
        run["error"] = f"Oriane credits exhausted (402): {exc}"
        logline(run["error"])
    except OrianeError as exc:
        run["status"] = "error"
        run["error"] = f"Oriane API error: {exc}"
        logline(run["error"])
    except Exception as exc:  # noqa: BLE001
        run["status"] = "error"
        run["error"] = f"{type(exc).__name__}: {exc}"
        run["traceback"] = traceback.format_exc()
        logline(run["error"])
    _finish(run, client, llm, t0)
    return run


def execute_creator(run: dict[str, Any], form: dict[str, Any], client: OrianeClient | None = None, llm: LLM | None = None) -> dict[str, Any]:
    """@handle -> Brand-Readiness Report (scout.creator)."""
    t0 = time.perf_counter()

    def logline(msg: str) -> None:
        stamp = f"{time.perf_counter() - t0:6.1f}s"
        run["log"].append(f"[{stamp}] {msg}")
        log.info("%s %s", run["id"], msg)

    client = client or OrianeClient()
    llm = llm or LLM()
    run["status"] = "running"
    run["kind"] = "creator"
    try:
        report = creator_report(client, form, llm, log=logline)
        run["report"] = report
        if report.get("error"):
            run["status"] = "error"
            run["error"] = report["error"]
            logline(run["error"])
        else:
            sc = report["score"]
            run["summary"] = (f"@{report['profile'].get('handle')} · readiness {sc['total']} ({sc['grade']}) · {len(report.get('market') or [])} brands buying in your niche · "
                              f"{len((report.get('plan') or {}).get('fix_before_pitching') or [])} thing(s) to fix before pitching")
            run["status"] = "done"
    except OrianeCreditsExhausted as exc:
        run["status"] = "error"; run["error"] = f"Oriane credits exhausted (402): {exc}"; logline(run["error"])
    except OrianeError as exc:
        run["status"] = "error"; run["error"] = f"Oriane API error: {exc}"; logline(run["error"])
    except Exception as exc:  # noqa: BLE001
        run["status"] = "error"; run["error"] = f"{type(exc).__name__}: {exc}"; run["traceback"] = traceback.format_exc(); logline(run["error"])
    _finish(run, client, llm, t0)
    return run


def _finish(run: dict[str, Any], client: OrianeClient, llm: LLM, t0: float) -> None:
    run["stats"] = {"oriane": client.stats.as_dict(), "llm": llm.describe(), "llm_last_error": llm.last_error, "seconds": round(time.perf_counter() - t0, 1)}
    run["finished"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _save(run)


def _slim_profile(p: dict[str, Any] | None) -> dict[str, Any] | None:
    if not p:
        return None
    return {k: p.get(k) for k in ("id", "platform", "handle", "displayName", "bio", "bioLink", "language", "isVerified", "isPrivate", "postsCount", "followersCount", "followingCount", "likesCount", "profilePictureUrl", "publicEmail", "locationCompleteAddress", "locationLatitude", "locationLongitude")}


def judge(llm: LLM, brief: Brief, row: dict[str, Any]) -> dict[str, Any] | None:
    c, v, p = row["candidate"], row["vetting"], row.get("profile") or {}
    evidence = {
        "handle": c.get("handle"), "platform": c.get("platform"), "followers": p.get("followersCount") or c.get("followers"), "bio": p.get("bio"), "verified": p.get("isVerified"),
        "matching_videos": c.get("matching_videos"), "top_captions": [t.get("caption") for t in c.get("top_videos") or []],
        "hooks": [h.get("hook") for h in v.get("hooks") or []], "flags": [{k: f.get(k) for k in ("type", "term", "quote", "t")} for f in v.get("flags") or []][:8],
        "sponsored_partners": v.get("sponsored_partners"), "language_mix": v.get("language_mix"), "cadence_per_week": v.get("cadence_per_week"),
        "authenticity_notes": v.get("authenticity_notes"), "top_comments": [t.get("content") for t in v.get("top_comments") or []],
        "transcript_excerpts": [e.get("transcript_excerpt") for e in v.get("evidence_videos") or []][:4],
        "score": row["score"],
    }
    system = (
        "You are the head of influencer casting at a GCC agency. Judge ONE creator for ONE brief using ONLY the evidence given (never invent facts). "
        "Return STRICT JSON: fit_summary (2 sentences, specific), fit_score (0-100 integer), tone_match (low|medium|high), recommended_angle (1 sentence: the collaboration format you would brief), "
        "best_hook (verbatim from evidence or empty), risks (array of short strings, may be empty), why_not (1 sentence: the strongest reason to skip, or empty)."
    )
    user = f"BRIEF: {json.dumps({k: brief.as_dict()[k] for k in ('brand', 'category', 'tone', 'audience', 'competitors', 'avoid_topics', 'region', 'languages')}, ensure_ascii=False)}\n\nEVIDENCE: {json.dumps(evidence, ensure_ascii=False)[:9000]}"
    out = llm.json(system, user, max_tokens=700)
    if not isinstance(out, dict):
        return None
    return {k: out.get(k) for k in ("fit_summary", "fit_score", "tone_match", "recommended_angle", "best_hook", "risks", "why_not")}


def blend_judgments(shortlist: list[dict[str, Any]]) -> None:
    """The judge read the evidence; its fit score moves the ranking, transparently.
    total = 0.6 * heuristic + 0.4 * ai_fit; caps stay in force; the heuristic is kept."""
    for row in shortlist:
        j = row.get("judgment") or {}
        sc = row["score"]
        try:
            fit = float(j.get("fit_score"))
        except (TypeError, ValueError):
            continue
        fit = max(0.0, min(100.0, fit))
        sc.setdefault("heuristic", sc["total"])
        total = 0.6 * sc["heuristic"] + 0.4 * fit
        for cap in sc.get("caps") or []:
            if "competitor" in cap:
                total = min(total, 69.0)
            elif "high-severity" in cap:
                total = min(total, 59.0)
            elif "medium-severity" in cap:
                total = min(total, 79.0)
        sc["ai_fit"] = round(fit, 1)
        sc["total"] = round(total, 1)
        sc["grade"] = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"


def summarize(brief: Brief, shortlist: list[dict[str, Any]]) -> str:
    vetted = [r for r in shortlist if r["vetting"]]
    clean = [r for r in vetted if not r["vetting"]["flags"]]
    flagged = [r for r in vetted if r["vetting"]["flags"]]
    top = shortlist[0] if shortlist else None
    parts = [f"{len(shortlist)} creators shortlisted for {brief.brand or brief.category or 'the brief'} in {brief.region.upper()}; {len(vetted)} vetted on recent videos, {len(clean)} clean, {len(flagged)} with flags."]
    if top:
        parts.append(f"Top pick @{top['candidate']['handle']} ({top['candidate']['platform']}, {(top.get('profile') or {}).get('followersCount') or top['candidate'].get('followers') or 0:,} followers) scored {top['score']['total']} ({top['score']['grade']}).")
    return " ".join(parts)
