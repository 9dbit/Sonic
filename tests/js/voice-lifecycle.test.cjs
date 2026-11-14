const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const code=fs.readFileSync('web/voice.js','utf8');
function fixture(overrides={}){
  const tracks=[];const sent=[];const requests=[];const states=[];let mediaCalls=0;
  const stream=()=>{const t={enabled:true,stopped:false,stop(){this.stopped=true;},onended:null};tracks.push(t);return {getTracks:()=>[t],getAudioTracks:()=>[t]};};
  class Peer{addTrack(){}constructor(){this.iceGatheringState=overrides.iceGatheringState||'complete';this.connectionState='new';this.listeners={};}addEventListener(k,fn){this.listeners[k]=fn;}removeEventListener(k){delete this.listeners[k];}createDataChannel(){return this.dc={readyState:'open',send:e=>sent.push(JSON.parse(e)),close(){this.readyState='closed';}};}async createOffer(){return {sdp:'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=candidate:1 1 UDP 1 192.0.2.1 1234 typ host\r\n'};}async setLocalDescription(v){this.localDescription=v;}async setRemoteDescription(v){this.remoteDescription=v;this.dc.onopen?.();}close(){this.closed=true;}}
  const api=async(path,opts)=>{requests.push([path,opts]);if(path==='/api/voice/sessions')return {sdp:'v=0',expires_at:new Date(Date.now()+300000).toISOString(),model:'synthetic'};return {closed:true,provider_close_confirmed:true,output:{results:[]},ui_actions:[]};};
  const context={window:{isSecureContext:true,RTCPeerConnection:Peer},RTCPeerConnection:Peer,crypto:{randomUUID:()=> '01234567-0123-4123-8123-012345678901'},navigator:{mediaDevices:{getUserMedia:async()=>{mediaCalls++;return overrides.media?await overrides.media(stream):stream();}}},document:{createElement:()=>({setAttribute(){},play:()=>Promise.resolve(),pause(){},remove(){}})},Date,JSON,Error,Set,Promise,setTimeout,clearTimeout,setInterval,clearInterval};
  vm.createContext(context);vm.runInContext(code,context);
  const voice=new context.window.SonicVoice({api:overrides.api||api,onState:s=>states.push(s),onActions:async()=>[],onError:()=>{}});
  return {voice,tracks,sent,requests,states,get mediaCalls(){return mediaCalls;}};
}
test('never opens microphone until start, then Stop closes all local media',async()=>{const f=fixture();assert.equal(f.mediaCalls,0);await f.voice.start();assert.equal(f.mediaCalls,1);assert.equal(f.voice.state,'listening');f.voice.mute();assert.equal(f.tracks[0].enabled,false);await f.voice.stop();assert.equal(f.voice.active,false);assert.ok(f.tracks.every(t=>t.stopped));assert.ok(f.requests.some(r=>r[0].endsWith('/stop')));});
test('Stop while microphone permission is pending disposes late tracks',async()=>{let grant;const f=fixture({media:make=>new Promise(r=>{grant=()=>r(make());})});const start=f.voice.start();await f.voice.stop();grant();await start;assert.ok(f.tracks.every(t=>t.stopped));assert.equal(f.voice.pc,null);assert.equal(f.requests.length,0);});
test('provider failure immediately closes microphone',async()=>{const f=fixture({api:async()=>{throw Error('provider rejected');}});await f.voice.start();assert.equal(f.voice.active,false);assert.ok(f.tracks.every(t=>t.stopped));});
test('duplicate realtime function event executes once and returns one result',async()=>{const f=fixture();await f.voice.start();const event={type:'response.function_call_arguments.done',call_id:'f1',name:'memory_search',arguments:'{"query":"bakso"}'};f.voice.event(event,f.voice.generation);f.voice.event(event,f.voice.generation);await f.voice.toolChain;assert.equal(f.requests.filter(r=>r[0].endsWith('/tools')).length,1);assert.equal(f.sent.filter(e=>e.item?.type==='function_call_output').length,1);await f.voice.stop();});
test('late tools after Stop cannot apply a graph change or restart response',async()=>{let release;let applied=0;const f=fixture();await f.voice.start();assert.equal(f.voice.active,true);const original=f.voice.options.api;f.voice.options.api=(p,o)=>p.endsWith('/tools')?new Promise(r=>{release=r;}):original(p,o);f.voice.options.onActions=()=>{applied++;};f.voice.toolEvent({call_id:'f1',name:'graph_reset',arguments:'{}'},f.voice.generation);await Promise.resolve();await f.voice.stop();release({output:{prepared:true},ui_actions:[{type:'graph.reset'}]});await f.voice.toolChain;assert.equal(applied,0);assert.equal(f.sent.filter(e=>e.type==='response.create').length,0);});


test('mobile ICE flap enters reconnecting then resumes original session without reopening the microphone',async()=>{
  const f=fixture();
  await f.voice.start();
  const firstGeneration=f.voice.generation;
  const firstSession=f.voice.sessionId;
  f.voice.pc.connectionState='disconnected';
  f.voice.pc.onconnectionstatechange();
  assert.equal(f.voice.state,'reconnecting');
  assert.equal(f.voice.active,true);
  assert.equal(f.tracks[0].stopped,false);
  assert.equal(f.requests.filter(r=>r[0]==='/api/voice/sessions').length,1);
  f.voice.pc.connectionState='connected';
  f.voice.pc.onconnectionstatechange();
  assert.equal(f.voice.state,'listening');
  assert.equal(f.voice.recoveryTimer,null);
  assert.equal(f.voice.sessionId,firstSession);
  assert.equal(f.voice.generation,firstGeneration);
  assert.equal(f.mediaCalls,1);
  await f.voice.stop();
});

test('data channel error has bounded recovery; permanent channel close releases microphone and provider',async()=>{
  const f=fixture();
  await f.voice.start();
  f.voice.dc.onerror?.();
  assert.equal(f.voice.state,'reconnecting');
  assert.equal(f.tracks[0].stopped,false);
  f.voice.dc.onclose?.();
  await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(f.voice.state,'idle');
  assert.equal(f.tracks[0].stopped,true);
  assert.equal(f.voice.recoveryTimer,null);
  const stops=f.requests.filter(r=>r[0].endsWith('/stop'));
  assert.equal(stops.length,1);
  assert.equal(JSON.parse(stops[0][1].body).reason,'channel_closed');
});

test('manual Stop during reconnect closes the same session with no automatic paid-provider retry',async()=>{
  const f=fixture();
  await f.voice.start();
  f.voice.pc.iceConnectionState='disconnected';
  f.voice.pc.oniceconnectionstatechange();
  assert.equal(f.voice.state,'reconnecting');
  await f.voice.stop('owner_stop');
  assert.equal(f.voice.active,false);
  assert.equal(f.voice.recoveryTimer,null);
  assert.equal(f.mediaCalls,1);
  assert.equal(f.requests.filter(r=>r[0]==='/api/voice/sessions').length,1);
});


test('a failed peer is not marked recovered because of stale ICE connected telemetry',async()=>{
  const f=fixture();
  await f.voice.start();
  f.voice.pc.iceConnectionState='connected';
  f.voice.pc.connectionState='failed';
  f.voice.pc.onconnectionstatechange();
  assert.equal(f.voice.state,'reconnecting');
  f.voice.pc.oniceconnectionstatechange?.();
  assert.equal(f.voice.state,'reconnecting');
  assert.equal(f.voice.transportReady(),false);
  f.voice.pc.connectionState='connected';
  f.voice.pc.onconnectionstatechange();
  assert.equal(f.voice.state,'listening');
  await f.voice.stop();
});

test('Safari candidate gathering waits for completion before any paid SDP exchange',async()=>{
  const f=fixture({iceGatheringState:'gathering'});
  const pending=f.voice.start();
  await new Promise(r=>setTimeout(r,8));
  assert.ok(f.voice.pc);
  assert.equal(f.requests.length,0);
  const pc=f.voice.pc;
  pc.iceGatheringState='complete';
  pc.listeners.icegatheringstatechange?.();
  await pending;
  assert.equal(f.requests.filter(x=>x[0]==='/api/voice/sessions').length,1);
  await f.voice.stop();
});

test('ICE gathering timeout fails without opening a second paid session',async()=>{
  const f=fixture();
  await f.voice.start();
  const initial=f.requests.filter(x=>x[0]==='/api/voice/sessions').length;
  const pc=f.voice.pc;
  pc.iceGatheringState='gathering';
  await assert.rejects(f.voice.waitForIceGathering(pc,f.voice.generation,18),/ICE/);
  assert.equal(f.requests.filter(x=>x[0]==='/api/voice/sessions').length,initial);
  await f.voice.stop();
});
