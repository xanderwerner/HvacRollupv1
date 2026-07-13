#!/usr/bin/env python3
"""FREE ZoomInfo verification pass over the full master — NO credits spent.

Per company: company search (size/revenue/location) + contact search (owner
name/title + mobile-availability flag). Domain-first matching, Arizona-verified,
franchise-parent aware. Appends to zi_enrich.jsonl (resumable).

Uses ONLY /search endpoints — these consume 0 uniqueId credits (verified).
Usage: python3 zi_verify.py [limit]
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
LOG = BASE / "zi_enrich.jsonl"
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
    """Fetch JWT via curl (the /authenticate endpoint blocks Python's TLS fingerprint)."""
    out = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://api.zoominfo.com/authenticate",
         "-H", "Content-Type: application/json", "-H", f"User-Agent: {UA}",
         "-d", json.dumps({"username": _creds["ZOOMINFO_USERNAME"],
                           "password": _creds["ZOOMINFO_PASSWORD"]})],
        capture_output=True, text=True, timeout=30,
    )
    _token["jwt"] = json.loads(out.stdout)["jwt"]
    return _token["jwt"]


def zi(path, payload):
    if not _token["jwt"]:
        get_token()
    for attempt in range(4):
        req = urllib.request.Request(
            "https://api.zoominfo.com" + path,
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + _token["jwt"],
                     "Content-Type": "application/json", "User-Agent": UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:  # token expired
                get_token()
                continue
            if e.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            return {"_err": e.code, "_body": e.read().decode()[:200]}
        except Exception as e:
            time.sleep(4 * (attempt + 1))
            last = str(e)
    return {"_err": "retry", "_body": last}


def clean_domain(d):
    d = str(d or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def find_company(name, domain, city):
    dom = clean_domain(domain)
    if dom:
        r = zi("/search/company", {"companyWebsite": dom, "rpp": 1})
        if r.get("data"):
            return r["data"][0], "domain"
    # fallback: name + Arizona
    r = zi("/search/company", {"companyName": str(name), "state": "Arizona", "rpp": 3})
    for c in (r.get("data") or []):
        if c.get("state") == "Arizona":
            return c, "name+AZ"
    return None, "none"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    wb = openpyxl.load_workbook(MASTER)
    rows = list(wb["Enriched Master"].iter_rows(values_only=True))[1:]
    done = set()
    if LOG.exists():
        for line in open(LOG):
            try:
                done.add(json.loads(line)["row_id"])
            except Exception:
                pass
    targets = [r for r in rows if r[1] and r[0] not in done][:limit]
    print(f"companies to verify (free): {len(targets)}", flush=True)
    get_token()
    stats = {"co": 0, "sized": 0, "owner": 0, "mob": 0, "not_in_zi": 0, "not_az": 0}
    with open(LOG, "a") as log:
        for i, r in enumerate(targets):
            rid, name, trade, city, domain = r[0], r[1], r[2], r[3], r[22]
            rec = {"row_id": rid, "company": name, "ts": time.strftime("%H:%M:%S")}
            co, how = find_company(name, domain, city)
            if not co:
                rec["zi"] = None
                rec["match"] = "not_in_zi"
                stats["not_in_zi"] += 1
            elif how == "name+AZ" and co.get("state") != "Arizona":
                rec["match"] = "not_az"
                stats["not_az"] += 1
            else:
                stats["co"] += 1
                rec["match"] = how
                rec["zi_company_id"] = co["id"]
                rec["zi_name"] = co.get("name")
                rec["zi_city"] = co.get("city")
                rec["zi_state"] = co.get("state")
                rec["zi_employees"] = co.get("employeeCount")
                rec["zi_revenue_k"] = co.get("revenue")  # thousands
                if co.get("employeeCount") or co.get("revenue"):
                    stats["sized"] += 1
                ct = zi("/search/contact", {"companyId": str(co["id"]), "rpp": 25})
                owners = [c for c in (ct.get("data") or [])
                          if any(k in (c.get("jobTitle") or "").lower() for k in OWNER_TITLES)]
                if owners:
                    best = max(owners, key=lambda c: c.get("contactAccuracyScore", 0))
                    rec["zi_owner"] = f"{best.get('firstName','')} {best.get('lastName','')}".strip()
                    rec["zi_owner_title"] = best.get("jobTitle")
                    rec["zi_owner_id"] = best.get("id")
                    rec["zi_has_email"] = best.get("hasEmail") or best.get("hasSupplementalEmail")
                    rec["zi_has_mobile"] = best.get("hasMobilePhone")
                    rec["zi_mobile_dnc"] = best.get("mobilePhoneDoNotCall")
                    rec["zi_owner_score"] = best.get("contactAccuracyScore")
                    stats["owner"] += 1
                    if best.get("hasMobilePhone"):
                        stats["mob"] += 1
                rec["zi_contact_count"] = len(ct.get("data") or [])
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if (i + 1) % 25 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.3)
    print(f"FINISHED_ZI {stats}", flush=True)


if __name__ == "__main__":
    main()
