import json
import sys
import traceback
from collections.abc import Sequence
from datetime import datetime, timedelta

from google.ads.googleads.errors import GoogleAdsException
from googleapiclient.errors import HttpError
from google.protobuf.json_format import MessageToDict
from mcp.server.fastmcp import FastMCP

from . import client as ads_client
from . import gsc_client

mcp = FastMCP("Google Ads MCP Reader")


def _log_exc(context: str) -> None:
    """Log full traceback to stderr so real errors are never masked."""
    print(f"[google-ads-mcp-reader] ERROR in {context}:", file=sys.stderr)
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
            "FROM customer_client WHERE customer_client.status = 'ENABLED' LIMIT 100",
        )
        return results
    except Exception:
        _log_exc(f"get_child_accounts for {customer_id}")
        return []


@mcp.tool()
def list_accessible_customers() -> list[str]:
    """Returns IDs of Google Ads accounts accessible by the authenticated user.

    Use this as the FIRST tool call to discover available customer IDs
    before using other tools. Most other tools require a valid customer ID.
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
    """Discovers which fields can be SELECTed, FILTERed, and SORTed by for a
    given Google Ads resource.

    Returns a dict with arrays: 'selectable', 'filterable', and 'sortable'.
    Compatible 'metrics.*' and 'segments.*' fields are included for reporting
    queries.

    ALWAYS call this tool BEFORE constructing a search query to ensure you
    use correct, fully-qualified field names. Incorrect field names cause
    Google Ads API errors.

    Example output for resource='campaign':
      selectable: ['campaign.id', 'campaign.name', 'campaign.status',
        'campaign.advertising_channel_type', 'metrics.clicks',
        'metrics.cost_micros', 'metrics.impressions', 'segments.date', ...]
      filterable: ['campaign.id', 'campaign.name', 'campaign.status', ...]
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
    """Executes a read-only GAQL (Google Ads Query Language) query and returns
    results as a list of flat dicts with dot-separated keys.

    If the customer_id is a **manager (MCC) account** and the query targets a
    resource that lives on client accounts (campaign, ad_group, ad_group_ad, etc.),
    this tool AUTOMATICALLY finds child accounts and runs the query on each of
    them, returning results from all children with a `_source_customer_id` field
    added to identify which account each row came from.

    USAGE WORKFLOW:
      1. Call list_accessible_customers to find available account IDs
      2. Call get_resource_metadata(resource) to discover valid field names
      3. Call this tool with customer_id, resource, and discovered fields
         — manager accounts are handled automatically

    KEY RULES:
      - Field names MUST be fully qualified (e.g. 'campaign.id', not 'id')
      - Dates MUST be in YYYY-MM-DD format with dashes
      - Use DURING for relative ranges: DURING LAST_7_DAYS, LAST_30_DAYS,
        THIS_MONTH, LAST_MONTH, THIS_QUARTER, THIS_YEAR
      - For change_event resource, limit MUST be <= 10000
      - Conditions are combined with AND

    COMMON CONDITIONS:
      campaign.status = 'ENABLED'
      campaign.advertising_channel_type = 'SEARCH'
      segments.date DURING LAST_30_DAYS
      metrics.impressions > 1000
      ad_group.status != 'REMOVED'
      campaign.id IN (123, 456)

    ORDERING FORMAT: 'field_name DIRECTION' (e.g. 'metrics.clicks DESC')

    EXAMPLE - active campaigns this week with performance:
      customer_id='1234567890', resource='campaign',
      fields=['campaign.id', 'campaign.name', 'campaign.status',
        'metrics.clicks', 'metrics.impressions', 'metrics.cost_micros'],
      conditions=["campaign.status = 'ENABLED'",
        'segments.date DURING LAST_7_DAYS'],
      orderings=['metrics.clicks DESC'], limit=10
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

        _account_resources = {
            "campaign", "ad_group", "ad_group_ad", "ad_group_criterion",
            "keyword_view", "search_term_view", "bidding_strategy",
            "campaign_budget", "campaign_criterion", "customer_client",
            "geographic_view", "user_interest", "user_list",
        }

        auto_routed = False
        if not results and resource in _account_resources:
            is_manager = _is_manager_account(client, customer_id)
            if is_manager:
                children = _get_child_accounts(client, customer_id)
                if len(children) == 1:
                    child_id = children[0].get("customer_client.id", "")
                    child_name = children[0].get("customer_client.descriptive_name", child_id)
                    child_results = _run_gaql(client, ga_service, child_id, query)
                    for r in child_results:
                        r["_source_customer_id"] = child_id
                        r["_source_customer_name"] = child_name
                    if child_results:
                        results = child_results
                        auto_routed = True
                elif len(children) > 1:
                    for child in children:
                        child_id = child.get("customer_client.id", "")
                        child_name = child.get("customer_client.descriptive_name", child_id)
                        child_results = _run_gaql(client, ga_service, child_id, query)
                        for r in child_results:
                            r["_source_customer_id"] = child_id
                            r["_source_customer_name"] = child_name
                        results.extend(child_results)
                    if results:
                        auto_routed = True

        if auto_routed:
            info = {
                "_note": f"Manager account detected. Results auto-routed from child accounts.",
            }
            results.insert(0, info)

        return results
    except GoogleAdsException as e:
        _log_exc(f"search query={query!r}")
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
        msg = body.get("error", {}).get("message", str(e))
        return {"error": f"GSC API Error (HTTP {status}): {msg}"}
    return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def gsc_list_properties() -> dict:
    """List all Google Search Console properties accessible by the authenticated user.

    Returns an object with a count and array of properties, each containing
    site_url and permission_level. Call this first to discover the exact
    site_url strings needed by other GSC tools.
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
    """Get verification and ownership details for a specific GSC property.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
                  (e.g. 'https://example.com/' or 'sc-domain:example.com')
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
    """Get top search queries and pages with clicks, impressions, CTR, and position.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
        days: Number of days to look back (default: 28)
        dimensions: Dimensions to group by (default: 'query').
                    Comma-separated options: query, page, device, country, date
        row_limit: Number of rows to return (default: 20, max: 500)
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
    """Get a summary of site performance with a daily trend over the time period.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
        days: Number of days to look back (default: 28)
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
    """Compare search performance between two date ranges.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
        period1_start: Start date for period 1 (YYYY-MM-DD)
        period1_end: End date for period 1 (YYYY-MM-DD)
        period2_start: Start date for period 2 (YYYY-MM-DD)
        period2_end: End date for period 2 (YYYY-MM-DD)
        dimensions: Dimensions to group by (default: 'query')
        limit: Top items per period to compare (default: 10)
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
    search_type: str = "WEB",
    row_limit: int = 100,
    start_row: int = 0,
    sort_by: str = "clicks",
    sort_direction: str = "descending",
    filters: str | None = None,
) -> dict:
    """Get search analytics with advanced filtering, sorting, and pagination.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
        start_date: Start date YYYY-MM-DD (defaults to 28 days ago)
        end_date: End date YYYY-MM-DD (defaults to today)
        dimensions: Comma-separated dimensions (query, page, device, country, date)
        search_type: Search type — WEB, IMAGE, VIDEO, NEWS, DISCOVER
        row_limit: Max rows to return (max 25000)
        start_row: Row offset for pagination
        sort_by: Metric to sort by — clicks, impressions, ctr, position
        sort_direction: ascending or descending
        filters: JSON array of filter objects. Each requires dimension, operator, expression.
                 Operators: contains, equals, notContains, notEquals
                 Dimensions: query, page, country, device
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
    """Check the crawl, index, and rich result status of a specific URL.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
        page_url: The full URL to inspect (e.g. 'https://example.com/page')
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
    """List all sitemaps for a GSC property with their status and error info.

    Args:
        site_url: Exact GSC property URL from gsc_list_properties
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
