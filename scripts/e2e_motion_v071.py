"""SONIC V0.7.1 visual QA: real Canvas pixels, cyan emission, mobile and desktop.

Uses a disposable local owner session and SQLite DB; never calls production
OpenAI endpoints, captures private desktop data, or touches TRADEVICEPC apps.
"""
import json
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT = Path("artifacts/motion-v071")
OUT.mkdir(parents=True, exist_ok=True)

with local_server() as (url, token), sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=shutil.which("chromium") or None,
        headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
    )
    results = []
    for name, viewport in [
        ("desktop", {"width": 1440, "height": 900}),
        ("mobile", {"width": 390, "height": 844}),
    ]:
        page = browser.new_page(
            viewport=viewport, device_scale_factor=1,
            is_mobile=name == "mobile", has_touch=name == "mobile"
        )
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(url, wait_until="networkidle")
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_have_class(__import__("re").compile(".*hidden.*"))
        core = page.locator("#sonicMotionFloat")
        expect(core).to_be_visible()
        page.wait_for_timeout(450)
        sample = page.evaluate("""() => {
            const m=window.sonicMotion, c=m.canvas;
            const pixels=m.ctx.getImageData(0,0,c.width,c.height).data;
            let opaque=0, cyan=0, white=0;
            for(let i=0;i<pixels.length;i+=4) {
                const [r,g,b,a]=pixels.slice(i,i+4);
                if(a < 24)continue;
                opaque++;
                if(g>=r+8 && b>=g-6)cyan++;
                if(r>=248 && g>=248 && b>=248)white++;
            }
            const t=performance.now();
            for(let j=0;j<8;j++)m.draw();
            return {
                count:m.points.length,
                spriteSize:m.sprite.width,
                coreColor:m.visual.coreCyan,
                glowColor:m.visual.glowCyan,
                imageWidth:c.width,
                imageHeight:c.height,
                opaquePixels:opaque,
                cyanPixels:cyan,
                whitePixels:white,
                cyanRatio:opaque?cyan/opaque:0,
                avgDrawMilliseconds:(performance.now()-t)/8,
                backgroundTransparent:getComputedStyle(c).backgroundColor==='rgba(0, 0, 0, 0)'
            };
        }""")
        assert sample["count"] == 2940, sample
        assert sample["spriteSize"] == 64, sample
        assert sample["opaquePixels"] > 130, sample
        assert sample["cyanPixels"] > 80, sample
        assert sample["cyanRatio"] > 0.25, sample
        assert sample["avgDrawMilliseconds"] < 180, sample
        page.screenshot(path=str(OUT / f"sonic-cyan-{name}.png"), full_page=False)
        core.click(force=True)
        page.wait_for_timeout(55)
        core.click(force=True)
        assert page.evaluate("window.sonicMotion.focused") is True
        page.evaluate("window.sonicMotion.setState('speaking')")
        page.wait_for_timeout(160)
        page.screenshot(path=str(OUT / f"sonic-cyan-{name}-focus.png"), full_page=False)
        page.evaluate("window.sonicMotion.handleCommand('SONIC, kembali ke tempat semula')")
        assert page.evaluate("window.sonicMotion.focused") is False
        assert not errors, errors
        results.append({"viewport": name, "render": sample, "motion_and_focus": True, "page_errors": errors})
        page.close()
    browser.close()
    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
