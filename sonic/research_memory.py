"""Owner-isolated, persistent, source-backed Research Memory v1.7.

This stores only owner-approved research results, not scraped full pages or
private credentials. SQLite and PostgreSQL use additive tables.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import auth
from .db import Base, get_db, utcnow
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ResearchMemory(Base):
    __tablename__ = "research_memory_v170"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(80), default="General", nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode: Mapped[str] = mapped_column(String(35), default="sources_only", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


router = APIRouter()
SENSITIVE_RE = re.compile(r"(?i)(password|token|api[_ -]?key|authorization|secret)\s*[:=]\s*[^\s]+")
WORDS = re.compile(r"(?u)\b[\w.-]{3,}\b")
STOP = {"untuk","apa","dan","yang","cara","bagaimana","dari","the","about","show","find","tolong","cari","data","reference","referensi"}
ALIASES = {"mitm": ["man-in-the-middle","network interception"],"xss":["cross-site scripting"],
           "csrf":["cross-site request forgery"],"ai":["artificial intelligence"],"cafe":["coffee shop"]}


def tokens(text: str) -> set[str]:
    v = text.casefold()
    for term, aliases in ALIASES.items():
        if re.search(r"\b"+term+r"\b", v):
            v += " " + " ".join(aliases)
    return {t for t in WORDS.findall(v) if t not in STOP}


def _safe_sources(sources: list[dict]) -> list[dict]:
    from .research_web import public_url
    results=[]
    for source in sources[:5]:
        url=public_url(source.get("url",""))
        if not url: continue
        results.append({"id":int(source.get("id",len(results)+1)),
                        "title":str(source.get("title",""))[:180],
                        "url":url, "publisher":str(source.get("publisher",""))[:150],
                        "date":source.get("date") if isinstance(source.get("date"),str) else None,
                        "snippet":str(source.get("snippet",""))[:550],
                        "excerpt":str(source.get("excerpt",""))[:550],
                        "read":bool(source.get("read",False))})
    return results


def save_research(db:Session, query:str, purpose:str, summary:str, sources:list[dict],
                  project:str="General", mode:str="sources_only")->ResearchMemory:
    if SENSITIVE_RE.search(query): raise HTTPException(422,"Do not save credentials")
    project = " ".join((project or "General").split())[:80] or "General"
    if SENSITIVE_RE.search(project): raise HTTPException(422,"Do not save credentials")
    filtered=_safe_sources(sources)
    if not filtered:
        raise HTTPException(422,"Research memory needs at least one public source")
    record=ResearchMemory(id=str(uuid4()),project=project,query=query[:300],
                          purpose=purpose,summary=summary[:3000],sources_json=json.dumps(filtered,ensure_ascii=False),
                          source_count=len(filtered),mode=mode)
    db.add(record)
    db.commit()
    return record


def dto(record:ResearchMemory,details:bool=False)->dict:
    result={"id":record.id,"project":record.project,"query":record.query,
            "purpose":record.purpose,"summary":record.summary[:1400] if not details else record.summary,
            "source_count":record.source_count,"mode":record.mode,"created_at":record.created_at.isoformat()+"Z"}
    if details:result["sources"]=json.loads(record.sources_json)
    return result


def related(db:Session, query:str, *, limit:int=3, exclude:str|None=None)->list[dict]:
    records=db.scalars(select(ResearchMemory).order_by(ResearchMemory.created_at.desc()).limit(150)).all()
    qt=tokens(query)
    scored=[]
    for record in records:
        if record.id==exclude:continue
        titles=" ".join(s.get("title","") for s in json.loads(record.sources_json)[:3])
        title_tokens=tokens(record.query+" "+titles)
        summary_tokens=tokens(record.summary[:1600])
        score=3*len(qt&title_tokens)+len(qt&summary_tokens)
        if score>0:scored.append((score,record))
    scored.sort(key=lambda item:(-item[0],-item[1].created_at.timestamp()))
    return [dto(record,details=True) for _,record in scored[:limit]]


@router.get("/api/agent/memory")
def list_memory(search:str=Query(default="",max_length=120),
                project:str=Query(default="",max_length=80),
                limit:int=Query(default=30,ge=1,le=100),
                _:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    query=select(ResearchMemory).order_by(ResearchMemory.created_at.desc()).limit(150)
    records=db.scalars(query).all()
    if project:
        records=[r for r in records if r.project.casefold()==project.casefold()]
    if search.strip():
        keys=tokens(search)
        records=[r for r in records if keys & tokens(r.query+" "+r.summary[:1000])]
    return {"results":[dto(r) for r in records[:limit]],"total":len(records)}


@router.get("/api/agent/memory/{memory_id}")
def get_memory(memory_id:str,_:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    record=db.get(ResearchMemory,memory_id)
    if record is None: raise HTTPException(404,"Research memory not found")
    return dto(record,details=True)


@router.delete("/api/agent/memory/{memory_id}")
def remove_memory(memory_id:str,_:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    record=db.get(ResearchMemory,memory_id)
    if record is None: raise HTTPException(404,"Research memory not found")
    db.delete(record)
    db.commit()
    return {"deleted":True,"id":memory_id}
