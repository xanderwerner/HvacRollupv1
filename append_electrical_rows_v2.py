#!/usr/bin/env python3
"""Append the widened electrical rows to BOTH the local master xlsx (source of truth for
build_super_sheet.py and most enrichment scripts) and the live 'Enriched Master' Google
Sheet mirror, so the two artifacts don't drift out of sync the way Super Enrichment did.
"""
import json
from pathlib import Path

import gspread
import openpyxl

DATA = Path(__file__).parent / "data"
MASTER = DATA / "AZ_targets_enriched_master.xlsx"

rows = json.load(open(DATA / "electrical_rows_to_add_v2.json"))
print(f"appending {len(rows)} rows")

wb = openpyxl.load_workbook(MASTER)
ws = wb["Enriched Master"]
for row in rows:
    ws.append(row)
wb.save(MASTER)
print(f"local xlsx updated, saved to {MASTER}")

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
gsheet_ws = sh.worksheet("Enriched Master")
gsheet_ws.append_rows(rows, value_input_option="RAW")
print("live Google Sheet 'Enriched Master' updated to match")
