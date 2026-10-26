/* SONIC Realtime transport. No API key, hidden microphone, or browser-side writes. */
(() => {
  'use strict';
  class SonicVoice {
    constructor(options) {
      this.options=options;this.state='idle';this.generation=0;this.pc=null;this.dc=null;
      this.stream=null;this.audio=null;this.sessionId=null;this.seen=new Set();this.toolChain=Promise.resolve();
      this.activeResponse=false;this.pendingTools=0;this.continueNeeded=false;this.inputSpeaking=false;this.muted=false;
      this.tick=null;this.connectTimer=null;this.speaking=false;this.requestStarted=false;this.turnChain=Promise.resolve();this.verifiedSpeech=[];this.transcriptsSeen=new Set();
      this.inputContexts=new Map();
    }
    get active(){return this.state!=='idle';}
    setState(state){this.state=state;this.options.onState?.(state);}
    send(event){if(this.dc?.readyState==='open')this.dc.send(JSON.stringify(event));}
    async start(){
      if(this.active)return;
      if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.RTCPeerConnection){throw Error('Realtime voice memerlukan HTTPS dan browser dengan WebRTC.');}
      const generation=++this.generation;this.setState('connecting');this.toolChain=Promise.resolve();this.seen.clear();this.pendingTools=0;this.continueNeeded=false;this.muted=false;this.requestStarted=false;
      this.sessionId=crypto.randomUUID();this.turnChain=Promise.resolve();this.verifiedSpeech=[];this.transcriptsSeen.clear();const sessionId=this.sessionId;
      this.inputContexts.clear();
      try{
        const media=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
        if(generation!==this.generation){media.getTracks().forEach(t=>t.stop());return;}
        this.stream=media;
        const pc=this.pc=new RTCPeerConnection();
        this.audio=document.createElement('audio');this.audio.autoplay=true;this.audio.setAttribute('playsinline','');
        pc.ontrack=e=>{if(generation!==this.generation)return;this.audio.srcObject=e.streams[0]||new MediaStream([e.track]);this.audio.play().catch(()=>this.options.onPlaybackBlocked?.());};
        for(const track of this.stream.getAudioTracks()){track.onended=()=>{if(generation===this.generation)this.stop('microphone_ended');};pc.addTrack(track,this.stream);}
        pc.onconnectionstatechange=()=>{if(generation!==this.generation)return;if(['failed','closed','disconnected'].includes(pc.connectionState))this.stop('connection_ended');};
        const dc=this.dc=pc.createDataChannel('oai-events');
        dc.onopen=()=>{if(generation!==this.generation)return;clearTimeout(this.connectTimer);this.setState('listening');};
        dc.onclose=()=>{if(generation===this.generation)this.stop('channel_closed');};
        dc.onerror=()=>{if(generation===this.generation){this.options.onError?.('Koneksi suara terputus.');this.stop('channel_error');}};
        dc.onmessage=e=>{if(generation!==this.generation||typeof e.data!=='string'||e.data.length>65536)return;try{this.event(JSON.parse(e.data),generation);}catch(_){this.options.onError?.('Event suara tidak dapat diproses.');}};
        const offer=await pc.createOffer();await pc.setLocalDescription(offer);
        await new Promise(resolve=>{if(pc.iceGatheringState==='complete'){resolve();return;}const done=()=>{clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',changed);resolve();};const changed=()=>{if(pc.iceGatheringState==='complete')done();};const timer=setTimeout(done,2000);pc.addEventListener('icegatheringstatechange',changed);});
        if(generation!==this.generation)return;
        this.requestStarted=true;
        const response=await this.options.api('/api/voice/sessions',{method:'POST',body:JSON.stringify({session_id:sessionId,sdp:pc.localDescription.sdp,consent:true})});
        if(generation!==this.generation){await this.closeRemote(sessionId);return;}
        this.expires=Date.parse(response.expires_at);if(!Number.isFinite(this.expires))throw Error('Voice expiry invalid');
        await pc.setRemoteDescription({type:'answer',sdp:response.sdp});
        this.options.onConnected?.({model:response.model,expires_at:response.expires_at});
        this.tick=setInterval(()=>{const seconds=Math.max(0,Math.ceil((this.expires-Date.now())/1000));this.options.onTick?.(seconds);if(seconds===0)this.stop('duration_limit');},1000);
        this.connectTimer=setTimeout(()=>{if(this.state==='connecting'){this.options.onError?.('Koneksi audio tidak terbentuk. Mikrofon dihentikan.');this.stop('connect_timeout');}},15000);
      }catch(error){
        if(generation===this.generation){if(error.status===429||error.status===422||error.status===503)this.requestStarted=false;await this.stop('start_failed');this.options.onError?.(error.name==='NotAllowedError'?'Izin mikrofon ditolak. Tidak ada sesi suara aktif.':error.message);}
      }
    }
    event(event,generation){
      switch(event.type){
        case 'input_audio_buffer.speech_started':
          if(typeof event.item_id==='string'){this.inputContexts.set(event.item_id,this.options.onInputStart?.()||null);if(this.inputContexts.size>200)this.inputContexts.delete(this.inputContexts.keys().next().value);}
          this.inputSpeaking=true;this.speaking=false;this.setState(this.muted?'muted':'listening');break;
        case 'input_audio_buffer.speech_stopped':this.inputSpeaking=false;if(!this.muted)this.setState('thinking');this.continueResponse();break;
        case 'response.created':this.activeResponse=true;if(!this.inputSpeaking&&!this.muted)this.setState('thinking');break;
        case 'response.done':this.activeResponse=false;this.continueResponse();if(!this.speaking&&!this.muted&&!this.pendingTools)this.setState('listening');break;
        case 'output_audio_buffer.started':this.speaking=true;this.setState('speaking');break;
        case 'output_audio_buffer.stopped':case 'output_audio_buffer.cleared':this.speaking=false;this.setState(this.muted?'muted':'listening');break;
        case 'conversation.item.input_audio_transcription.completed':
          if(typeof event.transcript==='string'&&event.transcript.trim()){
            const transcript=event.transcript.slice(0,1300);
            const itemId=typeof event.item_id==='string'?event.item_id:'';
            if(itemId&&this.transcriptsSeen.has(itemId))break;
            if(itemId)this.transcriptsSeen.add(itemId);
            if(this.transcriptsSeen.size>200)this.transcriptsSeen.clear();
            const inputContext=this.inputContexts.get(itemId)||null;this.inputContexts.delete(itemId);
            this.turnChain=this.turnChain.then(async()=>{
              let routing={handled:false};
              try{
                routing=await this.options.onTranscript?.('user',transcript,
                  {sessionId:this.sessionId,itemId,inputContext}) || {handled:false};
              }catch(err){
                this.options.onError?.('Rute suara gagal: '+(err?.message||'unknown'));
                routing={handled:true,reply:'Penerimaan perintah belum terkonfirmasi. Periksa aktivitas tugas sebelum mencoba lagi.'};
              }
              if(generation!==this.generation || !this.active)return;
              if(routing?.silent)return;
              if(routing?.handled){
                // Server-verified action responses are spoken in an isolated
                // no-tools response. The model cannot invent a second PC plan.
                this.send({type:'conversation.item.create',item:{
                  type:'message',role:'user',content:[{type:'input_text',
                    text:'VERIFIED_SONIC_ACTION_ROUTE (read-only application result): '+
                         JSON.stringify({status:routing.processing?'processing':'accepted',
                           reply:String(routing.reply||'').slice(0,1200)})}]
                }});
                this.sayVerified(routing.reply||'Perintah diterima, belum ada hasil Windows.');
                return;
              }
              // General conversation still uses the normal Realtime model,
              // after server validation has ruled out a PC command.
              this.continueNeeded=true;
              this.continueResponse();
            }).catch(err=>this.options.onError?.(String(err)));
          }
          break;
        case 'response.output_audio_transcript.done':if(typeof event.transcript==='string')this.options.onTranscript?.('assistant',event.transcript.slice(0,12000));break;
        case 'response.function_call_arguments.done':this.toolEvent(event,generation);break;
        case 'error':this.options.onError?.('OpenAI voice: '+String(event.error?.code||'session_error'));if(['invalid_api_key','insufficient_quota','session_expired'].includes(event.error?.code))this.stop('provider_error');break;
      }
    }
    toolEvent(event,generation){
      const callId=event.call_id;
      if(typeof callId!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(callId)||this.seen.has(callId))return;
      if(this.seen.size>=80){this.options.onError?.('Batas tool suara tercapai.');this.stop('tool_limit');return;}
      this.seen.add(callId);this.pendingTools++;
      this.toolChain=this.toolChain.then(async()=>{
        if(generation!==this.generation)return;
        let output;
        try{
          if(typeof event.arguments!=='string'||event.arguments.length>4096)throw Error('Invalid tool arguments');
          const args=JSON.parse(event.arguments);if(!args||typeof args!=='object'||Array.isArray(args))throw Error('Invalid tool arguments');
          const result=await this.options.api('/api/voice/sessions/'+this.sessionId+'/tools',{
            method:'POST',body:JSON.stringify({call_id:callId,name:event.name,arguments:args})});
          if(generation!==this.generation)return;
          output=result.output;
          if(result.ui_actions?.length)output={...output,browser_application:await this.options.onActions?.(result.ui_actions)};
          if(result.memory_references?.length)this.options.onReferences?.(result.memory_references);
          if(output?.requires_confirmation)this.options.onProposal?.(output,this.sessionId);
        }catch(error){output={error:'SONIC_TOOL_UNAVAILABLE'};if(generation===this.generation)this.options.onError?.(error.message);}
        if(generation===this.generation){this.send({type:'conversation.item.create',item:{type:'function_call_output',call_id:callId,output:JSON.stringify(output)}});this.continueNeeded=true;}
      }).catch(()=>{}).finally(()=>{if(generation===this.generation){this.pendingTools=Math.max(0,this.pendingTools-1);this.continueResponse();}});
    }
    sayVerified(text){
      const statement=String(text||'').trim().slice(0,1150);
      if(!this.active||!statement)return;
      this.verifiedSpeech.push(statement);
      // Bound backlog while a long spoken response is finishing.
      if(this.verifiedSpeech.length>5)this.verifiedSpeech.splice(0,this.verifiedSpeech.length-5);
      this.continueNeeded=true;
      this.continueResponse();
    }
    continueResponse(){
      if(!this.continueNeeded||this.pendingTools||this.activeResponse||this.inputSpeaking||!this.active)return;
      this.continueNeeded=false;
      this.activeResponse=true;
      if(this.verifiedSpeech.length){
        const statement=this.verifiedSpeech.shift();
        if(this.verifiedSpeech.length)this.continueNeeded=true;
        // Isolate status speech from the conversational model. The input is
        // always a bounded trusted application receipt, not a new PC command.
        this.send({type:'response.create',response:{
          conversation:'none',output_modalities:['audio'],tool_choice:'none',tools:[],
          max_output_tokens:240,
          instructions:'You are the SONIC status speaker. Read the provided Indonesian status faithfully in one concise sentence. Do not invent tool calls, promise an action, suggest alternatives, ask questions, or claim completed unless the status explicitly says completed. Do not add apologies or commentary.',
          input:[{type:'message',role:'user',content:[{type:'input_text',text:statement}]}]
        }});
      }else this.send({type:'response.create'});
    }
    verifiedPCReceipt(text){
      if(!this.active)return;
      this.send({type:'conversation.item.create',item:{type:'message',role:'user',content:[
        {type:'input_text',text:'VERIFIED_SONIC_DEVICE_RESULT (read-only receipt from the Windows agent): '+String(text).slice(0,1600)}
      ]}});
      this.sayVerified(text);
    }
    memoryReceipt(receipt){this.send({type:'conversation.item.create',item:{type:'message',role:'user',content:[{type:'input_text',text:'SAVED_MEMORY_RECEIPT from the SONIC application: '+JSON.stringify(receipt)}]}});this.continueNeeded=true;this.continueResponse();}
    mute(){if(!this.stream)return;this.muted=!this.muted;for(const t of this.stream.getAudioTracks())t.enabled=!this.muted;if(this.muted)this.send({type:'input_audio_buffer.clear'});this.setState(this.muted?'muted':'listening');}
    async resumeAudio(){if(this.audio){await this.audio.play();this.options.onPlaybackResumed?.();}}
    async closeRemote(id){try{const r=await this.options.api('/api/voice/sessions/'+id+'/stop',{method:'POST',body:'{}',keepalive:true});if(!r.provider_close_confirmed)this.options.onError?.('Mikrofon lokal berhenti; penutupan sesi provider belum terkonfirmasi.');}catch(_){this.options.onError?.('Mikrofon lokal berhenti. Penutupan provider belum terkonfirmasi; server akan mencoba cleanup.');}}
    async stop(reason='owner_stop'){
      const id=this.sessionId,started=this.requestStarted;
      ++this.generation;clearInterval(this.tick);clearTimeout(this.connectTimer);this.tick=null;this.connectTimer=null;
      const stream=this.stream;this.stream=null;stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
      if(this.dc){this.dc.onclose=null;this.dc.onerror=null;this.dc.onmessage=null;this.dc.close();this.dc=null;}
      if(this.pc){this.pc.onconnectionstatechange=null;this.pc.ontrack=null;this.pc.close();this.pc=null;}
      if(this.audio){this.audio.pause();this.audio.srcObject=null;this.audio.remove();this.audio=null;}
      this.sessionId=null;this.requestStarted=false;this.pendingTools=0;this.continueNeeded=false;this.activeResponse=false;this.speaking=false;this.inputSpeaking=false;this.verifiedSpeech=[];this.transcriptsSeen.clear();
      this.inputContexts.clear();
      this.setState('idle');this.options.onStopped?.(reason);
      if(id&&started)await this.closeRemote(id);
    }
  }
  window.SonicVoice=SonicVoice;
})();
