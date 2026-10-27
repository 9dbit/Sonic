"""Browser snapshot of public SONIC staging login, no credentials or mutations."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE="https://sonic-web-staging.up.railway.app/"
OUTPUT=Path("artifacts/sonic-command-deck-live-r1")
OUTPUT.mkdir(parents=True,exist_ok=True)
RESULTS=[]

with sync_playwright() as p:
    executable=shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chrome")
    browser=p.chromium.launch(executable_path=executable or None,headless=True,
                              args=["--no-sandbox","--enable-unsafe-swiftshader"])
    for label,width,height in [("desktop",1440,900),("tablet",820,1000),("mobile",390,844)]:
        page=browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1,
                              is_mobile=label=="mobile",has_touch=label=="mobile")
        failures=[]
        page.on("pageerror",lambda e:failures.append(str(e)))
        response=page.goto(BASE,wait_until="networkidle",timeout=45000)
        assert response is not None and response.status==200
        page.locator("#loginOverlay").wait_for(state="visible",timeout=15000)
        page.locator(".login-card img[alt='SONIC logo']").wait_for(state="visible",timeout=15000)
        assert page.locator("body").get_attribute("class")=="sonic-shell-v100"
        assert page.locator("#loginForm button[type=submit]").is_visible()
        assert not failures,failures
        metrics=page.evaluate("""() => ({
          viewport: innerWidth,
          width: document.documentElement.scrollWidth,
          logoLoaded: document.querySelector('.login-orb img')?.naturalWidth > 0,
          themeApplied: [...document.styleSheets].some(s=>s.href?.includes('sonic-shell-v100.css')),
          loginVisible: getComputedStyle(document.querySelector('#loginOverlay')).display!=='none'
        })""")
        assert metrics["width"] <= width+2,metrics
        assert metrics["logoLoaded"] and metrics["themeApplied"] and metrics["loginVisible"],metrics
        screenshot=OUTPUT/f"{label}-live-login.png"
        page.screenshot(path=str(screenshot),full_page=False)
        print(f"PASS {label} {width}x{height}: live login styled; no overflow/errors; screenshot={screenshot}",flush=True)
        RESULTS.append({"name":label,"size":[width,height],"status":"passed","metrics":metrics})
        page.close()
    browser.close()

(OUTPUT/"report.json").write_text(json.dumps(RESULTS,indent=2))
print("PASS: all public live staging browser snapshots (no authentication)",flush=True)
