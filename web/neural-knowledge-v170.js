/* SONIC v1.7 Knowledge List: compact mobile view, 3D remains opt-in. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  let mode='list',nodes=[],saved=[],query='';
  const mobile=()=>matchMedia('(max-width:720px)').matches;
  function render() {
    const host=$('neuralKnowledgeItems');if(!host)return;
    host.replaceChildren();
    const allowed=['memory','topic','integration'];
    let items=nodes.filter(item=>allowed.includes(item.category));
    const order={memory:0,topic:1,integration:2};
    items.sort((a,b)=>(order[a.category]??9)-(order[b.category]??9));
    if(query)items=items.filter(n=>(String(n.label||'')+' '+String(n.detail||'')).toLowerCase().includes(query));
    const researched=saved.filter(item=>!query||(String(item.query||'')+' '+String(item.summary||'')).toLowerCase().includes(query));
    for(const item of researched.slice(0,20)) {
      const card=document.createElement('article');card.className='neural-knowledge-card';
      card.setAttribute('role','listitem');
      const cat=document.createElement('span');cat.textContent='RESEARCH · '+String(item.project||'General').slice(0,45);
      const title=document.createElement('strong');title.textContent=String(item.query||'Untitled research').slice(0,130);
      const subtitle=document.createElement('p');subtitle.textContent=String(item.summary||'').slice(0,260);
      const meta=document.createElement('p');meta.textContent=String(item.source_count||0)+' source(s) · '+String(item.created_at||'').slice(0,10);
      const button=document.createElement('button');button.type='button';button.textContent='Continue research';
      button.addEventListener('click',()=>{
        document.querySelector('.sidebar .nav[data-tab="chat"]')?.click();
        document.querySelector('#agentModeResearch')?.click();
        const input=document.querySelector('#message');
        if(input){input.value='Lanjutkan riset "'+String(item.query||'').slice(0,130)+'" dan periksa data terbaru.';input.focus();}
      });
      card.append(cat,title,subtitle,meta,button);host.append(card);
    }
    if(!items.length&&!researched.length) {
      const p=document.createElement('p');p.textContent=nodes.length
        ?'Tidak ditemukan catatan yang cocok. Ubah kata kunci untuk mencari kembali.'
        :'Belum ada catatan. Simpan riset dari Chat agar SONIC bisa membangun knowledge.';
      host.append(p);return;
    }
    for(const item of items.slice(0,50)) {
      const card=document.createElement('article');card.className='neural-knowledge-card';card.setAttribute('role','listitem');
      const cat=document.createElement('span');cat.textContent=String(item.category||'Knowledge').toUpperCase();
      const heading=document.createElement('strong');heading.textContent=String(item.label||'Untitled').slice(0,130);
      const summary=document.createElement('p');summary.textContent=String(item.detail||'').slice(0,260);
      const button=document.createElement('button');button.type='button';button.textContent='Explore node';
      button.addEventListener('click',()=>{
        setMode('graph');
        window.dispatchEvent(new CustomEvent('sonic:select-node',{detail:{id:item.id}}));
      });
      card.append(cat,heading,summary,button);host.append(card);
    }
  }
  async function loadResearch(){
    if(document.body.classList.contains('sonic-open-preview')){saved=[];render();return;}
    try{
      const response=await fetch('/api/agent/memory?limit=35',{credentials:'same-origin',cache:'no-store'});
      if(!response.ok){saved=[];render();return;}
      const value=await response.json();
      saved=Array.isArray(value.results)?value.results:[];
    }catch(_){saved=[];}
    render();
  }
  function setMode(next) {
    mode=next==='graph'?'graph':'list';
    const list=$('neuralKnowledgeList');
    if(list)list.hidden=!mobile()||mode!=='list';
    document.body.classList.toggle('neural-knowledge-mode',mobile()&&mode==='list');
    $('neuralKnowledgeBtn')?.setAttribute('aria-pressed',String(mode==='list'));
    $('neuralGraphBtn')?.setAttribute('aria-pressed',String(mode==='graph'));
    window.dispatchEvent(new CustomEvent('sonic:neural-mode',{detail:{mode}}));
    if(mode==='list')render();
  }
  function adapt(){
    const controls=$('neuralMobileSwitcher');
    if(controls)controls.hidden=!mobile();
    if(!mobile())document.body.classList.remove('neural-knowledge-mode');
    else setMode(mode);
  }
  function init(){
    $('neuralKnowledgeBtn')?.addEventListener('click',()=>setMode('list'));
    $('neuralGraphBtn')?.addEventListener('click',()=>setMode('graph'));
    $('neuralKnowledgeSearch')?.addEventListener('input',event=>{query=event.target.value.trim().toLowerCase();render();});
    window.addEventListener('sonic:graph-loaded',event=>{nodes=Array.isArray(event.detail?.nodes)?event.detail.nodes:[];render();});
    window.addEventListener('sonic:logout',()=>{nodes=[];saved=[];render();});
    window.addEventListener('sonic:owner-ready',loadResearch);
    window.addEventListener('resize',adapt);
    window.addEventListener('sonic:tab',event=>{
      if(event.detail?.tab==='brain'){adapt();loadResearch();}
    });
    adapt();
  }
  window.sonicNeural={isGraphMode:()=>!mobile()||mode==='graph',setMode};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();