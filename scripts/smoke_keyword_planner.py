"""Smoke test for Keyword Planner tools against the live API.

Usage: source .env && .venv/bin/python scripts/smoke_keyword_planner.py [customer_id]

If customer_id is omitted, GOOGLE_ADS_DEFAULT_CUSTOMER_ID / LOGIN_CUSTOMER_ID
from .env is used (same fallback as the tools themselves).
"""
import sys

from open_google_mcp.server import (
    generate_keyword_forecast_metrics,
    generate_keyword_historical_metrics,
    generate_keyword_ideas,
    suggest_geo_target_constants,
)

if __name__ == "__main__":
    customer_id = sys.argv[1] if len(sys.argv) > 1 else None
    print("geo:", suggest_geo_target_constants(names=["United States"], country_code="US"))
    print("ideas:", generate_keyword_ideas(
        customer_id=customer_id,
        keywords=["running shoes"],
        geos=["geoTargetConstants/2840"],
        page_size=5,
    ))
    print("hist:", generate_keyword_historical_metrics(
        customer_id=customer_id,
        keywords=["running shoes", "trail running shoes"],
        geos=["geoTargetConstants/2840"],
    ))
    print("forecast:", generate_keyword_forecast_metrics(
        customer_id=customer_id,
        keywords=["running shoes"],
        match_types=["EXACT"],
        currency_code="USD",
        geos=["geoTargetConstants/2840"],
    ))
