# Agent context: open-google-mcp

This repository is a read-only MCP server for Google Ads, Search Console, Analytics 4 and Bing Webmaster Tools.

Before calling any tool, read `skills/open-google-mcp/SKILL.md`. It holds the discovery-first order, the argument rules and the file map.

- Product detail: `skills/open-google-mcp/references/` (search-console, analytics, ads-and-keywords, bing, setup-and-auth).
- Source of truth for parameter names: `src/open_google_mcp/server.py`.
- Nothing here writes data. No tool changes bids, budgets, campaigns or site settings.

Harness copies of the skill come from `python3 skills/open-google-mcp/scripts/install.py`. Edit the folder here, never a copy.
