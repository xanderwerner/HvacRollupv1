#!/usr/bin/env python3
"""Supplementary Google Places sweep for electrical contractors across AZ, to catch
anything the AZ ROC licensing sweep might have missed (DBA/trade names Google indexes
differently, very recently formed companies, etc). Cross-references against the
already-added 1,819 ROC-sourced electrical companies by normalized name; only truly
net-new candidates get reported.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dev/hvac-lead-sourcing"))
import places  # noqa: E402

CITIES = [
    "Phoenix", "Tucson", "Mesa", "Glendale", "Gilbert", "Scottsdale", "Peoria",
    "Tempe", "Surprise", "Lake Havasu City", "Chandler", "Flagstaff", "Queen Creek",
    "Yuma", "Prescott Valley", "Prescott", "Apache Junction", "San Tan Valley",
    "Buckeye", "Kingman", "Casa Grande", "Goodyear", "Avondale", "Litchfield Park",
    "Laveen", "Marana", "Maricopa", "Bullhead City", "Sierra Vista", "Show Low",
]

GENERIC_WORDS = {"electric", "electrical", "electricial", "wiring", "power", "volt",
                  "services", "solutions", "systems", "llc", "inc", "co", "company",
                  "the", "of", "az", "arizona", "contracting", "contractors",
                  "electrician", "electricians"}


def brand_tokens(name):
    words = re.findall(r"[a-z0-9']+", name.lower())
    return {w for w in words if w not in GENERIC_WORDS and len(w) > 1}


def load_existing_names():
    import openpyxl
    wb = openpyxl.load_workbook("data/AZ_targets_enriched_master.xlsx")
    ws = wb["Enriched Master"]
    rows = list(ws.iter_rows(values_only=True))
    data = [r for r in rows[1:] if r[1] and r[2] == "Electrical"]
    return [frozenset(brand_tokens(r[1])) for r in data if brand_tokens(r[1])]


def main():
    existing_token_sets = load_existing_names()
    print(f"existing electrical companies (brand-token sets): {len(existing_token_sets)}")

    seen_place_ids = set()
    all_results = []
    for city in CITIES:
        query = f"electrician in {city} AZ"
        try:
            results = places.text_search(query)
        except Exception as e:
            print(f"  ! {city}: {e}")
            continue
        new_here = 0
        for r in results:
            pid = r.get("place_id")
            if not pid or pid in seen_place_ids:
                continue
            seen_place_ids.add(pid)
            name = r.get("name", "")
            tokens = brand_tokens(name)
            is_new = not tokens or not any(tokens & existing for existing in existing_token_sets)
            if is_new:
                all_results.append({
                    "place_id": pid, "name": name, "city": city,
                    "address": r.get("formatted_address", ""),
                    "rating": r.get("rating"), "reviews": r.get("user_ratings_total"),
                    "business_status": r.get("business_status", ""),
                })
                new_here += 1
        print(f"  {city}: {len(results)} results, {new_here} not matched to existing electrical list")
        time.sleep(0.15)

    with open("data/elec_places_supplement_candidates.json", "w") as f:
        json.dump(all_results, f, indent=1)
    print(f"\nTotal net-new candidates (unmatched by brand token to existing 1,819): {len(all_results)}")


if __name__ == "__main__":
    main()
