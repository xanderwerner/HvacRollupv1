import json
import requests
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = service_account.Credentials.from_service_account_file(
    "/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json", scopes=SCOPES
)
creds.refresh(google.auth.transport.requests.Request()) if False else None
import google.auth.transport.requests
creds.refresh(google.auth.transport.requests.Request())

headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

body = {
    "properties": {"title": "TX and NM"},
    "sheets": [{"properties": {"title": "Enriched Master"}}]
}
r = requests.post("https://sheets.googleapis.com/v4/spreadsheets", headers=headers, json=body)
print(r.status_code)
data = r.json()
print(json.dumps(data, indent=2)[:2000])

if r.status_code == 200:
    sheet_id = data["spreadsheetId"]
    with open("data/tx_nm_sheet_id.txt", "w") as f:
        f.write(sheet_id)
    print("SHEET_ID:", sheet_id)
    print("URL:", data.get("spreadsheetUrl"))
