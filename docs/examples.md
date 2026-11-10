# Examples

Copy these into any MCP client. Tool names match the registrations in [tools.md](tools.md).

Never guess an ID. Call the discovery tool first for each platform.

## Google Ads

List accounts:

```
list_accessible_customers
```

Discover valid fields:

```
get_resource_metadata(resource_name="campaign")
```

Active search campaigns with performance:

```
search(
  customer_id="1234567890",
  resource="campaign",
  fields=["campaign.id", "campaign.name", "campaign.status",
          "campaign.advertising_channel_type", "metrics.clicks",
          "metrics.impressions", "metrics.cost_micros"],
  conditions=["campaign.status = 'ENABLED'",
              "segments.date DURING LAST_30_DAYS"],
  orderings=["metrics.clicks DESC"],
  limit=10
)
```

Child accounts under a manager:

```
search(
  customer_id="1234567890",
  resource="customer_client",
  fields=["customer_client.id", "customer_client.descriptive_name",
          "customer_client.manager"]
)
```

## Search Console

List properties:

```
gsc_list_properties
```

Top queries:

```
gsc_get_search_analytics(
  site_url="https://example.com/",
  days=28,
  dimensions="query",
  row_limit=10
)
```

Performance overview:

```
gsc_get_performance_overview(site_url="https://example.com/", days=28)
```

Compare two periods:

```
gsc_compare_search_periods(
  site_url="https://example.com/",
  period1_start="2025-01-01",
  period1_end="2025-01-31",
  period2_start="2025-02-01",
  period2_end="2025-02-28",
  dimensions="query",
  limit=10
)
```

Advanced analytics with filters:

```
gsc_get_advanced_search_analytics(
  site_url="https://example.com/",
  dimensions="query,device",
  search_type="WEB",
  row_limit=50,
  sort_by="impressions",
  sort_direction="descending",
  filters='[{"dimension":"country","operator":"equals","expression":"usa"}]'
)
```

Inspect one URL:

```
gsc_inspect_url(
  site_url="https://example.com/",
  page_url="https://example.com/blog/post"
)
```

List sitemaps:

```
gsc_get_sitemaps(site_url="https://example.com/")
```

The `site_url` must match the property string byte for byte. `sc-domain:` properties keep that prefix.

## Analytics 4

Discover properties:

```
ga4_list_properties
```

Browse dimensions and metrics:

```
ga4_get_metadata(property_id="123456789")
```

Property-level summary:

```
ga4_run_report(
  property_id="123456789",
  metrics="activeUsers,sessions,newUsers",
  start_date="28daysAgo",
  end_date="today"
)
```

Top countries:

```
ga4_run_report(
  property_id="123456789",
  dimensions="country",
  metrics="activeUsers",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys='[{"metric": "activeUsers", "desc": true}]'
)
```

Top pages:

```
ga4_run_report(
  property_id="123456789",
  dimensions="pagePath",
  metrics="screenPageViews,activeUsers",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys='[{"metric": "screenPageViews", "desc": true}]'
)
```

Traffic sources:

```
ga4_run_report(
  property_id="123456789",
  dimensions="sessionDefaultChannelGrouping",
  metrics="activeUsers,sessions",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys='[{"metric": "activeUsers", "desc": true}]'
)
```

Filter by country:

```
ga4_run_report(
  property_id="123456789",
  dimensions="city",
  metrics="activeUsers",
  start_date="28daysAgo",
  end_date="today",
  filters='{"field": "country", "type": "string_filter",
           "value": "United States", "match_type": "EXACT"}',
  limit=10
)
```

Device breakdown:

```
ga4_run_report(
  property_id="123456789",
  dimensions="deviceCategory",
  metrics="activeUsers,sessions",
  start_date="28daysAgo",
  end_date="today"
)
```

Real-time, last 30 minutes:

```
ga4_run_realtime_report(
  property_id="123456789",
  dimensions="country,deviceCategory",
  metrics="activeUsers",
  limit=10
)
```

Dates accept `today`, `yesterday`, `7daysAgo`, `28daysAgo`, or `YYYY-MM-DD`.

## Keyword Planner

`customer_id` is optional when `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` is set.

Ideas for a seed term:

```
generate_keyword_ideas(
  keywords=["running shoes", "trail running shoes"],
  geos=["geoTargetConstants/2840"],
  language="english"
)
```

Historical metrics:

```
generate_keyword_historical_metrics(
  keywords=["running shoes", "hiking boots"],
  geos=["geoTargetConstants/2840"]
)
```

Forecast a campaign:

```
generate_keyword_forecast_metrics(
  keywords=["running shoes", "trail running shoes"],
  match_types=["PHRASE", "EXACT"],
  currency_code="USD",
  daily_budget_micros=20000000,
  max_cpc_bid_micros=500000
)
```

Find a geo constant:

```
suggest_geo_target_constants(names=["United States"], country_code="US")
```

## Bing

List verified sites:

```
bing_list_sites()
```

Use the exact `url` value as `site_url` in every other Bing tool.

Top queries and pages:

```
bing_get_query_stats(site_url="https://example.com/", limit=50)
bing_get_page_stats(site_url="https://example.com/", limit=50)
```

Daily traffic:

```
bing_get_traffic_stats(site_url="https://example.com/", days=30)
```

Pages ranking for one query:

```
bing_get_query_pages(site_url="https://example.com/", query="running shoes")
```

Queries for one page:

```
bing_get_page_queries(site_url="https://example.com/",
                      page="https://example.com/classes")
```

Crawl and index details:

```
bing_get_url_info(site_url="https://example.com/",
                  url="https://example.com/classes")
bing_get_crawl_issues(site_url="https://example.com/", limit=50)
bing_get_sitemaps(site_url="https://example.com/")
```

Keyword data:

```
bing_keyword_stats(query="running shoes", country="us", language="en-US")
bing_get_related_keywords(query="running shoes", country="us", language="en-US")
```

Related keywords default to the last 30 days. Low-volume terms may return an empty list.

Compare Google and Bing:

```
seo_compare_google_bing(
  bing_site_url="https://example.com/",
  gsc_site_url="sc-domain:example.com",
  days=28,
  limit=25
)
```

The comparison joins queries by normalized text. It returns shared queries with click gaps, plus queries unique to one engine.

## Limits

| Tool | Limit |
|---|---|
| `gsc_get_search_analytics` | 500 rows |
| `gsc_get_advanced_search_analytics` | 25,000 rows per page |
| `ga4_run_report` | 100,000 rows |
| `search` on `change_event` | 10,000 rows |
