(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const tabs={brain:'brainPanel',chat:'chatPanel',memory:'memoryPanel',devices:'devicesPanel',setup:'setupPanel'};
  const titles={brain:'Neural Brain',chat:'Command Center',memory:'Memory Vault',devices:'Device Hub',setup:'SONIC Setup'};
  const categoryNames={system:'System',memory:'Memories',topic:'Topics',tool:'Tools',device:'Devices'};
  let csrf=null,currentTab='brain',waiting=false,voiceOn=false,speech=null,brainConfigured=false,toastTimer;
  let graphData={nodes:[],edges:[],counts:{categories:{},memories:0}},graphFingerprint='',activity='idle';
  const filters=new Set(Object.keys(categoryNames));
  const graph=new window.SonicGraph($('graphStage'),{
    onSelect:(node,path)=>{renderInspector(node,path);if(node&&innerWidth<=650)toggleInspector(true);},
    onRender:info=>{$('graphEngine').textContent=info.engine+' / '+info.nodes+' visible';}
  });
  // Useful for local browser QA, contains only the already-authorized graph, no tokens.
  window.sonicGraph=graph;

  function el(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;}
  function button(label,fn,className='small-button'){const b=el('button',className,label);b.type='button';b.addEventListener('click',fn);return b;}
  function dot(category){const d=el('i','node-dot');d.style.setProperty('--dot',window.SonicGraph.palette[category]||'#8293a5');return d;}
  function notify(message){clearTimeout(toastTimer);$('notice').textContent=String(message);$('notice').classList.remove('hidden');toastTimer=setTimeout(()=>$('notice').classList.add('hidden'),7000);}
  function activityState(next){activity=next;$('assistantCore').dataset.state=next;$('activityLabel').textContent=({idle:'READY',thinking:'THINKING',saving:'SAVED',listening:'LISTENING',speaking:'SPEAKING',error:'UNAVAILABLE'})[next]||'READY';}
  function clearPrivateUI(){
    graph.setVisible(false);graph.nodes=[];graph.edges=[];graph.lookup.clear();graph.positions.clear();graph.projected?.clear();graph.selected=null;graph.path=[];graph.highlight=null;graph.initialized=false;
    graph.ctx.clearRect(0,0,graph.width,graph.height);if(graph.gl)graph.gl.clear(graph.gl.COLOR_BUFFER_BIT);graph.tooltip.classList.add('hidden');
    graphData={nodes:[],edges:[],counts:{categories:{},memories:0}};graphFingerprint='';$('chatFeed').replaceChildren();$('memoryList').replaceChildren();$('brainAnswerText').textContent='';$('brainReceipt').replaceChildren();$('brainAnswer').classList.add('hidden');renderInspector(null);$('searchResults').replaceChildren();$('topHubs').replaceChildren();
  }
  async function API(path,opts={}){
    const headers={'Content-Type':'application/json',...(opts.headers||{})};if(csrf&&opts.method&&opts.method!=='GET')headers['X-Sonic-CSRF']=csrf;
    const response=await fetch(path,{credentials:'same-origin',...opts,headers});
    const body=await response.json().catch(()=>({}));
    if(response.status===401&&path!=='/api/login'){csrf=null;clearPrivateUI();$('loginOverlay').classList.remove('hidden');}
    if(!response.ok){const detail=body.detail||body.error;throw Error(typeof detail==='string'?detail:'Request failed (HTTP '+response.status+')');}
    return body;
  }
  function setTab(tab){if(!tabs[tab])return;currentTab=tab;for(const [name,id] of Object.entries(tabs))$(id).classList.toggle('hidden',name!==tab);
    document.querySelectorAll('.nav').forEach(b=>{const yes=b.dataset.tab===tab;b.classList.toggle('active',yes);b.setAttribute('aria-current',yes?'page':'false');});
    $('pageTitle').textContent=titles[tab];graph.setVisible(tab==='brain'&&!!csrf);
    if(!csrf)return;if(tab==='brain')refreshGraph();if(tab==='memory')loadMemory();if(tab==='devices')loadDevice();if(tab==='setup')loadSetup();
  }
  function toggleInspector(open){$('graphInspector').classList.toggle('open',open);$('toggleInspector').setAttribute('aria-expanded',String(open));if(open){$('graphFilters').classList.remove('open');}}
  function toggleFilters(open){$('graphFilters').classList.toggle('open',open);$('toggleFilters').setAttribute('aria-expanded',String(open));if(open)toggleInspector(false);}
  function chooseNode(id,focus=true){const node=graph.lookup.get(id);if(!node)return;if(!filters.has(node.category)){filters.add(node.category);graph.setFilters(filters);renderFilters();}graph.select(id,{focus});}
  async function refreshGraph(){
    if(!csrf)return;
    try{
      const data=await API('/api/knowledge/graph');if(!csrf)return;graphData=data;
      const fingerprint=JSON.stringify({nodes:data.nodes.map(n=>[n.id,n.label,n.degree,n.state]),edges:data.edges.map(e=>[e.id,e.label])});
      if(fingerprint!==graphFingerprint){graph.setData(data);graphFingerprint=fingerprint;}
      $('graphCounts').textContent=data.counts.memories+' memories / '+data.counts.nodes+' nodes / '+data.counts.edges+' links';
      $('graphEmpty').classList.toggle('hidden',data.counts.memories!==0);
      $('graphLimit').textContent=data.truncated?'Tampilan dibatasi '+data.counts.displayed_memories+' catatan / '+data.limits.topics+' topik.':'';
      renderFilters();renderHubs();renderSearch();renderInspector(graph.lookup.get(graph.selected)||null,graph.path);
    }catch(error){notify('Graph belum dapat dimuat: '+error.message);}
  }
  function renderFilters(){const host=$('filterList');host.replaceChildren();
    for(const [type,name] of Object.entries(categoryNames)){const count=graphData.counts.categories[type]||0;
      const label=el('label','filter-row');const check=el('input');check.type='checkbox';check.checked=filters.has(type);check.setAttribute('aria-label','Filter '+name);
      check.addEventListener('change',()=>{check.checked?filters.add(type):filters.delete(type);graph.setFilters(filters);});
      label.append(check,dot(type),el('span','filter-name',name),el('span','count',String(count)));host.append(label);
    }
  }
  function nodeButton(n){const b=button('',()=>chooseNode(n.id),'hub-button');b.append(dot(n.category),el('span','',n.label),el('b','',String(n.degree)));b.title=n.label;return b;}
  function renderHubs(){$('topHubs').replaceChildren(...[...graphData.nodes].sort((a,b)=>b.degree-a.degree||a.label.localeCompare(b.label)).slice(0,7).map(nodeButton));}
  function renderSearch(){const q=$('graphSearch').value.trim().toLocaleLowerCase(),host=$('searchResults');host.replaceChildren();if(!q)return;
    const matches=graphData.nodes.filter(n=>(n.label+' '+n.detail).toLocaleLowerCase().includes(q));
    if(!matches.length){host.append(el('p','search-empty','Tidak ada node yang cocok.'));return;}
    host.append(...matches.slice(0,12).map(nodeButton));if(matches.length>12)host.append(el('p','search-empty','Menampilkan 12 dari '+matches.length+' hasil.'));
  }
  function renderInspector(node,path=[]){const host=$('nodeInspector');host.replaceChildren();
    if(!node){host.append(el('p','','Pilih sebuah node untuk melihat isi, sumber, dan koneksinya.'));return;}
    host.append(el('span','node-kind',categoryNames[node.category]+' / '+node.degree+' connections'),el('h3','',node.label),el('p','',node.detail));
    let source='Source: '+node.source;if(node.source_message_id)source+=' / chat #'+node.source_message_id;if(node.created_at)source+=' / '+new Date(node.created_at).toLocaleString('id-ID');
    host.append(el('p','source-line',source));
    if(node.state==='derived')host.append(el('p','small-note','Indeks kata, bukan fakta baru hasil inferensi AI.'));
    if(node.category==='tool')host.append(el('p','small-note','Tool terdaftar, bukan bukti akun eksternal sudah terhubung.'));
    if(node.category==='device')host.append(el('p','small-note','Status: '+node.state));
    if(path.length)host.append(el('p','trace-note','Path: '+path.map(id=>graph.lookup.get(id)?.label||id).join(' > ')));
    const actions=el('div','node-actions');actions.append(button('Focus',()=>graph.select(node.id,{focus:true})),button('Trace path',()=>{graph.traceArmed=true;toggleInspector(false);notify('Pilih node kedua untuk menelusuri jalur.');}));
    if(node.category==='memory')actions.append(button('Connect note',()=>renderLinkForm(node,host)));
    host.append(actions);
    const relations=graphData.edges.filter(e=>e.kind==='owner_link'&&(e.source===node.id||e.target===node.id));
    for(const e of relations){const other=graph.lookup.get(e.source===node.id?e.target:e.source),row=el('div','saved-link');
      row.append(el('span','',e.label+' / '+(other?.label||'')),button('Remove',async()=>{if(!confirm('Hapus hubungan ini? Catatan tetap tersimpan.'))return;try{await API('/api/knowledge/links/'+e.link_id,{method:'DELETE'});await refreshGraph();}catch(error){notify(error.message);}},'plain'));host.append(row);}
  }
  function renderLinkForm(node,host){host.querySelector('.link-form')?.remove();const others=graphData.nodes.filter(n=>n.category==='memory'&&n.id!==node.id);
    if(!others.length){notify('Simpan minimal dua catatan untuk membuat hubungan.');return;}
    const form=el('form','link-form'),select=el('select');select.required=true;select.setAttribute('aria-label','Target memory');
    for(const n of others){const option=el('option','',n.label);option.value=String(n.memory_id);select.append(option);}
    const labelInput=el('input');labelInput.type='text';labelInput.maxLength=80;labelInput.value='related to';labelInput.required=true;labelInput.setAttribute('aria-label','Relation label');
    const consent=el('label'),check=el('input');check.type='checkbox';check.required=true;consent.append(check,document.createTextNode(' Saya konfirmasi hubungan ini.'));
    const submit=el('button','small-button','Save relation');submit.type='submit';form.append(select,labelInput,consent,submit);
    form.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;try{const result=await API('/api/knowledge/links',{method:'POST',body:JSON.stringify({source_id:node.memory_id,target_id:Number(select.value),label:labelInput.value})});notify(result.created?'Hubungan tersimpan.':'Hubungan ini sudah tersimpan.');await refreshGraph();}catch(error){notify(error.message);}finally{submit.disabled=false;}});host.append(form);
  }
  function line(role,content,error=false){$('hero')?.remove();const wrapper=el('div','message '+role+(error?' error':''));wrapper.append(el('span','speaker',role==='user'?'YOU':'SONIC'),el('div','body',content));$('chatFeed').append(wrapper);$('chatFeed').scrollTop=$('chatFeed').scrollHeight;return wrapper;}
  function appendReceipt(host,event){if(!event?.saved||!Number.isInteger(event.memory_id))return;
    const b=button('',async()=>{setTab('brain');await refreshGraph();chooseNode(event.node_id);},'receipt');
    b.append(el('span','',event.created?'Saved to Memory Vault':'Already in Memory Vault'),el('span','receipt-detail','#'+event.memory_id+' / View node'));host.append(b);
  }
  function brainAnswer(text,error=false,events=[]){$('brainAnswer').classList.remove('hidden');$('brainAnswer').classList.toggle('error',error);$('brainAnswerText').textContent=text;$('brainReceipt').replaceChildren();events.forEach(e=>appendReceipt($('brainReceipt'),e));}
  function setWaiting(value){waiting=value;$('send').disabled=value;$('brainSend').disabled=value;}
  async function send(source){const input=$(source==='brain'?'brainMessage':'message'),text=input.value.trim();if(!text||waiting)return;
    setWaiting(true);speech?.stop();window.speechSynthesis?.cancel();activityState('thinking');input.value='';line('user',text);const pending=line('assistant','SONIC is thinking...');brainAnswer('SONIC is thinking...');
    try{const r=await API('/api/chat',{method:'POST',body:JSON.stringify({message:text})});pending.querySelector('.body').textContent=r.reply;const events=r.memory_events||[];
      events.forEach(e=>appendReceipt(pending,e));brainAnswer(r.reply,false,events);activityState('idle');
      if(events.some(e=>e.saved)){await refreshGraph();if(currentTab==='memory')await loadMemory();const last=events.at(-1);if(last?.node_id&&graph.lookup.has(last.node_id)){graph.select(last.node_id);if(innerWidth<=650)toggleInspector(false);}}
      speak(r.reply);
    }catch(error){pending.classList.add('error');pending.querySelector('.body').textContent=error.message;brainAnswer(error.message,true);activityState('error');}
    finally{setWaiting(false);if(innerWidth>650&&currentTab!=='brain')input.focus();}
  }
  async function loadHistory(){try{const r=await API('/api/history');if(!csrf)return;if(r.messages.length){$('chatFeed').replaceChildren();r.messages.forEach(m=>line(m.role,m.content));const last=[...r.messages].reverse().find(m=>m.role==='assistant');if(last)brainAnswer(last.content);}}catch(error){notify(error.message);}}
  async function loadMemory(){const list=$('memoryList');try{const r=await API('/api/memories?limit=500');if(!csrf)return;list.replaceChildren();$('memoryTotal').textContent=String(r.total);$('memoryStatus').textContent=r.has_more?'Menampilkan 500 catatan terbaru dari '+r.total+'.':'';
      if(!r.memories.length){list.append(el('p','empty-list','Belum ada memory tersimpan. Tambahkan catatan di atas atau tulis "SONIC, ingat bahwa ..." di chat.'));return;}
      for(const m of r.memories){const item=el('div','memory-item'),copy=el('div'),actions=el('div','memory-actions');item.dataset.memoryId=String(m.id);
        copy.append(el('div','memory-text',m.text),el('span','metadata','#'+m.id+' / '+m.source+' / '+new Date(m.created_at).toLocaleDateString('id-ID')));
        actions.append(button('View node',async()=>{setTab('brain');await refreshGraph();chooseNode(m.node_id);},'view-node'),button('Delete',async()=>{if(!confirm('Hapus memory ini dan hubungan tersimpannya? Riwayat chat tidak dihapus.'))return;try{await API('/api/memories/'+m.id,{method:'DELETE'});await loadMemory();await refreshGraph();}catch(error){notify(error.message);}},'delete-memory'));
        item.append(copy,actions);list.append(item);}
    }catch(error){list.replaceChildren(el('p','empty-list',error.message));}
  }
  async function loadDevice(){try{const d=await API('/api/device/status');$('deviceName').textContent=d.hostname||d.device_id||'TRADEVICEPC';$('deviceDetail').textContent=d.connected?'Last seen '+d.last_seen_seconds_ago+' seconds ago':'Waiting for companion pairing or heartbeat';
      $('deviceBadge').textContent=d.connected?'Online':'Offline';$('devicePill').textContent=d.connected?'PC online':'PC offline';for(const id of ['deviceBadge','devicePill']){$(id).classList.toggle('online',d.connected);$(id).classList.toggle('offline',!d.connected);}$('snapshotDevice').disabled=!d.connected;
    }catch(error){$('deviceDetail').textContent=error.message;$('devicePill').textContent='PC unavailable';$('devicePill').className='pill offline';}}
  async function snapshot(){$('snapshotDevice').disabled=true;try{const job=await API('/api/device/jobs',{method:'POST',body:JSON.stringify({action:'system.status'})});$('deviceResult').textContent='Waiting for Windows companion...';
      for(let i=0;i<40;i++){await new Promise(r=>setTimeout(r,1500));const latest=await API('/api/device/jobs/'+job.id);if(['done','failed'].includes(latest.state)){$('deviceResult').textContent=JSON.stringify(latest.result,null,2);return;}}
      $('deviceResult').textContent='No result received yet. Refresh status before trying again.';
    }catch(error){$('deviceResult').textContent=error.message;}finally{loadDevice();}}
  async function loadSetup(){try{const s=await API('/api/setup/status');brainConfigured=s.provider_key_configured;$('brainPill').textContent=brainConfigured?'Model: '+s.model:'API key required';$('coreModel').textContent=s.model+' / configured';$('testProvider').disabled=!brainConfigured;
      if(!brainConfigured)$('coreModel').textContent='OpenAI not configured';
      const states=[['Owner authentication',s.owner_configured],['Persistent database',s.database_connected],['OpenAI key configured (not a live test)',s.provider_key_configured],['PC credential configured',s.device_credential_configured],['TRADEVICEPC heartbeat',s.device_online]];
      $('setupList').replaceChildren();for(const [label,ready] of states){const row=el('div','memory-item');row.append(el('span','',label),el('strong','',ready?'Ready':'Pending'));$('setupList').append(row);}
    }catch(error){$('setupMessage').textContent=error.message;}}
  async function initialize(){const r=await API('/api/session');$('loginOverlay').classList.toggle('hidden',!!r.authenticated);if(!r.authenticated){csrf=null;graph.setVisible(false);return;}
    csrf=r.csrf;$('coreModel').textContent=r.model;await Promise.all([loadHistory(),loadDevice(),loadSetup(),refreshGraph()]);setTab(brainConfigured?'brain':'setup');
  }
  async function signOut(){try{await API('/api/logout',{method:'POST'});}catch(error){notify('Sign out gagal: '+error.message);return;}
    csrf=null;speech?.stop();window.speechSynthesis?.cancel();clearPrivateUI();location.reload();}
  function speak(text){if(!voiceOn||!window.speechSynthesis)return;window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text.slice(0,1600));utterance.lang='id-ID';utterance.rate=1.02;
    utterance.onstart=()=>activityState('speaking');utterance.onend=()=>activityState(waiting?'thinking':'idle');utterance.onerror=()=>activityState(waiting?'thinking':'idle');window.speechSynthesis.speak(utterance);}
  function toggleVoice(){voiceOn=!voiceOn;document.querySelectorAll('.voice-control').forEach(b=>{b.classList.toggle('on',voiceOn);b.setAttribute('aria-pressed',String(voiceOn));b.querySelector('span').textContent=voiceOn?'Voice on':'Voice off';});if(!voiceOn){window.speechSynthesis?.cancel();activityState(waiting?'thinking':'idle');}}
  function startMic(){const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){notify('Voice input belum tersedia di browser ini. Gunakan keyboard.');return;}
    if(speech){speech.stop();return;}const r=new Recognition();r.lang='id-ID';r.interimResults=false;
    r.onstart=()=>{activityState('listening');document.querySelectorAll('.mic-control').forEach(b=>b.classList.add('on'));};
    r.onresult=e=>{const input=$(currentTab==='brain'?'brainMessage':'message');input.value=e.results[0][0].transcript;input.focus();};
    r.onerror=()=>notify('Mikrofon tidak tersedia atau izin ditolak.');r.onend=()=>{speech=null;document.querySelectorAll('.mic-control').forEach(b=>b.classList.remove('on'));activityState(waiting?'thinking':'idle');};speech=r;r.start();
  }
  async function sendVision(dataUrl,kind){if(waiting){notify('SONIC masih memproses permintaan sebelumnya.');return;}if(!brainConfigured){setTab('setup');notify('OpenAI belum dikonfigurasi.');return;}
    const [header,base64]=dataUrl.split(',',2),mimeType=header.match(/^data:(image\/(?:png|jpeg|webp));base64$/)?.[1];if(!mimeType||!base64){notify('Format gambar tidak didukung.');return;}
    const input=$(currentTab==='brain'?'brainMessage':'message'),question=input.value.trim().slice(0,500)||'Jelaskan apa yang terlihat pada gambar ini.';input.value='';line('user','['+kind+'] '+question);const p=line('assistant','SONIC is analyzing the image...');brainAnswer('SONIC is analyzing the image...');setWaiting(true);activityState('thinking');
    try{const r=await API('/api/vision',{method:'POST',body:JSON.stringify({mimeType,base64,question})});p.querySelector('.body').textContent=r.reply;brainAnswer(r.reply);activityState('idle');speak(r.reply);}
    catch(error){p.classList.add('error');p.querySelector('.body').textContent=error.message;brainAnswer(error.message,true);activityState('error');}finally{setWaiting(false);}}
  async function captureOnce(kind){if(waiting)return;if(!brainConfigured){setTab('setup');return;}const screen=kind==='Screen';
    if(!confirm('Kirim satu frame '+(screen?'layar':'kamera')+' ke OpenAI untuk dianalisis? Tidak ada rekaman terus-menerus.'))return;let stream;
    try{stream=screen?await navigator.mediaDevices.getDisplayMedia({video:true,audio:false}):await navigator.mediaDevices.getUserMedia({video:true,audio:false});
      const video=document.createElement('video');video.muted=true;video.playsInline=true;video.srcObject=stream;await video.play();await new Promise(r=>setTimeout(r,350));if(!video.videoWidth)throw Error('No video frame');
      const canvas=document.createElement('canvas');canvas.width=Math.min(1280,video.videoWidth);canvas.height=Math.round(canvas.width*video.videoHeight/video.videoWidth);canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/jpeg',.76);stream.getTracks().forEach(t=>t.stop());stream=null;await sendVision(data,kind);
    }catch(error){notify('Capture dibatalkan atau tidak tersedia: '+error.message);}finally{stream?.getTracks().forEach(t=>t.stop());}}

  $('loginForm').addEventListener('submit',async e=>{e.preventDefault();$('loginError').textContent='';const token=$('ownerToken').value;$('ownerToken').value='';const submit=e.submitter;submit.disabled=true;
    try{const r=await API('/api/login',{method:'POST',body:JSON.stringify({token})});csrf=r.csrf;await initialize();}catch(error){$('loginError').textContent=error.message;}finally{submit.disabled=false;}});
  for(const id of ['logout','setupLogout'])$(id).addEventListener('click',signOut);
  document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));
  for(const [form,input,source] of [['chatForm','message','chat'],['brainForm','brainMessage','brain']]){$(form).addEventListener('submit',e=>{e.preventDefault();send(source);});$(input).addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send(source);}});}
  $('goToBrain')?.addEventListener('click',()=>setTab('brain'));$('openFullChat').addEventListener('click',()=>setTab('chat'));
  $('memoryForm').addEventListener('submit',async e=>{e.preventDefault();const text=$('memoryInput').value.trim();if(!text)return;const b=e.submitter;b.disabled=true;
    try{const r=await API('/api/memories',{method:'POST',body:JSON.stringify({text})});if(!r.saved)throw Error('No storage receipt');$('memoryInput').value='';await loadMemory();await refreshGraph();notify(r.created?'Memory tersimpan.':'Catatan sudah ada di Memory Vault.');}catch(error){notify(error.message);}finally{b.disabled=false;}});
  $('refreshDevice').addEventListener('click',loadDevice);$('snapshotDevice').addEventListener('click',snapshot);$('refreshSetup').addEventListener('click',loadSetup);
  $('testProvider').addEventListener('click',async()=>{$('testProvider').disabled=true;$('setupMessage').textContent='Testing OpenAI...';try{const r=await API('/api/setup/test-provider',{method:'POST',body:'{}'});$('setupMessage').textContent=r.verified?'OpenAI live test passed. Chat is ready.':'Provider not verified.';}catch(error){$('setupMessage').textContent=error.message;}finally{$('testProvider').disabled=!brainConfigured;}});
  for(const id of ['voice','brainVoice'])$(id).addEventListener('click',toggleVoice);for(const id of ['mic','brainMic'])$(id).addEventListener('click',startMic);
  for(const id of ['camera','brainCamera'])$(id).addEventListener('click',()=>captureOnce('Camera'));for(const id of ['screen','brainScreen'])$(id).addEventListener('click',()=>captureOnce('Screen'));for(const id of ['image','brainImage'])$(id).addEventListener('click',()=>$('imageFile').click());
  $('imageFile').addEventListener('change',e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>3*1024*1024){notify('Ukuran gambar maksimal 3 MB.');return;}if(!['image/jpeg','image/png','image/webp'].includes(file.type)){notify('Gunakan JPG, PNG, atau WebP.');return;}const reader=new FileReader();reader.onerror=()=>notify('Gambar tidak dapat dibaca.');reader.onload=()=>sendVision(String(reader.result),'Image');reader.readAsDataURL(file);});
  if(!navigator.mediaDevices?.getDisplayMedia)document.querySelectorAll('.screen-control').forEach(b=>{b.disabled=true;b.title='Screen capture tidak tersedia. Upload screenshot melalui Image.';});
  $('graphSearch').addEventListener('input',renderSearch);$('fitGraph').addEventListener('click',()=>graph.fit());$('clearFocus').addEventListener('click',()=>graph.clear());$('refreshGraph').addEventListener('click',refreshGraph);
  $('dimensionGraph').addEventListener('click',()=>{graph.setDimension(!graph.is3D);$('dimensionGraph').textContent=graph.is3D?'3D':'2D';$('dimensionGraph').setAttribute('aria-pressed',String(graph.is3D));});
  $('rotateGraph').addEventListener('click',()=>{if(graph.reduced){notify('Orbit otomatis dimatikan karena pengaturan reduced motion.');return;}graph.autoRotate=!graph.autoRotate;$('rotateGraph').textContent=graph.autoRotate?'Orbit on':'Orbit off';$('rotateGraph').setAttribute('aria-pressed',String(graph.autoRotate));graph.invalidate();});
  document.querySelectorAll('[data-depth]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-depth]').forEach(x=>x.classList.toggle('active',x===b));graph.setDepth(Number(b.dataset.depth));}));
  $('toggleInspector').addEventListener('click',()=>toggleInspector(!$('graphInspector').classList.contains('open')));$('closeInspector').addEventListener('click',()=>toggleInspector(false));$('toggleFilters').addEventListener('click',()=>toggleFilters(!$('graphFilters').classList.contains('open')));$('closeFilters').addEventListener('click',()=>toggleFilters(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){toggleInspector(false);toggleFilters(false);}});
  initialize().catch(error=>{$('loginError').textContent=error.message;notify(error.message);});
  setInterval(()=>{if(csrf&&!document.hidden)loadDevice();},30000);
})();
