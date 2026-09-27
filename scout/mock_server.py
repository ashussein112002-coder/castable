"""Mock of the Oriane Connect API for offline development and rehearsal.

Implements the verified surface (contents/search, profiles/search, assets)
over a deterministic synthetic index. Honours the filter grammar that Scout
uses, nested and/or queries with matchedQueries, sort, pagination and the
three projections. It is clearly synthetic: handles end in `.demo`.

Run:  uvicorn scout.mock_server:app --port 8791
Use:  ORIANE_BASE_URL=http://127.0.0.1:8791 ORIANE_API_KEY=demo ORIANE_AUTH_STYLE=bearer
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
import re
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Oriane mock")
RNG = random.Random(20260927)
NOW = dt.datetime(2026, 9, 27, 8, 0, tzinfo=dt.timezone.utc)

CITIES = {
    "Dubai": (25.20, 55.27), "Abu Dhabi": (24.45, 54.65), "Riyadh": (24.71, 46.68), "Jeddah": (21.54, 39.17),
    "Doha": (25.28, 51.53), "Kuwait City": (29.37, 47.98), "Cairo": (30.04, 31.24), "London": (51.51, -0.13), "Paris": (48.86, 2.35),
}
CATS = {
    "skincare": {"kw": ["skincare routine", "serum", "moisturizer", "glow", "sunscreen", "retinol"], "ar": ["روتين بشرة", "سيروم", "واقي شمس"], "tags": ["skincare", "glowup", "skintok", "dubaiskincare"]},
    "beauty": {"kw": ["makeup", "grwm", "get ready with me", "lipstick", "foundation"], "ar": ["مكياج", "جاهزة معي"], "tags": ["makeup", "grwm", "beautytok"]},
    "fashion": {"kw": ["outfit", "ootd", "styling", "haul", "lookbook"], "ar": ["لوك", "تنسيق", "أزياء"], "tags": ["ootd", "fashion", "dubaifashion", "haul"]},
    "modest": {"kw": ["modest fashion", "hijab style", "abaya", "modest outfit"], "ar": ["عباية", "حجاب", "محتشم"], "tags": ["modestfashion", "hijabstyle", "abaya"]},
    "luxury": {"kw": ["luxury", "designer bag", "unboxing", "haute couture"], "ar": ["فخامة", "ماركات"], "tags": ["luxury", "unboxing", "designer"]},
    "fitness": {"kw": ["workout", "gym", "training", "protein"], "ar": ["تمرين", "جيم"], "tags": ["gym", "fitness", "dubaifitness"]},
    "food": {"kw": ["recipe", "restaurant", "cafe", "brunch"], "ar": ["مطعم", "وصفة", "كافيه"], "tags": ["foodie", "dubaifood", "recipe"]},
}
COMPETITORS = ["La Mer", "Estee Lauder", "Dior", "Charlotte Tilbury", "The Ordinary", "Fenty", "Huda Beauty", "Zara", "Shein", "Sephora"]
BRANDS = ["sephora.me", "hudabeauty", "namshi", "ounass", "farfetch", "noon", "carrefouruae", "nike", "adidasmena", "dior", "lamer"]
RISK = ["casino", "vodka", "bet365", "vape"]
FIRST = ["Noor", "Sara", "Layla", "Maya", "Reem", "Dana", "Hana", "Lina", "Salma", "Yara", "Omar", "Khalid", "Zain", "Ali", "Rami", "Jude", "Mira", "Tala", "Lara", "Rania", "Amal", "Farah", "Nadia", "Aisha", "Mona", "Jana", "Sami", "Adam", "Ziad", "Tamer"]


def _id(prefix: str, seed: str) -> str:
    return prefix + "_" + hashlib.sha1(seed.encode()).hexdigest()[:28]


def _build() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    profiles, contents = [], []
    i = 0
    for city, (lat, lng) in CITIES.items():
        n = 8 if city in ("Dubai", "Riyadh") else 4
        for _ in range(n):
            i += 1
            cat = RNG.choice(list(CATS))
            name = RNG.choice(FIRST)
            platform = RNG.choice(["instagram", "tiktok", "instagram"])
            handle = f"{name.lower()}.{cat}{i}.demo"
            followers = int(RNG.choice([3_000, 12_000, 25_000, 48_000, 90_000, 150_000, 320_000, 700_000, 1_400_000]) * RNG.uniform(0.7, 1.3))
            ar_share = 0.75 if city not in ("London", "Paris") else 0.05
            pid = _id("prf", handle)
            profiles.append({
                "id": pid, "platform": platform, "handle": handle, "displayName": f"{name} {city[:1]}.", "bio": f"{cat} creator based in {city}. Collabs: {handle}@mail.demo", "bioLink": f"https://linktr.ee/{handle}",
                "language": "ar" if ar_share > 0.5 else "en", "isPrivate": False, "isVerified": followers > 300_000, "postsCount": RNG.randint(80, 900), "likesCount": followers * RNG.randint(5, 40),
                "followersCount": followers, "followingCount": RNG.randint(100, 1500), "platformId": str(RNG.randint(10**9, 10**10)), "profilePictureUrl": f"https://picsum.photos/seed/{handle}/200",
                "publicEmail": f"{handle}@mail.demo", "locationPlatformId": str(RNG.randint(10**6, 10**7)), "locationCompleteAddress": f"{city}", "locationLatitude": lat + RNG.uniform(-0.05, 0.05), "locationLongitude": lng + RNG.uniform(-0.05, 0.05),
                "createdAt": "2024-01-01T00:00:00.000Z", "updatedAt": NOW.isoformat().replace("+00:00", "Z"), "_cat": cat, "_ar": ar_share,
            })
            base_er = RNG.uniform(0.01, 0.12)
            for j in range(RNG.randint(7, 14)):
                days_ago = RNG.randint(1, 200)
                published = NOW - dt.timedelta(days=days_ago, hours=RNG.randint(0, 23))
                is_ar = RNG.random() < ar_share
                kw = RNG.sample(CATS[cat]["ar" if is_ar else "kw"], 2)
                comp = RNG.choice(COMPETITORS) if RNG.random() < 0.18 else None
                risk = RNG.choice(RISK) if RNG.random() < 0.08 else None
                sponsored = RNG.random() < 0.3
                brand = RNG.choice(BRANDS) if sponsored else None
                hook = RNG.choice(["Stop scrolling, this changed my skin", "POV: you finally found the one", "Nobody talks about this", "I tested it for 30 days", "Okay this is a Dubai secret", "وقفي وشوفي هذا", "ما حد يقولكم هالشي", "جربته ٣٠ يوم وهذي النتيجة"]) if RNG.random() < 0.8 else f"Hi guys, today {kw[0]}"
                transcript = f"{hook}. So this is my {kw[0]} and honestly the {kw[1]} is the best part." + (f" I used to use {comp} but this is better." if comp else "") + (f" Also we went to the {risk} after." if risk else "") + (" Use my code for 15 percent off." if sponsored else "")
                chunks, t = [], 0.0
                for sent in re.split(r"(?<=[\.\!\؟])\s+", transcript):
                    if not sent:
                        continue
                    d = max(1.2, len(sent.split()) * 0.45)
                    chunks.append({"startSeconds": round(t, 2), "endSeconds": round(t + d, 2), "text": sent})
                    t += d
                views = int(followers * RNG.uniform(0.1, 3.5))
                er = max(0.002, base_er * RNG.uniform(0.5, 1.6))
                likes = int(views * er * 0.85)
                comments = int(views * er * 0.06 * RNG.uniform(0.2, 2.5))
                shares = int(views * er * 0.09)
                tags = RNG.sample(CATS[cat]["tags"], 2) + (["ad", "sponsored"] if sponsored else [])
                mentions = [{"id": _id("prf", brand), "platformId": str(RNG.randint(10**8, 10**9)), "profileHandle": brand}] if brand else []
                cid = _id("cnt", f"{handle}-{j}")
                contents.append({
                    "id": cid, "matchedQueries": [], "platform": platform, "profileHandle": handle, "profileDisplayName": f"{name} {city[:1]}.", "format": "video", "caption": f"{kw[0]} {'#' + ' #'.join(tags)}" + (f" @{brand}" if brand else ""), "captionLanguage": "ar" if is_ar else "en",
                    "thumbnailMediaId": _id("med", cid), "publishedAt": published.isoformat().replace("+00:00", "Z"), "profileId": pid, "thumbnailMediaUrl": f"https://picsum.photos/seed/{cid}/360/640",
                    "viewsCount": views, "likesCount": likes, "sharesCount": shares, "commentsCount": comments, "interactionsCount": likes + shares + comments, "engagementRatePerViews": round((likes + shares + comments) / max(views, 1), 4),
                    "engagementRatePerFollowers": round((likes + shares + comments) / max(followers, 1), 4), "profileFollowersCount": followers, "profileFollowingCount": 300, "profilePostsCount": 300, "mediaCount": 1, "duration": round(t + 1, 1), "hashtags": ["#" + x for x in tags], "coAuthors": [], "mentions": mentions,
                    "platformId": str(RNG.randint(7_000_000_000_000_000_000, 7_400_000_000_000_000_000)), "profilePlatformId": str(RNG.randint(10**9, 10**10)), "profilePictureUrl": f"https://picsum.photos/seed/{handle}/200", "profileBio": f"{cat} creator based in {city}", "profileVerified": followers > 300_000,
                    "locationPlatformId": None, "locationCompleteAddress": city, "locationLatitude": lat, "locationLongitude": lng, "profileLocationPlatformId": None, "profileLocationCompleteAddress": city, "profileLocationLatitude": lat, "profileLocationLongitude": lng,
                    "transcript": transcript, "transcriptLanguage": "ar" if is_ar else "en", "transcriptChunks": chunks,
                    "frames": [{"id": _id("med", f"{cid}-f{k}"), "position": k, "timestampSeconds": k * 2.0, "visualSimilarityScore": round(RNG.uniform(0.2, 0.9), 2), "url": f"https://picsum.photos/seed/{cid}{k}/270/480"} for k in range(1, 4)],
                    "audioPlatformId": str(RNG.randint(10**8, 10**9)), "audioTitle": RNG.choice(["Original sound", "Espresso", "Die With A Smile", "Habibi"]), "audioAuthor": RNG.choice([handle, "Sabrina Carpenter", "Bruno Mars", "DJ Khaled"]), "audioType": RNG.choice(["original", "licensed_music"]), "audioCopyrighted": RNG.random() < 0.4,
                    "popularComments": [{"platformId": str(RNG.randint(10**9, 10**10)), "profilePlatformId": "1", "profileHandle": RNG.choice(FIRST).lower(), "content": RNG.choice(["Where is this from?!", "Obsessed 😍", "link please", "ما شاء الله", "This is so overrated", "Is it available in Riyadh?"]), "likesCount": RNG.randint(5, 900), "repliesCount": RNG.randint(0, 20), "publishedAt": published.isoformat().replace("+00:00", "Z"), "createdAt": published.isoformat().replace("+00:00", "Z"), "updatedAt": published.isoformat().replace("+00:00", "Z")} for _ in range(3)],
                    "createdAt": published.isoformat().replace("+00:00", "Z"), "updatedAt": NOW.isoformat().replace("+00:00", "Z"),
                })
    return profiles, contents


PROFILES, CONTENTS = _build()
ASSETS: dict[str, dict[str, Any]] = {}

BASIC_C = ["id", "matchedQueries", "platform", "profileHandle", "profileDisplayName", "format", "caption", "captionLanguage", "thumbnailMediaId", "publishedAt"]
DEFAULT_C = BASIC_C + ["profileId", "thumbnailMediaUrl", "viewsCount", "likesCount", "sharesCount", "commentsCount", "interactionsCount", "engagementRatePerViews", "engagementRatePerFollowers", "profileFollowersCount", "profileFollowingCount", "profilePostsCount", "mediaCount", "duration", "hashtags", "coAuthors", "mentions"]
BASIC_P = ["id", "platform", "handle", "displayName", "bio", "bioLink", "language", "isPrivate", "isVerified"]
DEFAULT_P = BASIC_P + ["postsCount", "likesCount", "followersCount", "followingCount"]


def _auth_ok(authorization: str | None, x_api_key: str | None) -> bool:
    return bool((authorization and authorization.startswith("Bearer ")) or x_api_key)


def _text_match(value: str, operand: dict[str, Any]) -> bool:
    v = (value or "").lower()
    checks = []
    for key, fn in (("exactMatch", lambda t: v == t.lower()), ("includesExactly", lambda t: t.lower() in v), ("includesFuzzy", lambda t: all(w in v for w in t.lower().split()[:1]) or t.lower() in v), ("excludesExactly", lambda t: t.lower() not in v), ("excludesFuzzy", lambda t: t.lower() not in v)):
        op = operand.get(key)
        if op:
            vals = op.get("values") or []
            inner = op.get("operator", "or")
            hits = [fn(t) for t in vals]
            checks.append(all(hits) if inner == "and" else any(hits))
    if not checks:
        return True
    return all(checks) if operand.get("operator", "and") == "and" else any(checks)


def _enum_match(value: Any, operand: dict[str, Any]) -> bool:
    if isinstance(value, list):
        vals = [str(x).lstrip("#").lower() for x in value]
    else:
        vals = [str(value).lower()] if value is not None else []
    ok = True
    if operand.get("includes"):
        ok = ok and any(str(x).lower() in vals for x in operand["includes"])
    if operand.get("excludes"):
        ok = ok and not any(str(x).lower() in vals for x in operand["excludes"])
    return ok


def _range_match(value: Any, operand: dict[str, Any]) -> bool:
    if value is None:
        return False
    if "min" in operand and value < operand["min"]:
        return False
    if "max" in operand and value > operand["max"]:
        return False
    return True


def _date_match(value: str, operand: dict[str, Any]) -> bool:
    d = value[:10]
    if operand.get("after") and d < operand["after"][:10]:
        return False
    if operand.get("before") and d > operand["before"][:10]:
        return False
    return True


def _geo_match(lat: float | None, lng: float | None, operand: dict[str, Any]) -> bool:
    if lat is None or lng is None:
        return False
    inc = (operand.get("includes") or {}).get("values") or []
    if inc and not any(b["minLatitude"] <= lat <= b["maxLatitude"] and b["minLongitude"] <= lng <= b["maxLongitude"] for b in inc):
        return False
    exc = (operand.get("excludes") or {}).get("values") or []
    if exc and any(b["minLatitude"] <= lat <= b["maxLatitude"] and b["minLongitude"] <= lng <= b["maxLongitude"] for b in exc):
        return False
    return True


TEXT_FIELDS = {"caption", "profileBio", "transcript", "profileHandle", "audioTitle", "audioAuthor", "hashtags", "mentionHandles", "coAuthorHandles", "locationCompleteAddress", "profileLocationCompleteAddress", "handle", "displayName", "bio"}
ENUM_FIELDS = {"id", "platform", "platformId", "format", "profileId", "profilePlatformId", "captionLanguage", "transcriptLanguage", "audioPlatformId", "coAuthorIds", "mentionIds", "language"}
RANGE_FIELDS = {"viewsCount", "interactionsCount", "engagementRatePerViews", "engagementRatePerFollowers", "profileFollowersCount", "postsCount", "likesCount", "followersCount", "followingCount"}
DATE_FIELDS = {"publishedAt", "createdAt", "updatedAt"}


def _filters_match(item: dict[str, Any], filters: dict[str, Any] | None, kind: str) -> bool:
    for field, operand in (filters or {}).items():
        if field in TEXT_FIELDS:
            if field == "hashtags":
                value = " ".join(h.lstrip("#") for h in item.get("hashtags") or [])
            elif field == "mentionHandles":
                value = " ".join(m.get("profileHandle", "") for m in item.get("mentions") or [])
            else:
                value = item.get(field) or ""
            if not _text_match(value, operand):
                return False
        elif field in ENUM_FIELDS:
            if not _enum_match(item.get(field), operand):
                return False
        elif field in RANGE_FIELDS:
            if not _range_match(item.get(field), operand):
                return False
        elif field in DATE_FIELDS:
            if not _date_match(item.get(field) or "", operand):
                return False
        elif field in ("locationCoordinates", "profileLocationCoordinates"):
            if kind == "profiles":
                lat, lng = item.get("locationLatitude"), item.get("locationLongitude")
            else:
                lat, lng = (item.get("locationLatitude"), item.get("locationLongitude")) if field == "locationCoordinates" else (item.get("profileLocationLatitude"), item.get("profileLocationLongitude"))
            if not _geo_match(lat, lng, operand):
                return False
        elif field == "visualSimilarity":
            vals = (operand.get("includes") or {}).get("values") or []
            if vals and not all(v.get("assetId") in ASSETS for v in vals):
                return False
            # synthetic similarity: hash of asset+content id, thresholded
            for v in vals:
                sim = int(hashlib.sha1((v["assetId"] + item["id"]).encode()).hexdigest()[:4], 16) / 65535
                item["_sim"] = sim
                if sim < v.get("minScore", 0) or sim > v.get("maxScore", 1):
                    return False
        elif field in ("audioCopyrighted", "hasCoAuthors", "hasMentions", "isPrivate", "isVerified"):
            actual = item.get(field)
            if field == "hasMentions":
                actual = bool(item.get("mentions"))
            if field == "hasCoAuthors":
                actual = bool(item.get("coAuthors"))
            if bool(actual) != bool(operand):
                return False
    return True


def _query_match(item: dict[str, Any], q: dict[str, Any], kind: str, matched: list[str]) -> bool:
    own = _filters_match(item, q.get("filters"), kind)
    subs = q.get("queries") or []
    if subs:
        results = []
        for s in subs:
            local: list[str] = []
            r = _query_match(item, s, kind, local)
            results.append(r)
            if r:
                matched.extend(local)
                if s.get("name"):
                    matched.append(s["name"])
        sub_ok = all(results) if q.get("operator", "and") == "and" else any(results)
        ok = (own and sub_ok) if q.get("operator", "and") == "and" else (own and sub_ok) if q.get("filters") else sub_ok
    else:
        ok = own
    return ok


def _sort(items: list[dict[str, Any]], sort: str, kind: str) -> None:
    keys = []
    for part in [p.strip() for p in (sort or "publishedAt").split(",") if p.strip()]:
        field, _, direction = part.partition(":")
        keys.append((field, direction != "asc"))
    for field, desc in reversed(keys):
        if field == "visualSimilarity":
            items.sort(key=lambda x: x.get("_sim", 0), reverse=desc)
        elif field == "transcriptRelevance":
            items.sort(key=lambda x: len(x.get("matchedQueries") or []), reverse=desc)
        else:
            items.sort(key=lambda x: (x.get(field) is None, x.get(field) or 0), reverse=desc)


def _project(item: dict[str, Any], projection: str, kind: str) -> dict[str, Any]:
    if kind == "contents":
        keys = BASIC_C if projection == "basic" else DEFAULT_C if projection == "default" else None
    else:
        keys = BASIC_P if projection == "basic" else DEFAULT_P if projection == "default" else None
    if keys is None:
        return {k: v for k, v in item.items() if not k.startswith("_")}
    return {k: item.get(k) for k in keys}


def _meta(offset: int, limit: int, total: int, anchor: str | None = None) -> dict[str, Any]:
    m = {"requestId": hashlib.md5(str(RNG.random()).encode()).hexdigest()[:16], "executionTime": RNG.randint(9, 60), "timestamp": int(NOW.timestamp() * 1000), "pagination": {"offset": offset, "limit": limit, "totalCount": total}}
    if anchor:
        m["pagination"]["aiSearchAnchor"] = anchor
    return m


def _error(status: int, code: str, message: str, operation: str = "SEARCH") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"id": "err_mock", "operation": operation, "code": code, "message": message, "context": {}}, "metadata": _meta(0, 0, 0)})


@app.post("/rest/contents/search")
async def search_contents(request: Request, sort: str = Query("publishedAt"), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), projection: str = Query("default"), aiSearchAnchor: str | None = None, authorization: str | None = Header(None), x_api_key: str | None = Header(None)):
    if not _auth_ok(authorization, x_api_key):
        return _error(401, "UNAUTHORIZED", "Authorization failed.", "AUTHENTICATION")
    q = await request.json()
    if q.get("operator") not in ("and", "or"):
        return _error(400, "VALIDATION", "operator is required", "VALIDATION")
    rows = []
    for c in CONTENTS:
        matched: list[str] = []
        item = dict(c)
        if _query_match(item, q, "contents", matched):
            item["matchedQueries"] = sorted(set(matched))
            rows.append(item)
    _sort(rows, sort, "contents")
    total = len(rows)
    if offset > total and total > 0:
        return _error(416, "RANGE_NOT_SATISFIABLE", f"offset {offset} exceeds totalCount {total}")
    page = rows[offset : offset + limit]
    agg = {"totalViewsCount": sum(r["viewsCount"] for r in rows), "totalInteractionsCount": sum(r["interactionsCount"] for r in rows)}
    if projection == "full" and rows:
        agg["totalEngagementRatePerViews"] = round(sum(r["engagementRatePerViews"] for r in rows) / len(rows), 4)
        agg["totalEngagementRatePerFollowers"] = round(sum(r["engagementRatePerFollowers"] for r in rows) / len(rows), 4)
    anchor = "anchor_mock" if "visualSimilarity" in (q.get("filters") or {}) else None
    return {"data": {"aggregations": agg, "results": [_project(r, projection, "contents") for r in page]}, "metadata": _meta(offset, limit, total, anchor)}


@app.post("/rest/profiles/search")
async def search_profiles(request: Request, sort: str = Query("followersCount"), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), projection: str = Query("default"), authorization: str | None = Header(None), x_api_key: str | None = Header(None)):
    if not _auth_ok(authorization, x_api_key):
        return _error(401, "UNAUTHORIZED", "Authorization failed.", "AUTHENTICATION")
    q = await request.json()
    rows = [dict(p) for p in PROFILES if _query_match(p, q, "profiles", [])]
    _sort(rows, sort, "profiles")
    total = len(rows)
    page = rows[offset : offset + limit]
    return {"data": [_project(r, projection, "profiles") for r in page], "metadata": _meta(offset, limit, total)}


@app.post("/rest/assets", status_code=201)
async def create_asset(request: Request, authorization: str | None = Header(None), x_api_key: str | None = Header(None)):
    if not _auth_ok(authorization, x_api_key):
        return _error(401, "UNAUTHORIZED", "Authorization failed.", "AUTHENTICATION")
    body = await request.json()
    if body.get("type") not in ("text", "image"):
        return _error(400, "VALIDATION", "type must be text or image", "VALIDATION")
    aid = _id("ast", str(body))[:36]
    ASSETS[aid] = body
    return {"data": {"id": aid}, "metadata": _meta(0, 0, 0)}


@app.get("/health")
async def health():
    return {"ok": True, "profiles": len(PROFILES), "contents": len(CONTENTS), "mock": True}
