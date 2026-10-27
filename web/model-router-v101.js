/* SONIC V1.0 Model Router UI.
 * Isolated from the Neural, Motion, Voice and PC command controllers.
 * Never stores API keys, session secrets, chat history or model selections
 * in browser storage. All mutations go through existing owner cookie+CSRF.
 */
(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const text = (tag, value, klass='') => {
    const node = document.createElement(tag);
    if(klass) node.className=klass;
    node.textContent=String(value);
    return node;
  };
  let generation=0;
  let working=false;
  let lastModels=[];

  const status = message => {
    if($('brainModelStatus')) $('brainModelStatus').textContent=message;
  };

  function reset(){
    generation++;
    working=false;
    lastModels=[];
    $('brainModelSelect')?.replaceChildren();
    $('brainModelMetrics')?.replaceChildren();
    if($('applyBrainModel')) $('applyBrainModel').disabled=true;
    status('Login owner diperlukan untuk mengatur model SONIC.');
  }

  async function request(path, options={}){
    const response=await fetch(path,{
      method:options.method||'GET',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json',...(options.csrf?{'X-Sonic-CSRF':options.csrf}:{})},
      ...(options.body?{body:JSON.stringify(options.body)}:{})
    });
    const value=await response.json().catch(()=>({}));
    if(response.status===401){reset();throw Error('Session owner berakhir. Login kembali.');}
    if(!response.ok)throw Error(
      typeof value.detail==='string'?value.detail:'SONIC model request failed (HTTP '+response.status+')');
    return value;
  }

  function updateButton(){
    const option=lastModels.find(item=>item.provider+'|'+item.model===$('brainModelSelect').value);
    $('applyBrainModel').disabled=working||!option||!option.key_configured||!!option.selected;
  }

  function renderUsage(events){
    const host=$('brainModelMetrics');
    host.replaceChildren();
    if(!Array.isArray(events)||!events.length){
      host.append(text('p','Belum ada panggilan model yang dicatat. Tes koneksi dan chat dapat dikenakan biaya API.','small-note'));
      return;
    }
    const list=text('div','','model-usage-rows');
    for(const event of events.slice(0,8)){
      const row=text('div','','model-usage-row');
      const info=text('div','');
      const model=(event.provider||'unknown')+' / '+(event.model||'unknown');
      info.append(text('strong',model));
      const tokens=(event.input_tokens??'—')+' input · '+(event.output_tokens??'—')+' output tokens';
      const ms=Number.isFinite(event.latency_ms)?event.latency_ms+' ms':'Latency unavailable';
      const price=typeof event.provider_reported_cost_usd==='number'
        ?' · $'+event.provider_reported_cost_usd.toFixed(5)+' reported cost'
        :' · cost unavailable';
      info.append(text('small',ms+' · '+tokens+price));
      row.append(info,text('span',event.status||'unknown',
        'model-usage-status'+(event.status==='ok'?'':' error')));
      list.append(row);
    }
    host.append(list);
  }

  function render(data){
    lastModels=Array.isArray(data.models)?data.models:[];
    const select=$('brainModelSelect');
    select.replaceChildren();
    for(const item of lastModels){
      const option=document.createElement('option');
      option.value=item.provider+'|'+item.model;
      option.textContent=item.label+(item.key_configured?'':' · API key missing');
      option.disabled=!item.key_configured;
      option.selected=!!item.selected;
      select.append(option);
    }
    const selected=data.selected||{};
    status('Active chat: '+selected.provider+' / '+selected.model+
           '. Realtime Voice dan Vision tetap menggunakan OpenAI.');
    updateButton();
    renderUsage(data.usage||[]);
  }

  async function refresh(){
    const requestId=++generation;
    if(!$('brainModelSelect'))return;
    try{
      const session=await request('/api/session');
      if(!session.authenticated){reset();return;}
      const data=await request('/api/models');
      if(requestId!==generation)return;
      render(data);
    }catch(error){
      if(requestId!==generation)return;
      status('Model Router tidak tersedia: '+error.message);
    }
  }

  async function activate(){
    if(working)return;
    const [provider,model]=String($('brainModelSelect').value).split('|',2);
    const item=lastModels.find(x=>x.provider===provider&&x.model===model);
    if(!item||!item.key_configured||item.selected)return;
    if(!confirm('Aktifkan '+item.label+' untuk chat SONIC?\n\n'+
      (provider==='openrouter'
        ?'Konteks percakapan, catatan Memory Vault yang dipakai, dan hasil tool dapat dikirim ke OpenRouter serta penyedia model.'
        :'Chat akan dikirim ke OpenAI.')+
      '\n\nOpenAI Realtime Voice dan Vision tidak berubah. Tidak ada fallback otomatis.'))return;
    working=true;updateButton();
    try{
      const session=await request('/api/session');
      if(!session.authenticated)throw Error('Login owner diperlukan');
      const result=await request('/api/models/selection',{
        method:'PUT',csrf:session.csrf,body:{provider,model}
      });
      if(!result.saved)throw Error('Perubahan model tidak terkonfirmasi.');
      // Refresh the original SONIC Setup readiness and model badges.
      $('refreshSetup')?.click();
      await refresh();
      status('Model chat aktif: '+provider+' / '+model+'. Voice tetap OpenAI Realtime.');
    }catch(error){
      status('Perubahan dibatalkan: '+error.message);
    }finally{
      working=false;updateButton();
    }
  }

  function init(){
    if(!$('brainModelControl'))return;
    $('applyBrainModel').addEventListener('click',activate);
    $('brainModelSelect').addEventListener('change',updateButton);
    document.querySelector('.nav[data-tab="setup"]')?.addEventListener('click',refresh);
    $('refreshSetup')?.addEventListener('click',refresh);
    const login=$('loginOverlay');
    if(login){
      const observer=new MutationObserver(()=>{
        if(login.classList.contains('hidden')) refresh();
        else reset();
      });
      observer.observe(login,{attributes:true,attributeFilter:['class']});
    }
    // Native test button remains the only way to spend provider tokens on a
    // connectivity check. Only update the recent-usage display after it ends.
    const feedback=$('setupMessage');
    if(feedback){
      new MutationObserver(()=>{
        const value=feedback.textContent||'';
        if(/verified|passed|gagal|unavailable|failed|check response/i.test(value)
           && $('loginOverlay')?.classList.contains('hidden')) refresh();
      }).observe(feedback,{characterData:true,childList:true,subtree:true});
    }
    if(login?.classList.contains('hidden'))refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
