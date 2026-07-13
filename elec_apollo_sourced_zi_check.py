#!/usr/bin/env python3
"""Free ZI domain-based check for the 26 apollo(via places)-sourced qualified
electrical companies -- see if ZI independently has an owner-titled contact +
mobile flag for them, using their now-known domain (more reliable than name search).
"""
import json
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

import certifi

BASE = Path(__file__).parent / "data"
CTX = ssl.create_default_context(cafile=certifi.where())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV = Path.home() / "dev/hvac-lead-sourcing/.env"
OWNER_TITLES = ("owner", "president", "ceo", "chief executive", "founder",
                "principal", "partner", "proprietor", "co-owner", "managing member",
                "managing partner", "electrician")

_creds = {}
for line in open(ENV):
    if line.startswith("ZOOMINFO_"):
        k, v = line.strip().split("=", 1)
        _creds[k] = v
_token = {"jwt": None}


def get_token():
    out = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://api.zoominfo.com/authenticate",
         "-H", "Content-Type: application/json", "-H", f"User-Agent: {UA}",
         "-d", json.dumps({"username": _creds["ZOOMINFO_USERNAME"], "password": _creds["ZOOMINFO_PASSWORD"]})],
        capture_output=True, text=True, timeout=30,
    )
    _token["jwt"] = json.loads(out.stdout)["jwt"]


def zi(path, payload):
    if not _token["jwt"]:
        get_token()
    req = urllib.request.Request("https://api.zoominfo.com" + path, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + _token["jwt"], "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return json.loads(r.read())
    except Exception:
        return {}


merged = [json.loads(l) for l in open(BASE / "elec_merged_sized_v2.jsonl")]
qualified = [m for m in merged if m.get("final_employees") is not None and 18 <= m["final_employees"] <= 50]
targets = [m for m in qualified if m["size_source"] == "apollo(via places, verified)"]

get_token()
results = []
for m in targets:
    dom = m["final_domain"]
    r = zi("/search/company", {"companyWebsite": dom, "rpp": 1})
    co = (r.get("data") or [None])[0]
    rec = {"roc_name": m["roc_name"], "domain": dom}
    if co:
        rec["zi_company_id"] = co["id"]
        ct = zi("/search/contact", {"companyId": str(co["id"]), "rpp": 25})
        owners = [c for c in (ct.get("data") or [])
                  if any(k in (c.get("jobTitle") or "").lower() for k in OWNER_TITLES)]
        if owners:
            best = max(owners, key=lambda c: c.get("contactAccuracyScore", 0))
            rec["zi_owner"] = f"{best.get('firstName','')} {best.get('lastName','')}".strip()
            rec["zi_owner_id"] = best.get("id")
            rec["zi_owner_title"] = best.get("jobTitle")
            rec["zi_has_mobile"] = best.get("hasMobilePhone")
            rec["zi_mobile_dnc"] = best.get("mobilePhoneDoNotCall")
    results.append(rec)
    time.sleep(0.3)

json.dump(results, open(BASE / "elec_apollo_sourced_zi_check.json", "w"), indent=1)
flagged = [r for r in results if r.get("zi_has_mobile")]
print(f"Checked {len(results)} | matched ZI company: {sum(1 for r in results if r.get('zi_company_id'))} | owner found: {sum(1 for r in results if r.get('zi_owner'))} | mobile flagged: {len(flagged)}")
for r in flagged:
    print(" ", r["roc_name"], "|", r.get("zi_owner"), "| DNC:", r.get("zi_mobile_dnc"))
