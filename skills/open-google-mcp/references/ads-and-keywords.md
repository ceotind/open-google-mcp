# Google Ads and Keyword Planner

Three Ads tools and four Keyword Planner tools. All read-only. Verified against `src/open_google_mcp/server.py`.

## Ads Workflow

1. `list_accessible_customers()` returns customer IDs as strings.
2. `get_resource_metadata(resource_name)` lists which fields are selectable, filterable and sortable.
3. `search(...)` runs the GAQL query.

Skip step 2 only when the field names are known from this file.

## Tools

### list_accessible_customers
No arguments. Returns customer IDs. A manager account ID is usable directly.

### get_resource_metadata(resource_name)
Takes a resource like `campaign`, `ad_group`, `keyword_view`, `search_term_view`. Returns the field inventory for it. Call it before a query fails on an unknown field.

### search(customer_id, resource, fields, conditions=None, orderings=None, limit=100)
Runs a read-only GAQL query.

Field rules:

- Fully qualified names only: `campaign.id`, `campaign.name`, `metrics.clicks`, `metrics.cost_micros`, `segments.date`.
- Conditions AND together.
- Ordering is `"field DIRECTION"`, e.g. `"metrics.clicks DESC"`.
- Date conditions: `segments.date DURING LAST_7_DAYS`, or an explicit `BETWEEN` range with `YYYY-MM-DD`.
- `change_event` caps at 10,000 rows.

Example, enabled search campaigns last week:
```
search(customer_id="1234567890", resource="campaign",
  fields=["campaign.id","campaign.name","campaign.status",
          "metrics.clicks","metrics.impressions","metrics.cost_micros"],
  conditions=["campaign.status = 'ENABLED'",
              "campaign.advertising_channel_type = 'SEARCH'",
              "segments.date DURING LAST_7_DAYS"],
  orderings=["metrics.clicks DESC"], limit=10)
```

Cost values arrive in micros. Divide by one million for the currency amount.

Manager accounts: when `search` finds no rows on an account- level resource, it checks whether the ID is a manager account. If it is, it runs the same query on each child and returns combined rows. Each row gains `_source_customer_id` and `_source_customer_name`, and the first element is a note object. Filter those two keys before treating the list as data.

## Keyword Planner

### generate_keyword_ideas(customer_id?, keywords?, url?, geos?, language?, network?, include_adult_keywords?, page_size?)
Ideas from seed terms or a URL. Returns volume, competition and bid ranges.
Pass `keywords`, `url`, or both. At least one is required.
Defaults: language `english`, network GOOGLE_SEARCH_AND_PARTNERS, 50 ideas. `page_size` max is 2,000.

### generate_keyword_historical_metrics(customer_id?, keywords, geos?, language?)
Exact keywords only. No expansion. Use it to confirm volume for a known list.

### generate_keyword_forecast_metrics(customer_id?, keywords, match_types?, currency_code?, start_date?, end_date?, geos?, language?, daily_budget_micros?, max_cpc_bid_micros?)
Simulated campaign: impressions, clicks, CPC, cost. Nothing is created in the account.
Defaults: currency `EUR`, match type EXACT, start tomorrow, 30 day window.

### suggest_geo_target_constants(names, country_code?, locale?)
Turns a place name into a geo constant for the `geos` argument. Call it before any keyword tool that needs `geos`. Do not guess the constant number.

## Keyword Planner Rules

- `customer_id` is optional. It falls back to `GOOGLE_ADS_DEFAULT_CUSTOMER_ID`, then `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.
- The account needs Keyword Planner access in the Google Ads interface. Manager accounts usually do not have it. Pass a child customer ID instead.
- The developer token needs basic or standard access. An explorer token fails with "apply for basic or standard access".
- Budget and bid values are micros. 20,000,000 is 20 currency units.

## Pitfalls

- A bare `id` in `fields` fails. Always qualify.
- Dates with slashes fail. GAQL wants `YYYY-MM-DD`.
- An empty result on a manager account is not proof of no data. Check for `_source_customer_id` rows first.
- Keyword ideas for a URL need a domain Google can read. A blocked or empty page returns nothing useful.
