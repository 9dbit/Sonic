/* SONIC Persona Studio: persistent, owner-only selections plus real TTS previews. */
(()=>{'use strict';
 const $=id=>document.getElementById(id);
 const STYLE_LABELS={professional:'Professional',tegas:'Tegas',casual:'Casual',friendly:'Friendly',family:'Family',romantic:'Romantic',humor:'Humor',poetic:'Poetic',robot:'Robot',glitch:'Glitch'};
 const STYLE_DETAILS={professional:'Rapi dan efisien',tegas:'Tegas dan langsung',casual:'Santai dan natural',friendly:'Hangat dan komunikatif',family:'Lembut dan akrab',romantic:'Halus dan penuh perhatian',humor:'Ringan dan cerdas',poetic:'Puitis dan indah',robot:'Presisi dan sistematis',glitch:'Digital dan eksperimental'};
 const PREVIEW='Welcome back, sir. SONIC is online and ready. Siap membantu Anda hari ini.';
 class Studio {
  constructor(){this.data=null;this.active=null;this.csrf=null;this.audio=null;this.url=null;this.busy=false;
    this.root=$('personaStudio');if(!this.root)return;this.renderShell();
    this.root.addEventListener('change',e=>{if(e.target.matches('input[name="sonicVoice"]'))this.active.voice_id=e.target.value;
      if(e.target.id==='sonicPersonaStyle')this.active.style=e.target.value;
      if(e.target.id==='sonicPersonaIntensity')this.active.intensity=e.target.value;this.status('Belum disimpan. Tekan Save persona.');});
    this.root.addEventListener('click',e=>{const button=e.target.closest('button');if(!button)return;
      if(button.dataset.action==='preview')this.preview(button.dataset.voiceId).catch(x=>this.status(x.message));
      if(button.dataset.action==='save')this.save().catch(x=>this.status(x.message));
      if(button.dataset.preset)this.preset(button.dataset.preset).catch(x=>this.status(x.message));});
    window.addEventListener('pagehide',()=>this.stopAudio());
  }
  renderShell(){this.root.innerHTML=`<div class="persona-top"><div><span class="persona-eyebrow">SONIC V0.6 · PERSONALITY ENGINE</span><h3>Persona Studio</h3><p>Customize how SONIC sounds, speaks, and responds.</p></div><span class="persona-state">Owner profile</span></div><div id="personaReady" class="persona-loading">Loading persona...</div>`;}
  status(text){const box=$('personaStatus');if(box)box.textContent=text;}
  async request(path,options={}){const headers={'Content-Type':'application/json',...options.headers};if(options.method&&options.method!=='GET')headers['X-Sonic-CSRF']=this.csrf;const response=await fetch(path,{credentials:'same-origin',...options,headers});if(!response.ok){const body=await response.json().catch(()=>({}));throw Error(body.detail||'Request failed HTTP '+response.status);}return response.json();}
  async load(){const s=await this.request('/api/session');if(!s.authenticated){this.root.querySelector('#personaReady').textContent='Login required';return;}this.csrf=s.csrf;this.data=await this.request('/api/persona');this.active={...this.data.active};this.render();}
  render(){const host=$('personaReady');if(!this.data)return;
    host.replaceChildren();const voices=document.createElement('div');voices.className='persona-voice-groups';
    for(const [group,label] of [['male','Male-inspired'],['female','Female-inspired']]){
      const column=document.createElement('div');column.className='persona-voice-column';const title=document.createElement('h4');title.textContent=label;column.append(title);
      for(const voice of this.data.voices.filter(x=>x.group===group)){
        const row=document.createElement('label');row.className='persona-voice-row';
        const radio=document.createElement('input');radio.type='radio';radio.name='sonicVoice';radio.value=voice.id;radio.checked=voice.id===this.active.voice_id;
        const info=document.createElement('span');info.className='persona-voice-info';const strong=document.createElement('strong');strong.textContent=voice.id.replace('_',' ').toUpperCase();const small=document.createElement('small');small.textContent=voice.label;info.append(strong,small);
        const preview=document.createElement('button');preview.type='button';preview.dataset.action='preview';preview.dataset.voiceId=voice.id;preview.textContent='Play';preview.setAttribute('aria-label','Preview '+voice.id);
        row.append(radio,info,preview);column.append(row);
      }
      voices.append(column);
    }
    const panel=document.createElement('div');panel.className='persona-config';panel.innerHTML='<div><h4>Language style</h4><p>Applies to chat, speech prompts, and new Realtime sessions.</p><select id="sonicPersonaStyle" aria-label="Gaya bahasa SONIC"></select></div><div><h4>Response intensity</h4><p>Choose how brief or expressive SONIC should be.</p><select id="sonicPersonaIntensity" aria-label="Panjang respons SONIC"></select></div>';
    const style=panel.querySelector('#sonicPersonaStyle'),intensity=panel.querySelector('#sonicPersonaIntensity');
    for(const key of this.data.styles){const opt=document.createElement('option');opt.value=key;opt.textContent=STYLE_LABELS[key]+' · '+STYLE_DETAILS[key];opt.selected=key===this.active.style;style.append(opt);}
    for(const key of this.data.intensities){const opt=document.createElement('option');opt.value=key;opt.textContent=key[0].toUpperCase()+key.slice(1);opt.selected=key===this.active.intensity;intensity.append(opt);}
    const tools=document.createElement('div');tools.className='persona-tools';tools.innerHTML='<div class="persona-presets"><span>One-tap presets</span><button type="button" data-preset="work">Work</button><button type="button" data-preset="personal">Personal</button><button type="button" data-preset="experimental">Experimental</button></div><button type="button" class="persona-save" data-action="save">Save active persona</button>';
    const note=document.createElement('p');note.className='persona-note';note.textContent='Voice categories are curated listening impressions, not provider-certified gender. Preview each voice. Changes to voice require a new Realtime session.';
    const status=document.createElement('p');status.id='personaStatus';status.className='persona-feedback';status.setAttribute('role','status');status.textContent='Active persona loaded from persistent storage.';
    host.append(voices,panel,tools,note,status);
  }
  async save(){if(this.busy)return;this.busy=true;try{const out=await this.request('/api/persona',{method:'PUT',body:JSON.stringify(this.active)});if(!out.saved)throw Error('No save receipt');this.active={...out.active};this.status('Saved. New voice takes effect on the next Talk session.');}finally{this.busy=false;}}
  async preset(name){if(this.busy)return;this.busy=true;try{const out=await this.request('/api/persona/presets/'+encodeURIComponent(name),{method:'POST',body:'{}'});if(!out.saved)throw Error('No preset receipt');this.active={...out.active};this.render();this.status(name+' mode saved and active.');}finally{this.busy=false;}}
  stopAudio(){if(this.audio){this.audio.pause();this.audio.src='';this.audio=null;}if(this.url){URL.revokeObjectURL(this.url);this.url=null;}}
  async preview(voiceId){if(this.busy)return;this.stopAudio();this.busy=true;this.status('Generating preview. This calls the configured OpenAI TTS provider.');
    try{if(!this.data.voices.some(x=>x.id===voiceId))throw Error('Voice not available');const resp=await fetch('/api/voice/speak',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Sonic-CSRF':this.csrf},body:JSON.stringify({text:PREVIEW,consent:true,preview_voice_id:voiceId})});
      if(!resp.ok){const x=await resp.json().catch(()=>({}));throw Error(x.detail||'Voice provider unavailable');}
      this.url=URL.createObjectURL(await resp.blob());this.audio=new Audio(this.url);this.audio.onended=()=>{this.stopAudio();this.status('Preview finished.');};this.status('Playing '+voiceId+' (preview only; not saved).');await this.audio.play();
    }finally{this.busy=false;}}
 }
 const init=()=>{window.sonicPersonaStudio=new Studio();};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
