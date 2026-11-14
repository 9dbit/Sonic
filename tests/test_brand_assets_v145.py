"""SONIC brand icon and social share integration contracts."""
from __future__ import annotations
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PNG=b"\x89PNG\r\n\x1a\n"

def dimensions(body):
    assert body.startswith(PNG)
    return struct.unpack(">II",body[16:24])

def test_site_head_exposes_canonical_og_and_favicons(client,monkeypatch):
    origin="https://sonic-web-staging.up.railway.app"
    monkeypatch.setenv("SONIC_PUBLIC_URL",origin)
    response=client.get("/")
    assert response.status_code==200
    html=response.text
    assert "__SONIC_PUBLIC_URL__" not in html
    assert f'<link rel="canonical" href="{origin}/">' in html
    assert f'<meta property="og:url" content="{origin}/">' in html
    expected=origin+"/assets/sonic-og-1200x630.png?v=1.4.7"
    assert f'<meta property="og:image" content="{expected}">' in html
    assert f'<meta name="twitter:image" content="{expected}">' in html
    assert '<meta property="og:image:width" content="1200">' in html
    assert '<meta property="og:image:height" content="630">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<link rel="apple-touch-icon" sizes="180x180"' in html
    assert '<link rel="manifest" href="/site.webmanifest?v=1.4.7">' in html
    assert "/favicon.ico?v=1.4.7" in html
    assert "/assets/favicon-16.png?v=1.4.7" in html
    assert "/assets/favicon-32.png?v=1.4.7" in html
    assert client.get("/api/health").json()["version"]=="1.4.7"

def test_open_preview_and_other_origins_use_their_own_image_url(client,monkeypatch):
    monkeypatch.setenv("SONIC_PUBLIC_URL","https://sonic.example.net")
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    content=client.get("/").text
    assert 'https://sonic.example.net/assets/sonic-og-1200x630.png' in content
    assert 'sonic-web-staging.up.railway.app' not in content
    assert 'class="login-overlay hidden" id="loginOverlay"' in content

def test_public_icon_routes_are_valid_png_ico_and_manifest(client):
    cases=[("/apple-touch-icon.png",(180,180)),
           ("/assets/favicon-16.png",(16,16)),
           ("/assets/favicon-32.png",(32,32)),
           ("/assets/sonic-app-192.png",(192,192)),
           ("/assets/sonic-app-512.png",(512,512)),
           ("/assets/sonic-og-1200x630.png",(1200,630))]
    for path,expected in cases:
        response=client.get(path)
        assert response.status_code==200,(path,response.status_code)
        assert response.headers["content-type"].startswith("image/png")
        assert dimensions(response.content)==expected
    icon=client.get("/favicon.ico")
    assert icon.status_code==200
    assert icon.headers["content-type"]=="image/x-icon"
    reserved,kind,count=struct.unpack("<HHH",icon.content[:6])
    assert (reserved,kind,count)==(0,1,2)
    manifest=client.get("/site.webmanifest")
    assert manifest.status_code==200
    assert "manifest+json" in manifest.headers["content-type"]
    data=manifest.json()
    assert data["name"]=="SONIC | Intelligence Console"
    assert data["display"]=="standalone"
    assert {x["sizes"] for x in data["icons"]}=={"192x192","512x512"}
    for item in data["icons"]:
        assert client.get(item["src"]).status_code==200
