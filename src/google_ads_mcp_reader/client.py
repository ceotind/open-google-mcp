import os

from google.ads.googleads import oauth2
from google.ads.googleads.client import GoogleAdsClient

_client: GoogleAdsClient | None = None


def get_client() -> GoogleAdsClient:
    global _client
    if _client is not None:
        return _client

    developer_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if not developer_token:
        raise ValueError("GOOGLE_ADS_DEVELOPER_TOKEN environment variable is required")

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
