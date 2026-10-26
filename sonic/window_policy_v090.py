"""SONIC V0.9.0 deterministic, owner-origin Windows application intent policy.

No executable path, shell expression or arbitrary process name is accepted
from chat/voice. MetaTrader5 is a terminal application, not a trading API.
"""
from __future__ import annotations

import re

APP_LABELS = {
    'notepad': 'Notepad',
    'paint': 'Paint',
    'metatrader5': 'MetaTrader 5',
}
APP_ALIASES = {
    'notepad': frozenset({'notepad', 'notepad.exe', 'notes app'}),
    'paint': frozenset({'paint', 'mspaint', 'mspaint.exe', 'microsoft paint'}),
    'metatrader5': frozenset({'metatrader 5', 'metatrader5', 'meta trader 5',
                              'mt5', 'terminal mt5', 'terminal64.exe'}),
}
SENSITIVE_APPS = frozenset({'metatrader5'})
FORBIDDEN_CONTEXT = re.compile(
    r'\b(?:jangan|tidak usah|nggak usah|belum|bukan|contoh|misalnya|'
    r'bagaimana cara|how to|apakah|kenapa|mengapa|kalau|seandainya|'
    r'what if|can you|bisa(?:kah)?|posisi|position|order|'
    r'buy|sell|trade|trading|script|command|powershell)\b', re.I)
PREFIX = re.compile(r'^(?:(?:hey|hei|hai|halo)\s+)?(?:sonic|sonik)\s*[,.:]?\s*', re.I)
POLITE = re.compile(r'^(?:(?:tolong|please|coba|mohon)\s+)+', re.I)
TRAILING = re.compile(r'(?:[,\s]+(?:ya|dong|sekarang|please|untuk saya))+$', re.I)
VERBS = (
    (re.compile(r'^(?:tutup|close|keluar dari|quit|matikan|matiin)(?:\s+kamu)?(?:\s+(?:close|tutup))?\b\s*', re.I), 'window.close'),
    (re.compile(r'^(?:buka|open|jalankan|launch|start)\b\s*', re.I), 'window.open'),
    (re.compile(r'^(?:fokus(?:kan)?|focus|tampilkan|show|pindah ke|aktifkan)\b\s*', re.I), 'window.focus'),
)
TARGET_PREFIX = re.compile(r'^(?:(?:jendela|window|aplikasi|app|program|software)\s+)+', re.I)
SCOPE_SUFFIX = re.compile(r'\s+(?:di|pada|on)\s+(?:tradevice\s*pc|tradevicepc|pc|komputer saya|windows pc)$',re.I)


def recognized_app(value: str) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 70:
        return None
    name = re.sub(r'\s+', ' ', value.strip()).casefold()
    return next((app for app, aliases in APP_ALIASES.items() if name in aliases), None)


def parse_window_command(transcript: str) -> tuple[str, str] | None:
    """One explicit verb + one exactly allowlisted application, nothing else."""
    if not isinstance(transcript, str) or not 2 <= len(transcript) <= 250:
        return None
    text = re.sub(r'\s+', ' ', transcript.strip()).strip(' \t\r\n,.!?')
    text = PREFIX.sub('', text)
    text = POLITE.sub('', text)
    if FORBIDDEN_CONTEXT.search(text) or re.search(r'[;\n\r|&<>$%]', text):
        return None
    for pattern, action in VERBS:
        match = pattern.match(text)
        if not match:
            continue
        target = TARGET_PREFIX.sub('', text[match.end():].strip())
        target = TRAILING.sub('', target).strip(' \t\r\n,.!?')
        target = SCOPE_SUFFIX.sub('', target).strip()
        app = recognized_app(target)
        if app:
            return action, app
    return None


def looks_like_window_command(text: str) -> bool:
    if not isinstance(text,str) or len(text)>250:
        return False
    cleaned = PREFIX.sub('', text.strip())
    cleaned = POLITE.sub('', cleaned)
    if FORBIDDEN_CONTEXT.search(cleaned):
        return False
    return any(pattern.match(cleaned) for pattern, _ in VERBS) and bool(re.search(
        r'\b(?:window|jendela|aplikasi|program|metatrader|meta trader|mt5|notepad|paint)\b', cleaned,re.I))


def approval_notice(action: str, app: str) -> str:
    if action == 'window.close' and app == 'metatrader5':
        return ('PERINGATAN: menutup MetaTrader 5 dapat menghentikan EA, '
                'trailing stop lokal, dan otomasi trade. Posisi broker tidak '
                'otomatis ditutup. Periksa risiko sebelum menekan SETUJU. '
                'SONIC hanya mengirim WM_CLOSE, tidak force-kill.')
    if action == 'window.close':
        return ('Menutup window dapat memunculkan dialog penyimpanan dokumen. '
                'SONIC tidak memaksa penutupan atau membuang perubahan.')
    if action == 'window.open' and app == 'metatrader5':
        return ('SONIC hanya membuka terminal MetaTrader 5 dari path lokal '
                'yang telah diizinkan. Tidak mengirim order trading.')
    return 'Permintaan ini memerlukan persetujuan pemilik untuk satu tindakan.'
