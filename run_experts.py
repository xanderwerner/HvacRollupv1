"""Search Apollo for HVAC industry experts (COO / GM / VP Operations) in
Maricopa County and write them to the 'Expert List' tab.

Usage:
    python run_experts.py          # default: up to 50 results
    python run_experts.py 25       # stop after 25 net-new rows
"""
import sys
import time

import apollo
import expert_writer

# --- Search parameters ---
TITLES = [
    "Chief Operating Officer",
    "COO",
    "General Manager",
    "VP of Operations",
    "Vice President of Operations",
    "Director of Operations",
    "VP Operations",
]

# Maricopa County cities (covers the whole county)
LOCATIONS = [
    "Phoenix, Arizona, United States",
    "Scottsdale, Arizona, United States",
    "Mesa, Arizona, United States",
    "Chandler, Arizona, United States",
    "Gilbert, Arizona, United States",
    "Glendale, Arizona, United States",
    "Tempe, Arizona, United States",
    "Peoria, Arizona, United States",
    "Surprise, Arizona, United States",
    "Avondale, Arizona, United States",
    "Goodyear, Arizona, United States",
    "Maricopa County, Arizona, United States",
]

KEYWORD_TAGS = ["hvac", "air conditioning", "heating", "plumbing",
                "mechanical contractor", "home services"]

# 25 techs = roughly 30–35 total employees; using 25 as lower bound
EMPLOYEE_RANGES = ["25,10000"]

MIN_YEARS_EXP = 20
PER_PAGE = 25
PAUSE = 0.5  # seconds between API calls


def _fmt_revenue(org: dict) -> str:
    rv = org.get("estimated_num_employees") or 0
    ann = org.get("annual_revenue") or org.get("annual_revenue_printed") or ""
    return str(ann) if ann else ""


def _fmt_employees(org: dict) -> str:
    n = org.get("num_employees") or org.get("estimated_num_employees") or ""
    return str(n) if n else ""


def _city(person: dict) -> str:
    loc = person.get("city") or ""
    st = person.get("state") or ""
    if loc and st:
        return f"{loc}, {st}"
    return loc or st


def run(limit: int) -> None:
    print(f"Searching Apollo for HVAC operations leaders in Maricopa County "
          f"(target: {limit} rows)…")

    collected, page = [], 1
    while len(collected) < limit * 3:  # fetch extra to have room after reveal
        res = apollo.search_people(
            titles=TITLES,
            locations=LOCATIONS,
            keyword_tags=KEYWORD_TAGS,
            employee_ranges=EMPLOYEE_RANGES,
            min_years_exp=MIN_YEARS_EXP,
            page=page,
            per_page=PER_PAGE,
        )
        people = res.get("people", [])
        if not people:
            print(f"  No more results at page {page}.")
            break
        total = res.get("pagination", {}).get("total_entries", "?")
        print(f"  Page {page}: {len(people)} people (total ~{total})")
        collected.extend(people)
        page += 1
        time.sleep(PAUSE)
        if page > 10:  # safety cap: 250 candidates max
            break

    print(f"\nRevealing contact info for {len(collected)} candidates…")
    experts = []
    for stub in collected:
        pid = stub.get("id")
        if not pid:
            continue
        revealed = apollo.reveal_person(pid)
        person = revealed or stub
        time.sleep(PAUSE)

        org = person.get("organization") or {}
        org_id = org.get("id") or person.get("organization_id") or ""

        experts.append({
            "Full Name": person.get("name") or f"{person.get('first_name','')} {person.get('last_name','')}".strip(),
            "Title": (person.get("title") or person.get("headline") or "").strip(),
            "Company Name": org.get("name") or person.get("organization_name") or "",
            "Company Employees": _fmt_employees(org),
            "Company Revenue": _fmt_revenue(org),
            "City": _city(person),
            "Years of Experience": person.get("total_years_of_experience") or "",
            "Email": person.get("email") or "",
            "LinkedIn URL": person.get("linkedin_url") or "",
            "Apollo Person ID": pid,
            "Apollo Org ID": org_id,
        })

    print(f"\nWriting to '{expert_writer.TAB_NAME}'…")
    written = expert_writer.write_experts(experts, limit=limit)
    print(f"\nDone — {len(written)} new row(s) added:")
    for name in written:
        print(f"  + {name}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run(limit)
