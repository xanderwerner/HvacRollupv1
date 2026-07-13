#!/usr/bin/env python3
"""ZoomInfo owner-mobile enrichment -- sniper mode, not machine-gun mode.

Processes a curated ID list (step1_ids.json or step2_ids.json) one at a time,
using the already-confirmed zi_owner_id from the free search pass (no blind
re-searching). Paced deliberately, checks credit balance periodically so any
runaway cost is caught immediately, and logs full detail for manual review
before anything gets merged into the master.

Usage: python3 zi_enrich_phones.py <step1_ids.json|step2_ids.json> [limit]
"""
import json
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
CTX = ssl.create_default_context(cafile=certifi.where())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV = Path.home() / "dev/hvac-lead-sourcing/.env"

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
                time.sleep(15 * (attempt + 1)); continue
            return {"_err": e.code, "_body": e.read().decode()[:200]}
        except Exception:
            time.sleep(4 * (attempt + 1))
    return {"_err": "retry"}


def credit_balance():
    req = urllib.request.Request("https://api.zoominfo.com/lookup/usage",
        headers={"Authorization": "Bearer " + _token["jwt"], "User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=30, context=CTX).read())
    u = [x for x in d["usage"] if x["limitType"] == "uniqueIdLimit"][0]
    return u["currentUsage"], u["totalLimit"]


OUTPUT_FIELDS = ["firstName", "lastName", "jobTitle", "phone", "mobilePhone",
                 "mobilePhoneDoNotCall", "directPhoneDoNotCall", "email",
                 "managementLevel", "lastUpdatedDate", "contactAccuracyScore",
                 "companyName"]


def find_owner_id(company_name, domain):
    """Fallback free lookup when a stored owner_id is missing."""
    import re
    dom = re.sub(r"^https?://", "", str(domain or "")).split("/")[0]
    dom = dom[4:] if dom.startswith("www.") else dom
    if not dom:
        return None
    co = zi("/search/company", {"companyWebsite": dom, "rpp": 1})
    if not co.get("data"):
        return None
    cid = co["data"][0]["id"]
    ct = zi("/search/contact", {"companyId": str(cid), "rpp": 25})
    owners = [c for c in (ct.get("data") or [])
              if any(k in (c.get("jobTitle") or "").lower()
                     for k in ("owner","president","ceo","founder","principal","partner"))]
    if owners:
        return max(owners, key=lambda c: c.get("contactAccuracyScore", 0)).get("id")
    return None


def main():
    id_file = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
    step_ids = json.load(open(BASE / id_file))[:limit]
    step_name = "step1" if "step1" in id_file else "step2"
    log_path = BASE / f"{step_name}_enrich_results.jsonl"

    done = set()
    if log_path.exists():
        for l in open(log_path):
            try:
                done.add(json.loads(l)["row_id"])
            except Exception:
                pass
    step_ids = [rid for rid in step_ids if rid not in done]

    wb = openpyxl.load_workbook(MASTER)
    rows = {r[0].value: r for r in wb["Enriched Master"].iter_rows(min_row=2) if r[1].value}

    zi_data = {}
    for fname in ("zi_enrich.jsonl", "zi_reverify.jsonl"):
        p = BASE / fname
        if p.exists():
            for l in open(p):
                r = json.loads(l)
                zi_data[r["row_id"]] = r

    get_token()
    start_used, limit_total = credit_balance()
    print(f"[{step_name}] starting: {len(step_ids)} targets | credits used so far: {start_used}/{limit_total}", flush=True)

    mobiles_found = 0
    with open(log_path, "a") as log:
        for i, rid in enumerate(step_ids):
            row = rows.get(rid)
            if not row:
                continue
            company = row[1].value
            z = zi_data.get(rid, {})
            owner_id = z.get("zi_owner_id")
            if not owner_id:
                owner_id = find_owner_id(company, row[22].value)
                time.sleep(0.3)
            if not owner_id:
                log.write(json.dumps({"row_id": rid, "company": company, "error": "no_owner_id_found"}) + "\n")
                log.flush()
                print(f"[{i+1}/{len(step_ids)}] {company[:40]:40} SKIP - no owner id", flush=True)
                continue

            res = zi("/enrich/contact", {"matchPersonInput": [{"personId": owner_id}], "outputFields": OUTPUT_FIELDS})
            rec = {"row_id": rid, "company": company, "owner_id": owner_id, "ts": time.strftime("%H:%M:%S")}
            try:
                result = res["data"]["result"][0]
                match_status = result.get("matchStatus")
                data = result.get("data", [{}])[0] if result.get("data") else {}
                rec.update({
                    "match_status": match_status,
                    "zi_name": f"{data.get('firstName','')} {data.get('lastName','')}".strip(),
                    "zi_company": (data.get("company") or {}).get("name"),
                    "mobile": data.get("mobilePhone"),
                    "mobile_dnc": data.get("mobilePhoneDoNotCall"),
                    "direct_phone": data.get("phone"),
                    "direct_dnc": data.get("directPhoneDoNotCall"),
                    "email": data.get("email"),
                    "title": data.get("jobTitle"),
                    "accuracy": data.get("contactAccuracyScore"),
                    "last_updated": data.get("lastUpdatedDate"),
                })
                name_flag = ""
                zi_co = (rec.get("zi_company") or "").lower()
                if zi_co and company and zi_co not in company.lower() and company.lower() not in zi_co:
                    name_flag = "  <-- COMPANY NAME MISMATCH, verify before using"

                # domain cross-check: contact's email domain must agree with the
                # company's real domain, or this is likely a cross-contaminated
                # ZoomInfo contact record (wrong person attached to right company)
                row_domain = str(row[22].value or "").lower().strip()
                email = (rec.get("email") or "").lower()
                email_dom = email.split("@")[-1] if "@" in email else None
                suspect = bool(email_dom and row_domain and email_dom not in row_domain and row_domain not in email_dom)
                rec["suspect_contact_mismatch"] = suspect
                if suspect:
                    name_flag = f"  <-- SUSPECT: email domain '{email_dom}' != company domain '{row_domain}', DO NOT USE without manual check"

                mob = rec.get("mobile")
                if mob and not suspect:
                    mobiles_found += 1
                tag = ("SUSPECT (mobile withheld)" if (mob and suspect) else ("MOBILE " + mob if mob else "no mobile"))
                print(f"[{i+1}/{len(step_ids)}] {company[:40]:40} {tag}{name_flag}", flush=True)
            except Exception as e:
                rec["error"] = f"parse_error: {e}"
                rec["raw"] = res
                print(f"[{i+1}/{len(step_ids)}] {company[:40]:40} ERROR parsing response", flush=True)

            log.write(json.dumps(rec) + "\n")
            log.flush()
            time.sleep(1.5)

            if (i + 1) % 15 == 0:
                used, _ = credit_balance()
                spent = used - start_used
                expected = i + 1
                print(f"  --- credit check: {used}/{limit_total} used ({spent} spent this run, expected ~{expected}) ---", flush=True)
                if spent > expected + 5:
                    print("  !!! SPENDING FASTER THAN EXPECTED - STOPPING FOR REVIEW !!!", flush=True)
                    break

    used, _ = credit_balance()
    print(f"\n[{step_name}] FINISHED - {mobiles_found} mobiles found | credits used this run: {used - start_used} | total used: {used}/{limit_total}", flush=True)


if __name__ == "__main__":
    main()
