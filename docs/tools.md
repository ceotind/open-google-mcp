# Tools

36 read-only tools across four platforms. No tool writes, bids, or changes account settings.

Every product has a discovery call. Use it first: `list_accessible_customers`, `gsc_list_properties`, `ga4_list_properties`, `bing_list_sites`.

## Google Ads

| Tool | Input | Description |
|------|-------|-------------|
| `list_accessible_customers` | — | Discover Google Ads account IDs |
| `get_resource_metadata` | `resource_name` | Explore selectable, filterable, and sortable fields |
| `search` | `customer_id`, `resource`, `fields`, `conditions?`, `orderings?`, `limit?` | Execute read-only GAQL queries |

## Google Search Console

| Tool | Input | Description |
|------|-------|-------------|
| `gsc_get_capabilities` | — | Tool list with auth status |
| `gsc_list_properties` | — | List all properties (start here) |
| `gsc_get_site_details` | `site_url` | Verification and ownership |
| `gsc_get_search_analytics` | `site_url`, `days?`, `dimensions?`, `row_limit?` | Top queries with clicks, impressions, CTR, position |
| `gsc_get_performance_overview` | `site_url`, `days?` | Summary with daily trend |
| `gsc_compare_search_periods` | `site_url`, `period1_start/end`, `period2_start/end` | Compare two date ranges |
| `gsc_get_advanced_search_analytics` | `site_url`, `start_date?`, `end_date?`, `dimensions?`, `search_type?`, `row_limit?`, `start_row?`, `sort_by?`, `sort_direction?`, `filters?` | Filtered, sorted, paginated analytics |
| `gsc_inspect_url` | `site_url`, `page_url` | Crawl and index status for one URL |
| `gsc_get_sitemaps` | `site_url` | Sitemaps with status and errors |

## Google Analytics 4

| Tool | Input | Description |
|------|-------|-------------|
| `ga4_get_capabilities` | — | Tool list with auth status |
| `ga4_list_properties` | — | Discover accessible properties |
| `ga4_get_metadata` | `property_id` | Browse dimensions and metrics |
| `ga4_run_report` | `property_id`, `dimensions?`, `metrics?`, `start_date?`, `end_date?`, `filters?`, `order_bys?`, `limit?` | Standard report with filtering and ordering |
| `ga4_run_realtime_report` | `property_id`, `dimensions?`, `metrics?`, `limit?` | Real-time data, last 30 minutes |

`dimensions` and `metrics` are comma-separated strings, not arrays. `filters` and `order_bys` are JSON strings.

## Google Keyword Planner

| Tool | Input | Description |
|------|-------|-------------|
| `generate_keyword_ideas` | `customer_id?`, `keywords?`/`url?`, `geos?`, `language?`, `network?`, `page_size?` | Ideas with volume, competition, bid ranges |
| `generate_keyword_historical_metrics` | `customer_id?`, `keywords`, `geos?`, `language?` | Historical metrics for exact keywords |
| `generate_keyword_forecast_metrics` | `customer_id?`, `keywords`, `match_types?`, `currency_code?`, `start/end_date?`, `budget/bid?` | Simulated forecast: impressions, clicks, CPC, cost |
| `suggest_geo_target_constants` | `names`, `country_code?`, `locale?` | Look up geo names, for example `geoTargetConstants/2840` |

Keyword Planner reuses the Ads service account and developer token.

`customer_id` is optional. It falls back to `GOOGLE_ADS_DEFAULT_CUSTOMER_ID`, then `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.

The account needs Keyword Planner access. Manager accounts usually lack it, so use a child customer ID.

The developer token needs at least basic access. Explorer-level tokens are rejected.

## Bing Webmaster Tools

| Tool | Input | Description |
|------|-------|-------------|
| `bing_get_capabilities` | — | Tool list with auth status |
| `bing_list_sites` | — | Verified sites (start here) |
| `bing_get_query_stats` | `site_url`, `limit?` | Top queries |
| `bing_get_page_stats` | `site_url`, `limit?` | Top pages |
| `bing_get_traffic_stats` | `site_url`, `days?` | Daily clicks and impressions |
| `bing_get_query_pages` | `site_url`, `query`, `limit?` | Pages ranking for one query |
| `bing_get_page_queries` | `site_url`, `page`, `limit?` | Queries a page ranks for |
| `bing_get_url_info` | `site_url`, `url` | Crawl and index details |
| `bing_get_crawl_stats` | `site_url` | Crawl volume and response codes |
| `bing_get_crawl_issues` | `site_url`, `limit?` | Indexing problems |
| `bing_get_link_counts` | `site_url`, `page?` | Inbound link counts |
| `bing_get_sitemaps` | `site_url` | Submitted sitemaps and feeds |
| `bing_keyword_stats` | `query`, `country?`, `language?` | Historical keyword data |
| `bing_get_related_keywords` | `query`, `country?`, `language?`, `start/end_date?`, `limit?` | Related keyword discovery |
| `seo_compare_google_bing` | `bing_site_url`, `gsc_site_url`, `days?`, `limit?` | Join Google and Bing top queries |

Bing uses one API key. No OAuth, no service account.

Query and page reports are top-N snapshots, refreshed weekly. They accept no date range. `bing_get_traffic_stats` is the only daily series.

Responses are cached for 5 minutes to protect the daily quota.

Language tags need a region, such as `en-US` or `en-GB`. A bare `en` is rejected.

## Manager account auto-routing

`search` detects a manager (MCC) account and runs the query on each enabled child account.

Results carry `_source_customer_id` and `_source_customer_name`, so you can tell which account each row came from.

A leading `_note` row reports that routing happened.
