# Google Ads MCP Reader

A read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for querying Google Ads data using GAQL (Google Ads Query Language). Designed for AI assistants and LLM agents to safely read campaign performance, ad groups, keywords, and more.

## Tools

| Tool | Input | Description |
|------|-------|-------------|
| `list_accessible_customers` | — | Discover which Google Ads account IDs are accessible |
| `get_resource_metadata` | `resource_name` | Explore selectable/filterable/sortable fields for a resource |
| `search` | `customer_id`, `resource`, `fields`, `conditions?`, `orderings?`, `limit?` | Execute read-only GAQL queries |
| `gsc_list_properties` | — | List all Google Search Console properties |
| `gsc_get_site_details` | `site_url` | Get verification details for a GSC property |
| `gsc_get_search_analytics` | `site_url`, `days?`, `dimensions?`, `row_limit?` | Top queries with clicks, impressions, CTR, position |
| `gsc_get_performance_overview` | `site_url`, `days?` | Performance summary with daily trend |
| `gsc_compare_search_periods` | `site_url`, `period1_start`, `period1_end`, `period2_start`, `period2_end` | Compare performance between two date ranges |
| `gsc_get_advanced_search_analytics` | `site_url`, `start_date?`, `end_date?`, `dimensions?`, `search_type?`, `row_limit?`, `start_row?`, `sort_by?`, `sort_direction?`, `filters?` | Analytics with filtering, sorting, pagination |
| `gsc_inspect_url` | `site_url`, `page_url` | Check crawl/index status of a URL |
| `gsc_get_sitemaps` | `site_url` | List sitemaps with status and errors |

### Manager Account Auto-Routing

If `search` targets a **manager (MCC) account** and finds no data directly, it automatically:
1. Detects the account is a manager
2. Finds child accounts
3. Runs the query on each child
4. Returns combined results with `_source_customer_id` marking which account each row belongs to

## Setup

### Prerequisites

- Python 3.10+
- A Google Ads developer token (apply via Google Ads API Center)
- Google Ads API access enabled for your account
- OAuth 2.0 credentials or Application Default Credentials (ADC)

### 1. Clone and install

```bash
git clone https://github.com/ceotind/readonly-mcp-google-ads.git
cd readonly-mcp-google-ads
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure authentication

Copy `.env.example` and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your values
```

**Authentication methods:**

| Method | Env vars required | Notes |
|--------|------------------|-------|
| ADC (recommended) | `GOOGLE_ADS_DEVELOPER_TOKEN` | Run `gcloud auth application-default login` |
| OAuth refresh token | `GOOGLE_ADS_DEVELOPER_TOKEN` + `GOOGLE_ADS_REFRESH_TOKEN` + `GOOGLE_ADS_CLIENT_ID` + `GOOGLE_ADS_CLIENT_SECRET` | For automated environments |

**Google Search Console authentication** reuses your existing Google Ads OAuth
credentials (`GOOGLE_ADS_CLIENT_ID` and `GOOGLE_ADS_CLIENT_SECRET`) — no
additional environment variables needed.

Make sure the [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)
is enabled in your GCP project and the `.../auth/webmasters.readonly` scope is
added to your [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent).

On first use of any GSC tool, a browser window opens for you to authorize the
GSC scope. The token is cached afterwards.

| Alternative method | Env var | Notes |
|-------------------|---------|-------|
| Dedicated OAuth file | `GSC_OAUTH_CLIENT_SECRETS_FILE` | Path to a Desktop app client_secrets.json |
| Service account | `GSC_CREDENTIALS_PATH` | For headless/automated environments |

### 3. Run

```bash
source .venv/bin/activate
source .env
python -m google_ads_mcp_reader
```

Uses stdio transport by default (for Claude Desktop, Cursor, opencode, etc.).

## MCP Client Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/mcp-server-google-ads",
        "run", "python", "-m", "google_ads_mcp_reader"
      ],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_token",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "your_optional_mcc_id"
      }
    }
  }
}
```

Or use the wrapper script:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/path/to/mcp-server-google-ads/server.sh"
    }
  }
}
```

### opencode

Add to your `opencode.jsonc`:

```json
{
  "mcp": {
    "google-ads-mcp": {
      "type": "local",
      "command": ["/path/to/mcp-server-google-ads/server.sh"],
      "enabled": true
    }
  }
}
```

### Cursor

Go to Settings → MCP Servers → Add:

- **Name**: `google-ads`
- **Type**: `command`
- **Command**: `uv --directory /path/to/mcp-server-google-ads run python -m google_ads_mcp_reader`
- **Env vars**: Add `GOOGLE_ADS_DEVELOPER_TOKEN`, etc.

## Usage Examples

### List accounts

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

## GAQL Tips

- Field names must be fully qualified: `campaign.id`, not `id`
- Date format: `YYYY-MM-DD` with dashes
- Relative dates: `DURING LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH`, `THIS_QUARTER`
- For `change_event` resource, limit must be ≤ 10000
- Conditions are AND-combined
- Use `get_resource_metadata` first to discover valid fields

## License

MIT
