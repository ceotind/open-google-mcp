import sys
import traceback
from collections.abc import Sequence

from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.json_format import MessageToDict
from mcp.server.fastmcp import FastMCP

from . import client as ads_client

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
