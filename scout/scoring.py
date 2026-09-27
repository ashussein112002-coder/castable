"""Transparent composite score (0-100). Weights are explicit and every
component is returned so the dossier can show the breakdown.

  relevance   35  - how much of the creator's recent work matches the brief
  performance 25  - engagement per view relative to the candidate pool
  audience    15  - follower band, region, language fit
  safety      25  - 100 minus flag penalties (hard caps for high-severity)
"""
from __future__ import annotations

from typing import Any

from .brief import Brief

WEIGHTS = {"relevance": 0.35, "performance": 0.25, "audience": 0.15, "safety": 0.25}
PENALTY = {"high": 35, "medium": 12, "low": 5}


def _pct_rank(value: float, pool: list[float]) -> float:
    if not pool:
        return 50.0
    below = sum(1 for p in pool if p < value)
    return 100.0 * below / max(len(pool) - 1, 1)


def score_creator(candidate: dict[str, Any], vet: dict[str, Any] | None, profile: dict[str, Any] | None, brief: Brief, pool: list[dict[str, Any]]) -> dict[str, Any]:
    # relevance: matching videos (log-ish), multiple matched query types, visual rank
    mv = candidate.get("matching_videos") or 0
    rel = min(100.0, 30 + 18 * min(mv, 4))  # 1 video=48, 2=66, 3=84, 4+=100
    if len(candidate.get("matched_queries") or {}) >= 2:
        rel = min(100.0, rel + 8)
    vr = candidate.get("visual_best_rank")
    if vr:
        rel = min(100.0, rel + max(0, 12 - vr))

    # performance: percentile of mean ER per view within the pool, blended with views
    er_pool = [c.get("er_views_mean") or 0 for c in pool]
    views_pool = [c.get("views_max") or 0 for c in pool]
    perf = 0.7 * _pct_rank(candidate.get("er_views_mean") or 0, er_pool) + 0.3 * _pct_rank(candidate.get("views_max") or 0, views_pool)

    # audience: band fit + language + geo
    followers = (profile or {}).get("followersCount") or candidate.get("followers") or 0
    aud = 60.0
    if brief.followers_min <= followers <= brief.followers_max:
        aud += 20
    mix = (vet or {}).get("language_mix") or candidate.get("languages") or {}
    if brief.languages and mix:
        total = sum(mix.values()) or 1
        share = sum(v for k, v in mix.items() if k in brief.languages) / total
        aud += 20 * share
    else:
        aud += 10
    aud = min(100.0, aud)

    # safety
    safety = 100.0
    caps: list[str] = []
    worst = None
    for f in (vet or {}).get("flags") or []:
        sev = f.get("severity")
        safety -= PENALTY.get(sev, 5)
        if f.get("type") == "competitor_mention":
            caps.append("competitor mention in last 180 days")
        if sev == "high" or (sev == "medium" and worst != "high"):
            worst = sev
    # A brand-safety flag is never averaged away by relevance: it caps the grade.
    if worst == "high":
        caps.append("high-severity brand-safety flag (grade capped at C)")
    elif worst == "medium":
        caps.append("medium-severity brand-safety flag (grade capped at B)")
    for note in (vet or {}).get("authenticity_notes") or []:
        safety -= 8
    safety = max(0.0, safety)
    if not vet:
        safety = 70.0  # not vetted yet: unknown, not clean

    total = WEIGHTS["relevance"] * rel + WEIGHTS["performance"] * perf + WEIGHTS["audience"] * aud + WEIGHTS["safety"] * safety
    for cap in caps:
        if "competitor" in cap:
            total = min(total, 69.0)  # a competitor mention never yields an "A"
        elif "high-severity" in cap:
            total = min(total, 59.0)
        elif "medium-severity" in cap:
            total = min(total, 79.0)
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"
    return {
        "total": round(total, 1),
        "grade": grade,
        "components": {"relevance": round(rel, 1), "performance": round(perf, 1), "audience": round(aud, 1), "safety": round(safety, 1)},
        "weights": WEIGHTS,
        "caps": caps,
        "vetted": bool(vet),
    }
