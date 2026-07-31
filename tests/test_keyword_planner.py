import pytest

from google.ads.googleads.v25.common.types.keyword_plan_common import (
    ConceptGroup,
    KeywordAnnotations,
    KeywordConcept,
    KeywordPlanHistoricalMetrics,
)
from google.ads.googleads.v25.enums.types.keyword_match_type import (
    KeywordMatchTypeEnum,
)
from google.ads.googleads.v25.enums.types.keyword_plan_competition_level import (
    KeywordPlanCompetitionLevelEnum,
)
from google.ads.googleads.v25.services.types.keyword_plan_idea_service import (
    GenerateKeywordHistoricalMetricsResult,
    GenerateKeywordIdeaResult,
)

from open_google_mcp.keyword_planner import (
    LANGUAGE_CONSTANTS,
    build_forecast_request,
    build_historical_request,
    build_ideas_request,
    build_keyword_seed,
    build_url_seed,
    flatten_historical_result,
    flatten_idea_result,
    resolve_language,
)


# --- language resolution ---------------------------------------------------

def test_resolve_language_defaults_to_english():
    assert resolve_language(None) == "languageConstants/1000"
    assert resolve_language("") == "languageConstants/1000"


def test_resolve_language_passthrough_resource_name():
    assert resolve_language("languageConstants/1002") == "languageConstants/1002"


def test_resolve_language_by_name_case_insensitive():
    assert resolve_language("English") == "languageConstants/1000"
    assert resolve_language("german") == "languageConstants/1001"


def test_resolve_language_unknown_raises():
    with pytest.raises(ValueError):
        resolve_language("klingon")


# --- seed builders ---------------------------------------------------------

def test_build_keyword_seed():
    seed = build_keyword_seed(["salsa classes dublin", "salsa dancing"])
    assert list(seed.keywords) == ["salsa classes dublin", "salsa dancing"]


def test_build_url_seed():
    seed = build_url_seed("https://dublinsalsaacademy.com")
    assert seed.url == "https://dublinsalsaacademy.com"


# --- ideas request ---------------------------------------------------------

def test_ideas_request_keyword_seed():
    req = build_ideas_request(
        customer_id="123",
        keywords=["salsa"],
        url=None,
        geos=["geoTargetConstants/2328"],
        language=None,
        network="GOOGLE_SEARCH",
        include_adult_keywords=False,
        page_size=50,
    )
    assert req.customer_id == "123"
    assert req.language == "languageConstants/1000"
    assert list(req.geo_target_constants) == ["geoTargetConstants/2328"]
    assert req.keyword_seed.keywords == ["salsa"]
    assert req._pb.WhichOneof("seed") == "keyword_seed"


def test_ideas_request_url_seed_and_language():
    req = build_ideas_request(
        customer_id="123", keywords=None, url="https://example.com",
        geos=None, language="languageConstants/1002", network=None,
        include_adult_keywords=True, page_size=10,
    )
    assert req.url_seed.url == "https://example.com"
    assert req.language == "languageConstants/1002"
    assert req.include_adult_keywords is True
    assert req.page_size == 10


def test_ideas_request_both_seeds_uses_keyword_and_url():
    req = build_ideas_request(
        customer_id="123", keywords=["salsa"], url="https://example.com",
        geos=None, language=None, network=None, include_adult_keywords=False,
        page_size=50,
    )
    assert req.keyword_and_url_seed.keywords == ["salsa"]
    assert req.keyword_and_url_seed.url == "https://example.com"


def test_ideas_request_no_seed_raises():
    with pytest.raises(ValueError):
        build_ideas_request(
            customer_id="123", keywords=None, url=None, geos=None,
            language=None, network=None, include_adult_keywords=False,
            page_size=50,
        )


# --- historical request ----------------------------------------------------

def test_historical_request():
    req = build_historical_request(
        customer_id="123", keywords=["salsa classes", "salsa dublin"],
        geos=None, language=None, network=None, include_adult_keywords=False,
    )
    assert list(req.keywords) == ["salsa classes", "salsa dublin"]
    assert req.language == "languageConstants/1000"


# --- forecast request ------------------------------------------------------

def test_forecast_request_basic():
    req = build_forecast_request(
        customer_id="123",
        keywords=["salsa classes", "salsa dublin"],
        match_types=None,
        currency_code="EUR",
        start_date="2026-08-01",
        end_date="2026-08-30",
        geos=None, language=None,
        daily_budget_micros=None, max_cpc_bid_micros=None,
    )
    assert req.customer_id == "123"
    assert req.currency_code == "EUR"
    assert req.forecast_period.start_date == "2026-08-01"
    assert req.campaign.language_constants == ["languageConstants/1000"]
    ag = req.campaign.ad_groups[0]
    assert [k.text for k in ag.keywords] == ["salsa classes", "salsa dublin"]
    assert all(
        k.match_type == KeywordMatchTypeEnum.KeywordMatchType.EXACT
        for k in ag.keywords
    )


def test_forecast_request_match_types_and_budget():
    req = build_forecast_request(
        customer_id="123",
        keywords=["salsa classes", "salsa dublin"],
        match_types=["PHRASE", "EXACT"],
        currency_code="EUR",
        start_date="2026-08-01",
        end_date="2026-08-30",
        geos=["geoTargetConstants/2328"], language="german",
        daily_budget_micros=10_000_000, max_cpc_bid_micros=500_000,
    )
    kinds = [k.match_type for k in req.campaign.ad_groups[0].keywords]
    assert kinds[0] == KeywordMatchTypeEnum.KeywordMatchType.PHRASE
    assert kinds[1] == KeywordMatchTypeEnum.KeywordMatchType.EXACT
    manual = req.campaign.bidding_strategy.manual_cpc_bidding_strategy
    assert manual.daily_budget_micros == 10_000_000
    assert manual.max_cpc_bid_micros == 500_000
    assert req.campaign.language_constants == ["languageConstants/1001"]


def test_forecast_request_single_match_type_applies_to_all():
    req = build_forecast_request(
        customer_id="123",
        keywords=["a", "b", "c"],
        match_types=["BROAD"],
        currency_code="EUR",
        start_date="2026-08-01",
        end_date="2026-08-30",
        geos=None, language=None,
        daily_budget_micros=None, max_cpc_bid_micros=None,
    )
    kinds = [k.match_type for k in req.campaign.ad_groups[0].keywords]
    assert all(
        k == KeywordMatchTypeEnum.KeywordMatchType.BROAD for k in kinds
    )


# --- flatteners ------------------------------------------------------------

def _metrics(**overrides):
    base = dict(
        avg_monthly_searches=1200,
        competition=KeywordPlanCompetitionLevelEnum.KeywordPlanCompetitionLevel.HIGH,
        competition_index=85,
        low_top_of_page_bid_micros=100000,
        high_top_of_page_bid_micros=900000,
        average_cpc_micros=450000,
    )
    base.update(overrides)
    return KeywordPlanHistoricalMetrics(**base)


def test_flatten_idea_result():
    result = GenerateKeywordIdeaResult(
        text="salsa classes dublin",
        keyword_idea_metrics=_metrics(),
        keyword_annotations=KeywordAnnotations(
            concepts=[
                KeywordConcept(
                    name="Dance",
                    concept_group=ConceptGroup(name="Arts & Entertainment"),
                )
            ]
        ),
        close_variants=["salsa class dublin"],
    )
    flat = flatten_idea_result(result)
    assert flat["keyword"] == "salsa classes dublin"
    assert flat["avg_monthly_searches"] == 1200
    assert flat["competition"] == "HIGH"
    assert flat["competition_index"] == 85
    assert flat["low_top_of_page_bid_micros"] == 100000
    assert flat["average_cpc_micros"] == 450000
    assert flat["concepts"] == [{"name": "Dance", "group": "Arts & Entertainment"}]
    assert flat["close_variants"] == ["salsa class dublin"]


def test_flatten_idea_result_without_metrics():
    flat = flatten_idea_result(GenerateKeywordIdeaResult(text="salsa"))
    assert flat["keyword"] == "salsa"
    assert flat["avg_monthly_searches"] is None
    assert flat["competition"] is None
    assert flat["concepts"] == []


def test_flatten_historical_result():
    result = GenerateKeywordHistoricalMetricsResult(
        text="salsa classes", keyword_metrics=_metrics(avg_monthly_searches=900),
        close_variants=[],
    )
    flat = flatten_historical_result(result)
    assert flat["keyword"] == "salsa classes"
    assert flat["avg_monthly_searches"] == 900
    assert flat["competition"] == "HIGH"
