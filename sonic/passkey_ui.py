"""Small, server-rendered integration with the existing SONIC shell.

Keep the reviewed base HTML and its UI controllers intact. Passwordless mode
replaces the login panel, but retains hidden legacy element IDs so the existing
controller remains compatible. The token endpoint separately rejects login.
"""
from .passkeys import enabled
from .config import setting

LOGIN = '''<div class="login-overlay" id="loginOverlay"><div class="login-card">
<div class="login-orb"><img src="/assets/sonic-mark.svg?v=1.4.1" width="68" height="68" alt="SONIC logo"></div>
<span class="eyebrow">SONIC / PRIVATE INTELLIGENCE</span>
<h2>Your world.<br><span class="gradient-heading">One tap away.</span></h2>
<p>Masuk tanpa mengetik token. Gunakan passkey dengan Face ID, Touch ID, Windows Hello, atau kunci keamanan.</p>
<button id="passkeyLogin" type="button" class="passkey-primary" disabled>Continue with passkey</button>
<button id="passkeySetup" type="button" class="passkey-primary" hidden>Aktifkan passkey perangkat ini</button>
<p id="passkeyLoginState" class="passkey-message" role="status">Memeriksa akses...</p>
<span id="loginError" role="alert"></span>
<form id="loginForm" hidden><input id="ownerToken" type="password" autocomplete="off" disabled><button type="submit" disabled>Legacy login disabled</button></form>
<small>PRIVATE ACCESS / PASSKEY</small>
</div></div>'''

MANAGE = '''<section class="passkey-manage" aria-label="Passkey dan akses perangkat">
<h3>Masuk tanpa token</h3><p>Daftarkan passkey tambahan dari sesi ini. Data biometrik dan private key tidak dikirim ke SONIC.</p>
<button id="passkeyRegister" type="button">Tambahkan passkey</button>
<p id="passkeyMessage" class="passkey-message" role="status"></p><div id="passkeyList"></div>
</section>'''


def render(html: str, version: str) -> str:
    html = html.replace("<b>V1.2.0</b>", f"<b>V{version}</b>")
    html = html.replace("VERSION 1.2.0", f"VERSION {version}")
    if setting("SONIC_OPEN_PREVIEW", "false").lower() == "true":
        html = html.replace('<div class="login-overlay" id="loginOverlay">',
                            '<div class="login-overlay hidden" id="loginOverlay">', 1)
        return html
    if not enabled():
        return html
    start = html.index('  <div class="login-overlay" id="loginOverlay">')
    end = html.index('\n</body>', start)
    html = html[:start] + LOGIN + html[end:]
    html = html.replace('<section id="personaStudio"', MANAGE + '\n<section id="personaStudio"', 1)
    html = html.replace('</head>', '<link rel="stylesheet" href="/assets/passkey-login.css?v=1.3.0">\n</head>', 1)
    html = html.replace('</body>', '<script src="/assets/passkey-login.js?v=1.3.0" defer></script>\n</body>', 1)
    return html
