"""Bing Webmaster Tools API client.

Read-only client for the Bing Webmaster JSON API. Docs:
https://learn.microsoft.com/en-us/bingwebmaster/

Authentication uses a single API key from Bing Webmaster Tools:
Settings -> API Access -> Generate API Key.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CACHE_TTL = 300
MAX_RETRIES = 2

# Bing takes the API key in the query string. Stop httpx from logging full URLs,
# so the key never lands in server logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_DOTNET_DATE = re.compile(r"^/Date\((-?\d+)([-+]\d{4})?\)/$")

_cache: dict[str, tuple[float, Any]] = {}
_transport: httpx.BaseTransport | None = None


class BingAPIError(Exception):
    """Raised when the Bing Webmaster API returns an error."""

    def __init__(self, method: str, status: int | None, message: str, hint: str = ""):
        self.method = method
        self.status = status
        self.message = message
        self.hint = hint
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [f"Bing Webmaster API error in {self.method}"]
        if self.status:
            parts.append(f"(HTTP {self.status})")
        text = " ".join(parts) + f": {self.message}"
        if self.hint:
            text += f"\n{self.hint}"
        return text


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def api_key() -> str:
    """Return the configured Bing Webmaster API key."""
    key = os.environ.get("BING_WEBMASTER_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "BING_WEBMASTER_API_KEY is not set.\n\n"
            "Get the key from Bing Webmaster Tools:\n"
            "  1. Sign in at https://www.bing.com/webmasters\n"
            "  2. Verify your site\n"
            "  3. Settings -> API Access -> Generate API Key\n\n"
            "Then add it to .env:\n"
            '  BING_WEBMASTER_API_KEY="your_key_here"'
        )
    return key


def is_configured() -> bool:
    """Return True when an API key is present."""
    return bool(os.environ.get("BING_WEBMASTER_API_KEY", "").strip())


def _timeout() -> float:
    raw = os.environ.get("BING_REQUEST_TIMEOUT", "")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


def _cache_ttl() -> float:
    raw = os.environ.get("BING_CACHE_TTL", "")
    try:
        return float(raw) if raw else DEFAULT_CACHE_TTL
    except ValueError:
        return DEFAULT_CACHE_TTL


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _to_snake(name: str) -> str:
    """Convert PascalCase or camelCase keys to snake_case."""
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    second = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first)
    return second.lower()


def _parse_dotnet_date(value: str) -> str | None:
    """Convert a .NET '/Date(ms-offset)/' string to an ISO 8601 string."""
    match = _DOTNET_DATE.match(value)
    if not match:
        return None
    millis = int(match.group(1))
    offset = match.group(2)
    if offset:
        sign = 1 if offset[0] == "+" else -1
        hours = int(offset[1:3])
        minutes = int(offset[3:5])
        tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
    else:
        tz = timezone.utc
    moment = datetime.fromtimestamp(millis / 1000, tz=tz)
    return moment.isoformat()


def normalize(value: Any) -> Any:
    """Recursively normalize Bing JSON values.

    Rules: drop '__type', snake_case keys, convert .NET dates.
    """
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "__type":
                continue
            result[_to_snake(key)] = normalize(item)
        return result
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        parsed = _parse_dotnet_date(value)
        return parsed if parsed else value
    return value


def _as_rows(value: Any) -> list[dict]:
    """Return a list of rows from a Bing response value."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------

def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Override the HTTP transport. Used by tests."""
    global _transport
    _transport = transport
    clear_cache()


def clear_cache() -> None:
    """Drop cached responses."""
    _cache.clear()


def _cache_key(method: str, params: dict | None) -> str:
    return method + "|" + json.dumps(params or {}, sort_keys=True)


def _error_hint(status: int, message: str = "") -> str:
    lowered = message.lower()
    if "invalidapikey" in lowered or "invalid api key" in lowered:
        return (
            "Bing rejected the API key. BING_WEBMASTER_API_KEY must come from "
            "Bing Webmaster Tools -> Settings -> API Access. "
            "The site must also be verified in the same account."
        )
    if "quota" in lowered or "throttl" in lowered:
        return "Bing rate limit or daily quota reached. Wait before retrying."
    if status in (401, 403):
        return (
            "Check BING_WEBMASTER_API_KEY. The key must come from "
            "Bing Webmaster Tools -> Settings -> API Access. "
            "The site must also be verified in the same account."
        )
    if status == 404:
        return (
            "Check the site_url value. Run bing_list_sites to get the exact "
            "URL, including the trailing slash."
        )
    if status == 429:
        return "Bing rate limit or daily quota reached. Wait before retrying."
    if status == 400:
        return "Check the method parameters. Bing rejected the request."
    return ""


def _request(
    method: str,
    params: dict | None = None,
    body: dict | None = None,
    use_cache: bool = True,
) -> Any:
    """Call one Bing Webmaster API method and return normalized data."""
    key = _cache_key(method, params)
    if use_cache and body is None:
        cached = _cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]

    query = dict(params or {})
    query["apikey"] = api_key()
    url = f"{API_BASE}/{method}"

    response: httpx.Response | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(
                timeout=_timeout(), transport=_transport
            ) as client:
                response = client.request(
                    "POST" if body is not None else "GET",
                    url,
                    params=query,
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise BingAPIError(method, None, f"Network error: {exc}") from exc

        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
            continue
        break

    assert response is not None
    if response.status_code >= 400:
        message = _error_message(response)
        raise BingAPIError(
            method,
            response.status_code,
            message,
            _error_hint(response.status_code, message),
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise BingAPIError(method, response.status_code, "Response was not JSON") from exc

    data = payload.get("d") if isinstance(payload, dict) else payload
    result = normalize(data)

    if use_cache and body is None:
        _cache[key] = (time.time() + _cache_ttl(), result)
    return result


def _error_message(response: httpx.Response) -> str:
    """Best-effort error message from a Bing error response."""
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "Unknown error")[:300]
    if isinstance(payload, dict):
        for key in ("error", "message", "Message", "ErrorMessage"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = value.get("message") or value.get("Message")
                if nested:
                    return str(nested)
    return json.dumps(payload)[:300]


# ---------------------------------------------------------------------------
# API methods
# ---------------------------------------------------------------------------

def list_sites() -> list[dict]:
    """List all sites for the authenticated user."""
    return _as_rows(_request("GetUserSites"))


def get_query_stats(site_url: str) -> list[dict]:
    """Top queries with clicks, impressions, and average positions."""
    return _as_rows(_request("GetQueryStats", {"siteUrl": site_url}))


def get_page_stats(site_url: str) -> list[dict]:
    """Top pages with clicks, impressions, and average positions."""
    return _as_rows(_request("GetPageStats", {"siteUrl": site_url}))


def get_rank_and_traffic_stats(site_url: str) -> list[dict]:
    """Daily clicks and impressions for a site."""
    return _as_rows(_request("GetRankAndTrafficStats", {"siteUrl": site_url}))


def get_query_pages(site_url: str, query: str) -> list[dict]:
    """Pages that rank for one query."""
    return _as_rows(
        _request("GetQueryPageStats", {"siteUrl": site_url, "query": query})
    )


def get_page_queries(site_url: str, page: str) -> list[dict]:
    """Queries that a page ranks for."""
    return _as_rows(
        _request("GetPageQueryStats", {"siteUrl": site_url, "page": page})
    )


def get_url_info(site_url: str, url: str) -> dict:
    """Crawl and index details for one URL."""
    data = _request("GetUrlInfo", {"siteUrl": site_url, "url": url})
    return data if isinstance(data, dict) else {}


def get_crawl_stats(site_url: str) -> Any:
    """Crawl statistics for a site."""
    return _request("GetCrawlStats", {"siteUrl": site_url})


def get_crawl_issues(site_url: str) -> list[dict]:
    """Crawl issues reported for a site."""
    return _as_rows(_request("GetCrawlIssues", {"siteUrl": site_url}))


def get_link_counts(site_url: str, page: int = 0) -> Any:
    """Inbound link counts for site pages."""
    return _request("GetLinkCounts", {"siteUrl": site_url, "page": page})


def get_feeds(site_url: str) -> list[dict]:
    """List submitted sitemaps and feeds for a site."""
    return _as_rows(_request("GetFeeds", {"siteUrl": site_url}))


def _normalize_language(language: str, country: str) -> str:
    """Return a Bing IETF language tag such as en-US.

    Bing rejects a bare code like 'en'. When the caller passes one, add the
    country code. When the tag already has a region, keep it.
    """
    language = (language or "").strip()
    country = (country or "").strip().upper()
    if not language:
        language = "en"
    if "-" in language:
        return language
    return f"{language}-{country}" if country else language


def get_keyword_stats(
    query: str,
    country: str = "us",
    language: str = "en-US",
) -> list[dict]:
    """Historical keyword statistics."""
    params = {
        "q": query,
        "country": country.lower(),
        "language": _normalize_language(language, country),
    }
    return _as_rows(_request("GetKeywordStats", params))


def get_related_keywords(
    query: str,
    country: str = "us",
    language: str = "en-US",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Related keywords for a seed term."""
    params: dict[str, Any] = {
        "q": query,
        "country": country.lower(),
        "language": _normalize_language(language, country),
    }
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    return _as_rows(_request("GetRelatedKeywords", params))


# ---------------------------------------------------------------------------
# Google vs Bing query comparison
# ---------------------------------------------------------------------------

def _query_key(row: dict) -> str:
    query = row.get("query", "")
    return str(query).strip().lower()


def compare_queries(
    bing_rows: list[dict],
    gsc_rows: list[dict],
    limit: int = 25,
) -> dict:
    """Join Bing and GSC top-query rows on normalized query text.

    Both inputs use normalized keys: query, clicks, impressions.
    """
    bing_map: dict[str, dict] = {}
    for row in bing_rows:
        key = _query_key(row)
        if key:
            bing_map[key] = row

    gsc_map: dict[str, dict] = {}
    for row in gsc_rows:
        key = _query_key(row)
        if key:
            gsc_map[key] = row

    shared: list[dict] = []
    for key in set(bing_map) & set(gsc_map):
        bing = bing_map[key]
        gsc = gsc_map[key]
        bing_clicks = int(bing.get("clicks", 0) or 0)
        gsc_clicks = int(gsc.get("clicks", 0) or 0)
        bing_position = bing.get("avg_impression_position")
        if bing_position is None:
            bing_position = bing.get("avg_click_position")
        shared.append({
            "query": key,
            "bing_clicks": bing_clicks,
            "gsc_clicks": gsc_clicks,
            "click_gap": bing_clicks - gsc_clicks,
            "bing_impressions": int(bing.get("impressions", 0) or 0),
            "gsc_impressions": int(gsc.get("impressions", 0) or 0),
            "bing_position": bing_position,
            "gsc_position": gsc.get("position"),
        })

    shared.sort(key=lambda item: abs(item["click_gap"]), reverse=True)

    return {
        "shared": shared[:limit],
        "bing_only": sorted(
            bing_map.keys() - gsc_map.keys(),
            key=lambda key: int(bing_map[key].get("clicks", 0) or 0),
            reverse=True,
        )[:limit],
        "gsc_only": sorted(
            gsc_map.keys() - bing_map.keys(),
            key=lambda key: int(gsc_map[key].get("clicks", 0) or 0),
            reverse=True,
        )[:limit],
        "bing_query_count": len(bing_map),
        "gsc_query_count": len(gsc_map),
        "shared_query_count": len(set(bing_map) & set(gsc_map)),
    }
