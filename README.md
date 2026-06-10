# HVAC Roll-Up — Lead Sourcing (v1, free spine)

Automates the top of the **Organic Prospect List** for the Arizona HVAC /
plumbing / electrical acquisition roll-up. v1 uses **only free sources** to
produce *real*, deduped, buy-box-filtered, scored company rows written straight
into the `Organic List` tab of the Excel database.

> Full design + column fill-map: see the Obsidian vault —
> `HVAC ROLL-UP/Prospecting/Sourcing v1 (free version, no Apollo or ZoomInfo).md`

## What it does

```
discover (Google Places) → dedupe → FILTER (buy box) → score → details → store → write Excel
```

| Stage | Source | Fills |
|---|---|---|
| Discover + size | Google Places API | company, address, website, **review count**, rating |
| Filter | pure rules (Organic Legend) | keep 25–500 reviews + operational; drop too-small/too-big/closed |
| Score | pure rules | Buy Box Fit, Priority Tier (**capped at B** in v1) |
| Write | openpyxl | append survivors to `Organic List`, dropdown-safe, dedup by name |

### What v1 deliberately does NOT do
- **No owner contact** (direct mobile / email) — needs Apollo/ZoomInfo (v2).
- **No motivation/intent** — manual / enrichment (v2).
- Every row lands as `Research Stage = New`, `Ready to Hand Off = Not yet`.
  v1 output is a **call-research queue**, not a dial list.

### A note on ROC
The plan was ROC-first, but the AZ ROC license search is a Salesforce/Aura
portal (no clean API). To deliver *real* leads reliably, v1's discovery runs on
**Google Places**. `roc.py` contains the best-effort Playwright collector for
recovering ROC license # + owner (qualifier) name — the next increment.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env must contain GOOGLE_PLACES_API_KEY=...   (gitignored)
```

## Run

Output target is set by `config.WRITE_TARGET`:
- `"gsheet"` (default) → writes to the live Google Sheet "HVAC Database" / Organic
  List via `service_account.json` (gitignored). Re-runs auto-dedupe by company
  name, so each run appends only net-new survivors.
- `"excel"` → writes to the local `.xlsx` instead (auto-closes the workbook first).

```bash
python run.py            # source 10 leads into the Organic List
python run.py 25         # source 25
python cli.py discover   # preview survivors without writing anywhere
```

## Layout

| File | Role |
|---|---|
| `config.py` | cities, trades, buy-box thresholds, paths, `.env` loader |
| `places.py` | Google Places Text Search + Place Details (stdlib urllib) |
| `models.py` | `Lead` dataclass |
| `filter_score.py` | buy-box filter gate + scoring (pure functions) |
| `store.py` | SQLite staging store |
| `excel_writer.py` | dropdown-safe writer into `Organic List` |
| `roc.py` | best-effort AZ ROC Playwright collector (next increment) |
| `pipeline.py` / `run.py` / `cli.py` | orchestration + entry points |

## Safety
- `.env` (the API key) is gitignored and never committed.
- The writer only writes values that match the sheet's data-validation
  dropdowns, and never alters headers, the example row, or formatting.
