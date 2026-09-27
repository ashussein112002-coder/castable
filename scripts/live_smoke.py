"""Live smoke test against connect.oriane.xyz — spends ~5 result-credits, prints what the
pipeline depends on. Run the moment a key exists:

    ORIANE_API_KEY=... .venv/bin/python scripts/live_smoke.py

Exit 0 = the three endpoints answer and the fields the pipeline reads are present.
Anything missing is printed as MISSING (the pipeline degrades, but you want to know).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.oriane import OrianeClient, OrianeError  # noqa: E402

CONTENT_FIELDS = ["id", "platform", "platformId", "profileId", "profileHandle", "profileDisplayName", "profileFollowersCount", "caption", "captionLanguage",
                  "publishedAt", "viewsCount", "likesCount", "commentsCount", "engagementRatePerViews", "engagementRatePerFollowers", "thumbnailMediaUrl", "duration", "hashtags", "mentions"]
FULL_FIELDS = ["transcript", "transcriptLanguage", "transcriptChunks", "frames", "popularComments", "audioTitle", "audioAuthor", "audioCopyrighted", "matchedQueries"]
PROFILE_FIELDS = ["id", "platform", "handle", "displayName", "bio", "followersCount", "isVerified", "publicEmail", "locationCompleteAddress", "profilePictureUrl"]


def show(label: str, item: dict, fields: list[str]) -> int:
    missing = [f for f in fields if f not in item]
    present = [f for f in fields if f in item]
    print(f"\n[{label}] keys={len(item)}  present={len(present)}/{len(fields)}")
    for f in present[:40]:
        v = item[f]
        s = json.dumps(v, ensure_ascii=False)
        print(f"   {f:28} {s[:110]}")
    if missing:
        print("   MISSING:", ", ".join(missing))
    extra = [k for k in item if k not in fields][:30]
    if extra:
        print("   also present:", ", ".join(extra))
    return len(missing)


def main() -> int:
    if not os.environ.get("ORIANE_API_KEY"):
        print("ORIANE_API_KEY not set"); return 2
    c = OrianeClient(cache_ttl_s=0)
    t0 = time.perf_counter()
    try:
        style = c.detect_auth_style()
    except OrianeError as e:
        print("AUTH FAILED:", e.status, json.dumps(e.payload)[:400]); return 1
    print(f"auth style: {style}  ({(time.perf_counter() - t0) * 1000:.0f} ms)")

    miss = 0
    q = {"operator": "and", "filters": {"platform": {"includes": ["instagram", "tiktok"]}, "format": {"includes": ["video"]},
                                        "transcript": {"includesFuzzy": {"values": ["skincare", "outfit"], "operator": "or"}},
                                        "profileLocationCoordinates": {"includes": {"values": [{"minLatitude": 24.75, "maxLatitude": 25.4, "minLongitude": 54.85, "maxLongitude": 55.6}], "operator": "or"}}}}
    try:
        p = c.search_contents(q, sort="viewsCount:desc", limit=2, projection="default")
    except OrianeError as e:
        print("contents/search default FAILED:", e.status, json.dumps(e.payload)[:600]); return 1
    meta = p.get("metadata") or {}
    results = (p.get("data") or {}).get("results") or []
    print(f"contents/search default: {len(results)} results, totalCount={((meta.get('pagination') or {}).get('totalCount'))}, executionTime={meta.get('executionTime')}, metadata keys={list(meta)}")
    if not results:
        print("   no results for the Dubai geo-boxed query — retrying without geo")
        q["filters"].pop("profileLocationCoordinates", None)
        p = c.search_contents(q, sort="viewsCount:desc", limit=2, projection="default")
        results = (p.get("data") or {}).get("results") or []
        print(f"contents/search default (no geo): {len(results)} results")
    if not results:
        print("   still no results — check filters"); miss += 1
    else:
        miss += show("content default", results[0], CONTENT_FIELDS)
        pid = results[0].get("profileId")
        try:
            pf = c.search_contents({"operator": "and", "filters": {"profileId": {"includes": [pid]}, "format": {"includes": ["video"]}}}, sort="publishedAt:desc", limit=1, projection="full")
            fr = ((pf.get("data") or {}).get("results") or [{}])[0]
            miss += show("content FULL", fr, CONTENT_FIELDS + FULL_FIELDS)
            ch = fr.get("transcriptChunks") or []
            if ch:
                print("   transcriptChunks[0]:", json.dumps(ch[0], ensure_ascii=False)[:200])
            frs = fr.get("frames") or []
            if frs:
                print("   frames[0]:", json.dumps(frs[0], ensure_ascii=False)[:200])
            pc = fr.get("popularComments") or []
            if pc:
                print("   popularComments[0]:", json.dumps(pc[0], ensure_ascii=False)[:200])
        except OrianeError as e:
            print("contents/search FULL FAILED:", e.status, json.dumps(e.payload)[:600]); miss += 1
        try:
            pp = c.search_profiles({"operator": "and", "filters": {"id": {"includes": [pid]}}}, limit=1, projection="full")
            pdata = pp.get("data")
            prow = pdata if isinstance(pdata, list) else (pdata or {}).get("results") or []
            pr = (prow or [{}])[0]
            miss += show("profile FULL", pr, PROFILE_FIELDS)
        except OrianeError as e:
            print("profiles/search FAILED:", e.status, json.dumps(e.payload)[:600]); miss += 1
    try:
        aid = c.create_text_asset("a woman in an elegant modest outfit filming a try-on haul in a bright Dubai apartment")
        print(f"\nassets: text asset created {aid}")
        pv = c.search_contents({"operator": "and", "filters": {"platform": {"includes": ["instagram", "tiktok"]}, "visualSimilarity": {"includes": {"values": [{"assetId": aid, "minScore": 0.2}]}}}}, sort="visualSimilarity:desc", limit=1, projection="basic")
        vr = ((pv.get("data") or {}).get("results") or [])
        print(f"visual similarity search: {len(vr)} results; aiSearchAnchor={'yes' if ((pv.get('metadata') or {}).get('pagination') or {}).get('aiSearchAnchor') else 'no'}; first keys={list(vr[0])[:12] if vr else None}")
    except OrianeError as e:
        print("assets / visual search FAILED:", e.status, json.dumps(e.payload)[:600]); miss += 1
    print(f"\nstats: {c.stats.as_dict()}")
    print("RESULT:", "GREEN" if miss == 0 else f"AMBER ({miss} gaps) — pipeline degrades gracefully, read above")
    return 0 if miss == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
