/* Explicit software operations through SONIC's authenticated native queue.
 * Search output is untrusted display text. It never becomes executable input.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const FINISHED = new Set(['done', 'failed', 'cancelled', 'expired']);
  const READ = new Set(['software.search', 'software.inspect', 'software.inventory']);
  const PLAN_KEYS = ['accept_package_agreements', 'accept_source_agreements', 'allow_reboot',
    'package_id', 'scope', 'source', 'version'];
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function validPlan(plan) {
    return Boolean(plan && typeof plan === 'object' && !Array.isArray(plan) &&
      JSON.stringify(Object.keys(plan).sort()) === JSON.stringify(PLAN_KEYS) &&
      typeof plan.package_id === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.+-]{1,127}$/.test(plan.package_id) &&
      typeof plan.version === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}$/.test(plan.version) &&
      !['latest','stable','current','any'].includes(plan.version.toLowerCase()) &&
      plan.source === 'winget' && plan.scope === 'user' && plan.allow_reboot === false &&
      typeof plan.accept_source_agreements === 'boolean' && typeof plan.accept_package_agreements === 'boolean');
  }
  function installedEvidenceMatches(receipt) {
    const plan = receipt.payload?.plan, result = receipt.result || {}, installed = result.installed;
    if (!validPlan(plan) || !installed || result.evidence?.kind !== 'winget_export_json' ||
        result.verification?.status !== 'agent_verified' || result.verification?.method !== 'winget_export_json') return false;
    const matches = pkg => pkg && pkg.package_id === plan.package_id &&
      pkg.version === plan.version && pkg.source === plan.source;
    return matches(installed) && Array.isArray(result.evidence.packages) && result.evidence.packages.some(matches);
  }
  function receiptLabel(receipt) {
    const result = receipt.result || {}, status = result.status || receipt.state;
    if (receipt.action === 'software.install') {
      if (['cancelled', 'expired'].includes(receipt.state)) {
        const stopped = receipt.state === 'cancelled' ? 'Permintaan dibatalkan' : 'Waktu permintaan berakhir';
        return stopped + (installedEvidenceMatches(receipt) ? '; versi terpasang ditemukan pada bukti akhir' : '; perubahan installer belum terverifikasi');
      }
      if (['succeeded', 'already_installed'].includes(status)) {
        if (!installedEvidenceMatches(receipt)) return 'Versi terpasang belum terverifikasi';
        return status === 'already_installed' ? 'Versi yang dipilih sudah terpasang' : 'Versi terpasang terverifikasi';
      }
      if (['reconciliation_required', 'indeterminate'].includes(status)) return 'Hasil belum pasti — perlu rekonsiliasi';
      if (status === 'requires_user_action') return 'Memerlukan tindakan lokal di PC';
      if (status === 'reboot_required') return 'Installer meminta restart — belum dijalankan oleh SONIC';
      if (receipt.state === 'done') return 'Laporan diterima — hasil instalasi belum terverifikasi';
    }
    return ({pending:'Menunggu persetujuan', queued:'Dalam antrean PC', leased:'Sedang berjalan di PC',
      done:'Pemeriksaan selesai', failed:'Pekerjaan tidak selesai', expired:'Waktu tunggu berakhir',
      cancelled:'Permintaan dibatalkan', blocked:'Diblokir oleh aturan instalasi',
      inspected:'Paket diperiksa', searched:'Pencarian selesai', inventoried:'Inventaris diterima',
      succeeded:'Pemeriksaan selesai'}[status] || String(status || 'Status belum tersedia'));
  }
  function rawEvidence(result) {
    const evidence = result?.evidence || {};
    if (Array.isArray(evidence.packages)) {
      return evidence.packages.slice(0, 500).map(pkg =>
        `${String(pkg.package_id || '')}  |  ${pkg.version == null ? 'versi tidak diketahui' : String(pkg.version)}  |  ${String(pkg.source || '')}`
      ).join('\n') || 'Tidak ada paket yang cocok dalam inventaris WinGet.';
    }
    return [evidence.stdout, evidence.stderr].filter(value => typeof value === 'string' && value)
      .join('\n').slice(0, 26000) || (result?.error || result?.code ? String(result.error || result.code).slice(0, 1500) : 'Tidak ada output teks dari perangkat.');
  }

  class SoftwareManager {
    constructor(options = {}) {
      this.api = options.api || this.request.bind(this);
      this.pause = options.pause || pause;
      this.now = options.now || Date.now;
      this.busy = false; this.refreshing = false; this.active = null; this.pending = null;
      this.inspection = null; this.cursor = 0; this.needsReconcile = false;
      this.cap = {}; this.historyRows = []; this.lastRefresh = 0;
      this.dialog = $('softwareApproval');
      $('softwareSearchForm').addEventListener('submit', event => {
        event.preventDefault();
        this.runRead('software.search', {query: $('softwareQuery').value.trim(),
          accept_source_agreements: $('softwareSourceAgreement').checked});
      });
      $('softwareInspectForm').addEventListener('submit', event => {
        event.preventDefault();
        this.runRead('software.inspect', this.inspectPayload());
      });
      $('softwareInventory').addEventListener('click', () => this.runRead('software.inventory', {}));
      $('softwareReviewInstall').addEventListener('click', () => this.reviewInstall());
      $('softwareApprovalConfirm').addEventListener('click', () => this.approveInstall());
      $('softwareApprovalCancel').addEventListener('click', () => this.reject());
      this.dialog.addEventListener('cancel', event => {event.preventDefault(); this.reject();});
      for (const id of ['softwarePackage', 'softwareVersion', 'softwareSourceAgreement', 'softwarePackageAgreement']) {
        $(id).addEventListener(id.endsWith('Agreement') ? 'change' : 'input', () => this.invalidatePlan());
      }
      $('softwareRefreshHistory').addEventListener('click', () => this.history());
      $('softwareRefresh').addEventListener('click', () => this.refreshAndRecover());
      if (options.autoRefresh !== false) {
        this.timer = setInterval(() => {
          if (!document.hidden && !$('devicesPanel').classList.contains('hidden')) this.refresh();
        }, 12000);
        if (typeof MutationObserver !== 'undefined') {
          this.observer = new MutationObserver(() => {
            if (!$('devicesPanel').classList.contains('hidden')) this.refresh();
          });
          this.observer.observe($('devicesPanel'), {attributes:true, attributeFilter:['class']});
        }
        this.refresh();
      }
      this.controls();
    }

    async request(path, opts = {}) {
      const sessionResponse = await fetch('/api/session', {credentials:'same-origin', cache:'no-store'});
      const session = await sessionResponse.json();
      if (!sessionResponse.ok || !session.authenticated) {
        const error = Error('Masuk sebagai pemilik SONIC untuk melanjutkan.'); error.status = 401; throw error;
      }
      const headers = {'Content-Type':'application/json', ...(opts.headers || {})};
      if (opts.method && opts.method !== 'GET') headers['X-Sonic-CSRF'] = session.csrf;
      const response = await fetch(path, {credentials:'same-origin', cache:'no-store', ...opts, headers});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = Error(typeof body.detail === 'string' ? body.detail : 'HTTP ' + response.status);
        error.status = response.status; throw error;
      }
      return body;
    }
    inspectPayload() {
      return {package_id:$('softwarePackage').value.trim(), version:$('softwareVersion').value.trim(),
        accept_source_agreements:$('softwareSourceAgreement').checked,
        accept_package_agreements:$('softwarePackageAgreement').checked};
    }
    ready(action) {
      return this.cap.connected === true && this.cap.metrics_available === true &&
        this.cap.software?.discovery_enabled === true &&
        Array.isArray(this.cap.capabilities) && this.cap.capabilities.includes(action) &&
        (action !== 'software.install' || this.cap.software?.installation_enabled === true);
    }
    controls() {
      const locked = this.busy || Boolean(this.pending) || this.needsReconcile;
      for (const [id, action] of [['softwareSearch','software.search'], ['softwareInspect','software.inspect'],
        ['softwareInventory','software.inventory']]) $(id).disabled = locked || !this.ready(action);
      $('softwareReviewInstall').disabled = locked || !this.ready('software.install') || !this.currentPlan();
      $('softwareApprovalConfirm').disabled = this.busy || !this.pending;
      $('softwareApprovalCancel').disabled = this.busy;
    }
    status(text, state = 'idle') {
      $('softwareStatus').textContent = text;
      $('softwareStatus').dataset.state = state;
    }
    invalidatePlan() {
      this.inspection = null;
      $('softwarePlanHint').textContent = 'Pilihan berubah. Periksa ulang paket, versi, dan persetujuan lisensinya.';
      this.controls();
    }
    currentPlan() {
      if (!this.inspection || this.now() >= this.inspection.expires_at) return false;
      const plan = this.inspection.plan, current = this.inspectPayload();
      return validPlan(plan) && plan.accept_source_agreements && plan.accept_package_agreements &&
        Object.keys(current).every(key => current[key] === plan[key]) &&
        /^[a-f0-9]{64}$/.test(this.inspection.plan_sha256);
    }
    async refresh() {
      if (this.refreshing) return;
      this.refreshing = true;
      try {
        this.cap = await this.api('/api/operator/capabilities');
        const ready = this.ready('software.search');
        $('softwareReady').textContent = !this.cap.connected ? 'PC offline' : ready ?
          (this.ready('software.install') ? 'Siap mencari & memasang' : 'Pencarian siap') : 'Fitur belum diaktifkan';
        $('softwareReady').dataset.ready = String(ready);
        this.lastRefresh = this.now();
      } catch (error) {
        this.cap = {};
        $('softwareReady').textContent = error.status === 401 ? 'Login pemilik diperlukan' : 'Koneksi belum terverifikasi';
        $('softwareReady').dataset.ready = 'false';
        if (error.status === 401) {
          this.inspection = null;
          $('softwareOutput').textContent = 'Masuk untuk melihat hasil perangkat.';
          $('softwareSelected').replaceChildren(); $('softwareSelected').hidden = true;
          $('softwareHistory').replaceChildren();
        }
      } finally {this.refreshing = false; this.controls();}
    }
    async refreshAndRecover() {
      await this.refresh();
      await this.history();
      if (this.active && !this.busy) {
        const active = this.active; this.busy = true; this.controls();
        try {await this.watch(active);} finally {this.busy = false; this.controls();}
      }
    }
    async runRead(action, payload) {
      if (!READ.has(action) || this.busy || this.pending || this.needsReconcile) return;
      this.busy = true; this.controls(); // Set before the first network await.
      let submitted = false;
      try {
        await this.refresh();
        if (!this.ready(action)) throw Error('Companion atau fitur software belum siap.');
        this.status('Menyiapkan pemeriksaan di TRADEVICEPC...', 'queued');
        if (action === 'software.inspect') this.inspection = null;
        submitted = true;
        const receipt = await this.api('/api/operator/requests', {method:'POST', body:JSON.stringify({action, payload})});
        this.active = receipt; this.cursor = 0;
        try {
          await this.api('/api/operator/requests/' + receipt.id + '/confirm', {
            method:'POST', body:JSON.stringify({confirm:true, digest:receipt.digest})});
        } catch (error) {
          this.status('Konfirmasi belum pasti. Memeriksa permintaan yang sama...', 'unknown');
        }
        await this.watch(receipt);
      } catch (error) {
        this.status('Pemeriksaan belum selesai: ' + error.message, 'failed');
        this.needsReconcile = Boolean(this.active) || (submitted && !error.status);
      } finally {this.busy = false; this.controls(); this.history();}
    }
    displayPlan(target, plan) {
      target.replaceChildren(); target.hidden = false;
      for (const [label, value] of [['Paket', plan.package_id], ['Versi', plan.version], ['Sumber', plan.source],
        ['Pemasangan diminta', 'Akun Windows ini (user)'], ['Ketentuan sumber', plan.accept_source_agreements ? 'Disetujui' : 'Belum disetujui'],
        ['Lisensi paket', plan.accept_package_agreements ? 'Disetujui' : 'Belum disetujui'], ['Restart otomatis', 'Tidak diminta']]) {
        target.append(element('dt', label), element('dd', value));
      }
    }
    async reviewInstall() {
      if (this.busy || this.pending || this.needsReconcile || !this.currentPlan()) return;
      this.busy = true; this.controls();
      const selected = this.inspection;
      let submitted = false;
      try {
        await this.refresh();
        if (!this.ready('software.install')) throw Error('Instalasi belum diaktifkan pada server dan PC.');
        if (selected !== this.inspection || !this.currentPlan()) throw Error('Pilihan berubah. Periksa paket kembali.');
        submitted = true;
        const receipt = await this.api('/api/operator/requests', {method:'POST', body:JSON.stringify({
          action:'software.install', payload:{plan:selected.plan, plan_sha256:selected.plan_sha256}})});
        this.showApproval(receipt, selected.metadata);
      } catch (error) {
        this.status('Instalasi belum dikirim: ' + error.message, 'failed');
        if (submitted && !error.status) this.needsReconcile = true;
      } finally {this.busy = false; this.controls();}
    }
    showApproval(receipt, metadata = '') {
      if (receipt.action !== 'software.install' || !validPlan(receipt.payload?.plan) || receipt.state !== 'pending') {
        throw Error('Rencana instalasi tidak valid. Periksa paket kembali.');
      }
      this.pending = receipt;
      this.displayPlan($('softwareApprovalDetails'), receipt.payload.plan);
      $('softwareApprovalMetadata').textContent = metadata || 'Rencana dipulihkan dari riwayat. Metadata lengkap tersedia pada hasil pemeriksaan paket.';
      $('softwareApprovalExpiry').textContent = 'Persetujuan berlaku sampai ' + this.formatTime(receipt.expires_at) + '.';
      $('softwareApprovalError').textContent = '';
      this.dialog.showModal(); this.controls();
    }
    async approveInstall() {
      if (this.busy || !this.pending) return;
      const receipt = this.pending;
      this.busy = true; this.controls(); this.active = receipt; this.cursor = 0;
      this.inspection = null; // A plan is consumed once, including uncertain attempts.
      try {
        await this.api('/api/operator/requests/' + receipt.id + '/confirm', {
          method:'POST', body:JSON.stringify({confirm:true, digest:receipt.digest})});
        this.pending = null; this.dialog.close();
        this.status('Instalasi masuk antrean TRADEVICEPC. Menunggu bukti perangkat.', 'queued');
        await this.watch(receipt);
      } catch (error) {
        this.pending = null; if (this.dialog.open) this.dialog.close();
        this.needsReconcile = true;
        this.status('Status persetujuan belum pasti. Permintaan tetap dapat diperiksa dari riwayat.', 'unknown');
        await this.watch(receipt);
      } finally {this.busy = false; this.controls(); this.history();}
    }
    async reject() {
      if (this.busy) return;
      const pending = this.pending;
      if (!pending) {if (this.dialog.open) this.dialog.close(); return;}
      this.busy = true; this.controls();
      try {
        await this.api('/api/operator/requests/' + pending.id, {method:'DELETE'});
        this.pending = null; this.inspection = null; this.dialog.close();
        this.status('Persetujuan dibatalkan. Instalasi tidak diminta.', 'cancelled');
      } catch (error) {
        $('softwareApprovalError').textContent = 'Pembatalan belum terkonfirmasi: ' + error.message;
      } finally {this.busy = false; this.controls();}
    }
    async watch(receipt) {
      this.active = receipt;
      const deadline = this.now() + 25 * 60 * 1000;
      let failures = 0;
      while (this.now() < deadline) {
        try {
          const record = await this.api('/api/operator/requests/' + receipt.id);
          failures = 0;
          $('softwareReceipt').textContent = 'ID pekerjaan: ' + receipt.id;
          this.status(receiptLabel(record), record.result?.status || record.state);
          if (record.state === 'pending') {
            this.needsReconcile = true;
            this.status('Permintaan belum disetujui. Tinjau dari riwayat untuk melanjutkan.', 'unknown');
            return;
          }
          if (FINISHED.has(record.state)) {
            this.showResult(record); this.active = null; this.needsReconcile = false; return;
          }
          try {
            const stream = await this.api('/api/operator/requests/' + receipt.id + '/stream?after=' + this.cursor);
            for (const event of stream.events || []) {
              if (event.sequence > this.cursor && event.sequence <= 48) {
                this.cursor = event.sequence;
                $('softwareOutput').textContent = ($('softwareOutput').textContent + '\n' + String(event.text || '')).slice(-26000);
              }
            }
          } catch (error) { /* Status receipts remain authoritative if the optional stream fails. */ }
        } catch (error) {
          failures += 1; this.needsReconcile = true;
          this.status('Koneksi hasil terputus. Memantau ID yang sama; instalasi tidak dikirim ulang.', 'unknown');
          if ([401, 403, 404].includes(error.status)) return;
        }
        await this.pause(Math.min(15000, 2000 + failures * 2000));
      }
      this.needsReconcile = true;
      this.status('Pemantauan dijeda. Periksa status atau riwayat sebelum melakukan pekerjaan berikutnya.', 'unknown');
    }
    showResult(record) {
      const result = record.result || {};
      $('softwareOutput').textContent = rawEvidence(result);
      $('softwareReceipt').textContent = 'ID pekerjaan: ' + record.id + ' · ' + this.formatTime(record.created_at);
      const installUnverified = record.action === 'software.install' && ['succeeded','already_installed'].includes(result.status) && !installedEvidenceMatches(record);
      const lateInstall = record.action === 'software.install' && ['cancelled','expired'].includes(record.state);
      this.status(receiptLabel(record), installUnverified || lateInstall ? 'unknown' : result.status || record.state);
      if (record.action === 'software.inspect' && record.state === 'done' && validPlan(result.plan) &&
          /^[a-f0-9]{64}$/.test(result.plan_sha256 || '')) {
        const plan = result.plan;
        // An old history view does not gain a new 30-minute inspection lifetime.
        const created = Date.parse(record.created_at || '');
        const expires = Number.isFinite(created) ? created + 30 * 60 * 1000 : this.now();
        this.inspection = {plan, plan_sha256:result.plan_sha256, expires_at:expires, metadata:rawEvidence(result)};
        $('softwarePackage').value = plan.package_id; $('softwareVersion').value = plan.version;
        $('softwareSourceAgreement').checked = plan.accept_source_agreements;
        $('softwarePackageAgreement').checked = plan.accept_package_agreements;
        this.displayPlan($('softwareSelected'), plan);
        $('softwarePlanHint').textContent = this.currentPlan() ?
          'Paket siap ditinjau. Tombol berikutnya menampilkan konfirmasi sebelum pemasangan.' :
          'Tinjau metadata dan lisensinya, pilih persetujuan yang sesuai, lalu periksa detail kembali.';
      } else if (record.action === 'software.install' && validPlan(record.payload?.plan)) {
        this.displayPlan($('softwareSelected'), record.payload.plan);
        this.inspection = null;
        $('softwarePlanHint').textContent = 'Lihat hasil pekerjaan. Percobaan ulang membutuhkan pemeriksaan paket baru.';
      }
      this.controls();
    }
    formatTime(value) {
      const time = new Date(value);
      return Number.isFinite(time.getTime()) ? time.toLocaleString('id-ID', {dateStyle:'short', timeStyle:'short'}) : 'waktu belum tersedia';
    }
    async history() {
      try {
        const data = await this.api('/api/operator/history?limit=40');
        const rows = Array.isArray(data.requests) ? data.requests.filter(row => String(row.action || '').startsWith('software.')) : [];
        this.historyRows = rows;
        const completedActive = this.active && rows.find(row => row.id === this.active.id && FINISHED.has(row.state));
        if (completedActive && !this.busy) {
          this.showResult(completedActive); this.active = null; this.needsReconcile = false;
        }
        const target = $('softwareHistory'); target.replaceChildren();
        if (!rows.length) target.append(element('p', 'Belum ada riwayat pekerjaan software.', 'software-help'));
        const visible = [...rows.filter(row => !FINISHED.has(row.state)),
          ...rows.filter(row => FINISHED.has(row.state)).slice(0, 12)];
        for (const record of visible) {
          const row = element('div', undefined, 'software-history-row'), details = element('div');
          const pkg = record.payload?.plan?.package_id || record.payload?.package_id || record.payload?.query || 'Inventaris';
          const version = record.payload?.plan?.version || record.payload?.version;
          details.append(element('strong', pkg + (version ? ' · ' + version : '')), element('small',
            this.formatTime(record.created_at) + ' · ' + receiptLabel(record)));
          const button = element('button', FINISHED.has(record.state) ? 'Lihat hasil' : 'Lihat / lanjutkan', 'software-secondary');
          button.type = 'button'; button.disabled = this.busy || Boolean(this.pending);
          button.addEventListener('click', () => this.openHistory(record));
          row.append(details, button); target.append(row);
        }
        if (this.needsReconcile && !this.active && !this.pending && !rows.some(row => !FINISHED.has(row.state))) {
          this.needsReconcile = false;
        }
      } catch (error) {
        $('softwareHistory').textContent = 'Riwayat belum tersedia: ' + error.message;
      }
      this.controls();
    }
    async openHistory(record) {
      if (this.busy || this.pending) return;
      this.busy = true; this.controls();
      try {
        if (FINISHED.has(record.state)) {
          this.showResult(record);
          if (this.active?.id === record.id) {this.active = null; this.needsReconcile = false;}
          return;
        }
        const fresh = await this.api('/api/operator/requests/' + record.id);
        if (fresh.state === 'pending') {
          if (fresh.action === 'software.install') {this.showApproval(fresh); return;}
          if (!READ.has(fresh.action)) throw Error('Operasi software tidak dikenali.');
          await this.api('/api/operator/requests/' + fresh.id + '/confirm', {
            method:'POST', body:JSON.stringify({confirm:true, digest:fresh.digest})});
        }
        this.cursor = 0; this.needsReconcile = false;
        await this.watch(fresh);
      } catch (error) {
        this.status('Riwayat belum dapat dilanjutkan: ' + error.message +
          (error.status === 404 ? ' Permintaan aktif hanya dapat dilanjutkan dari sesi pemilik asal.' : ''), 'unknown');
      } finally {this.busy = false; this.controls(); this.history();}
    }
  }
  window.SonicSoftware = {SoftwareManager, validPlan, installedEvidenceMatches, receiptLabel};
  const init = () => {if ($('softwareManager')) window.sonicSoftware = new SoftwareManager();};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
