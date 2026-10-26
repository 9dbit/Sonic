const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/voice.js','utf8');

function setup(onTranscript){
  const win={};
  vm.runInNewContext(source,{window:win,console,Promise,JSON,Error,Date,Math,
    setInterval,clearInterval,setTimeout,clearTimeout});
  const outbound=[],notes=[];
  const v=new win.SonicVoice({api:async()=>({}),onTranscript,
    onError:err=>notes.push(err)});
  v.setState('listening');
  v.sessionId='synthetic_owner_session';
  v.dc={readyState:'open',send:e=>outbound.push(JSON.parse(e))};
  return {v,outbound,notes};
}

test('screenshot phrase is routed once and spoken as an isolated no-tools verified status',async()=>{
  let received=0;
  const h=setup(async(role,text,meta)=>{
    received++;
    assert.equal(text,'Buatkan di desktop dengan nama foldernya Today.');
    assert.equal(meta.itemId,'item_iPhone_11');
    return {handled:true,route:'chat_pc_action',
      reply:'Saya jalankan folder Today di Desktop TRADEVICEPC. Menunggu konfirmasi Windows agent.'};
  });
  const event={type:'conversation.item.input_audio_transcription.completed',
    item_id:'item_iPhone_11',transcript:'Buatkan di desktop dengan nama foldernya Today.'};
  h.v.event(event,0);
  h.v.event(event,0);
  await h.v.turnChain;
  assert.equal(received,1);
  assert.equal(h.outbound.filter(e=>e.type==='response.create').length,1);
  const response=h.outbound.find(e=>e.type==='response.create').response;
  assert.equal(response.conversation,'none');
  assert.equal(response.tool_choice,'none');
  assert.equal(response.output_modalities[0],'audio');
  assert.equal(response.tools.length,0);
  assert.match(response.input[0].content[0].text,/Menunggu konfirmasi/);
  assert.match(response.instructions,/Do not invent tool calls/);
  assert.equal(h.notes.length,0);
});

test('voice results queue behind active speech and cannot trigger generic response',async()=>{
  const h=setup(async()=>({handled:true,reply:'Perintah diterima, menunggu hasil.'}));
  h.v.event({type:'conversation.item.input_audio_transcription.completed',
    item_id:'item_cmd',transcript:'buat folder today di desktop'},0);
  await h.v.turnChain;
  assert.equal(h.outbound.filter(e=>e.type==='response.create').length,1);
  h.v.verifiedPCReceipt('Folder Desktop berhasil dibuat di TRADEVICEPC: Desktop\\Today');
  assert.equal(h.outbound.filter(e=>e.type==='response.create').length,1);
  h.v.event({type:'response.done'},0);
  const responses=h.outbound.filter(e=>e.type==='response.create');
  assert.equal(responses.length,2);
  assert.deepEqual(Array.from(responses[1].response.tools),[]);
  assert.match(responses[1].response.input[0].content[0].text,/berhasil dibuat/);
});

test('general conversation remains normal; no invented status injected',async()=>{
  const h=setup(async()=>({handled:false}));
  h.v.event({type:'conversation.item.input_audio_transcription.completed',
    item_id:'smalltalk',transcript:'Apa kabar?'},0);
  await h.v.turnChain;
  const events=h.outbound.filter(e=>e.type==='response.create');
  assert.equal(events.length,1);
  assert.equal('response' in events[0],false);
  assert.equal(h.outbound.some(e=>JSON.stringify(e).includes('VERIFIED_SONIC_ACTION_ROUTE')),false);
});

test('repeated owner voice item never starts a duplicate desktop job via frontend',async()=>{
  let called=0;
  const h=setup(async()=>{called++;return {handled:true,reply:'Queued'};});
  for(let i=0;i<4;i++){
    h.v.event({type:'conversation.item.input_audio_transcription.completed',
      item_id:'same_recording',transcript:'buat folder Today di Desktop'},0);
  }
  await h.v.turnChain;
  assert.equal(called,1);
});
