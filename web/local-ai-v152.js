/* SONIC local GGUF Control Center (owner-only, no credentials in browser). */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let csrf = '';
  let active = false;
  let busy = false;
  let timer = null;
  const put = (id, value) => { if ($(id)) $(id).textContent = String(value); };
  const human = value => Number.isInteger(value) ? value.toLocaleString('id-ID') + ' MB' : 'N/A';

  async function request(url, method='GET', body) {
    const response = await fetch(url, {
      method, credentials:'same-origin',
      headers:{'Content-Type':'application/json', ...(method!=='GET' ? {'X-Sonic-CSRF':csrf}: {})},
      ...(body ? {body:JSON.stringify(body)} : {})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail==='string' ? data.detail : 'Local AI request failed');
    return data;
  }

  function lockControls(value) {
    busy = value;
    for (const id of ['localAIStart','localAIStop','localAIChoose']) {
      if ($(id)) $(id).disabled = value || !active;
    }
  }

  async function refresh() {
    try {
      const session = await request('/api/session');
      if (!session.authenticated) {
        active = false; csrf = ''; lockControls(true);
        put('localAIState','Owner login required');
        put('localAIMessage','Local model controls are unavailable in public preview.');
        return;
      }
      active = true; csrf = session.csrf;
      const s = await request('/api/local-ai/status');
      window.dispatchEvent(new Event('sonic:runtime-updated'));
      const state = s.bridge_online ? s.state : 'offline';
      put('localAIState', state.toUpperCase());
      $('localAIState')?.setAttribute('data-state', state);
      put('localAIRam', human(s.hardware?.ram_free_mb));
      put('localAIVram', human(s.hardware?.gpu_free_mb));
      put('localAIDevice', s.device_online ? 'Companion online' : 'Companion offline');
      put('localAIModel',s.model||'Local GGUF');
      if (!busy) {
        $('localAIStart').disabled = !s.enabled || !s.bridge_online || state==='running' || state==='starting';
        $('localAIStop').disabled = !s.enabled || !s.bridge_online || state==='stopped' || state==='offline';
        $('localAIChoose').disabled = !s.enabled || !s.bridge_online || state!=='running';
      }
      if (!s.enabled) put('localAIMessage','Bridge disabled on Railway. Existing chat providers remain unchanged.');
      else if (!s.bridge_online) put('localAIMessage','Companion update or local owner opt-in is required.');
    } catch (e) {
      active = false; lockControls(true);
      put('localAIMessage','Status unavailable: '+e.message);
    }
  }

  async function waitJob(job) {
    const end = Date.now()+35000;
    while (Date.now()<end) {
      await new Promise(resolve=>setTimeout(resolve,1800));
      const result = await request('/api/local-ai/jobs/'+encodeURIComponent(job.id));
      if (['done','failed','expired'].includes(result.state)) {
        put('localAIMessage',result.state==='done'
          ? 'Perintah '+job.action+' diterima Companion. Refresh status untuk kondisi aktual.'
          : 'Perintah '+job.action+' tidak selesai. Periksa status perangkat.');
        await refresh();
        return;
      }
    }
    put('localAIMessage','Perintah masih diproses oleh Companion. Status akan diperbarui.');
  }

  async function control(action) {
    if (busy || !active) return;
    if (!confirm(action==='start'
      ? 'Aktifkan AI lokal di TRADEVICEPC? Model menggunakan sekitar 5-6 GB RAM dan berbagi GPU dengan MT5. Resource guard akan memeriksa kapasitas sebelum start.'
      : 'Hentikan hanya model AI yang dikelola SONIC Companion? MetaTrader 5 tidak disentuh.')) return;
    lockControls(true);
    put('localAIMessage',action==='start'?'Meminta SONIC Companion memulai model...':'Menghentikan model yang dikelola SONIC...');
    try {
      const job = await request('/api/local-ai/control','POST',{action});
      await waitJob(job);
    } catch (e) { put('localAIMessage','Perintah ditolak: '+e.message); }
    finally { lockControls(false); await refresh(); }
  }

  async function chooseModel() {
    if (busy || !active) return;
    if (!confirm('Gunakan DeepSeek GGUF lokal sebagai model chat SONIC? Chat akan transit melalui Railway dan tidak memiliki akses tool/PC. Voice dan Vision tetap terpisah.')) return;
    lockControls(true);
    try {
      const status = await request('/api/local-ai/status');
      if (status.state!=='running') throw Error('Start local engine first');
      const result=await request('/api/models/selection','PUT',{provider:'local',model:status.model});
      if (!result.saved) throw Error('Model selection not confirmed');
      put('localAIMessage','Local GGUF dipilih sebagai SONIC chat model. Buka tab Chat.');
      $('refreshSetup')?.click();
      window.dispatchEvent(new Event('sonic:model-changed'));
    } catch (e) { put('localAIMessage','Pemilihan gagal: '+e.message); }
    finally { lockControls(false); await refresh(); }
  }

  function init() {
    if (!$('localAIControl')) return;
    $('localAIStart').addEventListener('click',()=>control('start'));
    $('localAIStop').addEventListener('click',()=>control('stop'));
    $('localAIRefresh').addEventListener('click',refresh);
    $('localAIChoose').addEventListener('click',chooseModel);
    $('localAIOpenChat').addEventListener('click',()=>{
      document.querySelector('.nav[data-tab="chat"]')?.click();
    });
    document.querySelector('.nav[data-tab="devices"]')?.addEventListener('click',refresh);
    const login=$('loginOverlay');
    if (login) new MutationObserver(refresh).observe(login,{attributes:true,attributeFilter:['class']});
    refresh();
    timer=setInterval(()=>{
      if (!document.hidden && $('loginOverlay')?.classList.contains('hidden')) refresh();
    },12000);
    window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();