import os
import sys

from .server import mcp

DOCS_URL = "https://github.com/ceotind/open-google-mcp#setup"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _has_service_account() -> bool:
    return bool(_env("GOOGLE_SERVICE_ACCOUNT_EMAIL") and _env("GOOGLE_SERVICE_ACCOUNT_KEY"))


def _has_credential_file() -> bool:
    names = ("GOOGLE_ADS_JSON_KEY_FILE", "GA4_CREDENTIALS_PATH", "GSC_CREDENTIALS_PATH")
    return any(_env(name) for name in names)


def _warn_unconfigured() -> None:
    """Print setup hints to stderr. Never raises, never writes to stdout."""
    if not (_has_service_account() or _has_credential_file()):
        notes = [
            "Google Ads, Search Console and Analytics: no credentials. "
            "Set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_KEY.",
        ]
    else:
        notes = []

    if not _env("GOOGLE_ADS_DEVELOPER_TOKEN"):
        notes.append("Google Ads: GOOGLE_ADS_DEVELOPER_TOKEN is unset; Ads and Keyword Planner calls will fail.")

    if not _env("BING_WEBMASTER_API_KEY"):
        notes.append("Bing: BING_WEBMASTER_API_KEY is unset; Bing tools will fail.")

    if not notes:
        return

    try:
        print("[open-google-mcp] startup check", file=sys.stderr)
        for note in notes:
            print(f"  - {note}", file=sys.stderr)
        print("  Pass these in your MCP client 'env' block, or export them before launch.", file=sys.stderr)
        print(f"  Setup: {DOCS_URL}", file=sys.stderr)
    except Exception:
        pass


def main() -> None:
    _warn_unconfigured()
    mcp.run()


if __name__ == "__main__":
    main()
