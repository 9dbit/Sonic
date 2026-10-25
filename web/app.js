(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const tabs={brain:'brainPanel',chat:'chatPanel',memory:'memoryPanel',devices:'devicesPanel',setup:'setupPanel'};
  const titles={brain:'Neural Brain',chat:'Command Center',memory:'Memory Vault',devices:'Device Hub',setup:'SONIC Setup'};
  const categoryNames={system:'System',memory:'Memories',topic:'Topics',tool:'Tools',device:'Devices'};
  let csrf=null,currentTab='brain',waiting=false,voiceOn=false,speech=null,brainConfigured=false,toastTimer,liveVoice=null,wake=null,speechAudio=null;
  let graphData={nodes:[],edges:[],counts:{categories:{},memories:0}},graphFingerprint='',activity='idle';
  const filters=new Set(Object.keys(categoryNames));
  const graph=new window.SonicGraph($('graphStage'),{
    onSelect:(node,path)=>{renderInspector(node,path);if(node&&innerWidth<=650)toggleInspector(true);if(node?.category==='device')showDevicePopup().catch(e=>notify(e.message));else if(node)showNodePopup(node);},
    onRender:info=>{$('graphEngine').textContent=info.engine+' / '+info.nodes+' visible';}
  });
  // Useful for local browser QA, contains only the already-authorized graph, no tokens.
  window.sonicGraph=graph;

  function el(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;}
  function button(label,fn,className='small-button'){const b=el('button',className,label);b.type='button';b.addEventListener('click',fn);return b;}
  function dot(category){const d=el('i','node-dot');d.style.setProperty('--dot',window.SonicGraph.palette[category]||'#8293a5');return d;}
  function notify(message){clearTimeout(toastTimer);$('notice').textContent=String(message);$('notice').classList.remove('hidden');toastTimer=setTimeout(()=>$('notice').classList.add('hidden'),7000);}
  function activityState(next){activity=next;window.sonicMotion?.setState(next);$('assistantCore').dataset.state=next;$('activityLabel').textContent=({idle:'READY',thinking:'THINKING',saving:'SAVED',listening:'LISTENING',speaking:'SPEAKING',error:'UNAVAILABLE'})[next]||'READY';}
  function clearPrivateUI(){
    wake?.stop();liveVoice?.stop('session_expired');speechAudio?.pause();$('voiceProposalHost').replaceChildren();
    graph.setVisible(false);graph.nodes=[];graph.edges=[];graph.lookup.clear();graph.positions.clear();graph.projected?.clear();graph.selected=null;graph.path=[];graph.highlight=null;graph.initialized=false;
    graph.ctx.clearRect(0,0,graph.width,graph.height);if(graph.gl)graph.gl.clear(graph.gl.COLOR_BUFFER_BIT);graph.tooltip.classList.add('hidden');
    graphData={nodes:[],edges:[],counts:{categories:{},memories:0}};graphFingerprint='';$('chatFeed').replaceChildren();$('memoryList').replaceChildren();$('brainAnswerText').textContent='';$('brainReceipt').replaceChildren();$('brainAnswer').classList.add('hidden');renderInspector(null);$('searchResults').replaceChildren();$('topHubs').replaceChildren();
  }
  async function API(path,opts={}){
    const headers={'Content-Type':'application/json',...(opts.headers||{})};if(csrf&&opts.method&&opts.method!=='GET')headers['X-Sonic-CSRF']=csrf;
    const response=await fetch(path,{credentials:'same-origin',...opts,headers});
    const body=await response.json().catch(()=>({}));
    if(response.status===401&&path!=='/api/login'){csrf=null;clearPrivateUI();$('loginOverlay').classList.remove('hidden');}
    if(!response.ok){const detail=body.detail||body.error;const error=Error(typeof detail==='string'?detail:'Request failed (HTTP '+response.status+')');error.status=response.status;throw error;}
    return body;
  }
  function setTab(tab){if(!tabs[tab])return;currentTab=tab;for(const [name,id] of Object.entries(tabs))$(id).classList.toggle('hidden',name!==tab);
    document.querySelectorAll('.nav').forEach(b=>{const yes=b.dataset.tab===tab;b.classList.toggle('active',yes);b.setAttribute('aria-current',yes?'page':'false');});
    $('pageTitle').textContent=titles[tab];graph.setVisible(tab==='brain'&&!!csrf);
    if(!csrf)return;if(tab==='brain')refreshGraph();if(tab==='memory')loadMemory();if(tab==='devices')loadDevice();if(tab==='setup'){loadSetup();loadRuns();loadVoiceStatus().catch(e=>{$('voiceReadiness').textContent=e.message;});}
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
      renderFilters();renderHubs();renderSearch();renderInspector(graph.lookup.get(graph.selected)||null,graph.path,{preserveDraft:true});
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
  function renderInspector(node,path=[],{preserveDraft=false}={}){const host=$('nodeInspector');
    const draft=host.querySelector('.link-form');
    if(preserveDraft&&draft&&node&&host.dataset.nodeId===node.id){
      const target='memory:'+draft.querySelector('select').value;
      if(graph.lookup.has(target))return;
      notify('Catatan tujuan tidak tersedia lagi; hubungan tidak disimpan.');
    }
    host.dataset.nodeId=node?.id||'';host.replaceChildren();
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
    form.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;try{const result=await API('/api/knowledge/links',{method:'POST',body:JSON.stringify({source_id:node.memory_id,target_id:Number(select.value),label:labelInput.value})});notify(result.created?'Hubungan tersimpan.':'Hubungan ini sudah tersimpan.');form.remove();await refreshGraph();}catch(error){notify(error.message);}finally{submit.disabled=false;}});host.append(form);
  }
  function line(role,content,error=false){$('hero')?.remove();const wrapper=el('div','message '+role+(error?' error':''));wrapper.append(el('span','speaker',role==='user'?'YOU':'SONIC'),el('div','body',content));$('chatFeed').append(wrapper);$('chatFeed').scrollTop=$('chatFeed').scrollHeight;return wrapper;}
  function appendReceipt(host,event){if(!event?.saved||!Number.isInteger(event.memory_id))return;
    const b=button('',async()=>{setTab('brain');await refreshGraph();chooseNode(event.node_id);},'receipt');
    b.append(el('span','',event.created?'Saved to Memory Vault':'Already in Memory Vault'),el('span','receipt-detail','#'+event.memory_id+' / View node'));host.append(b);
  }
  function brainAnswer(text,error=false,events=[]){$('brainAnswer').classList.remove('hidden');$('brainAnswer').classList.toggle('error',error);$('brainAnswerText').textContent=text;$('brainReceipt').replaceChildren();events.forEach(e=>appendReceipt($('brainReceipt'),e));}
  function setWaiting(value){waiting=value;$('send').disabled=value;$('brainSend').disabled=value;}
  async function send(source,options={}){if(liveVoice?.active){notify('Stop sesi suara sebelum mengirim chat teks.');return;}const input=$(source==='brain'?'brainMessage':'message'),text=input.value.trim();if(!text||waiting)return;
    if(window.sonicMotion?.handleCommand(text)){input.value='';notify('SONIC Motion Core kembali ke posisi semula.');return;}
    setWaiting(true);speech?.stop();window.speechSynthesis?.cancel();activityState('thinking');input.value='';line('user',text);const pending=line('assistant','SONIC is thinking...');brainAnswer('SONIC is thinking...');
    try{const r=await API('/api/chat',{method:'POST',body:JSON.stringify({message:text,selected_node_id:graph.selected||null})});pending.querySelector('.body').textContent=r.reply;const events=r.memory_events||[];
      events.forEach(e=>appendReceipt(pending,e));brainAnswer(r.reply,false,events);activityState('idle');
      if(events.some(e=>e.saved)){await refreshGraph();if(currentTab==='memory')await loadMemory();const last=events.at(-1);if(last?.node_id&&graph.lookup.has(last.node_id)){graph.select(last.node_id);if(innerWidth<=650)toggleInspector(false);}}
      const applied=await applyGraphActions(r.ui_actions||[]);
      renderReferences(pending,r.memory_references||[]);renderReferences($('brainReceipt'),r.memory_references||[]);
      if(r.engine)pending.append(el('span','execution-note','Engine '+r.engine.route+' / '+r.engine.status+(applied.length?' / graph '+applied.map(x=>x.status).join(', '):'')));
      speak(r.reply,{force:!!options.readAloud});
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
  async function loadDevice(){try{
      const [d,telemetry]=await Promise.all([API('/api/device/status'),API('/api/device/metrics')]);
      $('deviceName').textContent=d.hostname||d.device_id||'TRADEVICEPC';
      $('deviceDetail').textContent=d.connected?('Last seen '+d.last_seen_seconds_ago+' seconds ago · '+(telemetry.agent_version?'Agent '+telemetry.agent_version:'Legacy companion')):'Waiting for companion pairing or heartbeat';
      $('deviceBadge').textContent=d.connected?'Online':'Offline';$('devicePill').textContent=d.connected?'PC online':'PC offline';
      for(const id of ['deviceBadge','devicePill']){$(id).classList.toggle('online',d.connected);$(id).classList.toggle('offline',!d.connected);}
      $('snapshotDevice').disabled=!d.connected;
      const m=telemetry.metrics||{},ready=telemetry.metrics_available&&Number.isFinite(m.ram_available_bytes)&&Number.isFinite(m.ram_total_bytes);
      $('telemetryValue').textContent=ready?(m.ram_available_bytes/2**30).toFixed(2)+' / '+(m.ram_total_bytes/2**30).toFixed(2)+' GiB':'Waiting for updated companion';
      $('telemetryFill').style.width=ready?Math.max(0,Math.min(100,100-(100*m.ram_available_bytes/m.ram_total_bytes)))+'%':'0%';
      $('telemetrySource').textContent=ready?('Authenticated Windows telemetry · '+telemetry.metrics_age_seconds+' sec ago'):
        (d.connected?'PC is connected, but legacy companion does not transmit RAM. Upgrade companion from a trusted local Windows session.':telemetry.notice);
      const hint=$('companionUpgradeHint');if(hint){hint.classList.toggle('hidden',ready||!d.connected);}
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
    csrf=r.csrf;$('coreModel').textContent=r.model;await Promise.all([loadHistory(),loadDevice(),loadSetup(),refreshGraph(),window.sonicPersonaStudio?.load().catch(e=>notify('Persona Studio unavailable: '+e.message))]);setTab(brainConfigured?'brain':'setup');
  }
  async function signOut(){await liveVoice?.stop('logout');try{await API('/api/logout',{method:'POST'});}catch(error){notify('Sign out gagal: '+error.message);return;}
    csrf=null;speech?.stop();window.speechSynthesis?.cancel();clearPrivateUI();location.reload();}
  async function speak(text,{force=false}={}){
    if(liveVoice?.active||(!voiceOn&&!force))return;
    speechAudio?.pause();window.speechSynthesis?.cancel();const words=String(text).slice(0,1600);
    if(!words)return;
    activityState('speaking');
    try{
      const response=await fetch('/api/voice/speak',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-Sonic-CSRF':csrf},body:JSON.stringify({text:words,consent:true})});
      if(!response.ok)throw Error('Synthetic voice unavailable');
      const blob=await response.blob(),url=URL.createObjectURL(blob),audio=new Audio(url);
      speechAudio=audio;audio.onended=()=>{URL.revokeObjectURL(url);speechAudio=null;activityState('idle');wake?.resume();};
      audio.onerror=()=>{URL.revokeObjectURL(url);speechAudio=null;activityState('idle');wake?.resume();};
      await audio.play();
    }catch(error){
      // Do not silently switch to a different system voice. That would make
      // the applied SONIC persona sound inconsistent across the application.
      activityState('idle');wake?.resume();notify('Suara persona tidak tersedia: '+error.message);
    }
  }
  function toggleVoice(){voiceOn=!voiceOn;document.querySelectorAll('.voice-control').forEach(b=>{b.classList.toggle('on',voiceOn);b.setAttribute('aria-pressed',String(voiceOn));b.querySelector('span').textContent=voiceOn?'Voice on':'Voice off';});if(!voiceOn){window.speechSynthesis?.cancel();activityState(waiting?'thinking':'idle');}}
  function startMic(){if(liveVoice?.active){notify('Realtime voice sedang aktif. Gunakan Mute atau Stop.');return;}const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){notify('Voice input belum tersedia di browser ini. Gunakan keyboard.');return;}
    if(speech){speech.stop();return;}const r=new Recognition();r.lang='id-ID';r.interimResults=false;
    r.onstart=()=>{activityState('listening');document.querySelectorAll('.mic-control').forEach(b=>b.classList.add('on'));};
    r.onresult=e=>{const input=$(currentTab==='brain'?'brainMessage':'message');input.value=e.results[0][0].transcript;input.focus();};
    r.onerror=()=>notify('Mikrofon tidak tersedia atau izin ditolak.');r.onend=()=>{speech=null;document.querySelectorAll('.mic-control').forEach(b=>b.classList.remove('on'));activityState(waiting?'thinking':'idle');};speech=r;r.start();
  }
  async function sendVision(dataUrl,kind){if(liveVoice?.active){notify('Stop sesi suara sebelum menganalisis gambar.');return;}if(waiting){notify('SONIC masih memproses permintaan sebelumnya.');return;}if(!brainConfigured){setTab('setup');notify('OpenAI belum dikonfigurasi.');return;}
    const [header,base64]=dataUrl.split(',',2),mimeType=header.match(/^data:(image\/(?:png|jpeg|webp));base64$/)?.[1];if(!mimeType||!base64){notify('Format gambar tidak didukung.');return;}
    const input=$(currentTab==='brain'?'brainMessage':'message'),question=input.value.trim().slice(0,500)||'Jelaskan apa yang terlihat pada gambar ini.';input.value='';line('user','['+kind+'] '+question);const p=line('assistant','SONIC is analyzing the image...');brainAnswer('SONIC is analyzing the image...');setWaiting(true);activityState('thinking');
    try{const r=await API('/api/vision',{method:'POST',body:JSON.stringify({mimeType,base64,question})});p.querySelector('.body').textContent=r.reply;brainAnswer(r.reply);activityState('idle');speak(r.reply);}
    catch(error){p.classList.add('error');p.querySelector('.body').textContent=error.message;brainAnswer(error.message,true);activityState('error');}finally{setWaiting(false);}}
  async function captureOnce(kind){if(waiting||liveVoice?.active)return;if(!brainConfigured){setTab('setup');return;}const screen=kind==='Screen';
    if(!confirm('Kirim satu frame '+(screen?'layar':'kamera')+' ke OpenAI untuk dianalisis? Tidak ada rekaman terus-menerus.'))return;let stream;
    try{stream=screen?await navigator.mediaDevices.getDisplayMedia({video:true,audio:false}):await navigator.mediaDevices.getUserMedia({video:true,audio:false});
      const video=document.createElement('video');video.muted=true;video.playsInline=true;video.srcObject=stream;await video.play();await new Promise(r=>setTimeout(r,350));if(!video.videoWidth)throw Error('No video frame');
      const canvas=document.createElement('canvas');canvas.width=Math.min(1280,video.videoWidth);canvas.height=Math.round(canvas.width*video.videoHeight/video.videoWidth);canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/jpeg',.76);stream.getTracks().forEach(t=>t.stop());stream=null;await sendVision(data,kind);
    }catch(error){notify('Capture dibatalkan atau tidak tersedia: '+error.message);}finally{stream?.getTracks().forEach(t=>t.stop());}}

  async function applyGraphActions(actions){
    for(const a of (actions||[]).filter(x=>x?.type==='device.metrics')){await showDevicePopup();}
    return window.applySonicGraphActions((actions||[]).filter(x=>x?.type!=='device.metrics'),{
      graph,refresh:refreshGraph,show:()=>{if(currentTab!=='brain')setTab('brain');},
      enableAll:()=>{for(const type of Object.keys(categoryNames))filters.add(type);graph.setFilters(filters);renderFilters();},
      search:q=>{$('graphSearch').value=q;renderSearch();},showSearch:()=>{if(innerWidth<=650)toggleInspector(true);},
      select:chooseNode,depth:value=>document.querySelectorAll('[data-depth]').forEach(b=>b.classList.toggle('active',Number(b.dataset.depth)===value)),notify
    });
  }
  function renderReferences(host,references){
    const seen=new Set(),box=el('div','memory-references');
    for(const r of references.slice(0,12)){if(!Number.isInteger(r.id)||seen.has(r.id))continue;seen.add(r.id);box.append(button('Memory #'+r.id,async()=>{setTab('brain');await refreshGraph();chooseNode(r.node_id||'memory:'+r.id);},'reference-chip'));}
    if(box.children.length){box.prepend(el('span','small-note','Catatan yang dibaca: '));host.append(box);}
  }
  async function loadRuns(){try{const r=await API('/api/engine/runs');$('engineRuns').replaceChildren();if(!r.runs.length)$('engineRuns').append(el('p','small-note','Belum ada eksekusi pada engine V0.4.'));for(const run of r.runs.slice(0,10)){const row=el('div','engine-run');row.append(el('span','',run.route),el('small','',run.status+' / '+run.duration_ms+' ms'));$('engineRuns').append(row);}}catch(e){$('engineRuns').textContent=e.message;}}
  async function loadVoiceStatus(){const status=await API('/api/voice/status');$('voiceReadiness').textContent=(status.enabled&&status.configured?'Configured, live audio not yet verified. ':'Not enabled. ')+status.model+' / '+status.max_session_seconds+' sec / '+status.sessions_started_today_utc+' of '+status.daily_session_limit+' sessions today (UTC).';return status;}
  async function openVoiceDialog(){
    if(liveVoice.active){$('voiceSessionBar').classList.remove('hidden');return;}
    if(waiting){notify('Tunggu respons chat selesai sebelum memulai suara.');return;}
    $('voiceAgree').checked=false;$('startVoice').disabled=true;$('voiceDialogStatus').textContent='Checking voice configuration...';$('voiceConsent').showModal();
    try{const status=await loadVoiceStatus();$('voiceLimits').textContent='Maksimal '+Math.round(status.max_session_seconds/60)+' menit per sesi, '+status.daily_session_limit+' sesi/hari (UTC). Pemakaian OpenAI API dapat dikenakan biaya.';
      if(status.active_session){$('voiceDialogStatus').textContent='Sesi sebelumnya masih tercatat. Tutup sesi itu sebelum memulai lagi.';const b=button('Close previous session',async()=>{b.disabled=true;try{await API('/api/voice/sessions/'+status.active_session.id+'/stop',{method:'POST',body:'{}'});$('voiceConsent').close();}catch(e){notify(e.message);}finally{b.disabled=false;}});$('voiceDialogStatus').append(b);}
      else{$('startVoice').disabled=!(status.enabled&&status.configured);$('voiceDialogStatus').textContent=status.enabled&&status.configured?'Siap untuk pengujian suara pada perangkat ini.':'Realtime voice belum diaktifkan pada server. Chat dan input suara browser tetap tersedia.';}
    }catch(e){$('voiceDialogStatus').textContent=e.message;}
  }
  function showNodePopup(node){
    if($('voiceProposalHost').children.length)return;
    $('nodePopupTitle').textContent=node.label;
    $('nodePopupText').textContent=node.detail||'No additional description available.';
    $('nodePopupSource').textContent='Source: '+(node.source||'unknown')+' / '+node.degree+' connections';
    $('nodeDetailPopup').classList.remove('hidden');
  }
  async function showDevicePopup(){
    const d=await API('/api/device/metrics');
    const m=d.metrics||{},valid=d.metrics_available&&Number.isFinite(m.ram_available_bytes);
    const format=n=>(n/2**30).toFixed(2)+' GiB';
    $('nodePopupTitle').textContent='TRADEVICEPC / '+(d.connected?'Online':'Offline');
    $('nodePopupText').textContent=valid?('RAM free: '+format(m.ram_available_bytes)+' / RAM total: '+format(m.ram_total_bytes)+'\nRAM used: '+m.ram_used_percent+'%\nTelemetry age: '+d.metrics_age_seconds+' seconds'):d.notice;
    $('nodePopupSource').textContent='Source: authenticated SONIC companion heartbeat; no estimated figures.';
    $('nodeDetailPopup').classList.remove('hidden');
    $('telemetryValue').textContent=valid?(format(m.ram_available_bytes)+' available'):'No fresh reading';
    $('telemetryFill').style.width=valid?Math.max(0,Math.min(100,m.ram_used_percent))+'%':'0%';
    $('telemetrySource').textContent=valid?('Last measurement '+d.metrics_age_seconds+' seconds ago. / '+d.agent_version):d.notice;
    return d;
  }
  function handleVoiceSessionCommand(text){
    const s=text.toLocaleLowerCase().trim();if(window.sonicMotion?.handleCommand(s)){notify('Motion Core kembali ke tempat semula.');return true;}if(!/\bsonic\b/.test(s))return false;
    if(/(?:stop all|berhenti semuanya|matikan semua mikrofon)/.test(s)){wake?.stop();liveVoice.stop('voice_stop_all');notify('All SONIC microphones stopped.');return true;}
    if(/(?:selesai|stop|akhiri sesi|end session)/.test(s)){liveVoice.stop('voice_command');return true;}
    if(/(?:tutup panel|hide panel|minimize|sembunyikan panel)/.test(s)){$('voiceSessionBar').classList.add('compact');notify('Panel diminimalkan. Sesi suara tetap aktif.');return true;}
    if(/(?:buka panel|show panel|expand)/.test(s)){$('voiceSessionBar').classList.remove('compact');return true;}
    return false;
  }
  function updateOperatorForm(){
    const a=$('operatorAction').value;
    $('operatorRecipeWrap').classList.toggle('hidden',a!=='shell.run');
    $('operatorPathWrap').classList.toggle('hidden',a!=='file.read'&&a!=='file.list');
    $('operatorWindowWrap').classList.toggle('hidden',!a.startsWith('mouse.')&&!a.startsWith('keyboard.'));
    $('operatorTextWrap').classList.toggle('hidden',a!=='keyboard.type');
    $('operatorKeyWrap').classList.toggle('hidden',a!=='keyboard.key');
    $('operatorCoordWrap').classList.toggle('hidden',a!=='mouse.click');
  }
  let pendingOperator=null;
  async function proposePCAction(){
    const action=$('operatorAction').value,payload={};
    if(action==='shell.run')payload.recipe=$('operatorRecipe').value;
    if(action==='file.read'||action==='file.list')payload.path=$('operatorPath').value.trim();
    if(action.includes('keyboard')||action.includes('mouse'))payload.window=$('operatorWindow').value.trim();
    if(action==='keyboard.type')payload.text=$('operatorText').value;
    if(action==='keyboard.key')payload.key=$('operatorKey').value;
    if(action==='mouse.click'){payload.x=Number($('operatorX').value);payload.y=Number($('operatorY').value);}
    try{
      pendingOperator=await API('/api/operator/requests',{method:'POST',body:JSON.stringify({action,payload})});
      $('operatorApprovalText').textContent=JSON.stringify({action,payload,expires_at:pendingOperator.expires_at},null,2);
      $('operatorApproval').showModal();
    }catch(e){$('operatorState').textContent=e.message;notify(e.message);}
  }
  async function confirmPCAction(){
    if(!pendingOperator)return;
    const request=pendingOperator;pendingOperator=null;$('operatorApproval').close();
    $('operatorState').textContent='Approved action queued...';
    try{
      await API('/api/operator/requests/'+request.id+'/confirm',{method:'POST',body:JSON.stringify({confirm:true,digest:request.digest})});
      for(let i=0;i<45;i++){
        await new Promise(r=>setTimeout(r,1200));
        const state=await API('/api/operator/requests/'+request.id);
        if(['done','failed','cancelled','expired'].includes(state.state)){
          $('operatorState').textContent='Result: '+state.state;
          $('deviceResult').textContent=JSON.stringify(state.result||state,null,2);return;
        }
      }
      $('operatorState').textContent='Result not yet confirmed; check the action status again before retrying.';
    }catch(e){$('operatorState').textContent='Action not confirmed: '+e.message;}
  }
  async function transcribeAudio(){
    const file=$('referenceAudioFile').files?.[0];
    if(!file){notify('Choose an MP3 or WAV reference first.');return;}
    if(file.size>10*1024*1024){notify('Reference audio must be 10 MB or smaller.');return;}
    if(!confirm('Transcribe this audio using OpenAI? Spoken words will be sent to the provider; SONIC does not save the audio. Music separation is not guaranteed.'))return;
    $('referenceTranscript').textContent='Transcribing speech; background music will be ignored where possible...';
    try{
      const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});
      const base64=String(dataUrl).split(',')[1];
      const result=await API('/api/voice/reference/transcribe',{method:'POST',body:JSON.stringify({mime_type:file.type||'audio/mpeg',audio_base64:base64,consent:true})});
      $('referenceTranscript').textContent='Spoken text: '+result.text+'\nMusic separated: no\nVoice cloned: no';
    }catch(e){$('referenceTranscript').textContent='Transcription failed: '+e.message;}
  }
  function showVoiceProposal(proposal,sessionId){
    $('nodeDetailPopup').classList.add('hidden');
    const host=$('voiceProposalHost');if(host.querySelector('[data-proposal="'+proposal.proposal_id+'"]'))return;
    const card=el('div','voice-proposal glass');card.dataset.proposal=proposal.proposal_id;
    card.append(el('strong','','Review memory'),el('p','',proposal.text),el('small','','Belum tersimpan. Periksa hasil transkripsi sebelum mengonfirmasi.'));
    const controls=el('div','node-actions');
    const save=button('Confirm memory',async()=>{save.disabled=true;reject.disabled=true;try{const receipt=await API('/api/voice/sessions/'+sessionId+'/memories/'+proposal.proposal_id+'/confirm',{method:'POST',body:JSON.stringify({confirm:true})});
      card.replaceChildren(el('strong','','Tersimpan di Memory Vault'));appendReceipt(card,receipt);await refreshGraph();liveVoice.memoryReceipt(receipt);setTimeout(()=>card.remove(),5000);
    }catch(e){notify(e.message);save.disabled=false;reject.disabled=false;}},'small-button');
    const reject=button('Discard',async()=>{try{await API('/api/voice/sessions/'+sessionId+'/memories/'+proposal.proposal_id+'/reject',{method:'POST',body:'{}'});card.remove();}catch(e){notify(e.message);}},'plain');controls.append(save,reject);card.append(controls);host.append(card);
  }
  liveVoice=new window.SonicVoice({api:API,onActions:applyGraphActions,onProposal:showVoiceProposal,onError:notify,
    onState:state=>{window.sonicRealtimeActive=state!=='idle';$('voiceSessionBar').classList.toggle('hidden',state==='idle');$('talkSonic').classList.toggle('active',state!=='idle');$('voiceStateText').textContent=({connecting:'Connecting...',listening:'Listening',thinking:'Thinking',speaking:'Speaking',muted:'Mic muted',idle:'Stopped'})[state]||state;activityState(['listening','thinking','speaking'].includes(state)?state:'idle');$('voiceMute').textContent=liveVoice?.muted?'Unmute':'Mute';$('voiceMute').setAttribute('aria-pressed',String(!!liveVoice?.muted));},
    onConnected:info=>{$('voiceStateText').textContent='Connecting audio';$('coreModel').textContent=info.model+' / realtime';},
    onTranscript:(role,text)=>{if(!text.trim())return;if(role==='user'&&handleVoiceSessionCommand(text))return;const item=line(role,text);item.append(el('small','execution-note','Voice transcript / not automatically saved'));if(role==='assistant')brainAnswer(text);},
    onReferences:refs=>renderReferences($('brainReceipt'),refs),
    onTick:seconds=>{$('voiceCountdown').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');},
    onPlaybackBlocked:()=>{$('voiceResume').classList.remove('hidden');notify('Tekan Enable audio untuk mengizinkan suara pada browser ini.');},
    onPlaybackResumed:()=>$('voiceResume').classList.add('hidden'),
    onStopped:()=>{$('voiceProposalHost').replaceChildren();$('voiceResume').classList.add('hidden');if(csrf)loadSetup();if(wake?.enabled&&!document.hidden)wake.resume();}
  });
  window.addEventListener('sonic:persona-applied',async event=>{
    // Future TTS and text chats already use the saved server persona.
    // Realtime voice output cannot be switched in the middle of a session.
    speechAudio?.pause();speechAudio=null;window.speechSynthesis?.cancel();
    const changed=event.detail?.active,previous=event.detail?.previous;
    if(liveVoice?.active){
      notify('Persona disimpan. Mengakhiri Talk lama agar voice dan style berikutnya sinkron.');
      await liveVoice.stop('persona_changed');
      // Explicit microphone consent remains required. Never silently restart it.
      if(csrf){await openVoiceDialog();$('voiceDialogStatus').textContent='Persona baru aktif. Tekan Start voice untuk memakai pilihan suara dan gaya bahasa baru.';}
    }else if(changed){
      notify('SONIC Persona aktif: '+changed.voice_id+' / '+changed.style+' / '+changed.intensity+'.');
    }
  });
  $('talkSonic').addEventListener('click',openVoiceDialog);$('cancelVoice').addEventListener('click',()=>$('voiceConsent').close());
  $('voiceConsentForm').addEventListener('submit',async e=>{e.preventDefault();if(!$('voiceAgree').checked)return;$('voiceConsent').close();wake?.pause();speech?.stop();window.speechSynthesis?.cancel();try{await liveVoice.start();}catch(error){notify(error.message);}});
  $('voiceStop').addEventListener('click',()=>liveVoice.stop());$('voiceHide').addEventListener('click',()=>{$('voiceSessionBar').classList.toggle('compact');$('voiceHide').textContent=$('voiceSessionBar').classList.contains('compact')?'Expand':'Minimize';});$('voiceMute').addEventListener('click',()=>liveVoice.mute());$('voiceResume').addEventListener('click',()=>liveVoice.resumeAudio().catch(e=>notify(e.message)));
  $('refreshRuns').addEventListener('click',loadRuns);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){if(liveVoice.active)liveVoice.stop('page_hidden');wake?.stop();}});
  window.addEventListener('pagehide',()=>{if(liveVoice.active)liveVoice.stop('page_hidden');wake?.stop();});

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
  const onStandbyState=state=>{const active=wake?.enabled||false;$('wakeToggle').textContent=active?'Standby on':'Standby off';$('wakeToggle').setAttribute('aria-pressed',String(active));$('wakeIndicator').classList.toggle('hidden',!active||state==='paused');$('wakeIndicator').textContent='● SONIC standby / mic active / foreground only';};
  wake=new window.SonicWake({onState:onStandbyState,onError:notify,onWake:async rest=>{
      if(!csrf){wake.stop();return;}
      if(rest){$('brainMessage').value=rest;setTab('brain');await send('brain',{readAloud:true});}
      else{try{await liveVoice.start();}catch(e){notify(e.message);wake.resume();}}
    }});
  $('wakeToggle').addEventListener('click',()=>{if(wake.enabled){wake.stop();return;}
    if(!confirm('Aktifkan standby mikrofon selama tab SONIC terlihat? Browser mungkin memproses transkripsi suara lewat layanan pihak ketiga. Tutup tab atau tekan Standby off untuk menghentikan.'))return;
    try{wake.start();}catch(e){notify(e.message);}
  });
  $('deviceRAM').addEventListener('click',()=>showDevicePopup().catch(e=>notify(e.message)));
  $('nodePopupClose').addEventListener('click',()=>$('nodeDetailPopup').classList.add('hidden'));
  $('nodePopupSpeak').addEventListener('click',()=>speak($('nodePopupText').textContent,{force:true}));
  $('operatorAction').addEventListener('change',updateOperatorForm);
  $('proposeOperator').addEventListener('click',proposePCAction);
  $('operatorCancel').addEventListener('click',()=>{$('operatorApproval').close();});
  $('operatorConfirm').addEventListener('click',confirmPCAction);
  $('testSonicSpeech').addEventListener('click',()=>speak('Welcome back, sir. SONIC is online and ready.',{force:true}));
  $('transcribeReference').addEventListener('click',transcribeAudio);
  updateOperatorForm();
  initialize().catch(error=>{$('loginError').textContent=error.message;notify(error.message);});
  setInterval(()=>{if(csrf&&!document.hidden)loadDevice();},30000);
})();
