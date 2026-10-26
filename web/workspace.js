/* Owner-only SONIC Cloud text workspace. DOM text only; no rendered HTML notes. */
(()=>{'use strict';
 const $=id=>document.getElementById(id);
 const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const action=(text,fn,cls='ws-button')=>{const b=node('button',cls,text);b.type='button';b.addEventListener('click',fn);return b;};
 class SonicWorkspace{
  constructor({api,notify,open,read}){
   Object.assign(this,{api,notify,open,read});this.parent='root';this.selected=null;this.folders=[];this.trash=false;this.dirty=false;this.epoch=0;this.searchSequence=0;this.selectionSequence=0;this.busy=false;this.visible=false;
   $('wsRefresh').onclick=()=>this.refresh().catch(e=>notify(e.message));
   $('wsNewFolder').onclick=()=>this.nameDialog('folder');$('wsNewNote').onclick=()=>this.nameDialog('text');
   $('wsTrash').onclick=()=>this.navigate('root',true);$('wsCloud').onclick=()=>this.navigate('root');
   $('wsSearch').addEventListener('input',()=>{clearTimeout(this.searchTimer);this.searchTimer=setTimeout(()=>this.refresh().catch(e=>notify(e.message)),160);});
   $('wsSave').onclick=()=>this.save().catch(e=>notify(e.message));
   $('wsEditor').addEventListener('input',()=>this.markDirty());
   $('wsRename').onclick=()=>this.nameDialog('rename');$('wsMove').onclick=()=>this.moveDialog();
   $('wsDelete').onclick=()=>this.reviewDelete();$('wsRestore').onclick=()=>this.restore().catch(e=>notify(e.message));
   $('wsReload').onclick=()=>{if(this.canLeave()){this.dirty=false;this.select(this.selected).catch(e=>notify(e.message));}};
   $('wsRead').onclick=()=>{if(this.selected?.kind==='text')read($('wsEditor').value);};
   $('wsDictate').onclick=()=>this.dictate();$('wsClosePreview').onclick=()=>{if(this.canLeave())this.closePreview();};
   $('wsForm').addEventListener('submit',e=>{e.preventDefault();this.submitDialog().catch(e=>notify(e.message));});
   $('wsDialogCancel').onclick=()=>this.cancelDialog();$('wsDialog').addEventListener('cancel',e=>{if(this.busy)e.preventDefault();else this.pending=null;});
   window.addEventListener('beforeunload',e=>{if(this.dirty){e.preventDefault();e.returnValue='';}});
   this.closePreview();
  }
  async request(path,opts){const epoch=this.epoch;const result=await this.api('/api/workspace'+path,opts);if(epoch!==this.epoch)throw Error('Sesi workspace sudah berubah.');return result;}
  canLeave(){return !this.dirty||confirm('Catatan belum disimpan. Tinggalkan perubahan ini?');}
  markDirty(){this.dirty=!!this.selected&&$('wsEditor').value!==this.selected.content;this.editorState();}
  editorState(){
   $('wsSave').disabled=!this.dirty||this.busy;
   $('wsSaveState').textContent=this.dirty?'Perubahan belum disimpan':this.selected?.trashed?'Di Trash':this.selected?'Tersimpan di SONIC Cloud · v'+this.selected.revision:'';
  }
  stopDictation(){this.recognition?.stop();}
  closePreview(){this.selectionSequence++;this.recognition?.stop();this.selected=null;this.dirty=false;$('workspacePanel').classList.remove('ws-editing');$('wsPreview').classList.add('hidden');$('wsEditor').value='';this.editorState();}
  clear(){this.epoch++;this.searchSequence++;this.visible=false;this.closePreview();this.parent='root';this.folders=[];this.rows=[];this.trash=false;clearTimeout(this.searchTimer);this.pending=null;this.busy=false;$('wsDialog').close();$('wsName').value='';$('wsSearch').value='';$('wsList').replaceChildren();$('wsTree').replaceChildren();$('wsBreadcrumbs').replaceChildren();$('wsMoveTarget').replaceChildren();for(const id of ['wsStatus','wsPreviewName','wsPreviewPath','wsFolderInfo','wsSaveState','wsDialogTitle','wsDialogHint','wsDialogError'])$(id).textContent='';}
  async navigate(parent,trash=false){
   if(this.busy||!this.canLeave())return;
   this.closePreview();this.parent=parent;this.trash=trash;$('wsSearch').value='';await this.refresh();
  }
  async refresh(){
   const sequence=++this.searchSequence,query=$('wsSearch').value.trim();$('wsStatus').textContent='Memuat workspace…';
   let data;
   try{data=await this.request('/items?'+new URLSearchParams({parent_id:this.parent,query,trash:String(this.trash)}));}
   catch(e){if(sequence===this.searchSequence){$('wsList').replaceChildren();$('wsStatus').textContent=e.message;}throw e;}
   if(sequence!==this.searchSequence)return;
   this.folders=data.folders;this.rows=data.items;$('wsStatus').textContent=data.notice;
   if(this.selected)$('wsPreviewPath').textContent=this.folderPath(this.selected.parent_id);
   $('wsNewFolder').disabled=this.trash;$('wsNewNote').disabled=this.trash;
   $('wsTrash').classList.toggle('active',this.trash);$('wsCloud').classList.toggle('active',!this.trash&&this.parent==='root');
   $('wsBreadcrumbs').replaceChildren();
   for(const part of data.breadcrumbs)$('wsBreadcrumbs').append(action(part.name,()=>this.navigate(part.id),'ws-crumb'));
   if(this.trash)$('wsBreadcrumbs').append(node('span','',' / Trash'));
   if(query)$('wsBreadcrumbs').append(node('span','',' / Pencarian seluruh workspace'));
   this.renderTree();this.renderRows();
  }
  renderTree(){
   const host=$('wsTree');host.replaceChildren();
   const append=(parent,depth)=>{for(const f of this.folders.filter(f=>f.parent_id===parent)){
    const b=action('▱ '+f.name,()=>this.navigate(f.id),'ws-tree-folder');b.style.paddingLeft=(12+depth*14)+'px';b.classList.toggle('active',!this.trash&&this.parent===f.id);b.title=f.name;host.append(b);append(f.id,depth+1);
   }};append('root',0);
  }
  folderPath(id){const labels=[],seen=new Set();while(id!=='root'&&!seen.has(id)){seen.add(id);const f=this.folders.find(f=>f.id===id);if(!f)break;labels.unshift(f.name);id=f.parent_id;}return ['SONIC Cloud',...labels].join(' / ');}
  renderRows(){
   const host=$('wsList');host.replaceChildren();
   if(!this.rows.length){host.append(node('div','ws-empty',this.trash?'Trash kosong.':$('wsSearch').value.trim()?'Tidak ada nama yang cocok.':'Folder ini masih kosong. Buat folder atau catatan pertama.'));return;}
   for(const item of this.rows){
    const row=node('article','ws-row');row.dataset.id=item.id;
    const icon=node('span','ws-file-icon',item.kind==='folder'?'▱':'≡');icon.setAttribute('aria-hidden','true');
    const name=action(item.name,()=>{if(this.trash||item.kind==='text')this.select(item).catch(e=>this.notify(e.message));else this.navigate(item.id).catch(e=>this.notify(e.message));},'ws-file-name');
    const meta=node('small','',item.kind==='folder'?'Folder':item.bytes.toLocaleString('id-ID')+' bytes · '+new Date(item.updated_at).toLocaleDateString('id-ID'));
    if($('wsSearch').value.trim())meta.textContent+=' · '+this.folderPath(item.parent_id);
    const info=node('div','ws-file-info');info.append(name,meta);
    const menu=action('•••',()=>this.select(item).catch(e=>this.notify(e.message)),'ws-more');menu.setAttribute('aria-label','Kelola '+item.name);
    row.append(icon,info,menu);host.append(row);
   }
  }
  async select(item){
   if(this.busy||!item||!this.canLeave())return;
   this.recognition?.stop();const sequence=++this.selectionSequence;
   const full=item.trashed?item:await this.request('/items/'+item.id);
   if(sequence!==this.selectionSequence)return;
   this.selected=full;this.dirty=false;
   $('wsPreview').classList.remove('hidden');$('workspacePanel').classList.add('ws-editing');$('wsPreviewName').textContent=full.name;
   $('wsPreviewPath').textContent=this.folderPath(full.parent_id);$('wsEditor').value=full.content||'';
   const text=full.kind==='text'&&!full.trashed;
   $('wsEditor').classList.toggle('hidden',!text);$('wsFolderInfo').classList.toggle('hidden',text);
   $('wsFolderInfo').textContent=full.trashed?'Pulihkan item ini untuk membuka isinya.':'Folder beserta isinya dapat dipindah, diganti nama, atau dikirim ke Trash.';
   for(const id of ['wsSave','wsRead','wsDictate','wsReload'])$(id).classList.toggle('hidden',!text);
   for(const id of ['wsRename','wsMove','wsDelete'])$(id).classList.toggle('hidden',full.trashed);
   $('wsRestore').classList.toggle('hidden',!full.trashed);this.editorState();
  }
  async save(){
   if(this.busy||!this.selected||!this.dirty)return;
   const chosen={...this.selected},content=$('wsEditor').value;this.busy=true;this.editorState();
   try{const updated=await this.request('/items/'+chosen.id,{method:'PATCH',body:JSON.stringify({revision:chosen.revision,content})});
    if(this.selected?.id===chosen.id){this.selected=updated;this.markDirty();}
    await this.refresh();this.notify('Catatan tersimpan di SONIC Cloud.');
   }finally{this.busy=false;this.editorState();}
  }
  nameDialog(kind){
   if(this.busy||(kind==='rename'&&!this.selected))return;
   this.pending={kind,item:this.selected?{...this.selected}:null,parent:this.parent,id:crypto.randomUUID()};
   $('wsDialogTitle').textContent=kind==='folder'?'Folder baru':kind==='text'?'Catatan baru':'Ganti nama';
   $('wsDialogHint').textContent=kind==='text'?'Gunakan .txt atau .md. Catatan tersimpan di SONIC Cloud.':'Satu nama dalam folder yang dipilih.';
   $('wsNameLabel').classList.remove('hidden');$('wsMoveLabel').classList.add('hidden');$('wsName').required=true;
   $('wsName').value=kind==='rename'?this.selected.name:kind==='text'?'Catatan baru.md':'';
   $('wsDialogSubmit').textContent='Simpan';$('wsDialogError').textContent='';$('wsDialog').showModal();$('wsName').focus();$('wsName').select();
  }
  moveDialog(){
   if(!this.selected||this.busy)return;this.pending={kind:'move',item:{...this.selected}};
   $('wsDialogTitle').textContent='Pindahkan '+this.selected.name;$('wsDialogHint').textContent='Pilih folder tujuan di SONIC Cloud.';
   $('wsNameLabel').classList.add('hidden');$('wsName').required=false;$('wsMoveLabel').classList.remove('hidden');$('wsMoveTarget').replaceChildren();
   for(const f of [{id:'root',name:'SONIC Cloud'},...this.folders]){if(f.id===this.selected.id)continue;const option=node('option','',f.id==='root'?f.name:this.folderPath(f.id));option.value=f.id;option.selected=f.id===this.selected.parent_id;$('wsMoveTarget').append(option);}
   $('wsDialogSubmit').textContent='Pindahkan';$('wsDialogError').textContent='';$('wsDialog').showModal();
  }
  reviewDelete(){
   if(!this.selected||this.busy)return;this.pending={kind:'trash',item:{...this.selected}};
   $('wsDialogTitle').textContent='Pindahkan ke Trash?';$('wsDialogHint').textContent=this.selected.name+(this.selected.kind==='folder'?' beserta seluruh isinya':'')+'. Bisa dipulihkan dari Trash.';
   $('wsNameLabel').classList.add('hidden');$('wsMoveLabel').classList.add('hidden');$('wsName').required=false;
   $('wsDialogSubmit').textContent='Ke Trash';$('wsDialogError').textContent='';$('wsDialog').showModal();
  }
  cancelDialog(){if(this.busy)return;this.pending=null;$('wsDialog').close();}
  async submitDialog(){
   if(this.busy||!this.pending)return;
   const p=this.pending;this.busy=true;$('wsDialogSubmit').disabled=true;$('wsDialogCancel').disabled=true;$('wsDialogError').textContent='';
   try{
    let result;
    if(p.kind==='trash'){
     if(this.selected?.id!==p.item.id||this.selected?.revision!==p.item.revision)throw Error('Pilihan berubah. Tinjau item lagi.');
     await this.request('/items/'+p.item.id+'?revision='+p.item.revision,{method:'DELETE'});this.closePreview();
    }else if(p.kind==='move'||p.kind==='rename'){
     result=await this.request('/items/'+p.item.id,{method:'PATCH',body:JSON.stringify({revision:p.item.revision,...(p.kind==='move'?{parent_id:$('wsMoveTarget').value}:{name:$('wsName').value})})});
     if(this.selected?.id===p.item.id){this.selected={...result};$('wsPreviewName').textContent=result.name;this.editorState();}
    }else{
     result=await this.request('/items',{method:'POST',body:JSON.stringify({id:p.id,parent_id:p.parent,name:$('wsName').value,kind:p.kind})});
    }
    this.pending=null;$('wsDialog').close();await this.refresh();
    if(result?.item?.kind==='text'){this.busy=false;await this.select(result.item);}
   }catch(e){$('wsDialogError').textContent=e.message;throw e;}
   finally{this.busy=false;$('wsDialogSubmit').disabled=false;$('wsDialogCancel').disabled=false;this.editorState();}
  }
  async restore(){
   if(this.busy||!this.selected?.trashed)return;const chosen={...this.selected};this.busy=true;
   try{await this.request('/items/'+chosen.id+'/restore',{method:'POST',body:JSON.stringify({revision:chosen.revision})});this.closePreview();await this.refresh();this.notify('Item dipulihkan ke folder asal.');}
   finally{this.busy=false;}
  }
  dictate(){
   if(this.recognition){this.recognition.stop();return;}
   if(window.sonicRealtimeActive){this.notify('Gunakan perintah “tambahkan ke catatan …” pada sesi suara aktif.');return;}
   const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
   if(!Recognition){this.notify('Dikte browser belum tersedia. Gunakan double tap SONIC dan perintah catatan.');return;}
   if(!this.selected||this.selected.kind!=='text')return;
   const id=this.selected.id,r=this.recognition=new Recognition();r.lang='id-ID';r.continuous=false;r.interimResults=false;
   $('wsDictate').textContent='Stop dikte';
   r.onresult=e=>{if(this.selected?.id!==id)return;const text=Array.from(e.results).filter(x=>x.isFinal).map(x=>x[0].transcript).join(' ');$('wsEditor').value+=($('wsEditor').value?'\n':'')+text;this.markDirty();};
   r.onerror=()=>this.notify('Dikte berhenti. Periksa izin mikrofon browser.');r.onend=()=>{if(this.recognition===r)this.recognition=null;$('wsDictate').textContent='Dikte';};
   try{r.start();}catch(e){this.recognition=null;$('wsDictate').textContent='Dikte';this.notify(e.message);}
  }
  captureContext(){return {parent:this.parent,id:this.selected?.id||null,revision:this.selected?.revision||null,visible:this.visible};}
  async handleVoice(raw,context=this.captureContext()){
   const text=String(raw).trim().replace(/^(?:sonic[,!]?\s+)?(?:tolong\s+)?/i,''),say=reply=>({handled:true,reply});
   if(/^buka (?:workspace|ruang kerja)(?: sonic)?[.!]?$/i.test(text)){this.open();await this.refresh();return say('Workspace SONIC Cloud terbuka.');}
   if(!this.visible)return {handled:false};
   // Explicit PC/Drive destinations keep their existing executor route.
   if(/\b(?:di|ke|pada)\s+(?:desktop|pc|windows|tradevicepc|google drive)\b/i.test(text))return {handled:false};
   const isWorkspace=/^(?:cari (?:file|folder|catatan)|buat (?:folder|catatan)|simpan catatan|bacakan catatan|tambahkan ke catatan|hapus (?:file|folder|catatan) ini)/i.test(text)||(this.pending?.kind==='trash'&&/^(?:setuju|batal)[.!]?$/i.test(text));
   if(isWorkspace&&(!context||!context.visible||context.parent!==this.parent||context.id!==(this.selected?.id||null)||context.revision!==(this.selected?.revision||null)))return say('Pilihan workspace berubah sejak mulai berbicara. Pilih file lalu ulangi perintah.');
   if(isWorkspace&&this.busy)return say('Workspace masih menyimpan perubahan. Tunggu hasilnya sebelum perintah berikutnya.');
   if(this.pending?.kind==='trash'&&/^(?:setuju|batal)[.!]?$/i.test(text)){
    if(/^batal/i.test(text)){this.cancelDialog();return say('Penghapusan dibatalkan.');}
    await this.submitDialog();return say('Item dipindahkan ke Trash SONIC Cloud.');
   }
   let match;
   if((match=text.match(/^cari (?:file|folder|catatan)\s+(.+)$/i))){$('wsSearch').value=match[1].replace(/[.!]$/,'');await this.refresh();return say('Pencarian nama menampilkan '+this.rows.length+' hasil.');}
   if((match=text.match(/^buat (folder|catatan)\s+(.+?)(?:\s+di workspace(?: sonic)?)?[.!]?$/i))){
    if(this.trash)return say('Buka folder SONIC Cloud sebelum membuat item.');
    if(this.dirty)return say('Simpan catatan saat ini sebelum membuat item baru.');
    const kind=match[1].toLowerCase()==='folder'?'folder':'text',name=match[2]+(kind==='text'&&!/\.(txt|md)$/i.test(match[2])?'.md':'');
    const result=await this.request('/items',{method:'POST',body:JSON.stringify({id:crypto.randomUUID(),parent_id:this.parent,name,kind})});await this.refresh();
    if(kind==='text')await this.select(result.item);return say((kind==='folder'?'Folder ':'Catatan ')+name+' dibuat di SONIC Cloud.');
   }
   if(/^simpan catatan[.!]?$/i.test(text)){if(!this.selected||this.selected.kind!=='text'||this.selected.trashed)return say('Pilih catatan aktif yang akan disimpan.');await this.save();return say('Catatan tersimpan di SONIC Cloud.');}
   if(/^bacakan catatan(?: ini)?[.!]?$/i.test(text)){if(!this.selected||this.selected.kind!=='text'||this.selected.trashed)return say('Pilih catatan aktif yang ingin dibacakan.');return say($('wsEditor').value.slice(0,1100)||'Catatan ini kosong.');}
   if((match=text.match(/^tambahkan ke catatan\s+([\s\S]+)$/i))){if(!this.selected||this.selected.kind!=='text'||this.selected.trashed)return say('Pilih catatan yang akan ditulis.');$('wsEditor').value+=($('wsEditor').value?'\n':'')+match[1];this.markDirty();return say('Teks ditambahkan ke draf. Ucapkan simpan catatan untuk menyimpan.');}
   if(/^hapus (?:file|folder|catatan) ini[.!]?$/i.test(text)){if(!this.selected)return say('Pilih item yang akan dipindahkan ke Trash.');this.reviewDelete();return say('Tinjau '+this.selected.name+'. Ucapkan setuju untuk memindahkan ke Trash, atau batal.');}
   return {handled:false};
  }
 }
 window.SonicWorkspace=SonicWorkspace;
})();
