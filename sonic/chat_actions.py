"""Chat-first SONIC PC actions with explicit natural-language intent.

Conservative deterministic recognizer: safe workspace operations queue without
a second consent, while powerful operations require one confirmation IN CHAT.
Never interpret text returned by tools or other people as an owner instruction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from .device_contract import clean_workspace_folder, clean_request

ACK_PATTERN=re.compile(r'^(?:setuju|saya setuju|ya[, ]+jalankan|iya[, ]+jalankan|oke[, ]+jalankan|ok[, ]+jalankan|'
                       r'silakan jalankan|konfirmasi|approve(?: once)?|confirm|yes[, ]+run|lanjutkan perintah)$',re.I)
CANCEL_PATTERN=re.compile(r'^(?:batal|batalkan|jangan jalankan|tidak setuju|cancel|reject|no[, ]+cancel)$',re.I)
BAD_CONTEXT=re.compile(r'\b(?:jangan|tidak usah|nggak usah|bukan|contoh|misalnya|contohnya|hypothetical|'
                       r'what if|bagaimana cara|how to|apakah|kenapa|mengapa|bisa(?:kah)?\s+sonic)\b',re.I)
PREFIX=re.compile(r'^\s*(?:(?:hei|hey)\s+)?sonic[,.:]?\s+',re.I)
ROOT=re.compile(r'^(?:d:[\\/]+sonic[\\/]+work[\\/]+)',re.I)
TAIL=re.compile(r'\s+(?:di|pada|on|in)\s+(?:tradevicepc|pc|komputer|komputer saya|'
                r'workspace(?: sonic)?|folder kerja(?: sonic)?)\s*$',re.I)


@dataclass(frozen=True)
class ChatAction:
    kind: Literal['automatic','review']
    action: str
    payload: dict


def _strip_scope(raw: str) -> str:
    value=raw.strip()
    value=TAIL.sub('',value)
    value=ROOT.sub('',value)
    value=value.strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
        value=value[1:-1].strip()
    return value


def classify(text: str) -> ChatAction | None:
    """Classify ONLY explicit owner-origin current-turn commands, not questions."""
    if not isinstance(text,str) or not 1<=len(text)<=3500:
        return None
    s=PREFIX.sub('',text.strip()).strip().rstrip('.!?').strip()
    if BAD_CONTEXT.search(s):
        return None

    # Direct typed PowerShell is powerful, so never autoapprove it.
    m=re.fullmatch(r'(?:jalankan|eksekusi|execute|run)\s+(?:perintah\s+|command\s+)?'
                   r'powershell\s*[:：]\s*(?P<command>[\s\S]{1,1200})',s,re.I)
    if not m:
        m=re.fullmatch(r'powershell\s*[:：]\s*(?P<command>[\s\S]{1,1200})',s,re.I)
    if m:
        payload=clean_request('powershell.exec',{'command':m.group('command').strip(),'timeout_seconds':30})
        return ChatAction('review','powershell.exec',payload)

    m=re.fullmatch(r'(?:hentikan|akhiri|kill|end task|terminate)\s+(?:proses|process)\s+'
                   r'(?P<name>[a-zA-Z0-9_. -]{1,100})\s+(?:pid|id)\s*[:#]?\s*(?P<pid>\d{1,10})',s,re.I)
    if m:
        payload=clean_request('process.terminate',{
            'pid':int(m.group('pid')),'expected_name':m.group('name').strip()})
        return ChatAction('review','process.terminate',payload)

    # The Windows Desktop is a distinct, explicitly named safe target.
    # Never silently redirect a "desktop" request to D:\Sonic\work.
    desktop=re.fullmatch(
        r'(?:(?:tolong|please|coba)\s+)?(?:buat(?:kan)?|bikin|create)\s+'
        r'(?:(?:sebuah|satu|a|new)\s+)?(?:folder|direktori|directory)\s+'
        r'(?:(?:baru|new)\s+)?(?:(?:bernama|named|nama(?:nya)?)\s*[:=]?\s*)?'
        r'(?P<name>.+?)\s+(?:di|pada|on|in)\s+'
        r'(?:desktop|dekstop|desktopku|desktop\s+saya)'
        r'(?:\s+(?:TRADEVICEPC|TRADEVICE\s+PC|THREADVICE\s+PC|THREADVICEPC|PC|'
        r'komputer(?:\s+saya)?|windows(?:\s+pc)?))?\s*',s,re.I|re.S)
    if desktop:
        name=_strip_scope(desktop.group('name'))
        if not name or '/' in name or '\\' in name:
            return None
        clean=clean_workspace_folder(name)
        return ChatAction('automatic','desktop.mkdir',{'name':clean})
    if re.search(r'\b(?:desktop|dekstop|desktopku)\b',s,re.I) and re.match(
        r'(?:(?:tolong|please|coba)\s+)?(?:buat(?:kan)?|bikin|create)\s+',s,re.I):
        return None

    m=re.fullmatch(r'(?:(?:tolong|please|coba)\s+)?(?:buat(?:kan)?|bikin|create)\s+'
                   r'(?:(?:sebuah|satu|a|new)\s+)?(?:folder|direktori|directory)\s+'
                   r'(?:(?:baru|new)\s+)?(?:(?:bernama|named|nama(?:nya)?)\s*[:=]?\s*)?'
                   r'(?P<name>.+?)\s*',s,re.I|re.S)
    if m:
        name=_strip_scope(m.group('name'))
        if not name or name.endswith('?'):
            return None
        path=clean_workspace_folder(name)
        return ChatAction('automatic','file.mkdir',{'path':path})

    m=re.fullmatch(r'(?:(?:tolong|please|coba)\s+)?(?:lihat|tampilkan|cek|list|show|'
                   r'daftarkan)\s+(?:(?:daftar|isi|list)\s+)?'
                   r'(?P<kind>folder|direktori|directory|file|berkas)\s*'
                   r'(?P<name>.*?)\s*',s,re.I|re.S)
    if m:
        name=_strip_scope(m.group('name'))
        if not name or name.casefold() in ('di pc','tradevicepc','di tradevicepc'):
            name='.'
        if name=='.':
            return ChatAction('automatic','file.list',{'path':'.'})
        path=clean_workspace_folder(name)
        return ChatAction('automatic','file.list',{'path':path})

    m=re.fullmatch(r'(?:(?:tolong|please|coba)\s+)?(?:baca|read|lihat isi|tampilkan isi)\s+'
                   r'(?:file|berkas)\s+(?P<name>.+?)\s*',s,re.I|re.S)
    if m:
        name=_strip_scope(m.group('name'))
        if not name or name.endswith('?'):
            return None
        if not 1 <= len(name) <= 180 or re.search(r'[<>:"|?*]',name) or name.startswith(('/', '\\', '~')):
            return None
        return ChatAction('automatic','file.read',{'path':name.replace('\\','/')})

    if re.fullmatch(r'(?:(?:tolong|please|coba)\s+)?(?:lihat|tampilkan|cek|list|show)\s+'
                    r'(?:(?:daftar|list)\s+)?(?:proses|process|processes)(?:\s+(?:di|on)\s+(?:pc|tradevicepc))?',s,re.I):
        return ChatAction('automatic','process.list',{})

    if re.fullmatch(r'(?:(?:tolong|please|coba)\s+)?(?:lihat|tampilkan|cek|list|show)\s+'
                    r'(?:(?:daftar|list)\s+)?(?:jendela|windows|window)(?:\s+(?:di|on)\s+(?:pc|tradevicepc))?',s,re.I):
        return ChatAction('automatic','window.list',{})
    return None


def confirmation_intent(text: str) -> Literal['approve','cancel'] | None:
    s=PREFIX.sub('',str(text).strip()).strip().rstrip('.!')
    if ACK_PATTERN.fullmatch(s):return 'approve'
    if CANCEL_PATTERN.fullmatch(s):return 'cancel'
    return None
