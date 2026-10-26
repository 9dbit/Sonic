/* SONIC V0.9.0 window manager: read-only capability refresh; owner
 * must approve every opening/closing request via existing operator dialog.
 * No direct Windows connection, passwords, paths, shell or hidden automation.
 */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const ACTIONS=new Set(['window.open','window.focus','window.close']);
  const APPS=new Set(['notepad','paint','metatrader5']);
  class SonicWindowManager{
    constructor(){
      this.busy=false;
      this.enabled=false;
      this.apps=[];
      this.root=$('pcWindowControl');
      if(!this.root)return;
      this.status=$('pcWindowStatus');
      this.select=$('pcWindowApp');
      for(const b of this.root.querySelectorAll('[data-window-action]')){
        b.addEventListener('click',()=>this.execute(b.dataset.windowAction));
        b.disabled=true;
      }
      this.root.querySelector('[data-window-refresh]')?.addEventListener('click',()=>this.refresh());
      this.show('Periksa koneksi companion sebelum mengakses window.');
    }
    show(message){this.status.textContent=message;}
    clear(){this.enabled=false;this.apps=[];this.busy=false;this.show('Login diperlukan untuk Window Control.');this.updateButtons();}
    updateButtons(){
      for(const b of this.root.querySelectorAll('[data-window-action]')){
        const action=b.dataset.windowAction;
        b.disabled=!this.enabled||this.busy||!ACTIONS.has(action)||!this.apps.includes(action);
      }
    }
    async refresh(){
      if(!this.root||this.busy)return;
      this.enabled=false;this.updateButtons();
      try{
        const pc=window.sonicPC;
        if(!pc||typeof pc.api!=='function')throw Error('PC Command Center belum aktif.');
        const info=await pc.api('/api/operator/capabilities');
        this.apps=(info.capabilities||[]).filter(x=>ACTIONS.has(x));
        this.enabled=info.connected===true&&this.apps.length>0;
        this.show(this.enabled
          ?'TRADEVICEPC mendukung Window Control. Aksi tetap memerlukan target dan persetujuan pemilik.'
          :'Window Control belum tersedia. Upgrade companion V0.9.0 secara lokal dan aktifkan opt-in Windows.');
      }catch(e){this.show('Window Control tidak tersedia: '+e.message);}
      this.updateButtons();
    }
    async execute(action){
      if(!this.enabled||this.busy||!ACTIONS.has(action))return;
      const app=this.select.value;
      if(!APPS.has(app)){this.show('Aplikasi tidak diizinkan.');return;}
      if(!this.apps.includes(action)){this.show('Kemampuan ini tidak diumumkan oleh companion.');return;}
      if(window.sonicPC?.pending||window.sonicPC?.busy){
        this.show('Selesaikan approval atau tugas PC yang sedang aktif dahulu.');return;
      }
      this.busy=true;this.updateButtons();
      try{
        // Re-read heartbeat before proposing; the server rechecks too.
        const info=await window.sonicPC.api('/api/operator/capabilities');
        if(!info.connected||!(info.capabilities||[]).includes(action))throw Error('Companion tidak siap.');
        await window.sonicPC.propose(action,{app});
        this.show('Periksa target dan dampaknya di dialog approval. Belum ada operasi dijalankan.');
      }catch(error){this.show('Tidak dijalankan: '+error.message);}
      finally{this.busy=false;this.updateButtons();}
    }
  }
  const init=()=>{window.sonicWindows=new SonicWindowManager();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
