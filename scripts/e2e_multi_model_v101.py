"""SONIC model selection in real desktop/mobile browsers and disposable DBs.

All provider credentials are explicitly empty or synthetic. Connectivity-test
HTTP responses are intercepted in the browser before reaching the local server;
no real provider API, production DB or Windows action is called.
"""
import json
import re
import shutil
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from qa_server import local_server


OUT = Path("artifacts/sonic-multi-model-v101")
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = []
DEEPSEEK = "deepseek|deepseek-flash"
BASE_SETTINGS = {
    # Pin each provider fixture independently of the ambient environment.
    # qa_server also strips inherited provider credentials before starting.
    "OPENAI_API_KEY": "",
    "OPENROUTER_API_KEY": "LOCAL-FAKE-OPENROUTER-DO-NOT-SEND",
    "DEEPSEEK_API_KEY": "",
    "SONIC_BRAIN_PROVIDER": "openai",
    "SONIC_MODEL": "gpt-4.1-mini",
    "SONIC_OPENROUTER_MODEL": "z-ai/glm-5.3-prime",
    "SONIC_DEEPSEEK_MODEL": "deepseek-flash",
}


def activate(page, value, sharing_text, *, test_pending=False):
    """Use the real owner/CSRF selection endpoint; no provider is invoked."""
    page.locator("#brainModelSelect").select_option(value)
    expect(page.locator("#applyBrainModel")).to_be_enabled()
    dialogs = []

    def consent(dialog):
        dialogs.append(dialog.message)
        dialog.accept()

    page.once("dialog", consent)
    page.locator("#applyBrainModel").click()
    assert len(dialogs) == 1
    assert sharing_text in dialogs[0], dialogs[0]
    assert "Memory Vault" in dialogs[0] and "hasilnya" in dialogs[0]
    assert "OpenAI Realtime Voice dan Vision tidak berubah" in dialogs[0]
    provider, model = value.split("|", 1)
    expect(page.locator("#brainModelStatus")).to_contain_text(provider + " / " + model + ".")
    expect(page.locator("#brainPill")).to_contain_text(model)
    if test_pending:
        expect(page.locator("#testProvider")).to_be_disabled()
    else:
        expect(page.locator("#testProvider")).to_be_enabled()


def verify_layout(page):
    metrics = page.evaluate("""() => ({
      viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
      selected:document.querySelector('#brainModelSelect').value,
      usage:document.querySelector('#brainModelMetrics').innerText,
      animationAnchor:!!document.querySelector('#sonicMotionAnchor'),
      neuralGraph:!!document.querySelector('#graphStage'),
      liveVoice:!!document.querySelector('#voiceSessionBar'),
    })""")
    assert metrics["documentWidth"] <= metrics["viewport"] + 2, metrics
    assert metrics["animationAnchor"] and metrics["neuralGraph"] and metrics["liveVoice"]
    assert "Belum ada panggilan model" in metrics["usage"]


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=shutil.which("chromium") or shutil.which("google-chrome") or None,
        headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    for scenario, deepseek_key in (
        ("deepseek-missing-key", ""),
        ("deepseek-configured", "LOCAL-FAKE-DEEPSEEK-DO-NOT-SEND"),
    ):
        settings = {**BASE_SETTINGS, "DEEPSEEK_API_KEY": deepseek_key}
        with local_server(settings=settings) as (url, owner_token):
            for viewport, size in (("desktop", {"width": 1440, "height": 900}),
                                   ("mobile", {"width": 390, "height": 844})):
                page = browser.new_page(viewport=size, device_scale_factor=1,
                                        is_mobile=viewport == "mobile",
                                        has_touch=viewport == "mobile")
                errors = []
                test_calls = []
                test_outcomes = []
                pending_tests = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def intercepted_test(route):
                    # This also blocks an unintended automatic test from ever
                    # reaching the backend or spending provider tokens.
                    request = route.request
                    test_calls.append({"method": request.method,
                                       "csrf_present": bool(request.headers.get("x-sonic-csrf"))})
                    assert request.method == "POST"
                    assert request.post_data_json == {}
                    assert test_calls[-1]["csrf_present"]
                    if not test_outcomes:
                        route.fulfill(status=409, json={"detail": "Unexpected fixture test blocked"})
                        return
                    outcome = test_outcomes.pop(0)
                    if outcome == "deferred-success":
                        pending_tests.append(route)
                    else:
                        route.fulfill(status=502, json={"detail":
                            "Synthetic DeepSeek connection failed (HTTP 401)"})

                page.route("**/api/setup/test-provider", intercepted_test)
                page.goto(url, wait_until="networkidle")
                page.locator("#ownerToken").fill(owner_token)
                page.locator("#loginForm button[type=submit]").click()
                expect(page.locator("#loginOverlay")).to_have_class(re.compile("hidden"), timeout=12000)
                page.locator('.nav[data-tab="setup"]').click()
                expect(page.locator("#brainModelControl")).to_be_visible()
                expect(page.locator("#brainModelSelect option")).to_have_count(5)
                key_row = page.locator('#brainProviderStatus [data-provider="deepseek"]')
                expect(key_row).to_contain_text("DeepSeek")
                expect(key_row).to_contain_text("DEEPSEEK_API_KEY")
                expect(page.locator(".setup-help")).to_contain_text("Railway")
                expect(page.locator(".setup-help")).to_contain_text("DEEPSEEK_API_KEY")
                assert not test_calls, "Login/readiness must not trigger a provider test"

                if not deepseek_key:
                    expect(page.locator(f'#brainModelSelect option[value="{DEEPSEEK}"]')).to_be_disabled()
                    expect(key_row).to_contain_text("Key belum diisi")
                    model = "z-ai/glm-5.3-prime" if viewport == "desktop" else "z-ai/glm-5.3"
                    if viewport == "desktop":
                        expect(page.locator("#testProvider")).to_be_disabled()
                    else:
                        expect(page.locator("#brainModelStatus")).to_contain_text("z-ai/glm-5.3-prime")
                    activate(page, "openrouter|" + model, "ke OpenRouter serta penyedia model")
                    selection = "openrouter|" + model
                else:
                    expect(page.locator(f'#brainModelSelect option[value="{DEEPSEEK}"]')).to_be_enabled()
                    expect(key_row).to_contain_text("Key terkonfigurasi")
                    if viewport == "mobile":
                        # This viewport observes the preceding owner's persisted
                        # DeepSeek choice, then exercises both directions again.
                        expect(page.locator("#brainModelSelect")).to_have_value(DEEPSEEK)
                        expect(page.locator("#applyBrainModel")).to_be_disabled()
                        activate(page, "openrouter|z-ai/glm-5.3", "ke OpenRouter serta penyedia model")
                    activate(page, DEEPSEEK, "langsung ke DeepSeek")
                    expect(page.locator("#setupList")).to_contain_text("Selected DeepSeek key configured")
                    assert not test_calls, "Model selection must not trigger a provider test"
                    # Only these deliberate clicks receive simulated connection
                    # results. This is frontend feedback QA, not a live test.
                    test_outcomes.append("deferred-success")
                    page.locator("#testProvider").click()
                    expect(page.locator("#setupMessage")).to_contain_text("Testing selected chat model")
                    expect(page.locator("#testProvider")).to_be_disabled()
                    activate(page, "openrouter|z-ai/glm-5.3", "ke OpenRouter serta penyedia model", test_pending=True)
                    assert len(pending_tests) == 1
                    pending_tests.pop().fulfill(status=200, json={"verified": True, "provider": "deepseek",
                                                                "model": "deepseek-flash"})
                    expect(page.locator("#setupMessage")).to_contain_text("Connection test passed: DeepSeek / deepseek-flash.")
                    expect(page.locator("#setupMessage")).to_contain_text("Only this chat model was tested")
                    expect(page.locator("#brainModelSelect")).to_have_value("openrouter|z-ai/glm-5.3")
                    expect(page.locator("#testProvider")).to_be_enabled()
                    activate(page, DEEPSEEK, "langsung ke DeepSeek")
                    test_outcomes.append("failure")
                    page.locator("#testProvider").click()
                    expect(page.locator("#setupMessage")).to_contain_text("Synthetic DeepSeek connection failed")
                    expect(key_row).to_contain_text("Key terkonfigurasi")
                    assert len(test_calls) == 2 and not test_outcomes and not pending_tests
                    selection = DEEPSEEK

                verify_layout(page)
                page.screenshot(path=str(OUT / f"{scenario}-{viewport}.png"), full_page=False)
                page.reload(wait_until="networkidle")
                page.locator('.nav[data-tab="setup"]').click()
                expect(page.locator("#brainModelSelect")).to_have_value(selection)
                expect(page.locator("#brainModelStatus")).to_contain_text(selection.split("|", 1)[1])
                assert len(test_calls) == (2 if deepseek_key else 0)
                assert not errors, errors
                RESULTS.append({"scenario": scenario, "viewport": viewport,
                                "selection_persists": True,
                                "deepseek_key_configured": bool(deepseek_key),
                                "connection_feedback": "synthetic success and failure" if deepseek_key else "not invoked",
                                "intercepted_explicit_test_calls": len(test_calls),
                                "no_paid_calls_or_windows_actions": True,
                                "voice_untouched": True, "animation_nodes_present": True,
                                "no_horizontal_overflow": True, "javascript_errors": errors})
                page.close()
    browser.close()

(OUT / "report.json").write_text(json.dumps(RESULTS, indent=2))
print(json.dumps(RESULTS, indent=2))
