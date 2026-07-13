#!/usr/bin/env python3
"""Broad ROC sweep for AZ electrical contractors (free) -- classification-filtered.

The classification param on ARCP_ContractorSearch appears server-ignored, so we
search broad text keys and filter client-side on licenseData[].subType.
Dedupes by accountId. Resumable via data/roc_electrical_raw.jsonl.
"""
import json
import ssl
import urllib.parse
import urllib.request
import time
from pathlib import Path

import certifi

BASE = Path(__file__).parent / "data"
RECON = BASE / "roc_recon" / "call_17.json"
OUT = BASE / "roc_electrical_raw.jsonl"
CTX = ssl.create_default_context(cafile=certifi.where())

recon = json.load(open(RECON))
URL = recon["url"]
POST_TEMPLATE = urllib.parse.parse_qs(recon["post"])

SEARCH_KEYS = [
    "electric", "electrical", "wiring", "electrician", "power", "volt",
    "amp electric", "electric co", "electric llc", "electric inc",
]

def roc_search(key):
    post = {k: v[0] for k, v in POST_TEMPLATE.items()}
    msg = json.loads(post["message"])
    msg["actions"][0]["params"]["searchKey"] = key
    msg["actions"][0]["params"]["classification"] = None
    msg["actions"][0]["params"]["city"] = ""
    post["message"] = json.dumps(msg)
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(post).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30, context=CTX).read())
            act = resp["actions"][0]
            if act["state"] != "SUCCESS":
                return []
            return act.get("returnValue") or []
        except Exception:
            time.sleep(6 * (attempt + 1))
    return []

def main():
    seen_ids = set()
    if OUT.exists():
        for line in open(OUT):
            seen_ids.add(json.loads(line)["accountId"])
    with open(OUT, "a") as f:
        for key in SEARCH_KEYS:
            results = roc_search(key)
            new = 0
            for r in results:
                aid = r.get("accountId")
                if not aid or aid in seen_ids:
                    continue
                subs = [ld.get("subType", "") for ld in (r.get("licenseData") or [])]
                is_elec = any(("electric" in s.lower() or s.strip().upper().startswith(("C-11", "CR-11", "L-11", "R-11")))
                              for s in subs)
                if not is_elec:
                    continue
                seen_ids.add(aid)
                f.write(json.dumps(r) + "\n")
                new += 1
            print(f"key={key!r}: {len(results)} raw, {new} new electrical-classified", flush=True)
            time.sleep(0.5)
    print(f"TOTAL unique electrical contractors: {len(seen_ids)}")

if __name__ == "__main__":
    main()
