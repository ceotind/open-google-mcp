import os
from functools import lru_cache

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _expand_path(path: str | None) -> str | None:
    if not path:
        return None
    return os.path.expandvars(os.path.expanduser(path))


def _load_service_account_creds() -> service_account.Credentials | None:
    """Try to load service account credentials from env vars or file.

    Uses the same GOOGLE_SERVICE_ACCOUNT_* env vars as the other clients,
    plus a dedicated GA4_CREDENTIALS_PATH or the shared GSC_CREDENTIALS_PATH.
    """
    creds_path = _expand_path(
        os.environ.get("GA4_CREDENTIALS_PATH")
        or os.environ.get("GSC_CREDENTIALS_PATH")
        or os.environ.get("GOOGLE_ADS_JSON_KEY_FILE")
    )
    if creds_path:
        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                f"Credential file set to {creds_path!r} but does not exist."
            )
        return service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES,
        )

    email = os.environ.get("GOOGLE_SERVICE_ACCOUNT_EMAIL")
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if email and key:
        info = {
            "type": "service_account",
            "client_email": email,
            "private_key": key.replace("\\n", "\n"),
            "private_key_id": os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_ID", ""),
            "client_id": os.environ.get("GOOGLE_SERVICE_ACCOUNT_CLIENT_ID", ""),
            "project_id": os.environ.get("GOOGLE_SERVICE_ACCOUNT_PROJECT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES,
        )

    return None


@lru_cache(maxsize=1)
def get_client() -> BetaAnalyticsDataClient:
    """Get a cached GA4 BetaAnalyticsDataClient.

    Tries in order: service account (env vars) -> ADC (gcloud).
    """
    creds = _load_service_account_creds()
    if creds:
        return BetaAnalyticsDataClient(credentials=creds)

    # Try Application Default Credentials
    try:
        import google.auth

        adc_creds, _ = google.auth.default(scopes=SCOPES)
        if adc_creds:
            return BetaAnalyticsDataClient(credentials=adc_creds)
    except Exception:
        pass

    raise ValueError(
        "No GA4 authentication configured.\n\n"
        "Use the same service account as Google Ads / Search Console:\n"
        "  - Set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_KEY in .env\n"
        "  - Ensure the service account has the 'analytics.readonly' scope\n"
        "  - Add the service account email to your GA4 property\n"
        "    (Admin → Account Access Management → Add user → View-only)\n\n"
        "Or use ADC:\n"
        "  gcloud auth application-default login \\\n"
        "    --scopes=https://www.googleapis.com/auth/analytics.readonly"
    )