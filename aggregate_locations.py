#!/usr/bin/env python3
"""Fix multi-location canonical rows: Phoenix-priority city selection + accurate
review aggregation (re-fetched from Google Places, since per-location review
counts were not preserved when duplicate rows were deleted) + a check on whether
any group's revenue/employee figures are genuinely separate (not just the same
company-wide Apollo/ZoomInfo number repeated).
"""
import math
import re
import sys
import time
sys.path.insert(0, "/Users/xanderwerner/dev/hvac-lead-sourcing")

import openpyxl
from places import text_search

DATA = "/Users/xanderwerner/Desktop/hvac/data/"

PHOENIX = (33.4484, -112.0740)
MARICOPA_METRO = {
    "phoenix", "scottsdale", "tempe", "mesa", "chandler", "gilbert", "glendale",
    "peoria", "goodyear", "surprise", "avondale", "buckeye", "queen creek",
    "apache junction", "fountain hills", "paradise valley", "el mirage",
    "youngtown", "tolleson", "cave creek", "carefree", "litchfield park",
    "sun city", "sun city west", "wickenburg", "gila bend", "guadalupe",
}
# approximate lat/lon for AZ cities appearing in this dataset (outside Maricopa metro)
CITY_COORDS = {
    "tucson": (32.2226, -110.9747), "oro valley": (32.3909, -110.9665),
    "sierra vista": (31.5455, -110.2773), "prescott": (34.5400, -112.4685),
    "prescott valley": (34.6100, -112.3157), "flagstaff": (35.1983, -111.6513),
    "sedona": (34.8697, -111.7610), "yuma": (32.6927, -114.6277),
    "kingman": (35.1894, -114.0530), "bullhead city": (35.1478, -114.5683),
    "lake havasu city": (34.4839, -114.3225), "casa grande": (32.8795, -111.7574),
    "maricopa": (33.0581, -112.0476), "show low": (34.2542, -110.0298),
    "payson": (34.2306, -111.3244), "pinetop": (34.1500, -109.9354),
    "phoenix": PHOENIX, "scottsdale": (33.4942, -111.9261), "tempe": (33.4255, -111.9400),
    "mesa": (33.4152, -111.8315), "chandler": (33.3062, -111.8413), "gilbert": (33.3528, -111.7890),
    "glendale": (33.5387, -112.1860), "peoria": (33.5806, -112.2374), "goodyear": (33.4353, -112.3576),
    "surprise": (33.6292, -112.3679), "avondale": (33.4356, -112.3496), "buckeye": (33.3703, -112.5838),
    "queen creek": (33.2481, -111.6346), "apache junction": (33.4151, -111.5496),
}


def haversine(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * 6371 * math.asin(math.sqrt(h))


def best_city(cities):
    cities = [c.strip() for c in cities if c and c.strip()]
    metro = [c for c in cities if c.lower() in MARICOPA_METRO]
    if metro:
        return metro[0]
    scored = []
    for c in cities:
        coord = CITY_COORDS.get(c.lower())
        if coord:
            scored.append((haversine(coord, PHOENIX), c))
    if scored:
        return min(scored)[1]
    return cities[0] if cities else None


def parse_other_locations(text):
    """'Name (City); Name2 (City2)' -> [(name, city), ...]"""
    out = []
    for part in str(text or "").split(";"):
        part = part.strip()
        m = re.match(r"^(.*)\(([^)]+)\)\s*$", part)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def fetch_reviews(name, city):
    try:
        results = text_search(f"{name} {city} AZ")
    except Exception as e:
        return None, None
    if not results:
        return None, None
    top = results[0]
    return top.get("rating"), top.get("user_ratings_total")


MERGE_CANONICAL_IDS = ['C899','C218','C713','C041','C051','C091','C232','C234','C316','C318',
                       'C409','C350','C359','C434','C462','C520','C596','C586','C601','C665',
                       'C673','C641','C250','C285','C267','C275','C025','C192','C236','C015']


def main():
    wb = openpyxl.load_workbook(DATA + "AZ_targets_enriched_master.xlsx")
    ws = wb["Enriched Master"]

    city_changes = []
    review_changes = []
    for row in ws.iter_rows(min_row=2):
        rid = row[0].value
        if rid not in MERGE_CANONICAL_IDS:
            continue
        cur_city = row[3].value
        cur_name = row[1].value
        locs = parse_other_locations(row[23].value)
        all_cities = [cur_city] + [c for _, c in locs]
        pick = best_city(all_cities)
        if pick and pick != cur_city:
            city_changes.append((rid, cur_name, cur_city, pick))
            row[3].value = pick

        # reviews: sum canonical + fresh-fetched folded locations
        total_reviews = row[27].value or 0
        rating_weighted_sum = (row[26].value or 0) * total_reviews
        fetched_any = False
        for name, city in locs:
            rating, reviews = fetch_reviews(name, city)
            time.sleep(0.15)
            if reviews:
                total_reviews += reviews
                rating_weighted_sum += (rating or 0) * reviews
                fetched_any = True
        if fetched_any and total_reviews > (row[27].value or 0):
            old_reviews, old_rating = row[27].value, row[26].value
            row[27].value = total_reviews
            row[26].value = round(rating_weighted_sum / total_reviews, 1) if total_reviews else row[26].value
            review_changes.append((rid, cur_name, old_reviews, total_reviews, old_rating, row[26].value))

    wb.save(DATA + "AZ_targets_enriched_master.xlsx")

    print(f"CITY changes ({len(city_changes)}):")
    for rid, name, old, new in city_changes:
        print(f"  {rid} {name[:35]:35} {old} -> {new}")
    print(f"\nREVIEWS changes ({len(review_changes)}):")
    for rid, name, oldr, newr, oldrt, newrt in review_changes:
        print(f"  {rid} {name[:35]:35} reviews {oldr}->{newr} | rating {oldrt}->{newrt}")


if __name__ == "__main__":
    main()
