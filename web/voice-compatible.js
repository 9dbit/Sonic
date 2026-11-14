/* Explicit Safari-compatible, turn-based voice. No WebRTC, hidden recording, or PC tools.
   Microphone audio is handled by the browser SpeechRecognition implementation.
   Only the resulting text is sent to SONIC preview chat, then local TTS plays it. */
(() => {
  'use strict';
  class SonicCompatibleVoice {
    constructor(options) {
      this.options=options;
      this.state='idle';this.generation=0;this.recognition=null;
      this.utterance=null;this.timeout=null;this.hasResult=false;
    }
    get available(){return !!(window.SpeechRecognition||window.webkitSpeechRecognition);}
    get active(){return this.state!=='idle';}
    setState(state){this.state=state;this.options.onState?.(state);}
    start(){
      if(this.active)return false;
      const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(!Constructor)throw Error('Safari tidak menyediakan Speech Recognition. Gunakan chat teks atau browser lain.');
      if(!window.speechSynthesis||!window.SpeechSynthesisUtterance)
        throw Error('Suara browser tidak didukung. Gunakan chat teks.');
      const generation=++this.generation;
      this.hasResult=false;
      this.recognition=new Constructor();
      const recognition=this.recognition;
      recognition.lang='id-ID';
      recognition.continuous=false;
      recognition.interimResults=false;
      recognition.maxAlternatives=1;
      recognition.onresult=e=>{
        if(generation!==this.generation||this.hasResult)return;
        const text=Array.from(e.results||[])
          .filter(result=>result.isFinal!==false)
          .map(result=>result[0]?.transcript||'').join(' ').trim().slice(0,900);
        if(!text)return;
        this.hasResult=true;
        clearTimeout(this.timeout);this.timeout=null;
        this.processTranscript(text,generation).catch(err=>{
          if(generation!==this.generation)return;
          this.options.onError?.('Voice kompatibel: '+err.message);
          this.stop('compat_model_error');
        });
      };
      recognition.onerror=e=>{
        if(generation!==this.generation||this.hasResult)return;
        const names={'not-allowed':'Izin mikrofon atau pengenalan suara Safari ditolak.',
          'audio-capture':'Mikrofon tidak tersedia.',network:'Layanan pengenalan suara Safari tidak terhubung.',
          'no-speech':'Belum terdengar ucapan.'};
        this.options.onError?.(names[e.error]||'Pengenalan suara Safari gagal. Coba lagi.');
        this.stop('compat_recognition_error');
      };
      recognition.onend=()=>{
        if(generation===this.generation&&!this.hasResult&&this.state==='listening')
          this.stop('compat_no_speech');
      };
      this.setState('listening');
      this.timeout=setTimeout(()=>{if(generation===this.generation)this.stop('compat_timeout');},19000);
      try{recognition.start();}catch(e){this.stop('compat_start_failed');throw e;}
      return true;
    }
    async processTranscript(text,generation){
      if(generation!==this.generation)return;
      this.setState('thinking');
      this.options.onTranscript?.('user',text);
      const response=await this.options.api('/api/chat',{
        method:'POST',body:JSON.stringify({message:text})
      });
      if(generation!==this.generation)return;
      const answer=String(response.reply||'').trim().slice(0,900);
      if(!answer)throw Error('Model tidak mengembalikan jawaban.');
      this.options.onTranscript?.('assistant',answer);
      const utterance=this.utterance=new window.SpeechSynthesisUtterance(answer);
      utterance.lang='id-ID';utterance.rate=1.04;utterance.pitch=1;
      const voices=window.speechSynthesis.getVoices?.()||[];
      const local=voices.find(v=>String(v.lang||'').toLowerCase().startsWith('id'));
      if(local)utterance.voice=local;
      utterance.onend=()=>{if(generation===this.generation)this.stop('compat_answer_done');};
      utterance.onerror=()=>{if(generation===this.generation){
        this.options.onError?.('Safari tidak dapat memutar audio. Jawaban teks sudah tersedia.');
        this.stop('compat_playback_error');
      }};
      this.setState('speaking');
      window.speechSynthesis.speak(utterance);
    }
    stop(reason='compat_owner_stop'){
      if(!this.active)return;
      ++this.generation;clearTimeout(this.timeout);this.timeout=null;
      const r=this.recognition;this.recognition=null;
      if(r){r.onend=null;r.onerror=null;r.onresult=null;try{r.abort();}catch(_){}}
      try{window.speechSynthesis?.cancel();}catch(_){}
      this.utterance=null;this.setState('idle');this.options.onStopped?.(reason);
    }
  }
  window.SonicCompatibleVoice=SonicCompatibleVoice;
})();
