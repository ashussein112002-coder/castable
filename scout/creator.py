"""Creator mode: @handle -> Brand-Readiness Report.

The same Oriane surface as the brand side, pointed the other way:

  1. profile     profiles/search handle.exactMatch (full)         -> who you are on the index
  2. my videos   contents/search profileId (full, recent)         -> what you actually say and show
  3. self-audit  vet_creator() on your own videos                 -> flags with timestamps, hooks,
                                                                     sponsors, cadence, languages
  4. topics      transcript + caption keywords (LLM-named niche)  -> the search intent for peers
  5. peers       discover(): transcript/caption intent + visual   -> creators the algorithm puts
                 similarity from your best thumbnail, same geo,       next to you
                 follower band around yours
  6. market      vet_creator() on the top peers                   -> which brands are buying in
                                                                     your niche, with the receipts
  7. benchmark   your ER / views-per-follower vs the peer pool    -> percentiles
  8. score       readiness 0-100, transparent components
  9. pitch       LLM (optional): 3 brands to pitch + angles + fixes; deterministic fallback

Every number links to a video. Nothing here is invented: if a step yields nothing,
the report says so.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from typing import Any

from .brief import Brief
from .discover import discover
from .llm import LLM
from .oriane import OrianeBudgetExceeded, OrianeClient, OrianeCreditsExhausted
from .scoring import _pct_rank
from .vetting import fetch_recent_videos, vet_creator, video_link

STOP = set("""a an and are as at be by for from has have i in is it its of on or that the this to was we were will with you your
me my our us they them their he she his her not no yes so if but just like really very can do did does about into than then there
here what when where which who why how all any more most some such only own same too also new get got make made one two three
today day days week video videos guys hi hello hey ok okay let lets go going come came see look looks watch this thing things
honestly best part good great love loved amazing literally actually thing everyone everything something nothing because still
after before first last next much many little lot bit way ways used use using know think feel felt want wants need needs
scrolling stop wait pov changed obsessed viral follow comment share link bio code discount check tap swipe watch until end
""".split())
LANG_NAMES = {"en": "English", "ar": "Arabic", "es": "Spanish", "fr": "French", "hi": "Hindi", "ur": "Urdu", "tr": "Turkish", "ru": "Russian", "de": "German", "it": "Italian", "pt": "Portuguese", "tl": "Filipino", "id": "Indonesian", "fa": "Persian"}
STOP_AR = set("في من على إلى عن مع هذا هذه ذلك التي الذي أن إن كان كانت هو هي هم أنا نحن أنت لكن أو و يا ما لا نعم كل بعد قبل عند حتى".split())
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}|[؀-ۿ]{3,}")


def _words(text: str) -> list[str]:
    out = []
    for w in WORD_RE.findall(text or ""):
        lw = w.lower()
        if lw in STOP or lw in STOP_AR or lw.startswith("http"):
            continue
        out.append(lw)
    return out


def topics_from_videos(videos: list[dict[str, Any]], n: int = 14) -> list[dict[str, Any]]:
    """Top terms across transcripts + captions + hashtags, with how many videos carry each."""
    per_video: list[set[str]] = []
    total = Counter()
    for v in videos:
        bag = set(_words((v.get("transcript") or "") + " " + (v.get("caption") or "")))
        bag |= {("#" + h.lstrip("#").lower()) for h in (v.get("hashtags") or [])}
        per_video.append(bag)
        total.update(bag)
    tagged = {t.lstrip("#") for t in total if t.startswith("#")}
    rows = [{"term": t, "videos": c, "share": round(c / max(len(videos), 1), 2)} for t, c in total.most_common(80) if not (not t.startswith("#") and t in tagged)]
    # hashtags first (the creator's own labels), then the most repeated spoken/written terms
    rows.sort(key=lambda r: (r["videos"], r["term"].startswith("#"), len(r["term"])), reverse=True)
    return rows[:n]


def _band_around(followers: int | None) -> tuple[int, int]:
    f = int(followers or 20_000)
    return max(1_000, int(f * 0.3)), max(5_000, int(f * 3))


def find_profile(client: OrianeClient, handle: str, platforms: list[str], log=print) -> dict[str, Any] | None:
    h = handle.strip().lstrip("@").lower()
    query = {"operator": "and", "filters": {"handle": {"exactMatch": {"values": [h]}}}}
    if platforms:
        query["filters"]["platform"] = {"includes": platforms}
    payload = client.search_profiles(query, sort="followersCount:desc", limit=5, projection="full")
    data = payload.get("data")
    rows = data if isinstance(data, list) else (data or {}).get("results") or []
    rows = [r for r in rows if (r.get("handle") or "").lower() == h] or rows
    if not rows:
        log(f"profile: @{h} is not in the index for {', '.join(platforms) or 'any platform'}")
        return None
    rows.sort(key=lambda r: r.get("followersCount") or 0, reverse=True)
    p = rows[0]
    log(f"profile: @{p.get('handle')} on {p.get('platform')} · {int(p.get('followersCount') or 0):,} followers · {'verified' if p.get('isVerified') else 'not verified'}")
    return p


def benchmark(me: dict[str, Any], peers: list[dict[str, Any]]) -> dict[str, Any]:
    er_pool = [c.get("er_views_mean") or 0 for c in peers]
    vf_pool = [((c.get("views_max") or 0) / (c.get("followers") or 1)) for c in peers if c.get("followers")]
    my_er = me.get("er_views_median") or 0
    my_vf = me.get("views_per_follower_median") or 0
    return {
        "peers": len(peers),
        "er_views_median": my_er,
        "er_percentile": round(_pct_rank(my_er, er_pool)) if er_pool else None,
        "peer_er_median": round(sorted(er_pool)[len(er_pool) // 2], 4) if er_pool else None,
        "views_per_follower_median": my_vf,
        "views_per_follower_percentile": round(_pct_rank(my_vf, vf_pool)) if vf_pool else None,
    }


def market_from_peers(peer_vets: dict[str, dict[str, Any]], peers_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Brands seen in sponsored posts across peers, with one receipt per (brand, peer)."""
    brands: dict[str, dict[str, Any]] = {}
    for pid, vet in peer_vets.items():
        peer = peers_by_id.get(pid) or {}
        for name, count in vet.get("sponsored_partners") or []:
            if not name or name.startswith("("):
                continue
            row = brands.setdefault(name, {"brand": name, "sponsored_posts": 0, "creators": 0, "receipts": []})
            row["sponsored_posts"] += int(count)
            row["creators"] += 1
            ev = next((e for e in vet.get("evidence_videos") or [] if name in ((e.get("caption") or "").lower())), None) or ((vet.get("evidence_videos") or [None])[0])
            if ev:
                row["receipts"].append({"handle": peer.get("handle"), "platform": peer.get("platform"), "followers": peer.get("followers"), "caption": ev.get("caption"), "link": ev.get("link"), "published": ev.get("published"), "views": ev.get("views"), "er_views": ev.get("er_views")})
    out = sorted(brands.values(), key=lambda r: (r["creators"], r["sponsored_posts"]), reverse=True)
    return out[:12]


def readiness(me: dict[str, Any], profile: dict[str, Any], bench: dict[str, Any], market: list[dict[str, Any]], topics: list[dict[str, Any]]) -> dict[str, Any]:
    """0-100, four transparent components. Weights are explicit; caps are named."""
    # consistency: cadence and recency
    cad = me.get("cadence_per_week") or 0
    last = me.get("last_post_days_ago")
    consistency = min(100.0, 40 + 30 * min(cad, 2.0))  # 2+/week -> 100
    if last is not None and last > 30:
        consistency -= min(40, (last - 30))
    consistency = max(0.0, consistency)
    # engagement: percentile vs peers, blended with views/follower percentile
    erp = bench.get("er_percentile")
    vfp = bench.get("views_per_follower_percentile")
    engagement = 50.0 if erp is None else 0.7 * erp + 0.3 * (vfp if vfp is not None else erp)
    # safety: 100 minus penalties (self-audit)
    safety = 100.0
    worst = None
    for f in me.get("flags") or []:
        sev = f.get("severity")
        safety -= {"high": 35, "medium": 12, "low": 5}.get(sev, 5)
        if sev == "high" or (sev == "medium" and worst != "high"):
            worst = sev
    safety = max(0.0, safety)
    # market fit: is there a paying market next to you, and do you already have sponsor history?
    market_fit = 30.0 + min(50.0, 12.0 * len(market)) + (20.0 if (me.get("sponsored_posts") or 0) > 0 else 0.0)
    market_fit = min(100.0, market_fit)
    weights = {"consistency": 0.2, "engagement": 0.3, "safety": 0.3, "market_fit": 0.2}
    comps = {"consistency": round(consistency, 1), "engagement": round(engagement, 1), "safety": round(safety, 1), "market_fit": round(market_fit, 1)}
    total = sum(weights[k] * comps[k] for k in weights)
    caps = []
    if worst == "high":
        total = min(total, 59.0)
        caps.append("high-severity brand-safety flag (capped at 59)")
    elif worst == "medium":
        total = min(total, 79.0)
        caps.append("medium-severity brand-safety flag (capped at 79)")
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"
    return {"total": round(total, 1), "grade": grade, "components": comps, "weights": weights, "caps": caps}


def pitch_plan(llm: LLM, profile: dict[str, Any], me: dict[str, Any], topics: list[dict[str, Any]], market: list[dict[str, Any]], bench: dict[str, Any]) -> dict[str, Any] | None:
    evidence = {
        "handle": profile.get("handle"), "platform": profile.get("platform"), "followers": profile.get("followersCount"), "bio": profile.get("bio"), "verified": profile.get("isVerified"),
        "topics": [t["term"] for t in topics[:14]], "language_mix": me.get("language_mix"), "cadence_per_week": me.get("cadence_per_week"),
        "hooks": [h.get("hook") for h in (me.get("hooks") or [])[:5]], "sponsored_partners": me.get("sponsored_partners"),
        "flags": [{k: f.get(k) for k in ("type", "term", "quote", "t")} for f in (me.get("flags") or [])[:8]],
        "benchmark": bench, "brands_buying_in_niche": [{"brand": m["brand"], "creators": m["creators"], "sponsored_posts": m["sponsored_posts"], "example_caption": (m["receipts"][0].get("caption") if m.get("receipts") else None)} for m in market[:8]],
        "top_comments": [c.get("content") for c in (me.get("top_comments") or [])[:6]],
    }
    system = (
        "You are a creator-economy talent manager in the GCC. Using ONLY the evidence given (never invent brands, numbers or quotes), "
        "coach ONE creator on getting brand deals. Return STRICT JSON with keys: niche (3-6 words naming what they actually make), "
        "positioning (2 sentences a brand manager would read), fix_before_pitching (array of <=4 short, concrete actions tied to the evidence; empty if clean), "
        "pitches (array of up to 3 objects {brand, why_fit, angle, subject_line, opener} — brand must come from brands_buying_in_niche or sponsored_partners; "
        "angle = the collaboration format in one sentence; opener = first 2 sentences of the outreach message, first person, no dashes), "
        "media_kit_line (one line, first person, with the two strongest numbers from benchmark/evidence), rate_hint (string: a cautious range logic in words, not a number, or empty)."
    )
    import json as _json
    out = llm.json(system, "EVIDENCE: " + _json.dumps(evidence, ensure_ascii=False)[:9000], max_tokens=1100)
    if not isinstance(out, dict):
        return None
    return {k: out.get(k) for k in ("niche", "positioning", "fix_before_pitching", "pitches", "media_kit_line", "rate_hint")}


def fallback_plan(profile: dict[str, Any], me: dict[str, Any], topics: list[dict[str, Any]], market: list[dict[str, Any]], bench: dict[str, Any]) -> dict[str, Any]:
    """No LLM available: a plan written from the evidence with fixed, honest sentences.
    Every number here is measured; nothing is invented. Brands come only from peers' sponsored posts."""
    handle = profile.get("handle") or "creator"
    followers = int(profile.get("followersCount") or 0)
    words = [t["term"].lstrip("#") for t in topics if not t["term"].startswith("#")][:3] or [t["term"].lstrip("#") for t in topics[:3]]
    niche = ", ".join(words) if words else "your niche"
    er = (me.get("er_views_median") or 0) * 100
    erp = bench.get("er_percentile")
    cad = me.get("cadence_per_week") or 0
    langs = me.get("language_mix") or {}
    lang_txt = " and ".join(LANG_NAMES.get(k, str(k).upper()) for k in sorted(langs, key=langs.get, reverse=True)[:2] if k and k != "?") if langs else ""
    hooks = [h.get("hook") for h in (me.get("hooks") or []) if h.get("hook")]
    sponsors = [n for n, _ in (me.get("sponsored_partners") or []) if n and not str(n).startswith("(")]

    fixes = []
    for f in (me.get("flags") or [])[:4]:
        when = (f.get("published") or "")[:10]
        t = f.get("t")
        stamp = f" at {int(t // 60):02d}:{int(t % 60):02d}" if isinstance(t, (int, float)) else ""
        fixes.append(f"Archive or re-cut the video from {when}{stamp}: \u201c{(f.get('quote') or '')[:90]}\u201d reads as {str(f.get('type') or 'risk').replace('_', ' ')} to a brand's safety check")
    if cad < 1:
        fixes.append(f"You post {cad:.1f} times a week; brands read cadence as reliability. Hold 2 posts a week for 4 weeks before pitching")
    if (me.get("last_post_days_ago") or 0) > 21:
        fixes.append(f"Your last post is {int(me.get('last_post_days_ago'))} days old; post before you pitch so the first thing a brand sees is fresh")
    if me.get("audio_copyrighted_share") and me["audio_copyrighted_share"] > 0.6:
        fixes.append("Most of your recent videos use copyrighted audio; sponsored content usually needs licensed or original sound")
    if (me.get("sponsored_posts") or 0) == 0:
        fixes.append("No disclosed brand work yet: do one gifted collaboration with #ad so brands can see how you present a product")

    pitches = []
    for m in market[:3]:
        r = (m.get("receipts") or [{}])[0]
        peer = r.get("handle")
        why = f"{m['creators']} creator(s) the index puts next to you posted {m['sponsored_posts']} sponsored video(s) with {m['brand']}" + (f"; the latest one, from @{peer}, is linked in your report" if peer else "")
        hook = hooks[0] if hooks else None
        angle = (f"Your usual {words[0]} format with the product in the first five seconds, opened the way your best hook opens: \u201c{hook[:70]}\u2026\u201d" if hook and words else "One video in your usual format, product in the first five seconds, your own hook style")
        opener = (f"I make {niche} videos for {followers:,} people" + (f", mostly in {lang_txt}" if lang_txt else "") + f". I saw your work with @{peer} and my audience is the same room, one seat over." if peer else f"I make {niche} videos for {followers:,} people. Creators in my niche are already working with {m['brand']} and my audience asks me about it.")
        pitches.append({"brand": m["brand"], "why_fit": why, "angle": angle, "subject_line": f"{m['brand']} \u00d7 @{handle}: {niche} for an audience that already buys", "opener": opener})

    positioning = f"@{handle} makes {niche} content for {followers:,} followers" + (f", mostly in {lang_txt}" if lang_txt else "") + f". Engagement per view {er:.1f}%" + (f", in the top {max(1, 100 - int(erp))}% of {bench.get('peers', 0)} comparable creators" if erp is not None else "") + f". {len(sponsors)} disclosed brand partner(s) in the last {me.get('window_days', 180)} days" + (": " + ", ".join(sponsors[:3]) if sponsors else "") + "."
    media_kit = f"@{handle} \u00b7 {followers:,} followers \u00b7 {er:.1f}% engagement per view" + (f" \u00b7 top {max(1, 100 - int(erp))}% of peers" if erp is not None else "") + (f" \u00b7 {cad:.1f} posts/week" if cad else "")
    rate = ("Price on engagement quality, not follower count: your ER per view is above the peer median." if (erp is not None and erp >= 50) else "Price conservatively until cadence and engagement are above the peer median; lead with the receipts, not the rate.")
    return {"niche": niche, "positioning": positioning, "fix_before_pitching": fixes, "pitches": pitches, "media_kit_line": media_kit, "rate_hint": rate}


def creator_report(client: OrianeClient, form: dict[str, Any], llm: LLM, log=print) -> dict[str, Any]:
    """The whole creator flow. Returns the report dict (also embedded in the run record)."""
    handle = (form.get("handle") or "").strip().lstrip("@")
    platforms = [p for p in (form.get("platforms") or ["instagram", "tiktok"]) if p in ("instagram", "tiktok")] or ["instagram", "tiktok"]
    region = (form.get("region") or "uae").lower()
    videos_n = int(form.get("videos_n") or 12)
    peers_n = int(form.get("peers_n") or 6)
    peer_videos_n = int(form.get("peer_videos_n") or 8)
    report: dict[str, Any] = {"kind": "creator", "handle": handle, "platforms": platforms, "region": region}

    profile = find_profile(client, handle, platforms, log=log)
    if not profile:
        report["error"] = f"@{handle} is not indexed on {', '.join(platforms)} yet"
        return report
    report["profile"] = profile
    pid = profile["id"]

    videos = fetch_recent_videos(client, pid, limit=videos_n, log=log)
    report["videos_checked"] = len(videos)
    if not videos:
        report["error"] = "no recent videos in the index for this profile"
        return report

    topics = topics_from_videos(videos)
    report["topics"] = topics
    log(f"topics: {', '.join(t['term'] for t in topics[:8])}")

    # the self-audit uses the creator's own niche words as "keywords" and no competitors
    niche_hint = (form.get("niche") or "").strip()
    brief = Brief.from_form({"text": niche_hint or profile.get("bio") or "", "region": region, "platforms": platforms, "keywords": ", ".join(t["term"] for t in topics[:10] if not t["term"].startswith("#")), "follower_band": "any"})
    lo, hi = _band_around(profile.get("followersCount"))
    brief.followers_min, brief.followers_max = lo, hi
    brief.hashtags = [t["term"].lstrip("#") for t in topics if t["term"].startswith("#")][:8]
    if form.get("use_llm", True):
        brief.enrich(llm)
        log(f"niche enriched by LLM ({llm.describe()}): {len(brief.keywords)} keywords")
    me_candidate = {"profileId": pid, "handle": profile.get("handle"), "platform": profile.get("platform"), "followers": profile.get("followersCount"), "matching_videos": len(videos), "matched_queries": {}, "visual_best_rank": None, "er_views_mean": 0, "views_max": max((v.get("viewsCount") or 0) for v in videos)}
    me = vet_creator(me_candidate, profile, videos, brief)
    report["self_audit"] = me
    log(f"self-audit: {len(me['flags'])} flag(s), {me['sponsored_posts']} sponsored post(s), cadence {me['cadence_per_week']}/week, languages {me['language_mix']}")

    # peers: same intent + the creator's own best thumbnail as the visual anchor
    best = max(videos, key=lambda v: v.get("viewsCount") or 0)
    if best.get("thumbnailMediaUrl"):
        brief.image_url = best["thumbnailMediaUrl"]
    try:
        disc = discover(client, brief, limit=int(form.get("discovery_limit") or 40), log=log)
    except (OrianeBudgetExceeded, OrianeCreditsExhausted) as exc:
        log(f"peers: stopped ({exc})")
        disc = {"candidates": [], "contents": [], "visual_asset": None, "text_query": None}
    peers = [c for c in disc["candidates"] if c.get("profileId") != pid and (c.get("handle") or "").lower() != (profile.get("handle") or "").lower()]
    if not peers:
        # widen the net once: any follower count, whole region family, hashtags only as extra intent
        log("peers: none in your follower band and area — widening (any followers, no geo)")
        brief.followers_min, brief.followers_max = 1_000, 50_000_000
        brief.region = "global"
        try:
            disc = discover(client, brief, limit=int(form.get("discovery_limit") or 40), log=log)
            peers = [c for c in disc["candidates"] if c.get("profileId") != pid and (c.get("handle") or "").lower() != (profile.get("handle") or "").lower()]
            report["peers_widened"] = True
        except (OrianeBudgetExceeded, OrianeCreditsExhausted) as exc:
            log(f"peers: stopped ({exc})")
    report["peers"] = peers[:20]
    report["discovery"] = {"videos": len(disc["contents"]), "creators": len(peers), "visual_asset": disc.get("visual_asset")}
    log(f"peers: {len(peers)} creators the index puts next to you")

    bench = benchmark(me, peers)
    report["benchmark"] = bench

    # market: sponsors among the top peers
    peer_vets: dict[str, dict[str, Any]] = {}
    peers_by_id = {c["profileId"]: c for c in peers}
    for c in peers[:peers_n]:
        try:
            pv = fetch_recent_videos(client, c["profileId"], limit=peer_videos_n, log=log)
            peer_vets[c["profileId"]] = vet_creator(c, None, pv, brief)
        except (OrianeBudgetExceeded, OrianeCreditsExhausted) as exc:
            log(f"market: stopped ({exc})")
            break
    market = market_from_peers(peer_vets, peers_by_id)
    report["market"] = market
    report["peer_sponsor_summary"] = {pid_: {"handle": (peers_by_id.get(pid_) or {}).get("handle"), "sponsored_posts": v.get("sponsored_posts"), "partners": v.get("sponsored_partners")} for pid_, v in peer_vets.items()}
    log(f"market: {len(market)} brand(s) buying from creators like you ({sum(m['sponsored_posts'] for m in market)} sponsored posts across {len(peer_vets)} peers)")

    report["score"] = readiness(me, profile, bench, market, topics)
    plan = pitch_plan(llm, profile, me, topics, market, bench) if form.get("use_llm", True) else None
    report["plan"] = plan or fallback_plan(profile, me, topics, market, bench)
    report["plan_source"] = llm.describe() if plan else "deterministic"
    log(f"plan: {len(report['plan'].get('pitches') or [])} pitch(es), {len(report['plan'].get('fix_before_pitching') or [])} fix(es) ({report['plan_source']})")
    report["generated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return report
