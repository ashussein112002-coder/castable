"""Vetting: evidence-backed checks on a creator's recent videos.

Every flag carries the video id, a verbatim quote and (when it comes from the
transcript) a timestamp, so a brand manager can open the video and verify it.
Heuristics are labelled as heuristics; nothing here claims to be a verdict.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import defaultdict
from typing import Any

from .brief import Brief
from .oriane import OrianeClient

# Small, transparent lexicons. Extend in data/lexicon.json if needed.
RISK_LEXICON: dict[str, list[str]] = {
    "profanity": ["fuck", "shit", "bitch", "asshole", "wtf", "كس", "زبي", "خرا", "كلب", "حمار", "عرص"],
    "alcohol": ["vodka", "whisky", "whiskey", "tequila", "cocktail", "champagne", "beer", "drunk", "hangover", "خمر", "بيرة", "سكران"],
    "gambling_scams": ["casino", "betting", "bet365", "1xbet", "forex signals", "guaranteed profit", "guaranteed returns", "double your money", "crypto giveaway", "pump", "قمار", "رهان", "أرباح مضمونة"],
    "adult": ["onlyfans", "nsfw", "18+", "strip", "escort", "sugar daddy"],
    "political_religious": ["election", "boycott", "zionist", "genocide", "regime", "مقاطعة", "انتخابات", "نظام"],
    "drugs_vape": ["weed", "cannabis", "vape", "hookah", "shisha", "حشيش", "شيشة", "فيب"],
    "weapons_violence": ["gun", "knife fight", "shooting", "سلاح", "مسدس"],
}
SPONSORED_TAGS = {"ad", "sponsored", "gifted", "paidpartnership", "paid", "collab", "partner", "ambassador", "اعلان", "إعلان", "تعاون", "شراكة", "اعلان_ممول"}
SPONSORED_WORDS = re.compile(r"\b(ad|sponsored|gifted|paid partnership|in collaboration with|partner(?:ed)? with|ambassador|discount code|use my code|promo code|link in bio)\b|إعلان|اعلان|تعاون مدفوع|كود خصم", re.I)


def _norm(s: str | None) -> str:
    return (s or "").lower()


def _find_in_chunks(chunks: list[dict[str, Any]], needle: str) -> tuple[str, float | None] | None:
    n = needle.lower()
    for ch in chunks or []:
        text = ch.get("text") or ""
        if n in text.lower():
            return text.strip(), ch.get("startSeconds")
    return None


def fetch_recent_videos(client: OrianeClient, profile_id: str, *, days: int = 180, limit: int = 12, log=print) -> list[dict[str, Any]]:
    query = {
        "operator": "and",
        "filters": {
            "profileId": {"includes": [profile_id]},
            "format": {"includes": ["video"]},
            "publishedAt": {"after": (dt.date.today() - dt.timedelta(days=days)).isoformat()},
        },
    }
    items = list(client.iter_contents(query, sort="publishedAt:desc", projection="full", want=limit, page=limit))
    log(f"vetting: {len(items)} recent videos for {profile_id}")
    return items


def vet_creator(candidate: dict[str, Any], profile: dict[str, Any] | None, videos: list[dict[str, Any]], brief: Brief) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []
    sponsored: dict[str, int] = defaultdict(int)
    mentioned_brands: dict[str, int] = defaultdict(int)
    audio_copyrighted = 0
    langs: dict[str, int] = defaultdict(int)
    hooks: list[dict[str, Any]] = []
    dates: list[dt.datetime] = []
    er_views: list[float] = []
    er_follow: list[float] = []
    comment_like_ratio: list[float] = []
    views_follow_ratio: list[float] = []
    followers = (profile or {}).get("followersCount") or candidate.get("followers") or 0

    competitors = [c.lower() for c in brief.competitors]
    avoid = [a.lower() for a in brief.avoid_topics]

    for v in videos:
        vid = v.get("id")
        caption = v.get("caption") or ""
        transcript = v.get("transcript") or ""
        chunks = v.get("transcriptChunks") or []
        tags = [str(h).lstrip("#").lower() for h in (v.get("hashtags") or [])]
        text_all = f"{caption}\n{transcript}".lower()
        link = video_link(v)

        # dates / cadence
        try:
            dates.append(dt.datetime.fromisoformat(str(v.get("publishedAt")).replace("Z", "+00:00")))
        except (TypeError, ValueError):
            pass
        # performance
        if v.get("engagementRatePerViews") is not None:
            er_views.append(float(v["engagementRatePerViews"]))
        if v.get("engagementRatePerFollowers") is not None:
            er_follow.append(float(v["engagementRatePerFollowers"]))
        likes, comments, views = v.get("likesCount") or 0, v.get("commentsCount") or 0, v.get("viewsCount") or 0
        if likes:
            comment_like_ratio.append(comments / likes)
        if followers and views:
            views_follow_ratio.append(views / followers)
        # audio rights
        if v.get("audioCopyrighted"):
            audio_copyrighted += 1
        # language mix
        langs[v.get("transcriptLanguage") or v.get("captionLanguage") or "?"] += 1
        # sponsored history
        is_sponsored = any(t in SPONSORED_TAGS for t in tags) or bool(SPONSORED_WORDS.search(caption))
        for m in v.get("mentions") or []:
            h = (m.get("profileHandle") or "").lower()
            if h:
                mentioned_brands[h] += 1
                if is_sponsored:
                    sponsored[h] += 1
        if is_sponsored and not (v.get("mentions") or []):
            sponsored["(undisclosed partner)"] += 1
        # competitor mentions
        for comp in competitors:
            if comp and comp in text_all:
                hit = _find_in_chunks(chunks, comp)
                flags.append({"type": "competitor_mention", "severity": "high", "term": comp, "video": vid, "link": link, "published": v.get("publishedAt"), "quote": (hit[0] if hit else _snippet(caption if comp in caption.lower() else transcript, comp)), "t": hit[1] if hit else None})
        # avoid topics from the brief
        for topic in avoid:
            if topic and topic in text_all:
                hit = _find_in_chunks(chunks, topic)
                flags.append({"type": "avoid_topic", "severity": "medium", "term": topic, "video": vid, "link": link, "published": v.get("publishedAt"), "quote": (hit[0] if hit else _snippet(text_all, topic)), "t": hit[1] if hit else None})
        # lexicon
        for cat, words in RISK_LEXICON.items():
            for w in words:
                if re.search(rf"(?<![\w؀-ۿ]){re.escape(w)}(?![\w؀-ۿ])", text_all):
                    hit = _find_in_chunks(chunks, w)
                    flags.append({"type": cat, "severity": "high" if cat in ("adult", "gambling_scams", "weapons_violence") else "medium", "term": w, "video": vid, "link": link, "published": v.get("publishedAt"), "quote": (hit[0] if hit else _snippet(text_all, w)), "t": hit[1] if hit else None})
                    break  # one flag per category per video is enough evidence
        # hooks: first ~3 seconds of speech
        first = [c for c in chunks if (c.get("startSeconds") or 0) < 3.5]
        if first:
            hook_text = " ".join((c.get("text") or "").strip() for c in first).strip()
            if hook_text:
                hooks.append({"video": vid, "link": link, "hook": hook_text[:160], "views": views, "er": v.get("engagementRatePerViews")})
        elif transcript:
            hooks.append({"video": vid, "link": link, "hook": transcript[:120], "views": views, "er": v.get("engagementRatePerViews")})

    # dedupe flags (same type+term+video)
    seen = set()
    uniq = []
    for f in flags:
        k = (f["type"], f["term"], f["video"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    flags = uniq

    # cadence
    cadence = None
    last_post_days = None
    if dates:
        dates.sort()
        span_days = max((dates[-1] - dates[0]).days, 1)
        cadence = round(len(dates) / (span_days / 7), 2)
        last_post_days = (dt.datetime.now(dt.timezone.utc) - dates[-1]).days

    # authenticity heuristics (labelled as such)
    auth_notes: list[str] = []
    med_er_f = statistics.median(er_follow) if er_follow else None
    med_cl = statistics.median(comment_like_ratio) if comment_like_ratio else None
    med_vf = statistics.median(views_follow_ratio) if views_follow_ratio else None
    if med_er_f is not None and followers >= 50_000 and med_er_f < 0.003:
        auth_notes.append(f"very low engagement per follower (median {med_er_f:.2%}) for {followers:,} followers - possible inflated audience")
    if med_cl is not None and med_cl < 0.002:
        auth_notes.append(f"comments/likes ratio {med_cl:.3%} - likes without conversation")
    if med_cl is not None and med_cl > 0.2:
        auth_notes.append(f"comments/likes ratio {med_cl:.1%} - unusually chatty (check for comment pods or controversy)")
    if med_vf is not None and med_vf > 5:
        auth_notes.append(f"views are {med_vf:.1f}x followers - reach driven by the algorithm, not the follower base (good for awareness, weaker for conversion)")

    hooks.sort(key=lambda h: (h.get("views") or 0), reverse=True)
    top_brands = sorted(mentioned_brands.items(), key=lambda kv: kv[1], reverse=True)[:8]
    return {
        "videos_checked": len(videos),
        "window_days": 180,
        "flags": flags,
        "flag_counts": _count_by(flags, "type"),
        "sponsored_posts": sum(sponsored.values()),
        "sponsored_partners": sorted(sponsored.items(), key=lambda kv: kv[1], reverse=True)[:8],
        "mentioned_brands": top_brands,
        "audio_copyrighted_share": round(audio_copyrighted / len(videos), 2) if videos else None,
        "language_mix": dict(langs),
        "cadence_per_week": cadence,
        "last_post_days_ago": last_post_days,
        "er_views_median": round(statistics.median(er_views), 4) if er_views else None,
        "er_followers_median": round(med_er_f, 4) if med_er_f is not None else None,
        "comment_like_ratio_median": round(med_cl, 4) if med_cl is not None else None,
        "views_per_follower_median": round(med_vf, 2) if med_vf is not None else None,
        "authenticity_notes": auth_notes,
        "hooks": hooks[:5],
        "top_comments": _top_comments(videos),
        "evidence_videos": [_evidence_video(v) for v in videos[:6]],
    }


def video_link(v: dict[str, Any]) -> str | None:
    """Best-effort deep link. TikTok ids map to canonical URLs; Instagram
    numeric media ids do not, so fall back to the profile."""
    platform, handle, pid = v.get("platform"), v.get("profileHandle"), v.get("platformId")
    if platform == "tiktok" and handle and pid:
        return f"https://www.tiktok.com/@{handle}/video/{pid}"
    if platform == "instagram" and handle:
        return f"https://www.instagram.com/{handle}/"
    if platform == "tiktok" and handle:
        return f"https://www.tiktok.com/@{handle}"
    return None


def _snippet(text: str, term: str, width: int = 90) -> str:
    i = text.lower().find(term.lower())
    if i == -1:
        return text[:width]
    a, b = max(0, i - width // 2), min(len(text), i + len(term) + width // 2)
    return ("…" if a else "") + text[a:b].replace("\n", " ") + ("…" if b < len(text) else "")


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for it in items:
        out[it.get(key) or "?"] += 1
    return dict(out)


def _top_comments(videos: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    rows = []
    for v in videos:
        for c in v.get("popularComments") or []:
            rows.append({"video": v.get("id"), "content": (c.get("content") or "")[:160], "likes": c.get("likesCount") or 0, "handle": c.get("profileHandle")})
    rows.sort(key=lambda r: r["likes"], reverse=True)
    return rows[:n]


def _evidence_video(v: dict[str, Any]) -> dict[str, Any]:
    frames = v.get("frames") or []
    return {
        "id": v.get("id"),
        "platform": v.get("platform"),
        "link": video_link(v),
        "published": v.get("publishedAt"),
        "caption": (v.get("caption") or "")[:200],
        "thumbnail": v.get("thumbnailMediaUrl"),
        "views": v.get("viewsCount"),
        "likes": v.get("likesCount"),
        "comments": v.get("commentsCount"),
        "er_views": v.get("engagementRatePerViews"),
        "duration": v.get("duration"),
        "language": v.get("transcriptLanguage") or v.get("captionLanguage"),
        "audio": {"title": v.get("audioTitle"), "author": v.get("audioAuthor"), "copyrighted": v.get("audioCopyrighted")},
        "transcript_excerpt": (v.get("transcript") or "")[:400],
        "frames": [{"t": f.get("timestampSeconds"), "url": f.get("url")} for f in frames[:4]],
        "hashtags": v.get("hashtags") or [],
    }
