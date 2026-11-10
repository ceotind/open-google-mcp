import json
import os
import sys
import traceback
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from google.ads.googleads.errors import GoogleAdsException
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    OrderBy,
    RunRealtimeReportRequest,
    RunReportRequest,
)
from googleapiclient.errors import HttpError
from google.protobuf.json_format import MessageToDict
from mcp.server.fastmcp import FastMCP

from . import bing_client
from . import client as ads_client
from . import ga4_client
from . import gsc_client
from . import keyword_planner

mcp = FastMCP("Open Google MCP")


def _log_exc(context: str) -> None:
    """Log full traceback to stderr so real errors are never masked."""
    print(f"[open-google-mcp] ERROR in {context}:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)


def _flatten(d: dict, parent_key: str = "") -> dict:
    items: dict = {}
    for k, v in d.items():
        new_key = f"{parent_key}{k}" if not parent_key else f"{parent_key}.{k}"
        if isinstance(v, dict):
            items.update(_flatten(v, new_key))
        else:
            items[new_key] = v
    return items


def _handle_google_ads_error(e: GoogleAdsException) -> str:
    parts = []
    parts.append(f"Request ID: {e.request_id}")
    for error in e.failure.errors:
        ec_str = "UNKNOWN"
        for field in error.error_code._pb.DESCRIPTOR.fields:
            val = getattr(error.error_code, field.name, None)
            if val and val != 0:
                ec_str = f"{field.name}={val}"
                break
        parts.append(f"Google Ads API Error [{ec_str}]: {error.message}")
    return "\n".join(parts)


def _run_gaql(
    client,
    ga_service,
    customer_id: str,
    query: str,
) -> list[dict]:
    """Execute a GAQL query and return flattened results."""
    request = client.get_type("SearchGoogleAdsRequest")
    request.customer_id = customer_id
    request.query = query

    response = ga_service.search(request=request)
    results: list[dict] = []
    for row in response:
        pb = row._pb if hasattr(row, "_pb") else row
        raw = MessageToDict(pb, preserving_proto_field_name=True)
        results.append(_flatten(raw))
    return results


def _is_manager_account(client, customer_id: str) -> bool | None:
    """Check if the given customer_id is a manager account.
    
    Returns True/False, or None if the check fails.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        results = _run_gaql(
            client, ga_service, customer_id,
            "SELECT customer.id, customer.manager, customer.descriptive_name FROM customer LIMIT 1",
        )
        if results:
            return bool(results[0].get("customer.manager", False))
        return None
    except Exception:
        _log_exc(f"is_manager_account check for {customer_id}")
        return None


def _get_child_accounts(client, customer_id: str) -> list[dict]:
    """Get child accounts under a manager account.
    
    Returns a list of dicts with customer_client.id and customer_client.descriptive_name.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        results = _run_gaql(
            client, ga_service, customer_id,
            "SELECT customer_client.id, customer_client.descriptive_name, "
            "customer_client.manager, customer_client.status "
            "FROM customer_client WHERE customer_client.status = 'ENABLED' "
            "AND customer_client.manager = FALSE LIMIT 100",
        )
        return results
    except Exception:
        _log_exc(f"get_child_accounts for {customer_id}")
        return []


def _is_manager_metrics_error(e: Exception) -> bool:
    """Return True when Google Ads rejected metrics on a manager account."""
    failure = getattr(e, "failure", None)
    for err in getattr(failure, "errors", None) or []:
        code = getattr(err, "error_code", None)
        try:
            if int(getattr(code, "query_error", 0)) == 59:
                return True
        except (TypeError, ValueError):
            continue
    return "manager account" in str(e).lower()


_ACCOUNT_LEVEL_RESOURCES = {
    "campaign", "ad_group", "ad_group_ad", "ad_group_criterion",
    "keyword_view", "search_term_view", "bidding_strategy",
    "campaign_budget", "campaign_criterion", "customer_client",
    "geographic_view", "user_interest", "user_list",
}


def _route_to_children(client, ga_service, customer_id: str, query: str) -> list[dict]:
    """Run a query against each child account of a manager account.

    Returns annotated rows, or an empty list when the account is not a manager
    or when no child account returns rows.
    """
    if not _is_manager_account(client, customer_id):
        return []

    results: list[dict] = []
    for child in _get_child_accounts(client, customer_id):
        child_id = child.get("customer_client.id", "")
        child_name = child.get("customer_client.descriptive_name", child_id)
        if not child_id:
            continue
        try:
            child_rows = _run_gaql(client, ga_service, child_id, query)
        except Exception:
            _log_exc(f"child query for {child_id}")
            continue
        for row in child_rows:
            row["_source_customer_id"] = child_id
            row["_source_customer_name"] = child_name
        results.extend(child_rows)

    if results:
        results.insert(0, {
            "_note": "Manager account detected. Results auto-routed from child accounts.",
        })
    return results


@mcp.tool()
def list_accessible_customers() -> list[str]:
    """**Start here** — Discover Google Ads customer IDs accessible by the
    authenticated user. Always call this first before search(). Returns
    resource names like 'customers/1234567890' — extract the numeric ID
    from the last segment to use in other tools.
    """
    try:
        client = ads_client.get_client()
        service = client.get_service("CustomerService")
        accessible = service.list_accessible_customers()
        return list(accessible.resource_names)
    except GoogleAdsException as e:
        _log_exc("list_accessible_customers")
        return [_handle_google_ads_error(e)]
    except ValueError as e:
        _log_exc("list_accessible_customers")
        return [str(e)]


@mcp.tool()
def get_resource_metadata(
    resource_name: str,
) -> dict:
    """Discover which fields are SELECTable, FILTERable, and SORTable for a
    Google Ads resource. **Always call this before search()** — using incorrect
    field names causes API errors. Compatible metrics.* and segments.* fields
    are included for reporting queries.

    Args:
        resource_name: The resource to explore (e.g. 'campaign', 'ad_group',
                       'keyword_view', 'search_term_view', 'customer_client').

    Returns:
        A dict with resource name and three sorted arrays of fully-qualified
        field names. Example for resource='campaign':
          selectable: ['campaign.id', 'campaign.name', 'campaign.status',
                       'metrics.clicks', 'metrics.impressions', ...]
          filterable: ['campaign.id', 'campaign.status', ...]
          sortable: ['campaign.id', 'metrics.clicks', ...]
    """
    try:
        client = ads_client.get_client()
        field_service = client.get_service("GoogleAdsFieldService")

        selectable: list[str] = []
        filterable: list[str] = []
        sortable: list[str] = []

        for prefix in [resource_name, f"{resource_name}.", "metrics.", "segments."]:
            sr = client.get_type("SearchGoogleAdsFieldsRequest")
            sr.query = (
                f"SELECT name, selectable, filterable, sortable "
                f"WHERE name LIKE '{prefix}%'"
            )
            try:
                response = field_service.search_google_ads_fields(sr)
                for row in response:
                    if row.selectable:
                        selectable.append(row.name)
                    if row.filterable:
                        filterable.append(row.name)
                    if row.sortable:
                        sortable.append(row.name)
            except GoogleAdsException:
                _log_exc(f"get_resource_metadata prefix={prefix!r}")

        return {
            "resource": resource_name,
            "selectable": sorted(selectable),
            "filterable": sorted(filterable),
            "sortable": sorted(sortable),
        }
    except GoogleAdsException as e:
        _log_exc("get_resource_metadata")
        return {"error": _handle_google_ads_error(e)}
    except ValueError as e:
        _log_exc("get_resource_metadata")
        return {"error": str(e)}


@mcp.tool()
def search(
    customer_id: str,
    resource: str,
    fields: Sequence[str],
    conditions: Sequence[str] | None = None,
    orderings: Sequence[str] | None = None,
    limit: int | None = 100,
) -> list[dict]:
    """Execute a read-only GAQL query and return flattened results.
    **Workflow:** list_accessible_customers() → get_resource_metadata(resource) → search()

    If customer_id is a **manager (MCC) account**, this auto-routes to child
    accounts and annotates results with _source_customer_id and
    _source_customer_name — no manual child enumeration needed.

    Field rules:
    - Use fully-qualified names: campaign.id (not id), metrics.clicks, segments.date
    - Dates: YYYY-MM-DD format with dashes
    - Relative ranges: DURING LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, THIS_QUARTER
    - Conditions are AND-combined
    - Ordering: 'field_name DIRECTION' (e.g. 'metrics.clicks DESC')
    - For change_event resource, limit max is 10000

    Common conditions:
      campaign.status = 'ENABLED'
      campaign.advertising_channel_type = 'SEARCH'
      segments.date DURING LAST_30_DAYS
      metrics.impressions > 1000

    Example — active campaigns with performance:
      customer_id='1234567890', resource='campaign',
      fields=['campaign.id', 'campaign.name', 'campaign.status',
        'metrics.clicks', 'metrics.impressions', 'metrics.cost_micros'],
      conditions=["campaign.status = 'ENABLED'", 'segments.date DURING LAST_7_DAYS'],
      orderings=['metrics.clicks DESC'], limit=10

    Args:
        customer_id: Numeric Google Ads customer ID (e.g. '1234567890').
                     Manager (MCC) accounts are auto-detected and routed.
        resource: GAQL resource name (e.g. 'campaign', 'ad_group', 'keyword_view').
        fields: Fully-qualified field names to SELECT.
        conditions: WHERE clauses joined with AND (optional).
        orderings: ORDER BY clauses (optional).
        limit: Max results (default: 100, max varies by resource).
    """
    _conditions = conditions or []
    _orderings = orderings or []

    select_clause = ", ".join(fields)
    query = f"SELECT {select_clause} FROM {resource}"

    if _conditions:
        query += f" WHERE {' AND '.join(_conditions)}"

    if _orderings:
        query += f" ORDER BY {', '.join(_orderings)}"

    if limit is not None:
        query += f" LIMIT {limit}"

    try:
        client = ads_client.get_client()
        ga_service = client.get_service("GoogleAdsService")

        results = _run_gaql(client, ga_service, customer_id, query)

        if not results and resource in _ACCOUNT_LEVEL_RESOURCES:
            results = _route_to_children(client, ga_service, customer_id, query)

        return results
    except GoogleAdsException as e:
        _log_exc(f"search query={query!r}")
        if resource in _ACCOUNT_LEVEL_RESOURCES and _is_manager_metrics_error(e):
            try:
                client = ads_client.get_client()
                ga_service = client.get_service("GoogleAdsService")
                routed = _route_to_children(client, ga_service, customer_id, query)
                if routed:
                    return routed
            except Exception:
                _log_exc("manager auto-routing fallback failed")
        return [{"error": _handle_google_ads_error(e)}]
    except Exception as e:
        _log_exc(f"search query={query!r}")
        return [{"error": f"{type(e).__name__}: {e}"}]


# ---------------------------------------------------------------------------
# Google Search Console tools
# ---------------------------------------------------------------------------

def _gsc_handle_error(context: str, e: Exception) -> dict:
    _log_exc(context)
    if isinstance(e, HttpError):
        status = e.resp.status
        body = json.loads(e.content.decode()) if e.content else {}
        error_info = body.get("error", {})
        msg = error_info.get("message", str(e))
        reason = error_info.get("errors", [{}])[0].get("reason", "")
        if status == 403 and "insufficientPermissions" in reason:
            return {
                "error": "Access denied. The service account or user needs to be added "
                         "to this GSC property (Search Console → Settings → Users and "
                         "permissions → Add user)."
            }
        if status == 404:
            return {
                "error": f"Property not found. Run gsc_list_properties to get the exact "
                         f"site_url value — it might be 'sc-domain:example.com' instead "
                         f"of 'https://example.com/'."
            }
        if status == 429:
            return {
                "error": "GSC API rate limit exceeded. Wait a moment before retrying."
            }
        return {"error": f"GSC API Error (HTTP {status}): {msg}"}
    if isinstance(e, ValueError):
        return {"error": str(e)}
    return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gsc_get_capabilities() -> str:
    """Get a categorized list of all available GSC tools and authentication status.
    Call this first if you're unsure which GSC tool to use, whether the server
    is authenticated, or what tools are available. Faster than searching individually.
    """
    try:
        gsc_client.get_service()
        auth = "Connected"
    except Exception as e:
        auth = f"Not connected — {e}"

    return (
        "Google Search Console Tools\n\n"
        f"Auth status: {auth}\n\n"
        "Start with:  gsc_list_properties  (to get site_url values)\n\n"
        "Discovery:\n"
        "  gsc_list_properties    — List all GSC properties (always start here)\n"
        "  gsc_get_site_details   — Verification/ownership for a specific property\n\n"
        "Analytics:\n"
        "  gsc_get_search_analytics          — Top queries/pages (quick overview)\n"
        "  gsc_get_performance_overview      — Executive summary with daily trend\n"
        "  gsc_compare_search_periods        — Month-over-month or week-over-week\n"
        "  gsc_get_advanced_search_analytics — Filtered, sorted, paginated (deep dive)\n\n"
        "Indexing:\n"
        "  gsc_inspect_url — Debug a single URL's crawl/index/rich result status\n\n"
        "Sitemaps:\n"
        "  gsc_get_sitemaps — View sitemaps, errors, and indexed URL counts"
    )


@mcp.tool()
def gsc_list_properties() -> dict:
    """**Start here** — Discover all GSC properties the user has access to.

    Returns the exact site_url strings needed by every other GSC tool.
    Always call this first before using any other GSC tool.
    """
    try:
        service = gsc_client.get_service()
        site_list = service.sites().list().execute()
        sites = site_list.get("siteEntry", [])
        return {
            "count": len(sites),
            "properties": [
                {
                    "site_url": s.get("siteUrl", "Unknown"),
                    "permission_level": s.get("permissionLevel", "Unknown"),
                }
                for s in sites
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_list_properties", e)


@mcp.tool()
def gsc_get_site_details(site_url: str) -> dict:
    """Get verification status and ownership details for a specific GSC property.
    Use this to check permission level, verification method, and ownership info.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' (URL-prefix) or
                  'sc-domain:example.com' (domain property).
    """
    try:
        service = gsc_client.get_service()
        info = service.sites().get(siteUrl=site_url).execute()
        return {
            "site_url": site_url,
            "permission_level": info.get("permissionLevel", "Unknown"),
        }
    except Exception as e:
        return _gsc_handle_error("gsc_get_site_details", e)


@mcp.tool()
def gsc_get_search_analytics(
    site_url: str,
    days: int = 28,
    dimensions: str = "query",
    row_limit: int = 20,
) -> dict:
    """Get top-performing queries and pages with clicks, impressions, CTR, position.
    **Use this for:** identifying high-value keywords, tracking rank changes, finding
    low-CTR opportunities. For filtered or paginated queries, use
    gsc_get_advanced_search_analytics instead. For an executive summary, use
    gsc_get_performance_overview.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
        days: How many days to look back (default: 28).
        dimensions: Group results by — 'query', 'page', 'device', 'country', 'date',
                    or any comma-separated combination (e.g. 'query,device').
        row_limit: Max rows to return (default: 20, max: 500). Use 5-10 for quick
                   overviews, 50-200 for deeper analysis.
    """
    try:
        service = gsc_client.get_service()
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        dims = [d.strip() for d in dimensions.split(",")]

        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": dims,
            "rowLimit": min(max(1, row_limit), 500),
        }

        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        rows = response.get("rows", [])

        return {
            "site_url": site_url,
            "date_range": {"start": start_date.strftime("%Y-%m-%d"), "end": end_date.strftime("%Y-%m-%d")},
            "dimensions": dims,
            "row_count": len(rows),
            "rows": [
                {
                    **{dims[i]: row.get("keys", [])[i] for i in range(len(dims))},
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": round(row.get("ctr", 0), 4),
                    "position": round(row.get("position", 0), 1),
                }
                for row in rows
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_get_search_analytics", e)


@mcp.tool()
def gsc_get_performance_overview(site_url: str, days: int = 28) -> dict:
    """Get an executive summary with daily trend — totals for clicks, impressions,
    CTR, and avg position plus a day-by-day breakdown.
    **Use this for:** quick snapshots, dashboards, spotting traffic spikes or drops.
    For detailed query-level data, use gsc_get_search_analytics.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
        days: How many days to look back (default: 28).
    """
    try:
        service = gsc_client.get_service()
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        totals_body = {
            "startDate": start_str,
            "endDate": end_str,
            "dimensions": [],
            "rowLimit": 1,
        }
        totals_resp = service.searchanalytics().query(siteUrl=site_url, body=totals_body).execute()
        totals_row = totals_resp.get("rows", [{}])[0]

        date_body = {
            "startDate": start_str,
            "endDate": end_str,
            "dimensions": ["date"],
            "rowLimit": days,
        }
        date_resp = service.searchanalytics().query(siteUrl=site_url, body=date_body).execute()

        return {
            "site_url": site_url,
            "date_range": {"start": start_str, "end": end_str, "days": days},
            "totals": {
                "clicks": totals_row.get("clicks", 0),
                "impressions": totals_row.get("impressions", 0),
                "ctr": round(totals_row.get("ctr", 0), 4),
                "position": round(totals_row.get("position", 0), 1),
            },
            "daily_trend": [
                {
                    "date": row["keys"][0],
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": round(row.get("ctr", 0), 4),
                    "position": round(row.get("position", 0), 1),
                }
                for row in sorted(date_resp.get("rows", []), key=lambda x: x["keys"][0])
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_get_performance_overview", e)


@mcp.tool()
def gsc_compare_search_periods(
    site_url: str,
    period1_start: str,
    period1_end: str,
    period2_start: str,
    period2_end: str,
    dimensions: str = "query",
    limit: int = 10,
) -> dict:
    """Compare search performance between two date ranges and surface what changed.
    **Use this for:** month-over-month analysis, campaign impact assessment,
    seasonal trend detection. Returns which queries improved or declined with
    click/impression changes.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
        period1_start: Start of baseline period, format YYYY-MM-DD (e.g. '2026-01-01').
        period1_end: End of baseline period, format YYYY-MM-DD (e.g. '2026-01-31').
        period2_start: Start of comparison period, format YYYY-MM-DD (e.g. '2026-02-01').
        period2_end: End of comparison period, format YYYY-MM-DD (e.g. '2026-02-28').
        dimensions: Group by — 'query', 'page', 'device', etc. (default: 'query').
        limit: Max items to return, sorted by biggest change (default: 10).
    """
    try:
        service = gsc_client.get_service()
        dims = [d.strip() for d in dimensions.split(",")]

        def fetch(start: str, end: str) -> list:
            body = {
                "startDate": start,
                "endDate": end,
                "dimensions": dims,
                "rowLimit": 1000,
            }
            resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
            return resp.get("rows", [])

        p1_rows = fetch(period1_start, period1_end)
        p2_rows = fetch(period2_start, period2_end)

        def build_map(rows):
            return {
                tuple(r.get("keys", [])): {
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "ctr": round(r.get("ctr", 0), 4),
                    "position": round(r.get("position", 0), 1),
                }
                for r in rows
            }

        p1_map = build_map(p1_rows)
        p2_map = build_map(p2_rows)

        all_keys = list(dict.fromkeys(list(p1_map.keys()) + list(p2_map.keys())))

        rows = []
        for key in all_keys:
            d1 = p1_map.get(key, {})
            d2 = p2_map.get(key, {})
            labels = [str(k) for k in key]
            rows.append({
                "key": labels if len(labels) > 1 else labels[0],
                "period1": d1,
                "period2": d2,
                "clicks_change": (d2.get("clicks", 0) or 0) - (d1.get("clicks", 0) or 0),
                "impressions_change": (d2.get("impressions", 0) or 0) - (d1.get("impressions", 0) or 0),
            })

        rows.sort(key=lambda r: abs(r.get("clicks_change", 0)), reverse=True)

        return {
            "site_url": site_url,
            "period1": {"start": period1_start, "end": period1_end},
            "period2": {"start": period2_start, "end": period2_end},
            "dimensions": dims,
            "row_count": len(rows),
            "rows": rows[:limit],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_compare_search_periods", e)


@mcp.tool()
def gsc_get_advanced_search_analytics(
    site_url: str,
    start_date: str | None = None,
    end_date: str | None = None,
    dimensions: str = "query",
    search_type: Literal["WEB", "IMAGE", "VIDEO", "NEWS", "DISCOVER"] = "WEB",
    row_limit: int = 100,
    start_row: int = 0,
    sort_by: Literal["clicks", "impressions", "ctr", "position"] = "clicks",
    sort_direction: Literal["ascending", "descending"] = "descending",
    filters: str | None = None,
) -> dict:
    """Full-featured search analytics with filtering, sorting, pagination (up to 25K rows).
    **Use this for:** deep analysis with country/device/page filters, large bulk exports,
    custom sort orders. For a quick top-N view without filters, use gsc_get_search_analytics
    instead — it returns faster with less overhead.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
        start_date: Start date YYYY-MM-DD (default: 28 days ago).
        end_date: End date YYYY-MM-DD (default: today).
        dimensions: Group by — comma-separated: query, page, device, country, date.
        search_type: Which search vertical to query (default: WEB).
        row_limit: Max rows to return (max 25000, default: 100). Use with start_row
                   for pagination: first call 100, then 100, then 200... via start_row.
        start_row: Row offset for pagination (default: 0).
        sort_by: Metric to sort results by (default: clicks).
        sort_direction: ascending or descending (default: descending).
        filters: JSON array of filter objects for AND logic across dimensions.
                 Each object: {"dimension": "...", "operator": "...", "expression": "..."}
                 Valid dimensions: query, page, country, device.
                 Valid operators: contains, equals, notContains, notEquals.
                 Example: '[{"dimension":"country","operator":"equals","expression":"usa"},
                            {"dimension":"device","operator":"equals","expression":"MOBILE"}]'
    """
    try:
        service = gsc_client.get_service()
        end = end_date or datetime.now().date().strftime("%Y-%m-%d")
        start = start_date or (datetime.now().date() - timedelta(days=28)).strftime("%Y-%m-%d")
        dims = [d.strip() for d in dimensions.split(",")]

        metric_map = {
            "clicks": "CLICK_COUNT",
            "impressions": "IMPRESSION_COUNT",
            "ctr": "CTR",
            "position": "POSITION",
        }

        body: dict = {
            "startDate": start,
            "endDate": end,
            "dimensions": dims,
            "rowLimit": min(row_limit, 25000),
            "startRow": start_row,
            "searchType": search_type.upper(),
        }

        if sort_by in metric_map:
            body["orderBy"] = [{
                "metric": metric_map[sort_by],
                "direction": sort_direction.lower(),
            }]

        if filters:
            filter_list = json.loads(filters) if isinstance(filters, str) else filters
            body["dimensionFilterGroups"] = [{"filters": filter_list}]

        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        rows = response.get("rows", [])

        return {
            "site_url": site_url,
            "date_range": {"start": start, "end": end},
            "search_type": search_type,
            "dimensions": dims,
            "pagination": {
                "start_row": start_row,
                "row_count": len(rows),
                "has_more": len(rows) == row_limit,
            },
            "rows": [
                {
                    **{dims[i]: row.get("keys", [])[i] for i in range(len(dims))},
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": round(row.get("ctr", 0), 4),
                    "position": round(row.get("position", 0), 1),
                }
                for row in rows
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_get_advanced_search_analytics", e)


@mcp.tool()
def gsc_inspect_url(site_url: str, page_url: str) -> dict:
    """Debug a single URL's indexing status — checks coverage state, crawl date,
    canonical URL, robots.txt allow/block, page fetch success, and rich results.
    **Use this for:** diagnosing why a page isn't ranking, checking if Google can
    crawl a new page, verifying canonical URLs, or troubleshooting indexing issues.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
        page_url: The full URL to inspect, e.g. 'https://example.com/blog/post'.
    """
    try:
        service = gsc_client.get_service()
        body = {"inspectionUrl": page_url, "siteUrl": site_url}
        response = service.urlInspection().index().inspect(body=body).execute()
        result = response.get("inspectionResult", {})

        index_status = result.get("indexStatusResult", {})
        rich_results = result.get("richResultsResult", {})

        return {
            "page_url": page_url,
            "site_url": site_url,
            "verdict": index_status.get("verdict", "UNKNOWN"),
            "coverage_state": index_status.get("coverageState"),
            "indexing_state": index_status.get("indexingState"),
            "page_fetch_state": index_status.get("pageFetchState"),
            "robots_txt_state": index_status.get("robotsTxtState"),
            "google_canonical": index_status.get("googleCanonical"),
            "user_canonical": index_status.get("userCanonical"),
            "crawled_as": index_status.get("crawledAs"),
            "rich_result_verdict": rich_results.get("verdict"),
            "rich_result_types": [
                item.get("richResultType")
                for item in rich_results.get("detectedItems", [])
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_inspect_url", e)


@mcp.tool()
def gsc_get_sitemaps(site_url: str) -> dict:
    """List all sitemaps for a GSC property with submission status, error/warning
    counts, and indexed URL totals.
    **Use this for:** monitoring crawl health, finding sitemap errors, checking if
    new content was picked up, verifying sitemap submission.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties.
                  Format: 'https://example.com/' or 'sc-domain:example.com'.
    """
    try:
        service = gsc_client.get_service()
        sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
        items = sitemaps.get("sitemap", [])

        return {
            "site_url": site_url,
            "count": len(items),
            "sitemaps": [
                {
                    "path": s.get("path", "Unknown"),
                    "last_downloaded": s.get("lastDownloaded"),
                    "errors": int(s.get("errors", 0)),
                    "warnings": int(s.get("warnings", 0)),
                    "submitted": _sum_submitted(s.get("contents", [])),
                }
                for s in items
            ],
        }
    except Exception as e:
        return _gsc_handle_error("gsc_get_sitemaps", e)


def _sum_submitted(contents: list) -> int:
    total = 0
    for c in contents:
        if c.get("type") == "web":
            val = c.get("submitted", 0)
            total += int(val) if val else 0
    return total


# ---------------------------------------------------------------------------
# Google Analytics 4 (GA4) tools
# ---------------------------------------------------------------------------

def _ga4_handle_error(context: str, e: Exception) -> dict:
    _log_exc(context)
    msg = f"{type(e).__name__}: {e}"
    if "PERMISSION_DENIED" in msg:
        return {
            "error": "Access denied. Add the service account email to your GA4 "
                     "property (Admin → Account Access Management → Add user → Viewer)."
        }
    if "not found" in msg.lower() or "NOT_FOUND" in msg:
        return {
            "error": "Property not found. Check the property ID is correct and you "
                     "have access. Use ga4_list_properties to discover your IDs."
        }
    return {"error": msg}


def _parse_dimensions(dims_str: str | None) -> list[Dimension] | None:
    """Parse comma-separated dimension names into Dimension objects."""
    if not dims_str:
        return None
    return [Dimension(name=d.strip()) for d in dims_str.split(",")]


def _parse_metrics(metrics_str: str | None) -> list[Metric] | None:
    """Parse comma-separated metric names into Metric objects."""
    if not metrics_str:
        return None
    return [Metric(name=m.strip()) for m in metrics_str.split(",")]


def _parse_filter_json(filter_json: str | dict | list | None) -> FilterExpression | None:
    """Parse a JSON filter string or object into a GA4 FilterExpression.

    Expected format:
      {"field": "dimensionName", "type": "string_filter", "value": "some_value",
       "match_type": "EXACT|CONTAINS|BEGINS_WITH|ENDS_WITH|NUMERIC_EQUAL|NUMERIC_GREATER_THAN|NUMERIC_LESS_THAN"}

    Or an array of such filters (AND-combined).
    """
    if not filter_json:
        return None
    import json
    filters_data = json.loads(filter_json) if isinstance(filter_json, str) else filter_json
    if isinstance(filters_data, dict):
        filters_data = [filters_data]

    expressions = []
    for f in filters_data:
        field = f.get("field", "")
        ftype = f.get("type", "string_filter")
        value = f.get("value", "")
        match_type = f.get("match_type", "EXACT")

        if ftype == "string_filter":
            expressions.append(
                FilterExpression(
                    filter=Filter(
                        field_name=field,
                        string_filter=Filter.StringFilter(
                            match_type=match_type,
                            value=value,
                        ),
                    )
                )
            )
        elif ftype == "numeric_filter":
            op = getattr(Filter.NumericFilter.Operation, match_type, Filter.NumericFilter.Operation.EQUAL)
            expressions.append(
                FilterExpression(
                    filter=Filter(
                        field_name=field,
                        numeric_filter=Filter.NumericFilter(
                            operation=op,
                            value=Filter.NumericValue(int64_value=int(value)),
                        ),
                    )
                )
            )

    if len(expressions) == 1:
        return expressions[0]
    return FilterExpression(
        and_group=FilterExpressionList(expressions=expressions)
    )


def _parse_order_bys(order_json: str | list | None) -> list[OrderBy] | None:
    """Parse JSON order-by config into OrderBy objects.

    Format: [{"metric": "metricName", "desc": true}, {"dimension": "dimName", "desc": false}]
    """
    if not order_json:
        return None
    import json
    orders = json.loads(order_json) if isinstance(order_json, str) else order_json
    result = []
    for o in orders:
        if "metric" in o:
            result.append(
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name=o["metric"]),
                    desc=o.get("desc", True),
                )
            )
        elif "dimension" in o:
            result.append(
                OrderBy(
                    dimension=OrderBy.DimensionOrderBy(dimension_name=o["dimension"]),
                    desc=o.get("desc", True),
                )
            )
    return result or None


def _ga4_rows_to_dicts(
    response,
    dim_names: list[str],
    metric_names: list[str],
) -> list[dict]:
    """Convert GA4 API response rows to flat dicts."""
    results = []
    for row in response.rows:
        item = {}
        for i, dim_val in enumerate(row.dimension_values):
            item[dim_names[i]] = dim_val.value
        for i, met_val in enumerate(row.metric_values):
            item[metric_names[i]] = met_val.value
        results.append(item)
    return results


@mcp.tool()
def ga4_get_capabilities() -> str:
    """Get a categorized list of all available GA4 tools and authentication status.
    Call this first to discover available tools and verify auth is working.
    """
    try:
        ga4_client.get_client()
        auth = "Connected"
    except Exception as e:
        auth = f"Not connected — {e}"

    return (
        "Google Analytics 4 (GA4) Tools\n\n"
        f"Auth status: {auth}\n\n"
        "Start with:  ga4_list_properties  (to discover your property IDs)\n\n"
        "Discovery:\n"
        "  ga4_list_properties    — List all accessible GA4 properties\n"
        "  ga4_get_metadata       — Browse available dimensions and metrics\n\n"
        "Reporting:\n"
        "  ga4_run_report         — Full report with dimensions, metrics, filters\n"
        "  ga4_run_realtime_report— Last 30 minutes of real-time data\n\n"
        "Filters:\n"
        '  JSON format: {"field": "dimensionName", "type": "string_filter",\n'
        '                "value": "text", "match_type": "EXACT|CONTAINS|BEGINS_WITH"}\n'
        "  Numeric filters: type=\"numeric_filter\", match_type=\"EQUAL|GREATER_THAN|LESS_THAN\"\n\n"
        "Property IDs are numeric (e.g., '123456789') — discover them with ga4_list_properties."
    )


@mcp.tool()
def ga4_list_properties() -> dict:
    """**Start here** — Discover all GA4 properties the service account has access to.

    Returns property IDs, display names, and currency/timezone info.
    Use the numeric 'property_id' from the results in all other GA4 tools.
    """
    try:
        from google.analytics.admin_v1beta import AnalyticsAdminServiceClient

        creds = ga4_client.load_service_account_creds()
        if creds:
            admin_client = AnalyticsAdminServiceClient(credentials=creds)
        else:
            admin_client = AnalyticsAdminServiceClient()

        account_summaries = admin_client.list_account_summaries()
        properties = []
        for summary in account_summaries:
            for prop in summary.property_summaries:
                # property name is "properties/123456789"
                prop_id = prop.property.split("/")[-1] if prop.property else ""
                properties.append({
                    "property_id": prop_id,
                    "display_name": prop.display_name,
                    "property": prop.property,
                    "property_type": str(prop.property_type) if prop.property_type else "",
                })

        return {
            "count": len(properties),
            "properties": properties,
        }
    except ImportError:
        return {
            "error": "Admin API library not installed. Install with: pip install google-analytics-admin",
            "hint": "Set GA4_PROPERTY_ID in .env and use ga4_run_report directly.",
        }
    except Exception as e:
        return _ga4_handle_error("ga4_list_properties", e)


@mcp.tool()
def ga4_get_metadata(property_id: str) -> dict:
    """Discover available dimensions and metrics for a GA4 property.
    **Use this before ga4_run_report** to find valid dimension/metric names.

    Args:
        property_id: Numeric GA4 property ID (e.g. '123456789').
                     Discover with ga4_list_properties or find in your
                     GA4 Admin → Property Settings → Property ID.
    """
    try:
        client = ga4_client.get_client()
        metadata = client.get_metadata(name=f"properties/{property_id}/metadata")

        return {
            "property_id": property_id,
            "dimensions": [
                {"api_name": d.api_name, "custom_definition": d.custom_definition,
                 "category": d.category or ""}
                for d in metadata.dimensions
            ],
            "metrics": [
                {"api_name": m.api_name, "custom_definition": m.custom_definition,
                 "category": m.category or ""}
                for m in metadata.metrics
            ],
            "dimension_count": len(metadata.dimensions),
            "metric_count": len(metadata.metrics),
        }
    except Exception as e:
        return _ga4_handle_error("ga4_get_metadata", e)


@mcp.tool()
def ga4_run_report(
    property_id: str,
    dimensions: str = "",
    metrics: str = "activeUsers",
    start_date: str = "28daysAgo",
    end_date: str = "today",
    filters: str | dict | list | None = None,
    order_bys: str | list | None = None,
    limit: int = 100,
) -> dict:
    """Run a standard GA4 report with dimensions, metrics, date range, and filters.

    **Workflow:** ga4_list_properties() → ga4_get_metadata() → ga4_run_report()

    Start with just metrics (no dimensions) for a quick property overview,
    then add dimensions for deeper analysis.

    Args:
        property_id: Numeric GA4 property ID (e.g. '123456789').
        dimensions: Comma-separated dimension names, e.g. 'city,country' or 'date,pagePath'.
                    Omit or leave empty for a property-level summary.
        metrics: Comma-separated metric names, e.g. 'activeUsers,sessions,newUsers'.
                 Default: 'activeUsers'.
        start_date: Start date in YYYY-MM-DD format, or relative like '7daysAgo',
                    '28daysAgo', 'yesterday', 'today'.
        end_date: End date in YYYY-MM-DD format, or relative like 'today'.
        filters: Optional JSON filter. Format:
                 {"field": "dimensionName", "type": "string_filter",
                  "value": "text", "match_type": "EXACT|CONTAINS|BEGINS_WITH|ENDS_WITH"}
                 Or array of filters (AND-combined).
                 Numeric: type="numeric_filter", match_type="EQUAL|GREATER_THAN|LESS_THAN"
        order_bys: Optional JSON ordering. Format:
                   [{"metric": "metricName", "desc": true},
                    {"dimension": "dimName", "desc": false}]
        limit: Max rows to return (default: 100, max: 100000).

    Examples:
      # Top 10 cities by active users
      property_id='123456789', dimensions='city', metrics='activeUsers',
      limit=10, order_bys='[{"metric": "activeUsers", "desc": true}]'

      # Traffic sources (channel groups)
      property_id='123456789',
      dimensions='sessionDefaultChannelGrouping',
      metrics='activeUsers,sessions,newUsers',
      start_date='2026-01-01'

      # Page performance with device filter
      property_id='123456789',
      dimensions='pagePath,deviceCategory',
      metrics='screenPageViews,engagementRate',
      start_date='2026-01-01',
      filters='{"field": "deviceCategory", "type": "string_filter",
                "value": "mobile", "match_type": "CONTAINS"}'
    """
    try:
        client = ga4_client.get_client()

        dims = _parse_dimensions(dimensions) if dimensions else None
        mets = _parse_metrics(metrics) if metrics else None
        filter_expr = _parse_filter_json(filters)
        order_list = _parse_order_bys(order_bys)

        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dims,
            metrics=mets,
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimension_filter=filter_expr,
            order_bys=order_list,
            limit=min(limit, 100000),
            return_property_quota=True,
        )

        response = client.run_report(request)

        dim_names = [h.name for h in response.dimension_headers]
        metric_names = [h.name for h in response.metric_headers]
        rows = _ga4_rows_to_dicts(response, dim_names, metric_names)

        # Metadata about quota
        quota = {}
        if response.property_quota:
            q = response.property_quota
            if q.tokens_per_day:
                quota["tokens_per_day_remaining"] = q.tokens_per_day.remaining
            if q.tokens_per_hour:
                quota["tokens_per_hour_remaining"] = q.tokens_per_hour.remaining

        return {
            "property_id": property_id,
            "date_range": {"start": start_date, "end": end_date},
            "dimensions": dim_names,
            "metrics": metric_names,
            "row_count": len(rows),
            "total_row_count": response.row_count if hasattr(response, "row_count") else len(rows),
            "rows": rows,
            "quota": quota if quota else None,
        }
    except Exception as e:
        return _ga4_handle_error("ga4_run_report", e)


@mcp.tool()
def ga4_run_realtime_report(
    property_id: str,
    dimensions: str = "",
    metrics: str = "activeUsers",
    limit: int = 100,
) -> dict:
    """Get real-time data for the last 30 minutes from a GA4 property.

    Useful for monitoring live traffic, testing event tracking, and
    verifying setup.

    Args:
        property_id: Numeric GA4 property ID (e.g. '123456789').
        dimensions: Comma-separated dimension names, e.g. 'city,country'.
                    Available realtime dimensions: country, city, deviceCategory,
                    eventName, pagePath, pageTitle, source, medium, etc.
        metrics: Comma-separated metric names, e.g. 'activeUsers,eventCount'.
                 Default: 'activeUsers'.
        limit: Max rows to return (default: 100, max: 100000).

    Example:
      property_id='123456789', dimensions='country,deviceCategory',
      metrics='activeUsers', limit=10
    """
    try:
        client = ga4_client.get_client()

        dims = _parse_dimensions(dimensions) if dimensions else None
        mets = _parse_metrics(metrics) if metrics else None

        request = RunRealtimeReportRequest(
            property=f"properties/{property_id}",
            dimensions=dims,
            metrics=mets,
            limit=min(limit, 100000),
            return_property_quota=True,
        )

        response = client.run_realtime_report(request)

        dim_names = [h.name for h in response.dimension_headers]
        metric_names = [h.name for h in response.metric_headers]
        rows = _ga4_rows_to_dicts(response, dim_names, metric_names)

        return {
            "property_id": property_id,
            "dimensions": dim_names,
            "metrics": metric_names,
            "row_count": len(rows),
            "rows": rows,
        }
    except Exception as e:
        return _ga4_handle_error("ga4_run_realtime_report", e)


# ---------------------------------------------------------------------------
# Google Keyword Planner tools
# ---------------------------------------------------------------------------

def _kp_handle_error(context: str, e: Exception) -> dict:
    _log_exc(context)
    if isinstance(e, GoogleAdsException):
        msg = _handle_google_ads_error(e)
        for error in e.failure.errors:
            auth_err = error.error_code.authorization_error
            if auth_err and auth_err.name == "DEVELOPER_TOKEN_NOT_APPROVED":
                return {
                    "error": "The Google Ads developer token is not approved for "
                             "Keyword Planner. Explorer-level tokens cannot call "
                             "Keyword Planner services — apply for basic or "
                             "standard access: ads.google.com → Tools → API "
                             "Center → Request higher access.",
                }
        low = msg.lower()
        if "keyword_plan" in low or "keyword plan" in low or "permission" in low:
            return {
                "error": "Keyword Planner is not available for this account. "
                         "The customer_id needs access to Keyword Planner "
                         "(Tools → Planning → Keyword Planner in Google Ads). "
                         "If this is a manager (MCC) account, run the query on "
                         "a child customer ID instead. Details:\n" + msg,
            }
        return {"error": msg}
    if isinstance(e, ValueError):
        return {"error": str(e)}
    return {"error": f"{type(e).__name__}: {e}"}


def _resolve_customer_id(customer_id: str | None) -> str:
    """Use the caller's customer_id, or fall back to env config.

    Env fallbacks, in order: GOOGLE_ADS_DEFAULT_CUSTOMER_ID, then
    GOOGLE_ADS_LOGIN_CUSTOMER_ID.
    """
    if customer_id:
        return customer_id
    env_id = (
        os.environ.get("GOOGLE_ADS_DEFAULT_CUSTOMER_ID")
        or os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        or ""
    )
    if env_id:
        return env_id
    raise ValueError(
        "No customer_id provided. Pass one explicitly or set "
        "GOOGLE_ADS_DEFAULT_CUSTOMER_ID (or GOOGLE_ADS_LOGIN_CUSTOMER_ID) "
        "in .env"
    )


@mcp.tool()
def generate_keyword_ideas(
    customer_id: str | None = None,
    keywords: Sequence[str] | None = None,
    url: str | None = None,
    geos: Sequence[str] | None = None,
    language: str | None = None,
    network: Literal["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"] | None = None,
    include_adult_keywords: bool = False,
    page_size: int = 50,
) -> dict:
    """Generate Google Keyword Planner keyword ideas from seed terms or a URL.

    **Use this for:** keyword research, expanding a seed list, finding
    search-volume/competition/bid estimates for potential keywords.

    Args:
        customer_id: Numeric Google Ads customer ID with Keyword Planner
                     access. Optional — falls back to
                     GOOGLE_ADS_DEFAULT_CUSTOMER_ID, then
                     GOOGLE_ADS_LOGIN_CUSTOMER_ID from .env.
        keywords: Seed terms (e.g. ['running shoes', 'trail running shoes']).
        url: Alternative seed — a URL to extract ideas from.
             Provide keywords, url, or both (both = keyword_and_url seed).
        geos: Geo targeting, e.g. ['geoTargetConstants/2840'] (United States).
              Find IDs with suggest_geo_target_constants. Omit = worldwide.
        language: 'english' (default), any name in the built-in map, or a
                  full resource name like 'languageConstants/1002'.
        network: 'GOOGLE_SEARCH' or 'GOOGLE_SEARCH_AND_PARTNERS' (default).
        include_adult_keywords: Whether to include adult ideas (default: False).
        page_size: Max ideas to return (default: 50, max: 2000).

    Returns each idea with avg_monthly_searches, competition (LOW/MEDIUM/HIGH),
    competition_index (0-100), top-of-page bid range, avg CPC, concepts, and
    close variants.
    """
    try:
        cid = _resolve_customer_id(customer_id)
        client = ads_client.get_client()
        service = client.get_service("KeywordPlanIdeaService")
        request = keyword_planner.build_ideas_request(
            customer_id=cid,
            keywords=keywords,
            url=url,
            geos=geos,
            language=language,
            network=network,
            include_adult_keywords=include_adult_keywords,
            page_size=page_size,
        )
        response = service.generate_keyword_ideas(request=request)
        return {
            "customer_id": cid,
            "seed": {
                "keywords": list(keywords or []),
                "url": url,
            },
            "count": len(response.results),
            "total_size": response.total_size,
            "keywords": [
                keyword_planner.flatten_idea_result(r) for r in response.results
            ],
        }
    except Exception as e:
        return _kp_handle_error("generate_keyword_ideas", e)


@mcp.tool()
def generate_keyword_historical_metrics(
    customer_id: str | None = None,
    keywords: Sequence[str] = (),
    geos: Sequence[str] | None = None,
    language: str | None = None,
    network: Literal["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"] | None = None,
    include_adult_keywords: bool = False,
) -> dict:
    """Get historical search metrics for exact keywords (no expansion).

    **Use this for:** validating a specific keyword list — real search
    volume, competition level, and CPC bid ranges per keyword.

    Args:
        customer_id: Numeric Google Ads customer ID with Keyword Planner
                     access. Optional — falls back to
                     GOOGLE_ADS_DEFAULT_CUSTOMER_ID, then
                     GOOGLE_ADS_LOGIN_CUSTOMER_ID from .env.
        keywords: Exact keywords to look up (e.g. ['running shoes']).
        geos: Geo targeting resource names (see generate_keyword_ideas).
        language: Language name or resource name (default: 'english').
        network: 'GOOGLE_SEARCH' or 'GOOGLE_SEARCH_AND_PARTNERS' (default).
        include_adult_keywords: Include adult data (default: False).
    """
    try:
        cid = _resolve_customer_id(customer_id)
        client = ads_client.get_client()
        service = client.get_service("KeywordPlanIdeaService")
        request = keyword_planner.build_historical_request(
            customer_id=cid,
            keywords=keywords,
            geos=geos,
            language=language,
            network=network,
            include_adult_keywords=include_adult_keywords,
        )
        response = service.generate_keyword_historical_metrics(request=request)
        return {
            "customer_id": cid,
            "count": len(response.results),
            "keywords": [
                keyword_planner.flatten_historical_result(r)
                for r in response.results
            ],
        }
    except Exception as e:
        return _kp_handle_error("generate_keyword_historical_metrics", e)


@mcp.tool()
def generate_keyword_forecast_metrics(
    customer_id: str | None = None,
    keywords: Sequence[str] = (),
    match_types: Sequence[str] | None = None,
    currency_code: str = "EUR",
    start_date: str | None = None,
    end_date: str | None = None,
    geos: Sequence[str] | None = None,
    language: str | None = None,
    daily_budget_micros: int | None = None,
    max_cpc_bid_micros: int | None = None,
) -> dict:
    """Forecast impressions, clicks, CPC, and cost for a keyword list.

    **Use this for:** pre-launch planning — what traffic/cost to expect
    from a set of keywords over a date range. Simulated in-memory campaign
    (one ad group, manual CPC bidding by default); nothing is created in
    the Ads account.

    Args:
        customer_id: Numeric Google Ads customer ID with Keyword Planner
                     access. Optional — falls back to
                     GOOGLE_ADS_DEFAULT_CUSTOMER_ID, then
                     GOOGLE_ADS_LOGIN_CUSTOMER_ID from .env.
        keywords: Keywords to forecast.
        match_types: 'EXACT' (default) for all, or one per keyword
                     ('BROAD', 'PHRASE', 'EXACT').
        currency_code: ISO 4217 code (default: 'EUR').
        start_date: YYYY-MM-DD (default: tomorrow).
        end_date: YYYY-MM-DD (default: 30 days from tomorrow).
        geos: Geo targeting resource names (see generate_keyword_ideas).
        language: Language name or resource name (default: 'english').
        daily_budget_micros: Optional daily budget ($1 = 1000000).
        max_cpc_bid_micros: Optional max CPC bid ($1 = 1000000).

    Returns campaign-level impressions, clicks, CTR, avg CPC, and cost in
    micros, plus per-ad-group breakdown when the API provides it.
    """
    try:
        from datetime import timedelta

        cid = _resolve_customer_id(customer_id)
        today = datetime.now().date()
        start = start_date or (today + timedelta(days=1)).isoformat()
        end = end_date or (today + timedelta(days=31)).isoformat()

        client = ads_client.get_client()
        service = client.get_service("KeywordPlanIdeaService")
        request = keyword_planner.build_forecast_request(
            customer_id=cid,
            keywords=keywords,
            match_types=match_types,
            currency_code=currency_code,
            start_date=start,
            end_date=end,
            geos=geos,
            language=language,
            daily_budget_micros=daily_budget_micros,
            max_cpc_bid_micros=max_cpc_bid_micros,
        )
        response = service.generate_keyword_forecast_metrics(request=request)
        result = keyword_planner.flatten_forecast_response(response)
        result.update({
            "customer_id": cid,
            "currency_code": currency_code,
            "forecast_period": {"start": start, "end": end},
            "keywords": list(keywords),
        })
        return result
    except Exception as e:
        return _kp_handle_error("generate_keyword_forecast_metrics", e)


@mcp.tool()
def suggest_geo_target_constants(
    names: Sequence[str],
    country_code: str | None = None,
    locale: str = "en",
) -> dict:
    """Look up Google Ads geo target constants (for geos in other tools).

    **Use this before generate_keyword_ideas/forecast when you need to
    target a country/region** — returns resource names like
    'geoTargetConstants/2840' (United States) to pass as geos.

    Args:
        names: Location names to search, e.g. ['United States', 'New York'].
        country_code: Optional ISO-2 country code to narrow results
                      (e.g. 'US').
        locale: Results language (default: 'en').
    """
    try:
        client = ads_client.get_client()
        service = client.get_service("GeoTargetConstantService")
        request = keyword_planner.build_geo_suggest_request(
            names=names,
            country_code=country_code,
            locale=locale,
        )
        response = service.suggest_geo_target_constants(request=request)
        return {
            "searched": list(names),
            "count": len(response.geo_target_constant_suggestions),
            "suggestions": keyword_planner.flatten_geo_suggestions(response),
        }
    except Exception as e:
        return _kp_handle_error("suggest_geo_target_constants", e)


# ---------------------------------------------------------------------------
# Bing Webmaster Tools (read-only)
# ---------------------------------------------------------------------------

def _bing_handle_error(context: str, e: Exception) -> dict:
    _log_exc(context)
    if isinstance(e, bing_client.BingAPIError):
        return {"error": str(e)}
    if isinstance(e, ValueError):
        return {"error": str(e)}
    return {"error": f"{type(e).__name__}: {e}"}


def _bing_daily_rows(rows: list[dict], days: int | None) -> list[dict]:
    """Sort daily rows by date and keep the last N days when asked."""
    ordered = sorted(
        rows,
        key=lambda row: str(row.get("date", "")),
    )
    if days is None:
        return ordered
    cutoff = datetime.now().date() - timedelta(days=days)
    kept = []
    for row in ordered:
        raw = str(row.get("date", ""))
        try:
            row_date = datetime.fromisoformat(raw).date()
        except ValueError:
            kept.append(row)
            continue
        if row_date >= cutoff:
            kept.append(row)
    return kept


@mcp.tool()
def bing_get_capabilities() -> str:
    """Get the Bing Webmaster tool list and authentication status.
    Call this first if Bing calls fail or you are unsure what is available.
    """
    if not bing_client.is_configured():
        auth = (
            "Not connected - BING_WEBMASTER_API_KEY is not set. "
            "Get a key from Bing Webmaster Tools -> Settings -> API Access."
        )
    else:
        try:
            sites = bing_client.list_sites()
            auth = f"Connected - {len(sites)} site(s) available"
        except Exception as e:
            auth = f"Not connected - {e}"

    return (
        "Bing Webmaster Tools\n\n"
        f"Auth status: {auth}\n\n"
        "Start with:  bing_list_sites  (to get exact site_url values)\n\n"
        "Discovery:\n"
        "  bing_list_sites          - List verified sites (always start here)\n"
        "  bing_get_url_info        - Crawl and index details for one URL\n\n"
        "Analytics:\n"
        "  bing_get_query_stats     - Top queries with clicks and impressions\n"
        "  bing_get_page_stats      - Top pages with clicks and impressions\n"
        "  bing_get_traffic_stats   - Daily clicks and impressions trend\n"
        "  bing_get_query_pages     - Pages ranking for one query\n"
        "  bing_get_page_queries    - Queries a page ranks for\n\n"
        "Indexing:\n"
        "  bing_get_crawl_stats     - Crawl volume and response codes\n"
        "  bing_get_crawl_issues    - Indexing problems\n"
        "  bing_get_sitemaps        - Submitted sitemaps and feeds\n\n"
        "Links:\n"
        "  bing_get_link_counts     - Inbound link counts per page\n\n"
        "Keywords:\n"
        "  bing_keyword_stats       - Historical keyword data\n"
        "  bing_get_related_keywords- Related keyword discovery\n\n"
        "Cross-engine:\n"
        "  seo_compare_google_bing  - Join Google and Bing top queries\n\n"
        "Bing query and page data updates weekly. Traffic data updates daily."
    )


@mcp.tool()
def bing_list_sites() -> dict:
    """**Start here** - List all sites verified in Bing Webmaster Tools.

    Returns the exact site_url strings needed by every other Bing tool.
    Always call this first.
    """
    try:
        sites = bing_client.list_sites()
        # Drop verification secrets. They are not needed for analytics.
        hidden = {"authentication_code", "dns_verification_code"}
        safe_sites = [
            {key: value for key, value in site.items() if key not in hidden}
            for site in sites
        ]
        return {
            "count": len(safe_sites),
            "sites": safe_sites,
        }
    except Exception as e:
        return _bing_handle_error("bing_list_sites", e)


@mcp.tool()
def bing_get_query_stats(site_url: str, limit: int = 100) -> dict:
    """Get top search queries with clicks, impressions, and average positions.
    **Use this for:** finding which queries drive Bing traffic.
    Bing refreshes this data weekly. There is no date-range filter.

    Args:
        site_url: Exact site URL from bing_list_sites.
        limit: Max rows to return (default: 100).
    """
    try:
        rows = bing_client.get_query_stats(site_url)
        return {
            "site_url": site_url,
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "queries": rows[: max(1, limit)],
            "note": "Bing updates query stats weekly. Rows are Bing top queries.",
        }
    except Exception as e:
        return _bing_handle_error("bing_get_query_stats", e)


@mcp.tool()
def bing_get_page_stats(site_url: str, limit: int = 100) -> dict:
    """Get top pages with clicks, impressions, and average positions.
    **Use this for:** finding which pages get Bing traffic.
    Bing refreshes this data weekly. There is no date-range filter.

    Args:
        site_url: Exact site URL from bing_list_sites.
        limit: Max rows to return (default: 100).
    """
    try:
        rows = bing_client.get_page_stats(site_url)
        return {
            "site_url": site_url,
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "pages": rows[: max(1, limit)],
            "note": "Bing updates page stats weekly. Rows are Bing top pages.",
        }
    except Exception as e:
        return _bing_handle_error("bing_get_page_stats", e)


@mcp.tool()
def bing_get_traffic_stats(site_url: str, days: int | None = None) -> dict:
    """Get daily clicks and impressions with totals.
    **Use this for:** Bing traffic trends, spikes, and drops.
    This is the only Bing report with a real daily time series.

    Args:
        site_url: Exact site URL from bing_list_sites.
        days: Keep only the last N days (optional). Omit for the full series.
    """
    try:
        rows = _bing_daily_rows(bing_client.get_rank_and_traffic_stats(site_url), days)
        total_clicks = sum(int(row.get("clicks", 0) or 0) for row in rows)
        total_impressions = sum(int(row.get("impressions", 0) or 0) for row in rows)
        return {
            "site_url": site_url,
            "days": days,
            "row_count": len(rows),
            "totals": {
                "clicks": total_clicks,
                "impressions": total_impressions,
            },
            "daily": rows,
        }
    except Exception as e:
        return _bing_handle_error("bing_get_traffic_stats", e)


@mcp.tool()
def bing_get_query_pages(site_url: str, query: str, limit: int = 100) -> dict:
    """Get the pages that rank for one query.
    **Use this for:** checking which URL Bing shows for a keyword.

    Args:
        site_url: Exact site URL from bing_list_sites.
        query: The search query to look up.
        limit: Max rows to return (default: 100).
    """
    try:
        rows = bing_client.get_query_pages(site_url, query)
        return {
            "site_url": site_url,
            "query": query,
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "pages": rows[: max(1, limit)],
        }
    except Exception as e:
        return _bing_handle_error("bing_get_query_pages", e)


@mcp.tool()
def bing_get_page_queries(site_url: str, page: str, limit: int = 100) -> dict:
    """Get the queries that one page ranks for.
    **Use this for:** keyword mapping and on-page optimization.

    Args:
        site_url: Exact site URL from bing_list_sites.
        page: The page URL to look up.
        limit: Max rows to return (default: 100).
    """
    try:
        rows = bing_client.get_page_queries(site_url, page)
        return {
            "site_url": site_url,
            "page": page,
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "queries": rows[: max(1, limit)],
        }
    except Exception as e:
        return _bing_handle_error("bing_get_page_queries", e)


@mcp.tool()
def bing_get_url_info(site_url: str, url: str) -> dict:
    """Get crawl and index details for one URL.
    **Use this for:** checking HTTP status, last crawl date, and link counts.
    Use the 'domain:example.com' form to inspect a whole domain.

    Args:
        site_url: Exact site URL from bing_list_sites.
        url: The URL to inspect.
    """
    try:
        info = bing_client.get_url_info(site_url, url)
        return {
            "site_url": site_url,
            "url": url,
            **info,
        }
    except Exception as e:
        return _bing_handle_error("bing_get_url_info", e)


@mcp.tool()
def bing_get_crawl_stats(site_url: str) -> dict:
    """Get crawl statistics for a site.
    **Use this for:** crawl volume, response codes, and indexing health.

    Args:
        site_url: Exact site URL from bing_list_sites.
    """
    try:
        stats = bing_client.get_crawl_stats(site_url)
        return {
            "site_url": site_url,
            "stats": stats,
        }
    except Exception as e:
        return _bing_handle_error("bing_get_crawl_stats", e)


@mcp.tool()
def bing_get_crawl_issues(site_url: str, limit: int = 100) -> dict:
    """List crawl issues found by Bing.
    **Use this for:** finding blocked pages, errors, and indexing problems.

    Args:
        site_url: Exact site URL from bing_list_sites.
        limit: Max rows to return (default: 100).
    """
    try:
        rows = bing_client.get_crawl_issues(site_url)
        return {
            "site_url": site_url,
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "issues": rows[: max(1, limit)],
        }
    except Exception as e:
        return _bing_handle_error("bing_get_crawl_issues", e)


@mcp.tool()
def bing_get_link_counts(site_url: str, page: int = 0) -> dict:
    """Get inbound link counts for site pages.
    **Use this for:** finding pages with the most backlinks.

    Args:
        site_url: Exact site URL from bing_list_sites.
        page: Result page number, starting at 0 (default: 0).
    """
    try:
        data = bing_client.get_link_counts(site_url, page)
        return {
            "site_url": site_url,
            "page": page,
            "links": data,
        }
    except Exception as e:
        return _bing_handle_error("bing_get_link_counts", e)


@mcp.tool()
def bing_get_sitemaps(site_url: str) -> dict:
    """List submitted sitemaps and feeds with their status.
    **Use this for:** checking sitemap submission and crawl pickup.

    Args:
        site_url: Exact site URL from bing_list_sites.
    """
    try:
        feeds = bing_client.get_feeds(site_url)
        return {
            "site_url": site_url,
            "count": len(feeds),
            "sitemaps": feeds,
        }
    except Exception as e:
        return _bing_handle_error("bing_get_sitemaps", e)


@mcp.tool()
def bing_keyword_stats(
    query: str,
    country: str = "us",
    language: str = "en-US",
) -> dict:
    """Get historical keyword statistics from Bing.
    **Use this for:** validating a keyword with Bing search data.

    Args:
        query: The keyword to look up.
        country: Two-letter market code (default: 'us').
        language: IETF language tag, for example 'en-US' or 'en-GB'
                  (default: 'en-US'). A bare code like 'en' gets the country
                  added automatically.
    """
    try:
        rows = bing_client.get_keyword_stats(query, country, language)
        return {
            "query": query,
            "country": country,
            "language": language,
            "row_count": len(rows),
            "stats": rows,
        }
    except Exception as e:
        return _bing_handle_error("bing_keyword_stats", e)


@mcp.tool()
def bing_get_related_keywords(
    query: str,
    country: str = "us",
    language: str = "en-US",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict:
    """Get related keywords for a seed term from Bing.
    **Use this for:** keyword discovery and topic expansion.

    Args:
        query: Seed keyword.
        country: Two-letter market code (default: 'us').
        language: IETF language tag, for example 'en-US' or 'en-GB'
                  (default: 'en-US'). A bare code like 'en' gets the country
                  added automatically.
        start_date: ISO date (YYYY-MM-DD). Default: 30 days ago.
        end_date: ISO date (YYYY-MM-DD). Default: today.
        limit: Max rows to return (default: 100).
    """
    try:
        today = datetime.now().date()
        end = end_date or today.isoformat()
        start = start_date or (today - timedelta(days=30)).isoformat()
        rows = bing_client.get_related_keywords(
            query, country, language, start, end
        )
        return {
            "query": query,
            "country": country,
            "language": language,
            "period": {"start": start, "end": end},
            "row_count": len(rows),
            "returned": len(rows[: max(1, limit)]),
            "keywords": rows[: max(1, limit)],
            "note": "Bing may return an empty list for low-volume terms.",
        }
    except Exception as e:
        return _bing_handle_error("bing_get_related_keywords", e)


@mcp.tool()
def seo_compare_google_bing(
    bing_site_url: str,
    gsc_site_url: str,
    days: int = 28,
    limit: int = 25,
) -> dict:
    """Compare top search queries between Bing and Google Search Console.
    **Use this for:** finding engines where a query over- or under-performs.
    Google uses the last N days. Bing uses its weekly top-query snapshot.

    Args:
        bing_site_url: Exact Bing site URL from bing_list_sites.
        gsc_site_url: Exact GSC property URL from gsc_list_properties.
        days: Google lookback window in days (default: 28).
        limit: Max rows per section (default: 25).
    """
    try:
        bing_rows = bing_client.get_query_stats(bing_site_url)

        service = gsc_client.get_service()
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "dimensions": ["query"],
            "rowLimit": 1000,
        }
        response = (
            service.searchanalytics()
            .query(siteUrl=gsc_site_url, body=body)
            .execute()
        )
        gsc_rows = [
            {
                "query": row.get("keys", [""])[0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "position": round(row.get("position", 0), 1),
            }
            for row in response.get("rows", [])
        ]

        comparison = bing_client.compare_queries(bing_rows, gsc_rows, limit=limit)
        return {
            "bing_site_url": bing_site_url,
            "gsc_site_url": gsc_site_url,
            "google_period": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
            },
            "bing_period": "latest weekly snapshot",
            **comparison,
        }
    except Exception as e:
        return _bing_handle_error("seo_compare_google_bing", e)
