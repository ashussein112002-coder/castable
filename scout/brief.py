"""Brand brief -> structured search intent.

Deterministic parsing first (so the pipeline works with no LLM), then an
optional LLM enrichment that only ADDS keywords/competitors and never removes
what the user typed.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .llm import LLM

FOLLOWER_BANDS: dict[str, tuple[int, int]] = {
    "nano": (1_000, 10_000),
    "micro": (10_000, 100_000),
    "mid": (100_000, 500_000),
    "macro": (500_000, 2_000_000),
    "any": (1_000, 50_000_000),
}

# tiny bilingual seed vocabulary so a bare category still yields good queries
CATEGORY_TERMS: dict[str, list[str]] = {
    "skincare": ["skincare", "skin care routine", "serum", "moisturizer", "glow", "عناية بالبشرة", "روتين بشرة"],
    "beauty": ["makeup", "beauty", "grwm", "get ready with me", "مكياج", "جمال"],
    "fashion": ["outfit", "ootd", "fashion", "styling", "lookbook", "haul", "أزياء", "لوك", "تنسيق"],
    "luxury": ["luxury", "designer", "haute couture", "unboxing", "فخامة"],
    "fragrance": ["perfume", "fragrance", "scent", "عطر", "عطور"],
    "fitness": ["workout", "gym", "fitness", "training", "تمرين", "رياضة"],
    "food": ["recipe", "restaurant", "foodie", "cafe", "مطعم", "وصفة"],
    "travel": ["travel", "hotel", "staycation", "سفر", "فندق"],
    "tech": ["gadget", "unboxing", "tech review", "iphone", "تقنية"],
    "cars": ["car", "supercar", "test drive", "سيارة"],
    "modest": ["modest fashion", "hijab style", "abaya", "عباية", "حجاب"],
    "haircare": ["hair care", "hair routine", "شعر", "عناية بالشعر"],
    "jewelry": ["jewelry", "jewellery", "gold", "diamond", "مجوهرات"],
}


@dataclass
class Brief:
    text: str
    brand: str = ""
    category: str = ""
    keywords: list[str] = field(default_factory=list)  # search terms (EN/AR)
    hashtags: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    avoid_topics: list[str] = field(default_factory=list)
    tone: str = ""
    audience: str = ""
    languages: list[str] = field(default_factory=list)  # ["en","ar"]
    region: str = "uae"
    platforms: list[str] = field(default_factory=lambda: ["instagram", "tiktok"])
    follower_band: str = "micro"
    followers_min: int = 10_000
    followers_max: int = 500_000
    days_back: int = 90
    image_url: str = ""
    visual_prompt: str = ""
    llm_used: str = "none"
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------ builders
    @classmethod
    def from_form(cls, form: dict[str, Any]) -> "Brief":
        text = (form.get("text") or "").strip()
        b = cls(text=text)
        b.brand = (form.get("brand") or "").strip()
        b.category = (form.get("category") or "").strip().lower()
        b.region = (form.get("region") or "uae").strip().lower()
        b.platforms = [p for p in (form.get("platforms") or ["instagram", "tiktok"]) if p in ("instagram", "tiktok")] or ["instagram", "tiktok"]
        band = (form.get("follower_band") or "micro").lower()
        b.follower_band = band if band in FOLLOWER_BANDS else "micro"
        lo, hi = FOLLOWER_BANDS[b.follower_band]
        if band == "micro":  # default band for GCC brand work: micro + mid
            hi = FOLLOWER_BANDS["mid"][1]
        b.followers_min = int(form.get("followers_min") or lo)
        b.followers_max = int(form.get("followers_max") or hi)
        b.days_back = int(form.get("days_back") or 90)
        b.image_url = (form.get("image_url") or "").strip()
        b.visual_prompt = (form.get("visual_prompt") or "").strip()
        b.competitors = _split_list(form.get("competitors"))
        b.keywords = _split_list(form.get("keywords"))
        b.languages = [l for l in _split_list(form.get("languages")) if l] or []
        b._parse_text()
        return b

    def _parse_text(self) -> None:
        t = self.text
        low = t.lower()
        # explicit "competitors: a, b" / "avoid: x, y" lines anywhere in the text
        for label, target in (("competitor", "competitors"), ("avoid", "avoid_topics"), ("keyword", "keywords"), ("hashtag", "hashtags")):
            for m in re.finditer(rf"{label}s?\s*[:\-]\s*([^\n\.]+)", t, re.I):
                vals = _split_list(m.group(1))
                current = getattr(self, target)
                for v in vals:
                    if v and v not in current:
                        current.append(v)
        if not self.brand:
            m = re.search(r"\b(?:brand|for|client)\s*[:\-]?\s*([A-Z][\w&'’\- ]{1,40})", t)
            if m:
                self.brand = m.group(1).strip()
        if not self.category:
            for cat in CATEGORY_TERMS:
                if cat in low:
                    self.category = cat
                    break
        # category seeds
        if self.category in CATEGORY_TERMS:
            for term in CATEGORY_TERMS[self.category]:
                if term not in self.keywords:
                    self.keywords.append(term)
        # languages
        if not self.languages:
            langs = []
            if re.search(r"\barabic\b|\bعرب", low):
                langs.append("ar")
            if re.search(r"\benglish\b", low):
                langs.append("en")
            self.languages = langs or ["en", "ar"]
        # region words
        for key, words in {
            "dubai": ["dubai", "دبي"], "abu-dhabi": ["abu dhabi", "أبوظبي"], "riyadh": ["riyadh", "الرياض"], "jeddah": ["jeddah", "جدة"],
            "saudi": ["saudi", "ksa", "السعودية"], "qatar": ["qatar", "doha", "قطر"], "kuwait": ["kuwait", "الكويت"], "bahrain": ["bahrain", "البحرين"],
            "oman": ["oman", "muscat", "عمان"], "egypt": ["egypt", "cairo", "مصر"], "gcc": ["gcc", "gulf", "الخليج"], "mena": ["mena", "middle east"], "uae": ["uae", "emirates", "الإمارات"],
        }.items():
            if any(w in low for w in words) and self.region in ("", "uae") and key != "uae":
                self.region = key
                break
        # hashtags typed inline
        for tag in re.findall(r"#([\w؀-ۿ]+)", t):
            if tag not in self.hashtags:
                self.hashtags.append(tag)
        # fallback keywords: capitalised words + nouns-ish tokens (very rough)
        if not self.keywords:
            words = [w.lower() for w in re.findall(r"[A-Za-z؀-ۿ]{4,}", t)]
            stop = {"with", "that", "this", "from", "have", "they", "their", "want", "need", "looking", "about", "brand", "campaign", "creators", "creator", "influencer", "influencers", "launch", "target", "targeting", "audience", "content", "video", "videos", "please", "which", "should", "would"}
            seen: list[str] = []
            for w in words:
                if w not in stop and w not in seen:
                    seen.append(w)
            self.keywords = seen[:8]

    # ---------------------------------------------------------------- LLM
    def enrich(self, llm: LLM) -> None:
        system = (
            "You are a senior influencer-marketing strategist for GCC brands. Convert a brand brief into search intent for a social video index "
            "(Instagram + TikTok, transcripts and captions). Return STRICT JSON with keys: brand (string), category (one of: "
            + ", ".join(CATEGORY_TERMS) + " or other), keywords (8-14 short search phrases; include Arabic variants when the audience is Arabic), "
            "hashtags (5-10, without #), competitors (brand names to flag when a creator mentions them), avoid_topics (brand-safety topics to flag), "
            "tone (5 words max), audience (one line), languages (ISO codes), visual_prompt (<=200 chars describing the ideal on-screen look, for visual similarity search)."
        )
        user = f"BRIEF:\n{self.text}\n\nKnown so far: {self.as_dict()}"
        out = llm.json(system, user, max_tokens=900)
        self.llm_used = llm.describe()
        if not isinstance(out, dict):
            self.notes.append("LLM enrichment unavailable; using deterministic parse")
            return
        self.brand = self.brand or str(out.get("brand") or "")
        cat = str(out.get("category") or "").lower()
        if not self.category and cat in CATEGORY_TERMS:
            self.category = cat
            for term in CATEGORY_TERMS[cat]:
                if term not in self.keywords:
                    self.keywords.append(term)
        for key in ("keywords", "hashtags", "competitors", "avoid_topics"):
            vals = out.get(key) or []
            if isinstance(vals, list):
                current = getattr(self, key)
                for v in vals:
                    v = str(v).strip().lstrip("#")
                    if v and v.lower() not in {c.lower() for c in current}:
                        current.append(v)
        self.tone = self.tone or str(out.get("tone") or "")
        self.audience = self.audience or str(out.get("audience") or "")
        langs = out.get("languages")
        if isinstance(langs, list) and langs:
            self.languages = [str(l).lower()[:2] for l in langs][:3]
        self.visual_prompt = self.visual_prompt or str(out.get("visual_prompt") or "")[:300]
        # keep query sizes sane (Oriane caps total filter values at 500; we stay far below)
        self.keywords = self.keywords[:14]
        self.hashtags = self.hashtags[:10]
        self.competitors = self.competitors[:12]


def _split_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        items = [str(v) for v in value]
    else:
        items = re.split(r"[,\n;/]+|\band\b", str(value))
    out: list[str] = []
    for it in items:
        it = it.strip().strip("#").strip()
        if it and it.lower() not in {o.lower() for o in out}:
            out.append(it)
    return out
