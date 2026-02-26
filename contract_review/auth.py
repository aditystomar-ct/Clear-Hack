"""Google API authentication."""

import json
import os
import sys
from .config import CREDS_PATH

_google_creds = None

_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def get_google_creds():
    """Load Google service-account credentials.

    Tries (in order):
    1. GOOGLE_CREDENTIALS_JSON env var (for Render / cloud deploys)
    2. credentials.json file on disk (for local dev)
    """
    global _google_creds
    if _google_creds is not None:
        return _google_creds

    from google.oauth2 import service_account

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if creds_json:
        info = json.loads(creds_json)
        _google_creds = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES,
        )
        return _google_creds

    if not CREDS_PATH.exists():
        print(f"Error: {CREDS_PATH} not found and GOOGLE_CREDENTIALS_JSON not set.")
        print("Place your Google service-account key as credentials.json")
        sys.exit(1)

    _google_creds = service_account.Credentials.from_service_account_file(
        str(CREDS_PATH), scopes=_SCOPES,
    )
    return _google_creds
