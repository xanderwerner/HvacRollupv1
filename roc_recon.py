#!/usr/bin/env python3
"""Recon: drive the AZ ROC contractor-search portal once, capture the Aura API calls."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "data" / "roc_recon"
OUT.mkdir(exist_ok=True)
QUERY = sys.argv[1] if len(sys.argv) > 1 else "Ground Zero Plumbing"

captured = []


def on_response(resp):
    if "aura" not in resp.url:
        return
    try:
        req = resp.request
        body = resp.text()
        captured.append(
            {
                "url": resp.url,
                "status": resp.status,
                "post": (req.post_data or "")[:8000],
                "resp_head": body[:4000],
                "resp_len": len(body),
            }
        )
        (OUT / f"call_{len(captured):02d}.json").write_text(
            json.dumps({"url": resp.url, "post": req.post_data, "resp": body}, indent=1)
        )
    except Exception as e:
        captured.append({"url": resp.url, "err": str(e)})


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_page()
    page.on("response", on_response)
    page.goto("https://azroc.my.site.com/AZRoc/s/contractor-search", timeout=60000)
    page.wait_for_timeout(6000)
    n_before = len(captured)
    # find the search box
    for sel in ["input[type='search']", "input[placeholder*='earch']", "input.slds-input", "input"]:
        try:
            box = page.locator(sel).first
            box.wait_for(timeout=5000)
            box.fill(QUERY)
            box.press("Enter")
            print(f"searched via {sel}", flush=True)
            break
        except Exception:
            continue
    page.wait_for_timeout(10000)
    page.screenshot(path=str(OUT / "after_search.png"), full_page=True)
    b.close()

print(f"captured {len(captured)} aura calls ({n_before} pre-search)")
for i, c in enumerate(captured, 1):
    marker = ""
    if "post" in c and c.get("post") and ("earch" in c["post"] or "icense" in c["post"]):
        marker = "  <-- search-ish"
    print(f"{i:02d} status={c.get('status')} len={c.get('resp_len')}{marker}")
