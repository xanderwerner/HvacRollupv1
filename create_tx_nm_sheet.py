import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.create("TX and NM")
sh.share("hvacrollup@hvacrollup.iam.gserviceaccount.com", perm_type="user", role="writer")

ws = sh.sheet1
ws.update_title("Enriched Master")

header = ["ID","Company Name","Trade","City","State","Owner Name","Owner Title","Owner Cell",
          "Cell DNC Status","Owner Email","Office Phone","Employees (Apollo)","Est. Revenue (Apollo)",
          "Est. EBITDA (12% proxy)","Founded","Data Check","Cell Source","Owner Found Via",
          "Owner Source (orig)","Co-Owners","Owner LinkedIn","Website","Domain","Other Locations",
          "License #","License Class","Google Rating","Reviews","Notes"]
ws.append_row(header)

print("Sheet created:", sh.url)
print("Sheet ID:", sh.id)
