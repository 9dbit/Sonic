/* SONIC v2.3.1: responsive header, authenticated entry, static focus stage.
 * UI-only. Existing authorization, voice transport and model handlers own state.
 */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const guest=()=>document.body.classList.contains('sonic-open-preview');
const link=(id,label)=>{
 const a=document.createElement('a');a.id=id;a.className='v231-owner-link';
 a.href='/owner';a.textContent=label;return a;
};
function mountGuest(){
 if(!guest())return;
 const right=document.querySelector('.topbar .top-right');
 if(right&&!$('sonicOwnerAccess')){
  const a=link('sonicOwnerAccess','Owner login');
  a.title='Open the private SONIC sign-in. Passkey or owner token required.';
  right.insertBefore(a,$('talkSonic')||null);
 }
 // Reuse the existing public-preview select and its existing onChange
 // handler; do not create a second model state or fake status.
 const picker=$('previewModelPicker'),model=$('v22ModelControl');
 if(picker&&model&&picker.parentElement!==model)model.append(picker);
 const pc=$('v22PCOnline');
 if(pc){pc.textContent='Private · owner only';pc.dataset.online='false';}
 const root=$('sonicArtifactRoot');
 if(root&&!$('v231OwnerGate')){
  const gate=document.createElement('section');gate.id='v231OwnerGate';
  gate.className='v231-owner-gate';gate.setAttribute('role','note');
  const tag=document.createElement('span');tag.className='v231-gate-tag';
  tag.textContent='PRIVATE WORKSPACE';
  const title=document.createElement('h3');title.textContent='Artifact Studio memerlukan akses owner';
  const copy=document.createElement('p');
  copy.textContent='Anda berada di public staging preview. Generate, source, penyimpanan, dan perangkat PC hanya tersedia setelah masuk sebagai owner.';
  const a=link('v231StudioOwnerLogin','Masuk ke SONIC Owner');
  gate.append(tag,title,copy,a);
  root.querySelector('.as-coding-card')?.before(gate);
 }
 for(const id of ['asGenerate','asCodingPrompt','asCodingProvider','asCodeRevise']){
  const item=$(id);if(item)item.disabled=true;
 }
}
function init(){
 // The app sets preview mode only after /api/session and /api/preview/models.
 // Body-class and tab observers cover both slow and instant responses.
 const refresh=()=>{if(guest())mountGuest()};
 const observer=new MutationObserver(refresh);
 observer.observe(document.body,{attributes:true,attributeFilter:['class']});
 const header=document.querySelector('.topbar .top-right');
 if(header)observer.observe(header,{childList:true});
 window.addEventListener('sonic:tab',refresh);
 // Minimize must return to the regular page; it must never leave a blank,
 // focused fullscreen behind a collapsed voice session bar.
 $('voiceHide')?.addEventListener('click',()=>{
  if(document.body.classList.contains('sonic-focused'))
   window.sonicMotion?.returnHome?.();
 },true);
 // A session ending due to time limit or connection drop must not leave
 // the user trapped on the voice focus stage.
 window.addEventListener('sonic:voice-state',event=>{
  if(event.detail?.state==='idle'&&document.body.classList.contains('sonic-focused'))
   window.sonicMotion?.returnHome?.();
 });
 refresh();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
