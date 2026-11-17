/* SONIC v1.7 Read-only Research Agent + owner Research Memory. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  let active=false,enabled=false,visible=false;
  let memoryOpen=false;

  function setMode(wantResearch) {
    active=Boolean(wantResearch&&enabled&&visible&&!document.body.classList.contains('sonic-open-preview'));
    $('agentModeChat')?.setAttribute('aria-pressed',String(!active));
    $('agentModeResearch')?.setAttribute('aria-pressed',String(active));
    if($('agentPurpose'))$('agentPurpose').disabled=!active;
    if($('agentResearchPreferences'))$('agentResearchPreferences').hidden=!active;
    if(!active){memoryOpen=false;if($('agentMemoryPanel'))$('agentMemoryPanel').hidden=true;}
    if($('message')){
      $('message').maxLength=active?300:3500;
      $('message').placeholder=active
        ?'Cari topik atau referensi...'
        :'Tanya SONIC...';
    }
  }

  function lock() {
    visible=Boolean($('loginOverlay')?.classList.contains('hidden')
      && !document.body.classList.contains('sonic-open-preview'));
    if($('agentResearchToolbar'))$('agentResearchToolbar').hidden=!visible;
    if(!visible){enabled=false;setMode(false);}
  }

  async function refresh(){
    lock();if(!visible)return;
    try{
      const response=await fetch('/api/agent/capabilities',{credentials:'same-origin',cache:'no-store'});
      if(!response.ok){enabled=false;setMode(false);return;}
      const data=await response.json();enabled=data.enabled===true;
      const btn=$('agentModeResearch');
      if(btn){
        btn.disabled=!enabled;
        btn.title=enabled?'Read-only web research, with citations':'Research Agent is disabled';
      }
      if($('agentCapability'))$('agentCapability').textContent=!enabled ? 'Research unavailable' : (data.runtime?.message || 'Status model belum terverifikasi');
      if(data.runtime)window.sonicModelTruth?.update(data.runtime);
      if(!enabled)setMode(false);
      if(enabled)refreshMemory();
    }catch(_){enabled=false;setMode(false);}
  }

  function text(tag,value,classname){
    const el=document.createElement(tag);if(classname)el.className=classname;
    el.textContent=String(value||'');return el;
  }

  function render(host,response){
    window.sonicModelTruth?.receipt(host,response.answer_origin);
    if(response.runtime)window.sonicModelTruth?.update(response.runtime);
    if(['system_status','model_unavailable'].includes(response.mode))return;
    const box=document.createElement('section');box.className='agent-research-results';
    box.setAttribute('aria-label','Research results and sources');
    const heading=text('div','', 'agent-results-head');
    const labels={
      local_summary:'Local AI summary',cloud_summary:'Cloud AI · source-backed',
      sources_only:'Sources collected',
      general_explanation_unverified:'AI explanation · sources unverified'
    };
    heading.append(text('strong','Research · '+(labels[response.mode]||'Results')));
    heading.append(text('span',String(response.sources?.length||0)+' sources'));
    box.append(heading);
    if(response.memory_saved){
      box.append(text('p','Tersimpan di Research Memory','agent-research-saved'));
    }
    const sources=Array.isArray(response.sources)?response.sources:[];
    if(sources.length){
      const details=document.createElement('details');details.className='agent-sources-details';
      const summary=text('summary','Lihat '+sources.length+' sumber dan kutipan');
      details.append(summary);
      const list=text('div','','agent-source-list');
      for(const source of sources.slice(0,5)){
        if(!source||typeof source.url!=='string')continue;
        let url;
        try{url=new URL(source.url);if(url.protocol!=='https:'||url.username||url.password||!url.hostname.includes('.'))continue;}catch(_){continue;}
        const item=text('div','','agent-source');
        const link=text('a','['+source.id+'] '+String(source.title||url.hostname).slice(0,180));
        link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';
        item.append(link);
        item.append(text('span',url.hostname+
          (source.date?' · '+source.date:'')+
          (source.read?' · inspected':' · snippet only'),'agent-source-meta'));
        item.append(text('p',String(source.excerpt||source.snippet||'').slice(0,500)));
        list.append(item);
      }
      details.append(list);box.append(details);
    }else{
      box.append(text('p',response.no_sources_reason==='provider_unavailable'
        ?'Search service unavailable. No references were invented.'
        :'No relevant sources found. Try a broader topic, alternative terminology or specific organization.','agent-research-notice'));
    }
    if(response.memory_matches?.length){
      const matches=document.createElement('details');matches.className='agent-related-memory';
      matches.append(text('summary','Related saved research ('+response.memory_matches.length+')'));
      for(const item of response.memory_matches.slice(0,3)){
        matches.append(text('p',String(item.project||'General')+' · '+String(item.query||'').slice(0,150)));
      }
      box.append(matches);
    }
    if(Array.isArray(response.steps)){
      const searches=response.steps.filter(s=>s.tool==='web.search'&&s.status==='ok').length;
      const pages=response.steps.filter(s=>s.tool==='web.open'&&s.status==='ok').length;
      box.append(text('p',searches+' searches · '+pages+' pages inspected'+
        (response.model_provider?' · '+response.model_provider+' synthesis':''),'agent-steps'));
    }
    if(response.notice&&sources.length)box.append(text('p',String(response.notice).slice(0,240),'agent-research-notice'));
    host.append(box);
  }

  async function refreshMemory(){
    if(!enabled||!visible)return;
    try{
      const query=$('agentMemorySearch')?.value.trim()||'';
      const response=await fetch('/api/agent/memory?limit=30&search='+encodeURIComponent(query),{
        credentials:'same-origin',cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();const results=data.results||[];
      const b=$('agentHistoryToggle');if(b)b.textContent='Saved ('+data.total+')';
      const host=$('agentMemoryItems');if(!host)return;
      host.replaceChildren();
      if(!results.length){host.append(text('p','Belum ada riset tersimpan yang cocok.','agent-memory-empty'));return;}
      for(const item of results){
        const card=text('div','','agent-memory-entry');
        card.append(text('strong',item.query));
        card.append(text('p',item.project+' · '+item.source_count+' sources · '+(item.created_at||'').slice(0,10)));
        const actions=text('div','','agent-memory-actions');
        const reuse=text('button','Use in research');
        reuse.type='button';reuse.addEventListener('click',()=>{
          if($('message')){$('message').value='Bandingkan temuan dari riset "'+item.query+'" dengan data terbaru.';$('message').focus();}
          if($('agentMemoryPanel'))$('agentMemoryPanel').hidden=true;
          memoryOpen=false;
        });
        const remove=text('button','Delete');remove.type='button';
        remove.addEventListener('click',async()=>{
          if(!confirm('Hapus riset ini dari Research Memory? Riwayat Chat tidak ikut dihapus.'))return;
          try{
            const session=await (await fetch('/api/session',{credentials:'same-origin',cache:'no-store'})).json();
            if(!session.authenticated||!session.csrf)throw Error('Owner login required');
            const response=await fetch('/api/agent/memory/'+encodeURIComponent(item.id),{
              method:'DELETE',credentials:'same-origin',headers:{'X-Sonic-CSRF':session.csrf}});
            if(!response.ok)throw Error('Delete failed ('+response.status+')');
            await refreshMemory();
          }catch(error){alert('Tidak bisa menghapus: '+error.message);}
        });
        actions.append(reuse,remove);card.append(actions);host.append(card);
      }
    }catch(_){ /* An inaccessible memory list cannot reveal private entries. */ }
  }

  function init(){
    if(!$('agentResearchToolbar'))return;
    $('agentModeChat')?.addEventListener('click',()=>setMode(false));
    $('agentModeResearch')?.addEventListener('click',()=>setMode(true));
    $('agentHistoryToggle')?.addEventListener('click',()=>{
      memoryOpen=!memoryOpen;
      if($('agentMemoryPanel'))$('agentMemoryPanel').hidden=!memoryOpen;
      $('agentHistoryToggle')?.setAttribute('aria-expanded',String(memoryOpen));
      if(memoryOpen)refreshMemory();
    });
    $('agentRefreshMemory')?.addEventListener('click',refreshMemory);
    $('agentMemorySearch')?.addEventListener('input',()=>refreshMemory());
    window.addEventListener('sonic:owner-ready',refresh);
    window.addEventListener('sonic:model-changed',refresh);
    window.addEventListener('sonic:logout',()=>{enabled=false;memoryOpen=false;setMode(false);lock();});
    refresh();
  }
  window.sonicResearch={
    active:()=>active&&enabled&&visible,
    purpose:()=>['targets','data','references'].includes($('agentPurpose')?.value)?$('agentPurpose').value:'references',
    options:()=>({save_to_memory:Boolean($('agentSaveMemory')?.checked),
                 project:($('agentProject')?.value||'General').trim().slice(0,80)||'General'}),
    render,refresh,refreshMemory,reset:()=>{enabled=false;setMode(false);lock();}
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();