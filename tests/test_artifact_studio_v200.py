"""Artifact Studio: owner-only storage, bounds, versioning and preview isolation contract."""
import base64

from tests.test_workspace_v088 import owner


def create(client, h, *, name="Sample tool", kind="app", content="<h1>Hello</h1>", mime="text/html"):
    return client.post("/api/artifacts", headers=h, json={"name": name, "kind": kind,
        "content": content, "mime": mime, "source": "manual"})


def test_artifact_owner_boundary_and_no_preview_leak(client):
    assert client.get("/api/artifacts").status_code == 401
    assert client.post("/api/artifacts", json={"name":"x","kind":"app",
        "mime":"text/html","content":"Hello"}).status_code == 401
    h=owner(client)
    assert create(client, {}).status_code == 403
    created=create(client,h).json()
    assert created["version"] == 1 and created["kind"] == "app"
    assert client.get("/api/artifacts").status_code == 200
    entries=client.get("/api/artifacts").json()["items"]
    assert len(entries) == 1 and "content" not in entries[0]
    assert client.get("/api/artifacts/"+created["id"]).json()["content"] == "<h1>Hello</h1>"
    assert client.put("/api/artifacts/"+created["id"], json={"base_version":1,"content":"<p>Modified</p>"}).status_code == 403
    assert client.delete("/api/artifacts/"+created["id"]).status_code == 403
    client.post("/api/logout", headers=h)
    assert client.get("/api/artifacts").status_code == 401
    assert client.get("/api/artifacts/"+created["id"]).status_code == 401


def test_edit_version_immutable_and_stale_rejected(client):
    h=owner(client)
    initial=create(client,h,content="<h1>First</h1>").json()
    url="/api/artifacts/"+initial["id"]
    edited=client.put(url,headers=h,json={"base_version":1,"content":"<h1>Second</h1>"}).json()
    assert edited["version"] == 2
    old=client.get(url,params={"version":1}).json()
    assert old["content"] == "<h1>First</h1>" and old["viewed_version"] == 1
    current=client.get(url).json()
    assert current["content"] == "<h1>Second</h1>"
    assert [v["version"] for v in current["versions"]] == [2,1]
    assert client.put(url,headers=h,json={"base_version":1,"content":"stale"}).status_code == 409
    assert client.get(url+"?version=3").status_code == 404
    assert client.delete(url,headers=h).json()["deleted"]
    assert client.get(url).status_code == 404


def test_external_website_urls_are_https_public_only(client):
    h=owner(client)
    for address in ("http://example.com","javascript:alert(1)","file:///etc/passwd",
        "https://localhost/private","https://127.0.0.1:8443",
        "https://10.0.0.1","https://192.168.1.15",
        "https://example.internal","https://user:pass@example.com",
        "https://example.com:8080","https://example.com:xyz"):
        r=create(client,h,name="bad",kind="website",content=address,mime="text/uri-list")
        assert r.status_code == 422, (address,r.text)
    ok=create(client,h,name="Public ref",kind="website",
       content="https://example.com/docs?id=12",mime="text/uri-list")
    assert ok.status_code == 201 and ok.json()["kind"] == "website"


def test_media_mime_magic_and_quota(client,monkeypatch):
    h=owner(client)
    import sonic.artifact_studio as artifacts
    good=base64.b64encode(b"\x89PNG\r\n\x1a\n"+b"\x00"*60).decode()
    value="data:image/png;base64,"+good
    r=create(client,h,name="Image",kind="image",content=value,mime="image/png")
    assert r.status_code == 201
    assert client.get("/api/artifacts/"+r.json()["id"]).json()["content"] == value
    assert create(client,h,name="Spoof",kind="image",content=value,mime="image/jpeg").status_code == 422
    assert create(client,h,name="Invalid",kind="image",content="data:image/png;base64,AAAA",mime="image/png").status_code in (413,422)
    assert create(client,h,name="Missing",kind="app",content="",mime="text/html").status_code == 422
    monkeypatch.setattr(artifacts,"MAX_ITEMS",1)
    assert create(client,h).status_code == 409


def test_code_is_stored_but_not_executed(client):
    h=owner(client)
    source="import os\nraise RuntimeError('should never run')"
    r=create(client,h,name="Review only",kind="code",content=source,mime="text/plain")
    assert r.status_code == 201
    assert client.get("/api/artifacts/"+r.json()["id"]).json()["content"] == source
    html=client.get("/").text
    assert "id=\"studioPanel\"" in html
    assert "artifact-studio-v200.js" in html
    assert "artifact-studio-v200.css" in html
    assert "frame-src" in client.get("/").headers.get("Content-Security-Policy","")
    assert "media-src 'self' blob: data:" in client.get("/").headers.get("Content-Security-Policy","")


def test_isolated_preview_is_owner_scoped_and_expires(client):
    from datetime import timedelta
    from sonic.db import ArtifactPreview, session_factory, utcnow
    h=owner(client)
    assert client.post("/api/artifacts/previews",json={"content":"<script>alert(1)</script>"}).status_code == 403
    made=client.post("/api/artifacts/previews",headers=h,json={"content":"<div>safe sample</div>"}).json()
    uri=made["url"]
    view=client.get(uri)
    assert view.status_code == 200
    assert "safe sample" in view.text
    csp=view.headers.get("Content-Security-Policy","")
    assert "sandbox allow-scripts" in csp
    assert "connect-src 'none'" in csp
    assert "script-src 'unsafe-inline'" in csp
    assert view.headers.get("X-Frame-Options") == "SAMEORIGIN"
    preview_id=uri.rsplit("/",1)[-1]
    with session_factory()() as db:
        row=db.get(ArtifactPreview,preview_id)
        row.expires_at=utcnow()-timedelta(seconds=1)
        db.commit()
    assert client.get(uri).status_code==404
    client.post("/api/logout",headers=h)
    assert client.get(uri).status_code==401
