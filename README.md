# Open Google MCP

[![PyPI](https://img.shields.io/pypi/v/open-google-mcp.svg)](https://pypi.org/project/open-google-mcp/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/ceotind/open-google-mcp/pkgs/container/open-google-mcp)
[![Python](https://img.shields.io/pypi/pyversions/open-google-mcp.svg)](https://pypi.org/project/open-google-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/ceotind/open-google-mcp/blob/main/LICENSE)

Read-only MCP server for Google Ads, Search Console, Google Analytics 4, and Bing Webmaster Tools.

Every tool reads data. Nothing bids, edits, or changes an account.

![Open Google MCP](https://raw.githubusercontent.com/ceotind/open-google-mcp/main/assets/open-google-mcp-hero.png)

## Install

No clone. One command, one config block.

### uvx

```bash
uvx open-google-mcp
```

### Docker

```bash
docker run -i --rm --env-file ~/.config/open-google-mcp/.env \
  ghcr.io/ceotind/open-google-mcp:latest
```

### Add it to your client

```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "uvx",
      "args": ["open-google-mcp"],
      "env": {
        "GOOGLE_SERVICE_ACCOUNT_EMAIL": "...",
        "GOOGLE_SERVICE_ACCOUNT_KEY": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "...",
        "BING_WEBMASTER_API_KEY": "optional"
      }
    }
  }
}
```

Cursor, VS Code, opencode, and the Docker form: [client configuration](https://github.com/ceotind/open-google-mcp/blob/main/docs/clients.md).

Then restart the client and ask for `gsc_list_properties`.

## Credentials

<details>
<summary>Set up a service account and developer token</summary>

One service account covers Google Ads, Search Console, and Analytics 4.

1. Create a service account in **GCP Console → APIs & Services → Credentials**.
2. Download the JSON key. Copy the `private_key` and the other fields.
3. Enable these APIs in the same GCP project:
   [Ads](https://console.cloud.google.com/apis/library/googleads.googleapis.com),
   [Search Console](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com),
   [Analytics Data](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com),
   [Analytics Admin](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com).
4. Grant the service account email access:
   - **Ads**: manager account → Settings → Account access → Service account users
   - **Search Console**: property → Settings → Users and permissions → Full access
   - **Analytics 4**: Admin → Account Access Management → Viewer
5. Apply for a [Google Ads developer token](https://developers.google.com/google-ads/api/docs/first-call/dev-token). Basic access is required.

| Variable | Needed | Use |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | yes | Service account address |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | yes | Private key, keep the `\n` escapes |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | yes | Google Ads API token |
| `GOOGLE_SERVICE_ACCOUNT_KEY_ID` | no | Private key ID |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID` | no | Client ID |
| `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID` | no | GCP project |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | no | Manager account routing |
| `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` | no | Default for Keyword Planner |
| `GA4_CREDENTIALS_PATH` | no | Separate Analytics credential file |
| `BING_WEBMASTER_API_KEY` | no | Bing tools only |

Simpler alternative: set `GOOGLE_ADS_JSON_KEY_FILE` to the path of your downloaded key. It covers all three Google products, and removes the need to paste a private key into JSON.

</details>

## What you get

| Platform | Tools | First call |
|---|---|---|
| Google Ads (GAQL) | 3 | `list_accessible_customers` |
| Search Console | 9 | `gsc_list_properties` |
| Analytics 4 | 5 | `ga4_list_properties` |
| Keyword Planner | 4 | `suggest_geo_target_constants` |
| Bing Webmaster | 15 | `bing_list_sites` |

36 tools total. Full list: [tools reference](https://github.com/ceotind/open-google-mcp/blob/main/docs/tools.md).

## Examples

```
list_accessible_customers
```

```
gsc_get_search_analytics(site_url="https://example.com/", days=28, dimensions="query")
```

```
ga4_run_report(property_id="123456789", dimensions="country",
               metrics="activeUsers", start_date="28daysAgo")
```

More, including keyword forecasting and Google-vs-Bing comparison: [examples](https://github.com/ceotind/open-google-mcp/blob/main/docs/examples.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `403 insufficientPermissions` | Add the service account to that product |
| Developer token rejected | Apply for basic access; explorer tokens fail |
| Keyword Planner returns nothing | Use a child customer ID, not the manager |
| Search Console returns empty | `site_url` must match the property string exactly |
| Bing auth error | Check the key, and that the site is verified |
| Tool missing in the client | Check the config path, and that `uvx` is on PATH |

A startup check prints missing variables to stderr. It never blocks the server.

## Documentation

| Topic | File |
|---|---|
| Every tool and parameter | [tools.md](https://github.com/ceotind/open-google-mcp/blob/main/docs/tools.md) |
| Worked examples | [examples.md](https://github.com/ceotind/open-google-mcp/blob/main/docs/examples.md) |
| Client configs | [clients.md](https://github.com/ceotind/open-google-mcp/blob/main/docs/clients.md) |
| GAQL rules | [gaql.md](https://github.com/ceotind/open-google-mcp/blob/main/docs/gaql.md) |
| Build and release | [development.md](https://github.com/ceotind/open-google-mcp/blob/main/docs/development.md) |

Upgrading: `uvx open-google-mcp@latest`. Plain `uvx` reuses the cached version.

## License

MIT
