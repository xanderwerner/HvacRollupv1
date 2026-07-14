#!/usr/bin/env python3
"""Write cleaned + enriched + dedup-flagged broker listing research into the 'Broker listings' tab."""
import json
from pathlib import Path

import gspread

DATA = Path(__file__).parent / "data"
SHEET_ID = "1Q1NmPaq2YoyooWYS9CtNiC7ziACskT0IF-xktPYdMY8"

FIELDS = ["broker_site", "listing_title", "trade_category", "asking_price", "gross_revenue",
          "cash_flow_sde", "ebitda", "city_county", "state", "employees", "year_established",
          "real_estate_included", "reason_for_selling", "broker_name", "broker_firm",
          "broker_phone", "broker_email", "listing_url", "date_listed", "description_notes"]
HEADER = ["Broker Site", "Listing Title", "Trade Category", "Asking Price", "Gross Revenue",
          "Cash Flow / SDE", "EBITDA", "City/County", "State", "Employees", "Year Established",
          "Real Estate Included", "Reason for Selling", "Broker Name", "Broker Firm",
          "Broker Phone", "Broker Email", "Listing URL", "Date Listed/Updated",
          "Description/Notes", "Cross-Posted Sites"]

dup_flags = json.load(open(DATA / "dup_flags.json"))

all_listings = []
for i in range(1, 7):
    for j, l in enumerate(json.load(open(DATA / f"broker_output{i}.json"))):
        l["_dup_flag"] = dup_flags.get(f"{i}_{j}", "")
        all_listings.append(l)

print(f"total listings: {len(all_listings)}")
from collections import Counter
print("by trade:", Counter(l.get("trade_category", "") for l in all_listings))
print("by site:", Counter(l.get("broker_site", "") for l in all_listings))
print("with phone:", sum(1 for l in all_listings if l.get("broker_phone")))
flagged = sum(1 for l in all_listings if l["_dup_flag"])
print(f"cross-posted (flagged, not removed): {flagged} of {len(all_listings)}")

rows = [[l.get(f, "") for f in FIELDS] + [l["_dup_flag"]] for l in all_listings]

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Broker listings")

last_col = gspread.utils.rowcol_to_a1(1, len(HEADER)).rstrip("1")
ws.batch_clear([f"A1:{last_col}1000"])
ws.update(values=[HEADER], range_name="A1", value_input_option="USER_ENTERED")
ws.update(values=rows, range_name="A2", value_input_option="USER_ENTERED")
print(f"wrote {len(rows)} listings to 'Broker listings' tab (header + {len(HEADER)} cols)")
