"""Discovery: brief -> candidate creators, using the Oriane index.

Two cheap searches (default projection) feed a per-creator aggregation:
  1. text intent  -> transcript / caption / hashtags fuzzy match (OR group)
  2. visual intent -> optional text/image asset -> visualSimilarity sort
Then one profiles/search (full projection) for the top candidates.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from .brief import Brief
from .geo import region_filter
from .oriane import OrianeClient


def build_text_query(brief: Brief) -> dict[str, Any]:
    base_filters: dict[str, Any] = {
        "platform": {"includes": brief.platforms},
        "format": {"includes": ["video"]},
        "publishedAt": {"after": (dt.date.today() - dt.timedelta(days=brief.days_back)).isoformat()},
        "profileFollowersCount": {"min": brief.followers_min, "max": brief.followers_max},
    }
    geo = region_filter(brief.region)
    if geo:
        base_filters["profileLocationCoordinates"] = geo
    sub: list[dict[str, Any]] = []
    if brief.keywords:
        sub.append({"name": "transcript", "operator": "and", "filters": {"transcript": {"includesFuzzy": {"values": brief.keywords[:14], "operator": "or"}}}})
        sub.append({"name": "caption", "operator": "and", "filters": {"caption": {"includesFuzzy": {"values": brief.keywords[:14], "operator": "or"}}}})
    if brief.hashtags:
        sub.append({"name": "hashtags", "operator": "and", "filters": {"hashtags": {"includesFuzzy": {"values": brief.hashtags[:10], "operator": "or"}}}})
    query: dict[str, Any] = {"operator": "and", "filters": base_filters}
    if sub:
        # depth: root -> one OR group -> named leaves (2 levels, the documented maximum)
        query["queries"] = [{"name": "intent", "operator": "or", "queries": sub}]
    return query


def build_visual_query(brief: Brief, asset_id: str, min_score: float = 0.25) -> dict[str, Any]:
    q = build_text_query(brief)
    q.pop("queries", None)  # visual search is a separate, wider net
    q["filters"]["visualSimilarity"] = {"includes": {"values": [{"assetId": asset_id, "minScore": min_score}]}}
    return q


def build_profile_query(brief: Brief, handle: str) -> dict[str, Any]:
    q = build_text_query(brief)
    q.pop("queries", None)
    q["filters"].pop("profileFollowersCount", None)
    q["filters"].pop("profileLocationCoordinates", None)
    q["filters"]["profileHandle"] = {"exactMatch": {"values": [handle.lstrip("@")]}}
    return q


def discover(client: OrianeClient, brief: Brief, *, limit: int = 100, log=print) -> dict[str, Any]:
    """Return {candidates: [...], contents: [...], aggregations: {...}, visual_asset: str|None}."""
    contents: dict[str, dict[str, Any]] = {}
    visual_rank: dict[str, int] = {}
    text_query = build_text_query(brief)
    log(f"discovery: text query over {len(brief.keywords)} keywords / {len(brief.hashtags)} hashtags, region={brief.region}, followers {brief.followers_min:,}-{brief.followers_max:,}")
    n_text = 0
    for item in client.iter_contents(text_query, sort="engagementRatePerViews:desc,viewsCount:desc", projection="default", want=limit):
        contents[item["id"]] = item
        n_text += 1
    log(f"discovery: {n_text} matching videos from text intent")

    visual_asset = None
    prompt = brief.visual_prompt or (f"{brief.category} {brief.brand}".strip() if brief.category else "")
    if brief.image_url or prompt:
        try:
            visual_asset = client.create_image_asset(brief.image_url) if brief.image_url else client.create_text_asset(prompt)
            log(f"discovery: visual asset {visual_asset} ({'image' if brief.image_url else 'text'})")
            n_vis = 0
            for rank, item in enumerate(client.iter_contents(build_visual_query(brief, visual_asset), sort="visualSimilarity:desc", projection="default", want=min(limit, 50))):
                contents.setdefault(item["id"], item)
                visual_rank[item["id"]] = rank + 1
                n_vis += 1
            log(f"discovery: {n_vis} videos from visual similarity")
        except Exception as exc:  # noqa: BLE001 - visual search is optional
            log(f"discovery: visual search skipped ({exc})")

    # ---- aggregate per creator ------------------------------------------------
    by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in contents.values():
        by_profile[c.get("profileId") or c.get("profileHandle")].append(c)
    candidates: list[dict[str, Any]] = []
    for pid, items in by_profile.items():
        items.sort(key=lambda x: (x.get("viewsCount") or 0), reverse=True)
        views = [x.get("viewsCount") or 0 for x in items]
        er_views = [x.get("engagementRatePerViews") or 0 for x in items]
        er_follow = [x.get("engagementRatePerFollowers") or 0 for x in items]
        matched = defaultdict(int)
        for x in items:
            for m in x.get("matchedQueries") or []:
                matched[m] += 1
        best = items[0]
        candidates.append({
            "profileId": pid,
            "handle": best.get("profileHandle"),
            "displayName": best.get("profileDisplayName"),
            "platform": best.get("platform"),
            "followers": best.get("profileFollowersCount"),
            "matching_videos": len(items),
            "matched_queries": dict(matched),
            "visual_best_rank": min([visual_rank[x["id"]] for x in items if x["id"] in visual_rank], default=None),
            "views_sum": sum(views),
            "views_max": max(views) if views else 0,
            "er_views_mean": round(sum(er_views) / len(er_views), 4) if er_views else 0,
            "er_followers_mean": round(sum(er_follow) / len(er_follow), 4) if er_follow else 0,
            "top_videos": [_slim(x) for x in items[:3]],
            "hashtags": _top_hashtags(items),
            "languages": _lang_mix(items),
        })
    candidates.sort(key=lambda c: (c["matching_videos"], c["er_views_mean"], c["views_sum"]), reverse=True)
    return {"candidates": candidates, "contents": list(contents.values()), "visual_asset": visual_asset, "text_query": text_query}


def fetch_profiles(client: OrianeClient, profile_ids: list[str], *, log=print) -> dict[str, dict[str, Any]]:
    """profiles/search by id, full projection, one page per 100 ids."""
    out: dict[str, dict[str, Any]] = {}
    ids = [p for p in profile_ids if p and str(p).startswith("prf_")]
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        payload = client.search_profiles({"operator": "and", "filters": {"id": {"includes": chunk}}}, sort="followersCount:desc", limit=len(chunk), projection="full")
        data = payload.get("data")
        rows = data if isinstance(data, list) else (data or {}).get("results") or []
        for p in rows:
            out[p["id"]] = p
    log(f"profiles: {len(out)}/{len(ids)} enriched")
    return out


def _slim(x: dict[str, Any]) -> dict[str, Any]:
    return {k: x.get(k) for k in ("id", "platform", "platformId", "profileHandle", "caption", "captionLanguage", "publishedAt", "thumbnailMediaUrl", "viewsCount", "likesCount", "commentsCount", "sharesCount", "engagementRatePerViews", "engagementRatePerFollowers", "duration", "hashtags", "matchedQueries")}


def _top_hashtags(items: list[dict[str, Any]], n: int = 8) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for x in items:
        for h in x.get("hashtags") or []:
            counts[str(h).lstrip("#").lower()] += 1
    return [h for h, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def _lang_mix(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for x in items:
        lang = x.get("captionLanguage") or "?"
        counts[lang] += 1
    return dict(counts)
