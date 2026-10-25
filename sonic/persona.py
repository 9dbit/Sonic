"""Owner-only persistent SONIC persona. Controls tone, never permissions or tools.

The ten voice mappings are curated listening categories, NOT provider-guaranteed
voice gender. OpenAI's Realtime voice inventory currently includes all ten IDs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from . import auth
from .db import PersonaPreference, get_db, utcnow

router = APIRouter()

VOICES = (
    {'id': 'male_01', 'provider_voice': 'cedar', 'group': 'male', 'label': 'Deep / composed'},
    {'id': 'male_02', 'provider_voice': 'ash', 'group': 'male', 'label': 'Clear / grounded'},
    {'id': 'male_03', 'provider_voice': 'echo', 'group': 'male', 'label': 'Measured / direct'},
    {'id': 'male_04', 'provider_voice': 'ballad', 'group': 'male', 'label': 'Expressive / smooth'},
    {'id': 'male_05', 'provider_voice': 'verse', 'group': 'male', 'label': 'Contemporary / bright'},
    {'id': 'female_01', 'provider_voice': 'marin', 'group': 'female', 'label': 'Warm / clear'},
    {'id': 'female_02', 'provider_voice': 'coral', 'group': 'female', 'label': 'Lively / friendly'},
    {'id': 'female_03', 'provider_voice': 'shimmer', 'group': 'female', 'label': 'Soft / polished'},
    {'id': 'female_04', 'provider_voice': 'sage', 'group': 'female', 'label': 'Calm / thoughtful'},
    {'id': 'female_05', 'provider_voice': 'alloy', 'group': 'female', 'label': 'Modern / neutral'},
)
VOICE_BY_ID = {v['id']: v for v in VOICES}

STYLE_PROMPTS = {
    'professional': 'Use professional, respectful, organized and concise language.',
    'tegas': 'Use firm, decisive, direct language without being rude.',
    'casual': 'Use natural, relaxed, conversational phrasing.',
    'friendly': 'Use warm, approachable, helpful language without being overly familiar.',
    'family': 'Use gentle, caring, family-friendly language and age-appropriate wording.',
    'romantic': 'Use soft, affectionate, respectful non-sexual expressions; respect boundaries.',
    'humor': 'Use light, contextual wit; never joke about distress, danger or sensitive facts.',
    'poetic': 'Use occasional graceful imagery, but remain clear and accurate.',
    'robot': 'Use precise, minimal, systematic, neutral phrasing.',
    'glitch': 'Use an occasional playful digital flourish; do not fake errors, logs, or facts.',
}
INTENSITY_PROMPTS = {
    'short': 'Answer briefly, typically one or two sentences.',
    'balanced': 'Use a natural moderate length appropriate to the task.',
    'expressive': 'Add useful detail and emotion where appropriate; remain focused.',
}
PRESETS = {
    'work': {'voice_id': 'male_01', 'style': 'professional', 'intensity': 'short'},
    'personal': {'voice_id': 'male_01', 'style': 'friendly', 'intensity': 'balanced'},
    'experimental': {'voice_id': 'male_05', 'style': 'glitch', 'intensity': 'expressive'},
}
DEFAULT = {'voice_id': 'male_01', 'style': 'friendly', 'intensity': 'balanced'}

class PersonaSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    voice_id: Literal['male_01','male_02','male_03','male_04','male_05',
                      'female_01','female_02','female_03','female_04','female_05']
    style: Literal['professional','tegas','casual','friendly','family','romantic','humor','poetic','robot','glitch']
    intensity: Literal['short','balanced','expressive']


def profile(db: Session) -> dict[str, str]:
    row = db.get(PersonaPreference, 1)
    if not row:
        return dict(DEFAULT)
    return {'voice_id': row.voice_id if row.voice_id in VOICE_BY_ID else DEFAULT['voice_id'],
            'style': row.style if row.style in STYLE_PROMPTS else DEFAULT['style'],
            'intensity': row.intensity if row.intensity in INTENSITY_PROMPTS else DEFAULT['intensity']}


def provider_voice(item: dict) -> str:
    return VOICE_BY_ID.get(item.get('voice_id'), VOICE_BY_ID[DEFAULT['voice_id']])['provider_voice']


def persona_instruction(item: dict) -> str:
    """Untrusted owner settings only select allowlisted, hard-coded tone instructions."""
    style = STYLE_PROMPTS.get(item.get('style'), STYLE_PROMPTS[DEFAULT['style']])
    intensity = INTENSITY_PROMPTS.get(item.get('intensity'), INTENSITY_PROMPTS[DEFAULT['intensity']])
    return ('SONIC Persona (communication style only): ' + style + ' ' + intensity +
            ' Keep facts, privacy, approvals, safety rules, and tool permissions unchanged. '
            'Never fabricate system actions, memory receipts or PC access.')


def update_profile(db: Session, data: dict[str, str]) -> dict[str, str]:
    row = db.get(PersonaPreference, 1)
    if row is None:
        row = PersonaPreference(id=1)
        db.add(row)
    row.voice_id, row.style, row.intensity = data['voice_id'], data['style'], data['intensity']
    row.updated_at = utcnow()
    db.commit()
    return profile(db)


@router.get('/api/persona')
def read_persona(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return {'active': profile(db), 'voices': VOICES, 'styles': list(STYLE_PROMPTS),
            'intensities': list(INTENSITY_PROMPTS), 'presets': PRESETS,
            'voice_note': 'Curated male/female-inspired groupings are subjective, not certified voice gender. Preview to choose.',
            'requires_new_realtime_session_for_voice_change': True}


@router.put('/api/persona')
def save_persona(data: PersonaSelection, _: dict = Depends(auth.require_owner_write),
                 db: Session = Depends(get_db)):
    return {'saved': True, 'active': update_profile(db, data.model_dump()),
            'note': 'New realtime voice selection applies to the next voice session.'}


@router.post('/api/persona/presets/{name}')
def apply_preset(name: Literal['work','personal','experimental'],
                 _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    return {'saved': True, 'active': update_profile(db, PRESETS[name]), 'preset': name}
