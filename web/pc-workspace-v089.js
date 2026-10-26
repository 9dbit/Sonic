/* SONIC V0.8.9: owner-approved, read-only Windows file browser.
 * Uses the EXISTING authenticated operator queue and V0.8.3 companion:
 * file.list and file.read only. No file writes, local shell, token storage,
 * background scanning, or automatic Windows access.
 */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const make=(tag,klass,text)=>{
    const item=document.createElement(tag);
    if(klass)item.className=klass;
    if(text!==undefined)item.textContent=text;
    return item;
  };
  const button=(label,callback,klass)=>{
    const b=make('button',klass||'ws-pc-button',label);
    b.type='button';
    b.addEventListener('click',callback);
    return b;
  };
  const RESERVED=/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i;
  const PROTECTED=new Set(['.git','.ssh','.aws','.config','.venv','secrets','credentials']);
  const TEXT_EXTENSIONS=/\.(?:txt|md|json|csv|log|py|js|html|css)$/i;
  function cleanRelative(value,kind='folder'){
    if(typeof value!=='string')throw Error('Path PC tidak valid.');
    if(value==='.'&&kind==='folder')return '.';
    if(value.length<1||value.length>180||value!==value.trim()||
       value.startsWith('/')||value.startsWith('\\')||value.startsWith('~')||
       /^[A-Za-z]:/.test(value)||value.includes('\\')){
      throw Error('Hanya path relatif dalam folder SONIC yang diizinkan.');
    }
    const parts=value.split('/');
    if(parts.length>5||parts.some(p=>!p||p.length>70||p==='.'||p==='..'||
       /[<>:"|?*$%\x00-\x1f]/.test(p)||p.endsWith(' ')||p.endsWith('.')||
       RESERVED.test(p)||PROTECTED.has(p.toLowerCase()))){
      throw Error('Path PC ditolak karena berisiko keluar dari workspace.');
    }
    if(parts.some(p=>/secret|password|token|credential|\.env/i.test(p))){
      throw Error('File rahasia tidak dapat dibuka dari browser SONIC.');
    }
    if(kind==='file'&&!TEXT_EXTENSIONS.test(parts[parts.length-1])){
      throw Error('Hanya preview file teks yang diizinkan.');
    }
    return value;
  }
  function joinPath(parent,part,kind){
    const base=cleanRelative(parent,'folder');
    if(typeof part!=='string'||part.includes('/')||part.includes('\\'))throw Error('Nama file PC tidak valid.');
    return cleanRelative(base==='.'?part:base+'/'+part,kind);
  }
  function pathEvidenceMatches(actual,relative){
    if(typeof actual!=='string'||actual.length<4||actual.length>500||
       /[\x00-\x1f]/.test(actual))return false;
    const normalized=actual.replace(/\//g,'\\');
    if(!/^[A-Za-z]:\\/.test(normalized)||normalized.split('\\').includes('..'))return false;
    if(relative==='.')return true; // Local root is enforced by the Windows companion.
    return normalized.toLowerCase().endsWith('\\'+relative.replace(/\//g,'\\').toLowerCase());
  }
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  class SonicPCWorkspace{
    constructor({api,notify,cloud}){
      Object.assign(this,{api,notify,cloud});
      this.mode='cloud';
      this.path='.';
      this.current=null;
      this.generation=0;
      this.pending=null;
      this.busy=false;
      this.ready=false;
      this.connectionCheck=0;
      $('wsPcCloudTab').addEventListener('click',()=>this.switchMode('cloud'));
      $('wsPcDeviceTab').addEventListener('click',()=>this.switchMode('pc'));
      $('wsPc').addEventListener('click',()=>this.switchMode('pc'));
      $('wsCloud').addEventListener('click',()=>this.switchMode('cloud'));
      $('wsPcRoot').addEventListener('click',()=>this.run('file.list','.').catch(e=>this.notify(e.message)));
      $('wsPcRefresh').addEventListener('click',()=>this.run('file.list',this.path).catch(e=>this.notify(e.message)));
      $('wsPcUp').addEventListener('click',()=>this.goUp().catch(e=>this.notify(e.message)));
      $('wsPcCancel').addEventListener('click',()=>this.cancel());
      $('wsPcClose').addEventListener('click',()=>this.hidePreview());
      this.renderState();
    }
    status(message){$('wsPcStatus').textContent=message;}
    renderState(){
      const active=this.mode==='pc';
      $('workspacePanel').classList.toggle('ws-pc-mode',active);
      $('wsPcArea').classList.toggle('hidden',!active);
      $('wsPcCloudTab').classList.toggle('active',!active);
      $('wsPcDeviceTab').classList.toggle('active',active);
      $('wsPcCloudTab').setAttribute('aria-pressed',String(!active));
      $('wsPcDeviceTab').setAttribute('aria-pressed',String(active));
      $('wsPcRoot').disabled=this.busy||!this.ready;
      $('wsPcRefresh').disabled=this.busy||!this.ready;
      $('wsPcUp').disabled=this.busy||this.path==='.'||!this.ready;
      $('wsPcCancel').disabled=!this.busy;
      this.renderBreadcrumbs();
    }
    async switchMode(next){
      if(next===this.mode)return;
      if(next==='pc'&&!this.cloud.canLeave())return;
      this.cancel({silent:true});
      if(next==='pc')this.cloud.closePreview();
      this.mode=next;
      if(next==='cloud'){
        this.clearFiles();
        this.cloud.refresh().catch(e=>this.notify(e.message));
      }else{
        this.status('Periksa koneksi Windows, lalu pilih "Buka root PC". Tidak ada file dibaca otomatis.');
        this.checkConnection().catch(e=>this.status('TRADEVICEPC belum siap: '+e.message));
      }
      this.renderState();
    }
    clearFiles(){
      this.path='.';
      this.current=null;
      $('wsPcList').replaceChildren();
      $('wsPcStatus').textContent='';
      this.hidePreview();
    }
    hidePreview(){
      $('wsPcPreview').classList.add('hidden');
      $('wsPcText').textContent='';
      $('wsPcFileName').textContent='';
      $('wsPcEvidence').textContent='';
    }
    clear(){
      this.generation++;
      this.pending=null;
      this.busy=false;
      this.ready=false;
      this.mode='cloud';
      this.connectionCheck++;
      this.clearFiles();
      this.renderState();
    }
    async checkConnection(){
      const current=++this.connectionCheck;
      const data=await this.api('/api/integrations');
      if(current!==this.connectionCheck||this.mode!=='pc')return false;
      const native=(data.adapters||[]).find(a=>a.id==='windows-native');
      const caps=new Set(native?.current_capabilities||[]);
      this.ready=native?.state==='online'&&native?.connected===true&&
        caps.has('file.list')&&caps.has('file.read');
      this.renderState();
      this.status(this.ready
        ?'TRADEVICEPC online. Read-only: file.list dan file.read. Tidak ada sinkronisasi PC atau izin menulis.'
        :'TRADEVICEPC offline atau kemampuan file.list / file.read belum tersedia. Tidak ada job dijalankan.');
      return this.ready;
    }
    async goUp(){
      const parent=this.path.split('/').slice(0,-1).join('/')||'.';
      return this.run('file.list',parent);
    }
    renderBreadcrumbs(){
      const host=$('wsPcBreadcrumbs');
      host.replaceChildren();
      host.append(button('SONIC PC root',()=>this.run('file.list','.').catch(e=>this.notify(e.message)),'ws-pc-crumb'));
      if(this.path==='.'){return;}
      const parts=this.path.split('/');
      parts.forEach((part,index)=>{
        host.append(make('span','ws-pc-slash',' / '));
        host.append(button(part,()=>this.run('file.list',parts.slice(0,index+1).join('/')).catch(e=>this.notify(e.message)),'ws-pc-crumb'));
      });
    }
    renderEntries(items,truncated){
      this.hidePreview();
      const host=$('wsPcList');
      host.replaceChildren();
      if(!items.length)host.append(make('p','ws-pc-empty','Folder kosong atau semua entri dilindungi.'));
      for(const item of items.slice(0,60)){
        if(!item||typeof item.name!=='string'||!['directory','file'].includes(item.kind))continue;
        const row=make('article','ws-pc-row');
        const label=make('span','ws-pc-kind',item.kind==='directory'?'▱':'≡');
        const details=make('div','ws-pc-details');
        const name=button(item.name,()=>this.openEntry(item).catch(e=>this.notify(e.message)),'ws-pc-filename');
        const allowed=(()=>{
          try{joinPath(this.path,item.name,item.kind==='file'?'file':'folder');return true;}
          catch(_){return false;}
        })();
        // Rendered after a completed listing, so do not leave rows disabled
        // when the asynchronous request transitions back to idle.
        name.disabled=!allowed;
        const info=make('small','',item.kind==='directory'?'Folder':Number.isSafeInteger(item.bytes)?item.bytes.toLocaleString('id-ID')+' bytes':'File teks');
        details.append(name,info);row.append(label,details);host.append(row);
      }
      if(truncated)host.append(make('p','ws-pc-notice','Daftar hanya memuat maksimal 60 entri. Gunakan folder yang lebih spesifik.'));
    }
    async openEntry(item){
      const kind=item.kind==='directory'?'folder':'file';
      const path=joinPath(this.path,item.name,kind);
      if(kind==='file'&&Number.isInteger(item.bytes)&&item.bytes>32768){
        throw Error('File lebih dari 32 KB, di luar batas preview Windows companion.');
      }
      await this.run(kind==='folder'?'file.list':'file.read',path);
    }
    async cancel({silent=false}={}){
      const pending=this.pending;
      this.pending=null;
      this.generation++;
      this.busy=false;
      this.renderState();
      if(pending){
        try{await this.api('/api/operator/requests/'+encodeURIComponent(pending),{method:'DELETE'});}
        catch(_){ /* The owner session may have expired; the device lease is bounded. */ }
      }
      if(!silent&&this.mode==='pc')this.status('Pembatalan diminta. Operasi yang sudah berjalan mungkin telah membaca file.');
    }
    async run(action,requested){
      if(this.mode!=='pc'||this.busy)return;
      if(!['file.list','file.read'].includes(action))throw Error('Aksi PC tidak diizinkan.');
      const path=cleanRelative(requested,action==='file.read'?'file':'folder');
      const beforeCheck=this.generation;
      if(!(await this.checkConnection())||this.mode!=='pc'||this.generation!==beforeCheck)return;
      const purpose=action==='file.list'?'melihat isi folder':'membaca file teks';
      const label=path==='.'?'root SONIC pada Windows':path;
      if(!confirm('Izinkan SONIC '+purpose+' "'+label+'" pada TRADEVICEPC?\n\nHanya di dalam root workspace Windows yang telah dikonfigurasi. Tidak membuat atau mengubah file.'))return;
      const generation=++this.generation;
      this.busy=true;
      this.renderState();
      this.status('Menyiapkan permintaan Windows: '+purpose+' "'+label+'"...');
      let id=null;
      try{
        const proposal=await this.api('/api/operator/requests',{method:'POST',
          body:JSON.stringify({action,payload:{path}})});
        id=proposal.id;
        if(generation!==this.generation){
          if(id)await this.api('/api/operator/requests/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{});
          return;
        }
        if(!id||proposal.action!==action||proposal.state!=='pending'||
           proposal.payload?.path!==path||!/^[a-f0-9]{64}$/i.test(proposal.digest||'')){
          throw Error('Proposal berubah atau tidak sesuai target. Tidak dieksekusi.');
        }
        this.pending=id;
        const submitted=await this.api('/api/operator/requests/'+encodeURIComponent(id)+'/confirm',{
          method:'POST',body:JSON.stringify({confirm:true,digest:proposal.digest})});
        if(generation!==this.generation)return;
        if(!['queued','leased'].includes(submitted.state))throw Error('PC tidak menerima perintah.');
        this.status('Meminta hasil dari companion Windows. ID '+id.slice(0,8)+'...');
        let final=submitted;
        for(let attempt=0;attempt<85;attempt++){
          if(generation!==this.generation)return;
          await wait(1000);
          if(generation!==this.generation)return;
          final=await this.api('/api/operator/requests/'+encodeURIComponent(id));
          if(!['queued','leased','pending'].includes(final.state))break;
        }
        if(generation!==this.generation)return;
        if(final.state!=='done')throw Error('Perintah PC '+(final.state||'belum selesai')+'. Tidak ada file ditampilkan.');
        if(final.action!==action||final.payload?.path!==path||!final.result||typeof final.result!=='object'){
          throw Error('Hasil companion tidak cocok dengan permintaan.');
        }
        const data=final.result;
        if(action==='file.list'){
          if(!pathEvidenceMatches(data.directory,path)||!Array.isArray(data.items))throw Error('Bukti daftar folder tidak sesuai target.');
          this.path=path;this.current=data;
          this.renderEntries(data.items,data.truncated===true);
          this.status('Daftar dari Windows companion diterima: '+path+' (agent-reported; bukan readback independen).');
        }else{
          if(!pathEvidenceMatches(data.path,path)||typeof data.content!=='string'||data.content.length>16000){
            throw Error('Bukti file tidak sesuai target atau melebihi batas.');
          }
          $('wsPcPreview').classList.remove('hidden');
          $('wsPcFileName').textContent=path;
          $('wsPcText').textContent=data.content;
          $('wsPcEvidence').textContent='Sumber: Windows companion terautentikasi. Baca saja; panjang maksimal 16.000 karakter, tanpa verifikasi independen.';
          this.status('Preview teks diterima. Tidak ada file PC yang diubah.');
        }
      }catch(error){
        if(generation===this.generation){
          // A transport failure after queuing is *uncertain*, not proof the PC
          // did nothing. Best-effort cancellation cannot undo a completed read.
          if(id){
            await this.api('/api/operator/requests/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{});
            this.status('Status pembacaan PC belum terkonfirmasi. Pembatalan diminta; operasi yang sudah berjalan mungkin telah membaca file. '+error.message);
          }else{
            this.status('Permintaan PC tidak terkirim: '+error.message);
          }
          this.notify(error.message);
        }
      }finally{
        if(generation===this.generation){
          this.busy=false;this.pending=null;this.renderState();
        }else if(id){
          await this.api('/api/operator/requests/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{});
        }
      }
    }
  }
  window.SonicPCPath={cleanRelative,joinPath,pathEvidenceMatches};
  window.SonicPCWorkspace=SonicPCWorkspace;
})();
