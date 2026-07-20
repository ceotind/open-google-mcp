import os

from google.ads.googleads import oauth2
from google.ads.googleads.client import GoogleAdsClient
from google.oauth2 import service_account

_client: GoogleAdsClient | None = None


def _expand_path(path: str | None) -> str | None:
    if not path:
        return None
    return os.path.expandvars(os.path.expanduser(path))


def _load_service_account_creds() -> service_account.Credentials | None:
    """Try to load service account credentials from env vars or file.

    Priority: GOOGLE_ADS_JSON_KEY_FILE (file path), then individual env vars.
    """
    json_key_file = _expand_path(os.environ.get("GOOGLE_ADS_JSON_KEY_FILE"))
    if json_key_file:
        if not os.path.exists(json_key_file):
            raise FileNotFoundError(
                f"GOOGLE_ADS_JSON_KEY_FILE is set to {json_key_file!r} but does not exist."
            )
        return service_account.Credentials.from_service_account_file(
            json_key_file, scopes=["https://www.googleapis.com/auth/adwords"],
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
            info, scopes=["https://www.googleapis.com/auth/adwords"],
        )

    return None


def get_client() -> GoogleAdsClient:
    global _client
    if _client is not None:
        return _client

    developer_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if not developer_token:
        raise ValueError("GOOGLE_ADS_DEVELOPER_TOKEN environment variable is required")

    sa_creds = _load_service_account_creds()
    if sa_creds:
        creds = sa_creds
    else:
        refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")
        client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

        if refresh_token and client_id and client_secret:
            from google.oauth2.credentials import Credentials

            creds = Credentials(
                token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_uri="https://accounts.google.com/o/oauth2/token",
            )
        else:
            creds = oauth2.get_application_default_credentials()

    kwargs: dict = {
        "credentials": creds,
        "developer_token": developer_token,
    }

    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        kwargs["login_customer_id"] = login_customer_id

    _client = GoogleAdsClient(**kwargs)
    return _client
