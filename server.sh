#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env if present (file is gitignored, contains local secrets)
if [ -f "$DIR/.env" ]; then
  set -a
  source "$DIR/.env"
  set +a
fi

exec "$DIR/.venv/bin/python" -m google_ads_mcp_reader
