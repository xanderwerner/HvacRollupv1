#!/usr/bin/env python3
import json
import re

raw_roc = {r["accountId"]: r for r in (json.loads(l) for l in open("data/roc_electrical_raw.jsonl"))}

def electrical_license(account_id):
    """Pick the Active electrical-classified license entry, not just licenseData[0]
    (companies often hold multiple trade licenses)."""
    for ld in (raw_roc.get(account_id, {}).get("licenseData") or []):
        sub = (ld.get("subType") or "")
        if ld.get("status") == "Active" and ("electric" in sub.lower() or sub.strip().upper().startswith(("C-11", "CR-11", "L-11", "R-11"))):
            return ld
    return {}

merged = [json.loads(l) for l in open("data/elec_merged_sized_v2.jsonl")]
qualified = [m for m in merged if m.get("final_employees") is not None and 18 <= m["final_employees"] <= 50]

def clean_dba(dba):
    if not dba:
        return None
    return re.sub(r"^DBA\s*:\s*", "", dba).strip()

def strip_tags(name):
    # strips ANY trailing parenthetical tag(s), e.g. "(Officer;Qualifying Party)"
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
for i, m in enumerate(qualified, start=907):
    rid = f"C{i}"
    dba = clean_dba(m.get("roc_dba"))
    company_name = dba or m["roc_name"]
    owner_name, owner_title, owner_src = pick_owner(m)
    elec_lic = electrical_license(m["account_id"])
    city = city_from_address(m.get("roc_address"))
    emp = m["final_employees"]
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
    if m["size_source"] == "apollo(via places, verified)":
        flags.append("Domain/employee size auto-matched via company-name search (Places->Apollo) - low residual mismatch risk, verify identity before high-stakes outreach")
    data_check = "; ".join(flags)

    row = [
        rid, company_name, "Electrical", city, "AZ",
        owner_name or "", owner_title or "", "", "", "",  # Owner Name, Title, Cell, DNC, Email
        phone, emp, rev or "", ebitda or "", "",  # Office Phone, Employees, Revenue, EBITDA, Founded
        data_check, "", owner_src, "", "",  # Data Check, Cell Source, Owner Found Via, Owner Source(orig), Co-Owners
        "", "", domain, "",  # LinkedIn, Website, Domain, Other Locations
        elec_lic.get("licenseNo", m.get("roc_license_no", "")), elec_lic.get("subType", m.get("roc_license_subtype", "")), "", "",  # License#, Class, Rating, Reviews
        f"Added 2026-07-13: electrical-coverage gap-fill from AZ ROC sweep (size via {m['size_source']})",
    ]
    rows_out.append(row)

with open("data/electrical_rows_to_add.json", "w") as f:
    json.dump(rows_out, f, indent=1)

print(f"Built {len(rows_out)} new electrical rows, IDs C907-C{906+len(rows_out)}")
print("Sample row:", rows_out[0])