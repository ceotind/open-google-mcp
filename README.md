# Open Google MCP

A read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Google **Ads** (via GAQL) and **Search Console**. Designed for AI assistants and LLM agents to safely read campaign performance, search analytics, and more.

## Tools

| Tool | Input | Description |
|------|-------|-------------|
| `list_accessible_customers` | — | Discover Google Ads account IDs |
| `get_resource_metadata` | `resource_name` | Explore selectable/filterable/sortable fields for a resource |
| `search` | `customer_id`, `resource`, `fields`, `conditions?`, `orderings?`, `limit?` | Execute read-only GAQL queries |
| `gsc_get_capabilities` | — | Get categorized tool list with auth status |
| `gsc_list_properties` | — | List all GSC properties (start here) |
| `gsc_get_site_details` | `site_url` | Verification/ownership for a property |
| `gsc_get_search_analytics` | `site_url`, `days?`, `dimensions?`, `row_limit?` | Top queries with clicks, impressions, CTR, position |
| `gsc_get_performance_overview` | `site_url`, `days?` | Executive summary with daily trend |
| `gsc_compare_search_periods` | `site_url`, `period1_start/end`, `period2_start/end` | Compare two date ranges |
| `gsc_get_advanced_search_analytics` | `site_url`, `start_date?`, `end_date?`, `dimensions?`, `search_type?`, `row_limit?`, `start_row?`, `sort_by?`, `sort_direction?`, `filters?` | Filtered, sorted, paginated analytics |
| `gsc_inspect_url` | `site_url`, `page_url` | Debug a URL's crawl/index status |
| `gsc_get_sitemaps` | `site_url` | List sitemaps with status and errors |

### Manager Account Auto-Routing

If `search` targets a **manager (MCC) account** and finds no data directly, it automatically:
1. Detects the account is a manager
2. Finds child accounts
3. Runs the query on each child
4. Returns combined results with `_source_customer_id` marking which account each row belongs to

## Setup

### Prerequisites (both paths)

- A Google Ads developer token (apply via Google Ads API Center)
- Google Cloud service account with both APIs enabled:
  - [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com)
  - [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)

---

### Option A: Docker (recommended — no Python required)

#### 1. Clone

```bash
git clone https://github.com/ceotind/open-google-mcp.git
cd open-google-mcp
```

#### 2. Create and authorize a service account

A single service account authenticates both Google Ads and Search Console.

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

#### 4. Build and run

```bash
docker compose build
docker compose run --rm open-google-mcp
```

#### 5. MCP client config

All configs point to the project directory (where `.env` lives):

**Claude Desktop:**
```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "docker",
      "args": ["compose", "run", "--rm", "open-google-mcp"],
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
      "command": ["docker", "compose", "run", "--rm", "open-google-mcp"],
      "workdir": "/path/to/open-google-mcp",
      "enabled": true
    }
  }
}
```

**Cursor:**
- **Name**: `open-google-mcp`
- **Type**: `command`
- **Command**: `docker compose run --rm open-google-mcp`
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

Same steps as Option A above — a single service account works for both Ads and GSC.

1. Go to **GCP Console → APIs & Services → Credentials → Create Credentials → Service Account**
2. Download the JSON key file, then copy these fields into `.env`:
   - `GOOGLE_SERVICE_ACCOUNT_EMAIL`
   - `GOOGLE_SERVICE_ACCOUNT_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_KEY_ID`
   - `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID`
   - `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID`
3. **Google Ads**: add the service account email in your manager account
4. **Search Console**: add the same email to your property with Full access

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

#### 4. Run

```bash
source .venv/bin/activate
source .env
python -m open_google_mcp
```

#### 5. MCP client config

**Claude Desktop:**
```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/open-google-mcp",
        "run", "python", "-m", "open_google_mcp"
      ],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_token",
        "GOOGLE_SERVICE_ACCOUNT_EMAIL": "your-sa@project.iam.gserviceaccount.com",
        "GOOGLE_SERVICE_ACCOUNT_KEY": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n",
        "GOOGLE_SERVICE_ACCOUNT_KEY_ID": "your_key_id",
        "GOOGLE_SERVICE_ACCOUNT_CLIENT_ID": "your_client_id",
        "GOOGLE_SERVICE_ACCOUNT_PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

Or use the wrapper script (loads `.env` automatically):
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
- **Command**: `uv --directory /path/to/open-google-mcp run python -m open_google_mcp`
- **Env vars**: All `GOOGLE_ADS_DEVELOPER_TOKEN` + `GOOGLE_SERVICE_ACCOUNT_*` variables

## Usage Examples

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
