# Google Ads MCP Reader

A read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for querying Google Ads data using GAQL (Google Ads Query Language). Designed for AI assistants and LLM agents to safely read campaign performance, ad groups, keywords, and more.

## Tools

| Tool | Input | Description |
|------|-------|-------------|
| `list_accessible_customers` | — | Discover which Google Ads account IDs are accessible |
| `get_resource_metadata` | `resource_name` | Explore selectable/filterable/sortable fields for a resource |
| `search` | `customer_id`, `resource`, `fields`, `conditions?`, `orderings?`, `limit?` | Execute read-only GAQL queries |

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
git clone https://github.com/sharpspirit/mcp-server-google-ads.git
cd mcp-server-google-ads
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

## GAQL Tips

- Field names must be fully qualified: `campaign.id`, not `id`
- Date format: `YYYY-MM-DD` with dashes
- Relative dates: `DURING LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH`, `THIS_QUARTER`
- For `change_event` resource, limit must be ≤ 10000
- Conditions are AND-combined
- Use `get_resource_metadata` first to discover valid fields

## License

MIT
