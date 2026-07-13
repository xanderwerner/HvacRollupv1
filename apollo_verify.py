#!/usr/bin/env python3
"""Apollo cross-check pass — confirm owner identity + firmographics (NO phone/email reveal).

For every master row with an owner name + domain/email that hasn't been through
Apollo yet, run a plain people/match (1 lead credit each, no phone/email reveal
since direct-dial is exhausted and email isn't being chased right now). Captures
title, LinkedIn, and the org's employee/revenue for cross-verification against
ZoomInfo and the existing master data.

Resumable via data/apollo_verify.jsonl.
Usage: python3 apollo_verify.py [limit]
"""
import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path

import certifi
import openpyxl

BASE = Path(__file__).parent / "data"
MASTER = BASE / "AZ_targets_enriched_master.xlsx"
LOG = BASE / "apollo_verify.jsonl"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
KEY = next(
    line.split("=", 1)[1].strip()
    for line in open(Path.home() / "dev/hvac-lead-sourcing/.env")
    if line.startswith("APOLLO_API_KEY=")
)


def api(payload):
    req = urllib.request.Request(
        "https://api.apollo.io/api/v1/people/match",
        data=json.dumps(payload).encode(),
        headers={"X-Api-Key": KEY, "Content-Type": "application/json"},
    )
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            return {"_err": e.code, "_body": e.read().decode()[:200]}
        except Exception as e:
            last = str(e)
            time.sleep(5 * (attempt + 1))
    return {"_err": "retry", "_body": last}


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
        r for r in rows
        if r[1] and r[5] and (r[22] or r[9]) and r[0] not in done
    ][:limit]
    print(f"targets: {len(targets)}", flush=True)
    stats = {"match": 0, "no_match": 0, "conflict_name": 0}
    with open(LOG, "a") as log:
        for i, r in enumerate(targets):
            rid, company, owner, email, domain = r[0], r[1], str(r[5]).strip(), r[9], r[22]
            payload = {"name": owner, "organization_name": company}
            if domain:
                payload["domain"] = str(domain).strip()
            if email:
                payload["email"] = str(email).strip()
            resp = api(payload)
            person = resp.get("person") or {}
            org = person.get("organization") or {}
            rec = {
                "row_id": rid, "company": company, "owner_input": owner,
                "matched": bool(person),
                "apollo_name": person.get("name"),
                "apollo_title": person.get("title"),
                "apollo_email": person.get("email"),
                "linkedin": person.get("linkedin_url"),
                "apollo_employees": org.get("estimated_num_employees"),
                "apollo_revenue": org.get("annual_revenue"),
                "error": resp.get("_err"),
            }
            if rec["matched"]:
                stats["match"] += 1
                if rec["apollo_name"] and owner.split()[0].lower() not in rec["apollo_name"].lower() \
                        and owner.split()[-1].lower() not in rec["apollo_name"].lower():
                    stats["conflict_name"] += 1
            else:
                stats["no_match"] += 1
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(1.0)
    print(f"FINISHED_APOLLO_VERIFY {stats}", flush=True)


if __name__ == "__main__":
    main()
