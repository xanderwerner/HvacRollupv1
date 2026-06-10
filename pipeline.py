"""Orchestrates the v1 free spine:

  discover (Places) -> dedupe -> filter -> score -> details -> store -> write Excel
"""
from typing import Optional

import config
import places
import store
from filter_score import apply_filter, score
from models import Lead


def _to_lead(raw: dict) -> Lead:
    return Lead(
        place_id=raw.get("place_id", ""),
        company_name=raw.get("name", ""),
        trade_type=raw.get("_trade", ""),
        city=raw.get("_city", ""),
        business_address=raw.get("formatted_address", ""),
        review_count=raw.get("user_ratings_total"),
        rating=raw.get("rating"),
        business_status=raw.get("business_status", ""),
    )


def _fit_rank(lead: Lead) -> tuple:
    rank = 2 if lead.buy_box_fit == "Strong" else 1
    return (rank, lead.rating or 0, lead.review_count or 0)


def run(limit: int = 10, write_excel: bool = True) -> dict:
    if not config.GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY missing from .env")

    print("== 1. DISCOVER (Google Places) ==")
    raw = places.discover(config.PHOENIX_METRO_CITIES, config.TRADES)
    print(f"   raw results: {len(raw)}")

    # dedupe by place_id, then by normalized company name (chains span cities)
    by_id, seen_names = {}, set()
    for r in raw:
        pid = r.get("place_id")
        if not pid or pid in by_id:
            continue
        nm = r.get("name", "").strip().lower()
        if nm in seen_names:
            continue
        seen_names.add(nm)
        by_id[pid] = r
    leads = [_to_lead(r) for r in by_id.values()]
    print(f"   unique companies: {len(leads)}")

    print("== 2. FILTER + SCORE (buy box) ==")
    for lead in leads:
        apply_filter(lead)
        if lead.survived_filter:
            score(lead)
    survivors = sorted(
        [l for l in leads if l.survived_filter], key=_fit_rank, reverse=True
    )
    print(f"   survivors (25-500 reviews, operational): {len(survivors)}")

    print("== 3. DETAILS (website/phone for top survivors) ==")
    top = survivors[: max(limit * 2, limit)]
    for lead in top:
        try:
            d = places.place_details(lead.place_id)
            lead.website = d.get("website", "")
            lead.business_phone = d.get("formatted_phone_number", "")
            if d.get("formatted_address"):
                lead.business_address = d["formatted_address"]
        except Exception as exc:
            print(f"  ! details failed for {lead.company_name}: {exc}")

    print("== 4. STORE (SQLite) ==")
    conn = store.connect()
    n = store.upsert(conn, leads)
    conn.close()
    print(f"   stored {n} leads in {config.DB_PATH.name}")

    written = []
    if write_excel:
        print("== 5. WRITE (Excel Organic List) ==")
        import excel_writer
        written = excel_writer.write_leads(survivors, limit=limit)
        print(f"   wrote {len(written)} rows")

    return {
        "raw": len(raw),
        "unique": len(leads),
        "survivors": len(survivors),
        "written": written,
        "top": top,
    }
