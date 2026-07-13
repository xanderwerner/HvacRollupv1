import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")
rows = ws.get_all_values()
header = rows[0]
idx = {h: i for i, h in enumerate(header)}
row_by_id = {r[idx["ID"]]: i for i, r in enumerate(rows[1:], start=2)}

updates = json.load(open("data/electrical_cell_updates2.json"))
cells = []
for u in updates:
    r = row_by_id[u["row_id"]]
    cells.append(gspread.Cell(r, idx["Owner Cell"] + 1, u["mobile"]))
    cells.append(gspread.Cell(r, idx["Cell DNC Status"] + 1, "DNC" if u["dnc"] else "Not DNC"))
    cells.append(gspread.Cell(r, idx["Cell Source"] + 1, "ZoomInfo enrich (domain-verified, sniper mode) 2026-07-13"))
    if u.get("email"):
        cells.append(gspread.Cell(r, idx["Owner Email"] + 1, u["email"]))

# Flag Integrity Electrical Contracting LLC (C933) as also contaminated (shared owner_id with the other 3)
row_by_id_full = row_by_id
r933 = row_by_id_full.get("C933")
if r933:
    existing = rows[r933-1][idx["Data Check"]]
    note = "ZI 'Michael Cobb' contact match (owner_id 2067719350) also confirmed via domain search here -- but same ID is shared across 3 OTHER unrelated 'Integrity Electrical' companies with different license#/city, so this appears to be a bad/duplicated contact record in ZI's own database. Not redeemed pending manual verification."
    cells.append(gspread.Cell(r933, idx["Data Check"] + 1, (existing + "; " if existing else "") + note))

ws.update_cells(cells, value_input_option="RAW")
print(f"Wrote {len(updates)} new electrical cells + flagged Integrity Electrical Contracting LLC ({len(cells)} total updates)")
