"""Merge ZoomInfo contact enrichment (mobile phone, email, LinkedIn) into the NM sheet.

Sanity rules applied:
- COMPANY_ONLY_MATCH / NO_MATCH -> no personal data to write, skip.
- Multiple ambiguous LinkedIn candidates -> don't write any (avoid a wrong link).
- A match whose returned title makes no sense for a business owner (e.g. a personal/
  household title) is treated as a wrong-person match despite ZoomInfo's own FULL_MATCH
  status -- not used, flagged in Data Check instead.
"""
import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1SdQE5OLeJufn253Tvb9ic2MZh3k4UpKANOZiLAawJX8")
ws = sh.worksheet("New mexico master")

rows = ws.get_all_values()
header = rows[0]
data = rows[1:]
col = {name: i for i, name in enumerate(header)}

zi = json.load(open("data/nm_zi_contact_enrich_raw.json"))

new_flags = {
    "NM0067": "ZoomInfo returned a FULL_MATCH for 'Michelle Robbins' at this company, but the job title ('Chief Executive Officer of the Household and Director of Child Development', NY area code) makes clear it's a mismatched, unrelated personal profile -- not used. Owner name/title from prior web research (Michelle Robbins, Owner) kept, but mobile/LinkedIn from ZoomInfo were rejected.",
}

updated = 0
for r in data:
    rid = r[0]
    if rid not in zi:
        continue
    z = zi[rid]
    notes_add = []

    if rid == "NM0067":
        r[col["Data Check"]] = new_flags[rid]
        notes_add.append("ZoomInfo match rejected as wrong-person -- see Data Check")
    elif z["match"] in ("NO_MATCH", "COMPANY_ONLY_MATCH"):
        pass  # nothing to write
    else:
        if z.get("email") and not r[col["Owner Email"]].strip():
            r[col["Owner Email"]] = z["email"]
        if z.get("mobile"):
            r[col["Owner Cell"]] = z["mobile"]
            r[col["Cell Source"]] = "ZoomInfo"
        candidates = z.get("linkedin_candidates", [])
        if len(candidates) == 1 and not r[col["Owner LinkedIn"]].strip():
            r[col["Owner LinkedIn"]] = candidates[0]
        if z.get("note"):
            notes_add.append(f"ZoomInfo: {z['note']}")
        elif z.get("mobile"):
            notes_add.append("Mobile phone via ZoomInfo enrich_contacts")

    if notes_add:
        existing_notes = r[col["Notes"]]
        addition = "; ".join(notes_add)
        r[col["Notes"]] = f"{existing_notes}; {addition}" if existing_notes else addition
    updated += 1

print(f"processed {updated} rows against ZoomInfo results")

data_sorted = sorted(data, key=lambda r: bool(r[col["Data Check"]].strip()))
clean_count = sum(1 for r in data_sorted if not r[col["Data Check"]].strip())
print(f"after merge: {clean_count} clean rows on top, {len(data_sorted) - clean_count} flagged rows at bottom")

ws.update(range_name="A2", values=data_sorted)
print("sheet updated")
