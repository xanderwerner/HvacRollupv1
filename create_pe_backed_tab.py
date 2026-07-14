#!/usr/bin/env python3
"""Create a dedicated 'PE backed' tab in the Super Enrichment sheet, segregating the
10 confirmed PE-backed companies out for visibility. They stay flagged/at-the-bottom
in the main Super Enrichment tab too (not removed from the master) -- this tab is an
additional, clearer view specifically for PE-backed companies."""
import json
from pathlib import Path

import gspread

DATA = Path(__file__).parent / "data"
SHEET_ID = "1Q1NmPaq2YoyooWYS9CtNiC7ziACskT0IF-xktPYdMY8"

rows = json.load(open(DATA / "pe_backed_tab_rows.json"))

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key(SHEET_ID)

existing_titles = [w.title for w in sh.worksheets()]
if "PE backed" in existing_titles:
    ws = sh.worksheet("PE backed")
    ws.clear()
else:
    ws = sh.add_worksheet(title="PE backed", rows=len(rows) + 5, cols=12)

header = ["ID", "Company Name", "Trade", "City", "State", "PE Firm / Parent Brand",
          "Owner Name", "Owner Cell", "Office Phone", "Employees", "Website"]
ws.update(values=[header] + rows, range_name="A1", value_input_option="USER_ENTERED")
print(f"'PE backed' tab created/updated with {len(rows)} companies")
