/* SONIC Artifact Studio v2: owner-only artifacts; browser-only static HTML sandbox. */
(()=>{
"use strict";
const $=id=>document.getElementById(id);
const make=(tag,cls,text)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x;};
const button=(text,fn,cls="as-button")=>{const x=make("button",cls,text);x.type="button";x.addEventListener("click",fn);return x;};
const host=$("sonicArtifactRoot");if(!host)return;
const demo=[
 '<style>body{font:15px system-ui;background:#f4f7fb;color:#172132;padding:25px}main{max-width:480px;margin:auto;background:#fff;padding:26px;border-radius:16px}',
 'label{display:grid;gap:8px;margin:14px 0}input{padding:10px;border:1px solid #abb8c7;border-radius:8px;font:inherit}output{display:block;font-size:26px;font-weight:bold;margin-top:15px}</style>',
 '<main><h2>Kalkulator RAB Interior</h2><p>Demo local browser only; tidak ada akses PC atau jaringan.</p>',
 '<label>Volume (m²)<input id="vol" type="number" min="0" value="120"></label>',
 '<label>Harga satuan (Rp)<input id="price" type="number" min="0" value="275000"></label>',
 '<output id="out"></output></main>',
 '<script>const v=document.getElementById("vol"),p=document.getElementById("price"),o=document.getElementById("out");',
 'function update(){o.textContent="Rp "+((Number(v.value)||0)*(Number(p.value)||0)).toLocaleString("id-ID")}',
 'v.oninput=p.oninput=update;update();</script>'
].join("");
const state={items:[],selection:null,draft:null,content:"",csrf:null,owner:false,filter:"all",historical:false,busy:false,generating:false,generationSeq:0,seq:0,previewSeq:0,epoch:0};
const types={app:"Web App",code:"Source",image:"Image",audio:"Audio",video:"Video",website:"Website"};
const icon={app:"▣",code:"⌘",image:"▧",audio:"♫",video:"▷",website:"◎"};
const size=n=>n>=1048576?(n/1048576).toFixed(1)+" MB":n>=1024?(n/1024).toFixed(1)+" KB":(n||0)+" B";
function inform(message,error=false){const x=$("asNotice");if(x){x.textContent=message;x.classList.toggle("is-error",error)}}
async function session(){
 const r=await fetch("/api/session",{credentials:"same-origin",cache:"no-store"});if(!r.ok)throw Error("Sesi tidak dapat dibaca");
 const d=await r.json();state.owner=d.authenticated===true;state.csrf=state.owner?d.csrf:null;return state.owner;
}
async function api(path,options={}){
 if(!await session())throw Error("Hanya owner yang bisa mengakses Artifact Studio pribadi");
 const r=await fetch("/api/artifacts"+path,{credentials:"same-origin",cache:"no-store",...options,
 headers:{"Content-Type":"application/json",...(options.method?{"X-Sonic-CSRF":state.csrf}:{}),...options.headers}});
 let data={};try{data=await r.json()}catch{}
 if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Artifact API error "+r.status);
 return data;
}
async function codingApi(path,opts={}){
 if(!await session())throw Error("Hanya owner yang dapat menjalankan generator.");
 const response=await fetch("/api/coding"+path,{
  credentials:"same-origin",cache:"no-store",...opts,
  headers:{"Content-Type":"application/json",...(opts.method?{"X-Sonic-CSRF":state.csrf}:{}),...opts.headers}
 });
 let payload={};try{payload=await response.json()}catch{}
 if(!response.ok)throw Error(typeof payload.detail==="string"?payload.detail:"Coding request failed (HTTP "+response.status+")");
 return payload;
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function codingNotice(text,error=false){
 const holder=$("asCodingStatus");
 if(holder){holder.textContent=text;holder.classList.toggle("is-error",error)}
}
function codingEngineChanged(){
 const provider=$("asCodingProvider").value;
 const hint=$("asCodingHint");
 if(provider==="local"){
  hint.textContent="Local GGUF (TRADEVICEPC): draft mini, konteks 1.024 token, respons hingga 384 token. Tidak bisa menjamin aplikasi kompleks.";
 }else if(provider==="deepseek"){
  hint.textContent="DeepSeek Cloud: prompt dan source revisi dikirim ke API DeepSeek. Biaya API mungkin berlaku. Tidak mengubah model Chat.";
 }else{
  hint.textContent="Pilih engine secara sadar. Tidak ada fallback cloud otomatis. Source hanya menjadi draft sebelum disimpan.";
 }
 $("asGenerate").disabled=state.generating||!provider;
}
async function generateCode(){
 if(state.generating)return;
 const provider=$("asCodingProvider").value;
 const prompt=$("asCodingPrompt").value.trim();
 if(!["local","deepseek"].includes(provider))return codingNotice("Pilih engine Local atau DeepSeek Cloud terlebih dahulu.",true);
 if(prompt.length<10)return codingNotice("Jelaskan tool dalam sedikitnya 10 karakter.",true);
 if(provider==="local"&&prompt.length>450)return codingNotice("Local GGUF hanya menerima prompt maksimal 450 karakter. Gunakan DeepSeek Cloud untuk instruksi panjang.",true);
 const revise=$("asCodeRevise").checked;
 const existing=revise?content():"";
 if(revise&&(!current()||current().kind!=="app"))return codingNotice("Pilih terlebih dahulu aplikasi HTML yang ingin direvisi.",true);
 if(provider==="local"&&revise)return codingNotice("Revisi source panjang memerlukan pilihan DeepSeek Cloud.",true);
 if(state.draft&&!confirm("Draft belum disimpan akan diganti setelah generator berhasil. Lanjut?"))return;
 if(provider==="deepseek"&&!confirm("Kirim instruksi"+(revise?" dan source HTML":"")+" ke API DeepSeek? Pilihan Chat tetap. Biaya API mungkin berlaku."))return;
 const initialEpoch=state.epoch;
 const request=++state.generationSeq;
 state.generating=true;codingEngineChanged();
 codingNotice(provider==="local"?"Mengirim satu tugas Local AI ke TRADEVICEPC…":"Meminta kode HTML dari DeepSeek Cloud…");
 try{
  const result=await codingApi("/generate",{method:"POST",body:JSON.stringify({provider,prompt,...(revise?{existing_html:existing}:{})})});
  let finished=result;
  if(result.state==="queued"){
   const start=Date.now();
   while(Date.now()-start<240000){
    if(initialEpoch!==state.epoch||request!==state.generationSeq)return;
    await delay(2300);
    finished=await codingApi("/local/"+encodeURIComponent(result.job_id));
    if(finished.state==="done"||finished.state==="failed")break;
    codingNotice("Local AI "+finished.state+" · "+Math.round((Date.now()-start)/1000)+" detik. Tidak ada kirim ulang.");
   }
   if(finished.state!=="done"&&finished.state!=="failed")throw Error("Tugas masih belum terverifikasi. Jangan mengirim ulang saat pekerjaan masih berjalan.");
  }
  if(initialEpoch!==state.epoch||request!==state.generationSeq)return;
  if(finished.state!=="done"||!finished.html)throw Error(finished.error||"Generasi HTML tidak selesai. Draft sebelumnya tidak berubah.");
  const title=revise?(current()?.name||"Revised HTML Tool"):"Generated HTML Tool";
  newDraft("app",finished.html,"text/html","chat-draft",title);
  show("code");codingNotice("Source lengkap diterima dari "+(provider==="local"?"Local AI":"DeepSeek")+"; periksa, Preview, lalu Save Version.");
  inform("Generated source is a draft; not executed, installed, saved, or deployed.");
 }catch(error){
  codingNotice(error.message||"Coding request failed",true);
 }finally{
  if(request===state.generationSeq){state.generating=false;codingEngineChanged()}
 }
}
function openGenerator(prefill=""){
 open();
 if(prefill)$("asCodingPrompt").value=prefill;
 $("asCodingPrompt").focus();
}
function current(){return state.draft||state.selection}
function content(){return state.draft?state.draft.content:state.content}
function updateMeta(){
 const a=current();$("asTitle").textContent=a?.name||"No artifact selected";
 $("asSubtitle").textContent=a?(types[a.kind]+" · "+(state.draft?"Unsaved draft":"v"+a.version)):"Buat HTML tool, impor file, atau pilih artifact tersimpan.";
 $("asKind").textContent=a?types[a.kind]:"—";
 $("asOrigin").textContent=a?.source==="chat-draft"?"Chat draft / unverified":a?.source==="import"?"Imported file":a?"Owner-created":"—";
 $("asVersion").textContent=a?(state.draft?"Draft":"v"+a.version):"—";
 $("asSize").textContent=a?.size?size(a.size):"—";
 $("asHash").textContent=a?.sha256?a.sha256.slice(0,16)+"…":"Not saved";
 for(const id of ["asPreviewBtn","asExportBtn"])$(id).disabled=!a;
 $("asSaveBtn").disabled=!a||!state.owner||state.historical;
 $("asEditBtn").disabled=!a||!["app","code","website"].includes(a.kind)||state.historical;
 $("asDeleteBtn").disabled=!state.selection||!state.owner;
}
function show(view,approved=false){
 for(const b of host.querySelectorAll("[data-as-tab]"))b.setAttribute("aria-selected",String(b.dataset.asTab===view));
 for(const id of ["asStage","asEditor","asHistory"])$(id).hidden=!(id===({preview:"asStage",code:"asEditor",versions:"asHistory"})[view]);
 if(view==="preview")render(approved);
 if(view==="code")$("asCode").value=content()||"";
 if(view==="versions")history();
}
function sandbox(url){
 const frame=make("iframe","as-iframe");
 frame.title="SONIC isolated HTML preview";
 frame.setAttribute("sandbox","allow-scripts"); // no same-origin, forms, downloads, popups or top navigation
 frame.referrerPolicy="no-referrer";
 frame.src=url;
 return frame;
}
function render(approved=false){
 const token=++state.previewSeq;
 const stage=$("asStage");stage.replaceChildren();const a=current();
 if(!a){stage.append(make("div","as-empty","No artifact selected. Create an HTML tool or import an image, audio or video."));return}
 const text=content();
 if(a.kind==="app"){
  if(!approved){
   const notice=make("div","as-empty","Source HTML tersedia. Tekan Preview untuk menjalankan tool di browser sandbox.");
   const launch=button("▷ Run isolated preview",()=>render(true),"as-button as-primary");
   stage.append(notice,launch);return;
  }
  stage.append(make("p","as-empty","Preparing isolated preview…"));
  api("/previews",{method:"POST",body:JSON.stringify({content:text})}).then(result=>{
   if(token!==state.previewSeq||$("asStage").hidden)return;
   stage.replaceChildren(sandbox(result.url),make("p","as-disclaimer",
      "Preview kedaluwarsa setelah 8 menit. Kode berjalan dengan origin terisolasi tanpa cookie, filesystem, shell atau jaringan."));
  }).catch(err=>{if(token===state.previewSeq){stage.replaceChildren(make("p","as-empty",err.message));inform(err.message,true)}});
 }else if(a.kind==="image"){
  const img=make("img","as-image");img.src=text;img.alt=a.name;stage.append(img);
 }else if(a.kind==="audio"){
  const audio=make("audio","as-audio");audio.controls=true;audio.preload="metadata";audio.src=text;stage.append(audio);
 }else if(a.kind==="video"){
  const video=make("video","as-video");video.controls=true;video.preload="metadata";video.playsInline=true;video.src=text;stage.append(video);
 }else if(a.kind==="website"){
  const box=make("div","as-website");
  box.append(make("span","as-kicker","EXTERNAL WEBSITE"),make("h3",null,a.name),make("code",null,text));
  const l=make("a","as-button as-primary","Open external website ↗");l.target="_blank";l.rel="noopener noreferrer";l.referrerPolicy="no-referrer";
  let valid=false;try{const parsed=new URL(text);valid=parsed.protocol==="https:"&&!parsed.username&&!parsed.password&&!!parsed.hostname}catch{}
  if(valid)l.href=text;else{l.removeAttribute("href");l.textContent="HTTPS URL invalid";l.setAttribute("aria-disabled","true")}
  box.append(l);
  box.append(make("p","as-disclaimer","Website dibuka di tab baru karena banyak situs melarang embedding. Ini bukan remote-browser execution."));
  stage.append(box);
 }else{
  stage.append(make("pre","as-code-preview",text),make("p","as-disclaimer","Source non-HTML tidak dieksekusi."));
 }
}
let workspaceStrip=null;
function renderWorkspaceItems(items){
 if(!workspaceStrip)return;
 const content=workspaceStrip.querySelector(".as-workspace-items");
 if(!content)return;
 content.replaceChildren();
 if(!items.length){content.append(make("p","as-caption","Belum ada artifact tersimpan. Buat di Artifact Studio."));return}
 for(const item of items.slice(0,4)){
  const card=button("",()=>{open();load(item.id)},"as-workspace-entry");
  card.append(make("span","as-entry-icon",icon[item.kind]||"▤"));
  const body=make("span","as-workspace-entry-name");
  body.append(make("strong",null,item.name),make("small",null,types[item.kind]+" · v"+item.version));
  card.append(body);content.append(card);
 }
}
async function refreshWorkspaceArtifacts(){
 if(!workspaceStrip)return;
 const epoch=state.epoch;
 if(!await session()){
  if(epoch===state.epoch){const c=workspaceStrip.querySelector(".as-workspace-items");if(c)c.replaceChildren(make("p","as-caption","Artifact pribadi hanya tersedia untuk owner."))}
  return;
 }
 const data=await api("");
 if(epoch!==state.epoch)return;
 renderWorkspaceItems(data.items);
}
function card(a){
 const b=button("",()=>load(a.id),"as-entry");b.dataset.id=a.id;
 b.append(make("span","as-entry-icon",icon[a.kind]||"▤"));
 const col=make("span","as-entry-text");col.append(make("strong",null,a.name),make("small",null,types[a.kind]+" · v"+a.version+" · "+size(a.size)));b.append(col);
 if(state.selection?.id===a.id)b.classList.add("selected");
 return b;
}
function library(){
 const needle=$("asSearch").value.toLowerCase().trim(),box=$("asLibrary");box.replaceChildren();
 const subset=state.items.filter(a=>(state.filter==="all"||state.filter===a.kind)&&a.name.toLowerCase().includes(needle));
 if(!subset.length){box.append(make("p","as-empty","Belum ada artifact pada filter ini."));return}
 for(const a of subset)box.append(card(a));
}
async function refresh(){
 const epoch=state.epoch;
 if(!await session()){if(epoch===state.epoch){state.items=[];library();updateMeta();inform("Mode publik: artifact owner tidak tersedia.",true)}return}
 const d=await api("");if(epoch!==state.epoch)return;
 state.items=d.items;
 $("asQuota").textContent=d.total+" items · "+size(d.total_bytes)+" / "+size(d.quota_bytes);
 library();updateMeta();
}
async function load(id,rev){
 if(state.draft&&!confirm("Buang draft yang belum tersimpan?"))return;
 const seq=++state.seq,epoch=state.epoch;
 try{
  const d=await api("/"+encodeURIComponent(id)+(rev?"?version="+rev:""));
  if(seq!==state.seq||epoch!==state.epoch)return;
  state.selection={...d};state.content=d.content;state.draft=null;state.historical=d.viewed_version!==d.version;
  updateMeta();library();show("preview");
  inform(state.historical?"Versi lama hanya untuk preview; kembali ke versi aktif sebelum edit.":"Artifact loaded: "+d.name);
 }catch(e){inform(e.message,true)}
}
function history(){
 const box=$("asHistory");box.replaceChildren();const a=state.selection;
 if(!a?.versions?.length){box.append(make("p","as-empty","Save artifact to start version history."));return}
 for(const v of a.versions)box.append(button("v"+v.version+" · "+size(v.size)+" · "+new Date(v.created_at).toLocaleString("id-ID"),()=>load(a.id,v.version),"as-history-btn"));
 if(state.historical)box.append(button("Return to current version",()=>load(a.id),"as-button"));
}
function newDraft(kind="app",text=null,mime="",origin="manual",name="Untitled HTML Tool"){
 state.seq++;state.selection=null;state.content="";state.historical=false;
 state.draft={name,kind,content:text===null?(kind==="app"?demo:""):text,mime:mime||(kind==="app"?"text/html":"text/plain"),source:origin,version:0};
 $("asDraftName").value=name;updateMeta();library();show(kind==="app"?"code":"preview");
 inform("Draft belum disimpan. Tinjau source lalu Preview dan Save Version.");
}
function editing(){
 const a=current();if(!a||state.historical||!["app","code","website"].includes(a.kind))return;
 if(!state.draft)state.draft={...a,content:state.content};
 $("asDraftName").value=state.draft.name;updateMeta();show("code");$("asCode").focus();
}
function syncEditor(){
 if(!$("asEditor").hidden){
  if(!state.draft)state.draft={...state.selection,content:state.content};
  if(state.draft){state.draft.content=$("asCode").value;state.draft.name=$("asDraftName").value.trim()||"Untitled artifact"}
 }
 updateMeta();
}
async function save(){
 if(state.busy||!current()||state.historical)return;
 state.busy=true;$("asSaveBtn").disabled=true;syncEditor();
 try{
  const a=current();
  const payload=state.selection?
    {name:a.name,base_version:state.selection.version,content:a.content}:
    {name:a.name,kind:a.kind,content:a.content,mime:a.mime,source:a.source};
  if(!payload.content)throw Error("Empty artifact cannot be saved");
  const result=await api(state.selection?"/"+state.selection.id:"",{method:state.selection?"PUT":"POST",body:JSON.stringify(payload)});
  state.draft=null;state.selection=null;await refresh();await load(result.id);
  inform("Saved to owner-only SONIC database · v"+result.version);
 }catch(e){inform(e.message,true)}
 finally{state.busy=false;updateMeta()}
}
async function remove(){
 const a=state.selection;if(!a||!confirm("Hapus "+a.name+" dan seluruh versi?"))return;
 try{await api("/"+a.id,{method:"DELETE"});state.selection=null;state.draft=null;state.content="";state.historical=false;await refresh();show("preview");inform("Artifact deleted.");}
 catch(e){inform(e.message,true)}
}
function exportFile(){
 const a=current();if(!a)return;
 if(a.kind==="app"&&!confirm("HTML yang diekspor dapat menjalankan JavaScript di luar sandbox. Export source?"))return;
 const ext={app:".html",code:".txt",image:".png",audio:".mp3",video:".mp4",website:".url"}[a.kind];
 const mime=a.mime||"text/plain";
 let blob;
 if(["image","audio","video"].includes(a.kind)){
  const encoded=content().split(",")[1]||"",bytes=atob(encoded),out=new Uint8Array(bytes.length);
  for(let i=0;i<bytes.length;i++)out[i]=bytes.charCodeAt(i);
  blob=new Blob([out],{type:mime});
 }else blob=new Blob([content()],{type:mime+";charset=utf-8"});
 const filename=(a.name||"artifact").replace(/[^a-z0-9._-]/gi,"_").slice(0,80)+ext;
 const url=URL.createObjectURL(blob),lnk=make("a");lnk.href=url;lnk.download=filename;document.body.append(lnk);lnk.click();lnk.remove();setTimeout(()=>URL.revokeObjectURL(url),300);
 inform("Downloaded source locally; no deployment performed.");
}
async function importFile(file){
 if(!state.owner)throw Error("Owner login required");
 if(file.size>16*1024*1024)throw Error("File lebih dari 16MB memerlukan object storage tahap berikutnya");
 let kind="code",mime=file.type||"text/plain",src="";
 if(file.name.toLowerCase().endsWith(".html")){kind="app";mime="text/html";src=await file.text()}
 else if(/^image\/(png|jpeg|webp)$/.test(mime)){kind="image"}
 else if(/^audio\//.test(mime)){kind="audio";if(mime==="audio/mp3")mime="audio/mpeg";if(mime==="audio/x-wav")mime="audio/wav"}
 else if(/^video\/(mp4|webm)$/.test(mime)){kind="video"}
 else if(/\.(js|css|json|md|txt|py)$/i.test(file.name)){kind="code";mime="text/plain";src=await file.text()}
 else throw Error("Format file tidak didukung");
 if(["image","audio","video"].includes(kind)){
  src=await new Promise((resolve,reject)=>{const reader=new FileReader();
   reader.onload=()=>resolve(String(reader.result).replace(/^data:[^;]+;base64,/,"data:"+mime+";base64,"));
   reader.onerror=reject;reader.readAsDataURL(file)});
 }
 newDraft(kind,src,mime,"import",file.name);
 show("preview");inform("Local preview ready; tekan Save Version untuk menyimpan.");
}
async function draftFromMessage(text){
 if(!await session()){inform("Sign in as owner first.",true);return}
 const ticks=String.fromCharCode(96).repeat(3),input=String(text);
 let start=input.toLowerCase().indexOf(ticks+"html");
 if(start<0)start=input.toLowerCase().indexOf(ticks+"htm");
 let html="";
 if(start>=0){const nl=input.indexOf("\n",start);const end=input.indexOf(ticks,nl+1);if(nl>=0&&end>nl)html=input.slice(nl+1,end)}
 if(!html&&/^\s*(?:<!doctype html|<html[\s>])/i.test(input))html=input;
 if(!html){inform("Source HTML tidak ditemukan pada pesan.",true);return}
 newDraft("app",html,"text/html","chat-draft","Tool from SONIC Chat");open();
 inform("Source dari Chat menjadi draft. Browser sandbox hanya aktif setelah Anda memilih Preview.");
}
function scanChat(){
 const feed=$("chatFeed");if(!feed)return;
 const ticks=String.fromCharCode(96).repeat(3);
 for(const message of feed.querySelectorAll(".message.assistant:not([data-as-artifact-ready])")){
  const text=message.querySelector(".body")?.textContent||"";
  if(text.length<25||text.length>100000)continue;
  if(!text.toLowerCase().includes(ticks+"html")&&!/^\s*(?:<!doctype html|<html[\s>])/i.test(text))continue;
  message.dataset.asArtifactReady="1";
  message.append(button("▣ Open code in Artifact Studio",()=>draftFromMessage(message.querySelector(".body")?.textContent||""),"as-chat-action"));
 }
}
function open(){document.querySelector('.sidebar [data-tab="studio"]')?.click()}
function init(){
 host.innerHTML=[
 '<div class="as-heading"><div><span class="as-kicker">SONIC / GENERATE · PREVIEW · SAVE</span><h2>Artifact Studio <small>Beta 2.0</small></h2>',
 '<p>Preview apps, images, audio, video and website links. Local GGUF creates source text, not executable host commands.</p></div>',
 '<div class="as-heading-actions"><button id="asNewBtn" type="button" class="as-button as-primary">+ New HTML Tool</button>',
 '<label class="as-button as-import">↑ Import File<input id="asFile" type="file" hidden accept=".html,.js,.css,.json,.txt,.md,.py,image/png,image/jpeg,image/webp,audio/*,video/mp4,video/webm"></label></div></div>',
 '<div class="as-steps"><span>1 · Generate / Import</span><span>2 · Review Source</span><span>3 · Browser Sandbox</span><span>4 · Save Version</span><span class="as-muted">5 · Deploy approval (not enabled)</span></div>',
 '<section class="as-coding-card" aria-label="SONIC Coding Studio"><div class="as-coding-head"><div><span class="as-kicker">CODE GENERATOR / OWNER CONTROLLED</span><h3>Generate a working HTML tool</h3><p>Local untuk draft ringkas, DeepSeek untuk aplikasi lengkap. Tidak ada eksekusi PC atau deploy otomatis.</p></div></div>',
 '<div class="as-coding-fields"><label class="as-coding-prompt">Tool request<textarea id="asCodingPrompt" maxlength="1200" rows="2" placeholder="Contoh: buat kalkulator RAB interior dengan volume, harga satuan, subtotal, dan total."></textarea></label>',
 '<div class="as-coding-controls"><label class="as-coding-provider">Generation engine<select id="asCodingProvider"><option value="" selected>Pilih engine…</option><option value="local">Local GGUF · small draft</option><option value="deepseek">DeepSeek Cloud · full HTML</option></select></label>',
 '<label class="as-coding-revise"><input type="checkbox" id="asCodeRevise"> Revise selected HTML</label><button id="asGenerate" type="button" class="as-button as-primary" disabled>✦ Generate</button></div></div>',
 '<p id="asCodingHint" class="as-coding-hint">Pilih engine secara sadar. Tidak ada fallback cloud otomatis. Source hanya menjadi draft sebelum disimpan.</p>',
 '<p id="asCodingStatus" class="as-coding-status" role="status" aria-live="polite">Ready to generate a draft. Preview dan Save merupakan langkah terpisah.</p></section>',
 '<div class="as-controls"><label class="as-search">⌕ <input id="asSearch" type="search" placeholder="Search artifacts…" autocomplete="off"></label>',
 '<div class="as-kind-tabs" id="asKindTabs"><button class="active" data-kind="all">All</button><button data-kind="app">Apps</button>',
 '<button data-kind="image">Images</button><button data-kind="audio">Audio</button><button data-kind="video">Video</button><button data-kind="website">Website</button>',
 '<button data-kind="code">Code</button></div><button id="asUrlBtn" type="button" class="as-button">+ Website URL</button></div>',
 '<div class="as-layout"><aside class="as-sidebar"><div class="as-box-head"><strong>Artifact Library</strong><button id="asRefresh" type="button">↻</button></div>',
 '<span id="asQuota" class="as-caption">Owner login required</span><div id="asLibrary" class="as-library"></div>',
 '<p class="as-caption as-side-note">Source, version dan media disimpan privat. Kode tidak diinstal pada PC.</p></aside>',
 '<section class="as-work"><div class="as-box-head"><div><h3 id="asTitle">No artifact selected</h3><p id="asSubtitle" class="as-caption"></p></div>',
 '<span id="asVersionBadge" class="as-badge">Owner only</span></div>',
 '<div class="as-view-tabs"><button data-as-tab="preview" aria-selected="true">Preview</button><button data-as-tab="code" aria-selected="false">Source / Edit</button>',
 '<button data-as-tab="versions" aria-selected="false">Versions</button></div>',
 '<div id="asStage" class="as-stage"></div>',
 '<div id="asEditor" class="as-editor" hidden><label>Name<input id="asDraftName" maxlength="120" placeholder="Artifact name"></label>',
 '<label>Source code<textarea id="asCode" spellcheck="false" placeholder="Paste HTML/CSS/JS…"></textarea></label>',
 '<p class="as-disclaimer">Source code tidak dijalankan ketika diedit. Gunakan Preview untuk menjalankan HTML di iframe terisolasi.</p></div>',
 '<div id="asHistory" class="as-history" hidden></div>',
 '<div class="as-work-actions"><button id="asPreviewBtn" type="button" class="as-button as-primary">▷ Preview</button>',
 '<button id="asEditBtn" type="button" class="as-button">✎ Edit</button><button id="asSaveBtn" type="button" class="as-button">▤ Save Version</button>',
 '<button id="asExportBtn" type="button" class="as-button">↓ Export</button><button id="asDeleteBtn" type="button" class="as-button as-danger">Delete</button></div></section>',
 '<aside class="as-inspector"><h3>Artifact Details</h3><div class="as-data"><span>Type</span><strong id="asKind">—</strong></div>',
 '<div class="as-data"><span>Origin</span><strong id="asOrigin">—</strong></div>',
 '<div class="as-data"><span>Version</span><strong id="asVersion">—</strong></div>',
 '<div class="as-data"><span>Size</span><strong id="asSize">—</strong></div>',
 '<div class="as-data"><span>Checksum</span><strong id="asHash">—</strong></div>',
 '<div class="as-box"><span class="as-kicker">LOCAL AI PIPELINE</span><strong>Text to browser preview</strong>',
 '<p>Local GGUF menghasilkan HTML dan kode teks. No arbitrary commands, installer, package build atau deploy otomatis.</p>',
 '<button id="asDeviceBtn" type="button" class="as-button">AI Runtime ↗</button></div>',
 '<div class="as-box"><span class="as-kicker">SECURITY</span><p>Iframe tanpa same-origin, filesystem, cookie, shell atau network. File besar membutuhkan object storage lanjutan.</p></div>',
 '</aside></div><p id="asNotice" role="status" aria-live="polite" class="as-notice">Owner login required.</p>'
 ].join("");
 $("asCodingProvider").addEventListener("change",codingEngineChanged);
 $("asGenerate").addEventListener("click",generateCode);
  $("asNewBtn").onclick=()=>newDraft();
 $("asRefresh").onclick=()=>refresh().catch(e=>inform(e.message,true));
 $("asSearch").oninput=library;
 for(const b of $("asKindTabs").querySelectorAll("button"))b.onclick=()=>{state.filter=b.dataset.kind;for(const n of $("asKindTabs").querySelectorAll("button"))n.classList.toggle("active",n===b);library()};
 for(const b of host.querySelectorAll("[data-as-tab]"))b.onclick=()=>show(b.dataset.asTab);
 $("asPreviewBtn").onclick=()=>{syncEditor();show("preview",true);inform("Loading owner-only sandbox preview. No Windows commands are executed.")};
 $("asEditBtn").onclick=editing;
 $("asSaveBtn").onclick=save;
 $("asDeleteBtn").onclick=remove;
 $("asExportBtn").onclick=exportFile;
 $("asCode").oninput=()=>{syncEditor();inform("Unsaved changes. Preview and save explicitly.")};
 $("asDraftName").oninput=syncEditor;
 $("asDeviceBtn").onclick=()=>{document.querySelector('.sidebar [data-tab="devices"]')?.click();document.querySelector('#devicesPanel [data-ia-target="ai"]')?.click()};
 $("asUrlBtn").onclick=()=>{
  if(!state.owner)return inform("Owner login required.",true);
  const raw=prompt("Public HTTPS website URL:","https://");if(raw===null)return;
  try{const url=new URL(raw);if(url.protocol!=="https:")throw Error("HTTPS required");newDraft("website",raw,"text/uri-list","manual",url.hostname);show("preview")}catch{inform("Gunakan URL HTTPS publik.",true)}
 };
 $("asFile").onchange=async e=>{const f=e.target.files?.[0];e.target.value="";if(f)try{await importFile(f)}catch(error){inform(error.message,true)}};
 const chat=$("chatPanel");if(chat){
  const bar=make("div","as-chat-banner");
  bar.append(make("span",null,"▣ Generate → Review → Preview → Save"));
  bar.append(button("✦ Coding Studio",()=>openGenerator(""),"as-button"));
  bar.append(button("Artifact Studio ↗",open,"as-button"));chat.prepend(bar);
 }
 const workspace=$("workspacePanel");
 const ws=workspace?.querySelector(".ws-heading .ws-actions");
 if(ws)ws.prepend(button("▣ Artifacts",open,"as-button"));
 const wsHeading=workspace?.querySelector(".ws-heading");
 if(wsHeading){
  workspaceStrip=make("section","as-workspace-strip");
  const heading=make("div","as-workspace-strip-head");
  heading.append(make("strong",null,"Recent Artifacts"));
  heading.append(button("Open Library ↗",open,"as-button"));
  workspaceStrip.append(heading,make("div","as-workspace-items"));
  wsHeading.after(workspaceStrip);
 }
 const dash=document.querySelector(".sonic-dash-quick");if(dash)dash.append(button("▣ Artifact Studio",open,"as-button"));
 const dev=document.querySelector('#devicesPanel [data-ia-group="ai"]');if(dev){
  const box=make("div","as-device-card");box.append(make("strong",null,"Artifact Pipeline (browser sandbox)"),
   make("p",null,"Local AI creates text. HTML previews do not execute on TRADEVICEPC. Host install/deploy requires a separate authorized workflow."));
  box.append(button("Open Artifact Studio ↗",open,"as-button"));dev.append(box);
 }
 const feed=$("chatFeed");if(feed){new MutationObserver(scanChat).observe(feed,{childList:true,subtree:true,characterData:true});scanChat()}
 window.addEventListener("sonic:tab",e=>{
 if(e.detail?.tab==="studio")refresh().catch(err=>inform(err.message,true));
 if(e.detail?.tab==="workspace")refreshWorkspaceArtifacts().catch(err=>inform(err.message,true));
 });
 const clear=()=>{state.epoch++;state.generationSeq++;state.seq++;state.previewSeq++;state.owner=false;state.csrf=null;state.items=[];state.selection=null;state.draft=null;state.content="";$("asQuota").textContent="Owner login required";renderWorkspaceItems([]);library();updateMeta();render()};
 window.addEventListener("sonic:overview",e=>{if(e.detail?.kind==="clear")clear()});
 window.addEventListener("sonic:logout",clear);
 window.SonicArtifactStudio={open,newDraft,fromChat:draftFromMessage,openGenerator};
 updateMeta();render();
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});else init();
})();