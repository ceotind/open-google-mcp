# Open Google MCP

A read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for **Google Ads** (via GAQL), **Search Console**, **Google Analytics 4**, and **Bing Webmaster Tools**. Designed for AI assistants and LLM agents to safely read campaign performance, search analytics, website traffic, and more.

<img width="1672" height="941" alt="open-google-mcp" src="https://github.com/user-attachments/assets/3e082501-6a06-43bb-b26d-3f026ba76348" />

## Tools

### Google Ads

| Tool | Input | Description |
|------|-------|-------------|
| `list_accessible_customers` | — | Discover Google Ads account IDs |
| `get_resource_metadata` | `resource_name` | Explore selectable/filterable/sortable fields for a resource |
| `search` | `customer_id`, `resource`, `fields`, `conditions?`, `orderings?`, `limit?` | Execute read-only GAQL queries |

### Google Search Console

| Tool | Input | Description |
|------|-------|-------------|
| `gsc_get_capabilities` | — | Get categorized tool list with auth status |
| `gsc_list_properties` | — | List all GSC properties (start here) |
| `gsc_get_site_details` | `site_url` | Verification/ownership for a property |
| `gsc_get_search_analytics` | `site_url`, `days?`, `dimensions?`, `row_limit?` | Top queries with clicks, impressions, CTR, position |
| `gsc_get_performance_overview` | `site_url`, `days?` | Executive summary with daily trend |
| `gsc_compare_search_periods` | `site_url`, `period1_start/end`, `period2_start/end` | Compare two date ranges |
| `gsc_get_advanced_search_analytics` | `site_url`, `start_date?`, `end_date?`, `dimensions?`, `search_type?`, `row_limit?`, `start_row?`, `sort_by?`, `sort_direction?`, `filters?` | Filtered, sorted, paginated analytics |
| `gsc_inspect_url` | `site_url`, `page_url` | Debug a URL's crawl/index status |
| `gsc_get_sitemaps` | `site_url` | List sitemaps with status and errors |

### Google Analytics 4

| Tool | Input | Description |
|------|-------|-------------|
| `ga4_get_capabilities` | — | Get categorized tool list with auth status |
| `ga4_list_properties` | — | Discover all accessible GA4 properties |
| `ga4_get_metadata` | `property_id` | Browse available dimensions and metrics |
| `ga4_run_report` | `property_id`, `dimensions?`, `metrics?`, `start_date?`, `end_date?`, `filters?`, `order_bys?`, `limit?` | Run a standard report with filtering and ordering |
| `ga4_run_realtime_report` | `property_id`, `dimensions?`, `metrics?`, `limit?` | Get real-time data (last 30 minutes) |

### Google Keyword Planner

| Tool | Input | Description |
|------|-------|-------------|
| `generate_keyword_ideas` | `customer_id?`, `keywords?`/`url?`, `geos?`, `language?`, `network?`, `page_size?` | Keyword ideas with search volume, competition, bid ranges |
| `generate_keyword_historical_metrics` | `customer_id?`, `keywords`, `geos?`, `language?` | Historical metrics for exact keywords |
| `generate_keyword_forecast_metrics` | `customer_id?`, `keywords`, `match_types?`, `currency_code?`, `start/end_date?`, `budget/bid?` | Simulated campaign forecast (impressions, clicks, CPC, cost) |
| `suggest_geo_target_constants` | `names`, `country_code?`, `locale?` | Look up geo resource names (e.g. Ireland → `geoTargetConstants/2372`) |

Keyword Planner tools reuse the same service account + developer token as the Ads tools. `customer_id` is optional — it falls back to `GOOGLE_ADS_DEFAULT_CUSTOMER_ID`, then `GOOGLE_ADS_LOGIN_CUSTOMER_ID` from `.env`. The account needs Keyword Planner access (Tools → Planning → Keyword Planner in Google Ads); manager (MCC) accounts usually don't have it — use a child customer ID. **The developer token must have at least basic access** (explorer-level tokens are rejected: "apply for basic or standard access" — ads.google.com → Tools → API Center → Request higher access).

### Bing Webmaster Tools

| Tool | Input | Description |
|------|-------|-------------|
| `bing_get_capabilities` | — | Get tool list with auth status |
| `bing_list_sites` | — | List verified sites (start here) |
| `bing_get_query_stats` | `site_url`, `limit?` | Top queries with clicks, impressions, positions |
| `bing_get_page_stats` | `site_url`, `limit?` | Top pages with clicks, impressions, positions |
| `bing_get_traffic_stats` | `site_url`, `days?` | Daily clicks and impressions with totals |
| `bing_get_query_pages` | `site_url`, `query`, `limit?` | Pages ranking for one query |
| `bing_get_page_queries` | `site_url`, `page`, `limit?` | Queries a page ranks for |
| `bing_get_url_info` | `site_url`, `url` | Crawl and index details for one URL |
| `bing_get_crawl_stats` | `site_url` | Crawl volume and response codes |
| `bing_get_crawl_issues` | `site_url`, `limit?` | Indexing problems found by Bing |
| `bing_get_link_counts` | `site_url`, `page?` | Inbound link counts per page |
| `bing_get_sitemaps` | `site_url` | Submitted sitemaps and feeds |
| `bing_keyword_stats` | `query`, `country?`, `language?` | Historical keyword data |
| `bing_get_related_keywords` | `query`, `country?`, `language?`, `start/end_date?`, `limit?` | Related keyword discovery |
| `seo_compare_google_bing` | `bing_site_url`, `gsc_site_url`, `days?`, `limit?` | Join Google and Bing top queries |

Bing tools use an API key — no OAuth and no service account. Bing updates query and page reports weekly. Traffic data updates daily. Query and page reports have no date-range filter.

### Manager Account Auto-Routing

If `search` targets a **manager (MCC) account** and finds no data directly, it automatically:
1. Detects the account is a manager
2. Finds child accounts
3. Runs the query on each child
4. Returns combined results with `_source_customer_id` marking which account each row belongs to

## Setup

### Prerequisites

Google credentials are only needed for Google tools. Bing tools need only an API key.

- **Bing only:** a Bing Webmaster Tools API key (see below).
- **Google Ads:** a developer token (apply via Google Ads API Center).
- **Google Cloud:** a service account with the following APIs enabled:
  - [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com)
  - [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)
  - [Google Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com)
  - [Google Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com)

#### Bing Webmaster Tools (optional)

Bing tools need one API key. No OAuth and no service account are required.

1. Sign in at [Bing Webmaster Tools](https://www.bing.com/webmasters).
2. Add your site and verify ownership.
3. Open **Settings → API Access**.
4. Accept the terms and click **Generate API Key**.
5. Add the key to `.env`:
   ```bash
   BING_WEBMASTER_API_KEY="your_key_here"
   ```

The key belongs to your user account. One key covers every verified site.

---

### Option A: Docker (recommended — no Python required)

#### 1. Clone

```bash
git clone https://github.com/ceotind/open-google-mcp.git
cd open-google-mcp
```

#### 2. Create and authorize a service account

A single service account authenticates Google Ads, Search Console, and Google Analytics 4.

1. Go to **GCP Console → APIs & Services → Credentials → Create Credentials → Service Account**
2. Download the JSON key file, then copy these fields into `.env`:
   - `GOOGLE_SERVICE_ACCOUNT_EMAIL`
   - `GOOGLE_SERVICE_ACCOUNT_KEY` (the `private_key` — keep the `\n` escapes)
   - `GOOGLE_SERVICE_ACCOUNT_KEY_ID`
   - `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID`
   - `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID`
3. **Google Ads**: add the service account email in your manager account
   (**Settings → Account access → Service account users**)
4. **Search Console**: add the same email to your property
   (**Settings → Users and permissions → Add user**, grant Full access)
5. **Google Analytics 4**: add the same email to your GA4 property
   (**Admin → Account Access Management → Add user → Viewer**)

#### 3. Configure `.env`

```bash
cp .env.example .env
# Edit .env with the service account values + developer token
```

| Variable | Description |
|----------|-------------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads API developer token |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | Service account email |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Private key (with `\n` newlines) |
| `GOOGLE_SERVICE_ACCOUNT_KEY_ID` | Private key ID |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID` | Client ID |
| `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID` | GCP project ID |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Optional — for MCC account routing |
| `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` | Optional — default customer_id for Keyword Planner tools (falls back to LOGIN_CUSTOMER_ID) |
| `GA4_CREDENTIALS_PATH` | Optional — dedicated GA4 credential file |
| `BING_WEBMASTER_API_KEY` | Optional — Bing Webmaster Tools API key |
| `BING_CACHE_TTL` | Optional — Bing response cache in seconds (default: 300) |
| `BING_REQUEST_TIMEOUT` | Optional — Bing HTTP timeout in seconds (default: 30) |

#### 4. Build and start the container (once)

```bash
docker compose build
docker compose up -d open-google-mcp
```

> This starts a single long-lived container. Client configs attach to it with
> `docker compose exec` instead of `docker compose run`, so a new container is
> **not** created every session. (Don't use `docker compose run` for a client —
> it spawns a new container each launch and `--rm` never removes a long-running
> stdio server, so containers pile up.)

#### 5. MCP client config

**Claude Desktop:**
```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "docker",
      "args": ["compose", "exec", "-T", "open-google-mcp", "python", "-m", "open_google_mcp"],
      "workdir": "/path/to/open-google-mcp"
    }
  }
}
```

**opencode:**
```json
{
  "mcp": {
    "open-google-mcp": {
      "type": "local",
      "command": ["docker", "compose", "exec", "-T", "open-google-mcp", "python", "-m", "open_google_mcp"],
      "workdir": "/path/to/open-google-mcp",
      "enabled": true
    }
  }
}
```

**Cursor:**
- **Name**: `open-google-mcp`
- **Type**: `command`
- **Command**: `docker compose exec -T open-google-mcp python -m open_google_mcp`
- **Working directory**: `/path/to/open-google-mcp`

---

### Option B: Python (local install)

#### 1. Clone and install

```bash
git clone https://github.com/ceotind/open-google-mcp.git
cd open-google-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### 2. Create and authorize a service account

Same steps as Option A above — a single service account works for Ads, GSC, and GA4.

1. Go to **GCP Console → APIs & Services → Credentials → Create Credentials → Service Account**
2. Download the JSON key file, then copy these fields into `.env`:
   - `GOOGLE_SERVICE_ACCOUNT_EMAIL`
   - `GOOGLE_SERVICE_ACCOUNT_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_KEY_ID`
   - `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID`
   - `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID`
3. **Google Ads**: add the service account email in your manager account
4. **Search Console**: add the same email to your property with Full access
5. **Google Analytics 4**: add the same email to your GA4 property with Viewer access

#### 3. Configure `.env`

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads API developer token |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | Service account email |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Private key (with `\n` newlines) |
| `GOOGLE_SERVICE_ACCOUNT_KEY_ID` | Private key ID |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID` | Client ID |
| `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID` | GCP project ID |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Optional — for MCC account routing |
| `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` | Optional — default customer_id for Keyword Planner tools (falls back to LOGIN_CUSTOMER_ID) |
| `GA4_CREDENTIALS_PATH` | Optional — dedicated GA4 credential file |
| `BING_WEBMASTER_API_KEY` | Optional — Bing Webmaster Tools API key |
| `BING_CACHE_TTL` | Optional — Bing response cache in seconds (default: 300) |
| `BING_REQUEST_TIMEOUT` | Optional — Bing HTTP timeout in seconds (default: 30) |

#### 4. Run

```bash
source .venv/bin/activate
source .env
python -m open_google_mcp
```

Or use the wrapper script (loads `.env` automatically):
```bash
./server.sh
```

#### 5. MCP client config

**Claude Desktop:**
```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "/path/to/open-google-mcp/server.sh"
    }
  }
}
```

**opencode:**
```json
{
  "mcp": {
    "open-google-mcp": {
      "type": "local",
      "command": ["/path/to/open-google-mcp/server.sh"],
      "enabled": true
    }
  }
}
```

**Cursor:**
- **Name**: `open-google-mcp`
- **Type**: `command`
- **Command**: `/path/to/open-google-mcp/server.sh`

---

## Google Ads — Usage Examples

### List Ads accounts

```
list_accessible_customers
```

### Discover fields for a resource

```
get_resource_metadata(resource_name="campaign")
```

### Get active search campaigns with performance

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

### Get child accounts under a manager

```
search(
  customer_id="1234567890",
  resource="customer_client",
  fields=["customer_client.id", "customer_client.descriptive_name", "customer_client.manager"]
)
```

---

## Google Search Console — Usage Examples

### List GSC properties

```
gsc_list_properties
```

### Get search analytics

```
gsc_get_search_analytics(
  site_url="https://example.com",
  days=28,
  dimensions="query",
  row_limit=10
)
```

### Get performance overview

```
gsc_get_performance_overview(
  site_url="https://example.com",
  days=28
)
```

### Compare two time periods

```
gsc_compare_search_periods(
  site_url="https://example.com",
  period1_start="2025-01-01",
  period1_end="2025-01-31",
  period2_start="2025-02-01",
  period2_end="2025-02-28",
  dimensions="query",
  limit=10
)
```

### Advanced analytics with filters

```
gsc_get_advanced_search_analytics(
  site_url="https://example.com",
  dimensions="query,device",
  search_type="WEB",
  row_limit=50,
  sort_by="impressions",
  sort_direction="descending",
  filters='[{"dimension":"country","operator":"equals","expression":"usa"}]'
)
```

### Inspect a URL

```
gsc_inspect_url(
  site_url="https://example.com",
  page_url="https://example.com/blog/post"
)
```

### List sitemaps

```
gsc_get_sitemaps(site_url="https://example.com")
```

---

## Google Analytics 4 — Usage Examples

### Start here — discover properties

```
ga4_list_properties
```

Returns your property ID (e.g. `123456789`) — use it in all other GA4 tools.

### Browse available dimensions and metrics

```
ga4_get_metadata(property_id="123456789")
```

Returns 300+ dimensions and 100+ metrics available for reporting.

### Run a basic report (property-level summary)

```
ga4_run_report(
  property_id="123456789",
  metrics="activeUsers,sessions,newUsers",
  start_date="28daysAgo",
  end_date="today"
)
```

### Top countries by users

```
ga4_run_report(
  property_id="123456789",
  dimensions="country",
  metrics="activeUsers",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys=[{"metric": "activeUsers", "desc": true}]
)
```

### Top pages with views

```
ga4_run_report(
  property_id="123456789",
  dimensions="pagePath",
  metrics="screenPageViews,activeUsers",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys=[{"metric": "screenPageViews", "desc": true}]
)
```

### Traffic sources breakdown

```
ga4_run_report(
  property_id="123456789",
  dimensions="sessionDefaultChannelGrouping",
  metrics="activeUsers,sessions",
  start_date="28daysAgo",
  end_date="today",
  limit=10,
  order_bys=[{"metric": "activeUsers", "desc": true}]
)
```

### Filter by country (e.g. only Ireland)

```
ga4_run_report(
  property_id="123456789",
  dimensions="city",
  metrics="activeUsers",
  start_date="28daysAgo",
  end_date="today",
  filters={"field": "country", "type": "string_filter",
           "value": "Ireland", "match_type": "EXACT"},
  limit=10
)
```

### Device breakdown

```
ga4_run_report(
  property_id="123456789",
  dimensions="deviceCategory",
  metrics="activeUsers,sessions",
  start_date="28daysAgo",
  end_date="today"
)
```

### Real-time report (last 30 minutes)

```
ga4_run_realtime_report(
  property_id="123456789",
  dimensions="country,deviceCategory",
  metrics="activeUsers",
  limit=10
)
```

### Date formats

You can use relative or absolute dates:
- Relative: `today`, `yesterday`, `7daysAgo`, `28daysAgo`, `30daysAgo`
- Absolute: `2026-01-01` (YYYY-MM-DD format)

---

## Google Keyword Planner — Usage Examples

`customer_id` is optional everywhere — set `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` in `.env` and omit it in calls.

### Keyword ideas for a seed term

```text
generate_keyword_ideas(
  keywords=["salsa classes dublin", "salsa dancing"],
  geos=["geoTargetConstants/2372"],   # Ireland — find via suggest_geo_target_constants
  language="english"
)
```

### Historical metrics for exact keywords

```text
generate_keyword_historical_metrics(
  keywords=["salsa classes dublin", "bachata classes dublin"],
  geos=["geoTargetConstants/2372"]
)
```

### Forecast a campaign for next month

```text
generate_keyword_forecast_metrics(
  keywords=["salsa classes dublin", "salsa dancing"],
  match_types=["PHRASE", "EXACT"],
  currency_code="EUR",
  daily_budget_micros=20000000,   # €20/day
  max_cpc_bid_micros=500000       # €0.50 max CPC
)
```

### Find a geo constant

```text
suggest_geo_target_constants(names=["Ireland"], country_code="IE")
```

---

## Bing Webmaster Tools — Usage Examples

Bing needs one API key. Set `BING_WEBMASTER_API_KEY` in `.env`. No OAuth flow runs.

### Start here — list verified sites

```text
bing_list_sites()
```

Use the exact `url` value from this response as `site_url` in every other Bing tool.

### Top queries

```text
bing_get_query_stats(site_url="https://example.com/", limit=50)
```

### Top pages

```text
bing_get_page_stats(site_url="https://example.com/", limit=50)
```

### Daily traffic trend

```text
bing_get_traffic_stats(site_url="https://example.com/", days=30)
```

### Pages ranking for one query

```text
bing_get_query_pages(site_url="https://example.com/", query="salsa classes dublin")
```

### Queries for one page

```text
bing_get_page_queries(site_url="https://example.com/", page="https://example.com/classes")
```

### Inspect a URL

```text
bing_get_url_info(site_url="https://example.com/", url="https://example.com/classes")
```

### Crawl issues

```text
bing_get_crawl_issues(site_url="https://example.com/", limit=50)
```

### Submitted sitemaps

```text
bing_get_sitemaps(site_url="https://example.com/")
```

### Keyword data

```text
bing_keyword_stats(query="salsa classes dublin", country="ie", language="en-IE")
bing_get_related_keywords(query="salsa classes dublin", country="ie", language="en-IE")
```

Use IETF language tags like `en-US`, `en-IE`, or `ja-JP`. Bing rejects a bare code like `en`. The client adds the country when the tag has no region.

`bing_get_related_keywords` defaults to the last 30 days. Bing may return an empty list for low-volume terms.

### Compare Google and Bing

```text
seo_compare_google_bing(
  bing_site_url="https://example.com/",
  gsc_site_url="sc-domain:example.com",
  days=28,
  limit=25
)
```

The comparison joins queries by normalized text. It returns shared queries with click gaps. It also returns queries that appear on only one engine.

### Bing data limits

- Query and page reports are top-N snapshots.
- Bing refreshes those reports weekly.
- No date-range filter exists for query or page data.
- `bing_get_traffic_stats` is the only daily series.
- New or low-traffic sites may return empty rows until Bing collects data.
- Responses are cached for 5 minutes to protect the daily quota.

---

## GAQL Tips

- Field names must be fully qualified: `campaign.id`, not `id`
- Date format: `YYYY-MM-DD` with dashes
- Relative dates: `DURING LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH`, `THIS_QUARTER`
- For `change_event` resource, limit must be ≤ 10000
- Conditions are AND-combined
- Use `get_resource_metadata` first to discover valid fields

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest          # unit tests — no network or credentials required
```

The Keyword Planner logic lives in `src/open_google_mcp/keyword_planner.py` (pure request builders and result flatteners, fully unit-tested). A live smoke test against the real API is available:

```bash
source .env && python scripts/smoke_keyword_planner.py [customer_id]
```

The Bing transport and normalization logic lives in `src/open_google_mcp/bing_client.py`. Its tests use `httpx.MockTransport`, so they need no network and no key.

## License

MIT
