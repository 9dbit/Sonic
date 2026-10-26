"""Minimal, privacy-safe OpenAI Realtime provider error classification.

Never store or echo an upstream error message, SDP, transcript, bearer
credential, organization identifier, or response body. Only strictly
allowlisted public error codes and bounded request IDs may be logged.
"""
from __future__ import annotations
import re

from typing import Any

DIAGNOSES = {
    'credit_balance_exhausted': (
        'Saldo API organisasi untuk key ini habis. Pastikan top-up masuk ke organisasi yang digunakan SONIC.'
    ),
    'organization_usage_limit_exceeded': (
        'Batas penggunaan organisasi tercapai. Periksa batas API organisasi yang digunakan key SONIC.'
    ),
    'organization_spend_limit_exceeded': (
        'Batas pengeluaran organisasi tercapai. Periksa pengaturan spend limit OpenAI.'
    ),
    'project_spend_limit_exceeded': (
        'Batas pengeluaran project tercapai. Periksa project yang membuat key SONIC.'
    ),
    'rate_limit_exceeded': (
        'Batas permintaan atau token sementara tercapai. Periksa Limits model Realtime dan Retry-After.'
    ),
    'insufficient_quota': (
        'Provider melaporkan kuota tidak mencukupi. Periksa saldo dan batas organisasi/project key SONIC.'
    ),
    'model_not_found': (
        'Model Realtime yang dikonfigurasi tidak tersedia untuk key/project SONIC.'
    ),
    'model_not_allowed': (
        'Model Realtime tidak diizinkan pada project OpenAI yang digunakan SONIC.'
    ),
    'model_access_denied': (
        'Akses model Realtime ditolak untuk project OpenAI yang digunakan SONIC.'
    ),
}
SAFE_TYPES = {'rate_limit_error', 'insufficient_quota', 'invalid_request_error',
              'authentication_error', 'permission_error', 'api_error'}


def classify_provider_error(status: int, body: Any, headers: Any = None) -> dict[str, str | int | None]:
    """Return safe diagnostics, not raw provider data.

    A 429 without a documented code remains unclassified, since retrying an
    exhausted billing budget differs from retrying a transient rate limit.
    """
    raw = body.get('error') if isinstance(body, dict) else None
    error = raw if isinstance(raw, dict) else {}
    code = error.get('code')
    error_type = error.get('type')
    if not isinstance(code, str) or code not in DIAGNOSES:
        code = None
    if not isinstance(error_type, str) or error_type not in SAFE_TYPES:
        error_type = None
    if code is None and error_type == 'insufficient_quota':
        code = 'insufficient_quota'
    elif code is None and error_type == 'rate_limit_error':
        code = 'rate_limit_exceeded'
    if code is None:
        code = 'unclassified_429' if status == 429 else 'unclassified_provider_error'
    reference = ''
    retry_after = None
    if headers is not None:
        candidate = str(headers.get('x-request-id', ''))
        if re.fullmatch(r'req_[A-Za-z0-9_-]{8,100}', candidate):
            reference = candidate
        delay = str(headers.get('retry-after', ''))
        if re.fullmatch(r'[0-9]{1,4}', delay) and 1 <= int(delay) <= 3600:
            retry_after = int(delay)
    return {
        'status': status,
        'code': code,
        'error_type': error_type,
        'request_id': reference or None,
        'retry_after_seconds': retry_after,
        'description': DIAGNOSES.get(
            code, 'Penyebab 429 belum diketahui; periksa error.code, saldo API, dan Limits pada organisasi/project yang benar.'
            if status == 429 else 'Provider tidak menerima permintaan voice.'
        ),
    }


def browser_error_description(diagnostic: dict) -> str:
    """Bounded actionable message safe for an authenticated SONIC owner."""
    status = diagnostic['status']
    code = diagnostic['code']
    result = f'Voice provider rejected initialization (HTTP {status}; code: {code}). {diagnostic["description"]}'
    delay = diagnostic.get('retry_after_seconds')
    if delay and code == 'rate_limit_exceeded':
        result += f' Retry-After: {delay} detik.'
    return result[:600]
