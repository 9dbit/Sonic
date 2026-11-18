/* SONIC v2.2 UI Engine: mobile-first, real-data surfaces, preserved owner workflows.
 * No generated media, fake metrics, new host permissions or network requests.
 */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const button=(text,handler,cls)=>{const b=node('button',cls,text);b.type='button';b.addEventListener('click',handler);return b;};
const mobile=()=>window.matchMedia('(max-width:720px)').matches;
let activeTab='dashboard',lastPulse=0,pulseTimer=0,viewAll=false,setupDone=false;
const docks={};
function makeDock(id){
 const d=node('div','v22-orb-dock');d.id=id;
 d.setAttribute('aria-label','SONIC animated presence');
 // Renderable even if GPU/Canvas motion is unavailable: same SONIC brand
 // asset plus a lightweight CSS orbit. The live MotionCore can overlay it.
 const fallback=node('span','v22-orb-fallback');
 fallback.setAttribute('aria-hidden','true');
 const img=node('img');img.alt='';img.src='/assets/sonic-mark.svg?v=1.5.1';
 fallback.append(img);d.append(fallback);
 return d;
}
function placeOrb(tab){
 const anchor=$('sonicMotionAnchor');
 if(!anchor||document.body.classList.contains('sonic-focused'))return;
 const dock=(tab==='studio'?docks.studio:tab==='brain'||tab==='memory'?docks.knowledge:tab==='chat'?docks.chat:docks.global);
 if(!dock)return;
 // Safari and Chromium can scroll the Artifact panel independently. Move its
 // presence dock outside the scrolling panel on phones, so fixed positioning
 // is relative to the viewport and the orb is never clipped offscreen.
 const studioHome=$('sonicArtifactRoot')?.querySelector('.v22-studio-hero');
 if(docks.studio&&studioHome){
   if(mobile()&&tab==='studio'){
     if(docks.studio.parentElement!==document.body)document.body.append(docks.studio);
   }else if(docks.studio.parentElement===document.body){
     studioHome.append(docks.studio);
   }
 }
 if(anchor.parentElement!==dock)dock.append(anchor);
 const update=()=>{
   if(!document.body.classList.contains('sonic-focused'))window.sonicMotion?.updateHome?.(true);
   const f=$('sonicMotionFloat'),r=f?.getBoundingClientRect();
   const real=Boolean(r&&r.width>10&&r.height>10&&r.right>0&&r.left<innerWidth&&getComputedStyle(f).display!=='none');
   dock.classList.toggle('v22-live-motion',real);
 };
 requestAnimationFrame(()=>requestAnimationFrame(update));
}
function buildHeader(){
 const header=document.querySelector('.topbar');
 if(!header)return;
 const dock=makeDock('v22GlobalOrbDock');
 header.append(dock);docks.global=dock;
 const brand=$('sonicHeaderOrb');if(brand)brand.title='SONIC voice and presence';
 document.querySelector('#knowledgeViews [data-sonic-knowledge=research]')?.replaceChildren(document.createTextNode('Archive'));
}
function buildKnowledge(){
 const panel=$('brainPanel'),nav=$('knowledgeViews');if(!panel||!nav)return;
 const strip=node('div','v22-knowledge-intro');
 strip.append(node('span','v22-knowledge-orb-label','SONIC · KNOWLEDGE'));
 const dock=makeDock('v22KnowledgeOrbDock');strip.append(dock);docks.knowledge=dock;
 nav.before(strip);
 const stage=$('graphStage');
 const status=node('div','v22-knowledge-status');status.id='v22KnowledgeStatus';
 const light=node('span','v22-live-light');light.setAttribute('aria-hidden','true');
 const copy=node('span','v22-live-copy');
 copy.append(node('strong',null,'Communication status'));
 const detail=node('small','', 'No active integration transfer');detail.id='v22IntegrationText';copy.append(detail);
 const bars=node('span','v22-signal-bars');bars.setAttribute('aria-hidden','true');
 for(let i=0;i<4;i++)bars.append(node('i'));
 status.append(light,copy,bars);
 const graph=$('graphStage');if(graph)graph.after(status);
 // The original 3D WebGL engine remains attached and fully interactive.
 const advanced=node('details','v22-graph-tools');
 advanced.id='v22GraphTools';
 advanced.append(node('summary',null,'Graph tools'));
 const actions=node('div','v22-graph-advanced-actions');
 for(const item of [['fitGraph','Fit all'],['focusIntegration','Integration'],['dimensionGraph','3D / 2D'],['rotateGraph','Orbit']]){
  const b=button(item[1],()=>$(item[0])?.click());
  actions.append(b);
 }
 advanced.append(actions);
 status.after(advanced);
 const fit=$('neuralMobileSwitcher');if(fit)fit.hidden=false;
 $('neuralGraphBtn')?.replaceChildren(document.createTextNode('3D'));
 $('neuralKnowledgeBtn')?.replaceChildren(document.createTextNode('List'));
 $('graphHint')?.replaceChildren(document.createTextNode('Tap a node to inspect · swipe to orbit'));
 const oldToolbar=panel.querySelector('.graph-toolbar');
 if(oldToolbar){
  const btn=button('Integration',()=>{
   $('focusIntegration')?.click();
   window.dispatchEvent(new CustomEvent('sonic:signal-integration',{detail:{reason:'owner-trace'}}));
  },'v22-integration-action');btn.id='v22TraceIntegration';
  oldToolbar.append(btn);
 }
}
function statusKnowledge(message,active=false){
 const s=$('v22KnowledgeStatus'),label=$('v22IntegrationText');
 if(label)label.textContent=message;
 if(s)s.classList.toggle('is-active',active);
 if(active){lastPulse=Date.now();clearTimeout(pulseTimer);pulseTimer=setTimeout(()=>{
    if(Date.now()-lastPulse>=3000)statusKnowledge('Idle · awaiting verified graph activity',false);
  },3200);}
}
function buildChat(){
 const panel=$('chatPanel'),feed=$('chatFeed'),wrap=panel?.querySelector('.compose-wrap');
 if(!panel||!feed||!wrap)return;
 const head=node('section','v22-chat-top');head.id='v22ChatTop';
 const modelRow=node('div','v22-chat-model');
 const model=node('div','v22-model-control');model.id='v22ModelControl';
 const dock=makeDock('v22ChatOrbDock');docks.chat=dock;
 modelRow.append(model,dock);
 head.append(modelRow);
 const second=node('div','v22-chat-actions');
 const device=node('div','v22-chat-device');
 device.append(node('span','v22-device-icon','▣'),node('strong',null,'TRADEVICEPC'));
 const online=node('span','v22-device-status','Checking');online.id='v22PCOnline';device.append(online);
 second.append(device);
 const research=node('div','v22-chat-research');research.id='v22ChatResearch';
 second.append(research);
 const tools=node('button','v22-chat-code','</> Coding');
 tools.type='button';tools.addEventListener('click',()=>window.SonicArtifactStudio?.openGenerator?.(''));
 second.append(tools);
 head.append(second);
 panel.prepend(head);
 const widget=panel.querySelector(':scope > .runtime-widget');
 if(widget)model.append(widget);
 const researchTools=$('agentResearchToolbar');
 if(researchTools)research.append(researchTools);
 // Legacy toolbar is retained for its event handlers; only its redundant
 // presentation is removed. Owner PC commands still remain in their panel.
 const pcControls=$('pcTools');
 if(pcControls){
   const advanced=node('details','v22-chat-advanced');
   advanced.append(node('summary',null,'PC tools'));
   advanced.append(pcControls);wrap.append(advanced);
 }
 const security=panel.querySelector('.chat-security-details');if(security)security.open=false;
 updatePc();
}
function updatePc(){
 const target=$('v22PCOnline');if(!target)return;
 const old=$('devicePill');
 const raw=old?.textContent||'';
 const online=old?.classList.contains('online')||/online|connected/i.test(raw);
 target.textContent=online?'Online':'Offline / checking';
 target.dataset.online=String(online);
}
function noteChatErrors(){
 const feed=$('chatFeed');if(!feed)return;
 for(const message of feed.querySelectorAll('.message.assistant.error:not([data-v22-reviewed])')){
  message.dataset.v22Reviewed='1';
  const text=message.querySelector('.body')?.textContent||'';
  const related=/local ai|melebihi batas|inference|model lokal|timeout|gagal|tidak menyelesaikan/i.test(text);
  if(!related)continue;
  message.classList.add('v22-recovery');
  const codeButton=button('Open Coding Studio →',()=>{
   const texts=[...feed.querySelectorAll('.message.user .body')];
   const original=texts.at(-1)?.textContent||'';
   window.SonicArtifactStudio?.openGenerator?.(original.slice(0,1200));
  },'v22-open-coding');
  message.append(codeButton);
 }
}
function buildStudio(){
 const root=$('sonicArtifactRoot');if(!root)return;
 const hero=node('div','v22-studio-hero');
 const icon=node('div','v22-studio-icon','</>');
 const name=node('div','v22-studio-name');
 name.append(node('h2',null,'Artifact Studio'),node('p',null,'Generate → Review → Preview → Save'));
 const dock=makeDock('v22StudioOrbDock');docks.studio=dock;
 hero.append(icon,name,dock);root.prepend(hero);
 const coding=root.querySelector('.as-coding-card');
 if(coding){
  const help=node('div','v22-generator-help');
  help.append(node('span','v22-info-symbol','i'));
  const copy=node('div');copy.append(node('strong',null,'Local vs. DeepSeek'));
  const p=node('p',null,'Local: privat, untuk draft ringkas. DeepSeek: kode lebih panjang melalui API setelah persetujuan.');
  p.id='v22ProviderHelp';copy.append(p);help.append(copy);coding.after(help);
 }
 const controls=root.querySelector('.as-controls');
 if(controls){
  const recent=node('section','v22-recent-artifacts');recent.id='v22RecentArtifacts';
  const title=node('div','v22-recent-heading');
  title.append(node('h3',null,'Artifact Terbaru'));
  const view=button('Lihat Semua →',()=>toggleLibrary(),'v22-view-all');
  view.id='v22ViewAll';title.append(view);
  const actions=root.querySelector('.as-heading-actions');
  if(actions){title.append(actions);}
  recent.append(title);
  const grid=node('div','v22-recent-grid');grid.id='v22RecentGrid';recent.append(grid);
  controls.after(recent);
 }
 const lib=$('asLibrary');if(lib){
  const obs=new MutationObserver(renderRecent);obs.observe(lib,{childList:true,subtree:true});
 }
 const selected=$('asTitle');if(selected){
  const obs=new MutationObserver(syncSelected);obs.observe(selected,{childList:true,characterData:true,subtree:true});
 }
 const provider=$('asCodingProvider');
 if(provider){
  // Local is private and incurs no provider fee. Cloud remains an explicit
  // owner selection and consent step, enforced by the existing generator.
  if(!provider.value){provider.value='local';provider.dispatchEvent(new Event('change',{bubbles:true}));}
  provider.addEventListener('change',updateProviderHelp);
  updateProviderHelp();
 }
 $('asGenerate')?.addEventListener('click',()=>{const s=$('v22RecentArtifacts');if(s)s.dataset.generating='true';});
 const status=$('asCodingStatus');if(status){
  const obs=new MutationObserver(()=>{
    if(/Source lengkap|Source.+diterima/i.test(status.textContent||'')){
      $('v22RecentArtifacts')?.removeAttribute('data-generating');
      syncSelected();
      if(mobile())requestAnimationFrame(()=>$('asEditor')?.scrollIntoView({block:'start',behavior:'smooth'}));
    }
  });obs.observe(status,{childList:true,characterData:true,subtree:true});
 }
 renderRecent();syncSelected();
}
function updateProviderHelp(){
 const p=$('v22ProviderHelp'),sel=$('asCodingProvider');if(!p||!sel)return;
 if(sel.value==='deepseek')p.textContent='DeepSeek: kode lengkap melalui API. Instruksi dikirim hanya setelah Anda menyetujui. Chat default tidak berubah.';
 else p.textContent='Local: draft ringkas, privat di TRADEVICEPC. Untuk aplikasi kompleks pilih DeepSeek secara sadar.';
}
function syncSelected(){
 const title=$('asTitle')?.textContent||'';
 const selected=title&&title!=='No artifact selected';
 $('studioPanel')?.classList.toggle('v22-has-artifact',Boolean(selected));
}
function toggleLibrary(force){
 const panel=$('studioPanel');if(!panel)return;
 viewAll=typeof force==='boolean'?force:!viewAll;
 panel.classList.toggle('v22-show-library',viewAll);
 const b=$('v22ViewAll');if(b)b.textContent=viewAll?'Tutup Library ↑':'Lihat Semua →';
 if(viewAll&&mobile())requestAnimationFrame(()=>$('asLibrary')?.scrollIntoView({block:'start',behavior:'smooth'}));
}
function renderRecent(){
 const grid=$('v22RecentGrid'),lib=$('asLibrary');if(!grid||!lib)return;
 grid.replaceChildren();
 const source=[...lib.querySelectorAll('button.as-entry')];
 if(!source.length){
  const empty=node('div','v22-no-artifacts');
  empty.append(node('strong',null,'Belum ada artifact tersimpan'),node('p',null,'Buat HTML tool atau impor file, lalu tekan Save Version.'));
  empty.append(button('+ New HTML Tool',()=>$('asNewBtn')?.click(),'v22-new-artifact'));
  grid.append(empty);return;
 }
 for(const b of source.slice(0,4)){
  const title=b.querySelector('.as-entry-text strong')?.textContent||'Untitled artifact';
  const meta=b.querySelector('.as-entry-text small')?.textContent||'';
  const card=button('',()=>{b.click();if(mobile()){syncSelected();requestAnimationFrame(()=>$('asStage')?.scrollIntoView({block:'start',behavior:'smooth'}));}},'v22-artifact-card');
  card.setAttribute('aria-label','Open '+title);
  const img=node('div','v22-artifact-visual');
  const kind=/image/i.test(meta)?'image':/audio/i.test(meta)?'audio':/video/i.test(meta)?'video':/website/i.test(meta)?'website':'code';
  img.dataset.kind=kind;
  img.append(node('span','v22-preview-label',kind==='code'?'HTML SOURCE':kind.toUpperCase()),
             node('span','v22-preview-glyph',kind==='code'?'</>':kind==='image'?'▧':kind==='video'?'▷':kind==='audio'?'♫':'◎'));
  const summary=node('div','v22-artifact-caption');
  summary.append(node('strong',null,title),node('small',null,meta));
  card.append(img,summary);grid.append(card);
 }
}
function activateTab(tab){
 activeTab=tab;
 document.body.dataset.sonicPage=tab;
 if(tab==='brain'&&mobile())window.sonicNeural?.setMode?.('graph');
 if(tab==='studio')renderRecent();
 if(tab==='chat')updatePc();
 placeOrb(tab);
}
function setup(){
 if(setupDone)return;setupDone=true;
 document.body.classList.add('sonic-ux-v220');
 buildHeader();buildKnowledge();buildChat();buildStudio();
 const chatFeed=$('chatFeed');if(chatFeed)new MutationObserver(noteChatErrors).observe(chatFeed,{childList:true,subtree:true,characterData:true});
 const device=$('devicePill');if(device)new MutationObserver(updatePc).observe(device,{childList:true,characterData:true,subtree:true,attributes:true});
 const model=$('v22ModelControl');
 // Model widget can arrive after DOMContentLoaded in future versions.
 if(model&&!model.querySelector('.runtime-widget')){
  const runtime=$('chatPanel')?.querySelector('.runtime-widget');if(runtime)model.append(runtime);
 }
 window.addEventListener('sonic:tab',event=>activateTab(event.detail?.tab||'dashboard'));
 window.addEventListener('sonic:graph-loaded',event=>{
  const nodes=Array.isArray(event.detail?.nodes)?event.detail.nodes:[];
  const count=nodes.filter(n=>n.category==='integration').length;
  statusKnowledge(count?'Graph refreshed · '+count+' integration node'+(count>1?'s':''):'No verified integration nodes',Boolean(count));
 });
 window.addEventListener('sonic:integration-visual',event=>{
  if(event.detail?.active){
   statusKnowledge('SONIC → Integration · tracing actual graph path',true);
  }else statusKnowledge('No verified SONIC → Integration graph route',false);
 });
 window.addEventListener('sonic:logout',()=>{
  lastPulse=0;clearTimeout(pulseTimer);statusKnowledge('Sign in to inspect real integrations',false);
 });
 window.addEventListener('resize',()=>{placeOrb(activeTab);});
 window.addEventListener('scroll',()=>{if(!document.body.classList.contains('sonic-focused'))window.sonicMotion?.updateHome?.(true);},{passive:true});
 activateTab(document.querySelector('.sidebar .nav.active')?.dataset.tab||'dashboard');
 noteChatErrors();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup,{once:true});else setup();
})();
