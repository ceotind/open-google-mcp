"""Pure helpers for Google Keyword Planner (google-ads API v25).

Everything in this module is side-effect free and unit-testable without
network access or credentials. The MCP tools in server.py are thin wrappers
around these builders/flatteners.

Types are imported from google.ads.googleads.v25 directly — v25 is the
default API version of google-ads 31.x (see _VALID_API_VERSIONS in
google.ads.googleads.client). If the project ever pins a different default
version, update the imports in this one module.
"""
from __future__ import annotations

from collections.abc import Sequence

from google.ads.googleads.v25.common.types import criteria, dates
from google.ads.googleads.v25.enums.types.keyword_match_type import (
    KeywordMatchTypeEnum,
)
from google.ads.googleads.v25.enums.types.keyword_plan_competition_level import (
    KeywordPlanCompetitionLevelEnum,
)
from google.ads.googleads.v25.enums.types.keyword_plan_network import (
    KeywordPlanNetworkEnum,
)
from google.ads.googleads.v25.services.types import (
    geo_target_constant_service as gtc,
    keyword_plan_idea_service as kp,
)

# Stable language constant IDs (Google Ads API docs, "codes-formats" page).
# https://developers.google.com/google-ads/api/data/codes-formats#languages
LANGUAGE_CONSTANTS = {
    "english": "languageConstants/1000",
    "german": "languageConstants/1001",
    "french": "languageConstants/1002",
    "spanish": "languageConstants/1003",
    "italian": "languageConstants/1004",
    "portuguese": "languageConstants/1005",
    "dutch": "languageConstants/1006",
}

_NETWORK = KeywordPlanNetworkEnum.KeywordPlanNetwork
_MATCH = KeywordMatchTypeEnum.KeywordMatchType
_COMPETITION = KeywordPlanCompetitionLevelEnum.KeywordPlanCompetitionLevel


def resolve_language(language: str | None) -> str:
    """Return a language resource name.

    None/'' -> English; 'languageConstants/1000' -> passthrough;
    'english'/'German' (case-insensitive) -> mapped constant.
    """
    if not language:
        return LANGUAGE_CONSTANTS["english"]
    lang = language.strip()
    if lang.startswith("languageConstants/"):
        return lang
    key = lang.lower()
    if key in LANGUAGE_CONSTANTS:
        return LANGUAGE_CONSTANTS[key]
    raise ValueError(
        f"Unknown language {language!r}. Pass a resource name like "
        "'languageConstants/1000' or one of: "
        + ", ".join(sorted(LANGUAGE_CONSTANTS))
    )


def resolve_network(network: str | None) -> _NETWORK:
    """Map 'GOOGLE_SEARCH'/'GOOGLE_SEARCH_AND_PARTNERS' to the enum."""
    return getattr(
        _NETWORK, network or "GOOGLE_SEARCH_AND_PARTNERS",
        _NETWORK.GOOGLE_SEARCH_AND_PARTNERS,
    )


def build_keyword_seed(keywords: Sequence[str]) -> kp.KeywordSeed:
    return kp.KeywordSeed(keywords=list(keywords))


def build_url_seed(url: str) -> kp.UrlSeed:
    return kp.UrlSeed(url=url)


def build_ideas_request(
    customer_id: str,
    keywords: Sequence[str] | None,
    url: str | None,
    geos: Sequence[str] | None,
    language: str | None,
    network: str | None,
    include_adult_keywords: bool,
    page_size: int,
) -> kp.GenerateKeywordIdeasRequest:
    request = kp.GenerateKeywordIdeasRequest(
        customer_id=customer_id,
        language=resolve_language(language),
        geo_target_constants=list(geos or []),
        include_adult_keywords=include_adult_keywords,
        page_size=max(1, min(page_size, 2000)),
        keyword_plan_network=resolve_network(network),
    )
    if keywords and url:
        request.keyword_and_url_seed = kp.KeywordAndUrlSeed(
            keywords=list(keywords), url=url,
        )
    elif keywords:
        request.keyword_seed = kp.KeywordSeed(keywords=list(keywords))
    elif url:
        request.url_seed = kp.UrlSeed(url=url)
    else:
        raise ValueError(
            "Provide at least one seed: keywords (list of terms) or url."
        )
    return request


def build_historical_request(
    customer_id: str,
    keywords: Sequence[str],
    geos: Sequence[str] | None,
    language: str | None,
    network: str | None,
    include_adult_keywords: bool,
) -> kp.GenerateKeywordHistoricalMetricsRequest:
    return kp.GenerateKeywordHistoricalMetricsRequest(
        customer_id=customer_id,
        keywords=list(keywords),
        geo_target_constants=list(geos or []),
        language=resolve_language(language),
        include_adult_keywords=include_adult_keywords,
        keyword_plan_network=resolve_network(network),
    )


def build_forecast_request(
    customer_id: str,
    keywords: Sequence[str],
    match_types: Sequence[str] | None,
    currency_code: str,
    start_date: str,
    end_date: str,
    geos: Sequence[str] | None,
    language: str | None,
    daily_budget_micros: int | None,
    max_cpc_bid_micros: int | None,
) -> kp.GenerateKeywordForecastMetricsRequest:
    """Assemble an in-memory single-ad-group campaign forecast request.

    match_types: one entry applied to all keywords, or one per keyword.
    Unknown match types fall back to EXACT.
    """
    if match_types and len(match_types) == 1:
        match_types = list(match_types) * len(keywords)
    elif not match_types:
        match_types = ["EXACT"] * len(keywords)

    keywords_info = [
        criteria.KeywordInfo(
            text=kw,
            match_type=getattr(_MATCH, mt, _MATCH.EXACT),
        )
        for kw, mt in zip(keywords, match_types)
    ]

    campaign = kp.CampaignToForecast(
        language_constants=[resolve_language(language)],
        geo_target_constants=list(geos or []),
        ad_groups=[kp.ForecastAdGroup(keywords=keywords_info)],
    )
    if daily_budget_micros is not None or max_cpc_bid_micros is not None:
        campaign.bidding_strategy.manual_cpc_bidding_strategy = (
            kp.ManualCpcBiddingStrategy(
                daily_budget_micros=daily_budget_micros or 0,
                max_cpc_bid_micros=max_cpc_bid_micros or 0,
            )
        )

    return kp.GenerateKeywordForecastMetricsRequest(
        customer_id=customer_id,
        currency_code=currency_code,
        forecast_period=dates.DateRange(start_date=start_date, end_date=end_date),
        campaign=campaign,
    )


def build_geo_suggest_request(
    names: Sequence[str],
    country_code: str | None,
    locale: str,
) -> gtc.SuggestGeoTargetConstantsRequest:
    """Build a SuggestGeoTargetConstantsRequest to search by location names.

    NOTE: location_names is a oneof message field — in proto-plus it must be
    assigned as a whole (unset oneof members read as None, so
    request.location_names.names.extend(...) raises AttributeError).
    """
    request = gtc.SuggestGeoTargetConstantsRequest(
        locale=locale,
        location_names=gtc.SuggestGeoTargetConstantsRequest.LocationNames(
            names=list(names),
        ),
    )
    if country_code:
        request.country_code = country_code
    return request


def _enum_name(value) -> str | None:
    return value.name if value else None


def _metrics_dict(metrics) -> dict:
    """Map a KeywordPlanHistoricalMetrics message to a clean dict."""
    if metrics is None or not metrics._pb.ListFields():
        return {
            "avg_monthly_searches": None,
            "competition": None,
            "competition_index": None,
            "low_top_of_page_bid_micros": None,
            "high_top_of_page_bid_micros": None,
            "average_cpc_micros": None,
        }
    return {
        "avg_monthly_searches": metrics.avg_monthly_searches,
        "competition": _enum_name(metrics.competition),
        "competition_index": metrics.competition_index,
        "low_top_of_page_bid_micros": metrics.low_top_of_page_bid_micros,
        "high_top_of_page_bid_micros": metrics.high_top_of_page_bid_micros,
        "average_cpc_micros": metrics.average_cpc_micros,
    }


def _concepts_dict(annotations) -> list[dict]:
    if not annotations or not annotations.concepts:
        return []
    return [
        {
            "name": c.name,
            "group": c.concept_group.name if c.concept_group else "",
        }
        for c in annotations.concepts
    ]


def flatten_idea_result(result) -> dict:
    return {
        "keyword": result.text,
        **_metrics_dict(result.keyword_idea_metrics),
        "concepts": _concepts_dict(result.keyword_annotations),
        "close_variants": list(result.close_variants),
    }


def flatten_historical_result(result) -> dict:
    return {
        "keyword": result.text,
        **_metrics_dict(result.keyword_metrics),
        "close_variants": list(result.close_variants),
    }


def flatten_forecast_response(response) -> dict:
    """Flatten GenerateKeywordForecastMetricsResponse.

    NOTE: verify attribute names against the installed package once the
    first live call works (dir(response.campaign_forecast_metrics)):
    expected fields impressions, clicks, ctr, average_cpc, cost_micros.
    """
    m = response.campaign_forecast_metrics
    flat = {
        "impressions": getattr(m, "impressions", None),
        "clicks": getattr(m, "clicks", None),
        "ctr": round(getattr(m, "ctr", 0), 4),
        "average_cpc_micros": getattr(m, "average_cpc", None),
        "cost_micros": getattr(m, "cost_micros", None),
    }
    ad_groups = []
    for ag in getattr(response, "ad_group_forecast_metrics", []) or []:
        ad_groups.append({
            "impressions": getattr(ag, "impressions", None),
            "clicks": getattr(ag, "clicks", None),
            "ctr": round(getattr(ag, "ctr", 0), 4),
            "average_cpc_micros": getattr(ag, "average_cpc", None),
            "cost_micros": getattr(ag, "cost_micros", None),
        })
    if ad_groups:
        flat["ad_groups"] = ad_groups
    return flat


def flatten_geo_suggestions(response) -> list[dict]:
    out = []
    for s in response.geo_target_constant_suggestions:
        g = s.geo_target_constant
        out.append({
            "resource_name": g.resource_name,
            "name": g.name,
            "country_code": g.country_code,
            "target_type": g.target_type,
            "parents": [p.name for p in (s.geo_target_constant_parents or [])],
        })
    return out
