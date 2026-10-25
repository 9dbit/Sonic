"""SONIC 0.3 browser + real local HTTP QA, with disposable synthetic data.

No OpenAI calls, production DB, credentials, or TRADEVICEPC operations.
Uses system Chromium when present, otherwise Playwright's Chromium install.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'


@contextlib.contextmanager
def local_server():
    with tempfile.TemporaryDirectory(prefix='sonic-neural-qa-') as temp:
        owner = secrets.token_urlsafe(32)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.startswith(('SONIC_', 'OPENAI_', 'DATABASE_', 'RAILWAY_'))}
        env.update(SONIC_ENV='local', SONIC_PUBLIC_URL=f'http://127.0.0.1:{port}',
                   SONIC_LOCAL_DB=str(Path(temp) / 'qa.sqlite3'), SONIC_SESSION_SECRET=secrets.token_urlsafe(48),
                   SONIC_OWNER_TOKEN_SHA256=hashlib.sha256(owner.encode()).hexdigest(), PYTHONPATH=str(ROOT))
        log = open(Path(temp) / 'server.log', 'w')
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'sonic.api:app', '--host', '127.0.0.1', '--port', str(port)],
                                cwd=ROOT, env=env, stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    if httpx.get(base + '/api/health', timeout=.5).status_code == 200: break
                except httpx.HTTPError: pass
                if proc.poll() is not None: raise RuntimeError('Local server exited')
                time.sleep(.08)
            else: raise RuntimeError('Local server not ready')
            yield base, owner
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            log.close()


def run():
    ARTIFACTS.mkdir(exist_ok=True)
    results = []
    with local_server() as (base, owner), sync_playwright() as pw:
        opts = {'headless': True, 'args': ['--no-sandbox', '--enable-unsafe-swiftshader']}
        executable = shutil.which('chromium')
        if executable: opts['executable_path'] = executable
        browser = pw.chromium.launch(**opts)
        try:
            for name, size in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
                context = browser.new_context(viewport=size, device_scale_factor=1, is_mobile=name=='mobile', has_touch=name=='mobile')
                page = context.new_page(); page.set_default_timeout(15000); errors=[]
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    page.goto(base)
                    page.locator('#ownerToken').fill(owner)
                    page.locator('#loginForm button').click()
                    expect(page.locator('#setupPanel')).to_be_visible()
                    page.locator('[data-tab=brain]').click()
                    expect(page.locator('#brainPanel')).to_be_visible()
                    expect(page.locator('#graphCounts')).to_contain_text('memories')
                    page.locator('#brainMessage').fill('SONIC, simpan ke memoriku bahwa saya suka bakso')
                    page.locator('#brainSend').click()
                    expect(page.locator('#brainAnswerText')).to_contain_text('tersimpan', ignore_case=True)
                    expect(page.locator('#brainReceipt .receipt')).to_be_visible()
                    page.locator('[data-tab=memory]').click()
                    expect(page.locator('#memoryList')).to_contain_text('saya suka bakso')
                    page.reload()
                    expect(page.locator('#setupPanel')).to_be_visible()
                    page.locator('[data-tab=memory]').click()
                    expect(page.locator('#memoryList')).to_contain_text('saya suka bakso')
                    page.locator('#memoryInput').fill('Kantor contoh saya di Bandung ' + name)
                    page.locator('#memoryForm button').click()
                    expect(page.locator('#memoryList')).to_contain_text('Kantor contoh')
                    page.locator('[data-tab=brain]').click()
                    if name == 'mobile' and not page.locator('#graphInspector').is_visible():
                        page.locator('#toggleInspector').click()
                    page.locator('#graphSearch').fill('saya suka bakso')
                    page.locator('#searchResults button').first.click()
                    expect(page.locator('#nodeInspector')).to_contain_text('saya suka bakso')
                    page.locator('#nodeInspector').get_by_role('button', name='Connect note').click()
                    form = page.locator('.link-form')
                    form.locator('input[type=text]').fill('contoh hubungan terkonfirmasi')
                    form.locator('input[type=checkbox]').check()
                    # A delayed/manual graph refresh must not discard a consented draft.
                    with page.expect_response(lambda r: '/api/knowledge/graph' in r.url and r.request.method == 'GET'):
                        page.locator('#refreshGraph').click()
                    page.wait_for_timeout(250)
                    expect(form.locator('input[type=text]')).to_have_value('contoh hubungan terkonfirmasi')
                    expect(form.locator('input[type=checkbox]')).to_be_checked()
                    form.get_by_role('button', name='Save relation').click()
                    expect(page.locator('#nodeInspector .saved-link').first).to_be_visible()
                    page.locator('[data-depth="2"]').click()
                    if name=='mobile': page.locator('#closeInspector').click()
                    page.locator('#dimensionGraph').click()
                    expect(page.locator('#dimensionGraph')).to_have_text('2D')
                    page.locator('#dimensionGraph').click()
                    page.locator('#fitGraph').click()
                    page.wait_for_timeout(200)
                    before=page.evaluate('window.sonicGraph.yaw')
                    rect=page.locator('#graphStage').bounding_box()
                    x=rect['x']+rect['width']*.5; y=rect['y']+rect['height']*.27
                    page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+45,y+12,steps=8); page.mouse.up()
                    assert page.evaluate('window.sonicGraph.yaw') != before
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    engine=page.locator('#graphStage').get_attribute('data-engine')
                    assert engine and ('WebGL' in engine or 'Canvas' in engine)
                    page.screenshot(path=str(ARTIFACTS / f'sonic-{name}-memory-graph.png'))
                    # Synthetic richness exists ONLY in this throw-away local database.
                    if name=='desktop':
                        session=page.request.get(base+'/api/session').json()
                        fixtures=[]
                        for project,topic in [('Atlas','interior hotel'),('Harbor','restoran marina'),('Grove','taman vila'),('Orbit','workspace studio')]:
                            fixtures.extend([
                                f'Project {project}: desain {topic} menggunakan material kayu.',
                                f'Project {project}: jadwal review desain setiap Senin.',
                                f'Project {project}: proposal warna biru dengan material batu.',
                                f'Project {project}: dokumentasi desain dengan sumber yang jelas.'
                            ])
                        fixtures.extend([
                            'Riset contoh: Python untuk automasi data.',
                            'Riset contoh: JavaScript untuk visualisasi data.',
                            'Riset contoh: API dan database untuk memory persisten.',
                            'Preferensi contoh: tema gelap dengan aksen teal.',
                            'Preferensi contoh: catatan harus rapi dan terbaca.',
                            'Workshop Bandung: pembahasan desain dan visualisasi graph.',
                            'Workshop Jakarta: pembahasan API dan keamanan data.'
                        ])
                        for text in fixtures:
                            r=page.request.post(base+'/api/memories',data={'text':text},headers={'X-Sonic-CSRF':session['csrf']})
                            assert r.ok, r.text()
                        page.locator('#graphSearch').fill('')
                        page.locator('#clearFocus').click()
                        page.locator('#refreshGraph').click(); page.wait_for_timeout(300)
                        page.locator('#fitGraph').click(); page.wait_for_timeout(200)
                        page.screenshot(path=str(ARTIFACTS / 'sonic-desktop-neural-fixture.png'))
                    page.locator('[data-tab=setup]').click(); page.locator('#setupLogout').click()
                    expect(page.locator('#loginOverlay')).to_be_visible()
                    assert not errors, 'Browser errors: ' + json.dumps(errors)
                    results.append({'viewport':name,'status':'PASS','javascript_errors':0,'engine':engine})
                except Exception:
                    page.screenshot(path=str(ARTIFACTS / f'sonic-{name}-failure.png'))
                    raise
                finally:
                    context.close()
        finally: browser.close()
    report={'results':results,'live_openai_tested':False,'production_data_used':False,'physical_iphone_tested':False,'screenshots_use':'Disposable local QA data, never seeded into production.'}
    (ARTIFACTS/'neural-browser-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__': run()
