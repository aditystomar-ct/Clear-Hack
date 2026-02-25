"""Google API authentication."""

import sys
from .config import CREDS_PATH

_google_creds = None


def get_google_creds():
    """Load Google service-account credentials from credentials.json."""
    global _google_creds
    if _google_creds is not None:
        return _google_creds

    from google.oauth2 import service_account

    if not CREDS_PATH.exists():
        print(f"Error: {CREDS_PATH} not found.")
        print("Place your Google service-account key as credentials.json")
        sys.exit(1)

    _google_creds = service_account.Credentials.from_service_account_file(
        str(CREDS_PATH),
        scopes=[
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return _google_creds
