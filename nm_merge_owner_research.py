"""Merge the 5 owner-research batch outputs into the New Mexico master sheet."""
import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1SdQE5OLeJufn253Tvb9ic2MZh3k4UpKANOZiLAawJX8")
ws = sh.worksheet("New mexico master")

rows = ws.get_all_values()
header = rows[0]
data = rows[1:]

col = {name: i for i, name in enumerate(header)}

# --- load research ---
research = {}
for i in range(1, 6):
    for r in json.load(open(f"data/nm_research_output{i}.json")):
        research[r["id"]] = r

# --- hand-curated viability/confidence flags from reading the 5 agents' full reports ---
flags = {
    "NM0005": "Possible rebrand/sale -- domain redirects to justcallace.com; BBB lists GM (Nick Knight) as principal contact, not the D&B-listed owner -- ownership status unclear",
    "NM0006": "Appears already acquired by Modigent (Phoenix-based) ~2022 -- may not be an independent acquisition target despite Mike Travers still showing as Owner on LinkedIn",
    "NM0007": "Apollo hint pointed to an unrelated 'Phoenix Mechanical' -- actual current owners are 3 co-owners (Cain/Sturges/Struck) per a 2022 ownership change from founder Bob Draper",
    "NM0008": "Conflicting owner candidates (Kenneth Sailors vs Kris Webb) -- no owner name confirmed",
    "NM0018": "Wholly-owned subsidiary of Yearout Industrial LLC -- not an independent owner-operated business",
    "NM0026": "Two co-owners (father/son, both titled Owner) -- could not confidently match LinkedIn to Sr. vs Jr.",
    "NM0040": "Conflicting leadership sources -- Frank Schmitt (President) vs Mark Cunningham/Joe Gombar (Co-Presidents); domain redirects to a Phoenix-HQ site; a similarly-named 'Mechanical Southwest Inc' also exists in Gallup -- entity-identity risk",
    "NM0043": "Apollo hint (Anthony Fierro, GM) may not be the true owner -- a separate directory lists Jeremy Vargas as Owner, no LinkedIn found for Vargas",
    "NM0049": "Apollo hint pointed to an LA-based 'Tom Perdomo' claiming CEO -- company site/LinkedIn instead name Roger Sheak as Owner/President; confirm there isn't a separate corporate/franchise layer",
    "NM0060": "Phone number inconsistent across sources (BBB vs current live website)",
    "NM0069": "LinkedIn profile lists title as 'Plumber' not 'President' -- moderate confidence match only",
    "NM0070": "A similarly-named 'Allied Drains & Plumbing Services' with a different owner (David Fematt) also exists -- possible entity confusion, not used",
    "NM0074": "Electrician license shows inactive since 2015 -- likely defunct; no owner found",
    "NM0078": "Both a Sr. (President) and Jr. (GM) Caldwell exist; the one LinkedIn profile found couldn't be confirmed as either",
    "NM0080": "Conflicting owner info -- a company-site testimonial names someone called 'Elijah' as owner/operator vs. Patricia Taylor as the listed Owner",
    "NM0082": "Domain's homepage rendered generic Orlando, FL content -- likely a parked/repurposed site, not the actual NM business; no owner found",
    "NM0085": "Input domain (acrcooling.com) doesn't resolve; BBB suggests the business may be defunct (returned mail 2022) -- verify still operating",
    "NM0086": "No domain given; matched to 'P3 Plumbing, Inc.' in Albuquerque, but BBB's alternate name for that company is 'Prompt Precise Plumbing,' not 'Mip' -- confirm intended target",
    "NM0087": "Longtime owner Vic Arguello died June 2025; BBB shows business as apparently out of business; website has expired SSL cert -- needs re-verification before outreach",
    "NM0090": "Only the VP (Scott Moore, son) has a confirmed LinkedIn -- did not substitute for the Owner (Bobby Moore) field",
    "NM0092": "Owner not found despite multiple searches",
    "NM0093": "Owner name found only as initials ('KC Armstrong') everywhere searched -- no full name or LinkedIn confirmed",
    "NM0103": "Conflicting principal records -- formation docs name Lee and Bobby Carver, but BBB currently lists George Carver as President; current owner not confirmed with confidence",
}

co_owners = {
    "NM0007": "Ky Sturges; Jason Struck",
    "NM0026": "Eddie J. Saiz Jr. (also Owner)",
    "NM0040": "Mark Cunningham (Co-President); Joe Gombar (Co-President)",
    "NM0065": "Aaron Biel (General Manager)",
}

updated = 0
for r in data:
    rid = r[0]
    if rid not in research:
        continue
    rec = research[rid]
    r[col["Owner Name"]] = rec.get("owner_name", "")
    r[col["Owner Title"]] = rec.get("owner_title", "")
    r[col["Owner LinkedIn"]] = rec.get("owner_linkedin_url", "")
    r[col["Office Phone"]] = rec.get("office_phone", "") or r[col["Office Phone"]]
    r[col["Owner Found Via"]] = "Google/LinkedIn web research 2026-07-13"
    existing_notes = r[col["Notes"]]
    new_note = rec.get("confidence_notes", "")
    r[col["Notes"]] = f"{existing_notes}; Owner research: {new_note}" if existing_notes else f"Owner research: {new_note}"
    if rid in flags:
        r[col["Data Check"]] = flags[rid]
    if rid in co_owners:
        r[col["Co-Owners"]] = co_owners[rid]
    updated += 1

print(f"updated {updated} rows with research")

# stable sort: rows with empty Data Check first, flagged rows after (preserves relative order in each bucket)
data_sorted = sorted(data, key=lambda r: bool(r[col["Data Check"]].strip()))

clean_count = sum(1 for r in data_sorted if not r[col["Data Check"]].strip())
flagged_count = len(data_sorted) - clean_count
print(f"after merge: {clean_count} clean rows on top, {flagged_count} flagged rows at bottom")

ws.update(range_name="A2", values=data_sorted)
print("sheet updated")
