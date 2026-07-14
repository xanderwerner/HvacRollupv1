#!/usr/bin/env python3
"""Widen electrical coverage to match how HVAC/Plumbing were actually added to the master:
NO employee-count restriction at ingestion time (ICP tiering is a separate downstream
concern, same as HVAC/Plumbing) -- include every active AZ ROC electrical account, sized
or not. This was the root cause behind the "hardly any electrical companies" gap: the
original build_electrical_rows.py restricted to the 18-50 employee ICP band at ingestion,
which HVAC/Plumbing were never restricted to.
"""
import json
import re

raw_roc = {r["accountId"]: r for r in (json.loads(l) for l in open("data/roc_electrical_raw.jsonl"))}


def electrical_license(account_id):
    for ld in (raw_roc.get(account_id, {}).get("licenseData") or []):
        sub = (ld.get("subType") or "")
        if ld.get("status") == "Active" and ("electric" in sub.lower() or sub.strip().upper().startswith(("C-11", "CR-11", "L-11", "R-11"))):
            return ld
    return {}


merged = [json.loads(l) for l in open("data/elec_merged_sized_v2.jsonl")]

# recover which account_ids the original 87 (18-50 band) came from, to exclude re-adding them
already_added = {m["account_id"] for m in merged
                  if m.get("final_employees") is not None and 18 <= m["final_employees"] <= 50}
print(f"already in master (18-50 band): {len(already_added)}")

new_candidates = [m for m in merged if m["account_id"] not in already_added]
print(f"new candidates to add (any size, including unsized): {len(new_candidates)}")


def clean_dba(dba):
    if not dba:
        return None
    return re.sub(r"^DBA\s*:\s*", "", dba).strip()


def strip_tags(name):
    return re.sub(r"\s*\([^)]*\)\s*", "", name).strip()


def pick_owner(m):
    if m.get("zi_owner"):
        return m["zi_owner"], m.get("zi_owner_title") or "Owner", "ZoomInfo free search"
    contacts = m.get("roc_contacts") or []
    owner_tagged = [c["contactName"] for c in contacts if "Owner" in c.get("contactName", "") and "Qualifying" not in c.get("contactName", "")]
    if owner_tagged:
        return strip_tags(owner_tagged[0]).title(), "Owner", "AZ ROC (tagged Owner)"
    qp = [c["contactName"] for c in contacts if "Qualifying Party" in c.get("contactName", "")]
    if qp:
        return strip_tags(qp[0]).title(), "Qualifying Party (unverified as true owner)", "AZ ROC (qualifying party)"
    return m["roc_name"], None, "ROC account name (individual licensee)"


def city_from_address(addr):
    return (addr or "").split(",")[0].strip()


rows_out = []
seen_names = set()
for i, m in enumerate(new_candidates, start=994):
    dba = clean_dba(m.get("roc_dba"))
    company_name = dba or m["roc_name"]
    name_key = re.sub(r"[^A-Z0-9]", "", company_name.upper())
    if name_key in seen_names:
        continue  # skip exact-name dupes (e.g. the one coincidental ROC duplicate found)
    seen_names.add(name_key)

    rid = f"C{i}"
    owner_name, owner_title, owner_src = pick_owner(m)
    elec_lic = electrical_license(m["account_id"])
    city = city_from_address(m.get("roc_address"))
    emp = m.get("final_employees")
    rev = m.get("final_revenue")
    rev = int(rev) if rev else None
    ebitda = int(rev * 0.12) if rev else None
    phone = m.get("roc_phone") or ""
    if phone and not phone.startswith("("):
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            phone = f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
    domain = m.get("final_domain") or ""
    flags = []
    if owner_title == "Qualifying Party (unverified as true owner)":
        flags.append("QP may be hired qualifier - verify owner")
    if m.get("size_source") == "apollo(via places, verified)":
        flags.append("Domain/employee size auto-matched via company-name search (Places->Apollo) - low residual mismatch risk, verify identity before high-stakes outreach")
    if emp is None:
        flags.append("Not sized yet -- no ZI/Places/Apollo match found during electrical sweep")
    data_check = "; ".join(flags)

    row = [
        rid, company_name, "Electrical", city, "AZ",
        owner_name or "", owner_title or "", "", "", "",
        phone, emp if emp is not None else "", rev or "", ebitda or "", "",
        data_check, "", owner_src, "", "",
        "", "", domain, "",
        elec_lic.get("licenseNo", m.get("roc_license_no", "")), elec_lic.get("subType", m.get("roc_license_subtype", "")), "", "",
        "Added 2026-07-13 (widened sweep): electrical-coverage gap-fill, no employee-count restriction at ingestion (matches HVAC/Plumbing inclusion pattern)",
    ]
    rows_out.append(row)

with open("data/electrical_rows_to_add_v2.json", "w") as f:
    json.dump(rows_out, f, indent=1)

print(f"Built {len(rows_out)} new electrical rows, IDs C994-C{993+len(rows_out)}")
sized = sum(1 for r in rows_out if r[11] != "")
print(f"of these, {sized} have a known employee count, {len(rows_out)-sized} are unsized")
