#!/usr/bin/env python3
"""Apollo owner-sourcing pass for master rows with NO owner name at all.

For rows with a domain: organizations/enrich -> org id -> mixed_people/api_search
(owner-titled) -> people/match (reveal_personal_emails=true, NOT phone -- Apollo
direct-dial pool is exhausted). For rows without a domain: skip (handled separately
via ZI name-search or left for manual/ROC research).

Credit cost: ~1 credit for org enrich (0 if not found) + ~1 credit per person match
(0 if not found). NOT touching direct-dial/phone reveal credits.

Usage: python3 apollo_source_owners.py [limit]
Resumable via data/apollo_source_owners.jsonl.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dev" / "hvac-lead-sourcing"))
import apollo  # noqa: E402
import gspread  # noqa: E402

BASE = Path(__file__).parent / "data"
LOG = BASE / "apollo_source_owners.jsonl"
SHEET_ID = "1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    gc = gspread.service_account(filename=str(Path.home() / "dev/hvac-lead-sourcing/service_account.json"))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet("Enriched Master")
    rows = ws.get_all_values()
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}

    done = set()
    if LOG.exists():
        for line in open(LOG):
            try:
                done.add(json.loads(line)["row_id"])
            except Exception:
                pass

    targets = []
    for i, r in enumerate(rows[1:], start=2):
        if not r[idx["Company Name"]]:
            continue
        rid = r[idx["ID"]]
        if rid in done:
            continue
        if r[idx["Owner Name"]].strip():
            continue
        domain = r[idx["Domain"]].strip()
        if not domain:
            continue
        targets.append((rid, i, r[idx["Company Name"]], domain))
    targets = targets[:limit]
    print(f"Apollo owner-sourcing targets (have domain, no owner): {len(targets)}", flush=True)

    stats = {"org_found": 0, "owner_found": 0, "email_found": 0, "not_found": 0}
    with open(LOG, "a") as log:
        for i, (rid, row_i, name, domain) in enumerate(targets):
            rec = {"row_id": rid, "company": name, "domain": domain, "ts": time.strftime("%H:%M:%S")}
            org = apollo.enrich_org(domain)
            if not org or not org.get("id"):
                rec["result"] = "org_not_found"
                stats["not_found"] += 1
                log.write(json.dumps(rec) + "\n"); log.flush()
                time.sleep(0.4)
                continue
            stats["org_found"] += 1
            rec["apollo_org_id"] = org["id"]
            rec["apollo_employees"] = org.get("estimated_num_employees")
            person = apollo.find_owner(org["id"])
            if not person:
                rec["result"] = "no_owner_contact"
                log.write(json.dumps(rec) + "\n"); log.flush()
                time.sleep(0.4)
                continue
            stats["owner_found"] += 1
            revealed = apollo.reveal_person(person["id"])
            if revealed:
                rec["owner_name"] = revealed.get("name")
                rec["owner_title"] = revealed.get("title")
                rec["owner_email"] = revealed.get("email")
                rec["owner_linkedin"] = revealed.get("linkedin_url")
                if revealed.get("email") and "email_not_unlocked" not in str(revealed.get("email")):
                    stats["email_found"] += 1
                rec["result"] = "success"
            else:
                rec["result"] = "reveal_failed"
            log.write(json.dumps(rec) + "\n"); log.flush()
            if (i + 1) % 25 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.4)
    print(f"FINISHED_APOLLO_SOURCE {stats}", flush=True)


if __name__ == "__main__":
    main()
