# Google Search Console

Nine tools. All read-only. Verified against `src/open_google_mcp/server.py`.

## Workflow

1. `gsc_list_properties()` returns every property with its permission level. Copy the exact site URL.
2. Call any analytics tool with that URL.

Site URL forms, both valid:

- `https://example.com/` (URL prefix property, keeps the trailing slash)
- `sc-domain:example.com` (domain property, keeps the prefix)

A mismatch returns zero rows with no error.

## Tools

### gsc_get_capabilities
No arguments. Lists the tools and reports whether the service account authenticates.

### gsc_list_properties
No arguments. Returns properties, permission levels and verification state.

### gsc_get_site_details(site_url)
Verification and ownership detail for one property.

### gsc_get_search_analytics(site_url, days=28, dimensions="query", row_limit=20)
Quick top-N view. `row_limit` max is 500. Use 5 to 10 for a fast look.
Returns clicks, impressions, CTR and position per row.

### gsc_get_performance_overview(site_url, days=28)
Totals plus a daily trend. Use this for "how is the site doing" questions.

### gsc_compare_search_periods(site_url, period1_start, period1_end, period2_start, period2_end)
Two ranges side by side. Returns what gained and what lost.

Example:
```
gsc_compare_search_periods(
  site_url="https://example.com/",
  period1_start="2026-09-01", period1_end="2026-09-30",
  period2_start="2026-10-01", period2_end="2026-10-31")
```

### gsc_get_advanced_search_analytics(...)
The full-power call. Defaults: last 28 days, `dimensions="query"`, WEB search, 100 rows, sorted by clicks descending.

Arguments:

- `site_url` exact property URL.
- `start_date`, `end_date` as `YYYY-MM-DD`.
- `dimensions` comma-separated: `query`, `page`, `device`, `country`, `date`.
- `search_type`: WEB, IMAGE, VIDEO, NEWS, DISCOVER.
- `row_limit` max 25,000. `start_row` offsets for paging.
- `sort_by`: clicks, impressions, ctr, position. `sort_direction`: ascending, descending.
- `filters` JSON array of objects. Each has `dimension`, `operator`, `expression`.
  Operators: contains, equals, notContains, notEquals. Filters AND together.

Example, mobile traffic from United States:
```
gsc_get_advanced_search_analytics(
  site_url="https://example.com/",
  dimensions="query",
  row_limit=100,
  filters='[{"dimension":"country","operator":"equals","expression":"usa"},
             {"dimension":"device","operator":"equals","expression":"MOBILE"}]')
```

Bulk export: ask for `dimensions="query"` with `row_limit=25000`, then re-call with `start_row` advanced until `pagination.has_more` is false.

### gsc_inspect_url(site_url, page_url)
One URL. Returns coverage state, crawl date, canonical URL, robots.txt verdict, fetch success and rich results.
Use it when a page does not rank and the cause is unknown.

### gsc_get_sitemaps(site_url)
Submitted sitemaps with status, errors and warnings.

## Pitfalls

- `row_limit` above 500 on `gsc_get_search_analytics` is clamped, not rejected.
- The advanced call clamps at 25,000 per page. More rows need paging.
- Filters are country codes in lowercase (`irl`, `usa`) or device names in uppercase (`MOBILE`).
- Every response carries a `error` key on failure, with the Google message and a hint about permissions.
- The daily trend can stop one or two days before `end_date`. Google backfills search data with a short delay, so treat the last two dates as incomplete.
