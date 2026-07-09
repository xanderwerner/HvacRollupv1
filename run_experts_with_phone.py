"""Search Apollo for HVAC ops leaders in AZ — write ONLY rows with a verified phone.

One API call per person: reveal email (sync) + fire phone webhook simultaneously.
Wait once for all callbacks. Total runtime ~2-3 minutes for 40 targets.

Run:  python3 run_experts_with_phone.py          # default: 40 rows
      python3 run_experts_with_phone.py 20
"""
import json
import ssl
import subprocess
import sys
import time
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

import apollo
import config
import expert_writer

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CALLBACKS_FILE = Path(__file__).parent / "phone_callbacks.jsonl"
WEBHOOK_PORT = 8756
WEBHOOK_WAIT = 100  # seconds

TITLES = [
    "Chief Operating Officer", "COO",
    "Vice President of Operations", "VP of Operations", "VP Operations",
    "General Manager", "Director of Operations",
]
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
    "Arizona, United States",
]
KEYWORD_TAGS = ["hvac", "air conditioning", "heating", "plumbing",
                "mechanical contractor", "home services"]
EMPLOYEE_RANGES = ["25,10000"]
MIN_YEARS_EXP = 20
PER_PAGE = 25
PAUSE = 0.15


def _fmt_phone(raw):
    if not raw:
        return ""
    d = "".join(c for c in raw if c.isdigit())
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return d or ""


def _existing_ids(ws) -> set:
    vals = ws.get_all_values()
    if not vals:
        return set()
    H = {h: i for i, h in enumerate(vals[0]) if h}
    col = H.get("Apollo Person ID")
    if col is None:
        return set()
    return {row[col].strip() for row in vals[1:] if col < len(row) and row[col].strip()}


def _start_tunnel(port):
    CALLBACKS_FILE.write_text("")
    server = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "webhook_server.py"), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    tunnel = subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
         "-R", f"80:localhost:{port}", "serveo.net"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    public_url = None
    deadline = time.time() + 30
    import re
    while time.time() < deadline:
        try:
            line = tunnel.stdout.readline().decode("utf-8", "replace").strip()
        except Exception:
            time.sleep(1)
            continue
        # strip ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if clean:
            print(f"  tunnel: {clean}")
        # match forwarding URLs: https://xxx.serveo.net or https://xxx.serveousercontent.com
        m = re.search(r'https://[\w\-]+\.serveo(?:usercontent)?\.(?:net|com)\b', clean)
        if m:
            public_url = m.group(0)
            break
    return server, tunnel, public_url


def run(limit=40):
    creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    ws = gspread.authorize(creds).open_by_key(config.GSHEET_ID).worksheet(expert_writer.TAB_NAME)
    existing_ids = _existing_ids(ws)
    print(f"Existing rows: {len(existing_ids)}")

    # ── 1. Collect fresh candidates (just stubs, no reveal yet) ──────────────
    print("Fetching candidates from Apollo…")
    fresh, page = [], 1
    while len(fresh) < limit * 5:  # fetch 5x target to account for phone hit rate
        res = apollo.search_people(
            titles=TITLES, locations=LOCATIONS,
            keyword_tags=KEYWORD_TAGS, employee_ranges=EMPLOYEE_RANGES,
            min_years_exp=MIN_YEARS_EXP, page=page, per_page=PER_PAGE,
        )
        stubs = res.get("people", [])
        if not stubs:
            break
        new = [s for s in stubs if s.get("id") and s["id"] not in existing_ids]
        fresh.extend(new)
        print(f"  page {page}: {len(new)} new (total fresh: {len(fresh)})")
        page += 1
        time.sleep(PAUSE)
        if page > 10:
            break

    if not fresh:
        print("No new candidates found.")
        return

    # ── 2. Start tunnel ───────────────────────────────────────────────────────
    print("\nStarting webhook tunnel…")
    server_proc, tunnel_proc, public_url = _start_tunnel(WEBHOOK_PORT)
    if not public_url:
        print("ERROR: could not get serveo.net URL. Aborting.")
        if server_proc: server_proc.terminate()
        if tunnel_proc: tunnel_proc.terminate()
        return
    print(f"  {public_url}")

    # ── 3. One call per person: email (sync) + phone webhook (async) ──────────
    print(f"\nRevealing {len(fresh)} candidates (email + phone in one call)…")
    revealed = {}  # pid -> person dict
    for stub in fresh:
        pid = stub.get("id")
        if not pid:
            continue
        res = apollo._req("POST", "/people/match", body={
            "id": pid,
            "reveal_personal_emails": True,
            "reveal_phone_number": True,
            "webhook_url": public_url,
        })
        person = res.get("person") or stub
        revealed[pid] = person
        org = person.get("organization") or {}
        name = (person.get("name") or "").strip() or "…"
        email_tag = "✓" if person.get("email") else "✗"
        print(f"  {name[:30]:30} {(org.get('name') or '')[:26]:26} email={email_tag}")
        time.sleep(PAUSE)

    # ── 4. Poll once for all phone callbacks ──────────────────────────────────
    print(f"\nWaiting up to {WEBHOOK_WAIT}s for phone callbacks…")
    phones = {}  # pid -> formatted phone
    deadline = time.time() + WEBHOOK_WAIT
    while time.time() < deadline and len(phones) < len(revealed):
        time.sleep(4)
        try:
            lines = CALLBACKS_FILE.read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                body = json.loads(rec["body"]) if isinstance(rec.get("body"), str) else rec.get("body", {})
            except Exception:
                continue
            person = body.get("person") or {}
            pid = person.get("id")
            if not pid or pid in phones:
                continue
            pnums = person.get("phone_numbers") or []
            mobile = ""
            for ph in pnums:
                if ph.get("type") == "mobile":
                    mobile = ph.get("sanitized_number") or ph.get("raw_number") or ""
                    break
            if not mobile and pnums:
                mobile = pnums[0].get("sanitized_number") or pnums[0].get("raw_number") or ""
            phones[pid] = _fmt_phone(mobile)
            p = revealed.get(pid, {})
            name = (p.get("name") or "").strip()
            tag = f"✓ {phones[pid]}" if phones[pid] else "✗ no number"
            print(f"  callback: {name[:30]:30} {tag}")
        remaining = len(revealed) - len(phones)
        if remaining:
            elapsed = int(WEBHOOK_WAIT - (deadline - time.time()))
            print(f"  {len(phones)}/{len(revealed)} ({elapsed}s)…", end="\r", flush=True)

    server_proc.terminate()
    tunnel_proc.terminate()

    got = sum(1 for v in phones.values() if v)
    print(f"\n\nCallbacks: {len(phones)}/{len(revealed)} received, {got} with actual numbers")

    # ── 5. Build rows for phone-confirmed experts only ────────────────────────
    rows_to_write = []
    for pid, phone in phones.items():
        if not phone:
            continue
        person = revealed.get(pid, {})
        org = person.get("organization") or {}
        name = (person.get("name") or "").strip()
        company = org.get("name") or person.get("organization_name") or ""
        city = person.get("city") or ""
        state = person.get("state") or ""
        emp = org.get("num_employees") or org.get("estimated_num_employees") or ""
        rev = org.get("annual_revenue_printed") or org.get("annual_revenue") or ""
        rows_to_write.append({
            "Full Name": name,
            "Title": (person.get("title") or "").strip(),
            "Company Name": company,
            "Company Employees": str(emp) if emp else "",
            "Company Revenue": str(rev) if rev else "",
            "City": f"{city}, {state}".strip(", "),
            "Years of Experience": person.get("total_years_of_experience") or "",
            "Email": person.get("email") or "",
            "LinkedIn URL": person.get("linkedin_url") or "",
            "Apollo Person ID": pid,
            "Apollo Org ID": org.get("id") or person.get("organization_id") or "",
            "Direct Mobile": phone,
        })
        if len(rows_to_write) >= limit:
            break

    print(f"\nWriting {len(rows_to_write)} phone-confirmed experts to sheet…")
    written = expert_writer.write_experts(rows_to_write, limit=limit)
    print(f"\nDone — {len(written)} added:")
    for n in written:
        print(f"  + {n}")
    if len(written) < limit:
        print(f"\n  ({len(written)}/{limit} — Apollo phone coverage is limited. "
              f"Run again to pull more from the next batch.)")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    run(limit)
