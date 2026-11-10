# Development

## Local checkout

```bash
git clone https://github.com/ceotind/open-google-mcp.git
cd open-google-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the tests. They need no network and no credentials.

```bash
pytest
```

## Run from the checkout

```bash
cp .env.example .env      # edit with your credentials
./server.sh               # loads .env, starts the stdio server
```

## Docker build

```bash
cp .env.example .env
docker compose build
docker compose run --rm open-google-mcp
```

`docker compose run` starts one container per session and removes it on exit.

## Live smoke test

Keyword Planner hits the real API:

```bash
source .env && python scripts/smoke_keyword_planner.py [customer_id]
```

## Where the logic lives

| File | Contents |
|---|---|
| `src/open_google_mcp/server.py` | All tool registrations and GAQL execution |
| `src/open_google_mcp/client.py` | Ads credentials and query runner |
| `src/open_google_mcp/gsc_client.py` | Search Console client and OAuth |
| `src/open_google_mcp/ga4_client.py` | Analytics 4 client |
| `src/open_google_mcp/keyword_planner.py` | Keyword Planner request builders |
| `src/open_google_mcp/bing_client.py` | Bing transport, cache, and normalization |

Keyword Planner and Bing have unit tests that use pure fixtures and `httpx.MockTransport`.

## Release

The publish workflow runs on a `v*` tag and does three things:

1. Builds the wheel and sdist, then publishes to PyPI with Trusted Publishing.
2. Builds and pushes a multi-arch image to GHCR, for `amd64` and `arm64`.
3. Tags the image with the version and `latest`.

```bash
# bump version in pyproject.toml, commit, then
git tag v0.2.3
git push origin main --tags
```

Trusted Publishing needs no API token. GHCR uses the workflow token.
