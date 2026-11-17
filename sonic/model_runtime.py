"""Owner model identity, live readiness and explicit answer provenance.

No vendor inference, web search, credential values or PC actions in this module.
Selection is NOT an inference receipt, and configured cloud keys are NOT proof
that a remote model is currently available.
"""
from __future__ import annotations
import re
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from . import auth
from .config import setting
from .db import get_db
from .providers import selected_model, configured, Selection
from .local_ai import runtime_snapshot

router = APIRouter()


def is_model_status_question(text: str) -> bool:
    """Narrow first-party intent, never route general model discovery here."""
    q = ' '.join(text.lower().split())
    if len(q) > 240 or re.search(r'^(cari|carikan|search|find|bandingkan|compare|jelaskan perbedaan)\b', q):
        return False
    if not re.search(r'\b(sonic|kamu|anda|you|your|sekarang|currently)\b|model\s+(aktif|terpilih)|(?:local|lokal)\s+(?:ai|engine)|engine\s+lokal', q):
        return False
    return bool(re.search(
        r'\b(model|ai|llm|engine)\b.{0,65}\b(aktif|terpilih|dipakai|digunakan|gunakan|pakai|running|stopped|menyala|berjalan)\b'
        r'|\b(model|ai)\s+(apa|mana)\s+(ini|kamu|sonic)\b'
        r'|\b(what|which)\s+(ai\s+)?model\b.{0,60}\b(using|use|selected|active|running)\b'
        r'|\b(kamu|sonic)\b.{0,35}\b(pakai|menggunakan|gunakan)\b.{0,25}\b(model|ai)\b', q))


def snapshot(db: Session, selection: Selection | None = None) -> dict:
    selected = selection or selected_model(db)
    local = runtime_snapshot(db)
    local_ready = bool(local['enabled'] and local['device_online'] and
                       local['bridge_online'] and local['state'] == 'running')
    key_configured = configured(selected.provider)
    if selected.provider == 'local':
        state = 'running' if local_ready else ('stopped' if local['bridge_online'] and
                  local['state'] == 'stopped' else 'unavailable')
        message = ('Local Qwen 9B berjalan di TRADEVICEPC.' if local_ready else
                   'Local Qwen 9B terpilih, tetapi engine belum berjalan. Start local atau pilih model cloud.')
    else:
        state = 'configured_not_probed' if key_configured else 'not_configured'
        message = (selected.model + ' terpilih di cloud. Key terkonfigurasi; koneksi belum diuji pada permintaan ini.'
                   if key_configured else selected.model + ' belum memiliki key server.')
    flag = setting('SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED', 'false').lower() in ('1','true','yes')
    eligible = local_ready if selected.provider == 'local' else bool(flag and key_configured)
    return {
        'selected': {'provider': selected.provider, 'model': selected.model,
                     'label': 'Local Qwen 9B Q4_K_M' if selected.provider == 'local' else selected.model,
                     'state': state, 'configured': key_configured},
        'local': {'state': local['state'], 'ready': local_ready,
                  'device_online': local['device_online'], 'bridge_online': local['bridge_online'],
                  'checked_seconds_ago': local['checked_seconds_ago']},
        'research_synthesis_eligible': eligible,
        'cloud_synthesis_eligible': bool(selected.provider != 'local' and eligible),
        'inference_verified': False,
        'message': message,
        'fallback': 'none',
        'limits': {'local_context_tokens': 1024, 'local_max_output_tokens': 256},
        'privacy': 'Local inference melewati relay Railway ke TRADEVICEPC. Cloud inference mengirim konteks ke provider terpilih. Web research memakai layanan pencarian terpisah.',
    }


def origin(kind: str, selection: Selection | None = None) -> dict:
    return {'kind': kind, 'provider': selection.provider if selection else None,
            'model': selection.model if selection else None,
            'inference_performed': kind == 'model_output', 'fallback': False}


def status_answer(db: Session) -> dict:
    status = snapshot(db)
    chosen = status['selected']
    answer = ('Model terpilih: ' + chosen['label'] + ' (' + chosen['provider'] + ').\n' +
              status['message'] + '\nStatus ini dibaca langsung dari SONIC, bukan hasil pencarian web dan bukan jawaban model. '
              'Tidak ada pergantian provider otomatis.')
    return {'reply': answer, 'mode': 'system_status', 'runtime': status,
            'answer_origin': origin('system_status'), 'model_provider': None,
            'sources': [], 'steps': [{'tool': 'sonic.model_status', 'status': 'completed'}],
            'searched_queries': [], 'notice': '', 'local_ai_used': False,
            'read_only': True, 'memory_saved': False, 'memory_matches': []}


@router.get('/api/intelligence/status')
def get_status(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return snapshot(db)
