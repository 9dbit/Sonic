/* SONIC Hugging Face Hub v1.8.0. Metadata-only catalog, pinned local engine. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const PIN='mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF';
  const STORE={loaded:false,authenticated:false,selected:PIN,model:null,local:null,results:[],busy:false};
  const put=(id,content)=>{const node=$(id);if(node)node.textContent=String(content??'');};
  function safeURL(modelId){
    if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,94}\/[-A-Za-z0-9_.]{1,95}$/.test(modelId)) return null;
    return 'https://huggingface.co/'+modelId;
  }
  function el(tag,label,cls){
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(label!==undefined&&label!==null)node.textContent=String(label);
    return node;
  }
  function compact(number){
    const n=Number(number)||0;
    return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(n);
  }
  function size(bytes){
    if(typeof bytes!=='number'||!Number.isFinite(bytes)||bytes<0)return 'Size unknown';
    return bytes>=1e9?(bytes/1e9).toFixed(2)+' GB':(bytes/1e6).toFixed(0)+' MB';
  }
  function errText(err){return String(err?.message||'Request failed').slice(0,180);}
  async function readJson(path) {
    const res=await fetch(path,{credentials:'same-origin',cache:'no-store',
      headers:{'Accept':'application/json'}});
    const data=await res.json().catch(()=>({}));
    if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:'Request HTTP '+res.status);
    return data;
  }
  function enablePinned(state){
    const installed=STORE.selected===PIN;
    const ready=Boolean(STORE.authenticated && STORE.local?.enabled && STORE.local?.bridge_online);
    $('hfStartPinned').disabled=!(ready&&installed&&state!=='running'&&state!=='starting');
    $('hfStopPinned').disabled=!(ready&&installed&&state==='running');
    $('hfUseChatPinned').disabled=!(ready&&installed&&state==='running');
  }
  async function status(){
    if(!STORE.authenticated)return;
    try{
      const local=await readJson('/api/huggingface/local');
      STORE.local=local;
      const state=local.bridge_online?local.state:'offline';
      put('hfDevice',local.device_online?'TRADEVICEPC · ONLINE':'TRADEVICEPC · OFFLINE');
      put('hfLocalState',state.toUpperCase());
      put('hfFreeVram',Number.isInteger(local.hardware?.gpu_free_mb)?
        local.hardware.gpu_free_mb.toLocaleString('id-ID')+' MB':'N/A');
      enablePinned(state);
      if(!local.enabled)put('hfActionStatus','Local bridge belum aktif di server. Model dapat ditelusuri, tetapi tidak bisa dijalankan.');
      else if(!local.bridge_online)put('hfActionStatus','Companion belum siap. Model tidak dapat dijalankan dari browser.');
    }catch(error){put('hfLocalState','OFFLINE');put('hfActionStatus','Status lokal: '+errText(error));enablePinned('offline');}
  }
  function renderResults(){
    const host=$('hfResults');if(!host)return;
    host.replaceChildren();
    if(!STORE.results.length){host.append(el('p','Tidak ada model yang cocok. Coba kata kunci lain.'));return;}
    for(const model of STORE.results){
      const card=el('button',null,'hf-result');card.type='button';
      card.setAttribute('aria-pressed',String(model.id===STORE.selected));
      const main=el('span',null,'hf-result-inner');
      main.append(el('strong',model.title));
      main.append(el('span',model.author+' · '+compact(model.downloads)+' downloads'+
        (model.gated?' · Gated':'')+(model.installed_in_sonic?' · Pinned':'') ));
      card.append(main,el('span','›','hf-result-arrow'));
      card.addEventListener('click',()=>details(model.id));
      host.append(card);
    }
  }
  function renderFiles(model){
    const host=$('hfFiles');if(!host)return;
    host.replaceChildren();
    const files=Array.isArray(model.files)?model.files:[];
    put('hfFileCount',files.length+' GGUF');
    if(!files.length){host.append(el('p','Tidak ada file GGUF yang ditampilkan oleh API. Periksa repository untuk detail lengkap.'));return;}
    for(const file of files){
      const item=el('div',null,'hf-file');item.setAttribute('role','listitem');
      const pinned=model.id===PIN && String(file.filename).endsWith('.Q4_K_M.gguf');
      item.dataset.pinned=String(pinned);
      item.append(el('strong',file.filename),el('span',size(file.bytes)+(pinned?' · LOCAL':'')));
      host.append(item);
    }
  }
  async function details(modelId){
    if(!safeURL(modelId))return;
    STORE.selected=modelId;
    renderResults();
    put('hfSelectedTitle','Loading model...');
    put('hfSelectedAuthor',modelId.split('/')[0]);
    put('hfInspectionBadge','Inspecting');
    put('hfFileCount','...');
    const repo=$('hfOpenRepository');
    repo.href=safeURL(modelId);
    try{
      const parts=modelId.split('/');
      const data=await readJson('/api/huggingface/model/'+encodeURIComponent(parts[0])+'/'+encodeURIComponent(parts[1]));
      if(STORE.selected!==modelId)return;
      STORE.model=data;
      put('hfSelectedTitle',data.title);
      put('hfSelectedAuthor',data.author);
      put('hfInspectionBadge',data.installed_in_sonic?'Pinned local':'Catalog only');
      put('hfDownloads','Downloads: '+compact(data.downloads));
      put('hfLikes','Likes: '+compact(data.likes));
      put('hfLicense','License: '+String(data.license||'Not specified'));
      renderFiles(data);
      put('hfRuntimeNotice',data.installed_in_sonic?
        'Ini model SONIC yang sudah tersedia di TRADEVICEPC. Tombol Start/Stop meneruskan kontrol yang sama ke Windows Companion setelah persetujuan owner. Hanya Q4_K_M terverifikasi yang bisa digunakan.':
        'Repositori ini hanya untuk eksplorasi. SONIC belum mendukung unduhan, instalasi, atau menjalankan model sembarang dari browser. Buka sumber resminya untuk meninjau.');
      enablePinned(STORE.local?.bridge_online?STORE.local.state:'offline');
    }catch(error){
      put('hfSelectedTitle','Model unavailable');
      put('hfRuntimeNotice','Gagal memeriksa model: '+errText(error));
      renderFiles({files:[]});
      enablePinned('offline');
    }
  }
  async function search(){
    const input=$('hfSearchInput');
    const query=input?.value.trim()||'';
    if(query.length<2)return;
    if(STORE.busy)return;
    STORE.busy=true;
    if($('hfSearchButton'))$('hfSearchButton').disabled=true;
    put('hfSearchStatus','Mencari model di Hugging Face...');
    try{
      const data=await readJson('/api/huggingface/search?q='+encodeURIComponent(query)+'&limit=12');
      STORE.results=Array.isArray(data.results)?data.results:[];
      put('hfSearchStatus','Model publik · metadata saja');
      put('hfSearchCount',STORE.results.length+' results');
      renderResults();
    }catch(error){
      STORE.results=[];
      put('hfSearchStatus','Pencarian gagal: '+errText(error));
      put('hfSearchCount','');
      $('hfResults')?.replaceChildren();
    }finally{
      STORE.busy=false;
      if($('hfSearchButton'))$('hfSearchButton').disabled=false;
    }
  }
  function ownerLogin(){
    STORE.authenticated=false;
    const login=$('loginOverlay');
    return Boolean(login && login.classList.contains('hidden')
      && !document.body.classList.contains('sonic-open-preview'));
  }
  async function initialize(){
    if(STORE.loaded)return;
    if(!ownerLogin()){
      put('hfConnection','OWNER ONLY');
      put('hfSearchStatus','Masuk ke SONIC Owner untuk membuka katalog model.');
      return;
    }
    try{
      const session=await readJson('/api/session');
      if(!session.authenticated)throw Error('Owner login required');
      STORE.authenticated=true;STORE.loaded=true;
      put('hfConnection','CONNECTED');
      $('hfConnection').dataset.state='connected';
      await Promise.all([search(),status(),details(PIN)]);
    }catch(error){STORE.loaded=false;put('hfConnection','LOGIN REQUIRED');put('hfSearchStatus',errText(error));}
  }
  function action(nodeId,existingId){
    const button=$(nodeId);
    button?.addEventListener('click',()=>{
      if(!STORE.authenticated||STORE.selected!==PIN)return;
      const existing=$(existingId);
      if(existing?.disabled){put('hfActionStatus','Control ini belum siap. Periksa status Companion.');return;}
      if(existing)existing.click();
      else put('hfActionStatus','Local Control Center tidak tersedia.');
    });
  }
  function init(){
    if(!$('huggingFaceHub'))return;
    $('hfJump')?.addEventListener('click',()=>$('huggingFaceHub')?.scrollIntoView({behavior:'smooth',block:'start'}));
    $('hfSearchForm')?.addEventListener('submit',event=>{event.preventDefault();search();});
    document.querySelectorAll('[data-hf-preset]').forEach(button=>button.addEventListener('click',()=>{
      $('hfSearchInput').value=button.dataset.hfPreset;search();
    }));
    $('hfRefreshDetails')?.addEventListener('click',()=>{details(STORE.selected);status();});
    action('hfStartPinned','localAIStart');
    action('hfStopPinned','localAIStop');
    action('hfUseChatPinned','localAIChoose');
    $('hfGoChat')?.addEventListener('click',()=>document.querySelector('.nav[data-tab="chat"]')?.click());
    document.querySelector('.nav[data-tab="devices"]')?.addEventListener('click',()=>{initialize();if(STORE.loaded)status();});
    const login=$('loginOverlay');
    if(login)new MutationObserver(()=>{
      if(ownerLogin())initialize();
      else{STORE.authenticated=false;STORE.loaded=false;STORE.local=null;enablePinned('offline');put('hfConnection','OWNER ONLY');$('hfConnection').dataset.state='locked';$('hfResults')?.replaceChildren();}
    }).observe(login,{attributes:true,attributeFilter:['class']});
    window.addEventListener('sonic:logout',()=>{
      STORE.authenticated=false;STORE.loaded=false;STORE.local=null;enablePinned('offline');$('hfResults')?.replaceChildren();
    });
    initialize();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();