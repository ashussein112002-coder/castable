"""Bounding boxes for the geo filters (profileLocationCoordinates /
locationCoordinates). Oriane takes lat/lng boxes, so regions are approximated
by one or more rectangles. Coarse on purpose: the filter is a pre-selection,
not a legal jurisdiction test."""
from __future__ import annotations

Box = dict[str, float]


def box(min_lat: float, max_lat: float, min_lng: float, max_lng: float) -> Box:
    return {"minLatitude": min_lat, "maxLatitude": max_lat, "minLongitude": min_lng, "maxLongitude": max_lng}


REGIONS: dict[str, dict] = {
    "dubai": {"label": "Dubai", "boxes": [box(24.75, 25.40, 54.85, 55.60)]},
    "abu-dhabi": {"label": "Abu Dhabi", "boxes": [box(24.20, 24.70, 54.20, 54.85)]},
    "uae": {"label": "United Arab Emirates", "boxes": [box(22.60, 26.30, 51.50, 56.50)]},
    "riyadh": {"label": "Riyadh", "boxes": [box(24.40, 25.10, 46.30, 47.10)]},
    "jeddah": {"label": "Jeddah", "boxes": [box(21.30, 21.90, 39.00, 39.50)]},
    "saudi": {"label": "Saudi Arabia", "boxes": [box(16.30, 32.20, 34.50, 55.70)]},
    "qatar": {"label": "Qatar", "boxes": [box(24.45, 26.20, 50.70, 51.70)]},
    "kuwait": {"label": "Kuwait", "boxes": [box(28.50, 30.10, 46.50, 48.50)]},
    "bahrain": {"label": "Bahrain", "boxes": [box(25.75, 26.35, 50.35, 50.70)]},
    "oman": {"label": "Oman", "boxes": [box(16.60, 26.40, 52.00, 60.00)]},
    "gcc": {
        "label": "GCC (UAE, Saudi, Qatar, Kuwait, Bahrain, Oman)",
        "boxes": [
            box(22.60, 26.30, 51.50, 56.50),  # UAE
            box(16.30, 32.20, 34.50, 55.70),  # Saudi
            box(24.45, 26.20, 50.70, 51.70),  # Qatar
            box(28.50, 30.10, 46.50, 48.50),  # Kuwait
            box(25.75, 26.35, 50.35, 50.70),  # Bahrain
            box(16.60, 26.40, 52.00, 60.00),  # Oman
        ],
    },
    "egypt": {"label": "Egypt", "boxes": [box(22.00, 31.70, 24.70, 36.90)]},
    "mena": {
        "label": "MENA (GCC + Egypt + Levant + Maghreb)",
        "boxes": [
            box(16.30, 32.20, 34.50, 60.00),  # Arabian peninsula
            box(22.00, 31.70, 24.70, 36.90),  # Egypt
            box(29.00, 37.50, 34.00, 42.50),  # Levant / Iraq west
            box(18.00, 37.50, -17.50, 12.00),  # Maghreb
        ],
    },
    "london": {"label": "London", "boxes": [box(51.28, 51.70, -0.52, 0.34)]},
    "global": {"label": "Global (no geo filter)", "boxes": []},
}


def region_filter(region: str | None) -> dict | None:
    """Return the `profileLocationCoordinates` filter for a region key, or
    None for global / unknown."""
    if not region:
        return None
    r = REGIONS.get(region.lower().strip())
    if not r or not r["boxes"]:
        return None
    return {"includes": {"values": r["boxes"], "operator": "or"}}


def region_label(region: str | None) -> str:
    if not region:
        return "Global"
    r = REGIONS.get(region.lower().strip())
    return r["label"] if r else region


def in_region(lat: float | None, lng: float | None, region: str | None) -> bool | None:
    """Client-side check used for evidence (None when unknown)."""
    if lat is None or lng is None or not region:
        return None
    r = REGIONS.get(region.lower().strip())
    if not r or not r["boxes"]:
        return True
    return any(b["minLatitude"] <= lat <= b["maxLatitude"] and b["minLongitude"] <= lng <= b["maxLongitude"] for b in r["boxes"])
