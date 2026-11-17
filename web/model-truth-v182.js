/* Model selection, readiness and response origin are three distinct facts. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  let owner=false,busy=false,last=null,requestSeq=0;
  function node(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;}
  function widget(target,where='prepend'){
    if(!target)return;
    const box=node('details',null,'runtime-widget');
    const summary=node('summary');summary.append(node('span','Model: checking','runtime-title'),node('span','...','runtime-state'));
    const content=node('div',null,'runtime-content');
    content.append(node('p','Membaca status server...','runtime-message'));
    const actions=node('div',null,'runtime-actions');
    for(const [id,label] of [['start','Start local'],['settings','Pilih model'],['refresh','Refresh']]){
      const b=node('button',label);b.type='button';b.dataset.runtimeAction=id;
      b.addEventListener('click',()=>{
        if(!owner)return;
        if(id==='start'){$('localAIStart')?.click();setTimeout(refresh,1800);}
        if(id==='settings'){document.querySelector('.nav[data-tab="setup"]')?.click();$('brainModelControl')?.scrollIntoView({block:'start'});}
        if(id==='refresh')refresh();
      });actions.append(b);
    }
    content.append(actions,node('p','Lokal: inference di PC melalui relay Railway. Cloud: konteks dikirim ke provider terpilih. Pilih model tidak sama dengan menyalakan engine. Tidak ada fallback otomatis.','runtime-privacy'));
    box.append(summary,content);where==='append'?target.append(box):target.prepend(box);
  }
  function update(data){
    last=data;const chosen=data?.selected;if(!chosen)return;
    const local=chosen.provider==='local';
    const state=local?(data.local?.ready?'RUNNING':'BELUM BERJALAN'):
      (chosen.configured?'CLOUD · TERKONFIGURASI':'KEY BELUM DIISI');
    for(const host of document.querySelectorAll('.runtime-widget')){
      host.querySelector('.runtime-title').textContent=chosen.label;
      host.querySelector('.runtime-state').textContent=state;
      host.dataset.runtime=local?'local':'cloud';
      host.dataset.ready=String(local?Boolean(data.local?.ready):Boolean(chosen.configured));
      host.querySelector('.runtime-message').textContent=data.message;
      const start=host.querySelector('[data-runtime-action=start]');
      start.hidden=!local||Boolean(data.local?.ready);
      start.disabled=!owner||!data.local?.bridge_online||!data.local?.device_online;
    }
  }
  function receipt(host,data){
    if(!host||!data||host.querySelector('.answer-origin'))return;
    const el=node('div',null,'answer-origin');
    const prefix={system_status:'STATUS SONIC · Tanpa model/web',engine_unavailable:'ENGINE BELUM BERJALAN · Tanpa inference',source_listing:'DAFTAR SUMBER · Bukan jawaban model',sonic_action:'AKSI SONIC · Hasil sistem'};
    el.textContent=data.inference_performed?
      'MODEL '+(data.provider==='local'?'LOCAL · Qwen 9B Q4_K_M':String(data.provider)+' · '+String(data.model)):
      (prefix[data.kind]||'SUMBER JAWABAN BELUM TERVERIFIKASI');
    el.dataset.origin=data.kind;host.append(el);
  }
  async function refresh(){
    if(busy||document.hidden)return;
    if(!$('loginOverlay')?.classList.contains('hidden')||document.body.classList.contains('sonic-open-preview')){owner=false;return;}
    busy=true;const seq=++requestSeq;
    try{
      const r=await fetch('/api/intelligence/status',{credentials:'same-origin',cache:'no-store'});
      if(!r.ok){owner=false;return;}
      const data=await r.json();if(seq!==requestSeq)return;owner=true;update(data);
    }catch(_){document.querySelectorAll('.runtime-state').forEach(e=>e.textContent='STATUS TIDAK TERSEDIA');}
    finally{busy=false;}
  }
  function init(){
    widget($('chatPanel'));
    widget($('brainModelControl'));
    // Keep the verified runtime panel before the discovery catalog.
    const local=$('localAIControl'),hub=$('huggingFaceHub');
    if(local&&hub)hub.before(local);
    const prefs=$('agentResearchPreferences');
    if(prefs){
      const details=node('details',null,'research-options');
      details.append(node('summary','Memory & preferensi riset'));
      prefs.before(details);details.append(prefs);
    }
    window.addEventListener('sonic:tab',event=>{
      const more=$('mobileMoreNav');
      if(more)more.dataset.current=String(['workspace','setup'].includes(event.detail?.tab));
    });
    window.addEventListener('sonic:owner-ready',refresh);
    window.addEventListener('sonic:model-changed',refresh);
    window.addEventListener('sonic:runtime-updated',refresh);
    window.addEventListener('sonic:logout',()=>{owner=false;last=null;requestSeq++;document.querySelectorAll('.runtime-widget').forEach(e=>{e.open=false;e.querySelector('.runtime-title').textContent='Login owner diperlukan';e.querySelector('.runtime-state').textContent='TERKUNCI';});});
    for(const id of ['agentModeChat','agentModeResearch','hfStartPinned','hfStopPinned'])$(id)?.addEventListener('click',refresh);
    document.querySelectorAll('.nav[data-tab]').forEach(b=>b.addEventListener('click',refresh));
    refresh();
  }
  window.sonicModelTruth={update,refresh,receipt};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
