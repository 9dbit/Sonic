/* Durable reply transport. Only a random request ID is kept in sessionStorage.
 * Never store a prompt, answer, cookie or CSRF token in browser storage.
 * Recovery is GET-only after an uncertain POST; never auto-run an installer.
 */
(() => {
 'use strict';
 const KEY='sonic.pending-chat.v183';
 let generation=0;
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 function remember(id){try{sessionStorage.setItem(KEY,JSON.stringify({id,at:Date.now()}));}catch(_){}}
 function forget(id){try{if(pending()?.id===id)sessionStorage.removeItem(KEY);}catch(_){}}
 function pending(){try{const v=JSON.parse(sessionStorage.getItem(KEY)||'null');
   return v&&typeof v.id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(v.id)&&Date.now()-v.at<86400000?v:null;}catch(_){return null;}}
 function completed(data,id){
   if(data.delivery?.state==='failed'){
     forget(id);const e=Error(data.error?.message||data.reply||'Pekerjaan tidak selesai.');
     e.status=data.error?.status||502;e.terminal=true;throw e;
   }
   if(!data.delivery||data.delivery.state==='done'){
     if(typeof data.reply!=='string')throw Error('Balasan server belum lengkap; memeriksa receipt.');
     forget(id);return data;
   }
   return null;
 }
 async function bounded(api,path,opts={},ms=12000){
   const c=new AbortController(),timer=setTimeout(()=>c.abort(),ms);
   try{return await api(path,{cache:'no-store',...opts,signal:c.signal});}finally{clearTimeout(timer);}
 }
 async function poll(api,id,update=()=>{}){
   const guard=generation,start=Date.now();let misses=0;
   while(Date.now()-start<210000){
     if(guard!==generation){const e=Error('Sesi berakhir. Login kembali.');e.status=401;throw e;}
     try{
       const data=await bounded(api,'/api/chat/delivery/'+encodeURIComponent(id));
       misses=0;const done=completed(data,id);if(done)return done;
       const state=data.delivery?.state;
       update((state==='queued'?'TRADEVICEPC sedang memproses jawaban':'Memeriksa pekerjaan')+
         ' · '+(data.delivery?.elapsed_seconds||0)+' detik. Tidak dikirim ulang.');
     }catch(e){
       if(e.terminal||[401,403].includes(e.status))throw e;
       if(e.status===404){misses++;if(misses>=4){forget(id);e.message='Permintaan belum tercatat di server. Kirim kembali setelah koneksi pulih.';e.terminal=true;throw e;}}
       update('Koneksi terputus. Memulihkan status pekerjaan yang sama; tidak menjalankan ulang.');
     }
     await sleep(1800);
   }
   const e=Error('Pemantauan dijeda. Tekan Periksa hasil untuk membaca pekerjaan yang sama, bukan mengirim ulang.');
   e.recoverable=true;throw e;
 }
 async function send(api,body,update=()=>{}){
   const id=body.request_id,existing=pending();
   if(existing?.id===id)return poll(api,id,update);
   if(existing){const e=Error('Pulihkan jawaban sebelumnya sebelum mengirim permintaan baru.');e.recoverable=true;throw e;}
   remember(id);
   try{
     const result=await bounded(api,'/api/chat',{method:'POST',headers:{'X-Sonic-Async':'1'},body:JSON.stringify(body)},15000);
     const done=completed(result,id);if(done)return done;
   }catch(e){
     // A proxy may fail after the server accepted the request. Preserve its ID.
     if(e.terminal||(e.status>=400&&e.status<500&&![408,425].includes(e.status))){forget(id);throw e;}
     update('Koneksi jawaban terputus. Memeriksa ID yang sama tanpa mengirim ulang.');
   }
   return poll(api,id,update);
 }
 window.addEventListener('sonic:logout',()=>{generation++;try{sessionStorage.removeItem(KEY);}catch(_){}});
 window.sonicDelivery={send,poll,pending,forget};
})();
