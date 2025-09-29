import logging
import os
import gspread
import gspread.utils
from google.oauth2.service_account import Credentials

from libs.database_loader import *

# Setup logger
logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Default credentials file (can be overridden by env var)
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")


def get_client() -> gspread.Client:
    """
    Create and return a gspread client using service account credentials.

    Returns:
        gspread.Client: Authorized Google Sheets client.
    """
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)
