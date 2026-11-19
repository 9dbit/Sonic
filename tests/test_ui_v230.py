"""SONIC v2.3 quiet graphite UI safety and regression contracts."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/"web"

def test_theme_loads_last_without_replacing_existing_controllers():
    html=(WEB/"index.html").read_text(encoding="utf-8")
    assert "sonic-ux-v230 sonic-auth-locked" in html
    assert html.index("sonic-ux-v220.css") < html.index("sonic-ux-v230.css") < html.index("sonic-ux-v220.js")
    assert 'id="talkSonic"' in html
    assert 'id="voiceDialog"' in html
    assert 'id="graphStage"' in html

def test_graphite_theme_keeps_blue_for_actions_and_keeps_mobile_nav():
    css=(WEB/"sonic-ux-v230.css").read_text(encoding="utf-8")
    assert "--v22-bg:#090a0c" in css
    assert "--v22-panel:#15171a" in css
    assert ".sidebar .nav.active" in css
    assert ".v22-artifact-card" in css
    assert "#asGenerate" in css
    assert "@media(max-width:720px)" in css
    assert "border-radius:10px!important" in css

def test_sonic_icon_is_static_but_voice_gestures_stay_installed():
    css=(WEB/"sonic-ux-v230.css").read_text(encoding="utf-8")
    motion=(WEB/"motion-core.js").read_text(encoding="utf-8")
    icon=(WEB/"sonic-mark.svg").read_text(encoding="utf-8")
    assert ".sonic-motion-float canvas" in css
    assert "display:none!important" in css
    assert ".v22-orb-fallback:before" in css
    assert "animation:none!important" in css
    assert "this.staticIconMode?0:requestAnimationFrame" in motion
    assert "sonic:invoke" in motion
    assert "sonicHeaderOrb" in motion
    assert "<svg" in icon
    assert "@keyframes" not in icon
    assert "animation:" not in icon
