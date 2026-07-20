import os

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from platformdirs import user_config_dir

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

_config_dir = os.environ.get("GSC_CONFIG_DIR") or user_config_dir("mcp-gsc")
os.makedirs(_config_dir, exist_ok=True)
_token_file = os.path.join(_config_dir, "token.json")

_service: Resource | None = None


def _expand_path(path: str | None) -> str | None:
    if not path:
        return None
    return os.path.expandvars(os.path.expanduser(path))


def _oauth_client_config() -> dict | None:
    """Build an OAuth client config dict from existing env vars.

    Tries, in order:
      1. GOOGLE_ADS_CLIENT_ID + GOOGLE_ADS_CLIENT_SECRET (reuse Ads creds)
      2. GSC_OAUTH_CLIENT_SECRETS_FILE (dedicated GSC secrets file)

    Returns None if neither is available.
    """
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    secrets_file = _expand_path(os.environ.get("GSC_OAUTH_CLIENT_SECRETS_FILE"))
    if secrets_file:
        if not os.path.exists(secrets_file):
            raise FileNotFoundError(
                f"GSC_OAUTH_CLIENT_SECRETS_FILE is set to {secrets_file!r} but the file does not exist."
            )
        with open(secrets_file) as f:
            import json
            return json.load(f)

    return None


def get_service() -> Resource:
    global _service
    if _service is not None:
        return _service

    # Option A: Service account (headless / automated)
    # Checks GSC_CREDENTIALS_PATH first, then falls back to GOOGLE_ADS_JSON_KEY_FILE
    # so a single service account works for both APIs.
    creds_path = _expand_path(
        os.environ.get("GSC_CREDENTIALS_PATH")
        or os.environ.get("GOOGLE_ADS_JSON_KEY_FILE")
    )
    if creds_path:
        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                f"GSC_CREDENTIALS_PATH is set to {creds_path!r} but the file does not exist."
            )
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
        _service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        return _service

    # Option B: OAuth desktop flow
    client_config = _oauth_client_config()
    if client_config:
        creds = None
        if os.path.exists(_token_file):
            try:
                creds = Credentials.from_authorized_user_file(_token_file, SCOPES)
            except Exception:
                if os.path.exists(_token_file):
                    os.remove(_token_file)
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(_token_file, "w") as f:
                    f.write(creds.to_json())
            else:
                flow = Flow.from_client_config(client_config, scopes=SCOPES)
                flow.redirect_uri = "http://localhost:0"
                creds = flow.run_local_server(port=0)
                with open(_token_file, "w") as f:
                    f.write(creds.to_json())

        _service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        return _service

    # Option C: Application Default Credentials (ADC)
    # Works with `gcloud auth application-default login` — no env vars needed.
    try:
        creds, project = google.auth.default()
        if hasattr(creds, "with_scopes"):
            creds = creds.with_scopes(SCOPES)
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        # Validate scope by listing properties (cheapest API call).
        # A 403 with "insufficient authentication scopes" means ADC needs
        # the GSC scope added.
        svc.sites().list().execute()
        _service = svc
        return _service
    except HttpError as e:
        if e.resp.status == 403 and "insufficient authentication scopes" in str(e).lower():
            raise ValueError(
                "Your Application Default Credentials (ADC) are missing the GSC scope. "
                "Run this command to fix:\n\n"
                "  gcloud auth application-default login \\\n"
                "    --scopes=https://www.googleapis.com/auth/webmasters.readonly,\\\n"
                "    https://www.googleapis.com/auth/cloud-platform\n"
            )
        raise
    except Exception:
        pass

    raise ValueError(
        "No GSC authentication configured. You already have Application Default "
        "Credentials (ADC) set up via `gcloud auth application-default login`, "
        "which the server will use. Run the following command to add the GSC scope:\n\n"
        "  gcloud auth application-default login \\\n"
        "    --scopes=https://www.googleapis.com/auth/webmasters.readonly,\\\n"
        "    https://www.googleapis.com/auth/cloud-platform\n\n"
        "Alternatively, set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in "
        "your .env and the server can run the OAuth browser flow automatically."
    )
