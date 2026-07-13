#!/usr/bin/env python3
"""Recon: drive the NM RLD public search portal, capture the Aura API calls."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "data" / "nm_recon"
OUT.mkdir(exist_ok=True, parents=True)

captured = []

def on_response(resp):
    if "aura" not in resp.url or "auraFW" in resp.url or "auraCmpDef" in resp.url or "auraAF" in resp.url:
        return
    try:
        req = resp.request
        body = resp.text()
        captured.append({
            "url": resp.url,
            "status": resp.status,
            "post": (req.post_data or "")[:8000],
            "resp_head": body[:2000],
            "resp_len": len(body),
        })
        (OUT / f"call_{len(captured):02d}.json").write_text(
            json.dumps({"url": resp.url, "post": req.post_data, "resp": body}, indent=1)
        )
    except Exception as e:
        captured.append({"url": resp.url, "err": str(e)})


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_page()
    page.on("response", on_response)
    page.goto("https://nmrldlpi.my.site.com/bcd/s/rld-public-search", timeout=60000)
    page.wait_for_timeout(4000)
    n_before = len(captured)

    # Click the Profession dropdown to trigger option loading
    try:
        page.locator("text=Select a Profession").first.click(timeout=5000)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "profession_dropdown.png"))
    except Exception as e:
        print("profession click failed:", e)

    print(f"captured {len(captured)} aura calls ({n_before} pre-click)")
    b.close()
