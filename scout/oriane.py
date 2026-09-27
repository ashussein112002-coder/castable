"""Oriane Connect REST client.

Surface (verified from the inline OpenAPI 3.0.0 spec served at
https://connect.oriane.xyz/rest/docs on 2026-09-27; a copy lives in
`scripts/oriane_openapi.json`):

    POST /rest/contents/search   ?sort&offset&limit&projection&aiSearchAnchor
    POST /rest/profiles/search   ?sort&offset&limit&projection
    POST /rest/assets            {type: text|image ...} -> {data: {id: ast_...}}

Design constraints this client enforces:
  * Credits are charged per returned result -> every call is cached on disk,
    `limit` is explicit, and a per-run budget guard refuses runaway fetches.
  * The auth header name is not documented -> auto-detect once with a 1-result
    probe and persist the working style.
  * 402 (credits), 416 (offset past totalCount) and 206 (partial) are handled
    explicitly instead of crashing the pipeline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .config import CACHE_DIR, DATA_DIR, settings

log = logging.getLogger("scout.oriane")

AUTH_STYLES: dict[str, tuple[str, str]] = {
    # style -> (header name, value template)
    "bearer": ("Authorization", "Bearer {key}"),
    "x-api-key": ("x-api-key", "{key}"),
    "api-key": ("api-key", "{key}"),
    "authorization-raw": ("Authorization", "{key}"),
}
AUTO_ORDER = ["bearer", "x-api-key", "api-key", "authorization-raw"]
AUTH_STYLE_FILE = DATA_DIR / "auth_style.txt"
CREDIT_LEDGER = DATA_DIR / "credits.jsonl"


class OrianeError(RuntimeError):
    def __init__(self, status: int, payload: Any, message: str | None = None):
        self.status = status
        self.payload = payload
        super().__init__(message or f"Oriane HTTP {status}: {json.dumps(payload)[:300]}")


class OrianeAuthError(OrianeError):
    pass


class OrianeCreditsExhausted(OrianeError):
    pass


class OrianeBudgetExceeded(RuntimeError):
    pass


@dataclass
class CallStats:
    calls: int = 0
    cached: int = 0
    results: int = 0
    results_by_projection: dict[str, int] = field(default_factory=dict)
    execution_ms: list[float] = field(default_factory=list)
    wall_ms: list[float] = field(default_factory=list)

    def record(self, projection: str, n: int, execution_ms: float | None, wall_ms: float, cached: bool) -> None:
        self.calls += 1
        if cached:
            self.cached += 1
        else:
            self.results += n
            self.results_by_projection[projection] = self.results_by_projection.get(projection, 0) + n
            if execution_ms is not None:
                self.execution_ms.append(execution_ms)
            self.wall_ms.append(wall_ms)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "served_from_cache": self.cached,
            "results_fetched_live": self.results,
            "results_by_projection": self.results_by_projection,
            "api_execution_ms_avg": round(sum(self.execution_ms) / len(self.execution_ms), 1) if self.execution_ms else None,
            "wall_ms_avg": round(sum(self.wall_ms) / len(self.wall_ms), 1) if self.wall_ms else None,
        }


def _cache_key(method: str, path: str, params: dict[str, Any], body: Any) -> str:
    blob = json.dumps({"m": method, "p": path, "q": params, "b": body}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class OrianeClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        auth_style: str | None = None,
        offline: bool | None = None,
        cache_ttl_s: int | None = None,
        max_results: int | None = None,
        timeout_s: float | None = None,
    ):
        self.base_url = (base_url or settings.ORIANE_BASE_URL or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ORIANE_API_KEY
        self.auth_style = auth_style or settings.ORIANE_AUTH_STYLE or "auto"
        self.offline = settings.SCOUT_OFFLINE if offline is None else offline
        self.cache_ttl_s = settings.SCOUT_CACHE_TTL_S if cache_ttl_s is None else cache_ttl_s
        self.max_results = settings.SCOUT_MAX_RESULTS_PER_RUN if max_results is None else max_results
        self.timeout_s = settings.ORIANE_TIMEOUT_S if timeout_s is None else timeout_s
        self.stats = CallStats()
        self._client = httpx.Client(timeout=self.timeout_s)
        if self.auth_style == "auto" and AUTH_STYLE_FILE.exists():
            saved = AUTH_STYLE_FILE.read_text().strip()
            if saved in AUTH_STYLES:
                self.auth_style = saved

    # ------------------------------------------------------------------ auth
    def _headers(self, style: str) -> dict[str, str]:
        if not self.api_key:
            return {"Content-Type": "application/json"}
        name, template = AUTH_STYLES[style]
        return {"Content-Type": "application/json", name: template.format(key=self.api_key)}

    def detect_auth_style(self) -> str:
        """Probe the API with a 1-result basic search until one header style is
        accepted. Persists the answer. Costs at most 1 credit-result."""
        if self.auth_style != "auto":
            return self.auth_style
        if not self.api_key:
            raise OrianeAuthError(401, {}, "ORIANE_API_KEY is not set")
        body = {"operator": "and", "filters": {"platform": {"includes": ["instagram", "tiktok"]}}}
        params = {"limit": 1, "offset": 0, "projection": "basic", "sort": "publishedAt:desc"}
        last: OrianeError | None = None
        for style in AUTO_ORDER:
            try:
                r = self._client.post(f"{self.base_url}/rest/contents/search", params=params, json=body, headers=self._headers(style))
            except httpx.HTTPError as exc:  # network problem, not an auth problem
                raise OrianeError(0, {"error": str(exc)}, f"network error while probing auth: {exc}") from exc
            if r.status_code in (200, 206):
                self.auth_style = style
                AUTH_STYLE_FILE.write_text(style)
                log.info("Oriane auth style detected: %s", style)
                return style
            last = OrianeError(r.status_code, _safe_json(r))
            if r.status_code not in (401, 403):
                # Any other status means the header was accepted (e.g. 402) or
                # the request itself is wrong; stop probing.
                break
        raise OrianeAuthError(last.status if last else 401, last.payload if last else {}, "no auth header style was accepted; read the exact header from app.oriane.xyz -> Billing -> Subscription -> API")

    # --------------------------------------------------------------- request
    def _request(self, method: str, path: str, params: dict[str, Any] | None, body: Any, *, cacheable: bool = True, expected_results: int = 0) -> dict[str, Any]:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        key = _cache_key(method, path, params, body)
        cache_file = CACHE_DIR / f"{key}.json"
        if cacheable and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                fresh = (time.time() - cached.get("_cached_at", 0)) < self.cache_ttl_s
                if fresh or self.offline:
                    self.stats.record(params.get("projection", "default"), _count_results(cached.get("payload")), None, 0.0, cached=True)
                    return cached["payload"]
            except (OSError, ValueError):
                pass
        if self.offline:
            raise OrianeError(0, {}, f"offline mode and no cached response for {path}")
        if self.stats.results + expected_results > self.max_results:
            raise OrianeBudgetExceeded(f"run budget exceeded: {self.stats.results} results fetched, +{expected_results} requested, cap {self.max_results}")

        style = self.detect_auth_style() if self.auth_style == "auto" else self.auth_style
        t0 = time.perf_counter()
        try:
            r = self._client.request(method, f"{self.base_url}{path}", params=params, json=body, headers=self._headers(style))
        except httpx.HTTPError as exc:
            raise OrianeError(0, {"error": str(exc)}, f"network error calling {path}: {exc}") from exc
        wall_ms = (time.perf_counter() - t0) * 1000
        payload = _safe_json(r)
        if r.status_code in (401, 403):
            raise OrianeAuthError(r.status_code, payload)
        if r.status_code == 402:
            raise OrianeCreditsExhausted(r.status_code, payload, "Oriane returned 402 Payment Required: credits exhausted")
        if r.status_code == 416:
            # offset beyond totalCount: return an empty page instead of failing
            return {"data": {"results": [], "aggregations": {}}, "metadata": {"pagination": {"offset": params.get("offset", 0), "limit": params.get("limit", 0), "totalCount": 0}, "partial": True}}
        if r.status_code not in (200, 201, 206):
            raise OrianeError(r.status_code, payload)
        if r.status_code == 206:
            payload.setdefault("metadata", {})["partial"] = True
        n = _count_results(payload)
        exec_ms = (payload.get("metadata") or {}).get("executionTime")
        self.stats.record(params.get("projection", "default"), n, exec_ms, wall_ms, cached=False)
        _ledger({"ts": time.time(), "path": path, "projection": params.get("projection"), "limit": params.get("limit"), "results": n, "execution_ms": exec_ms, "wall_ms": round(wall_ms, 1), "status": r.status_code})
        if cacheable:
            try:
                cache_file.write_text(json.dumps({"_cached_at": time.time(), "payload": payload}), encoding="utf-8")
            except OSError:
                pass
        return payload

    # -------------------------------------------------------------- endpoints
    def search_contents(self, query: dict[str, Any], *, sort: str = "publishedAt:desc", offset: int = 0, limit: int = 20, projection: str = "default", ai_search_anchor: str | None = None) -> dict[str, Any]:
        params = {"sort": sort, "offset": offset, "limit": min(max(limit, 1), 100), "projection": projection, "aiSearchAnchor": ai_search_anchor}
        return self._request("POST", "/rest/contents/search", params, query, expected_results=params["limit"])

    def search_profiles(self, query: dict[str, Any], *, sort: str = "followersCount:desc", offset: int = 0, limit: int = 20, projection: str = "default") -> dict[str, Any]:
        params = {"sort": sort, "offset": offset, "limit": min(max(limit, 1), 100), "projection": projection}
        return self._request("POST", "/rest/profiles/search", params, query, expected_results=params["limit"])

    def create_text_asset(self, text: str) -> str:
        payload = self._request("POST", "/rest/assets", None, {"type": "text", "text": text[:300]}, expected_results=0)
        return (payload.get("data") or {}).get("id") or payload.get("id")

    def create_image_asset(self, url: str) -> str:
        payload = self._request("POST", "/rest/assets", None, {"type": "image", "image": {"type": "url", "url": url}}, expected_results=0)
        return (payload.get("data") or {}).get("id") or payload.get("id")

    # --------------------------------------------------------------- helpers
    def iter_contents(self, query: dict[str, Any], *, sort: str, projection: str, want: int, page: int = 100):
        """Yield up to `want` results, paginating and honouring totalCount /
        aiSearchAnchor. Stops before the offset exceeds totalCount."""
        offset, anchor, got, total = 0, None, 0, None
        while got < want:
            limit = min(page, want - got)
            payload = self.search_contents(query, sort=sort, offset=offset, limit=limit, projection=projection, ai_search_anchor=anchor)
            data = payload.get("data") or {}
            results = data.get("results") or []
            pag = (payload.get("metadata") or {}).get("pagination") or {}
            total = pag.get("totalCount", total)
            anchor = pag.get("aiSearchAnchor", anchor)
            for item in results:
                yield item
            got += len(results)
            offset += len(results)
            if not results or (total is not None and offset >= total):
                break

    def probe(self) -> dict[str, Any]:
        """One cheap live call; returns timing + auth style. Used by /api/health."""
        t0 = time.perf_counter()
        style = self.detect_auth_style()
        payload = self.search_contents({"operator": "and", "filters": {"platform": {"includes": ["instagram", "tiktok"]}}}, sort="publishedAt:desc", limit=1, projection="basic")
        return {
            "ok": True,
            "auth_style": style,
            "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
            "execution_ms": (payload.get("metadata") or {}).get("executionTime"),
            "totalCount": ((payload.get("metadata") or {}).get("pagination") or {}).get("totalCount"),
        }


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text[:500]}


def _count_results(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if isinstance(data, dict):
        return len(data.get("results") or [])
    if isinstance(data, list):
        return len(data)
    return 0


def _ledger(entry: dict[str, Any]) -> None:
    try:
        with CREDIT_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def ledger_totals() -> dict[str, Any]:
    """Aggregate the append-only ledger: live results fetched so far, by projection."""
    totals: dict[str, int] = {}
    calls = 0
    if CREDIT_LEDGER.exists():
        for line in CREDIT_LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            calls += 1
            totals[e.get("projection") or "n/a"] = totals.get(e.get("projection") or "n/a", 0) + int(e.get("results") or 0)
    return {"live_calls": calls, "live_results_by_projection": totals, "live_results_total": sum(totals.values())}
