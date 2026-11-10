const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/model-router-v101.js','utf8');

function harness({deepseekKey=true,consent=true,override,extraModel}={}){
  const elements=new Map(),calls=[],dialogs=[];
  const models=[
    {provider:'openai',model:'gpt-4.1-mini',label:'OpenAI · GPT-4.1 mini',key_configured:true,selected:true},
    {provider:'openrouter',model:'z-ai/glm-5.3-prime',label:'OpenRouter · GLM-5.3 Prime',key_configured:true,selected:false},
    {provider:'deepseek',model:'deepseek-flash',label:'DeepSeek · Flash',key_configured:deepseekKey,selected:false},
    ...(extraModel?[extraModel]:[]),
  ];
  const state={models,selected:{provider:'openai',model:'gpt-4.1-mini',key_configured:true}};
  class Element {
    constructor(tag='div'){
      this.tagName=tag;this.value='';this.textContent='';this.children=[];this.dataset={};
      this.events={};this.disabled=false;this.selected=false;this.className='';
      this.classList={contains:value=>value==='hidden'};
    }
    append(...nodes){
      this.children.push(...nodes);
      if(this.tagName==='select')for(const node of nodes)if(node.selected)this.value=node.value;
    }
    replaceChildren(...nodes){this.children=[];if(this.tagName==='select')this.value='';this.append(...nodes);}
    addEventListener(type,handler){(this.events[type]??=[]).push(handler);}
    click(){return Promise.all((this.events.click||[]).map(handler=>handler()));}
    set innerHTML(_){throw Error('Provider data must be rendered as text, never HTML');}
  }
  function element(id){
    if(!elements.has(id))elements.set(id,new Element(id==='brainModelSelect'?'select':'div'));
    return elements.get(id);
  }
  const document={readyState:'complete',getElementById:element,
    createElement:tag=>new Element(tag),querySelector:()=>element('setupNavigation')};
  const window={};
  for(const key of ['localStorage','sessionStorage'])Object.defineProperty(window,key,{
    get(){throw Error('Model selection and keys must not use browser storage');}
  });
  const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(data)});
  const fetch=async(path,options={})=>{
    const call={path,method:options.method||'GET',headers:options.headers,
      body:options.body?JSON.parse(options.body):null,credentials:options.credentials};
    calls.push(call);
    if(override){const value=await override(call,state);if(value)return response(value.data,value.status);}
    if(path==='/api/session')return response({authenticated:true,csrf:'synthetic-owner-csrf'});
    if(path==='/api/models')return response({...state,usage:[]});
    if(path==='/api/models/selection'){
      const choice=state.models.find(model=>model.provider===call.body.provider&&model.model===call.body.model);
      assert.ok(choice);
      state.selected={provider:choice.provider,model:choice.model,key_configured:choice.key_configured};
      state.models=state.models.map(model=>({...model,selected:model===choice}));
      return response({saved:true,selected:state.selected});
    }
    throw Error('Unexpected network call '+path);
  };
  class MutationObserver {observe(){}}
  vm.runInNewContext(source,{document,window,fetch,MutationObserver,console,
    confirm:message=>{dialogs.push(message);return consent;}});
  const settle=()=>new Promise(resolve=>setImmediate(resolve));
  const choose=async value=>{
    element('brainModelSelect').value=value;
    for(const handler of element('brainModelSelect').events.change||[])handler();
    await element('applyBrainModel').click();
    await settle();
  };
  const textOf=node=>node.textContent+node.children.map(textOf).join(' ');
  return {calls,dialogs,elements,state,settle,choose,element,textOf};
}

test('provider status exposes key names and configured booleans without claiming a live connection',async()=>{
  const h=harness({deepseekKey:false});await h.settle();
  const row=h.element('brainProviderStatus').children.find(node=>node.dataset.provider==='deepseek');
  assert.match(h.textOf(row),/DeepSeek/);
  assert.match(h.textOf(row),/DEEPSEEK_API_KEY/);
  assert.match(h.textOf(row),/Key belum diisi/);
  assert.doesNotMatch(h.textOf(row),/verified|connected|terhubung/i);
  assert.equal(h.element('brainModelSelect').children.find(node=>node.value==='deepseek|deepseek-flash').disabled,true);
  assert.equal(h.calls.some(call=>call.method!=='GET'),false);
});

test('DeepSeek activation discloses the correct recipient and sends only model choice with owner CSRF',async()=>{
  const h=harness();await h.settle();await h.choose('deepseek|deepseek-flash');
  assert.equal(h.dialogs.length,1);
  assert.match(h.dialogs[0],/langsung ke DeepSeek/);
  assert.match(h.dialogs[0],/Memory Vault/);
  assert.match(h.dialogs[0],/OpenAI Realtime Voice dan Vision tidak berubah/);
  assert.doesNotMatch(h.dialogs[0],/ke OpenRouter/);
  const writes=h.calls.filter(call=>call.method==='PUT');
  assert.equal(writes.length,1);
  assert.deepEqual(writes[0].body,{provider:'deepseek',model:'deepseek-flash'});
  assert.equal(writes[0].headers['X-Sonic-CSRF'],'synthetic-owner-csrf');
  assert.equal(writes[0].credentials,'same-origin');
  assert.equal(h.state.selected.provider,'deepseek');
  assert.equal(h.element('applyBrainModel').disabled,true);
  assert.equal(h.calls.some(call=>call.path==='/api/setup/test-provider'),false);
});

for(const keyValue of [false,'true'])test('missing or non-boolean DeepSeek key state blocks activation: '+keyValue,async()=>{
  const h=harness({deepseekKey:keyValue});await h.settle();
  await h.choose('deepseek|deepseek-flash');
  assert.equal(h.element('applyBrainModel').disabled,true);
  assert.equal(h.dialogs.length,0);
  assert.equal(h.calls.some(call=>call.method==='PUT'),false);
});

test('declining provider context sharing preserves the selected model and performs no mutation',async()=>{
  const h=harness({consent:false});await h.settle();await h.choose('deepseek|deepseek-flash');
  assert.equal(h.dialogs.length,1);
  assert.equal(h.state.selected.provider,'openai');
  assert.equal(h.calls.some(call=>call.method!=='GET'),false);
});

test('OpenRouter retains its downstream-provider disclosure',async()=>{
  const h=harness();await h.settle();await h.choose('openrouter|z-ai/glm-5.3-prime');
  assert.match(h.dialogs[0],/ke OpenRouter serta penyedia model/);
  assert.doesNotMatch(h.dialogs[0],/langsung ke DeepSeek/);
  assert.equal(h.state.selected.provider,'openrouter');
});

test('an unrecognized server provider cannot inherit the OpenAI confirmation or be activated',async()=>{
  const h=harness({extraModel:{provider:'unreviewed',model:'model',label:'Unreviewed model',
    key_configured:true,selected:false}});await h.settle();await h.choose('unreviewed|model');
  assert.equal(h.element('applyBrainModel').disabled,true);
  assert.equal(h.dialogs.length,0);
  assert.equal(h.calls.some(call=>call.method==='PUT'),false);
});

test('an expired owner session removes model and key status instead of retaining an active claim',async()=>{
  const h=harness({override:call=>call.method==='PUT'?{status:401,data:{detail:'Unauthorized'}}:undefined});
  await h.settle();await h.choose('deepseek|deepseek-flash');
  assert.equal(h.element('brainModelSelect').children.length,0);
  assert.equal(h.element('brainProviderStatus').children.length,0);
  assert.equal(h.element('brainModelMetrics').children.length,0);
  assert.equal(h.element('applyBrainModel').disabled,true);
  assert.match(h.element('brainModelStatus').textContent,/Session owner berakhir/);
});

test('duplicate activation clicks submit one selection and never run a paid connection test',async()=>{
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const h=harness({override:async call=>{if(call.method==='PUT')await gate;}});
  await h.settle();
  const first=h.choose('deepseek|deepseek-flash');
  const second=h.choose('deepseek|deepseek-flash');
  release();await Promise.all([first,second]);
  assert.equal(h.dialogs.length,1);
  assert.equal(h.calls.filter(call=>call.method==='PUT').length,1);
  assert.equal(h.calls.some(call=>call.path==='/api/setup/test-provider'),false);
});
