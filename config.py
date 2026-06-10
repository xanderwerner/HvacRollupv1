"""Configuration for the HVAC Roll-Up v1 lead-sourcing pipeline.

v1 = free spine only: Google Places (discovery + sizing) -> buy-box filter ->
write into the Organic List tab of the Excel database. No Apollo/ZoomInfo,
no owner contact info. See README.md.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def load_env(path: Path = PROJECT_ROOT / ".env") -> None:
    """Minimal .env loader (no external dependency)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


load_env()

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")

# --- Target market (from the Buy Box / Master Reference docs) ---
PHOENIX_METRO_CITIES = [
    "Phoenix", "Scottsdale", "Mesa", "Tempe", "Chandler", "Gilbert",
    "Glendale", "Peoria", "Surprise", "Avondale", "Goodyear",
]

# Trade Type (matches the Organic List dropdown) -> Google search term
TRADES = {
    "HVAC": "HVAC contractor",
    "Plumbing": "plumber",
    "Electrical": "electrician",
}

# --- Buy box thresholds (from the Organic Legend size-signal guide) ---
MIN_REVIEWS = 25     # under 25 = too small / one-man shop -> disqualify
MAX_REVIEWS = 500    # over 500 = likely too big / PE-scaled -> flag

# --- Output target ---
# "gsheet" = write to the live Google Sheet (default); "excel" = local .xlsx
WRITE_TARGET = "gsheet"

# Google Sheet (live master)
GSHEET_ID = "1OLBI9bgRZ3dDoGAeaYCohwNsv0KJbqtv90a7AAPHu-o"   # "HVAC Database"
GSHEET_TAB = "Organic List"
SERVICE_ACCOUNT_FILE = PROJECT_ROOT / "service_account.json"  # gitignored

# Excel (local fallback target)
EXCEL_PATH = Path(
    "/Users/xanderwerner/Documents/HVAC ROLL-UP/Copy of HVAC Database 2.xlsx"
)
EXCEL_SHEET = "Organic List"
HEADER_ROW = 4          # column headers live on row 4
FIRST_DATA_ROW = 6      # row 6 is the existing example; real data appends after

# --- Working store ---
DB_PATH = PROJECT_ROOT / "leads.sqlite"
