"""SONIC 1.8 Hugging Face Hub API and security regression."""
from tests.test_auth_and_api import auth
from sonic import huggingface_hub as hf


def mock_model(model_id=hf.PINNED):
    return {
        "id":model_id,"downloads":52345,"likes":350,"gated":False,"private":False,
        "pipeline_tag":"text-generation","cardData":{"license":"apache-2.0"},
        "siblings":[
            {"rfilename":"Model.Q4_K_M.gguf","size":5780092768},
            {"rfilename":"Model.Q8_0.gguf","size":9800000000},
            {"rfilename":"../../../etc/password.gguf","size":12345},
            {"rfilename":"readme.md","size":152},
        ]
    }


def test_hf_public_preview_cannot_enumerate_models(client, monkeypatch):
    calls=[]
    monkeypatch.setattr(hf,"hub_fetch",lambda *a,**kw:calls.append((a,kw)))
    assert client.get("/api/huggingface/search?q=Qwen").status_code==401
    assert client.get("/api/huggingface/model/a/b").status_code==401
    assert client.get("/api/huggingface/local").status_code==401
    assert calls==[]


def test_hf_owner_search_and_bounded_public_metadata(client, monkeypatch):
    auth(client)
    calls=[]
    def fake(path,*,params=None):
        calls.append((path,params))
        return [mock_model(), mock_model("unsloth/Qwen3.5-9B-GGUF")]
    monkeypatch.setattr(hf,"hub_fetch",fake)
    q=client.get("/api/huggingface/search?q=Qwen3.5+GGUF&limit=6")
    assert q.status_code==200,q.text
    data=q.json()
    assert data["count"]==2 and data["read_only"] is True
    assert calls[0][0]=="/api/models"
    assert calls[0][1]["limit"]==6
    assert data["results"][0]["installed_in_sonic"]
    assert not data["results"][1]["can_activate"]
    assert data["results"][0]["files"]==[
        {"filename":"Model.Q4_K_M.gguf","bytes":5780092768},
        {"filename":"Model.Q8_0.gguf","bytes":9800000000},
    ]
    assert client.get("/api/huggingface/search?q=A").status_code==422
    assert client.get("/api/huggingface/search?q=foo&limit=100").status_code==422


def test_hf_repo_validation_and_owner_detail(client,monkeypatch):
    auth(client)
    observed=[]
    def fake(path,*,params=None):
        observed.append((path,params))
        return mock_model()
    monkeypatch.setattr(hf,"hub_fetch",fake)
    out=client.get("/api/huggingface/model/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF")
    assert out.status_code==200,out.text
    assert out.json()["license"]=="apache-2.0"
    assert observed==[("/api/models/"+hf.PINNED,{"blobs":"true"})]
    assert client.get("/api/huggingface/model/bad%20id/repo").status_code in (404,422)


def test_hf_local_status_reuses_readonly_broker(client):
    auth(client)
    r=client.get("/api/huggingface/local")
    assert r.status_code==200
    assert r.json()["catalog_read_only"] is True
    assert r.json()["operations"]==["start","stop","use_for_chat"]
    assert r.json()["repo"]==hf.PINNED
    # Hub API exposes no repository download or arbitrary model-run endpoint.
    assert client.post("/api/huggingface/download",json={"url":"http://localhost"}).status_code==404
    assert client.post("/api/huggingface/model/activate",json={"name":"a/b"}).status_code==404


def test_hf_markup_owner_ui_exists_and_loads_after_legacy(client):
    html=client.get("/").text
    assert 'id="huggingFaceHub"' in html
    assert 'id="hfSearchInput"' in html
    assert 'id="hfStartPinned"' in html
    assert "huggingface-v180.js" in html
    assert "huggingface-v180.css" in html
