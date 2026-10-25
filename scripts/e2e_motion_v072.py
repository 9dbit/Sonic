"""SONIC V0.7.2 isolated Chrome visual/performance regression.

Uses ephemeral owner auth and database. Does not touch the deployed SONIC,
the real TRADEVICEPC applications, microphones, or any model provider.
"""
import json
import re
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUTPUT = Path("artifacts/motion-v072")
OUTPUT.mkdir(parents=True, exist_ok=True)

with local_server() as (url, token), sync_playwright() as playwright:
    chrome = shutil.which("chromium") or shutil.which("chrome")
    if not chrome:
        for candidate in (
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ):
            if candidate.is_file():
                chrome = str(candidate)
                break
    browser = playwright.chromium.launch(
        executable_path=chrome or None,
        headless=True,
        args=["--no-sandbox", "--enable-unsafe-swiftshader"],
    )
    observations = []
    for label, viewport in [
        ("desktop", {"width": 1440, "height": 900}),
        ("mobile", {"width": 390, "height": 844}),
    ]:
        page = browser.new_page(
            viewport=viewport,
            device_scale_factor=1,
            is_mobile=label == "mobile",
            has_touch=label == "mobile",
        )
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        assert page.title().startswith("SONIC")
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_have_class(re.compile(".*hidden.*"))
        page.locator('.nav[data-tab="brain"]').click()
        expect(page.locator("#sonicMotionFloat")).to_be_visible()
        page.wait_for_timeout(440)
        sample = page.evaluate("""() => {
          const core=window.sonicMotion, c=core.canvas, ctx=core.ctx;
          const style=e=>getComputedStyle(document.querySelector(e));
          const pixels=ctx.getImageData(0,0,c.width,c.height).data;
          const distinct=new Set();
          let visible=0, cyanBlue=0, orange=0, white=0;
          for(let p=0;p<pixels.length;p+=4) {
            const r=pixels[p],g=pixels[p+1],b=pixels[p+2],a=pixels[p+3];
            if(a<28)continue;
            visible++;
            if(b>=g-3 && g>=r-3 && b>=190)cyanBlue++;
            if(r>200&&g<155&&b<150)orange++;
            if(r>=245&&g>=245&&b>=245)white++;
            if(a>80)distinct.add(r+','+g+','+b);
          }
          const diameter=window.SonicMotionMath.particleDiameter(178,.65);
          const old=Math.min(9.5,Math.max(.95,(178/190)*(.72+.66*.65)*1.68));
          const start=performance.now();
          for(let n=0;n<10;n++)core.draw();
          const average=(performance.now()-start)/10;
          return {
            particleCount:core.points.length,
            oldPointCount:core.visual.previousCount,
            pointSizeRatio:diameter/old,
            paletteEntries:core.palette.length,
            usesSprite:!!core.sprite,
            visiblePixels:visible,
            cyanBluePixels:cyanBlue,
            cyanBlueRatio:visible?cyanBlue/visible:0,
            distinctiveColors:distinct.size,
            orangePixels:orange,
            whitePixels:white,
            avgFrameMs:average,
            noGlow:style('#sonicMotionFloat canvas').filter==='none' &&
                   ctx.shadowBlur===0 && ctx.globalCompositeOperation==='source-over',
            canvasTransparent:style('#sonicMotionFloat canvas').backgroundColor==='rgba(0, 0, 0, 0)',
            bodyBlack:style('body').backgroundColor==='rgb(0, 0, 0)',
            graphBlack:style('#brainPanel').backgroundColor==='rgb(0, 0, 0)',
            headerGrey:style('.topbar').backgroundColor==='rgb(20, 20, 20)',
            panelGrey:style('.brain-side').backgroundColor==='rgb(23, 23, 23)',
            panelBorderless:style('.brain-side').borderTopWidth==='0px',
            solidBlueButton:style('#talkSonic').backgroundColor==='rgb(21, 107, 255)' &&
              style('#talkSonic').backgroundImage==='none',
            activeNavSolid:style('.nav.active').backgroundColor==='rgb(21, 107, 255)',
            blueLabel:style('.top-title .eyebrow').color==='rgb(77, 163, 255)',
            orangeOfflineText:style('.pill.offline').color==='rgb(255, 159, 47)',
            textWhite:style('body').color==='rgb(255, 255, 255)',
            version:document.querySelector('.top-title .eyebrow').textContent,
            canvasSize:[c.width,c.height]
          };
        }""")
        assert sample["particleCount"] == 5880, sample
        assert sample["oldPointCount"] == 2940, sample
        assert abs(sample["pointSizeRatio"] - .5) < .0000001, sample
        assert sample["paletteEntries"] == 48, sample
        assert sample["usesSprite"] is False, sample
        assert sample["visiblePixels"] > 50, sample
        assert sample["cyanBlueRatio"] > .94, sample
        assert sample["distinctiveColors"] >= 12, sample
        assert sample["orangePixels"] == 0, sample
        assert sample["whitePixels"] == 0, sample
        assert sample["avgFrameMs"] < 120, sample
        for key in [
            "noGlow", "canvasTransparent", "bodyBlack", "graphBlack",
            "headerGrey", "panelGrey", "panelBorderless",
            "solidBlueButton", "activeNavSolid", "blueLabel",
            "orangeOfflineText", "textWhite",
        ]:
            assert sample[key], (label, key, sample)
        assert "0.7.2" in sample["version"], sample
        page.screenshot(path=str(OUTPUT / f"sonic-v072-{label}.png"), full_page=False)
        orb = page.locator("#sonicMotionFloat")
        orb.click(force=True)
        page.wait_for_timeout(55)
        orb.click(force=True)
        assert page.evaluate("window.sonicMotion.focused") is True
        page.evaluate("window.sonicMotion.setState('speaking')")
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUTPUT / f"sonic-v072-{label}-focused.png"), full_page=False)
        page.evaluate("window.sonicMotion.handleCommand('SONIC, kembali ke tempat semula')")
        assert page.evaluate("window.sonicMotion.focused") is False
        page.locator('.nav[data-tab="chat"]').click()
        assert page.evaluate("getComputedStyle(document.querySelector('#chatPanel')).backgroundColor") == "rgb(0, 0, 0)"
        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator("#taskManagerPanel")).to_be_visible()
        assert not page_errors, page_errors
        observations.append({
            "viewport": label,
            "render": sample,
            "focusVoiceReturn": True,
            "chatAndDeviceTabs": True,
            "pageErrors": page_errors,
        })
        page.close()
    browser.close()
    (OUTPUT / "report.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
    print(json.dumps(observations, indent=2))
