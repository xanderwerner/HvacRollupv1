import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "data" / "nm_recon2"
OUT.mkdir(exist_ok=True, parents=True)
captured = []

def on_response(resp):
    if "aura" not in resp.url or "auraFW" in resp.url or "auraCmpDef" in resp.url:
        return
    try:
        req = resp.request
        body = resp.text()
        captured.append({"url": resp.url, "post": req.post_data, "resp": body})
        (OUT / f"call_{len(captured):02d}.json").write_text(json.dumps(captured[-1], indent=1))
    except Exception as e:
        pass

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_page()
    page.on("response", on_response)
    page.goto("https://nmrldlpi.my.site.com/bcd/s/license-list-request", timeout=60000)
    page.wait_for_timeout(4000)
    try:
        page.locator("text=Select Board").first.click(timeout=5000)
        page.wait_for_timeout(2000)
    except Exception as e:
        print("click failed:", e)
    print(f"captured {len(captured)} aura calls")
    b.close()
