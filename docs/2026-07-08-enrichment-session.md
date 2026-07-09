# 2026-07-08 Enrichment Session — Owner Cells + ROC Names

Phase: **Owner / Acquisition outreach** (cold-calling AZ HVAC/plumbing/electrical owners to acquire). This session enriched the 906-company master database that drives the call tracker.

Related: [[Lead Sourcing Script — Build Spec]] · [[Sourcing v1 (free version, no Apollo or ZoomInfo)]]

## Results at a glance

| Metric | Start of session | End |
|---|---|---|
| Owner names | 620 | **731** (+111) |
| Owner cells | 197 | **224** (+27) |
| Dial-ready (name + cell) | 186 | **217** |
| ICP hot-list dial-ready | 43 | **58** |
| ICP tier promotions (B/B2 → A/A2) | — | **11** |

All changes written live to the three Google Sheets (master, ICP hot list, tracker `Companies` tab). Formula columns in the tracker (O–R) were left untouched.

## What ran

### 1. Apollo owner-mobile reveals
- **Source:** master rows with an owner name but no cell, plus a domain/email (401 rows), prioritized ICP Tier B/B2 first, then by Google review count.
- **Method:** raw Apollo API — `people/match` with `reveal_phone_number=true` + any `webhook_url`, then poll `GET /api/v1/webhook_result/{request_id}`. **No webhook server / tunnel needed** (unlike the earlier expert-phone flow). Result purges minutes after completion, so poll promptly.
- **Yield:** ~140 person-matches, **27 mobile numbers** recovered (~20% of attempts — the easy Tier B/B2 wins came first, long tail is thinner). Each cell carries DNC status (1 of 27 on the DNC registry). Also captured 19 titles, 29 LinkedIn URLs, 3 emails as a side effect.
- **Cost:** ~8 direct-dial credits per successful reveal.

### 2. AZ ROC qualifying-party name fill
- **Source:** all 286 companies with no owner name.
- **Method:** reverse-engineered the AZ Registrar of Contractors search portal. It's a Salesforce Lightning/Aura site; the internal endpoint `ARCP_ContractorSearch/ACTION$getRecords` (params `searchKey`, `city`) returns qualifying party, contacts with Member/QP roles, all licenses (number, status, class), and the company phone — over **plain HTTP, no auth, no browser, free.**
- **Yield:** 190/286 matched; **111 owner names accepted** (company-name match ratio ≥ 0.55), 99 license numbers, 32 companies flagged **"ROC license INACTIVE — verify still operating"** (possible dead targets), 92 companies had a Member-role contact (stronger ownership signal than a bare qualifying party).

## ⚠️ Action items

1. **Apollo direct-dial credits exhausted: 30,000 / 30,000 consumed** (resets 2027-06-21). This session only used ~1,300; the other ~25k is unexplained (team contacts unchanged at 193). **Check Apollo → Settings → Usage and contact support.** Phone reveals silently no-op when the pool is empty. ~17,000 lead/enrichment credits still remain.
2. **~507 named-but-no-cell rows** remain — feed to the ZoomInfo trial (ICP band) and skip tracing (~$0.15/hit, ~$80 for the long tail). The 111 new ROC names are now skip-traceable.
3. **~96 still nameless** — 61 had weak ROC matches worth a manual look; rest need AZ Corporation Commission lookups.
4. **32 ROC-inactive flags** — review before dialing; some may be closed businesses.
5. **Line-type scan** of office numbers still pending a Twilio account (~$10 total).

## Reusable tooling (in the `hvac-lead-sourcing` repo)

- `enrich_cells.py` — batch Apollo owner-mobile reveal, wave-based with rate-limit cooldowns, resumable via `data/reveals.jsonl`.
- `roc_fill_names.py` — batch AZ ROC owner-name fill, resumable via `data/roc_names.jsonl`.
- `roc_recon.py` — one-shot Playwright capture of the ROC Aura API (used to build the template `roc_fill_names.py` replays).

Working data snapshots (xlsx + jsonl logs, gitignored — contain PII) live in `~/Desktop/hvac/data/`.
