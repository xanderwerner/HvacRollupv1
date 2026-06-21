"""Enrich existing Organic List rows in the Google Sheet with Apollo data.

For each lead that has a website but no owner yet:
  domain -> Apollo (org employees/revenue/founded + owner name/title/email/LinkedIn)
  -> update that row's cells in place (only the cells we have data for).

Run:  python enrich.py [N]      (N = max rows to enrich, default all)
"""
import sys

import gspread
from google.oauth2.service_account import Credentials

import apollo
import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_TITLE_MAP = {"owner": "Owner", "president": "President", "founder": "Founder",
              "principal": "Principal", "partner": "Partner"}
_REV_BANDS = [(500_000, "Under $500K"), (1_000_000, "$500K–$1M"),
              (3_000_000, "$1M–$3M"), (5_000_000, "$3M–$5M"),
              (10_000_000, "$5M–$10M")]


def _title(t: str) -> str:
    if not t:
        return ""
    tl = t.lower()
    for k, v in _TITLE_MAP.items():
        if k in tl:
            return v
    return "Other"


def _rev_band(rev) -> str:
    if not rev:
        return ""
    for thr, label in _REV_BANDS:
        if rev < thr:
            return label
    return "Over $10M"


def _worksheet():
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(
        config.GSHEET_ID).worksheet(config.GSHEET_TAB)


def enrich_sheet(limit: int = None) -> int:
    ws = _worksheet()
    vals = ws.get_all_values()
    hrow = next(i for i, row in enumerate(vals) if "Company Name" in row)
    H = {h: j for j, h in enumerate(vals[hrow]) if h}

    def cell(row, header):
        j = H.get(header)
        return row[j] if j is not None and j < len(row) else ""

    cells, done = [], 0
    for i in range(hrow + 1, len(vals)):
        row = vals[i]
        name = cell(row, "Company Name").strip()
        website = cell(row, "Website").strip()
        if not name or not website:
            continue
        if cell(row, "Owner Name").strip():          # already enriched
            continue
        domain = website.split("://")[-1].split("/")[0].replace("www.", "")
        print(f"  · {name[:34]:34} ({domain}) ...", end="", flush=True)

        res = apollo.enrich_company(domain)
        org, owner = res["org"] or {}, res["owner"] or {}
        updates, notes = {}, []

        if org.get("estimated_num_employees"):
            updates["Est. # of Employees"] = org["estimated_num_employees"]
        if org.get("annual_revenue"):
            updates["ZoomInfo Rev. Estimate"] = _rev_band(org["annual_revenue"])
        if org.get("founded_year"):
            updates["Years in Business"] = f"{2026 - int(org['founded_year'])} years"

        if owner:
            if owner.get("name"):
                updates["Owner Name"] = owner["name"]
            if owner.get("title"):
                updates["Owner Title"] = _title(owner["title"])
            if owner.get("email"):
                updates["Owner Email"] = owner["email"]
            if owner.get("linkedin_url"):
                updates["Owner LinkedIn"] = owner["linkedin_url"]
            updates["Research Stage"] = "In Progress"
            notes.append(f"Apollo: owner {owner.get('name')} "
                         f"<{owner.get('email') or 'email n/a'}>; mobile pending (webhook).")
            print(f" owner: {owner.get('name')}")
        else:
            notes.append("Apollo: no owner record found.")
            print(" no owner in Apollo")

        if org.get("estimated_num_employees"):
            rp = org.get("annual_revenue_printed")
            notes.append(f"Apollo size: {org['estimated_num_employees']} emp"
                         + (f", rev {rp}" if rp else "") + ".")

        prev = cell(row, "Notes").strip()
        updates["Notes"] = (prev + " | " if prev else "") + " ".join(notes)

        for header, val in updates.items():
            if header in H:
                cells.append(gspread.Cell(i + 1, H[header] + 1, val))

        done += 1
        if limit and done >= limit:
            break

    if cells:
        ws.update_cells(cells, value_input_option="USER_ENTERED")
    return done


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Apollo enrichment -> Google Sheet (limit={n or 'all'})\n")
    count = enrich_sheet(limit=n)
    print(f"\nenriched {count} rows.")
