"""Enrich the Expert List with phone numbers.

Strategy (in order):
  1. Apollo async webhook -> direct mobile for each person (using stored Person ID)
     Uses a local webhook_server.py + serveo.net SSH tunnel as the public URL.
  2. Google Places fallback -> company main line for anyone without a direct mobile

Adds "Direct Mobile" and "Company Phone" columns to the Expert List if missing.

Run:  python3 enrich_expert_phones.py
      python3 enrich_expert_phones.py --dry
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

import apollo
import config
import places

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TAB_NAME = "Expert List"
COL_MOBILE = "Direct Mobile"
COL_COMPANY_PHONE = "Company Phone"
WEBHOOK_PORT = 8755
CALLBACKS_FILE = Path(__file__).parent / "phone_callbacks.jsonl"
WEBHOOK_WAIT = 120   # seconds to poll for callbacks


def _fmt_phone(raw):
    if not raw:
        return ""
    d = "".join(ch for ch in raw if ch.isdigit())
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return f"({d[0:3]}) {d[3:6]}-{d[6:]}"
    return d or ""


def _places_phone(name, city):
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


def _ensure_col(ws, headers, col_name, dry):
    if col_name not in headers:
        new_idx = len(headers)
        headers.append(col_name)
        if not dry:
            if ws.col_count < new_idx + 1:
                ws.add_cols(new_idx + 1 - ws.col_count)
            ws.update_cell(1, new_idx + 1, col_name)
        print(f"+ added '{col_name}' column at position {new_idx + 1}")
    return headers


def _start_tunnel():
    """Launch webhook_server.py + serveo.net tunnel. Returns (server_proc, tunnel_proc, public_url)."""
    # clear old callbacks
    CALLBACKS_FILE.write_text("")

    server = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "webhook_server.py"), str(WEBHOOK_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # let server bind

    tunnel = subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
         "-R", f"80:localhost:{WEBHOOK_PORT}", "serveo.net"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    # read tunnel output until we see the forwarding URL (up to 30s)
    public_url = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = ""
        try:
            tunnel.stdout._sock.settimeout(5)
        except Exception:
            pass
        try:
            line = tunnel.stdout.readline().decode("utf-8", "replace").strip()
        except Exception:
            time.sleep(1)
            continue
        if "serveo.net" in line and ("Forwarding" in line or "http" in line.lower()):
            # typical: "Forwarding HTTP traffic from https://abc.serveo.net"
            for part in line.split():
                if "serveo.net" in part:
                    public_url = part.rstrip(".")
                    break
        if public_url:
            break

    return server, tunnel, public_url


def _poll_callbacks(by_pid: dict, deadline: float) -> dict:
    """Poll phone_callbacks.jsonl until all person IDs are accounted for or deadline passes."""
    received = {}
    while time.time() < deadline and len(received) < len(by_pid):
        time.sleep(5)
        try:
            lines = CALLBACKS_FILE.read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                body = json.loads(rec.get("body", "{}")) if isinstance(rec.get("body"), str) else rec.get("body", {})
            except Exception:
                continue
            person = body.get("person") or {}
            pid = person.get("id")
            if not pid or pid in received:
                continue
            phones = person.get("phone_numbers") or []
            mobile = ""
            for ph in phones:
                if ph.get("type") == "mobile":
                    mobile = ph.get("sanitized_number") or ph.get("raw_number") or ""
                    break
            if not mobile and phones:
                mobile = phones[0].get("sanitized_number") or phones[0].get("raw_number") or ""
            received[pid] = _fmt_phone(mobile)
            t = by_pid.get(pid, {})
            print(f"  callback: {t.get('name','')[:28]:28}  -> {received[pid] or '(no number)'}")
        remaining = len(by_pid) - len(received)
        elapsed = int(WEBHOOK_WAIT - (deadline - time.time()))
        if remaining:
            print(f"  {len(received)}/{len(by_pid)} received ({elapsed}s elapsed)…",
                  end="\r", flush=True)
    return received


def run(dry=False):
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(config.GSHEET_ID).worksheet(TAB_NAME)

    vals = ws.get_all_values()
    headers = list(vals[0]) if vals else []
    added = False
    if COL_MOBILE not in headers:
        headers = _ensure_col(ws, headers, COL_MOBILE, dry)
        added = True
    if COL_COMPANY_PHONE not in headers:
        headers = _ensure_col(ws, headers, COL_COMPANY_PHONE, dry)
        added = True
    if added:
        vals = ws.get_all_values()
        headers = vals[0]

    H = {h: i for i, h in enumerate(headers) if h}

    def cell(row, h):
        j = H.get(h)
        return (row[j] if j is not None and j < len(row) else "").strip()

    # ── Phase 1: async mobile reveal ──────────────────────────────────────────
    rows_needing_mobile = []
    for i, row in enumerate(vals[1:], start=2):
        name = cell(row, "Full Name")
        if not name:
            continue
        if cell(row, COL_MOBILE):
            continue
        pid = cell(row, "Apollo Person ID")
        if not pid:
            continue
        rows_needing_mobile.append({
            "row_idx": i,
            "name": name,
            "company": cell(row, "Company Name"),
            "city": cell(row, "City"),
            "person_id": pid,
        })

    received_mobiles = {}

    if rows_needing_mobile:
        print(f"Experts needing mobile reveal: {len(rows_needing_mobile)}")
        print("\nStarting local webhook server + serveo.net tunnel…")
        server_proc, tunnel_proc, public_url = _start_tunnel()

        if not public_url:
            print("  WARNING: could not get serveo.net URL — skipping mobile phase.")
            if server_proc:
                server_proc.terminate()
            if tunnel_proc:
                tunnel_proc.terminate()
        else:
            webhook_url = public_url
            print(f"  Public URL: {webhook_url}\n")

            print(f"Firing {len(rows_needing_mobile)} mobile reveal requests…")
            by_pid = {}
            for t in rows_needing_mobile:
                r = apollo._req("POST", "/people/match", body={
                    "id": t["person_id"],
                    "reveal_phone_number": True,
                    "webhook_url": webhook_url,
                })
                status = r.get("error") or r.get("status") or "queued"
                print(f"  {t['name'][:28]:28}  {t['company'][:28]:28}  {status}")
                by_pid[t["person_id"]] = t
                time.sleep(0.4)

            print(f"\nPolling for callbacks (up to {WEBHOOK_WAIT}s)…")
            received_mobiles = _poll_callbacks(by_pid, time.time() + WEBHOOK_WAIT)

            server_proc.terminate()
            tunnel_proc.terminate()

            print(f"\n\nMobiles received: {len(received_mobiles)}/{len(rows_needing_mobile)}")
            found = sum(1 for v in received_mobiles.values() if v)
            print(f"  With an actual number: {found}")

    # ── Phase 2: company phone via Google Places ──────────────────────────────
    rows_needing_phone = []
    for i, row in enumerate(vals[1:], start=2):
        name = cell(row, "Full Name")
        if not name:
            continue
        if cell(row, COL_COMPANY_PHONE):
            continue
        pid = cell(row, "Apollo Person ID")
        if pid and received_mobiles.get(pid):
            continue  # got a direct mobile, skip company phone
        company = cell(row, "Company Name")
        city = cell(row, "City").split(",")[0].strip()
        if not company:
            continue
        rows_needing_phone.append({"row_idx": i, "name": name, "company": company, "city": city})

    print(f"\nLooking up company phones for {len(rows_needing_phone)} experts (Places)…")
    company_phones = {}
    for t in rows_needing_phone:
        phone = _fmt_phone(_places_phone(t["company"], t["city"]))
        src = "places" if phone else "—"
        print(f"  {t['company'][:34]:34}  {phone or '(not found)':20}  [{src}]")
        if phone:
            company_phones[t["row_idx"]] = phone
        time.sleep(0.3)

    # ── Write to sheet ────────────────────────────────────────────────────────
    cells = []
    for t in rows_needing_mobile:
        phone = received_mobiles.get(t["person_id"], "")
        if not phone:
            continue
        col = H.get(COL_MOBILE)
        if col is not None:
            cells.append(gspread.Cell(t["row_idx"], col + 1, phone))

    for row_idx, phone in company_phones.items():
        col = H.get(COL_COMPANY_PHONE)
        if col is not None:
            cells.append(gspread.Cell(row_idx, col + 1, phone))

    print(f"\n{len(cells)} cell update(s) to write.")
    if dry:
        print("DRY RUN — nothing written.")
        return
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
        print("Written to sheet.")
    else:
        print("Nothing to write.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
