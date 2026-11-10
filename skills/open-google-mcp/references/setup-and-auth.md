# Setup, Credentials and Client Config

The server runs as a stdio MCP process. Three install paths, in order of speed: `uvx`, Docker, then a local checkout. The `uvx` path needs no clone and no project folder.

## Environment Variables

Google tools need a service account plus an Ads developer token. Bing needs one API key.

| Variable | Use |
|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads API token |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | service account address |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | private key, keep the `\n` escapes |
| `GOOGLE_SERVICE_ACCOUNT_KEY_ID` | private key ID |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID` | client ID |
| `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID` | GCP project |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | optional, manager account routing |
| `GOOGLE_ADS_DEFAULT_CUSTOMER_ID` | optional, default for Keyword Planner |
| `GA4_CREDENTIALS_PATH` | optional, separate GA4 credentials file |
| `BING_WEBMASTER_API_KEY` | optional, Bing tools only |
| `BING_CACHE_TTL` | optional, seconds, default 300 |
| `BING_REQUEST_TIMEOUT` | optional, seconds, default 30 |

Credentials reach the process one of two ways. The `uvx` install has no project folder, so it must use the client `env` block. The Docker and checkout installs read `.env` at the project root. Never commit it.

## Access Each Product Needs

The same service account email goes into three places:

- Google Ads: manager account, Settings, Account access, service account users.
- Search Console: property, Settings, Users and permissions, Full access.
- Analytics 4: Admin, Account Access Management, Viewer.

The four Google APIs must be enabled in the GCP project: Google Ads API, Search Console API, Analytics Data API, Analytics Admin API.

## install paths

### uvx

`uvx open-google-mcp` runs the published package from the PyPI cache. It needs uv, not Python. Nothing installs globally and no folder is created. All config goes in the client `env` block. Credential files, such as `GA4_CREDENTIALS_PATH`, need absolute paths in this mode.

First run takes about a minute. Later runs start in under a second.

### Docker

```
docker compose build
docker compose up -d open-google-mcp
```

Clients attach with `docker compose exec`, never `docker compose run`. Run creates a new container on every launch, and a long-running stdio server never exits, so containers pile up.

### Local checkout

Install into a virtual environment at the project root, then run the entry point. `server.sh` starts it from the checkout and loads `.env` for you.

## Client Config

The `uvx` form needs no path:

```json
{
  "mcpServers": {
    "open-google-mcp": {
      "command": "uvx",
      "args": ["open-google-mcp"],
      "env": { "GOOGLE_ADS_DEVELOPER_TOKEN": "...", "GOOGLE_SERVICE_ACCOUNT_EMAIL": "...", "GOOGLE_SERVICE_ACCOUNT_KEY": "..." }
    }
  }
}
```

For Docker and checkout, point the client at the absolute path of `server.sh` or at the Docker exec form. The project README, section "Setup", lists every client.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `403 insufficientPermissions` | service account not added to that product |
| `developer token` rejected | explorer-level token, needs basic or standard access |
| Keyword Planner returns nothing | the account has no Keyword Planner access, use a child customer ID |
| Empty result on Search Console | site URL does not match the property string |
| Bing auth error | key missing or wrong, or the site is not verified |
| Tool missing from the client | client config path wrong, or the process failed to start |

Every error response carries an `error` key with the provider message. Read it before retrying.
