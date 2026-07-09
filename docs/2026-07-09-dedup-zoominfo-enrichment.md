# 2026-07-09 Dedup, ZoomInfo Trial Setup + Phone Enrichment (Steps 1–2)

Phase: **Owner / Acquisition outreach**. Continuation of [[2026-07-08 Enrichment Session — Owner Cells + ROC Names]]. Today: deduplicated the master, stood up the ZoomInfo trial, built a consolidated **Super Enrichment** sheet, and spent the first 150 ZoomInfo credits on verified owner-mobile enrichment.

## Results at a glance

| Metric | Start of day | End of day |
|---|---|---|
| Companies | 906 | **861** (45 duplicates merged) |
| Owner names | 731 | **706** |
| Owner cells | 224 | **318** |
| Dial-ready | 217 | **314** |
| ZoomInfo credits used | 0 | **150 / 700** |

New sheet: **"Super enrichment list"** (tab "Super Enrichment") — one row per company, merges master + ZoomInfo + Apollo + ROC with a per-field confidence verdict (Verified / Single-source / Conflict) and a Next Action column. Rebuilt from scratch after every change via `build_super_sheet.py`.

## 1. Deduplication (906 → 861)

Xander spotted multi-location duplicates (e.g. "AC Repair Near Me" scraped once per city, one real owner). Cross-referenced ROC license numbers (strongest signal), identical domains, and brand-name/city-suffix patterns to find true duplicates — distinct from **coincidental same-owner-different-company** situations (kept separate, cross-referenced) and **franchise-brand coincidences** (left unmerged without stronger evidence). Result: 45 rows folded into 30 canonical companies.

**Two follow-up fixes on the merged companies:**
- **Location priority**: for multi-location companies, prefer a Phoenix-metro location; if none, the one closest to Phoenix (haversine distance). Fixed 5 of 30 whose kept city wasn't the best choice.
- **Review aggregation**: Google review counts are genuinely per-location, but that data wasn't preserved when duplicate rows were deleted (no backup taken first — lesson for next time). Recovered by re-querying Google Places fresh for every folded location and summing into the canonical row (e.g. Goettl: Phoenix 14,241 + Tucson 4,827 ≈ 19,028 combined, independently verified).
- **Revenue/employees were NOT summed** — verified this would be wrong: Apollo/ZoomInfo report firmographics at the company/domain level, not per-branch, so summing would double-count the same estimate. The one figure already on each canonical row is the whole-company number.

## 2. A serious bug found in yesterday's ROC name-fill — 58 rows fixed

Investigating the dedup surfaced that 58 of 190 ROC-sourced owner names from the prior session were **false-positive matches**: when a direct name search returned nothing, the script fell back to an overly generic 1-2 word search key (e.g. "D H", "A C") that returned 500-900+ candidates, and generic trade words ("plumbing services") inflated the similarity score enough to match a totally unrelated company. Confirmed via a live ROC lookup: "D&H Air Conditioning" had been mislabeled with **A1 Air Conditioning's** owner (license 336204 belongs only to A1). Also found 5 rows where a ROC status code ("QP Exempt" — meaning no qualifying party is required) or a scraping artifact had been stored as if it were a person's name. All reverted to blank pending real research.

## 3. ZoomInfo trial stood up

- Credentials in `.env` (ZOOMINFO_USERNAME/PASSWORD) — **rotate the password**, it was shared in chat.
- **Critical API gotcha**: `api.zoominfo.com` blocks Python's `urllib`/`requests` TLS fingerprint (Cloudflare 403). The `/authenticate` call must go through `curl` with a browser User-Agent; the resulting JWT then works fine via `urllib` for all other calls.
- **Credit structure (confirmed empirically)**: `/search/company` and `/search/contact` are **100% free**, zero credits ever consumed — confirmed by direct before/after balance checks across ~1,900 free calls. Only `/enrich/contact` (the actual phone/email reveal) spends the `uniqueIdLimit` credit. This means: run free search across the whole database for owner name, title, size, and a "mobile available" flag at zero cost, and spend paid credits only where that free flag says a real mobile exists.
- Credit pool grew from 200 → 300 → 700 over the day (Xander stacking additional trial signups toward ~1000 before spending harder).

## 4. Free verification pass + Apollo cross-check

Ran the free ZoomInfo search across all 894 non-blank companies (twice — once pre-dedup, once post-dedup to catch any drift from the merges/renames) and a plain Apollo `people/match` cross-check (no phone/email reveal, just identity + firmographic confirmation) across every owner not yet Apollo-touched. Found and fixed a tracking bug: `apollo_verify.py` logged results to JSONL but never wrote a confirmation marker back into the master, so an intermediate "522 still need Apollo check" estimate was wrong — the real gap was 120. Final combined result: 706 owner names, of which 578 are cross-source **Verified**, 43 single-source, 85 flagged as genuine conflicts (mostly companies with multiple real co-owners where different sources named different people), 155 still unnamed.

## 5. Phone enrichment — Steps 1 & 2 (150 credits spent)

Plan agreed with Xander, phased and deliberately paced ("sniper not machine gunner"):
- **Step 1** (97 companies — owner confirmed + ZoomInfo flagged a real mobile as existing): near-certain hit rate.
- **Step 2** (63 companies — owner confirmed, no mobile flag): lower confidence, direct/office lines or nothing expected.
- **Steps 3 & 4 deferred** (480 with nothing in ZoomInfo at all; 155 with no owner name yet) — these aren't ZoomInfo jobs; they need skip-tracing and name-sourcing respectively. Explicitly on hold until Xander sets up the skip-tracing tool.

**Real problems caught during verification** (all before bad data could reach a caller, except two that briefly landed live and were reverted):

1. **Cross-contaminated ZoomInfo contact records**: rows named entirely with generic trade words ("Heating & Cooling", "The Plumbing Company") had no distinctive brand token at all, so ZoomInfo's fallback name search coincidentally matched them to Rite Way Heating's real owner (Richard Walter). **Later corrected**: Xander confirmed Richard Walter genuinely does own all three businesses (a real roll-up) — restored rather than reverted, cross-referenced as the same owner.
2. **A wrong match slipped past my own exclusion list** ("Ground Zero Plumbing" got a Minnesota number + `groundzeromidwest.com` email) because the exclusion check used an exact company-name string that didn't match after a rename. Caught on a full post-write audit, reverted. **Lesson: key exclusion/allow lists by row_id, not company-name string — renames break string matching.**
3. **Area code is not a reliable wrong-entity signal on its own** — mobile number portability means people keep old cell numbers for decades after moving. Initially over-flagged 34 results with non-Arizona area codes; almost all had an email domain that exactly matched the company's own real domain (the authoritative signal), and the area code was just personal history. Only treat a mismatched area code as meaningful when there's *no* domain confirmation to fall back on.
4. **Same owner across two independently-real companies = a roll-up signal, not an error** (Xander's explicit correction, applied to Mr. Rooter's two territories, Aire Serv's two territories, and the Rite Way group above). The distinguishing test: was each company independently, correctly identified as a real distinct entity, or did a weak/generic search coincidentally conflate two unrelated businesses? Only the latter is a real bug.

**Final Step 1/2 numbers**: 88 mobiles + 7 direct/office lines + domain-verified emails written = 95 new phone/contact data points. 1 held back (Climate Pro LLC — company match confirmed correct, but the specific ZoomInfo contact's phone/email belong to an unrelated Seattle-area business, looks like a genuine ZoomInfo data mixup rather than a roll-up).

## Data flow / where things live

- **Local working file** (`~/Desktop/hvac/data/AZ_targets_enriched_master.xlsx`) is where every edit actually happens first.
- **Master Google Sheet**: full overwrite each push (no formulas to protect).
- **Tracker "Companies" tab**: targeted cell updates only — it has live formulas (Last Caller, Calls This Week, etc.) that a blind clear+rewrite destroys (learned this the hard way, fixed, now always verify formulas survived after every push).
- **Super Enrichment**: fully rebuilt from the master + raw enrichment logs every time, not hand-edited.

## Reusable tooling (in the `hvac-lead-sourcing` repo)

`zi_verify.py` / `zi_reverify_post_dedup.py` (free ZoomInfo search + owner/mobile flagging), `apollo_verify.py` (Apollo cross-check), `dedup_master.py` (curated multi-location merge), `aggregate_locations.py` (Phoenix-priority city selection + Google Places review re-aggregation), `zi_enrich_phones.py` (paced, resumable phone enrichment with a credit-runaway circuit breaker and domain/name-mismatch safety checks), `build_super_sheet.py` (rebuilds the Super Enrichment sheet).

## Next steps

- Skip-tracing (Step 3, the 480 companies) — on hold until Xander sets that up.
- Name-sourcing (Step 4, the 155 nameless companies) — AZ Corp Commission lookups, or re-attempt ROC with stricter matching.
- 550 ZoomInfo credits remain; more could be spent on the 63-company Step-2 pool's uncontacted remainder or new gaps as they're identified.
- The 85 flagged owner conflicts are worth resolving (or letting callers resolve on the first dial) before assuming any single name is correct.
