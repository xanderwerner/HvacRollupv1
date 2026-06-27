"""Writes industry-expert (COO/GM/VP) records to the 'Expert List' tab.

Creates the tab + headers on first run if it doesn't exist.
Dedupes by Full Name + Company Name.
"""
import datetime

import gspread
from google.oauth2.service_account import Credentials

import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Expert #",
    "Full Name",
    "Title",
    "Company Name",
    "Company Employees",
    "Company Revenue",
    "City",
    "Years of Experience",
    "Email",
    "LinkedIn URL",
    "Apollo Person ID",
    "Apollo Org ID",
    "Date Added",
    "Outreach Status",
    "Notes",
]

TAB_NAME = "Expert List"


def _col_a1(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _worksheet():
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(config.GSHEET_ID)
    try:
        ws = sh.worksheet(TAB_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=TAB_NAME, rows=500, cols=len(HEADERS))
        ws.update("A1:O1", [HEADERS], value_input_option="RAW")
        ws.format("A1:O1", {"textFormat": {"bold": True}})
    return ws


def write_experts(experts: list[dict], limit: int | None = None) -> list[str]:
    """Append expert rows to the Expert List tab. Returns names written."""
    ws = _worksheet()
    vals = ws.get_all_values()

    if not vals or vals[0] != HEADERS:
        # Tab exists but headers may have shifted — trust row 0
        hrow = 0
    else:
        hrow = 0

    # build dedup key set from existing rows
    existing = set()
    max_no = 0
    for row in vals[1:]:
        name = row[1].strip().lower() if len(row) > 1 else ""
        company = row[2].strip().lower() if len(row) > 2 else ""
        if name or company:
            existing.add((name, company))
        try:
            max_no = max(max_no, int(str(row[0]).strip()))
        except (ValueError, IndexError):
            pass

    first_empty = len(vals) + 1  # append after last row

    date_str = datetime.date.today().strftime("%m/%d/%y")
    matrix, written, no = [], [], max_no

    for ex in experts:
        name = (ex.get("Full Name") or "").strip()
        company = (ex.get("Company Name") or "").strip()
        key = (name.lower(), company.lower())
        if not name:
            continue
        if key in existing:
            continue
        no += 1
        row = [
            no,
            name,
            ex.get("Title", ""),
            company,
            ex.get("Company Employees", ""),
            ex.get("Company Revenue", ""),
            ex.get("City", ""),
            ex.get("Years of Experience", ""),
            ex.get("Email", ""),
            ex.get("LinkedIn URL", ""),
            ex.get("Apollo Person ID", ""),
            ex.get("Apollo Org ID", ""),
            date_str,
            "New",
            ex.get("Notes", ""),
        ]
        matrix.append(row)
        existing.add(key)
        written.append(f"{name} ({company})")
        if limit and len(written) >= limit:
            break

    if matrix:
        r = first_empty
        rng = f"A{r}:{_col_a1(len(HEADERS))}{r + len(matrix) - 1}"
        ws.update(range_name=rng, values=matrix, value_input_option="RAW")

    return written
