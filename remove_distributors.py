#!/usr/bin/env python3
"""Remove distributor/wholesale companies miscategorized as contractors, including
fixing the C2810 bug (Vegas Electrical Supply Co, identified as a CED branch during
LinkedIn research but never actually removed -- EXCLUDE_IDS was defined but never
checked in az_audit_cleanup.py's removal logic)."""
from pathlib import Path

import gspread
import openpyxl

DATA = Path(__file__).parent / "data"
MASTER = DATA / "AZ_targets_enriched_master.xlsx"

REMOVE = {
    "C001": "Geary Pacific Supply -- HVAC wholesale distributor, not a contractor",
    "C833": "Hughes Supply Buckeye -- national plumbing/electrical supply distributor (Home Depot-owned), not a contractor",
    "C892": "Hvac Supplies -- supply company, not a contractor",
    "C2810": "Vegas Electrical Supply Co -- identified as a CED (Consolidated Electrical Distributors) branch during LinkedIn research; should have been removed with the other CED branches but the exclusion never actually ran",
}

wb = openpyxl.load_workbook(MASTER)
ws = wb["Enriched Master"]
all_rows = [row for row in ws.iter_rows(min_row=2) if row[1].value]
matched = [row for row in all_rows if row[0].value in REMOVE]
print(f"removing {len(matched)} rows:")
for row in matched:
    print(" ", row[0].value, row[1].value, "--", REMOVE[row[0].value])

rows_to_delete = sorted([row[0].row for row in matched], reverse=True)
for r in rows_to_delete:
    ws.delete_rows(r)
wb.save(MASTER)
print(f"local xlsx saved: {len(matched)} rows removed")

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
gsheet_ws = sh.worksheet("Enriched Master")
all_values = gsheet_ws.get_all_values()
grows_to_delete = sorted([i + 2 for i, r in enumerate(all_values[1:]) if r and r[0] in REMOVE], reverse=True)
for r in grows_to_delete:
    gsheet_ws.delete_rows(r)
print(f"live Google Sheet: removed {len(grows_to_delete)} rows")
