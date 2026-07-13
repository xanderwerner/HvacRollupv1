import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")
rows = ws.get_all_values()
header = rows[0]
idx = {h: i for i, h in enumerate(header)}

row_by_id = {r[idx["ID"]]: i for i, r in enumerate(rows[1:], start=2)}

updates = json.load(open("data/electrical_cell_updates.json"))
integrity_flag_ids = json.load(open("data/integrity_flag_ids.json"))

cells = []
for u in updates:
    r = row_by_id[u["row_id"]]
    cells.append(gspread.Cell(r, idx["Owner Cell"] + 1, u["mobile"]))
    cells.append(gspread.Cell(r, idx["Cell DNC Status"] + 1, "DNC" if u["dnc"] else "Not DNC"))
    cells.append(gspread.Cell(r, idx["Cell Source"] + 1, "ZoomInfo enrich (verified, sniper mode) 2026-07-13"))
    if u.get("email"):
        cells.append(gspread.Cell(r, idx["Owner Email"] + 1, u["email"]))

for rid in integrity_flag_ids:
    r = row_by_id[rid]
    existing = rows[r-1][idx["Data Check"]]
    note = "ZI owner match (Michael Cobb) shared identically across 3 different 'Integrity Electrical' ROC companies with different license#/city/QP names -- confirmed generic-name contamination, do NOT trust this owner name, needs real research"
    cells.append(gspread.Cell(r, idx["Owner Name"] + 1, ""))
    cells.append(gspread.Cell(r, idx["Owner Title"] + 1, ""))
    cells.append(gspread.Cell(r, idx["Data Check"] + 1, (existing + "; " if existing else "") + note))

ws.update_cells(cells, value_input_option="RAW")
print(f"Wrote {len(updates)} cells + flagged {len(integrity_flag_ids)} contaminated rows ({len(cells)} total cell updates)")
