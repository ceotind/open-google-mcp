import json
import sys
import traceback
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from google.ads.googleads.errors import GoogleAdsException
from googleapiclient.errors import HttpError
from google.protobuf.json_format import MessageToDict
from mcp.server.fastmcp import FastMCP

from . import client as ads_client
from . import gsc_client

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
            "FROM customer_client WHERE customer_client.status = 'ENABLED' LIMIT 100",
        )
        return results
    except Exception:
        _log_exc(f"get_child_accounts for {customer_id}")
        return []


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
