"""Re-score the existing Places-sourced leads against the updated buy box
(10+ employees, no ceiling), using the Apollo employee count already in the
sheet. Only touches Google-Maps-sourced rows; Apollo-sourced rows are already
sized at search time.
"""
import gspread
from google.oauth2.service_account import Credentials

import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _ws():
    creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_FILE, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(config.GSHEET_ID).worksheet(config.GSHEET_TAB)


def requalify() -> int:
    ws = _ws()
    vals = ws.get_all_values()
    hrow = next(i for i, r in enumerate(vals) if "Company Name" in r)
    H = {h: j for j, h in enumerate(vals[hrow]) if h}

    def cell(row, h):
        j = H.get(h)
        return row[j] if j is not None and j < len(row) else ""

    cells, changed = [], 0
    for i in range(hrow + 1, len(vals)):
        row = vals[i]
        name = cell(row, "Company Name").strip()
        if not name or cell(row, "Discovery Source").strip() != "Google Maps":
            continue
        try:
            emp = int(cell(row, "Est. # of Employees").strip())
        except ValueError:
            emp = None

        if emp is not None and emp >= config.BUY_BOX_MIN_EMPLOYEES:
            upd = {"Buy Box Fit": "Strong"}
            if cell(row, "Owner Name").strip():
                upd["Research Stage"] = "In Progress"
            note = f"Re-qualified (10+ emp buy box): {emp} emp = QUALIFIES."
        elif emp is not None:
            upd = {"Buy Box Fit": "Weak", "Disqualify Reason": "Too small",
                   "Research Stage": "Disqualified"}
            note = f"Re-qualified (10+ emp buy box): {emp} emp = too small, disqualified."
        else:
            upd = {"Buy Box Fit": "Weak"}
            note = ("Re-qualified (10+ emp buy box): employee count unverified "
                    "(not in Apollo) — confirm 10+ manually.")

        prev = cell(row, "Notes").strip()
        upd["Notes"] = (prev + " | " if prev else "") + note
        for h, v in upd.items():
            if h in H and v != "":
                cells.append(gspread.Cell(i + 1, H[h] + 1, v))
        changed += 1

    if cells:
        ws.update_cells(cells, value_input_option="USER_ENTERED")
    return changed


if __name__ == "__main__":
    print("Re-qualifying existing leads against 10+ employee buy box...\n")
    print(f"re-qualified {requalify()} rows.")
