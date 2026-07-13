#!/usr/bin/env python3
import json
import re
import difflib
from collections import Counter

def compact(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

# Trade-generic words (not distinctive brand identifiers) plus corp-suffix noise.
GENERIC = {"electric","electrical","llc","inc","co","company","the","of","az","arizona",
           "contracting","contractors","services","service","solutions","corp","corporation",
           "and","group","enterprises","power","energy","solar","lighting","control","controls",
           "systems","valley","plumbing","cooling","heating","air","conditioning","construction",
           "mechanical","professional","commercial","residential",
           "phoenix","tucson","mesa","chandler","gilbert","scottsdale","tempe","glendale",
           "peoria","surprise","avondale","goodyear","buckeye","flagstaff","prescott","yuma",
           "kingman","sedona","casa","grande","maricopa","pinal","pima","legacy","apex","absolute"}

def tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in GENERIC and len(w) >= 3}

def primary_identifier(roc_name, roc_dba):
    return roc_dba.strip() if roc_dba and roc_dba.strip() else roc_name

def is_real_match(roc_name, roc_dba, places_domain, places_name):
    if re.search(r"\.(com\.au|co\.uk|co\.nz|com\.br|de|fr|es|it|ca)$", places_domain or ""):
        return False  # non-US TLD -- almost certainly the wrong company
    primary = primary_identifier(roc_name, roc_dba)
    my_tok = tokens(primary)
    cand_tok = tokens(places_name)
    if my_tok and (my_tok & cand_tok):
        return True
    ratio = difflib.SequenceMatcher(None, compact(primary), compact(places_name)).ratio()
    return ratio > 0.85

places_recs = {r["account_id"]: r for r in (json.loads(l) for l in open("data/elec_places_size.jsonl"))}
zi_recs = {r["account_id"]: r for r in (json.loads(l) for l in open("data/elec_zi_verify.jsonl"))}

# First pass: name-match filter
prelim = {}
for aid, p in places_recs.items():
    if not p.get("domain"):
        continue
    roc = zi_recs.get(aid, {})
    roc_name = roc.get("roc_name") or p.get("roc_name", "")
    roc_dba = (roc.get("roc_dba") or "").replace("DBA :", "").strip()
    places_name = p.get("places_name", "")
    prelim[aid] = is_real_match(roc_name, roc_dba, p.get("domain"), places_name)

# Second pass: reject any domain claimed by more than one different ROC account --
# ambiguous shared match, can't trust either without manual review.
domain_counts = Counter(places_recs[aid].get("domain") for aid, ok in prelim.items() if ok)
out = {}
ambiguous = 0
for aid, ok in prelim.items():
    dom = places_recs[aid].get("domain")
    if ok and domain_counts.get(dom, 0) > 1:
        out[aid] = False
        ambiguous += 1
    else:
        out[aid] = ok

verified = sum(1 for v in out.values() if v)
rejected = len(out) - verified
print(f"Places-sourced domains: {len(out)} | verified: {verified} | rejected: {rejected} (incl. {ambiguous} ambiguous shared-domain)")
json.dump(out, open("data/places_match_verdict.json", "w"))
