#!/usr/bin/env python3
"""Browser smoke checks using disposable local fixtures, never real credentials.
Chromium desktop + WebKit mobile viewport; not a physical-iPhone verification.
Run: python -m scripts.e2e_browser (after installing Playwright and browsers).
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from scripts.e2e_smoke import local_server


def run():
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    outcomes = []
    with sync_playwright() as playwright:
        for name, browser_type, options in [
            ("desktop", playwright.chromium, {"viewport": {"width": 1440, "height": 1000}}),
            ("mobile", playwright.webkit, {"viewport": {"width": 390, "height": 844},
                "device_scale_factor": 2, "is_mobile": True, "has_touch": True})
        ]:
            with local_server() as (base, owner, _device, _env, _restart):
                browser = browser_type.launch()
                context = browser.new_context(**options)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(base)
                    page.locator("#ownerToken").fill(owner)
                    page.locator("#loginForm button").click()
                    expect(page.locator("#setupPanel")).to_be_visible()
                    expect(page.locator("#setupList")).to_contain_text("Persistent database")
                    expect(page.locator("#testProvider")).to_be_disabled()
                    assert page.locator("#ownerToken").input_value() == ""
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    page.screenshot(path=str(artifacts / ("sonic-" + name + "-setup.png")), full_page=True)
                    page.locator('[data-tab="memory"]').click()
                    page.locator("#memoryInput").fill("Disposable SONIC browser test note")
                    page.locator('#memoryForm button').click()
                    expect(page.locator("#memoryList")).to_contain_text("Disposable SONIC browser test note")
                    page.reload()
                    expect(page.locator("#setupPanel")).to_be_visible()
                    page.locator('[data-tab="memory"]').click()
                    expect(page.locator("#memoryList")).to_contain_text("Disposable SONIC browser test note")
                    page.once("dialog", lambda dialog: dialog.accept())
                    page.locator('#memoryList button').click()
                    expect(page.locator("#memoryList")).to_contain_text("No memories saved")
                    page.locator('[data-tab="setup"]').click()
                    page.locator("#setupLogout").click()
                    expect(page.locator("#loginOverlay")).to_be_visible()
                    assert not errors, "Browser errors: " + json.dumps(errors)
                    outcomes.append({"viewport": name, "status": "PASS", "javascript_errors": 0})
                finally:
                    context.close()
                    browser.close()
    print(json.dumps({"browser_checks": outcomes, "live_openai_tested": False,
                      "physical_iphone_tested": False}))


if __name__ == "__main__":
    run()
