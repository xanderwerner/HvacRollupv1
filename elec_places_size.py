#!/usr/bin/env python3
"""Google Places + Apollo sizing pass for ROC electrical candidates that ZoomInfo
free search couldn't find (no B2B footprint). Places gives us a domain via
place_details; Apollo organizations/enrich then gives a real employee count
(cheap, ~1 lead credit per match, 0 if not found).

Usage: python3 elec_places_size.py [limit]
Resumable via data/elec_places_size.jsonl.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dev" / "hvac-lead-sourcing"))
import places  # noqa: E402
import apollo  # noqa: E402

BASE = Path(__file__).parent / "data"
ZI_LOG = BASE / "elec_zi_verify.jsonl"
LOG = BASE / "elec_places_size.jsonl"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    zi_recs = [json.loads(l) for l in open(ZI_LOG)]
    unsized = [r for r in zi_recs if not r.get("zi_employees")]

    done = set()
    if LOG.exists():
        for line in open(LOG):
            try:
                done.add(json.loads(line)["account_id"])
            except Exception:
                pass
    targets = [r for r in unsized if r["account_id"] not in done][:limit]
    print(f"Places+Apollo sizing targets: {len(targets)} (of {len(unsized)} ZI-unsized)", flush=True)

    stats = {"place_found": 0, "domain_found": 0, "apollo_sized": 0}
    with open(LOG, "a") as log:
        for i, r in enumerate(targets):
            aid = r["account_id"]
            name = r["roc_name"]
            addr = r.get("roc_address") or ""
            city = addr.split(",")[0].strip() if addr else ""
            rec = {"account_id": aid, "roc_name": name, "ts": time.strftime("%H:%M:%S")}
            try:
                query = f"{name} {city} AZ"
                results = places.text_search(query)
            except Exception as e:
                rec["error"] = f"places_search: {e}"
                log.write(json.dumps(rec) + "\n"); log.flush()
                time.sleep(0.2)
                continue
            if not results:
                rec["places_match"] = None
                log.write(json.dumps(rec) + "\n"); log.flush()
                time.sleep(0.2)
                continue
            stats["place_found"] += 1
            top = results[0]
            rec["places_name"] = top.get("name")
            rec["places_place_id"] = top.get("place_id")
            rec["places_rating"] = top.get("rating")
            rec["places_review_count"] = top.get("user_ratings_total")
            try:
                details = places.place_details(top["place_id"])
            except Exception as e:
                details = {}
                rec["details_error"] = str(e)
            website = (details.get("website") or "").strip()
            rec["places_phone"] = details.get("formatted_phone_number")
            rec["places_status"] = details.get("business_status")
            if website:
                stats["domain_found"] += 1
                dom = website.replace("https://", "").replace("http://", "").split("/")[0]
                dom = dom[4:] if dom.startswith("www.") else dom
                rec["domain"] = dom
                org = apollo.enrich_org(dom)
                if org and org.get("id"):
                    stats["apollo_sized"] += 1
                    rec["apollo_employees"] = org.get("estimated_num_employees")
                    rec["apollo_revenue"] = org.get("annual_revenue")
                    rec["apollo_org_id"] = org.get("id")
            log.write(json.dumps(rec) + "\n"); log.flush()
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(targets)}] {stats}", flush=True)
            time.sleep(0.15)
    print(f"FINISHED_PLACES_SIZE {stats}", flush=True)


if __name__ == "__main__":
    main()
