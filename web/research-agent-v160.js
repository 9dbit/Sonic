/* SONIC v1.6.0: owner-only, read-only Web Research Agent UI. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let active = false;
  let enabled = false;
  let visible = true;

  function setMode(research) {
    active = Boolean(research && enabled && visible && !document.body.classList.contains('sonic-open-preview'));
    const chat = $('agentModeChat');
    const researchButton = $('agentModeResearch');
    if (chat) chat.setAttribute('aria-pressed', String(!active));
    if (researchButton) researchButton.setAttribute('aria-pressed', String(active));
    if ($('agentPurpose')) $('agentPurpose').disabled = !active;
    if ($('message')) {
      $('message').maxLength = active ? 300 : 3500;
      $('message').placeholder = active
        ? 'Cari target, data, perusahaan, produk atau referensi publik...'
        : 'Ask SONIC anything...';
    }
    if ($('agentPrivacy')) {
      $('agentPrivacy').textContent = active
        ? 'READ-ONLY AGENT · Pencarian dikirim ke Bing, URL halaman ke Jina Reader. SONIC tidak login ke website atau menjalankan perintah PC. AI lokal merangkum bila aktif.'
        : 'Mode Chat biasa. Pilih Research Agent untuk mencari sumber publik dengan referensi.';
    }
  }

  function lock() {
    const loggedIn = $('loginOverlay')?.classList.contains('hidden');
    visible = Boolean(loggedIn && !document.body.classList.contains('sonic-open-preview'));
    if ($('agentResearchToolbar')) $('agentResearchToolbar').hidden = !visible;
    if (!visible) {
      enabled = false;
      setMode(false);
    }
  }

  async function refresh() {
    lock();
    if (!visible) return;
    try {
      const response = await fetch('/api/agent/capabilities', {
        method: 'GET', credentials: 'same-origin', cache: 'no-store'
      });
      if (!response.ok) {
        enabled = false;
        if (response.status === 401) lock();
        return;
      }
      const data = await response.json();
      enabled = data.enabled === true;
      if ($('agentModeResearch')) {
        $('agentModeResearch').disabled = !enabled;
        $('agentModeResearch').title = enabled
          ? 'Cari sumber publik menggunakan read-only Research Agent'
          : 'Research Agent belum diaktifkan di staging';
      }
      if ($('agentCapability')) {
        $('agentCapability').textContent = enabled
          ? (data.local_ai_running ? 'Local AI ready' : 'Research ready · AI local stopped')
          : 'Research Agent disabled';
      }
      if (!enabled) setMode(false);
    } catch (_) {
      enabled = false;
      setMode(false);
    }
  }

  function render(host, response) {
    const details = document.createElement('section');
    details.className = 'agent-research-results';
    details.setAttribute('aria-label', 'Research Agent evidence and steps');
    const heading = document.createElement('div');
    heading.className = 'agent-results-head';
    const label = document.createElement('strong');
    label.textContent = 'Research Agent · ' + (response.local_ai_used ? 'AI summary' : 'Sources only');
    heading.append(label);
    const count = document.createElement('span');
    count.textContent = String(response.sources?.length || 0) + ' sources';
    heading.append(count);
    details.append(heading);
    const list = document.createElement('div');
    list.className = 'agent-source-list';
    for (const source of (response.sources || []).slice(0, 5)) {
      if (!source || typeof source.url !== 'string') continue;
      let url;
      try {
        url = new URL(source.url);
        if (url.protocol !== 'https:' || url.username || url.password || !url.hostname.includes('.')) continue;
      } catch (_) { continue; }
      const item = document.createElement('div');
      item.className = 'agent-source';
      const a = document.createElement('a');
      a.href = url.href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = '[' + source.id + '] ' + String(source.title || url.hostname).slice(0, 180);
      item.append(a);
      const meta = document.createElement('span');
      meta.className = 'agent-source-meta';
      meta.textContent = url.hostname + (source.date ? ' · ' + source.date : '') +
        (source.read ? ' · page inspected' : ' · search snippet');
      item.append(meta);
      const excerpt = document.createElement('p');
      excerpt.textContent = String(source.excerpt || source.snippet || '').slice(0, 520);
      item.append(excerpt);
      list.append(item);
    }
    details.append(list);
    if (Array.isArray(response.steps)) {
      const tally = document.createElement('p');
      tally.className = 'agent-steps';
      const countSearch = response.steps.filter(step => step.tool === 'web.search' && step.status === 'ok').length;
      const countRead = response.steps.filter(step => step.tool === 'web.open' && step.status === 'ok').length;
      tally.textContent = 'Tools: ' + countSearch + ' searches · ' + countRead +
        ' pages read · ' + (response.local_ai_used ? 'local synthesis complete' : 'local synthesis unavailable');
      details.append(tally);
    }
    if (response.notice) {
      const note = document.createElement('p');
      note.className = 'agent-research-notice';
      note.textContent = String(response.notice).slice(0, 300);
      details.append(note);
    }
    host.append(details);
  }

  function init() {
    if (!$('agentResearchToolbar')) return;
    $('agentModeChat')?.addEventListener('click', () => setMode(false));
    $('agentModeResearch')?.addEventListener('click', () => setMode(true));
    window.addEventListener('sonic:owner-ready', refresh);
    window.addEventListener('sonic:logout', () => {
      enabled = false;
      setMode(false);
      lock();
    });
    refresh();
  }

  window.sonicResearch = {
    active: () => active && enabled && visible,
    purpose: () => ['targets', 'data', 'references'].includes($('agentPurpose')?.value)
      ? $('agentPurpose').value : 'references',
    render,
    refresh,
    reset: () => { enabled = false; setMode(false); lock(); }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();