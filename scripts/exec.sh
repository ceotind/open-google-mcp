#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$DIR"
exec docker compose exec -T open-google-mcp python -m open_google_mcp
