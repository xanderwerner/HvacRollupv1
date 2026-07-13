#!/usr/bin/env python3
"""Fill missing owner names from the AZ ROC contractor-search portal (free).

For every master row with no Owner Name, search ROC by company name and record
qualifying-party names + license data. Results append to roc_names.jsonl
(resumable). Match confidence is scored by name similarity + city agreement.

Usage: python3 roc_fill_names.py [limit]
"""
import difflib
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import openpyxl

BASE = Path(__file__).parent / "data"
MASTER = BASE / "AZ_targets_enriched_master.xlsx"
LOG = BASE / "roc_names.jsonl"
RECON = BASE / "roc_recon" / "call_17.json"
CTX = ssl.create_default_context(cafile=certifi.where())

recon = json.load(open(RECON))
URL = recon["url"]
POST_TEMPLATE = urllib.parse.parse_qs(recon["post"])

SUFFIX = re.compile(
    r",?\s*(llc\.?|l\.l\.c\.?|inc\.?|corp\.?|co\.?|company|ltd\.?|plc|pllc)\s*$", re.I
)
NOISE = re.compile(
    r"\b(heating|cooling|air conditioning|air|plumbing|electrical|electric|hvac|"
    r"services?|solutions|systems|mechanical|refrigeration|&|and|the|of|az|arizona)\b",
    re.I,
)


def simplify(name):
    n = SUFFIX.sub("", str(name).strip())
    n = re.sub(r"\s*-\s*(phoenix|tucson|mesa|chandler|gilbert|scottsdale|tempe|glendale|peoria).*$", "", n, flags=re.I)
    return n.strip()


def roc_search(key, city=""):
    post = {k: v[0] for k, v in POST_TEMPLATE.items()}
    msg = json.loads(post["message"])
    msg["actions"][0]["params"]["searchKey"] = key
    msg["actions"][0]["params"]["city"] = ""
    post["message"] = json.dumps(msg)
    req = urllib.request.Request(
        URL,
        data=urllib.parse.urlencode(post).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
    )
    for attempt in range(4):
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30, context=CTX).read())
            act = resp["actions"][0]
            if act["state"] != "SUCCESS":
                return {"_error": act["state"]}
            return {"results": act.get("returnValue") or []}
        except Exception as e:
            err = str(e)
            time.sleep(8 * (attempt + 1))
    return {"_error": err}


def best_match(company, city, results):
    target = simplify(company).lower()
    scored = []
    for r in results:
        cand = simplify(r.get("accountName", "")).lower()
        ratio = difflib.SequenceMatcher(None, target, cand).ratio()
        city_ok = city and city.lower() in (r.get("address") or "").lower()
        scored.append((ratio + (0.15 if city_ok else 0), ratio, r))
    scored.sort(key=lambda x: -x[0])
    return scored[0] if scored else None


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
    targets = [
        (r[0], r[1], r[3], r[24])  # id, name, city, license#
        for r in rows
        if r[1] and not r[5] and r[0] not in done
    ][:limit]
    print(f"targets: {len(targets)}", flush=True)
    hits = 0
    with open(LOG, "a") as log:
        for i, (rid, company, city, lic) in enumerate(targets):
            key = str(lic).strip() if lic else simplify(company)
            res = roc_search(key)
            rec = {"row_id": rid, "company": company, "city": city, "search_key": key,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if "_error" in res:
                rec["error"] = res["_error"]
            elif not res["results"]:
                # retry once with an even simpler key (first 2 significant words)
                words = [w for w in re.split(r"\W+", simplify(company)) if w and not NOISE.match(w)]
                alt = " ".join(words[:2]) if words else None
                if alt and alt.lower() != key.lower():
                    time.sleep(1.5)
                    res2 = roc_search(alt)
                    rec["search_key_alt"] = alt
                    if res2.get("results"):
                        res = res2
            if res.get("results"):
                m = best_match(company, city, res["results"])
                if m:
                    score, ratio, r = m
                    rec.update(
                        {
                            "roc_name": r.get("accountName"),
                            "match_ratio": round(ratio, 3),
                            "roc_phone": r.get("phone"),
                            "roc_address": r.get("address"),
                            "contacts": [c.get("contactName") for c in r.get("accountContactData", [])],
                            "licenses": [
                                {"no": l.get("licenseNo"), "qp": l.get("qpName"),
                                 "status": l.get("status"), "class": l.get("subType")}
                                for l in r.get("licenseData", [])
                            ],
                            "n_results": len(res["results"]),
                        }
                    )
                    hits += 1
            log.write(json.dumps(rec) + "\n")
            log.flush()
            qp = rec.get("licenses", [{}])[0].get("qp") if rec.get("licenses") else None
            print(f"[{i+1}/{len(targets)}] {str(company)[:42]:42s} {qp or rec.get('error') or 'no roc match'}", flush=True)
            time.sleep(2.0)
    print(f"FINISHED_ROC hits={hits}/{len(targets)}", flush=True)


if __name__ == "__main__":
    main()
