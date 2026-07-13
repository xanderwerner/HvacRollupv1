"""Build a deduped Texas company name list from TDLR (electrical + A/C) and TSBPE (plumbing) data.

Company-level dedup only -- this is a name list for the next (sizing) pass, not enrichment.
Dedup key is normalized company name + trade (NOT county -- a company operating across
multiple TX counties must collapse to one row, not one row per county). A second pass merges
remaining rows that share a phone number within the same trade, since that's almost always
the same real-world business/contact even when the registered name differs slightly (DBAs,
"Inc" vs "LLC" filings, parent/sub naming, etc).
"""
import csv
import json
import re
from datetime import date
from collections import defaultdict

TODAY = date(2026, 7, 13)


def parse_exp(mmddccyy):
    if not mmddccyy:
        return None
    try:
        m, d, y = mmddccyy.split("/")
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def normalize_name(name):
    name = name.upper().strip()
    name = re.sub(r"[^A-Z0-9& ]", "", name)
    name = re.sub(r"\s+", " ", name)
    # strip common suffixes that cause false-distinct dupes
    name = re.sub(r"\b(LLC|INC|CORP|CO|LTD|LP|LLP)\b\.?$", "", name).strip()
    return name


def merge_into(existing, phone, addr, city, county, license_count_inc=1):
    existing["license_count"] += license_count_inc
    if not existing["phone"] and phone:
        existing["phone"] = phone
    if not existing["address"] and addr:
        existing["address"] = addr
    if not existing["city"] and city:
        existing["city"] = city
    if county and county not in existing["counties"]:
        existing["counties"].append(county)


def load_tdlr(path, trade):
    companies = {}
    rows = json.load(open(path))
    for r in rows:
        exp = parse_exp(r.get("license_expiration_date_mmddccyy"))
        if not exp or exp < TODAY:
            continue  # not current
        raw_name = r.get("business_name") or r.get("owner_name")
        if not raw_name:
            continue
        key = normalize_name(raw_name)
        phone = r.get("business_telephone") or r.get("owner_telephone") or ""
        city_state_zip = r.get("business_city_state_zip") or r.get("mailing_address_city_state_zip") or ""
        city = city_state_zip.rsplit(" TX", 1)[0].strip() if " TX" in city_state_zip else ""
        addr = r.get("business_address_line1") or r.get("mailing_address_line1") or ""
        county = r.get("business_county") or r.get("mailing_address_county") or ""

        if key in companies:
            merge_into(companies[key], phone, addr, city, county)
        else:
            companies[key] = {
                "company_name": raw_name.strip(),
                "trade": trade,
                "city": city,
                "state": "TX",
                "counties": [county] if county else [],
                "phone": phone,
                "address": addr,
                "license_number": r.get("license_number", ""),
                "license_source": "TDLR",
                "license_count": 1,
            }
    return companies


def load_tsbpe(path):
    companies = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("LIC_STATUS") != "Current":
                continue
            raw_name = (r.get("PLUMB_COMPANY") or "").strip()
            if not raw_name:
                continue
            key = normalize_name(raw_name)
            phone = r.get("PHONE") or ""
            city = r.get("CITY") or ""
            addr = r.get("ADDR1") or ""
            county = r.get("COUNTY") or ""

            if key in companies:
                merge_into(companies[key], phone, addr, city, county)
            else:
                companies[key] = {
                    "company_name": raw_name,
                    "trade": "Plumbing",
                    "city": city,
                    "state": "TX",
                    "counties": [county] if county else [],
                    "phone": phone,
                    "address": addr,
                    "license_number": r.get("LICENSE_NBR", ""),
                    "license_source": "TSBPE",
                    "license_count": 1,
                }
    return companies


def merge_by_phone(companies_dict):
    """Second pass: within one trade's company dict, collapse rows that share a phone
    number onto the row with the highest license_count (most likely the 'real' filing name).
    Other names sharing that phone are recorded in 'aka'."""
    by_phone = defaultdict(list)
    for key, c in companies_dict.items():
        if c["phone"]:
            by_phone[c["phone"]].append(key)

    merged_keys = set()
    for phone, keys in by_phone.items():
        if len(keys) < 2:
            continue
        keys_sorted = sorted(keys, key=lambda k: -companies_dict[k]["license_count"])
        primary_key = keys_sorted[0]
        primary = companies_dict[primary_key]
        primary.setdefault("aka", [])
        for k in keys_sorted[1:]:
            if k in merged_keys:
                continue
            dupe = companies_dict[k]
            primary["license_count"] += dupe["license_count"]
            primary["aka"].append(dupe["company_name"])
            for county in dupe["counties"]:
                if county not in primary["counties"]:
                    primary["counties"].append(county)
            if not primary["address"] and dupe["address"]:
                primary["address"] = dupe["address"]
            if not primary["city"] and dupe["city"]:
                primary["city"] = dupe["city"]
            merged_keys.add(k)

    for k in merged_keys:
        del companies_dict[k]
    return companies_dict


if __name__ == "__main__":
    electrical = merge_by_phone(load_tdlr("data/tx_tdlr_electrical_raw.json", "Electrical"))
    hvac = merge_by_phone(load_tdlr("data/tx_tdlr_ac_raw.json", "HVAC"))
    plumbing = merge_by_phone(load_tsbpe("data/tx_rmp_raw.csv"))

    print(f"Electrical: {len(electrical)} unique companies")
    print(f"HVAC (A/C Contractor): {len(hvac)} unique companies")
    print(f"Plumbing: {len(plumbing)} unique companies")

    all_companies = list(electrical.values()) + list(hvac.values()) + list(plumbing.values())
    print(f"Combined total: {len(all_companies)}")

    out_path = "data/tx_companies_raw.csv"
    fieldnames = ["company_name", "trade", "city", "state", "county", "aka", "phone", "address",
                  "license_number", "license_source", "license_count"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in all_companies:
            writer.writerow({
                "company_name": c["company_name"],
                "trade": c["trade"],
                "city": c["city"],
                "state": c["state"],
                "county": "; ".join(c["counties"]),
                "aka": "; ".join(c.get("aka", [])),
                "phone": c["phone"],
                "address": c["address"],
                "license_number": c["license_number"],
                "license_source": c["license_source"],
                "license_count": c["license_count"],
            })

    print(f"Written -> {out_path}")
