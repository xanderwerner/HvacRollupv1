"""Apollo as a SOURCING tool — find 10+ employee trades owners in Phoenix metro,
reveal their contact info, and hand back ready-to-write Organic List rows.

Buy box (updated): 10+ employees, no upper ceiling. Apollo's
organization_num_employees_ranges filter enforces the size at search time, so
every sourced lead is correctly sized AND comes with an owner contact.
"""
import datetime
import time

import apollo
import config

EMP_RANGES = ["11,20", "21,50", "51,100", "101,200", "201,500", "501,1000", "1001,5000"]
TITLES = ["owner", "president", "ceo", "founder", "general manager", "partner", "principal"]
TRADE_TAGS = {"HVAC": ["hvac"], "Plumbing": ["plumbing"], "Electrical": ["electrical"]}
METRO = ["Phoenix, Arizona", "Scottsdale, Arizona", "Mesa, Arizona", "Tempe, Arizona",
         "Chandler, Arizona", "Gilbert, Arizona", "Glendale, Arizona", "Peoria, Arizona",
         "Surprise, Arizona", "Avondale, Arizona", "Goodyear, Arizona"]
METRO_CITIES = {c.split(",")[0].strip().lower() for c in METRO}

_TITLE_MAP = {"owner": "Owner", "president": "President", "founder": "Founder",
              "principal": "Principal", "partner": "Partner"}
_REV_BANDS = [(500_000, "Under $500K"), (1_000_000, "$500K–$1M"), (3_000_000, "$1M–$3M"),
              (5_000_000, "$3M–$5M"), (10_000_000, "$5M–$10M")]


def _title(t):
    tl = (t or "").lower()
    for k, v in _TITLE_MAP.items():
        if k in tl:
            return v
    return "Other"


def _rev_band(rev):
    if not rev:
        return ""
    for thr, label in _REV_BANDS:
        if rev < thr:
            return label
    return "Over $10M"


def _clean_url(u):
    if not u:
        return ""
    u = u.split("://")[-1]
    return u[4:].rstrip("/") if u.startswith("www.") else u.rstrip("/")


def search(trade, per_page=25, page=1):
    res = apollo._req("POST", "/mixed_people/api_search", body={
        "person_titles": TITLES, "organization_locations": METRO,
        "organization_num_employees_ranges": EMP_RANGES,
        "q_organization_keyword_tags": TRADE_TAGS[trade],
        "per_page": per_page, "page": page})
    return res.get("people", []) if isinstance(res, dict) else []


def _row_from_person(person, trade, date_str):
    org = person.get("organization") or {}
    emp = org.get("estimated_num_employees")
    if not emp or emp < config.BUY_BOX_MIN_EMPLOYEES:
        return None
    city = org.get("city") or person.get("city") or ""
    if city and city.strip().lower() not in METRO_CITIES:
        # keep AZ but flag non-core-metro in notes rather than drop
        pass
    founded = org.get("founded_year")
    note = (f"Apollo-sourced (10+ emp buy box) {date_str}. "
            f"Owner {person.get('name')} <{person.get('email') or 'email n/a'}>; "
            f"mobile pending (webhook). Apollo size: {emp} emp"
            + (f", rev {org.get('annual_revenue_printed')}" if org.get('annual_revenue_printed') else "") + ".")
    return {
        "Researched By": "", "Research Stage": "In Progress",
        "Discovery Source": "Apollo", "Ad Platform Seen On": "N/A",
        "Date Added": date_str,
        "Company Name": org.get("name", ""), "Trade Type": trade,
        "City": city, "Business Address": org.get("raw_address") or org.get("street_address") or "",
        "Website": _clean_url(org.get("website_url") or org.get("primary_domain")),
        "Years in Business": f"{2026 - int(founded)} years" if founded else "",
        "Est. # of Employees": emp,
        "ZoomInfo Rev. Estimate": _rev_band(org.get("annual_revenue")),
        "Running Ads": "Unknown",
        "Owner Name": person.get("name", ""), "Owner Title": _title(person.get("title")),
        "Owner Email": person.get("email", ""), "Owner LinkedIn": person.get("linkedin_url", ""),
        "Owner Age Estimate": "Unknown", "ZoomInfo Intent Signal": "Not checked",
        "Ever Listed for Sale": "Unknown", "GM / Ops Job Posting": "Unknown",
        "Succession Gap": "Unknown",
        "ROC Checked": "No", "ACC Checked": "No", "Google Checked": "No",
        "ZoomInfo Checked": "No", "LinkedIn Checked": "No", "BBB / Reviews Checked": "No",
        "PE / Roll-up Check": "Unknown",
        "Buy Box Fit": "Strong" if emp >= config.BUY_BOX_MIN_EMPLOYEES else "Possible",
        "Priority Tier": "B — email first",   # A needs a confirmed mobile
        "Ready to Hand Off": "Not yet",       # email yes, mobile pending
        "Notes": note,
    }


def source(trades=("HVAC", "Plumbing", "Electrical"), target=12, reveal_cap=30,
           per_trade=25):
    """Search + reveal until `target` qualifying rows (or `reveal_cap` reveals)."""
    date_str = datetime.date.today().strftime("%m/%d/%y")
    rows, seen, reveals = [], set(), 0
    for trade in trades:
        people = search(trade, per_page=per_trade)
        for stub in people:
            if len(rows) >= target or reveals >= reveal_cap:
                break
            org = stub.get("organization") or {}
            cname = (org.get("name") or "").strip().lower()
            if not cname or cname in seen:
                continue
            seen.add(cname)
            person = apollo.reveal_person(stub["id"]) or stub
            reveals += 1
            time.sleep(0.4)
            row = _row_from_person(person, trade, date_str)
            if row and row["Company Name"]:
                rows.append(row)
                print(f"  + {row['Company Name'][:32]:32} | {row['Est. # of Employees']:>3} emp "
                      f"| {row['Owner Name']} <{row['Owner Email'] or 'no email'}>")
        if len(rows) >= target:
            break
    print(f"\n  sourced {len(rows)} qualifying leads from {reveals} reveals")
    return rows
