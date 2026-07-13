"""Pull full TDLR Electrical Contractor + A/C Contractor datasets via Socrata API."""
import json
import time
import requests

BASE = "https://data.texas.gov/resource/7358-krk7.json"
PAGE_SIZE = 1000

LICENSE_TYPES = {
    "Electrical Contractor": "data/tx_tdlr_electrical_raw.json",
    "A/C Contractor": "data/tx_tdlr_ac_raw.json",
}


def pull(license_type, out_path):
    all_rows = []
    offset = 0
    while True:
        params = {
            "license_type": license_type,
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "license_number",
        }
        resp = requests.get(BASE, params=params, timeout=60)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        print(f"  {license_type}: pulled {len(all_rows)} so far (offset {offset})")
        offset += PAGE_SIZE
        if len(rows) < PAGE_SIZE:
            break
        time.sleep(0.2)

    with open(out_path, "w") as f:
        json.dump(all_rows, f)
    print(f"{license_type}: {len(all_rows)} total rows -> {out_path}")
    return len(all_rows)


if __name__ == "__main__":
    for lt, path in LICENSE_TYPES.items():
        print(f"Pulling {lt}...")
        pull(lt, path)
