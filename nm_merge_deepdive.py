"""Merge the deep-dive research (batches A + B) into the New Mexico master sheet."""
import json
import gspread

gc = gspread.service_account(filename="/Users/xanderwerner/dev/hvac-lead-sourcing/service_account.json")
sh = gc.open_by_key("1SdQE5OLeJufn253Tvb9ic2MZh3k4UpKANOZiLAawJX8")
ws = sh.worksheet("New mexico master")

rows = ws.get_all_values()
header = rows[0]
data = rows[1:]
col = {name: i for i, name in enumerate(header)}

deepdive = {}
for r in json.load(open("data/nm_deepdive_output_a.json")):
    deepdive[r["id"]] = {"linkedin": r.get("owner_linkedin_url", ""), "email": r.get("owner_email", ""), "notes": r.get("notes", "")}
for r in json.load(open("data/nm_deepdive_output_b.json")):
    d = {"linkedin": r.get("owner_linkedin_url", ""), "email": r.get("owner_email", ""), "notes": r.get("notes", "")}
    if r.get("owner_name"):
        d["owner_name"] = r["owner_name"]
        d["owner_title"] = r.get("owner_title", "")
    deepdive[r["id"]] = d

new_flags = {
    "NM0021": "Owner name not found despite extensive research (BuildZoom, D&B, BBB, NM SOS, LinkedIn all checked); domain roadrunner4u.com no longer belongs to this business (now an unrelated Utah company) -- use phone (575) 491-3447 only, not the website/email",
    "NM0023": "Title ambiguous -- company site calls Frank Martinez 'Owner', but BBB lists him as 'Vice-President' alongside Laurie Martinez (also VP), with no one listed as President/Owner at BBB",
    "NM0054": "Company website (rmcelectricllc.com) returned 404/appears down -- verify still operating before outreach",
}

updated = 0
for r in data:
    rid = r[0]
    if rid not in deepdive:
        continue
    d = deepdive[rid]
    if d.get("linkedin"):
        r[col["Owner LinkedIn"]] = d["linkedin"]
    if d.get("email"):
        r[col["Owner Email"]] = d["email"]
    if d.get("owner_name"):
        r[col["Owner Name"]] = d["owner_name"]
        r[col["Owner Title"]] = d.get("owner_title", "")
    existing_notes = r[col["Notes"]]
    r[col["Notes"]] = f"{existing_notes}; Deep-dive: {d['notes']}" if existing_notes else f"Deep-dive: {d['notes']}"
    if rid in new_flags and not r[col["Data Check"]].strip():
        r[col["Data Check"]] = new_flags[rid]
    updated += 1

print(f"updated {updated} rows with deep-dive research")

data_sorted = sorted(data, key=lambda r: bool(r[col["Data Check"]].strip()))
clean_count = sum(1 for r in data_sorted if not r[col["Data Check"]].strip())
print(f"after merge: {clean_count} clean rows on top, {len(data_sorted) - clean_count} flagged rows at bottom")

ws.update(range_name="A2", values=data_sorted)
print("sheet updated")
