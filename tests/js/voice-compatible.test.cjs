const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('web/voice-compatible.js','utf8');
function make(){
  const requests=[],states=[],turns=[],errors=[],stops=[];
  let rec=null,utterance=null,cancelled=0;
  class Recognition {
    start(){this.started=true;}
    abort(){this.aborted=true;}
    constructor(){rec=this;}
  }
  class Utterance {
    constructor(text){this.text=text;utterance=this;}
  }
  const win={
    webkitSpeechRecognition:Recognition,SpeechSynthesisUtterance:Utterance,
    speechSynthesis:{getVoices:()=>[{lang:'id-ID',name:'Bahasa Indonesia'}],
      speak:u=>{utterance=u;},cancel:()=>{cancelled++;}}
  };
  const context={window:win,Set,Array,JSON,Error,Promise,setTimeout,clearTimeout};
  vm.createContext(context);vm.runInContext(code,context);
  let api=async(path,options)=>{
    requests.push({path,body:JSON.parse(options.body)});
    return {reply:'Halo, saya SONIC.'};
  };
  const voice=new win.SonicCompatibleVoice({
    api:(...args)=>api(...args),
    onState:s=>states.push(s),onTranscript:(role,text)=>turns.push([role,text]),
    onError:e=>errors.push(e),onStopped:s=>stops.push(s)
  });
  return {voice,requests,states,turns,errors,stops,win,
    get rec(){return rec;},get utterance(){return utterance;},
    get cancelled(){return cancelled;},
    setApi:fn=>api=fn};
}
test('compatible voice is idle until explicit user tap, then handles speech and speaks answer',async()=>{
  const f=make();assert.equal(f.voice.available,true);assert.equal(f.rec,null);
  assert.equal(f.voice.start(),true);assert.equal(f.rec.started,true);
  f.rec.onresult({results:[{isFinal:true,0:{transcript:'Halo SONIC'}}]});
  await new Promise(r=>setTimeout(r,5));
  assert.equal(f.requests.length,1);
  assert.equal(f.requests[0].path,'/api/chat');
  assert.equal(f.requests[0].body.message,'Halo SONIC');
  assert.equal(f.voice.state,'speaking');
  assert.equal(f.utterance.lang,'id-ID');
  assert.equal(f.utterance.text,'Halo, saya SONIC.');
  f.utterance.onend();
  assert.equal(f.voice.state,'idle');
  assert.equal(f.rec.aborted,true);
  assert.equal(f.stops[0],'compat_answer_done');
  assert.deepEqual(f.turns,[['user','Halo SONIC'],['assistant','Halo, saya SONIC.']]);
});
test('permission denial does not call provider and releases recognition',()=>{
  const f=make();f.voice.start();f.rec.onerror({error:'not-allowed'});
  assert.equal(f.voice.active,false);assert.equal(f.requests.length,0);
  assert.equal(f.rec.aborted,true);assert.match(f.errors[0],/Izin mikrofon/);
});
test('Stop during an outstanding AI response prevents stale audio playback',async()=>{
  const f=make();let finish;
  f.setApi(async()=>new Promise(resolve=>{finish=resolve;}));
  f.voice.start();f.rec.onresult({results:[{isFinal:true,0:{transcript:'Apa kabar?'}}]});
  await Promise.resolve();f.voice.stop('compat_owner_stop');
  finish({reply:'Jawaban terlambat'});
  await new Promise(r=>setTimeout(r,5));
  assert.equal(f.voice.state,'idle');assert.equal(f.utterance,null);
  assert.equal(f.stops[0],'compat_owner_stop');
});
test('recognizer unavailable fails before starting microphone or provider',()=>{
  const f=make();delete f.win.webkitSpeechRecognition;
  assert.throws(()=>f.voice.start(),/Speech Recognition/);
  assert.equal(f.voice.active,false);assert.equal(f.requests.length,0);
});
test('No final speech result ends cleanly without model request',()=>{
  const f=make();f.voice.start();f.rec.onend();
  assert.equal(f.voice.state,'idle');assert.equal(f.requests.length,0);
  assert.equal(f.stops[0],'compat_no_speech');
});
