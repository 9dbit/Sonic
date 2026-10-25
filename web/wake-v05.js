/* SONIC foreground opt-in wake word. Browser SpeechRecognition can use a remote provider.
   No background processing, no hidden recording, no automatic owner grants. */
(() => {
  'use strict';
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const WAKE = /\bsonic\b[\s,:.!-]*(.*)$/i;
  class SonicWake {
    constructor(options={}){this.options=options;this.enabled=false;this.running=false;this.suspended=false;this.listener=null;this.timer=null;this.generation=0;}
    supported(){return !!Recognition && window.isSecureContext;}
    state(value){this.options.onState?.(value);}
    start(){
      if(!this.supported())throw Error('Wake word membutuhkan HTTPS dan SpeechRecognition browser. Tidak tersedia pada perangkat ini.');
      this.enabled=true;this.suspended=false;this.generation++;this.listen();
    }
    listen(){
      if(!this.enabled||this.suspended||document.hidden||this.running||this.listener)return;
      const g=this.generation,r=new Recognition();this.listener=r;r.lang='id-ID';r.continuous=true;r.interimResults=false;r.maxAlternatives=1;
      r.onstart=()=>{if(g===this.generation){this.running=true;this.state('listening');}};
      r.onresult=e=>{
        if(g!==this.generation)return;
        for(let i=e.resultIndex;i<e.results.length;i++){
          if(!e.results[i].isFinal)continue;
          const text=String(e.results[i][0]?.transcript||'').trim();
          const match=text.match(WAKE);
          if(match){this.pause();this.options.onWake?.(match[1].trim());break;}
        }
      };
      r.onerror=e=>{if(g===this.generation&&e.error!=='no-speech'&&e.error!=='aborted'){
        this.options.onError?.('Standby mic: '+String(e.error));
        if(['not-allowed','service-not-allowed','audio-capture'].includes(e.error))this.stop();
      }};
      r.onend=()=>{
        if(g!==this.generation)return;this.running=false;this.listener=null;
        if(this.enabled&&!this.suspended&&!document.hidden){this.timer=setTimeout(()=>this.listen(),750);}
        else this.state(this.enabled?'paused':'off');
      };
      try{r.start();}catch(error){this.listener=null;this.running=false;this.options.onError?.(error.message);this.stop();}
    }
    pause(){this.suspended=true;clearTimeout(this.timer);try{this.listener?.stop();}catch(_){}this.state('paused');}
    resume(){if(!this.enabled)return;this.suspended=false;this.generation++;
      try{this.listener?.abort();}catch(_){}this.listener=null;this.running=false;
      this.timer=setTimeout(()=>this.listen(),500);
    }
    stop(){this.enabled=false;this.suspended=false;this.generation++;clearTimeout(this.timer);try{this.listener?.abort();}catch(_){}this.listener=null;this.running=false;this.state('off');}
  }
  window.SonicWake=SonicWake;
})();
