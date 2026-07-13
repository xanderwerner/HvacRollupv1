"""Build a deduped Texas company name list from TDLR (electrical + A/C) and TSBPE (plumbing) data.

No sizing/ICP/enrichment yet -- just company-level dedup, ready for the next (sizing) pass.
"""
import csv
import json
import re
from datetime import date

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


def load_tdlr(path, trade):
    rows = json.load(open(path))
    companies = {}
    for r in rows:
        exp = parse_exp(r.get("license_expiration_date_mmddccyy"))
        if not exp or exp < TODAY:
            continue  # not current
        raw_name = r.get("business_name") or r.get("owner_name")
        if not raw_name:
            continue
        key = (normalize_name(raw_name), r.get("business_county") or r.get("mailing_address_county") or "")
        phone = r.get("business_telephone") or r.get("owner_telephone") or ""
        city_state_zip = r.get("business_city_state_zip") or r.get("mailing_address_city_state_zip") or ""
        city = city_state_zip.rsplit(" TX", 1)[0].strip() if " TX" in city_state_zip else ""
        addr = r.get("business_address_line1") or r.get("mailing_address_line1") or ""
        county = r.get("business_county") or r.get("mailing_address_county") or ""

        existing = companies.get(key)
        if existing:
            existing["license_count"] += 1
            if not existing["phone"] and phone:
                existing["phone"] = phone
            if not existing["address"] and addr:
                existing["address"] = addr
            if not existing["city"] and city:
                existing["city"] = city
        else:
            companies[key] = {
                "company_name": raw_name.strip(),
                "trade": trade,
                "city": city,
                "state": "TX",
                "county": county,
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
            key = (normalize_name(raw_name), r.get("COUNTY") or "")
            phone = r.get("PHONE") or ""
            city = r.get("CITY") or ""
            addr = r.get("ADDR1") or ""

            existing = companies.get(key)
            if existing:
                existing["license_count"] += 1
                if not existing["phone"] and phone:
                    existing["phone"] = phone
            else:
                companies[key] = {
                    "company_name": raw_name,
                    "trade": "Plumbing",
                    "city": city,
                    "state": "TX",
                    "county": r.get("COUNTY") or "",
                    "phone": phone,
                    "address": addr,
                    "license_number": r.get("LICENSE_NBR", ""),
                    "license_source": "TSBPE",
                    "license_count": 1,
                }
    return companies


if __name__ == "__main__":
    electrical = load_tdlr("data/tx_tdlr_electrical_raw.json", "Electrical")
    hvac = load_tdlr("data/tx_tdlr_ac_raw.json", "HVAC")
    plumbing = load_tsbpe("data/tx_rmp_raw.csv")

    print(f"Electrical: {len(electrical)} unique companies (from TDLR license rows)")
    print(f"HVAC (A/C Contractor): {len(hvac)} unique companies (from TDLR license rows)")
    print(f"Plumbing: {len(plumbing)} unique companies (from TSBPE)")

    all_companies = list(electrical.values()) + list(hvac.values()) + list(plumbing.values())
    print(f"Combined total (pre cross-trade dedup): {len(all_companies)}")

    out_path = "data/tx_companies_raw.csv"
    fieldnames = ["company_name", "trade", "city", "state", "county", "phone", "address",
                  "license_number", "license_source", "license_count"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in all_companies:
            writer.writerow(c)

    print(f"Written -> {out_path}")
