"""Owner-consented synthetic SONIC voice and optional reference transcription.

Uploaded audio is not persisted by SONIC. TTS is a standard synthetic voice,
not a clone of an uploaded person's voice.
"""
from __future__ import annotations
import asyncio
import base64
import binascii
import time
from collections import defaultdict
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from . import auth
from .config import setting
from .memory import SECRET_PATTERN
from .db import get_db
from sqlalchemy.orm import Session
from .persona import profile, provider_voice, persona_instruction, VOICE_BY_ID

router=APIRouter()
_requests=defaultdict(list)
_semaphore=asyncio.Semaphore(2)

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',strict=True)
class Speech(Strict):
    text:str=Field(min_length=1,max_length=1600)
    consent:Literal[True]
    preview_voice_id:str|None = Field(default=None, max_length=24)
class Reference(Strict):
    mime_type:Literal['audio/mpeg','audio/mp3','audio/wav','audio/x-wav','audio/mp4','audio/webm']
    audio_base64:str=Field(min_length=24,max_length=13981016)
    consent:Literal[True]


def admit(owner,kind):
    key=setting('OPENAI_API_KEY')
    if not key:raise HTTPException(503,'OpenAI is not configured')
    now=time.monotonic();sid=auth.sha256(owner['sid'])+kind
    _requests[sid]=[i for i in _requests[sid] if now-i<60]
    if len(_requests[sid]) >= (3 if kind=='reference' else 12):
        raise HTTPException(429,'Audio request limit reached; retry later')
    _requests[sid].append(now)
    return key


@router.post('/api/voice/speak')
async def speak(p:Speech,owner:dict=Depends(auth.require_owner_write), db:Session=Depends(get_db)):
    text=p.text.strip()
    if not text or SECRET_PATTERN.search(text):
        raise HTTPException(422,'Empty or credential-like text is not sent to speech')
    key=admit(owner,'speak')
    if p.preview_voice_id is not None and p.preview_voice_id not in VOICE_BY_ID:
        raise HTTPException(422,'Unknown preview voice')
    choice = profile(db)
    if p.preview_voice_id:
        choice = {**choice, 'voice_id':p.preview_voice_id}
    voice = provider_voice(choice)
    payload={'model':setting('SONIC_SPEECH_MODEL','gpt-4o-mini-tts'),'voice':voice,'input':text,'response_format':'mp3',
             'instructions':'Natural Indonesian when content is Indonesian; composed English otherwise. Standard synthetic voice. Do not imitate a real person or film character. Read provided words accurately. ' + persona_instruction(choice)}
    try:
        async with _semaphore:
            async with httpx.AsyncClient(timeout=35) as client:
                r=await client.post('https://api.openai.com/v1/audio/speech',
                    headers={'Authorization':'Bearer '+key},json=payload)
        if r.status_code!=200:raise HTTPException(502,'Speech provider rejected the request')
        if len(r.content)>8*1024*1024:raise HTTPException(502,'Audio response too large')
        return Response(r.content,media_type='audio/mpeg',headers={'Cache-Control':'no-store','X-Sonic-Voice':voice})
    except httpx.RequestError:
        raise HTTPException(502,'Speech provider is unavailable') from None


@router.post('/api/voice/reference/transcribe')
async def transcribe(p:Reference,owner:dict=Depends(auth.require_owner_write)):
    try:data=base64.b64decode(p.audio_base64,validate=True)
    except (ValueError,binascii.Error):raise HTTPException(422,'Invalid audio encoding') from None
    if not 16<=len(data)<=10*1024*1024:raise HTTPException(422,'Audio outside allowed 10 MB limit')
    is_mp3=data[:3]==b'ID3' or data[:1]==b'\xff'
    is_wav=data[:4]==b'RIFF' and data[8:12]==b'WAVE'
    is_webm=data[:4]==b'\x1aE\xdf\xa3'
    is_mp4=data[4:8]==b'ftyp'
    valid={'audio/mpeg':is_mp3,'audio/mp3':is_mp3,'audio/wav':is_wav,'audio/x-wav':is_wav,
           'audio/webm':is_webm,'audio/mp4':is_mp4}
    if not valid[p.mime_type]:raise HTTPException(422,'Audio format signature mismatch')
    ext={'audio/mpeg':'mp3','audio/mp3':'mp3','audio/wav':'wav','audio/x-wav':'wav',
         'audio/webm':'webm','audio/mp4':'m4a'}[p.mime_type]
    key=admit(owner,'reference')
    try:
        async with _semaphore:
            async with httpx.AsyncClient(timeout=60) as client:
                r=await client.post('https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization':'Bearer '+key},files={'file':('reference.'+ext,data,p.mime_type)},
                    data={'model':'gpt-4o-mini-transcribe','response_format':'json',
                          'prompt':'Transcribe the intelligible spoken words only. Ignore background music and instrument sounds. Do not invent words.'})
        if r.status_code!=200:raise HTTPException(502,'Reference transcription rejected by provider')
        text=r.json().get('text','')
        if not isinstance(text,str):raise ValueError('Invalid provider response')
        return {'text':text[:12000],'audio_stored':False,'music_separated':False,'voice_cloned':False}
    except (httpx.RequestError,ValueError):raise HTTPException(502,'Transcription failed') from None
