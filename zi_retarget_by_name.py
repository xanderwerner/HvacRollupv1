#!/usr/bin/env python3
"""Targeted ZI redeem-by-name pass for master rows where the company matched
in ZI's free search but no owner-titled contact was found there (so the free
pass never confirmed a mobile). We already know the real owner's name from
another source (Apollo/ROC) -- try redeeming THAT specific person directly.

Skips rows whose zi_owner_id is shared with >1 other row in the free-search
log (confirmed generic-name/franchise contamination pattern found this session).

Usage: python3 zi_retarget_by_name.py [limit]
Resumable via data/zi_retarget_by_name.jsonl. Has a credit-runaway breaker.
"""
import json
import ssl
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import certifi

BASE = Path(__file__).parent / "data"
LOG = BASE / "zi_retarget_by_name.jsonl"
CTX = ssl.create_default_context(cafile=certifi.where())
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV = Path.home() / "dev/hvac-lead-sourcing/.env"
SHEET_ID = "1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0"
CREDIT_LIMIT = 700
MAX_SPEND_THIS_RUN = 200  # circuit breaker

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


def zi(path, payload, method="POST"):
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
            try:
                body = json.loads(e.read())
            except Exception:
                body = {}
            return {"_err": e.code, "_body": body}
        except Exception:
            time.sleep(4 * (attempt + 1))
    return {"_err": "retry"}


def credit_used():
    req = urllib.request.Request("https://api.zoominfo.com/lookup/usage",
        headers={"Authorization": "Bearer " + _token["jwt"], "User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=30, context=CTX).read())
    u = [x for x in d["usage"] if x["limitType"] == "uniqueIdLimit"][0]
    return u["currentUsage"], u["totalLimit"]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    import gspread
    gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet("Enriched Master")
    rows = ws.get_all_values()
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}

    zi_log = {}
    for line in open(BASE / "zi_enrich.jsonl"):
        d = json.loads(line)
        zi_log[d["row_id"]] = d

    owner_id_counts = Counter(d["zi_owner_id"] for d in zi_log.values() if d.get("zi_owner_id"))

    done = set()
    if LOG.exists():
        for line in open(LOG):
            try:
                done.add(json.loads(line)["row_id"])
            except Exception:
                pass

    targets = []
    for r in rows[1:]:
        if not r[idx["Company Name"]]:
            continue
        rid = r[idx["ID"]]
        if rid in done:
            continue
        owner = r[idx["Owner Name"]].strip()
        cell = r[idx["Owner Cell"]].strip()
        if not owner or cell:
            continue
        d = zi_log.get(rid)
        # Now include not_in_zi (person-level enrich can succeed even when the
        # company wasn't in ZI's structured company index) AND rows that were
        # never free-searched at all (new electrical rows). Only requirement:
        # skip if ZI's free search already gave a confirmed owner contact here
        # (that path is handled separately) or the contact is a known-contaminated
        # shared ID.
        if d and d.get("zi_owner"):
            continue
        oid = d.get("zi_owner_id") if d else None
        if oid and owner_id_counts.get(oid, 0) > 1:
            continue  # contaminated shared-contact case
        targets.append((rid, owner, r[idx["Company Name"]], r[idx["Domain"]].strip()))
    targets = targets[:limit]
    print(f"Targeted retry-by-name candidates: {len(targets)}", flush=True)

    get_token()
    start_used, _ = credit_used()
    stats = {"matched": 0, "mobile_found": 0, "no_match": 0}
    with open(LOG, "a") as log:
        for i, (rid, owner, company, domain) in enumerate(targets):
            used, _ = credit_used()
            if used - start_used >= MAX_SPEND_THIS_RUN:
                print(f"CIRCUIT BREAKER: spent {used - start_used} credits this run, stopping.", flush=True)
                break
            payload = {"fullName": owner, "companyName": company}
            res = zi("/enrich/contact", {"matchPersonInput": [payload],
                     "outputFields": ["firstName", "lastName", "phone", "mobilePhone",
                                       "mobilePhoneDoNotCall", "email", "jobTitle"]})
            rec = {"row_id": rid, "owner": owner, "company": company, "ts": time.strftime("%H:%M:%S")}
            result = ((res.get("data") or {}).get("result") or [{}])[0] if isinstance(res, dict) else {}
            match_status = result.get("matchStatus")
            cdata = (result.get("data") or [{}])[0] if result.get("data") else {}
            rec["match_status"] = match_status
            if match_status in ("FULL_MATCH", "COMPANY_ONLY_MATCH") and cdata:
                stats["matched"] += 1
                rec["result"] = cdata
                if cdata.get("mobilePhone"):
                    stats["mobile_found"] += 1
            else:
                stats["no_match"] += 1
                rec["result"] = res if isinstance(res, dict) else None
            log.write(json.dumps(rec) + "\n"); log.flush()
            if (i + 1) % 20 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.3)
    print(f"FINISHED_RETARGET {stats}", flush=True)


if __name__ == "__main__":
    main()
