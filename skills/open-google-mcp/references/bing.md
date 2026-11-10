# Bing Webmaster Tools

Fifteen tools. All read-only. Verified against `src/open_google_mcp/server.py`.

## Workflow

1. `bing_list_sites()` returns verified sites. Copy the exact `url` field.
2. Pass that value as `site_url` in every other Bing tool.

Bing needs one API key (`BING_WEBMASTER_API_KEY`). No service account, no OAuth.

## Tools

### bing_get_capabilities
No arguments. Lists tools and reports whether the API key authenticates.

### bing_list_sites
No arguments. Verified sites with their exact URLs.

### bing_get_query_stats(site_url, limit=100)
Top queries with clicks, impressions and position. Weekly snapshot.

### bing_get_page_stats(site_url, limit=100)
Top pages. Weekly snapshot.

### bing_get_traffic_stats(site_url, days=None)
Daily clicks and impressions with totals. Updates daily. Omit `days` for the default window.

### bing_get_query_pages(site_url, query, limit=100)
Pages that rank for one query. Use it to see which page owns a term.

### bing_get_page_queries(site_url, page, limit=100)
Queries one page ranks for. Use it for content audits.

### bing_get_url_info(site_url, url)
Crawl and index detail for one URL.

### bing_get_crawl_stats(site_url)
Crawl volume and response codes.

### bing_get_crawl_issues(site_url, limit=100)
Indexing problems Bing found.

### bing_get_link_counts(site_url, page=0)
Inbound link counts. `page` is a result page number, not a URL.

### bing_get_sitemaps(site_url)
Submitted sitemaps and feeds.

### bing_keyword_stats(query, country=None, language=None)
Historical keyword data for one term.

### bing_get_related_keywords(query, country=None, language=None, start_date=None, end_date=None, limit=None)
Related term discovery.

### seo_compare_google_bing(bing_site_url, gsc_site_url, days=28, limit=25)
Joins Bing top queries with Google Search Console top queries. Google uses the last N days. Bing uses its latest weekly snapshot. Returns where each engine over- or under-performs.

Example:
```
seo_compare_google_bing(
  bing_site_url="https://example.com/",
  gsc_site_url="https://example.com/",
  days=28, limit=25)
```

Both URLs come from their own list calls. They often differ in form, so copy each one separately.

## Pitfalls

- Query and page reports have no date filter. Only `bing_get_traffic_stats` takes `days`.
- Bing reports lag up to a week. A change published today does not show in query data yet.
- Responses are cached for `BING_CACHE_TTL` seconds, 300 by default. A repeat call can return the same payload.
- The site URL must match the list call. A mismatch returns an error from the Bing API.
