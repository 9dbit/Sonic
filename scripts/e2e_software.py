"""Software Manager acceptance in the full app with a synthetic Windows device.

Uses a disposable local owner/session/database and real authenticated HTTP
callbacks. Never runs WinGet, installs software, or contacts TRADEVICEPC.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

import httpx
from playwright.sync_api import sync_playwright, expect

from qa_server import local_server


OUT = Path('artifacts/software-manager')
OUT.mkdir(parents=True, exist_ok=True)
DEVICE_TOKEN = 'synthetic-software-agent-token-only-for-local-qa'
SETTINGS = {
    'SONIC_DEVICE_TOKEN_SHA256': hashlib.sha256(DEVICE_TOKEN.encode()).hexdigest(),
    'SONIC_ENABLE_SOFTWARE_DISCOVERY': 'true',
    'SONIC_ENABLE_SOFTWARE_INSTALL': 'true',
}


def plan_for(payload):
    return {**payload, 'source': 'winget', 'scope': 'user', 'allow_reboot': False}


def digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def installation_result(plan):
    installed = {key: plan[key] for key in ('package_id', 'version', 'source')}
    return {'ok': True, 'status': 'succeeded', 'plan_sha256': digest(plan),
            'installed': installed, 'requested_scope': 'user', 'scope_verified': False,
            'evidence': {'kind': 'winget_export_json', 'packages': [installed]},
            'verification': {'status': 'agent_verified', 'method': 'winget_export_json'}}


with local_server(settings=SETTINGS) as (url, owner), sync_playwright() as playwright:
    def agent(route, payload):
        response = httpx.post(url + route, headers={'Authorization': 'Bearer ' + DEVICE_TOKEN},
                              json=payload, timeout=12)
        assert response.status_code == 200, (route, response.status_code, response.text[:400])
        return response.json()

    heartbeat = {'device_id': 'TRADEVICEPC', 'hostname': 'Synthetic TRADEVICEPC', 'platform': 'Windows',
                 'agent_version': '1.1.0',
                 'capabilities': ['system.status', 'system.metrics', 'software.search',
                                  'software.inspect', 'software.inventory', 'software.install'],
                 'metrics': {'ram_total_bytes': 16 * 2**30, 'ram_available_bytes': 8 * 2**30},
                 'gui_targets': []}

    def next_job(page, action):
        for _ in range(50):
            job = agent('/api/device/operator/next', {}).get('job')
            if job:
                assert job['action'] == action, job
                return job
            page.wait_for_timeout(120)
        raise AssertionError('No queued job for ' + action)

    def complete(job, result, success=True):
        return agent('/api/device/operator/result', {'request_id': job['id'], 'lease': job['lease'],
                                                     'success': success, 'result': result})

    browser = playwright.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chrome') or None,
                                          headless=True, args=['--no-sandbox', '--enable-unsafe-swiftshader'])
    reports = []
    for label, viewport, version in [('desktop', {'width': 1440, 'height': 1000}, '1.2.3'),
                                     ('mobile', {'width': 390, 'height': 844}, '2.3.4')]:
        agent('/api/device/heartbeat', heartbeat)
        page = browser.new_page(viewport=viewport, device_scale_factor=1,
                                has_touch=label == 'mobile', is_mobile=label == 'mobile')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url, wait_until='networkidle')
        page.locator('#ownerToken').fill(owner)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.locator('.nav[data-tab=devices]').click()
        expect(page.locator('#softwareManager')).to_be_visible()
        expect(page.locator('#softwareReady')).to_have_text('Siap mencari & memasang', timeout=12000)
        assert not page.locator('#softwareSourceAgreement').is_checked()
        assert not page.locator('#softwarePackageAgreement').is_checked()
        assert agent('/api/device/operator/next', {})['job'] is None

        # Search is an explicit read-only request, with no inferred source terms.
        page.locator('#softwareQuery').fill('editor')
        page.locator('#softwareSearch').click()
        search = next_job(page, 'software.search')
        assert search['payload'] == {'query': 'editor', 'accept_source_agreements': False}
        complete(search, {'ok': True, 'status': 'searched', 'source_identity_verified': True,
                          'evidence': {'kind': 'winget_search_raw', 'exit_code': 0,
                                       'stdout': 'Example Editor  Example.Editor  ' + version, 'stderr': ''}})
        expect(page.locator('#softwareStatus')).to_have_text('Pencarian selesai', timeout=12000)
        expect(page.locator('#softwareOutput')).to_contain_text('Example.Editor')

        # Inspect first with no package agreement; display arbitrary catalog text literally.
        page.locator('#softwarePackage').fill('Example.Editor')
        page.locator('#softwareVersion').fill(version)
        page.locator('#softwareInspect').click()
        first = next_job(page, 'software.inspect')
        assert first['payload']['accept_package_agreements'] is False
        plan = plan_for(first['payload'])
        metadata = ('Publisher: Example Publisher\nVersion: ' + version +
                    '\nLicense: Synthetic test license\n<img src=x onerror="window.softwareXss=true">')
        complete(first, {'ok': True, 'status': 'inspected', 'plan': plan, 'plan_sha256': digest(plan),
                         'source_identity_verified': True, 'metadata_parsed': False,
                         'publisher_signature_verified': False,
                         'evidence': {'kind': 'winget_show_raw', 'exit_code': 0, 'stdout': metadata, 'stderr': ''}})
        expect(page.locator('#softwareStatus')).to_have_text('Paket diperiksa', timeout=12000)
        expect(page.locator('#softwareOutput')).to_contain_text('<img src=x')
        assert page.locator('#softwareOutput img').count() == 0
        assert page.evaluate('window.softwareXss === undefined')
        assert page.locator('#softwareReviewInstall').is_disabled()

        # Changing agreement choices invalidates the inspection. Both are bound to a new plan.
        page.locator('#softwareSourceAgreement').check()
        page.locator('#softwarePackageAgreement').check()
        assert page.locator('#softwareReviewInstall').is_disabled()
        page.locator('#softwareInspect').click()
        inspection = next_job(page, 'software.inspect')
        assert inspection['payload']['accept_package_agreements'] is True
        assert inspection['payload']['accept_source_agreements'] is True
        plan = plan_for(inspection['payload'])
        complete(inspection, {'ok': True, 'status': 'inspected', 'plan': plan, 'plan_sha256': digest(plan),
                              'source_identity_verified': True, 'metadata_parsed': False,
                              'publisher_signature_verified': False,
                              'evidence': {'kind': 'winget_show_raw', 'exit_code': 0, 'stdout': metadata, 'stderr': ''}})
        expect(page.locator('#softwareReviewInstall')).to_be_enabled(timeout=12000)
        page.locator('#softwareManager').scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / f'{label}-software-manager.png'), full_page=False)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')

        # Preview cannot dispatch. Even a rapid double click on final approval dispatches one job.
        page.locator('#softwareReviewInstall').click()
        expect(page.locator('#softwareApproval')).to_be_visible()
        expect(page.locator('#softwareApprovalDetails')).to_contain_text(version)
        expect(page.locator('#softwareApprovalDetails')).to_contain_text('Example.Editor')
        assert agent('/api/device/operator/next', {})['job'] is None
        page.screenshot(path=str(OUT / f'{label}-install-approval.png'), full_page=False)
        page.locator('#softwareApprovalConfirm').evaluate('(button) => {button.click(); button.click();}')
        install = next_job(page, 'software.install')
        assert install['payload'] == {'plan': plan, 'plan_sha256': digest(plan)}
        assert agent('/api/device/operator/next', {})['job'] is None
        complete(install, installation_result(plan))
        expect(page.locator('#softwareStatus')).to_have_text('Versi terpasang terverifikasi', timeout=12000)
        expect(page.locator('#softwareOutput')).to_contain_text(version)

        # An authenticated inventory receipt remains useful after installation.
        page.locator('#softwareInventory').click()
        inventory = next_job(page, 'software.inventory')
        assert inventory['payload'] == {}
        complete(inventory, {'ok': True, 'status': 'inventoried', 'evidence':
                             {'kind': 'winget_export_json', 'packages': [installation_result(plan)['installed']]}})
        expect(page.locator('#softwareStatus')).to_have_text('Inventaris diterima', timeout=12000)

        late_cancel = False
        if label == 'desktop':
            # Cloud cancellation can precede a late installer receipt. UI must preserve both facts.
            page.locator('#softwareVersion').fill('9.9.9')
            page.locator('#softwareInspect').click()
            late_inspect = next_job(page, 'software.inspect')
            late_plan = plan_for(late_inspect['payload'])
            complete(late_inspect, {'ok': True, 'status': 'inspected', 'plan': late_plan,
                                    'plan_sha256': digest(late_plan), 'evidence':
                                    {'kind': 'winget_show_raw', 'exit_code': 0, 'stdout': 'Synthetic 9.9.9 package'}})
            expect(page.locator('#softwareReviewInstall')).to_be_enabled(timeout=12000)
            page.locator('#softwareReviewInstall').click()
            page.locator('#softwareApprovalConfirm').click()
            late_install = next_job(page, 'software.install')
            page.evaluate("async (id) => window.sonicSoftware.api('/api/operator/requests/' + id, {method:'DELETE'})", late_install['id'])
            result = complete(late_install, installation_result(late_plan))
            assert result['state'] == 'cancelled', result
            expect(page.locator('#softwareStatus')).to_contain_text('dibatalkan', timeout=12000)
            page.locator('#softwareRefreshHistory').click()
            history_row = page.locator('.software-history-row').filter(has_text='9.9.9').first
            expect(history_row).to_contain_text('dibatalkan', timeout=12000)
            history_row.locator('button').click()
            expect(page.locator('#softwareStatus')).to_contain_text('bukti akhir')
            assert page.locator('#softwareStatus').get_attribute('data-state') == 'unknown'
            assert agent('/api/device/operator/next', {})['job'] is None
            late_cancel = True

        assert errors == [], errors
        reports.append({'viewport': label, 'search_receipt': True, 'agreements_explicit': True,
                        'catalog_xss_inert': True, 'inspection_bound_to_plan': True,
                        'no_install_before_final_approval': True, 'single_install_on_double_click': True,
                        'exact_version_evidence': True, 'inventory_receipt': True,
                        'late_cancellation_evidence': late_cancel, 'browser_errors': errors,
                        'synthetic_windows_only': True})
        page.close()
    browser.close()
    print(json.dumps(reports, indent=2))
