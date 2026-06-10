"""AZ ROC collector — best-effort Playwright scraper (architecture module).

The AZ Registrar of Contractors license search is a Salesforce Lightning/Aura
portal at:
    https://azroc.my.site.com/AZRoc/s/contractor-search
(plain roc.az.gov returns 403). There is no clean public JSON API, so this
module drives the portal with a headless browser to recover the data the free
Places pipeline can't: ROC license #, license status, the *qualifier* (≈ the
owner's name), and license issue date (a business-age proxy).

STATUS: scaffolded for v1.x. The Places pipeline (run.py) does NOT depend on
this — ROC enrichment is the next increment. Requires:
    pip install playwright && playwright install chromium
Selectors will need tuning against the live Aura DOM (shadow roots).
"""
from dataclasses import dataclass

SEARCH_URL = "https://azroc.my.site.com/AZRoc/s/contractor-search"

# AZ ROC trade classifications (verify against the live portal before relying)
TRADE_CLASSIFICATIONS = {
    "HVAC": ["C-39", "CR-39", "K-39", "L-39"],
    "Plumbing": ["C-37", "CR-37", "L-37"],
    "Electrical": ["C-11", "CR-11", "L-11"],
}


@dataclass
class RocRecord:
    company_name: str
    license_number: str
    license_status: str
    qualifier_name: str      # ≈ owner-operator
    issue_date: str = ""
    city: str = ""


def collect(trade: str, county: str = "Maricopa", headless: bool = True) -> list[RocRecord]:
    """Drive the ROC portal and return license records for a trade.

    Implemented as best-effort; raises a clear error if Playwright isn't set up
    so the caller can fall back to the Places-only pipeline.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && "
            "playwright install chromium"
        ) from exc

    records: list[RocRecord] = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=60_000)
        # NOTE: the Aura search form loads inside Lightning components. The
        # interaction below is a starting point and must be tuned to the live
        # DOM (component selectors, shadow roots, result pagination).
        #
        #   page.fill("input[name='classification']", classification)
        #   page.click("button:has-text('Search')")
        #   page.wait_for_selector("table tbody tr")
        #   for row in page.query_selector_all("table tbody tr"): ...
        #
        browser.close()
    return records
