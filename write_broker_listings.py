#!/usr/bin/env python3
"""Write all compiled broker listing research into the 'Broker listings' tab."""
import json
from pathlib import Path

import gspread

DATA = Path(__file__).parent / "data"
SHEET_ID = "1Q1NmPaq2YoyooWYS9CtNiC7ziACskT0IF-xktPYdMY8"

FIELDS = ["broker_site", "listing_title", "trade_category", "asking_price", "gross_revenue",
          "cash_flow_sde", "ebitda", "city_county", "state", "employees", "year_established",
          "real_estate_included", "reason_for_selling", "broker_name", "broker_firm",
          "broker_phone", "broker_email", "listing_url", "date_listed", "description_notes"]

all_listings = []
for i in range(1, 7):
    all_listings.extend(json.load(open(DATA / f"broker_output{i}.json")))

print(f"total listings: {len(all_listings)}")
from collections import Counter
print("by trade:", Counter(l.get("trade_category", "") for l in all_listings))
print("by site:", Counter(l.get("broker_site", "") for l in all_listings))

rows = [[l.get(f, "") for f in FIELDS] for l in all_listings]

gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("Broker listings")
ws.update(values=rows, range_name="A2", value_input_option="USER_ENTERED")
print(f"wrote {len(rows)} listings to 'Broker listings' tab")
