"""Test-only application used by real HTTP browser QA. Never deployed.

No OpenAI requests can leave this process. Requires a disposable local server.
"""
import os
from uuid import uuid4
if os.environ.get('SONIC_ENV')!='local' or os.environ.get('SONIC_QA_VOICE')!='synthetic-only':
    raise RuntimeError('Voice QA application requires the explicit disposable local test environment')
import httpx
from sonic.api import app
import sonic.voice as voice

class SyntheticProvider:
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,**kwargs):
        if url==voice.CREATE_URL:
            return httpx.Response(201,text='v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n',headers={'Location':'/v1/realtime/calls/rtc_qa_'+uuid4().hex})
        if url.startswith(voice.CREATE_URL+'/') and url.endswith('/hangup'):
            return httpx.Response(200)
        raise RuntimeError('Network calls are disabled in voice QA')
voice.httpx.AsyncClient=SyntheticProvider
