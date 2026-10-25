/* SONIC Persona Studio. A preview always reflects the current draft combination;
   Apply persists voice, style and intensity atomically. */
(()=>{'use strict';
 const $=id=>document.getElementById(id);
 const STYLE_LABELS={professional:'Professional',tegas:'Tegas',casual:'Casual',friendly:'Friendly',family:'Family',romantic:'Romantic',humor:'Humor',poetic:'Poetic',robot:'Robot',glitch:'Glitch'};
 const STYLE_DETAILS={professional:'Rapi dan efisien',tegas:'Tegas dan langsung',casual:'Santai dan natural',friendly:'Hangat dan komunikatif',family:'Lembut dan akrab',romantic:'Halus dan penuh perhatian',humor:'Ringan dan cerdas',poetic:'Puitis dan indah',robot:'Presisi dan sistematis',glitch:'Digital dan eksperimental'};
 const EXAMPLES={
  professional:'Selamat datang kembali. Saya SONIC, siap membantu merencanakan pekerjaan Anda secara efisien.',
  tegas:'Selamat datang kembali. Sistem siap. Sebutkan prioritas berikutnya.',
  casual:'Welcome back, bro. SONIC udah siap. Mau lanjut yang mana?',
  friendly:'Halo bro, senang kamu kembali! Saya siap bantu kapan pun kamu butuh.',
  family:'Selamat datang kembali. Semoga keluarga baik-baik saja. Apa yang bisa saya bantu hari ini?',
  romantic:'Selamat datang kembali. Saya di sini untuk menemani hari Anda dengan penuh perhatian.',
  humor:'Welcome back, bro! Baterai ide sudah penuh, tinggal pilih misi hari ini.',
  poetic:'Selamat datang kembali. Sejumlah gagasan menanti untuk kita rangkai menjadi karya.',
  robot:'SONIC ONLINE. SISTEM SIAP. MENUNGGU INSTRUKSI BERIKUTNYA.',
  glitch:'S0NIC online... sistem tersambung. Welcome back, sir... siap untuk misi berikutnya.'
 };
 const formatVoice=(s)=>s.replace('_',' ').toUpperCase();
 class Studio{
  constructor(){this.data=null;this.active=null;this.saved=null;this.csrf=null;this.audio=null;this.url=null;this.busy=false;this.previewToken=0;
   this.root=$('personaStudio');if(!this.root)return;this.renderShell();
   this.root.addEventListener('change',e=>{if(!this.active)return;
    if(e.target.matches('input[name="sonicVoice"]'))this.active.voice_id=e.target.value;
    if(e.target.id==='sonicPersonaStyle')this.active.style=e.target.value;
    if(e.target.id==='sonicPersonaIntensity')this.active.intensity=e.target.value;
    this.stopAudio();this.status('Draft belum diterapkan. Preview kombinasi pilihanmu lalu Apply.');this.updateSummary();});
   this.root.addEventListener('click',e=>{const button=e.target.closest('button');if(!button)return;
    if(button.dataset.action==='preview-voice')this.preview({...this.active,voice_id:button.dataset.voiceId}).catch(error=>this.status(error.message));
    if(button.dataset.action==='preview-style')this.preview({...this.active,style:button.dataset.style||this.active.style}).catch(error=>this.status(error.message));
    if(button.dataset.action==='stop-preview'){this.stopAudio();this.status('Preview dihentikan.');}
    if(button.dataset.action==='save')this.save().catch(error=>this.status(error.message));
    if(button.dataset.preset)this.preset(button.dataset.preset).catch(error=>this.status(error.message));
   });
   window.addEventListener('pagehide',()=>this.stopAudio());
  }
  renderShell(){this.root.innerHTML='<div class="persona-top"><div><span class="persona-eyebrow">SONIC · PERSONALITY ENGINE</span><h3>Persona Studio</h3><p>Selected voice + language style + response intensity, as one character.</p></div><span class="persona-state">Owner profile</span></div><div id="personaReady" class="persona-loading">Loading persona...</div>';}
  status(text){const node=$('personaStatus');if(node)node.textContent=text;}
  async request(path,options={}){const headers={'Content-Type':'application/json',...options.headers};if(options.method&&options.method!=='GET')headers['X-Sonic-CSRF']=this.csrf;
   const response=await fetch(path,{credentials:'same-origin',...options,headers});if(!response.ok){const json=await response.json().catch(()=>({}));throw Error(json.detail||'Request failed HTTP '+response.status);}return response.json();}
  async load(){const session=await this.request('/api/session');if(!session.authenticated){const el=this.root.querySelector('#personaReady');if(el)el.textContent='Login required';return;}
   this.csrf=session.csrf;this.data=await this.request('/api/persona');this.saved={...this.data.active};this.active={...this.saved};this.render();}
  updateSummary(){const el=$('personaSelection');if(el&&this.active)el.textContent='Preview: '+formatVoice(this.active.voice_id)+' / '+STYLE_LABELS[this.active.style]+' / '+this.active.intensity;}
  render(){const host=$('personaReady');if(!host||!this.data)return;host.replaceChildren();
   const voices=document.createElement('div');voices.className='persona-voice-groups';
   for(const [group,label] of [['male','Male-inspired'],['female','Female-inspired']]){
    const column=document.createElement('div');column.className='persona-voice-column';const title=document.createElement('h4');title.textContent=label;column.append(title);
    for(const voice of this.data.voices.filter(item=>item.group===group)){
     const row=document.createElement('label');row.className='persona-voice-row';const radio=document.createElement('input');radio.type='radio';radio.name='sonicVoice';radio.value=voice.id;radio.checked=voice.id===this.active.voice_id;
     const info=document.createElement('span');info.className='persona-voice-info';const strong=document.createElement('strong');strong.textContent=formatVoice(voice.id);const small=document.createElement('small');small.textContent=voice.label;info.append(strong,small);
     const play=document.createElement('button');play.type='button';play.dataset.action='preview-voice';play.dataset.voiceId=voice.id;play.textContent='Play';play.setAttribute('aria-label','Play '+voice.id+' with '+this.active.style+' style');row.append(radio,info,play);column.append(row);
    }
    voices.append(column);
   }
   const panel=document.createElement('div');panel.className='persona-config';panel.innerHTML='<div><h4>Language Style</h4><p>Play any style using the currently selected voice and intensity.</p><select id="sonicPersonaStyle" aria-label="Gaya bahasa SONIC"></select><div class="style-play-row"><button type="button" data-action="preview-style">▶ Play selected style</button></div></div><div><h4>Response Intensity</h4><p>Preview respects this selection, too.</p><select id="sonicPersonaIntensity" aria-label="Panjang respons SONIC"></select><p id="personaSelection" class="persona-selection"></p></div>';
   const style=panel.querySelector('#sonicPersonaStyle'),intensity=panel.querySelector('#sonicPersonaIntensity');
   for(const key of this.data.styles){const opt=new Option(STYLE_LABELS[key]+' · '+STYLE_DETAILS[key],key,undefined,key===this.active.style);style.append(opt);}
   for(const key of this.data.intensities){const opt=new Option(key[0].toUpperCase()+key.slice(1),key,undefined,key===this.active.intensity);intensity.append(opt);}
   const tools=document.createElement('div');tools.className='persona-tools';tools.innerHTML='<div class="persona-presets"><span>One-tap presets</span><button type="button" data-preset="work">Work</button><button type="button" data-preset="personal">Personal</button><button type="button" data-preset="experimental">Experimental</button></div><div class="persona-apply-actions"><button type="button" data-action="stop-preview">Stop preview</button><button type="button" class="persona-save" data-action="save">Apply voice + style</button></div>';
   const note=document.createElement('p');note.className='persona-note';note.textContent='Preview tidak mengubah pengaturan aktif. Apply menyimpan voice, style, dan intensity bersamaan. Jika Talk sedang berjalan, mulai sesi voice baru untuk menerapkan pilihan suara.';
   const status=document.createElement('p');status.id='personaStatus';status.className='persona-feedback';status.setAttribute('role','status');status.textContent='Active persona loaded from database.';
   host.append(voices,panel,tools,note,status);this.updateSummary();
  }
  async save(){if(this.busy)return;this.stopAudio();this.busy=true;try{const previous={...this.saved};
    const out=await this.request('/api/persona',{method:'PUT',body:JSON.stringify(this.active)});if(!out.saved)throw Error('No save receipt');
    this.saved={...out.active};this.active={...out.active};this.render();this.status('Applied: '+formatVoice(this.active.voice_id)+' + '+STYLE_LABELS[this.active.style]+' + '+this.active.intensity+'. Chat/TTS now use this persona.');
    window.dispatchEvent(new CustomEvent('sonic:persona-applied',{detail:{active:{...out.active},previous}}));
   }finally{this.busy=false;}}
  async preset(name){if(this.busy)return;this.stopAudio();this.busy=true;try{const previous={...this.saved};const out=await this.request('/api/persona/presets/'+encodeURIComponent(name),{method:'POST',body:'{}'});if(!out.saved)throw Error('No preset receipt');
    this.saved={...out.active};this.active={...out.active};this.render();this.status(name+' mode applied. Voice & style synchronized.');window.dispatchEvent(new CustomEvent('sonic:persona-applied',{detail:{active:{...out.active},previous}}));
   }finally{this.busy=false;}}
  stopAudio(){++this.previewToken;const wasPlaying=!!this.audio;if(this.audio){const audio=this.audio;this.audio=null;audio.onended=null;audio.onerror=null;audio.onplaying=null;audio.pause();audio.removeAttribute('src');}if(this.url){URL.revokeObjectURL(this.url);this.url=null;}if(wasPlaying&&!window.sonicRealtimeActive)window.sonicMotion?.setState('idle');}
  async preview(choice){if(this.busy)return;if(window.sonicRealtimeActive)throw Error('Akhiri Talk to SONIC sebelum memainkan voice preview.');this.stopAudio();const seq=this.previewToken;this.busy=true;
   try{if(!this.data.voices.some(v=>v.id===choice.voice_id)||!this.data.styles.includes(choice.style)||!this.data.intensities.includes(choice.intensity))throw Error('Invalid preview selection');
    this.status('Generating '+formatVoice(choice.voice_id)+' + '+STYLE_LABELS[choice.style]+' preview with OpenAI TTS...');
    const response=await fetch('/api/voice/speak',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Sonic-CSRF':this.csrf},body:JSON.stringify({text:EXAMPLES[choice.style],consent:true,preview_voice_id:choice.voice_id,preview_style:choice.style,preview_intensity:choice.intensity})});
    if(!response.ok){const j=await response.json().catch(()=>({}));throw Error(j.detail||'TTS unavailable, check API billing/model');}
    if(this.previewToken!==seq)return;this.url=URL.createObjectURL(await response.blob());this.audio=new Audio(this.url);this.audio.onplaying=()=>window.sonicMotion?.setState('speaking');
    this.audio.onended=()=>{this.stopAudio();this.status('Preview finished.');};
    this.audio.onerror=()=>{this.stopAudio();this.status('Preview audio unavailable.');};
    this.status('Playing '+formatVoice(choice.voice_id)+' · '+STYLE_LABELS[choice.style]+' · '+choice.intensity+' (preview, not saved).');
    try{await this.audio.play();}catch(error){this.status('Audio belum diizinkan browser. Tap Play sekali lagi. '+error.name);}
   }finally{this.busy=false;}
  }
 }
 const init=()=>{window.sonicPersonaStudio=new Studio();};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
 window.SonicPersonaExamples=EXAMPLES;
})();
