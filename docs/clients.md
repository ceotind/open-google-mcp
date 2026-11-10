# Client configuration

Every client needs the same two things: a command that starts the server, and credentials in an `env` block.

Three ways to start it:

| Mode | Command |
|---|---|
| uvx | `uvx open-google-mcp` |
| Docker | `docker run -i --rm --env-file /abs/path/.env ghcr.io/ceotind/open-google-mcp:latest` |
| Checkout | `/abs/path/to/open-google-mcp/server.sh` |

The uvx and Docker modes need no repository. Credentials arrive through the client, not a local `.env`.

## Claude Desktop

`~/.config/Claude/claude_desktop_config.json` on Linux, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

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
        "BING_WEBMASTER_API_KEY": "..."
      }
    }
  }
}
```

## opencode

`~/.config/opencode/opencode.json`, or `opencode.json` in the project root.

opencode calls the field `environment`, not `env`.

```json
{
  "mcp": {
    "open-google-mcp": {
      "type": "local",
      "command": ["uvx", "open-google-mcp"],
      "environment": {
        "GOOGLE_SERVICE_ACCOUNT_EMAIL": "...",
        "GOOGLE_SERVICE_ACCOUNT_KEY": "...",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "..."
      },
      "enabled": true
    }
  }
}
```

Or let the CLI write it:

```bash
opencode mcp add open-google-mcp -- uvx open-google-mcp
```

## Cursor

`~/.cursor/mcp.json`. Same shape as the Claude Desktop block.

## VS Code

`.vscode/mcp.json` in the workspace. VS Code uses `servers`, not `mcpServers`.

```json
{
  "servers": {
    "open-google-mcp": {
      "command": "uvx",
      "args": ["open-google-mcp"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "..."
      }
    }
  }
}
```

## Docker variant

Replace the command and args in any block above:

```json
{
  "command": "docker",
  "args": ["run", "-i", "--rm",
           "--env-file", "/home/you/.config/open-google-mcp/.env",
           "ghcr.io/ceotind/open-google-mcp:latest"]
}
```

No `env` block is needed. The file supplies every variable.

## Rules that break configs

1. **The private key stays one JSON string.** `\n` inside it is correct. A raw multi-line paste breaks the file.
2. **No trailing commas.** These parsers are strict.
3. **Paths must be absolute.** GUI clients do not start in your shell, so `~` fails.
4. **`uvx` must be on the client's PATH.** If the terminal works and the client does not, use the output of `which uvx`.
5. **One server per name.** Two entries with the same name conflict.

## Verify

```bash
opencode mcp list      # opencode
```

Then ask the agent for `gsc_get_capabilities`. A reply of `Connected` means the config works.

## Security

These files hold a private key.

1. Run `chmod 600` on them.
2. Never commit them.
3. Add `.cursor/` and `.vscode/mcp.json` to `.gitignore`.
