"""Deterministic spoken PC command resolver for SONIC.

The LLM cannot manufacture actions. Only the owner's recognized transcript,
with a single unambiguous safe target, may produce an allowlisted action.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from .chat_actions import ChatAction, BAD_CONTEXT, PREFIX, classify
from .device_contract import clean_workspace_folder

FOLDER_WORD=re.compile(r'\b(?:folder(?:nya)?|direktori|directory|map|berkas)\b',re.I)
DESKTOP_WORD=re.compile(r'\b(?:desktop|dekstop|desk\s*top|dek\s*stop|layar\s+desktop)\b',re.I)
WORKSPACE_WORD=re.compile(r'\b(?:TRADEVICE\s*PC|TRADEVICEPC|THREADVICE\s*PC|'
                          r'TREADVICE\s*PC|workspace|folder\s+kerja)\b',re.I)
CREATE_WORD=re.compile(r'\b(?:buat(?:kan)?|dibuatkan|bikinin|bikin(?:kan)?|create|'
                       r'tambahkan|dibikinin|tolong\s+bikin|mau\s+buat|minta\s+buat|buat\s+dong)\b',re.I)
LEADING=re.compile(r'^(?:(?:hei|hey|hai|halo)\s+)?(?:sonic|sonik)\s*[,.:]?\s*',re.I)
NAME_LABEL=re.compile(r'\b(?:nama\s+folder(?:nya)?|namanya|nama\s+direktori|'
                      r'bernama|yang\s+namanya|dengan\s+nama|nama|disebut|called|named)\s*[:=]?\s*',re.I)
UNSAFE_CONTEXT=re.compile(r'\b(?:jangan|tidak\s+usah|nggak\s+usah|bukan|contoh(?:nya)?|'
                          r'misalnya|bagaimana\s+cara|gimana\s+cara|apakah|kenapa|'
                          r'mengapa|andaikan|what\s+if|kalau\s+misal|pernah|sebelumnya)\b',re.I)
COMMAND_START=re.compile(r'^(?:(?:ya|oke|ok|sekarang|coba|tolong|mohon|'
                         r'please|bisa\s+tolong|bisa|coba\s+tolong)\s*[, ]*\s*)*'
                         r'(?:buat(?:kan)?|bikin(?:kan)?|bikinin|create|'
                         r'tambahkan|dibuatkan|dibikinin)\b',re.I)
MULTI_ACTION=re.compile(r'\b(?:lalu|kemudian|setelah\s+itu|terus\s+hapus|'
                        r'dan\s+(?:hapus|delete|rename|pindahkan|jalankan))\b',re.I)
TAIL_STOP=re.compile(r'\s+(?:(?:di|pada|on|in)\s+)?(?:desktop|dekstop|'
                     r'tradevice\s*pc|threadvice\s*pc|komputer(?:\s+saya)?|'
                     r'pc)(?:\s+(?:komputer(?:\s+saya)?|pc|saya|ini))?\s*$',re.I)
FILLER_START=re.compile(r'^(?:(?:folder|direktori|directory|baru|new|satu|'
                        r'yang|dengan|namanya|nama|bernama|disebut)\s+)+',re.I)
FILLER_END=re.compile(r'[,.\s]+(?:ya|dong|tolong|sekarang|please|untuk\s+saya)\s*$',re.I)


@dataclass(frozen=True)
class VoiceIntent:
    kind: str
    action: ChatAction | None = None
    detail: str = ''


def normalize_spoken(text: str) -> str:
    if not isinstance(text,str) or not 1<=len(text)<=1300:
        return ''
    s=unicodedata.normalize('NFKC',text).strip()
    s=re.sub(r'[\u200b\u200c\u200d]','',s)
    s=re.sub(r'\s+',' ',s)
    s=LEADING.sub('',s).strip()
    return s.strip(' \t\r\n.!?,')


def _single_name(value: str) -> str | None:
    s=value.strip(' \t\r\n,;:.')
    if re.match(r'^(?:(?:di|pada|on|in)\s+)?(?:desktop|dekstop)(?:\s+.+)?$',s,re.I):
        return None
    s=TAIL_STOP.sub('',s).strip(' \t\r\n,;:.')
    s=FILLER_START.sub('',s).strip()
    s=FILLER_END.sub('',s).strip(' \t\r\n,;:.')
    if len(s)>=2 and s[0] == s[-1] and s[0] in ("'",'"','“','”'):
        s=s[1:-1].strip()
    if not s or s.casefold() in ('folder','foldernya','baru','new','folder baru',
                                 'nama foldernya','di desktop') or re.search(
            r'\b(?:folder|foldernya|di\s+desktop)\s*$',s,re.I):
        return None
    if MULTI_ACTION.search(s) or any(x in s for x in ('\n','\r',';')):
        return None
    if len(s.split())>7 or len(s)>70:
        return None
    try:
        result=clean_workspace_folder(s)
    except (ValueError,TypeError):
        return None
    return result if '/' not in result else None


def parse_voice_intent(transcript: str) -> VoiceIntent:
    """Strict text classification first, then spoken phrase recovery only for mkdir."""
    s=normalize_spoken(transcript)
    if not s:return VoiceIntent('not_pc')
    if UNSAFE_CONTEXT.search(s):
        return VoiceIntent('not_pc')
    try:
        typed=classify(s)
    except (ValueError,TypeError):
        return VoiceIntent('unsafe')
    if typed and typed.action not in ('file.mkdir','desktop.mkdir'):
        return VoiceIntent('action',typed)
    if not CREATE_WORD.search(s):
        return VoiceIntent('not_pc')
    has_folder=bool(FOLDER_WORD.search(s))
    desktop=bool(DESKTOP_WORD.search(s))
    workspace=bool(WORKSPACE_WORD.search(s))
    if not has_folder and not desktop:
        return VoiceIntent('not_pc')
    # A positive imperative is mandatory. No commands from narrative sentences.
    if not COMMAND_START.search(s):
        return VoiceIntent('not_pc')
    if MULTI_ACTION.search(s):
        return VoiceIntent('ambiguous')
    if typed and typed.action=='desktop.mkdir':
        raw_name=typed.payload.get('name','')
        # Generic words and spoken labels aren't actual names.
        if raw_name.strip().casefold() not in ('folder','foldernya','baru','new',
             'folder baru','nama foldernya') and not re.match(
             r'^(?:yang\s+)?(?:namanya|bernama)\b',raw_name,re.I):
            return VoiceIntent('action',typed)
    if typed and typed.action=='file.mkdir' and workspace and not desktop:
        return VoiceIntent('action',typed)
    if typed and typed.action=='file.mkdir' and not desktop and not workspace:
        return VoiceIntent('need_location',detail=typed.payload.get('path',''))
    if desktop and workspace and re.search(r'\b(?:workspace|folder\s+kerja)\b',s,re.I):
        return VoiceIntent('ambiguous')
    if not desktop and not workspace:
        return VoiceIntent('need_location',detail='folder')
    if not desktop:
        return VoiceIntent('need_name',detail='workspace')
    # Prefer a directly named folder, with the name anywhere in the utterance.
    markers=list(NAME_LABEL.finditer(s))
    names=[]
    if markers:
        for match in markers:
            after=s[match.end():]
            name=_single_name(after)
            if name:names.append(name)
    if not names:
        # Some ASR outputs use 'buat folder Today di Desktop', where no label
        # exists, or invert order 'di Desktop buat folder Today'.
        m=re.search(r'\b(?:folder|direktori|directory)\s+(.+)$',s,re.I)
        if m:
            name=_single_name(m.group(1))
            if name:names.append(name)
    if not names:
        return VoiceIntent('need_name',detail='desktop')
    if len(set(names))!=1:
        return VoiceIntent('ambiguous')
    name=names[0]
    return VoiceIntent('action',ChatAction('automatic','desktop.mkdir',{'name':name}))


def parse_followup_name(text: str) -> str | None:
    """Accept a single safe folder name only after an explicit pending slot."""
    s=normalize_spoken(text)
    if not s or BAD_CONTEXT.search(s) or UNSAFE_CONTEXT.search(s) or re.match(r'^(?:delete|hapus|shutdown|restart|stop|batal|cancel)\b',s,re.I):
        return None
    if CREATE_WORD.search(s):
        return None
    s=re.sub(r'^(?:namanya|nama(?:\s+folder(?:nya)?)?|bernama|'
             r'foldernya)\s*[:=]?\s*','',s,flags=re.I).strip()
    return _single_name(s)
