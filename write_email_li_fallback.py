import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")
rows = ws.get_all_values()
header = rows[0]
idx = {h: i for i, h in enumerate(header)}
row_by_id = {r[idx["ID"]]: i for i, r in enumerate(rows[1:], start=2)}

recs = [json.loads(l) for l in open("data/apollo_reveal_all_missing.jsonl")]
cells = []
email_n = li_n = 0
for r in recs:
    rid = r["row_id"]
    if rid not in row_by_id:
        continue
    ri = row_by_id[rid]
    email = r.get("email")
    li = r.get("linkedin")
    if email and "not_unlocked" not in str(email) and not (rows[ri-1][idx["Owner Email"]] or "").strip():
        cells.append(gspread.Cell(ri, idx["Owner Email"]+1, email))
        email_n += 1
    if li and not (rows[ri-1][idx["Owner LinkedIn"]] or "").strip():
        cells.append(gspread.Cell(ri, idx["Owner LinkedIn"]+1, li))
        li_n += 1

ws.update_cells(cells, value_input_option="RAW")
print(f"Wrote {email_n} emails + {li_n} LinkedIn URLs ({len(cells)} total cell updates)")
