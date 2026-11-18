/* Authenticated PC controls. Model text never becomes an executable command. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 const node=(tag,label)=>{const n=document.createElement(tag);if(label)n.textContent=label;return n;};
 let panel,cap={},refreshId=0;
 function command(text){panel.open=false;window.sonicPCChat?.command(text);}
 function button(label,text,action){const b=node('button',label);b.type='button';b.dataset.pcAction=action;
   b.disabled=true;b.addEventListener('click',()=>command(text));return b;}
 async function refresh(){
   if(!panel)return;
   const id=++refreshId;
   const owner=()=>$('loginOverlay')?.classList.contains('hidden')&&!document.body.classList.contains('sonic-open-preview');
   panel.hidden=!owner();if(panel.hidden){cap={};panel.open=false;return;}
   try{const r=await fetch('/api/operator/capabilities',{credentials:'same-origin',cache:'no-store'});
     if(!r.ok)throw Error('status unavailable');const next=await r.json();if(id!==refreshId||!owner())return;cap=next;
   }catch(_){if(id!==refreshId)return;cap={};}
   const online=cap.connected===true&&cap.metrics_available===true;
   $('pcToolsState').textContent=online?'TRADEVICEPC terhubung':'Perangkat belum siap';
   panel.querySelectorAll('[data-pc-action]').forEach(b=>{
     const action=b.dataset.pcAction;
     const allowed=action==='hardware'?cap.connected===true:online&&cap.capabilities?.includes(action)&&(!action.startsWith('software.')||cap.software?.discovery_enabled===true);
     b.disabled=!allowed;
   });
   $('pcInspect').disabled=!(online&&cap.capabilities?.includes('software.inspect')&&cap.software?.discovery_enabled);
 }
 function init(){
   const wrap=document.querySelector('#chatPanel .compose-wrap');if(!wrap)return;
   panel=node('details');panel.id='pcTools';panel.hidden=true;
   const summary=node('summary','Kontrol PC');const state=node('span');state.id='pcToolsState';summary.append(state);panel.append(summary);
   const actions=node('div');actions.className='pc-quick-actions';
   actions.append(button('Status PC','cek status pc','hardware'),
     button('Software terpasang','lihat software terpasang','software.inventory'),
     button('Jalankan Notepad','buka notepad','window.open'),
     button('Jalankan Paint','buka paint','window.open'));
   panel.append(actions);
   const search=node('form');search.className='pc-software-search';
   const q=node('input');q.id='pcSoftwareQuery';q.type='search';q.placeholder='Cari software…';q.maxLength=120;q.required=true;
   q.setAttribute('aria-label','Cari software di WinGet');
   const find=node('button','Cari software');find.type='submit';find.dataset.pcAction='software.search';find.disabled=true;
   search.append(q,find);search.addEventListener('submit',e=>{e.preventDefault();if(!find.disabled&&q.value.trim())command('cari software '+q.value.trim());});panel.append(search);
   const inspect=node('details');inspect.className='pc-inspect-form';inspect.append(node('summary','Periksa & instal versi tertentu'));
   const form=node('form');form.id='pcInspectForm';
   for(const [id,label,placeholder] of [['pcPackage','Package ID','contoh: Git.Git'],['pcVersion','Versi persis','dari hasil pencarian']]){
     const l=node('label',label);const input=node('input');input.id=id;input.required=true;input.maxLength=id==='pcPackage'?128:80;input.placeholder=placeholder;l.append(input);form.append(l);
   }
   form.append(node('p','Periksa paket terlebih dahulu. Informasi penerbit dan lisensi muncul di chat; centang persetujuan setelah membacanya.'));
   for(const [id,label] of [['pcSourceConsent','Saya menyetujui ketentuan sumber WinGet'],['pcPackageConsent','Saya menyetujui lisensi paket yang dipilih']]){
     const l=node('label');const input=node('input');input.id=id;input.type='checkbox';l.append(input,document.createTextNode(label));form.append(l);
   }
   const submit=node('button','Periksa paket');submit.id='pcInspect';submit.type='submit';submit.disabled=true;form.append(submit);
   form.addEventListener('submit',e=>{e.preventDefault();if(submit.disabled)return;window.sonicPCChat?.inspect({package_id:$('pcPackage').value.trim(),version:$('pcVersion').value.trim(),accept_source_agreements:$('pcSourceConsent').checked,accept_package_agreements:$('pcPackageConsent').checked});panel.open=false;});
   inspect.append(form);panel.append(inspect);
   panel.append(node('p','SONIC Companion menjalankan perintah di TRADEVICEPC. Instalasi dan membuka aplikasi meminta konfirmasi di chat. Dukungan aplikasi: Notepad, Paint, dan MT5 dengan izin khusus.'));
   const open=node('button','Software Manager lengkap');open.type='button';open.addEventListener('click',()=>{panel.open=false;document.querySelector('.nav[data-tab="devices"]')?.click();$('softwareManager')?.scrollIntoView({block:'start',behavior:'smooth'});});panel.append(open);
   const slot=node('div');slot.className='pc-tools-slot';slot.append(panel);wrap.prepend(slot);
   function fit(){
     const runtime=document.querySelector('#chatPanel .runtime-widget');
     const top=Math.max(runtime?.getBoundingClientRect().bottom||$('chatPanel').getBoundingClientRect().top,(window.visualViewport?.offsetTop||0)+8);
     panel.style.maxHeight=Math.max(40,Math.min(400,slot.getBoundingClientRect().bottom-top-8))+'px';
   }
   // Size before the native details toggle paints, including Chromium's first frame.
   summary.addEventListener('click',fit);
   panel.addEventListener('toggle',()=>{if(panel.open){panel.scrollTop=0;fit();refresh();}});
   panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();panel.open=false;summary.focus();}});
   document.addEventListener('pointerdown',e=>{if(panel.open&&!panel.contains(e.target))panel.open=false;});
   window.addEventListener('resize',fit);window.visualViewport?.addEventListener('resize',()=>requestAnimationFrame(fit));
   if(window.ResizeObserver){new ResizeObserver(fit).observe(wrap);}
   document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&panel.open)refresh();});
   window.addEventListener('sonic:owner-ready',refresh);
   window.addEventListener('sonic:logout',()=>{refreshId++;cap={};panel.open=false;panel.hidden=true;form.reset();q.value='';panel.querySelectorAll('[data-pc-action],#pcInspect').forEach(b=>b.disabled=true);});
   window.sonicPCTools={prefill:plan=>{panel.open=true;inspect.open=true;$('pcPackage').value=plan.package_id||'';$('pcVersion').value=plan.version||'';$('pcSourceConsent').checked=false;$('pcPackageConsent').checked=false;refresh();requestAnimationFrame(()=>{fit();$('pcPackage').focus({preventScroll:true});$('pcPackage').scrollIntoView({block:'nearest'});});}};
   refresh();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
