import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0")
ws = sh.worksheet("Enriched Master")

rows = json.load(open("data/electrical_rows_to_add.json"))
ws.append_rows(rows, value_input_option="RAW")
print(f"Appended {len(rows)} electrical companies to Enriched Master")
