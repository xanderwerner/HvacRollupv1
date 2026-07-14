#!/usr/bin/env python3
"""Fetch phone/website details for the 91 Places-sourced net-new electrical candidates
and append them to both master artifacts (no owner/employee enrichment yet -- that's
the next step, this is just adding them to the list)."""
import json
import re
import sys
import time
from pathlib import Path

import gspread
import openpyxl

sys.path.insert(0, str(Path.home() / "dev/hvac-lead-sourcing"))
import places  # noqa: E402

DATA = Path(__file__).parent / "data"
MASTER = DATA / "AZ_targets_enriched_master.xlsx"

cands = json.load(open(DATA / "elec_places_supplement_candidates.json"))

wb = openpyxl.load_workbook(MASTER)
ws = wb["Enriched Master"]
last_id = max(int(r[0][1:]) for r in ws.iter_rows(values_only=True) if r[0] and r[0].startswith("C"))
print(f"last id: C{last_id}")

rows_out = []
for i, c in enumerate(cands, start=last_id + 1):
    rid = f"C{i}"
    try:
        d = places.place_details(c["place_id"])
    except Exception as e:
        d = {}
        print(f"  ! details failed for {c['name']}: {e}")
    phone = d.get("formatted_phone_number", "")
    website = d.get("website", "")
    addr = d.get("formatted_address") or c.get("address", "")
    city = c["city"]

    row = [
        rid, c["name"], "Electrical", city, "AZ",
        "", "", "", "", "",  # Owner Name, Title, Cell, DNC, Email
        phone, "", "", "", "",  # Office Phone, Employees, Revenue, EBITDA, Founded
        "Not sized yet -- Google Places sourced, no ROC license cross-check or employee count yet",
        "", "", "", "",  # Cell Source, Owner Found Via, Owner Source(orig), Co-Owners
        "", website, "", "",  # LinkedIn, Website, Domain, Other Locations
        "", "", c.get("rating", ""), c.get("reviews", ""),  # License#, Class, Rating, Reviews
        "Added 2026-07-13: Google Places supplement sweep (net-new vs ROC-sourced electrical list, brand-token unmatched)",
    ]
    rows_out.append(row)
    time.sleep(0.1)

for row in rows_out:
    ws.append(row)
wb.save(MASTER)
print(f"local xlsx updated with {len(rows_out)} Places-sourced electrical rows")

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
gsheet_ws = sh.worksheet("Enriched Master")
gsheet_ws.append_rows(rows_out, value_input_option="RAW")
print("live Google Sheet 'Enriched Master' updated to match")

with open(DATA / "electrical_places_rows_added.json", "w") as f:
    json.dump(rows_out, f, indent=1)
