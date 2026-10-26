import pytest
from sonic.voice_intent import parse_voice_intent,parse_followup_name

@pytest.mark.parametrize('speech,name',[
  ('Buatkan di desktop dengan nama foldernya Today.', 'Today'),
  ('SONIC tolong buatkan folder bernama Today di desktop TRADEVICEPC.', 'Today'),
  ('Bisa tolong bikin folder Today pada Desktop komputer saya?', 'Today'),
  ('Buatkan folder baru di desktop, nama foldernya Today.', 'Today'),
  ('Buatkan folder yang namanya Today di Desktop.', 'Today'),
  ('Bikin folder namanya Today di dekstop PC.', 'Today'),
  ('Tolong buatkan folder Today di desktop.', 'Today'),
  ('SONIK, buat folder Today di desktop Tradevice PC', 'Today'),
  ('Tolong dibikinin folder di desktop dengan nama Today', 'Today'),
])
def test_voice_variations_produce_safe_desktop_action(speech,name):
    x=parse_voice_intent(speech)
    assert x.kind=='action', (speech,x)
    assert x.action.action=='desktop.mkdir'
    assert x.action.payload=={'name':name}


@pytest.mark.parametrize('speech',[
 'Tolong buatkan folder di Desktop.',
 'Buatkan di Desktop dengan nama foldernya.',
 'Buat folder baru di Desktop.',
])
def test_missing_desktop_folder_name_requests_a_slot(speech):
    x=parse_voice_intent(speech)
    assert x.kind=='need_name',(speech,x)
    assert x.detail=='desktop'

@pytest.mark.parametrize('speech',[
 'Bagaimana cara membuat folder Today di Desktop?',
 'Jangan buat folder Today di Desktop.',
 'Sebelumnya kamu sudah buatkan folder Today di Desktop, betul?',
 'Misalnya kita buat folder rahasia di desktop.',
])
def test_questions_negations_prior_history_do_not_execute(speech):
    x=parse_voice_intent(speech)
    assert x.kind=='not_pc',(speech,x)


def test_voice_folder_without_location_needs_destination():
    x=parse_voice_intent('Buat folder Today')
    assert x.kind=='need_location'


@pytest.mark.parametrize('name',[
 'Today','namanya Today','nama foldernya Markstudios Project',
])
def test_slot_followup_accepts_only_safe_explicit_name(name):
    assert parse_followup_name(name) in ('Today','Markstudios Project')

@pytest.mark.parametrize('bad',[
 '../Windows','D:\\Windows','secrets','NUL','folder/child','jangan jadi','apakah sudah jadi?',
 'tolong buat folder lagi','delete all','folder; shutdown'
])
def test_slot_followup_rejects_unsafe_or_new_task(bad):
    assert parse_followup_name(bad) is None
