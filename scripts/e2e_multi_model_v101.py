"""SONIC Multi-Model Router UI smoke on disposable local DB only.

Synthetic OpenRouter key is never sent to any external provider. This test only
changes the owner's local model preference, with no paid model calls.
"""
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT = Path("artifacts/sonic-multi-model-v101")
OUT.mkdir(parents=True, exist_ok=True)
result = []

with local_server(settings={"OPENROUTER_API_KEY": "LOCAL-FAKE-KEY-DO-NOT-SEND"}) as (url, token), sync_playwright() as p:
    browser = p.chromium.launch(executable_path=shutil.which("chromium") or
                                shutil.which("google-chrome") or None,
                                headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    for name, size in (("desktop", {"width": 1440, "height": 900}),
                       ("mobile", {"width": 390, "height": 844})):
        page = browser.new_page(viewport=size, device_scale_factor=1,
                                is_mobile=name == "mobile", has_touch=name == "mobile")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="networkidle")
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_have_class(re.compile("hidden"), timeout=12000)
        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator("#brainModelControl")).to_be_visible()
        expect(page.locator("#brainModelSelect option")).to_have_count(4)
        # Both viewports share this disposable DB: desktop selects Prime,
        # then mobile observes the persisted Prime and switches to Standard.
        initial_provider="openai" if name=="desktop" else "openrouter"
        model="z-ai/glm-5.3-prime" if name=="desktop" else "z-ai/glm-5.3"
        expect(page.locator("#brainModelStatus")).to_contain_text(initial_provider)
        if name=="desktop":
            assert page.locator("#testProvider").is_disabled(), "Missing OpenAI key must not pass a live test"
        else:
            expect(page.locator("#brainModelStatus")).to_contain_text("z-ai/glm-5.3-prime")

        page.locator("#brainModelSelect").select_option("openrouter|"+model)
        expect(page.locator("#applyBrainModel")).to_be_enabled()
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#applyBrainModel").click()
        expect(page.locator("#brainModelStatus")).to_contain_text(model, timeout=12000)
        expect(page.locator("#brainPill")).to_contain_text(model)
        expect(page.locator("#testProvider")).to_be_enabled()
        assert "Voice tetap OpenAI" in page.locator("#brainModelStatus").inner_text()
        metrics = page.evaluate("""() => ({
          viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
          selected: document.querySelector('#brainModelSelect').value,
          usage:document.querySelector('#brainModelMetrics').innerText,
          animationAnchor:!!document.querySelector('#sonicMotionAnchor'),
          neuralGraph:!!document.querySelector('#graphStage'),
          liveVoice:!!document.querySelector('#voiceSessionBar'),
        })""")
        assert metrics["documentWidth"] <= metrics["viewport"] + 2, metrics
        assert metrics["animationAnchor"] and metrics["neuralGraph"] and metrics["liveVoice"]
        assert "Belum ada panggilan model" in metrics["usage"]
        page.screenshot(path=str(OUT / f"{name}-settings.png"), full_page=False)

        page.reload(wait_until="networkidle")
        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator("#brainModelStatus")).to_contain_text(model)
        expect(page.locator("#brainModelSelect")).to_have_value("openrouter|"+model)
        assert not errors, errors
        result.append({"viewport": name, "selection_persists": True,
                       "no_paid_calls_or_windows_actions": True,
                       "voice_untouched": True, "animation_nodes_present": True,
                       "no_horizontal_overflow": True, "javascript_errors": errors})
        page.close()
    browser.close()

(OUT / "report.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
