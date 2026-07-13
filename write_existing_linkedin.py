import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")
rows = ws.get_all_values()
header = rows[0]
idx = {h: i for i, h in enumerate(header)}
row_by_id = {r[idx["ID"]]: i for i, r in enumerate(rows[1:], start=2)}

recs = [json.loads(l) for l in open("data/apollo_reveal_emails.jsonl")]
cells = []
written = 0
for r in recs:
    if not r.get("linkedin"):
        continue
    rid = r["row_id"]
    if rid not in row_by_id:
        continue
    ri = row_by_id[rid]
    if (rows[ri-1][idx["Owner LinkedIn"]] or "").strip():
        continue  # already has one
    cells.append(gspread.Cell(ri, idx["Owner LinkedIn"]+1, r["linkedin"]))
    written += 1

ws.update_cells(cells, value_input_option="RAW")
print(f"Wrote {written} LinkedIn URLs from existing (already-fetched, no new cost) data")
