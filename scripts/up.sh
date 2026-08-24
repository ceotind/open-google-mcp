#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$DIR"
docker compose up -d open-google-mcp
echo "Container up. Client configs attach with: docker compose exec -T open-google-mcp python -m open_google_mcp"
