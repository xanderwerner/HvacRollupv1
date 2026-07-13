"""Write the deduped, solar-excluded TX company list to the 'texas master' tab."""
import csv
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1SdQE5OLeJufn253Tvb9ic2MZh3k4UpKANOZiLAawJX8")
ws = sh.worksheet("texas master")

rows = list(csv.DictReader(open("data/tx_companies_raw.csv")))
print(f"loaded {len(rows)} rows from data/tx_companies_raw.csv")

header = ['ID', 'Company Name', 'Trade', 'City', 'State', 'Owner Name', 'Owner Title', 'Owner Cell',
          'Cell DNC Status', 'Owner Email', 'Office Phone', 'Employees (Apollo)', 'Est. Revenue (Apollo)',
          'Est. EBITDA (12% proxy)', 'Founded', 'Data Check', 'Cell Source', 'Owner Found Via',
          'Owner Source (orig)', 'Co-Owners', 'Owner LinkedIn', 'Website', 'Domain', 'Other Locations',
          'License #', 'License Class', 'Google Rating', 'Reviews', 'Notes']

sheet_rows = []
for i, r in enumerate(rows, start=1):
    tx_id = f"TX{i:05d}"
    notes_parts = [f"Sourced 2026-07-13 via {r['license_source']} (TX gov licensing data)"]
    if r["address"]:
        notes_parts.append(f"Address: {r['address']}")
    if r["license_count"] and r["license_count"] != "1":
        notes_parts.append(f"License count: {r['license_count']}")
    if r["aka"]:
        notes_parts.append(f"AKA: {r['aka']}")
    notes = "; ".join(notes_parts)

    sheet_rows.append([
        tx_id, r["company_name"], r["trade"], r["city"], r["state"],
        "", "", "", "", "",  # Owner Name..Owner Email
        r["phone"],  # Office Phone
        "", "", "", "",  # Employees, Revenue, EBITDA, Founded
        "",  # Data Check
        "", "", "", "",  # Cell Source, Owner Found Via, Owner Source, Co-Owners
        "",  # Owner LinkedIn
        "", "",  # Website, Domain
        r["county"],  # Other Locations (repurposed to hold county coverage for now)
        r["license_number"], r["license_source"],
        "", "",  # Google Rating, Reviews
        notes,
    ])

print(f"writing {len(sheet_rows)} rows in chunks...")
CHUNK = 5000
for start in range(0, len(sheet_rows), CHUNK):
    chunk = sheet_rows[start:start + CHUNK]
    ws.append_rows(chunk, value_input_option="RAW")
    print(f"  wrote rows {start+1}-{start+len(chunk)}")

print("done")
