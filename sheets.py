import json

import gspread

from config import GOOGLE_CREDENTIALS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client():
    if not GOOGLE_CREDENTIALS:
        raise ValueError("GOOGLE_CREDENTIALS environment variable is not set")

    credentials_info = json.loads(GOOGLE_CREDENTIALS)
    return gspread.service_account_from_dict(credentials_info, scopes=SCOPES)
