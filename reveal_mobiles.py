"""Reveal owner mobile phones for all existing Organic List rows via Apollo,
using webhook.site as a zero-infrastructure callback receiver.

Flow:
  1. Create a webhook.site inbox (free, no account needed)
  2. For each row: org enrich -> find owner person id -> people/match with
     reveal_phone_number + webhook_url
  3. Poll webhook.site API until all callbacks arrive (or timeout)
  4. Match each callback back to the right row by person id
  5. Write Owner Direct Mobile into the Google Sheet

Run:  python reveal_mobiles.py [--dry]
"""
import json
import ssl
import sys
import time
import urllib.request
import urllib.parse

import gspread
from google.oauth2.service_account import Credentials

import apollo
import config

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_SKIP_NAMES = {"full legal or trade name", "desert air hvac"}

OWNER_TITLES = ["owner", "president", "ceo", "founder", "general manager",
                "partner", "principal"]


def _http(url, body=None, method=None):
    data = json.dumps(body).encode() if body else None
    m = method or ("POST" if body else "GET")
    req = urllib.request.Request(url, data=data, method=m)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20, context=_CTX) as r:
        return json.loads(r.read().decode())


def wh_create():
    d = _http("https://webhook.site/token", body={})
    return d["uuid"]


def wh_poll(uuid, since_page=1):
    """Return list of raw request bodies posted to this inbox."""
    url = f"https://webhook.site/token/{uuid}/requests?page={since_page}&sorting=newest"
    d = _http(url)
    return d.get("data", [])


def _domain(website):
    return website.split("://")[-1].split("/")[0].replace("www.", "").strip()


def _fmt_phone(raw):
    if not raw:
        return ""
    d = "".join(ch for ch in raw if ch.isdigit())
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return f"({d[0:3]}) {d[3:6]}-{d[6:]}"
    return d or ""


def _worksheet():
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(
        config.GSHEET_ID).worksheet(config.GSHEET_TAB)


def run(dry=False):
    ws = _worksheet()
    vals = ws.get_all_values()
    hrow = next(i for i, r in enumerate(vals) if "Company Name" in r)
    H = {h: j for j, h in enumerate(vals[hrow]) if h}

    def cell(row, h):
        j = H.get(h)
        return (row[j] if j is not None and j < len(row) else "").strip()

    # collect rows that need a phone reveal
    targets = []   # {row_idx(1-based), company, domain, owner_name, owner_email}
    for i in range(hrow + 1, len(vals)):
        row = vals[i]
        name = cell(row, "Company Name")
        if not name or name.lower() in _SKIP_NAMES:
            continue
        website = cell(row, "Website")
        if not website:
            continue
        if cell(row, "Owner Direct Mobile").strip():
            continue   # already has a mobile
        targets.append({
            "row": i + 1,
            "company": name,
            "domain": _domain(website),
            "owner_name": cell(row, "Owner Name"),
            "owner_email": cell(row, "Owner Email"),
        })

    print(f"Rows needing phone reveal: {len(targets)}\n")

    # --- phase 1: resolve person ids from Apollo ---
    print("Phase 1 — resolving Apollo person IDs...")
    reveals = []   # {person_id, row, company, ...}
    for t in targets:
        org = apollo.enrich_org(t["domain"])
        if not org or not org.get("id"):
            print(f"  {t['company'][:36]:36} no org in Apollo")
            continue
        time.sleep(0.3)

        # prefer owner by name match if we already have it
        stub = None
        if t["owner_name"]:
            res = apollo._req("POST", "/mixed_people/api_search", body={
                "organization_ids": [org["id"]],
                "person_titles": OWNER_TITLES,
                "per_page": 5})
            for p in res.get("people", []):
                if (p.get("name") or "").lower() == t["owner_name"].lower():
                    stub = p
                    break
            if not stub and res.get("people"):
                stub = res["people"][0]
        else:
            stub = apollo.find_owner(org["id"])

        if not stub or not stub.get("id"):
            print(f"  {t['company'][:36]:36} no owner person found")
            continue

        reveals.append({**t, "person_id": stub["id"],
                        "person_name": stub.get("name", t["owner_name"])})
        print(f"  {t['company'][:36]:36} id={stub['id'][:12]}...  {stub.get('name','')}")
        time.sleep(0.3)

    if not reveals:
        print("Nothing to reveal — stopping.")
        return

    # --- phase 2: create webhook and fire reveals ---
    print(f"\nPhase 2 — creating webhook.site inbox...")
    uuid = wh_create()
    webhook_url = f"https://webhook.site/{uuid}"
    print(f"  Inbox: {webhook_url}\n")

    print(f"Phase 3 — requesting {len(reveals)} phone reveals...")
    by_person_id = {}
    for rv in reveals:
        r = apollo._req("POST", "/people/match", body={
            "id": rv["person_id"],
            "reveal_phone_number": True,
            "webhook_url": webhook_url,
        })
        status = r.get("error") or r.get("status", "queued")
        print(f"  {rv['company'][:36]:36} {status}")
        by_person_id[rv["person_id"]] = rv
        time.sleep(0.4)

    # --- phase 3: poll for callbacks ---
    print(f"\nPhase 4 — polling webhook.site for callbacks (up to 90s)...")
    received = {}   # person_id -> phone
    deadline = time.time() + 90
    while time.time() < deadline and len(received) < len(reveals):
        time.sleep(4)
        try:
            items = wh_poll(uuid)
        except Exception as e:
            print(f"  poll error: {e}")
            continue
        for item in items:
            try:
                body = json.loads(item.get("content", "{}"))
            except Exception:
                continue
            person = body.get("person") or {}
            pid = person.get("id")
            if not pid or pid in received:
                continue
            phones = person.get("phone_numbers") or []
            mobile = ""
            # prefer type=mobile; fall back to first number
            for ph in phones:
                if ph.get("type") == "mobile":
                    mobile = ph.get("sanitized_number") or ph.get("raw_number") or ""
                    break
            if not mobile and phones:
                mobile = phones[0].get("sanitized_number") or phones[0].get("raw_number") or ""
            received[pid] = _fmt_phone(mobile)
            name = by_person_id.get(pid, {}).get("company", pid)
            print(f"  callback: {name[:36]:36} -> {received[pid] or '(no number)'}")
        elapsed = int(time.time() - deadline + 90)
        remaining = len(reveals) - len(received)
        if remaining > 0:
            print(f"  {len(received)}/{len(reveals)} received ({elapsed}s elapsed, waiting...)  ",
                  end="\r", flush=True)

    print(f"\n\nCallbacks received: {len(received)}/{len(reveals)}")

    # --- phase 4: write to sheet ---
    cells = []
    for pid, phone in received.items():
        if not phone:
            continue
        rv = by_person_id.get(pid, {})
        row_idx = rv.get("row")
        if not row_idx:
            continue
        col = H.get("Owner Direct Mobile")
        if col is None:
            print("Warning: 'Owner Direct Mobile' column not found in sheet!")
            continue
        cells.append(gspread.Cell(row_idx, col + 1, phone))
        print(f"  queued: {rv['company'][:36]:36} {phone} -> row {row_idx}")

    print(f"\n{len(cells)} mobile(s) to write.")
    if dry:
        print("DRY RUN — nothing written.")
        return
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
        print("Written to sheet.")
    else:
        print("No phone numbers came back from Apollo for these owners.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
