"""Writes qualified leads straight into the live Google Sheet's Organic List.

Mirrors excel_writer (reuses its dropdown-safe row mapping) but targets the
shared Google Sheet via gspread + a service-account key. Opens by spreadsheet
ID (Sheets API only — no Drive API needed).
"""
import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

import config
from models import Lead
from excel_writer import _row_values  # same dropdown-safe field mapping

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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
    return gc.open_by_key(config.GSHEET_ID).worksheet(config.GSHEET_TAB)


def write_leads(leads: list[Lead], limit: Optional[int] = None) -> list[str]:
    """Append survivor leads to the Google Sheet Organic List. Returns names."""
    ws = _worksheet()
    vals = ws.get_all_values()

    # header row = the one containing 'Company Name'
    hrow = next(i for i, row in enumerate(vals) if "Company Name" in row)
    headers = vals[hrow]
    ccol = headers.index("Company Name")
    pcol = headers.index("Prospect #") if "Prospect #" in headers else None

    # existing names, max prospect #, first empty row (1-based)
    existing, max_no, first_empty = set(), 0, None
    for i in range(hrow + 1, len(vals)):
        cell = vals[i][ccol] if ccol < len(vals[i]) else ""
        if cell.strip() == "":
            first_empty = i + 1
            break
        existing.add(cell.strip().lower())
        if pcol is not None and pcol < len(vals[i]):
            try:
                max_no = max(max_no, int(str(vals[i][pcol]).strip()))
            except ValueError:
                pass
    first_empty = first_empty or len(vals) + 1

    date_str = datetime.date.today().strftime("%m/%d/%y")
    matrix, written, no = [], [], max_no
    for lead in leads:
        if not lead.survived_filter:
            continue
        if lead.company_name.strip().lower() in existing:
            continue
        no += 1
        rv = _row_values(lead, no, date_str)
        matrix.append(["" if rv.get(h) is None else rv.get(h, "") for h in headers])
        existing.add(lead.company_name.strip().lower())
        written.append(lead.company_name)
        if limit and len(written) >= limit:
            break

    if matrix:
        end = first_empty + len(matrix) - 1
        rng = f"A{first_empty}:{_col_a1(len(headers))}{end}"
        ws.update(range_name=rng, values=matrix, value_input_option="USER_ENTERED")
    return written
