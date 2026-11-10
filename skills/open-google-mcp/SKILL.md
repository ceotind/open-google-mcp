---
name: open-google-mcp
description: Query Google Ads, GSC, GA4 and Bing with this MCP server.
version: 0.1.0
author: Sharp Digital
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  author: Sharp Digital
  hermes:
    tags: [google-ads, search-console, ga4, bing, seo, mcp, reporting]
    related_skills: [agent-skill-distribution]
---

# Open Google MCP Skill

Read-only access to Google Ads, Google Search Console, Google Analytics 4 and Bing Webmaster Tools through this project's MCP server. Every tool reads data. No tool writes, bids, or changes an account.

## When to Use

- The user asks for ads spend, clicks, CPC, or campaign performance.
- The user asks for search queries, rankings, impressions, or indexing status.
- The user asks for site traffic, users, sessions, or page views.
- The user asks for keyword volume, bids, or a campaign forecast.
- The user asks to compare Google and Bing search data.
- Do not use for: changing bids, budgets, campaigns, or account settings. This server is read-only and cannot do it.

## Start Here, Every Time

Never guess an ID. Every product needs a discovery call first.

| Product | First call | Then |
|---|---|---|
| Search Console | `gsc_list_properties` | copy the exact `site_url` |
| Analytics 4 | `ga4_list_properties` | copy the numeric `property_id` |
| Google Ads | `list_accessible_customers` | copy the numeric `customer_id` |
| Bing | `bing_list_sites` | copy the exact `url` field |

Each family also has a capability tool (`gsc_get_capabilities`, `ga4_get_capabilities`, `bing_get_capabilities`) that reports whether its credentials work. Call it when a family fails and the cause is unclear.

## Which File to Load

| Task | File |
|---|---|
| Queries, rankings, indexing, sitemaps | `references/search-console.md` |
| Traffic, users, sessions, page views | `references/analytics.md` |
| Campaigns, spend, keywords, forecasts | `references/ads-and-keywords.md` |
| Bing stats, crawl issues, Google vs Bing | `references/bing.md` |
| Credentials, install, client config, errors | `references/setup-and-auth.md` |

Load one file. Each file holds the exact parameters, the examples and the failure modes for that family.

## Rules That Break Calls

- `site_url` must be byte for byte what the list call returned. `example.com` fails where `https://example.com/` works. `sc-domain:` properties keep that prefix.
- Google Ads fields need the full prefix. `campaign.id`, not `id`. `metrics.clicks`, not `clicks`.
- Dates use dashes. `2026-01-01`, never `2026/01/01`.
- GA4 accepts both ISO dates and relative dates (`28daysAgo`, `today`).
- Filter arguments are JSON strings, not Python dicts.
- Results come back rounded to 4 decimals for CTR and 1 decimal for position.
- A manager account ID is safe to pass. `search` detects it and routes to child accounts, then marks each row with `_source_customer_id`.

## Limits

- `gsc_get_search_analytics` returns at most 500 rows. `gsc_get_advanced_search_analytics` returns at most 25,000 rows per page.
- `ga4_run_report` returns at most 100,000 rows.
- `search` caps `change_event` at 10,000 rows.
- Bing query and page reports refresh weekly. Traffic data refreshes daily.
- Keyword Planner needs a developer token with basic access. Explorer-level tokens are rejected.

## Verification

- A successful call returns rows with the metrics you asked for, not an `error` key.
- A wrong site URL returns an empty result set, not an error. Confirm the URL against the list call first.
- Row counts match the `row_count` or `pagination` field in the response.
