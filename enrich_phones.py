"""Enrich the existing Organic List rows with a CALLABLE COMPANY PHONE (+ fill
employee count / revenue / owner where blank).

Phone strategy (the owner's *direct mobile* needs Apollo's async webhook flow —
not built yet; see notes). What we CAN get inline today:
  1. Apollo  organizations/enrich  -> company main line  (free, inline)
  2. fallback: Google Places text-search -> place_details -> formatted_phone

Writes the number into a dedicated "Company Phone" column (created at the end of
the header row if missing, so existing dropdowns/columns are untouched). The
"Owner Direct Mobile" column is left for the future webhook flow.

Run:  python enrich_phones.py            (dry run -> python enrich_phones.py --dry)
"""
import sys
import time

import gspread
from google.oauth2.service_account import Credentials

import apollo
import config
import places

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PHONE_COL = "Company Phone"
_TITLE_MAP = {"owner": "Owner", "president": "President", "founder": "Founder",
              "principal": "Principal", "partner": "Partner"}
_REV_BANDS = [(500_000, "Under $500K"), (1_000_000, "$500K–$1M"),
              (3_000_000, "$1M–$3M"), (5_000_000, "$3M–$5M"),
              (10_000_000, "$5M–$10M")]
# rows that are the template / placeholder example, not real prospects
_SKIP_NAMES = {"full legal or trade name", "desert air hvac"}


def _title(t):
    tl = (t or "").lower()
    for k, v in _TITLE_MAP.items():
        if k in tl:
            return v
    return "Other" if t else ""


def _rev_band(rev):
    if not rev:
        return ""
    for thr, label in _REV_BANDS:
        if rev < thr:
            return label
    return "Over $10M"


def _domain(website):
    return website.split("://")[-1].split("/")[0].replace("www.", "").strip()


def _fmt_phone(raw):
    """Normalize to (AAA) PPP-NNNN so the leading '+' can't trip Sheets' formula
    parser. Non-US / odd lengths are returned digit-cleaned without a leading +."""
    if not raw:
        return ""
    d = "".join(ch for ch in raw if ch.isdigit())
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return f"({d[0:3]}) {d[3:6]}-{d[6:]}"
    return d or ""


def _places_phone(name, city):
    """Find this company on Google Places and return its formatted phone."""
    try:
        q = f"{name} {city} AZ".strip()
        results = places.text_search(q)
        if not results:
            return ""
        pid = results[0].get("place_id")
        if not pid:
            return ""
        return places.place_details(pid).get("formatted_phone_number", "")
    except Exception:
        return ""


def _worksheet():
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(
        config.GSHEET_ID).worksheet(config.GSHEET_TAB)


def run(dry=False):
    ws = _worksheet()
    vals = ws.get_all_values()
    hrow = next(i for i, r in enumerate(vals) if "Company Name" in r)
    headers = vals[hrow]
    H = {h: j for j, h in enumerate(headers) if h}

    # ensure a Company Phone column exists (appended at the end, non-destructive)
    if PHONE_COL not in H:
        new_col = len(headers)  # 0-based index of the new column
        H[PHONE_COL] = new_col
        if not dry:
            if ws.col_count < new_col + 1:        # widen grid if needed
                ws.add_cols(new_col + 1 - ws.col_count)
            ws.update_cell(hrow + 1, new_col + 1, PHONE_COL)
        print(f"+ added '{PHONE_COL}' column at position {new_col + 1}")

    def cell(row, h):
        j = H.get(h)
        return (row[j] if j is not None and j < len(row) else "").strip()

    cells = []
    n = phones = owners = 0
    for i in range(hrow + 1, len(vals)):
        row = vals[i]
        name = cell(row, "Company Name")
        if not name or name.lower() in _SKIP_NAMES:
            continue
        website = cell(row, "Website")
        if not website:
            continue
        n += 1
        city = cell(row, "City")
        org = apollo.enrich_org(_domain(website)) if website else None
        upd = {}

        # --- phone: Apollo company line, else Google Places ---
        phone = ""
        if org:
            phone = org.get("phone") or (org.get("primary_phone") or {}).get("number") or ""
        src = "apollo"
        if not phone:
            phone = _places_phone(name, city)
            src = "places"
        phone = _fmt_phone(phone)
        cur = cell(row, PHONE_COL)
        # write if empty OR previously corrupted ("#ERROR!" from a leading '+')
        if phone and (not cur or cur.startswith("#")):
            upd[PHONE_COL] = phone
            phones += 1

        # --- company facts (only fill blanks) ---
        if org:
            if org.get("estimated_num_employees") and not cell(row, "Est. # of Employees"):
                upd["Est. # of Employees"] = org["estimated_num_employees"]
            if org.get("annual_revenue") and not cell(row, "ZoomInfo Rev. Estimate"):
                upd["ZoomInfo Rev. Estimate"] = _rev_band(org["annual_revenue"])
            if org.get("founded_year") and not cell(row, "Years in Business"):
                upd["Years in Business"] = f"{2026 - int(org['founded_year'])} years"

            # --- owner (only if row has none yet) ---
            if not cell(row, "Owner Name") and org.get("id"):
                time.sleep(0.3)
                stub = apollo.find_owner(org["id"])
                if stub and stub.get("id"):
                    time.sleep(0.3)
                    p = apollo.reveal_person(stub["id"]) or stub
                    if p.get("name"):
                        upd["Owner Name"] = p["name"]
                        owners += 1
                    if p.get("title"):
                        upd["Owner Title"] = _title(p["title"])
                    if p.get("email"):
                        upd["Owner Email"] = p["email"]
                    if p.get("linkedin_url"):
                        upd["Owner LinkedIn"] = p["linkedin_url"]

        flag = "" if phone else "  (no phone found)"
        print(f"  {name[:34]:34} {phone[:17]:17} [{src if phone else '—'}]{flag}")
        for h, v in upd.items():
            cells.append(gspread.Cell(i + 1, H[h] + 1, v))
        time.sleep(0.3)

    print(f"\n{n} companies | phones: {phones} | new owners: {owners} | "
          f"cell updates queued: {len(cells)}")
    if dry:
        print("DRY RUN — nothing written.")
        return
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
        print(f"wrote {len(cells)} cells to the sheet.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
