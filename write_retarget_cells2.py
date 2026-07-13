import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")
rows = ws.get_all_values()
header = rows[0]
idx = {h: i for i, h in enumerate(header)}
row_by_id = {r[idx["ID"]]: i for i, r in enumerate(rows[1:], start=2)}

mobiles = json.load(open("data/zi_retarget_mobiles_found2.json"))
cells = []
skipped = []
for m in mobiles:
    rid = m["row_id"]
    if rid not in row_by_id:
        continue
    res = m["result"]
    mobile = res["mobilePhone"]
    if not mobile.startswith("(") and not mobile.startswith("+1"):
        skipped.append((rid, mobile))
        continue  # non-US number -- wrong-person match, don't write
    r = row_by_id[rid]
    cells.append(gspread.Cell(r, idx["Owner Cell"] + 1, mobile))
    cells.append(gspread.Cell(r, idx["Cell DNC Status"] + 1, "DNC" if res.get("mobilePhoneDoNotCall") else "Not DNC"))
    cells.append(gspread.Cell(r, idx["Cell Source"] + 1, "ZoomInfo enrich (targeted retry-by-name, sniper mode) 2026-07-13"))
    if res.get("email") and not (rows[r-1][idx["Owner Email"]] or "").strip():
        cells.append(gspread.Cell(r, idx["Owner Email"] + 1, res["email"]))

ws.update_cells(cells, value_input_option="RAW")
print(f"Wrote cells for {len(mobiles)-len(skipped)} mobiles, skipped {len(skipped)} non-US (likely wrong-person): {skipped}")
