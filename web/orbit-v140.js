/* Observes the app's authenticated data events. No fetch, media or private storage. */
(()=>{
 'use strict';
 const el=id=>document.getElementById(id);
 const stateLabels={idle:'Ready',connecting:'Connecting',listening:'Listening',thinking:'Thinking',speaking:'Speaking',muted:'Microphone muted',error:'Unavailable',saving:'Saved'};
 function put(id,text){const node=el(id);if(node)node.textContent=text;}
 function clear(){put('orbitMemory','Locked');put('orbitDevice','Not connected');put('orbitTelemetry','Sign in to view telemetry');put('orbitModel','Not available');}
 window.addEventListener('sonic:overview',event=>{
  const d=event.detail||{};
  if(d.kind==='clear'){clear();return;}
  if(!el('loginOverlay')?.classList.contains('hidden')){clear();return;}
  if(d.kind==='memory')put('orbitMemory',Number.isInteger(d.count)?String(d.count):'Not available');
  if(d.kind==='device'){
   put('orbitDevice',d.connected?'Connected':'Offline');
   put('orbitTelemetry',d.connected&&d.available?('CPU '+window.SonicOrbitMath.metric(d.cpu,'%')+' / RAM '+window.SonicOrbitMath.metric(d.ram,'%')):'No fresh telemetry');
  }
  if(d.kind==='model')put('orbitModel',d.configured&&typeof d.model==='string'?d.model:'Key required');
 });
 window.addEventListener('sonic:focus',event=>{const on=event.detail?.focused===true;el('orbitVoiceCaption').hidden=!on;});
 window.addEventListener('sonic:activity',event=>{if(!window.sonicRealtimeActive)put('orbitVoiceState','Ready');});
 window.addEventListener('sonic:voice-state',event=>{put('orbitVoiceState',stateLabels[event.detail?.state]||'Ready');document.body.dataset.orbitVoice=event.detail?.state||'idle';});
 window.addEventListener('sonic:tab',event=>{el('orbitOverview').hidden=event.detail?.tab!=='brain';});
 document.querySelectorAll('[data-orbit-tab]').forEach(node=>node.addEventListener('click',()=>document.querySelector('.nav[data-tab="'+node.dataset.orbitTab+'"]')?.click()));
 const login=el('loginOverlay');
 if(login){new MutationObserver(()=>{if(!login.classList.contains('hidden'))clear();}).observe(login,{attributes:true,attributeFilter:['class']});if(!login.classList.contains('hidden'))clear();}
})();
