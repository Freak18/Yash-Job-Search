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


COMPANIES_WORKSHEET_NAME = "Companies"
COMPANIES_HEADERS = ["Company Name", "LinkedIn ID", "Type"]


def _seed_companies_worksheet(worksheet) -> None:
    from paths import load_seed_companies

    rows = [COMPANIES_HEADERS] + [
        [c["name"], c["id"], c["type"]] for c in load_seed_companies()
    ]
    worksheet.clear()
    worksheet.update(range_name="A1", values=rows, value_input_option="RAW")


def get_companies_worksheet(spreadsheet):
    """Open the Companies tab; create/seed it from company_ids.json if missing or without data rows."""
    try:
        worksheet = spreadsheet.worksheet(COMPANIES_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=COMPANIES_WORKSHEET_NAME, rows=1000, cols=len(COMPANIES_HEADERS)
        )
        _seed_companies_worksheet(worksheet)
        return worksheet

    has_data = any(row and row[0].strip() for row in worksheet.get_all_values()[1:])
    if not has_data:
        _seed_companies_worksheet(worksheet)
    return worksheet


def read_companies(spreadsheet) -> list:
    worksheet = get_companies_worksheet(spreadsheet)
    companies = []
    for row in worksheet.get_all_values()[1:]:
        row = row + [""] * (len(COMPANIES_HEADERS) - len(row))
        if row[0].strip():
            companies.append(
                {"name": row[0].strip(), "id": row[1].strip(), "type": row[2].strip()}
            )
    return companies


def write_companies(spreadsheet, companies: list) -> None:
    worksheet = get_companies_worksheet(spreadsheet)
    rows = [COMPANIES_HEADERS] + [[c["name"], c["id"], c["type"]] for c in companies]
    worksheet.clear()
    worksheet.update(range_name="A1", values=rows, value_input_option="RAW")
