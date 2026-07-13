#!/usr/bin/env python3
"""Apollo email-reveal pass for master rows that HAVE an owner name but no email.

Uses people/match keyed by name + organization_name/domain (reveal_personal_emails=true).
NOT touching phone-reveal credits. ~1 lead credit per matched person, 0 if not found.

Usage: python3 apollo_reveal_emails.py [limit]
Resumable via data/apollo_reveal_emails.jsonl.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dev" / "hvac-lead-sourcing"))
import apollo  # noqa: E402
import gspread  # noqa: E402

BASE = Path(__file__).parent / "data"
LOG = BASE / "apollo_reveal_emails.jsonl"
SHEET_ID = "1bbOBPow3M9a4dgEtQ2wodtdlkXy_fcAiyexKz7yfsQ0"


def reveal_by_name(name, domain, org_name):
    res = apollo._req("POST", "/people/match", body={
        "name": name,
        "domain": domain or None,
        "organization_name": org_name if not domain else None,
        "reveal_personal_emails": True,
    })
    return res.get("person") if isinstance(res, dict) else None


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
        if not r[idx["Owner Name"]].strip() or r[idx["Owner Email"]].strip():
            continue
        targets.append((rid, r[idx["Owner Name"]], r[idx["Domain"]].strip(), r[idx["Company Name"]]))
    targets = targets[:limit]
    print(f"Email-reveal targets (owner known, no email): {len(targets)}", flush=True)

    stats = {"matched": 0, "email_found": 0, "not_found": 0}
    with open(LOG, "a") as log:
        for i, (rid, name, domain, org_name) in enumerate(targets):
            rec = {"row_id": rid, "owner_name": name, "company": org_name, "domain": domain, "ts": time.strftime("%H:%M:%S")}
            person = reveal_by_name(name, domain, org_name)
            if not person:
                rec["result"] = "not_found"
                stats["not_found"] += 1
            else:
                stats["matched"] += 1
                email = person.get("email")
                rec["result"] = "matched"
                rec["email"] = email
                rec["linkedin"] = person.get("linkedin_url")
                if email and "not_unlocked" not in str(email):
                    stats["email_found"] += 1
            log.write(json.dumps(rec) + "\n"); log.flush()
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.4)
    print(f"FINISHED_EMAIL_REVEAL {stats}", flush=True)


if __name__ == "__main__":
    main()
