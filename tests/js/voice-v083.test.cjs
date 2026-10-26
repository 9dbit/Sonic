const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/voice.js','utf8');

function harness(onTranscript){
  const win={};
  vm.runInNewContext(source,{window:win,console,Promise,JSON,Error,Date,Math,
    setInterval,clearInterval,setTimeout,clearTimeout});
  const emitted=[];
  const obj=new win.SonicVoice({
    api:async()=>({}),onTranscript,onError:message=>{throw Error(message);}
  });
  obj.setState('listening');
  obj.sessionId='synthetic-realtime-session';
  obj.dc={readyState:'open',send:x=>emitted.push(JSON.parse(x))};
  return {obj,emitted};
}

test('Realtime voice waits for owner transcript routing before response.create',async()=>{
  let release;
  const gate=new Promise(resolve=>release=resolve);
  const seen=[];
  const {obj,emitted}=harness(async(role,text,meta)=>{
    seen.push({role,text,meta});
    await gate;
    return {handled:true,reply:'Folder Today queued on Desktop'};
  });
  obj.event({type:'conversation.item.input_audio_transcription.completed',
     item_id:'item_441',transcript:'Buat folder Today di desktop Threadvice PC'},0);
  await Promise.resolve();
  assert.equal(emitted.length,0,'no early generic refusal should be emitted');
  release();
  await obj.turnChain;
  assert.equal(seen.length,1);
  assert.equal(seen[0].meta.itemId,'item_441');
  assert.equal(seen[0].meta.sessionId,'synthetic-realtime-session');
  assert.equal(emitted.filter(x=>x.type==='response.create').length,1);
  const receipt=emitted.find(x=>x.type==='conversation.item.create');
  assert.match(receipt.item.content[0].text,/VERIFIED_SONIC_ACTION_ROUTE/);
  assert.match(receipt.item.content[0].text,/queued/);
});

test('General voice conversation still responds without fake PC receipts',async()=>{
  const {obj,emitted}=harness(async()=>({handled:false}));
  obj.event({type:'conversation.item.input_audio_transcription.completed',
    item_id:'item_general',transcript:'Apa kabar?'},0);
  await obj.turnChain;
  assert.deepEqual(emitted.map(x=>x.type),['response.create']);
});

test('Silent commands do not trigger an unwanted AI response',async()=>{
  const {obj,emitted}=harness(async()=>({handled:true,silent:true}));
  obj.event({type:'conversation.item.input_audio_transcription.completed',
    item_id:'item_stop',transcript:'SONIC berhenti'},0);
  await obj.turnChain;
  assert.equal(emitted.length,0);
});

test('Only a verified agent receipt can prompt spoken completion',()=>{
  const {obj,emitted}=harness(async()=>({handled:false}));
  obj.verifiedPCReceipt('Folder Desktop berhasil dibuat: Today');
  assert.deepEqual(emitted.map(x=>x.type),[
    'conversation.item.create','response.create'
  ]);
  assert.match(emitted[0].item.content[0].text,/VERIFIED_SONIC_DEVICE_RESULT/);
});
