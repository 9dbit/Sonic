"""Render deterministic SONIC icons and social preview from the existing logo SVG."""
from pathlib import Path
import struct
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/"web"
svg=(WEB/"sonic-mark.svg").read_text(encoding="utf-8")
assert 'viewBox="0 0 160 180"' in svg
mark=svg.replace('viewBox="0 0 160 180"','viewBox="0 0 160 160"',1)
mark=mark.replace("</svg>","<style>*{animation:none!important;transition:none!important}</style></svg>",1)
common="html,body{margin:0;overflow:hidden}*{box-sizing:border-box}body{font-family:'Segoe UI',Arial,sans-serif}"
def icon_html(s):
    return f"""<style>{common}
    .tile{{height:{s}px;width:{s}px;display:grid;place-items:center;overflow:hidden;
    background:radial-gradient(circle at 50% 47%,#282045 0%,#13112c 50%,#080914 100%)}}
    .logo{{width:96%;height:96%;filter:drop-shadow(0 0 {max(1,s//48)}px #6145a5)}} svg{{width:100%;height:100%}}
    </style><div class="tile"><div class="logo">{mark}</div></div>"""
og_html=f"""<style>{common}
 .canvas{{width:1200px;height:630px;position:relative;overflow:hidden;color:#f9f7ff;
 background:radial-gradient(ellipse 54% 90% at 78% 49%,#24214b 0%,#121126 55%,transparent 95%),
 linear-gradient(118deg,#090911 6%,#0b0a19 56%,#070d1c 100%)}}
 .canvas:before{{content:"";position:absolute;inset:30px;border:1px solid #473b703d;border-radius:35px}}
 .glow{{position:absolute;width:560px;height:560px;right:28px;top:25px;
 background:radial-gradient(circle,#4b409475,transparent 65%);filter:blur(30px)}}
 .orb{{position:absolute;width:425px;height:425px;right:57px;top:94px;
 filter:drop-shadow(0 0 22px #6550a988) drop-shadow(0 0 50px #2545a755)}}
 .orb svg{{width:100%;height:100%}}
 .ring{{position:absolute;width:355px;height:355px;right:94px;top:133px;
 border:1px solid #6d62bd37;border-radius:50%}}
 .copy{{position:absolute;top:105px;left:88px;z-index:2;width:620px}}
 .eyebrow{{font-size:17px;color:#b6a6f5;letter-spacing:.25em;font-weight:700}}
 .title{{font-size:94px;letter-spacing:.18em;font-weight:800;margin:32px 0 28px}}
 .tagline{{font-size:45px;font-weight:750;line-height:1.15;letter-spacing:-.035em}}
 .accent{{display:block;background:linear-gradient(100deg,#d0b2ff,#8c78f1,#58adf5);
 color:transparent;background-clip:text;-webkit-background-clip:text}}
 .description{{max-width:510px;margin-top:25px;font-size:19px;color:#b5b6d1;line-height:1.45}}
 .footer{{position:absolute;left:88px;bottom:72px;color:#a8a6c3;font-size:15px;
 letter-spacing:.2em;font-weight:600}}
 </style><div class="canvas"><div class="glow"></div><div class="ring"></div>
 <div class="orb">{mark}</div><div class="copy"><div class="eyebrow">PRIVATE INTELLIGENCE</div>
 <div class="title">SONIC</div><div class="tagline">Your world.
 <span class="accent">One tap away.</span></div>
 <div class="description">One intelligence space for conversation, voice, knowledge and your workspace.</div></div>
 <div class="footer">NEURAL BRAIN&nbsp; / &nbsp;VOICE&nbsp; / &nbsp;WORKSPACE</div></div>"""
def image_size(b):
    assert b.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II",b[16:24])
def ico_export():
    frames=[]
    for n in (16,32):
        data=(WEB/f"favicon-{n}.png").read_bytes()
        assert image_size(data)==(n,n)
        frames.append((n,data))
    offset=6+16*len(frames)
    directory=struct.pack("<HHH",0,1,len(frames))
    payload=b""
    for n,b in frames:
        directory+=struct.pack("<BBBBHHII",n,n,0,0,1,32,len(b),offset)
        payload+=b;offset+=len(b)
    (WEB/"favicon.ico").write_bytes(directory+payload)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    try:
        for size,name in [(16,"favicon-16.png"),(32,"favicon-32.png"),
                          (180,"apple-touch-icon.png"),(192,"sonic-app-192.png"),
                          (512,"sonic-app-512.png")]:
            page=browser.new_page(viewport={"width":size,"height":size},device_scale_factor=1)
            page.set_content(icon_html(size),wait_until="load")
            page.screenshot(path=str(WEB/name),animations="disabled")
            page.close()
            assert image_size((WEB/name).read_bytes())==(size,size)
            print(name,(WEB/name).stat().st_size)
        page=browser.new_page(viewport={"width":1200,"height":630},device_scale_factor=1)
        page.set_content(og_html,wait_until="load")
        page.screenshot(path=str(WEB/"sonic-og-1200x630.png"),animations="disabled")
        page.close()
        assert image_size((WEB/"sonic-og-1200x630.png").read_bytes())==(1200,630)
        ico_export()
    finally:
        browser.close()
print("OG", (WEB/"sonic-og-1200x630.png").stat().st_size)
print("ICO", (WEB/"favicon.ico").stat().st_size)
