/* Native WebAuthn. No credentials in localStorage, cookies readable by JS, or URLs sent to server. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const supported = !!(window.isSecureContext && window.PublicKeyCredential && navigator.credentials);
  let busy = false;
  let enrollmentKey = new URLSearchParams(location.hash.slice(1)).get('setup') || '';
  if (enrollmentKey) history.replaceState(null, '', location.pathname + location.search);
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(enrollmentKey)) enrollmentKey = '';

  const decode = value => {
    const b64 = value.replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')), x => x.charCodeAt(0));
  };
  const encode = value => {
    const bytes = new Uint8Array(value), parts = [];
    for (let i = 0; i < bytes.length; i += 8192)
      parts.push(String.fromCharCode(...bytes.slice(i, i + 8192)));
    return btoa(parts.join('')).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  };
  function options(source, registration) {
    const value = {...source, challenge: decode(source.challenge)};
    if (registration) {
      value.user = {...source.user, id: decode(source.user.id)};
      value.excludeCredentials = (source.excludeCredentials || []).map(x => ({...x, id: decode(x.id)}));
    } else {
      value.allowCredentials = (source.allowCredentials || []).map(x => ({...x, id: decode(x.id)}));
    }
    return value;
  }
  function serialize(credential) {
    if (typeof credential.toJSON === 'function') return credential.toJSON();
    const r = credential.response;
    const value = {id: credential.id, rawId: encode(credential.rawId), type: credential.type,
      clientExtensionResults: credential.getClientExtensionResults?.() || {}};
    if (credential.authenticatorAttachment) value.authenticatorAttachment = credential.authenticatorAttachment;
    value.response = r.attestationObject ? {
      clientDataJSON: encode(r.clientDataJSON), attestationObject: encode(r.attestationObject),
      transports: r.getTransports?.() || []
    } : {
      clientDataJSON: encode(r.clientDataJSON), authenticatorData: encode(r.authenticatorData),
      signature: encode(r.signature), userHandle: r.userHandle ? encode(r.userHandle) : null
    };
    return value;
  }
  async function api(path, method = 'GET', body, csrf) {
    const response = await fetch(path, {method, credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(csrf ? {'X-Sonic-CSRF': csrf} : {})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'HTTP ' + response.status);
    return data;
  }
  function message(value) {
    if ($('passkeyMessage')) $('passkeyMessage').textContent = value;
    if (!$('loginOverlay')?.classList.contains('hidden')) $('loginError').textContent = value;
  }
  function lock(value) {
    busy = value;
    for (const id of ['passkeyLogin', 'passkeySetup', 'passkeyRegister']) if ($(id)) $(id).disabled = value || !supported;
  }
  async function owner() {
    const state = await api('/api/session');
    if (!state.authenticated || !state.csrf) throw Error('Masuk dengan passkey terlebih dahulu.');
    return state;
  }
  async function signIn() {
    if (busy || !supported) return;
    lock(true); message('Konfirmasi passkey di perangkat Anda.');
    try {
      const start = await api('/api/passkeys/login/options', 'POST', {});
      const credential = await navigator.credentials.get({publicKey: options(start.options, false)});
      if (!credential) throw Error('Verifikasi dibatalkan.');
      const result = await api('/api/passkeys/login/verify', 'POST', {
        ceremony_id: start.ceremony_id, credential: serialize(credential)});
      if (!result.authenticated) throw Error('Akses belum terverifikasi.');
      location.reload();
    } catch (error) {
      message(error.name === 'NotAllowedError' ? 'Verifikasi dibatalkan atau waktunya habis. Tekan masuk untuk mencoba lagi.' : error.message);
    } finally {lock(false);}
  }
  async function register(initial = false) {
    if (busy || !supported) return;
    lock(true); message('Simpan passkey menggunakan verifikasi perangkat Anda.');
    try {
      if (initial && !enrollmentKey) throw Error('Buka tautan pendaftaran sekali pakai terlebih dahulu.');
      const csrf = initial ? undefined : (await owner()).csrf;
      const authority = initial ? {enrollment_key: enrollmentKey} : {};
      const start = await api('/api/passkeys/register/options', 'POST', authority, csrf);
      const credential = await navigator.credentials.create({publicKey: options(start.options, true)});
      if (!credential) throw Error('Pendaftaran dibatalkan.');
      const result = await api('/api/passkeys/register/verify', 'POST', {
        ...authority, ceremony_id: start.ceremony_id, credential: serialize(credential)}, csrf);
      if (!result.registered) throw Error('Passkey belum tersimpan.');
      if (initial) {enrollmentKey = ''; location.reload();}
      else {message('Passkey ditambahkan. Login berikutnya tanpa mengetik token.'); await loadKeys();}
    } catch (error) {
      message(error.name === 'NotAllowedError' ? 'Pendaftaran dibatalkan atau waktunya habis. Tekan aktivasi untuk mencoba lagi.' : error.message);
    } finally {lock(false);}
  }
  async function loadKeys() {
    const host = $('passkeyList');
    if (!host) return;
    try {
      const session = await owner();
      const result = await api('/api/passkeys/manage');
      host.replaceChildren();
      for (const [i, item] of result.passkeys.entries()) {
        const row = document.createElement('div'); row.className = 'passkey-row';
        const label = document.createElement('span');
        label.textContent = 'Passkey ' + (i + 1) + ' / ' + new Date(item.created_at).toLocaleDateString('id-ID');
        const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Hapus';
        remove.disabled = result.passkeys.length <= 1;
        remove.title = remove.disabled ? 'Tambahkan passkey lain sebelum menghapus yang terakhir.' : 'Cabut passkey dan keluar dari semua sesi.';
        remove.addEventListener('click', async () => {
          if (busy || !confirm('Hapus passkey ini dan keluarkan semua sesi SONIC? Login kembali dengan passkey yang tersisa.')) return;
          lock(true); remove.disabled = true;
          try {
            await api('/api/passkeys/' + encodeURIComponent(item.id), 'DELETE', undefined, session.csrf);
            location.reload();
          } catch (error) {message(error.message); remove.disabled = false;}
          finally {lock(false);}
        });
        row.append(label, remove); host.append(row);
      }
    } catch (_) {host.replaceChildren();}
  }
  async function refresh() {
    try {
      const status = await api('/api/passkeys/status');
      $('passkeyLogin').hidden = !status.enrolled;
      $('passkeyLogin').disabled = !supported || !status.enrolled;
      $('passkeySetup').hidden = !enrollmentKey || status.enrolled;
      $('passkeySetup').disabled = !supported;
      $('passkeyLoginState').textContent = !supported ?
        'Gunakan browser terbaru melalui HTTPS yang mendukung passkey.' : status.enrolled ?
        'Akses privat. Konfirmasi dengan perangkat Anda untuk masuk.' : enrollmentKey ?
        'Tautan pendaftaran siap. Aktifkan passkey untuk membuka SONIC.' :
        'Belum ada passkey. Buka tautan pendaftaran sekali pakai dari administrator SONIC.';
    } catch (_) {$('passkeyLoginState').textContent = 'Status akses belum tersedia. Muat ulang halaman.';}
    await loadKeys();
  }
  $('passkeyLogin')?.addEventListener('click', signIn);
  $('passkeySetup')?.addEventListener('click', () => register(true));
  $('passkeyRegister')?.addEventListener('click', () => register(false));
  document.querySelector('.nav[data-tab="setup"]')?.addEventListener('click', loadKeys);
  refresh();
})();
