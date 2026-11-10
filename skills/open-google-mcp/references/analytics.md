# Google Analytics 4

Five tools. All read-only. Verified against `src/open_google_mcp/server.py`.

## Workflow

1. `ga4_list_properties()` returns every accessible property. Copy the numeric property ID.
2. Call `ga4_get_metadata(property_id)` before inventing a dimension or metric name.
3. Run `ga4_run_report` with metrics only for a summary, then add dimensions.

Property IDs are numbers as strings, like `123456789`. Never pass the measurement ID (`G-XXXX`).

## Tools

### ga4_get_capabilities
No arguments. Lists the tools and reports whether credentials authenticate.

### ga4_list_properties
No arguments. Returns property IDs, display names and account names.

### ga4_get_metadata(property_id)
Every available dimension and metric for that property. Custom dimensions appear here too. Check this before a report fails on an unknown name.

### ga4_run_report(...)
Defaults: no dimensions, metric `activeUsers`, last 28 days, 100 rows.

Arguments:

- `property_id` numeric string.
- `dimensions` comma-separated, e.g. `city,country` or `date,pagePath`.
- `metrics` comma-separated, e.g. `activeUsers,sessions,newUsers`.
- `start_date`, `end_date`: `YYYY-MM-DD`, or relative words `today`, `yesterday`, `7daysAgo`, `28daysAgo`.
- `filters` JSON. String filter: `{"field":"deviceCategory","type":"string_filter","value":"mobile","match_type":"CONTAINS"}`.
  Match types: EXACT, CONTAINS, BEGINS_WITH, ENDS_WITH.
  Numeric filter: `{"field":"...","type":"numeric_filter","value":"...","match_type":"EQUAL"}`.
  An array of filters ANDs together.
- `order_bys` JSON array: `[{"metric":"activeUsers","desc":true}]` or `[{"dimension":"date","desc":false}]`.
- `limit` max 100,000.

Examples:

```
# top pages by views
ga4_run_report(property_id="123456789",
  dimensions="pagePath", metrics="screenPageViews",
  start_date="28daysAgo",
  order_bys='[{"metric":"screenPageViews","desc":true}]', limit=20)

# channel breakdown
ga4_run_report(property_id="123456789",
  dimensions="sessionDefaultChannelGrouping",
  metrics="activeUsers,sessions,newUsers",
  start_date="2026-01-01", end_date="today")

# mobile only, United States
ga4_run_report(property_id="123456789",
  dimensions="pagePath",
  metrics="screenPageViews",
  filters='[{"field":"deviceCategory","type":"string_filter","value":"mobile","match_type":"CONTAINS"},
            {"field":"country","type":"string_filter","value":"United States","match_type":"EXACT"}]')
```

### ga4_run_realtime_report(property_id, dimensions="", metrics="activeUsers", limit=100)
Last 30 minutes only. Same dimension and metric names. No date arguments.

## Response Shape

- `rows`, `row_count`, `total_row_count`.
- `quota`, with remaining tokens per day and per hour. Google caps calls per property per hour, so a quota of 0 means wait.

## Pitfalls

- An unknown dimension or metric fails the whole call. Check `ga4_get_metadata` first.
- `(not set)` appears as a value on many dimensions. It is real data, not an error.
- Filters are JSON strings. A Python dict is rejected on some clients.
- Date strings with slashes fail.
