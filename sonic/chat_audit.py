"""Owner-only chat history friction diagnostics; never logs conversation text."""
import re
import json
from collections import Counter
from sqlalchemy import select
from .db import ChatMessage, OperatorRequest, VoiceActionDispatch, VoiceSession


def is_chat_log_request(text: str) -> bool:
    if not isinstance(text,str) or len(text)>250:return False
    s=text.casefold().strip()
    if re.search(r'\b(?:jangan|tidak usah|contoh|misalnya)\b',s):return False
    return bool(re.search(r'(?:cek|lihat|audit|periksa|review|analisa|analisis)\b.{0,80}'
                          r'(?:log|riwayat|history).{0,40}(?:chat|percakapan)|'
                          r'(?:cek|lihat|audit|periksa)\b.{0,40}(?:chat|percakapan).{0,25}'
                          r'(?:history|log|riwayat)',s))


def summarize_chat_friction(db) -> str:
    """Aggregates personal SONIC history in place. Never echoes raw chat text."""
    messages=db.scalars(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(100)).all()
    user=[row for row in messages if row.role=='user']
    folder=sum(bool(re.search(r'\b(?:folder(?:nya)?|direktori|directory|mkdir)\b',row.content,re.I)) for row in user)
    powershell=sum('powershell' in row.content.casefold() for row in user)
    confirmations=sum(bool(re.fullmatch(r'(?:setuju|batal|batalkan|approve|konfirmasi|ya jalankan|oke jalankan)',row.content.casefold().strip())) for row in user)
    jobs=db.scalars(select(OperatorRequest).order_by(OperatorRequest.created_at.desc()).limit(80)).all()
    state=Counter(row.state for row in jobs)
    actions=Counter(row.action for row in jobs)
    voice=db.scalars(select(VoiceActionDispatch).order_by(
        VoiceActionDispatch.created_at.desc()).limit(80)).all()
    sessions=db.scalars(select(VoiceSession).order_by(
        VoiceSession.created_at.desc()).limit(30)).all()
    voice_routes=Counter()
    accepted_jobs=0
    for item in voice:
        try:receipt=json.loads(item.result_json)
        except (ValueError,TypeError):receipt={}
        voice_routes[receipt.get('route','unavailable')]+=1
        accepted_jobs+=len(receipt.get('operator_jobs') or [])
    voice_route_text=', '.join(f'{k}={v}' for k,v in voice_routes.most_common(5)) or 'belum ada'
    notes=(
        f"Audit histori SONIC (maksimal 100 pesan terbaru): {len(user)} pesan pengguna, "
        f"{folder} menyebut folder/direktori, {powershell} menyebut PowerShell, "
        f"{confirmations} balasan konfirmasi. "
        f"Dari {len(jobs)} request operator terbaru: {sum(state.values())} request, "
        f"{state['pending']} pending, {state['queued']} queued, {state['leased']} running, "
        f"{state['done']} selesai, {state['failed']} gagal, "
        f"{state['cancelled']} dibatalkan, {state['expired']} kedaluwarsa. "
        f"Jenis terbanyak: "+(', '.join(f'{k}={v}' for k,v in actions.most_common(4)) or 'belum ada')+'. '
        "Perubahan V0.8.5: membuat folder di workspace dan tindakan baca yang aman tidak memerlukan approval tambahan. "
        "PowerShell dan End Task disetujui langsung lewat chat (SETUJU/BATAL). "
        f"Audit voice (maksimal 80 dispatch tersimpan): {len(voice)} percobaan, "
        f"{accepted_jobs} tindakan PC diterima, {len(sessions)} sesi suara terbaru, "
        f"rute {voice_route_text}. "
        "Voice yang tidak dikenali sebagai tindakan PC belum seluruhnya tercatat pada versi lama. "
        "Audit ini hanya merangkum data database yang tersedia, bukan isi log eksternal atau kredensial."
    )
    return notes
