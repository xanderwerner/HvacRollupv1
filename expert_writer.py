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
    "Direct Mobile",
    "Company Phone",
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
    """Append expert rows to the Expert List tab. Returns names written.

    Reads the live sheet headers so it stays correct even if columns were
    added or reordered outside this script (e.g. by enrich_expert_phones.py).
    """
    ws = _worksheet()
    vals = ws.get_all_values()

    # live headers from the sheet (row 0); fall back to canonical HEADERS
    live_headers = vals[0] if vals else HEADERS

    # ensure any HEADERS we know about are present (add missing ones)
    for h in HEADERS:
        if h not in live_headers:
            new_idx = len(live_headers)
            live_headers.append(h)
            if ws.col_count < new_idx + 1:
                ws.add_cols(new_idx + 1 - ws.col_count)
            ws.update_cell(1, new_idx + 1, h)

    H = {h: i for i, h in enumerate(live_headers) if h}
    name_col = H.get("Full Name", 1)
    co_col = H.get("Company Name", 3)
    no_col = H.get("Expert #", 0)

    existing = set()
    max_no = 0
    for row in vals[1:]:
        name = row[name_col].strip().lower() if name_col < len(row) else ""
        co = row[co_col].strip().lower() if co_col < len(row) else ""
        if name:
            existing.add((name, co))
        try:
            max_no = max(max_no, int(str(row[no_col]).strip()))
        except (ValueError, IndexError):
            pass

    first_empty = len(vals) + 1
    date_str = datetime.date.today().strftime("%m/%d/%y")
    matrix, written, no = [], [], max_no

    for ex in experts:
        name = (ex.get("Full Name") or "").strip()
        company = (ex.get("Company Name") or "").strip()
        key = (name.lower(), company.lower())
        if not name or key in existing:
            continue
        no += 1
        ex_full = {
            "Expert #": no,
            "Full Name": name,
            "Title": ex.get("Title", ""),
            "Company Name": company,
            "Company Employees": ex.get("Company Employees", ""),
            "Company Revenue": ex.get("Company Revenue", ""),
            "City": ex.get("City", ""),
            "Years of Experience": ex.get("Years of Experience", ""),
            "Email": ex.get("Email", ""),
            "LinkedIn URL": ex.get("LinkedIn URL", ""),
            "Apollo Person ID": ex.get("Apollo Person ID", ""),
            "Apollo Org ID": ex.get("Apollo Org ID", ""),
            "Date Added": date_str,
            "Outreach Status": "New",
            "Notes": ex.get("Notes", ""),
            "Direct Mobile": ex.get("Direct Mobile", ""),
            "Company Phone": ex.get("Company Phone", ""),
        }
        row = ["" if ex_full.get(h) is None else ex_full.get(h, "")
               for h in live_headers]
        matrix.append(row)
        existing.add(key)
        written.append(f"{name} ({company})")
        if limit and len(written) >= limit:
            break

    if matrix:
        r = first_empty
        rng = f"A{r}:{_col_a1(len(live_headers))}{r + len(matrix) - 1}"
        ws.update(range_name=rng, values=matrix, value_input_option="RAW")

    return written
