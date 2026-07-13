#!/usr/bin/env python3
"""FREE ZoomInfo sizing + owner-contact pass over the ROC electrical candidate pool.

Filters to Active, AZ-addressed electrical licenses from roc_electrical_raw.jsonl,
then for each runs a free ZI company+contact search (name+AZ, same safe brand-token
matching used elsewhere) to get employeeCount/revenue/domain + owner-titled contact
+ mobile-availability flag. Zero credits spent (search-only). Resumable via
data/elec_zi_verify.jsonl.
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

BASE = Path(__file__).parent / "data"
RAW = BASE / "roc_electrical_raw.jsonl"
LOG = BASE / "elec_zi_verify.jsonl"
CTX = ssl.create_default_context(cafile=certifi.where())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV = Path.home() / "dev/hvac-lead-sourcing/.env"

OWNER_TITLES = ("owner", "president", "ceo", "chief executive", "founder",
                "principal", "partner", "proprietor", "co-owner", "managing member",
                "managing partner", "chief exec", "electrician")

GENERIC_WORDS = {"electric", "electrical", "electricial", "wiring", "power", "volt",
                 "services", "solutions", "systems", "llc", "inc", "co", "company",
                 "the", "of", "az", "arizona", "contracting", "contractors"}

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
                time.sleep(12 * (attempt + 1)); continue
            return {"_err": e.code}
        except Exception:
            time.sleep(4 * (attempt + 1))
    return {"_err": "retry"}


def brand_tokens(name):
    words = re.findall(r"[a-z0-9']+", name.lower())
    return {w for w in words if w not in GENERIC_WORDS and len(w) > 1}


def find_company(name):
    r = zi("/search/company", {"companyName": name, "state": "Arizona", "rpp": 3})
    my_tokens = brand_tokens(name)
    for c in (r.get("data") or []):
        if c.get("state") != "Arizona":
            continue
        cand_tokens = brand_tokens(c.get("name", ""))
        if my_tokens & cand_tokens:  # require a shared non-generic brand token
            return c
    return None


def load_candidates():
    recs = [json.loads(l) for l in open(RAW)]
    out = []
    for r in recs:
        active_elec = any(
            ld.get("status") == "Active" and
            ("electric" in (ld.get("subType") or "").lower() or (ld.get("subType") or "").strip().upper().startswith(("C-11", "CR-11", "L-11", "R-11")))
            for ld in r.get("licenseData", [])
        )
        addr = r.get("address") or ""
        is_az = ", AZ," in addr or addr.strip().endswith("AZ") or ", AZ " in addr
        if active_elec and is_az:
            out.append(r)
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    candidates = load_candidates()
    done = set()
    if LOG.exists():
        for line in open(LOG):
            try:
                done.add(json.loads(line)["account_id"])
            except Exception:
                pass
    targets = [r for r in candidates if r["accountId"] not in done][:limit]
    print(f"Electrical candidates to size (free): {len(targets)} (of {len(candidates)} total)", flush=True)
    get_token()
    stats = {"sized": 0, "owner": 0, "mob": 0, "not_in_zi": 0}
    with open(LOG, "a") as log:
        for i, r in enumerate(targets):
            aid = r["accountId"]
            name = r["accountName"]
            rec = {"account_id": aid, "roc_name": name,
                   "roc_dba": r.get("accountDbaName"), "roc_phone": r.get("phone"),
                   "roc_address": r.get("address"),
                   "roc_license_no": (r.get("licenseData") or [{}])[0].get("licenseNo"),
                   "roc_license_subtype": (r.get("licenseData") or [{}])[0].get("subType"),
                   "roc_contacts": r.get("accountContactData"),
                   "ts": time.strftime("%H:%M:%S")}
            try:
                co = find_company(name)
            except Exception as e:
                rec["error"] = str(e)
                log.write(json.dumps(rec) + "\n")
                log.flush()
                continue
            if not co:
                rec["zi_match"] = None
                stats["not_in_zi"] += 1
            else:
                stats["sized"] += 1
                rec["zi_company_id"] = co.get("id")
                rec["zi_name"] = co.get("name")
                rec["zi_employees"] = co.get("employeeCount")
                rec["zi_revenue_k"] = co.get("revenue")
                rec["zi_domain"] = (co.get("website") or "")
                ct = zi("/search/contact", {"companyId": str(co["id"]), "rpp": 25})
                owners = [c for c in (ct.get("data") or [])
                          if any(k in (c.get("jobTitle") or "").lower() for k in OWNER_TITLES)]
                if owners:
                    best = max(owners, key=lambda c: c.get("contactAccuracyScore", 0))
                    rec["zi_owner"] = f"{best.get('firstName','')} {best.get('lastName','')}".strip()
                    rec["zi_owner_title"] = best.get("jobTitle")
                    rec["zi_owner_id"] = best.get("id")
                    rec["zi_has_mobile"] = best.get("hasMobilePhone")
                    rec["zi_mobile_dnc"] = best.get("mobilePhoneDoNotCall")
                    stats["owner"] += 1
                    if best.get("hasMobilePhone"):
                        stats["mob"] += 1
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.3)
    print(f"FINISHED_ELEC_SIZE {stats}", flush=True)


if __name__ == "__main__":
    main()
