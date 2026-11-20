"""SONIC v2.3.1 owner/preview, compact mobile and static voice contracts."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/"web"

def test_v231_loaded_after_graphite_without_changing_auth_lock_token():
    html=(WEB/"index.html").read_text(encoding="utf-8")
    assert "sonic-ux-v231 sonic-ux-v230 orbit-v140 sonic-auth-locked" in html
    assert html.index("sonic-ux-v230.css")<html.index("sonic-ux-v231.css")
    assert html.index("sonic-ux-v220.js")<html.index("sonic-ux-v231.js")
    assert 'href="/owner"' not in html  # generated only for preview mode

def test_owner_required_for_studio_and_public_picker_reuses_existing_state():
    js=(WEB/"sonic-ux-v231.js").read_text(encoding="utf-8")
    assert "sonic-open-preview" in js
    assert "a.href='/owner'" in js
    assert "model.append(picker)" in js
    assert "'asGenerate'" in js
    assert "window.sonicMotion?.returnHome?.()" in js
    assert "fetch(" not in js  # no new data flow

def test_mobile_has_single_static_mark_and_focus_stage():
    css=(WEB/"sonic-ux-v231.css").read_text(encoding="utf-8")
    assert "#sonicFocusShade::after" in css
    assert "sonic-mark.svg?v=2.3.1" in css
    assert ".sonic-motion-float:not(.focused)" in css
    assert "body.sonic-ux-v231.sonic-focused .sidebar" in css
    assert "@media(max-width:720px)" in css
