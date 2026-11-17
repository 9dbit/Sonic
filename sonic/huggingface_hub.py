"""SONIC Hugging Face Hub: owner-only, read-only model discovery.

Remote egress is pinned to huggingface.co over HTTPS. Model metadata does not
authorize downloads, execution, file writes, CLI arguments, or PC tool calls.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from . import auth
from .db import get_db
from sqlalchemy.orm import Session

router = APIRouter()
HUB = "https://huggingface.co"
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,94}/[A-Za-z0-9][A-Za-z0-9_.-]{0,94}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,94}$")
PINNED = "mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF"
MAX_METADATA = 460_000


def hub_fetch(path: str, *, params: dict | None = None):
    # Caller must provide an internally constructed, fixed-host relative path.
    if not path.startswith("/api/models") or "//" in path or "?" in path or "#" in path:
        raise HTTPException(400, "Invalid metadata path.")
    try:
        with httpx.Client(base_url=HUB, trust_env=False, follow_redirects=False,
                          timeout=httpx.Timeout(12,connect=5),
                          headers={"Accept":"application/json","User-Agent":"SONIC-HuggingFace-Hub/1.8"},
                          limits=httpx.Limits(max_connections=2,max_keepalive_connections=0)) as client:
            with client.stream("GET",path,params=params) as response:
                if response.status_code == 404:
                    raise HTTPException(404, "Hugging Face model not found.")
                if response.status_code == 429:
                    raise HTTPException(503, "Hugging Face rate limit reached.")
                if response.status_code != 200:
                    raise HTTPException(502, "Hugging Face metadata unavailable.")
                chunks=bytearray()
                for b in response.iter_bytes():
                    chunks.extend(b)
                    if len(chunks)>MAX_METADATA:
                        raise HTTPException(502, "Hugging Face metadata response too large.")
                try:
                    data=json.loads(chunks)
                except (TypeError,ValueError):
                    raise HTTPException(502, "Hugging Face returned invalid model data.") from None
                return data
    except HTTPException:
        raise
    except (httpx.HTTPError,TimeoutError):
        raise HTTPException(503,"Hugging Face is temporarily unavailable.") from None


def clean_model(model: dict)->dict:
    identifier=str(model.get("id") or model.get("modelId") or "")
    if not REPO.fullmatch(identifier):
        raise ValueError("Invalid model identifier")
    tags=model.get("tags") if isinstance(model.get("tags"),list) else []
    card=model.get("cardData") if isinstance(model.get("cardData"),dict) else {}
    siblings=model.get("siblings") if isinstance(model.get("siblings"),list) else []
    gguf=[]
    for row in siblings:
        if not isinstance(row,dict):continue
        filename=row.get("rfilename")
        if not isinstance(filename,str) or len(filename)>240 or not filename.lower().endswith(".gguf"):
            continue
        if filename.startswith("/") or ".." in filename or "\\" in filename: continue
        size=row.get("size")
        gguf.append({"filename":filename,"bytes":size if isinstance(size,int) and size>=0 else None})
        if len(gguf)>=80:break
    likes=model.get("likes")
    downloads=model.get("downloads")
    gated=model.get("gated")
    return {
        "id":identifier,"title":identifier.split("/",1)[1],
        "author":identifier.split("/",1)[0],
        "url":HUB+"/"+quote(identifier,safe="/._-"),
        "downloads":downloads if type(downloads) is int and downloads>=0 else 0,
        "likes":likes if type(likes) is int and likes>=0 else 0,
        "private":bool(model.get("private")),
        "gated":bool(gated) if gated not in (None,False,"false") else False,
        "license":str(card.get("license") or "Not specified")[:85],
        "pipeline_tag":str(model.get("pipeline_tag") or "")[:65],
        "last_modified":str(model.get("lastModified") or "")[:35],
        "tags":[str(tag)[:75] for tag in tags[:14] if isinstance(tag,str)],
        "files":gguf,"gguf_count":len(gguf),
        "installed_in_sonic":identifier == PINNED,
        "can_activate":identifier == PINNED,
    }


@router.get("/api/huggingface/search")
def search_models(q:str=Query(default="Qwen3.5 GGUF",max_length=110),
                  limit:int=Query(default=12,ge=1,le=20),
                  _:dict=Depends(auth.require_owner)):
    query=" ".join(q.split())
    if len(query)<2 or any(ord(c)<32 for c in query):
        raise HTTPException(422,"Enter a model search query.")
    data=hub_fetch("/api/models",params={"search":query,"limit":limit,
                "sort":"downloads","direction":"-1","filter":"gguf"})
    if not isinstance(data,list):
        raise HTTPException(502,"Invalid model list.")
    models=[]
    for value in data[:limit]:
        if not isinstance(value,dict):continue
        try:models.append(clean_model(value))
        except ValueError:continue
    return {"results":models,"query":query,"count":len(models),
            "read_only":True,
            "notice":"Model search is metadata only. Search does not download or execute files."}


@router.get("/api/huggingface/model/{author}/{name}")
def model_details(author:str,name:str,_:dict=Depends(auth.require_owner)):
    repo=author+"/"+name
    if not REPO.fullmatch(repo) or not SAFE_ID.fullmatch(name):
        raise HTTPException(422,"Invalid model repository.")
    data=hub_fetch("/api/models/"+quote(author,safe="._-")+"/"+quote(name,safe="._-"),
                   params={"blobs":"true"})
    if not isinstance(data,dict):raise HTTPException(502,"Invalid model metadata.")
    try:result=clean_model(data)
    except ValueError:raise HTTPException(502,"Unexpected model identifier.") from None
    if result["id"] != repo:raise HTTPException(502,"Unexpected Hugging Face repository.")
    return result


@router.get("/api/huggingface/local")
def local_model(_:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    from .local_ai import runtime_snapshot
    return {"repo":PINNED,**runtime_snapshot(db),"catalog_read_only":True,
            "operations":["start","stop","use_for_chat"],
            "notice":"Only the preverified pinned GGUF may be started by the existing Companion. Other repository downloads are not implemented."}
