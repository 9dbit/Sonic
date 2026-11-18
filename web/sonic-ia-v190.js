/* SONIC 1.9: information architecture, non-destructive DOM-only orchestration. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const nav=tab=>document.querySelector('.sidebar .nav[data-tab="'+tab+'"]')?.click();
let selectedDevice='overview',selectedSettings='ai';
const deviceGroups=[
 ['overview','Overview','Device health and snapshots'],
 ['monitor','Monitor','Live performance and connectivity'],
 ['control','Control','Approved Windows actions'],
 ['applications','Applications','Search, inspect and install'],
 ['ai','AI Runtime','Local engine and available resources'],
 ['activity','Activity','Tasks, receipts and audit']
];
const settingsGroups=[
 ['general','General','Appearance and interface'],
 ['ai','AI & Models','Model router, cloud providers and GGUF'],
 ['voice','Voice & Persona','Personality, voice and wake preferences'],
 ['privacy','Memory & Privacy','Owner knowledge and retention'],
 ['security','Devices & Security','Access permissions and approvals'],
 ['system','Integrations & System','Connections and readiness']
];
function el(tag,className,text){
 const n=document.createElement(tag);if(className)n.className=className;if(text)n.textContent=text;return n;
}
function section(name,label){const box=el('section','sonic-ia-group');box.dataset.iaGroup=name;
 const h=el('header','sonic-ia-group-header');h.append(el('h3',null,label));
 box.append(h);return box;
}
function appendIf(target,node){if(target&&node)target.append(node);}
function appendMatching(parent,target,selector){if(!parent||!target)return;for(const node of Array.from(parent.querySelectorAll(selector))){if(node.closest('.sonic-ia-group'))continue;appendIf(target,node);}}
function buildTabs(panel,kind,groups){
 const wrapper=el('div','sonic-ia-tabs');wrapper.setAttribute('role','tablist');wrapper.setAttribute('aria-label',kind+' sections');
 const content=el('div','sonic-ia-content');const map=new Map();
 for(const [key,name,subtitle] of groups){
  const b=el('button',null,name);b.type='button';b.dataset.iaTarget=key;b.setAttribute('role','tab');b.setAttribute('aria-selected','false');b.title=subtitle;
  b.addEventListener('click',()=>kind==='devices'?showDevice(key):showSettings(key));
  wrapper.append(b);
  const body=section(key,name);body.dataset.iaFor=kind;content.append(body);map.set(key,body);
 }
 const intro=panel.querySelector(':scope > .section-head');
 if(intro)intro.after(wrapper,content);else panel.prepend(wrapper,content);
 return map;
}
let devices=null,settings=null;
function showGroup(panel,map,key,kind){
 if(!map||!map.has(key))return;
 for(const [id,body] of map){body.hidden=id!==key;}
 for(const btn of panel.querySelectorAll(':scope > .sonic-ia-tabs [data-ia-target]')){
  const on=btn.dataset.iaTarget===key;btn.setAttribute('aria-selected',String(on));btn.tabIndex=on?0:-1;
 }
 panel.dataset.activeGroup=key;
}
function showDevice(key){selectedDevice=key;showGroup($('devicesPanel'),devices,key,'devices');}
function showSettings(key){selectedSettings=key;showGroup($('setupPanel'),settings,key,'setup');}
function moveSetupActivity(){
 const setup=$('setupPanel'),activity=devices.get('activity');
 const tasks=Array.from(setup.querySelectorAll(':scope > .operator-panel')).find(n=>n.getAttribute('aria-label')==='Aktivitas tugas');
 appendIf(activity,tasks);
 const ready=setup.querySelector(':scope > .engine-readiness');
 if(!ready)return;
 const title=Array.from(ready.children).find(n=>n.tagName==='H3'&&n.textContent.trim()==='Execution receipts');
 if(title){
  let item=title;
  while(item){const next=item.nextElementSibling;activity.append(item);item=next;}
 }
}
function initializeOrganization(){
 const device=$('devicesPanel'),setup=$('setupPanel');
 if(!device||!setup)return;
 devices=buildTabs(device,'devices',deviceGroups);
 settings=buildTabs(setup,'settings',settingsGroups);
 const first=(sel)=>device.querySelector(':scope > '+sel);
 for(const selector of [':scope > .device-card',':scope > .device-controls',':scope > .device-telemetry']){
  const node=device.querySelector(selector);appendIf(devices.get('overview'),node);
 }
 for(const selector of ['#taskManagerPanel'])appendIf(devices.get('monitor'),$(selector));
 for(const selector of ['#pcWindowControl','#pcCommandCenter','#operatorPanel','#deviceResult']){
  appendIf(devices.get('control'),$(selector));
 }
 for(const element of Array.from(device.children)){
  if(element.matches('p.small-note')&&element.textContent.includes('PowerShell'))appendIf(devices.get('control'),element);
 }
 appendIf(devices.get('applications'),$('softwareManager'));
 appendIf(devices.get('ai'),$('localAIControl'));
 moveSetupActivity();
 appendIf(settings.get('ai'),$('brainModelControl'));
 appendIf(settings.get('ai'),$('huggingFaceHub'));
 appendIf(settings.get('voice'),$('personaStudio'));
 appendIf(settings.get('voice'),setup.querySelector(':scope > .engine-readiness'));
 appendIf(settings.get('system'),$('setupList'));
 appendIf(settings.get('system'),setup.querySelector(':scope > .device-controls'));
 appendIf(settings.get('system'),$('setupMessage'));
 appendIf(settings.get('system'),setup.querySelector(':scope > .setup-help'));
 settings.get('general').append(el('p','sonic-ia-copy','Dark charcoal and blue accents are active. Interface settings will remain separate from device commands.'));
 settings.get('privacy').append(el('p','sonic-ia-copy','Saved memories and research belong to the owner. Public preview does not reveal private content.'));
 const memory=el('button','sonic-ia-link','Open Memory Vault →');memory.type='button';memory.addEventListener('click',()=>{nav('brain');requestAnimationFrame(()=>nav('memory'));});settings.get('privacy').append(memory);
 settings.get('security').append(el('p','sonic-ia-copy','PC actions require verified owner approval and exact operation review. The interface does not change underlying permissions.'));
 const inspect=el('button','sonic-ia-link','View approved PC controls →');inspect.type='button';inspect.addEventListener('click',()=>{nav('devices');showDevice('control');});settings.get('security').append(inspect);
 showDevice('overview');showSettings('ai');
 // Existing Hub jump targeted an old DOM location; route through Settings.
 $('hfJump')?.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();nav('setup');showSettings('ai');},true);
}
function knowledge(tab){
 const strip=$('knowledgeViews');if(!strip)return;
 strip.hidden=!['brain','memory'].includes(tab);
 for(const b of strip.querySelectorAll('[data-sonic-knowledge]')){
  const current=tab===b.dataset.sonicKnowledge;
  b.setAttribute('aria-current',current?'page':'false');
 }
}
function goKnowledge(mode){
 if(mode==='research'){
  nav('chat');$('agentModeResearch')?.click();$('agentMemoryPanel')?.removeAttribute('hidden');
  return;
 }
 nav(mode==='memory'?'memory':'brain');
}
function routeAction(kind){
 if(kind==='research'||kind==='knowledge'||kind==='memory'){goKnowledge(kind);return;}
 if(kind==='settings'){nav('setup');showSettings('system');return;}
 if(kind==='pc'||kind==='activity'){nav('devices');showDevice(kind==='activity'?'activity':'control');return;}
 nav('chat');
 if(kind==='chat')$('agentModeChat')?.click();
}
function updateOverview(){
 const model=$('orbitModel')?.textContent?.trim()||'Checking';
 const pc=$('orbitDevice')?.textContent?.trim()||'Protected';
 const memory=$('orbitMemory')?.textContent?.trim()||'Private';
 if($('dashModelState'))$('dashModelState').textContent=model;
 if($('dashPCState'))$('dashPCState').textContent=pc;
 if($('dashKnowledgeState'))$('dashKnowledgeState').textContent=
  /^\d+$/.test(memory)?memory+' saved memories':memory==='Locked'?'Owner-only knowledge':'Saved knowledge';
 const owner=$('loginOverlay')?.classList.contains('hidden')&&!document.body.classList.contains('sonic-open-preview');
 if($('dashActivityState'))$('dashActivityState').textContent=owner?'Review recent tasks':'Owner access required';
 if($('dashActivityText'))$('dashActivityText').textContent=owner?
  'Open the Activity tab to inspect pending approvals and execution receipts.':
  'Private jobs and approval history are only available to the signed-in owner.';
}
function init(){
 initializeOrganization();
 for(const b of document.querySelectorAll('#knowledgeViews [data-sonic-knowledge]')){
  b.addEventListener('click',()=>goKnowledge(b.dataset.sonicKnowledge));
 }
 for(const b of document.querySelectorAll('[data-sonic-open]')){
  b.addEventListener('click',()=>routeAction(b.dataset.sonicOpen));
 }
 $('dashTalk')?.addEventListener('click',()=>$('talkSonic')?.click());
 $('dashAskForm')?.addEventListener('submit',e=>{
  e.preventDefault();const value=$('dashAsk')?.value.trim();if(!value)return;
  nav('chat');$('agentModeChat')?.click();const input=$('message');
  if(input){input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();$('chatForm')?.requestSubmit();}
  $('dashAsk').value='';
 });
 window.addEventListener('sonic:overview',updateOverview);
 window.addEventListener('sonic:owner-ready',updateOverview);
 window.addEventListener('sonic:logout',updateOverview);
 window.addEventListener('sonic:tab',e=>{
  const tab=e.detail?.tab;
  knowledge(tab);
  if(tab==='devices')showDevice(selectedDevice);
  if(tab==='setup')showSettings(selectedSettings);
  updateOverview();
 });
 const model=$('orbitModel'),pc=$('orbitDevice'),memory=$('orbitMemory');
 const observe=new MutationObserver(updateOverview);
 for(const n of [model,pc,memory])if(n)observe.observe(n,{childList:true,characterData:true,subtree:true});
 const overview=$('orbitOverview');if(overview)overview.hidden=false;
 knowledge('dashboard');updateOverview();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();