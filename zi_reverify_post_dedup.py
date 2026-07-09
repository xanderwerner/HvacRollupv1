#!/usr/bin/env python3
"""Free re-verification pass after dedup: re-check the 30 merged canonical companies
(new name/city) and re-check all still-nameless companies fresh. Zero credits --
/search endpoints only. Appends to zi_reverify.jsonl.
"""
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import certifi
import openpyxl

BASE = Path(__file__).parent / "data"
MASTER = BASE / "AZ_targets_enriched_master.xlsx"
LOG = BASE / "zi_reverify.jsonl"
CTX = ssl.create_default_context(cafile=certifi.where())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV = Path.home() / "dev/hvac-lead-sourcing/.env"
OWNER_TITLES = ("owner", "president", "ceo", "chief executive", "founder",
                "principal", "partner", "proprietor", "co-owner", "managing member",
                "managing partner", "chief exec")

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
    for attempt in range(4):
        req = urllib.request.Request("https://api.zoominfo.com" + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + _token["jwt"], "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                get_token(); continue
            if e.code == 429:
                time.sleep(10 * (attempt + 1)); continue
            return {"_err": e.code}
        except Exception:
            time.sleep(4 * (attempt + 1))
    return {"_err": "retry"}


def clean_domain(d):
    d = str(d or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def find_company(domain, name):
    dom = clean_domain(domain)
    if dom:
        r = zi("/search/company", {"companyWebsite": dom, "rpp": 1})
        if r.get("data"):
            return r["data"][0], "domain"
    r = zi("/search/company", {"companyName": str(name), "state": "Arizona", "rpp": 3})
    for c in (r.get("data") or []):
        if c.get("state") == "Arizona":
            return c, "name+AZ"
    return None, "none"


def check_row(rid, name, domain):
    rec = {"row_id": rid, "company": name, "ts": time.strftime("%H:%M:%S")}
    co, how = find_company(domain, name)
    if not co:
        rec["match"] = "not_in_zi"
        return rec
    if how == "name+AZ" and co.get("state") != "Arizona":
        rec["match"] = "not_az"
        return rec
    rec.update({"match": how, "zi_company_id": co["id"], "zi_name": co.get("name"),
                "zi_city": co.get("city"), "zi_state": co.get("state"),
                "zi_employees": co.get("employeeCount"), "zi_revenue_k": co.get("revenue")})
    ct = zi("/search/contact", {"companyId": str(co["id"]), "rpp": 25})
    owners = [c for c in (ct.get("data") or []) if any(k in (c.get("jobTitle") or "").lower() for k in OWNER_TITLES)]
    if owners:
        best = max(owners, key=lambda c: c.get("contactAccuracyScore", 0))
        rec["zi_owner"] = f"{best.get('firstName','')} {best.get('lastName','')}".strip()
        rec["zi_owner_title"] = best.get("jobTitle")
        rec["zi_has_mobile"] = best.get("hasMobilePhone")
        rec["zi_owner_score"] = best.get("contactAccuracyScore")
    return rec


def main():
    get_token()
    wb = openpyxl.load_workbook(MASTER)
    rows = [r for r in wb["Enriched Master"].iter_rows(values_only=True) if r[1]][1:]

    merged_canonical_ids = ['C899','C218','C713','C041','C051','C091','C232','C234','C316','C318',
                            'C409','C350','C359','C434','C462','C520','C596','C586','C601','C665',
                            'C673','C641','C250','C285','C267','C275','C025','C192','C236','C015']
    nameless = [r for r in rows if not r[5]]

    print(f"re-checking {len(merged_canonical_ids)} merged canonicals + {len(nameless)} still-nameless companies (free)", flush=True)
    by_id = {r[0]: r for r in rows}
    with open(LOG, "a") as log:
        for i, rid in enumerate(merged_canonical_ids):
            r = by_id.get(rid)
            if not r:
                continue
            rec = check_row(r[0], r[1], r[22])
            rec["group"] = "merged_canonical"
            rec["master_emp"], rec["master_rev"] = r[11], r[12]
            log.write(json.dumps(rec) + "\n"); log.flush()
            drift = ""
            if rec.get("zi_employees") and r[11] and abs(rec["zi_employees"] - r[11]) > 5:
                drift = f"  <-- DRIFT emp {r[11]}->{rec['zi_employees']}"
            print(f"[merged {i+1}/{len(merged_canonical_ids)}] {r[1][:35]:35} match={rec['match']}{drift}", flush=True)
            time.sleep(0.3)

        for i, r in enumerate(nameless):
            rec = check_row(r[0], r[1], r[22])
            rec["group"] = "nameless_recheck"
            log.write(json.dumps(rec) + "\n"); log.flush()
            if (i + 1) % 25 == 0:
                print(f"[nameless {i+1}/{len(nameless)}]", flush=True)
            time.sleep(0.3)
    print("FINISHED_REVERIFY", flush=True)


if __name__ == "__main__":
    main()
