const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');

function setup(){
  const nodes=new Map(),writes=[];
  const state={models:[
    {provider:'openai',model:'gpt-4.1-mini',label:'OpenAI',key_configured:true,selected:true},
    {provider:'deepseek',model:'deepseek-flash',label:'DeepSeek',key_configured:true,selected:false}
  ],selected:{provider:'openai',model:'gpt-4.1-mini',key_configured:true},usage:[]};
  class Node{
    constructor(tag){this.tag=tag;this.children=[];this.events={};this.value='';this.dataset={};this.classList={contains:()=>true};}
    append(...items){this.children.push(...items);if(this.tag==='select')for(const i of items)if(i.selected)this.value=i.value;}
    replaceChildren(...items){this.children=[];if(this.tag==='select')this.value='';this.append(...items);}
    addEventListener(name,handler){this.events[name]=handler;}
    click(){return this.events.click?.();}
  }
  const get=id=>{if(!nodes.has(id))nodes.set(id,new Node(id==='brainModelSelect'?'select':'div'));return nodes.get(id);};
  const document={readyState:'complete',getElementById:get,createElement:tag=>new Node(tag),querySelector:()=>get('nav')};
  const fetch=async(path,options)=>{
    if(options.method!=='GET')writes.push(path);
    return {ok:true,status:200,json:async()=>structuredClone(path==='/api/session'?{authenticated:true,csrf:'fake'}:state)};
  };
  class MutationObserver{observe(){}}
  vm.runInNewContext(fs.readFileSync('web/model-router-v101.js','utf8'),{document,fetch,MutationObserver,confirm:()=>false});
  const settle=()=>new Promise(resolve=>setImmediate(resolve));
  const choose=()=>{get('brainModelSelect').value='deepseek|deepseek-flash';get('brainModelSelect').events.change();};
  return {get,state,writes,settle,choose,refresh:()=>get('nav').click()};
}

test('a completed provider test refresh cannot overwrite an unsaved model choice',async()=>{
  const h=setup();await h.settle();h.choose();
  assert.equal(h.get('applyBrainModel').disabled,false);
  await h.refresh();
  assert.equal(h.get('brainModelSelect').value,'deepseek|deepseek-flash');
  assert.equal(h.get('applyBrainModel').disabled,false);
  assert.deepEqual(h.writes,[]);
});

test('a disappeared provider key invalidates the draft instead of permitting activation',async()=>{
  const h=setup();await h.settle();h.choose();h.state.models[1].key_configured=false;
  await h.refresh();
  assert.equal(h.get('brainModelSelect').value,'openai|gpt-4.1-mini');
  assert.equal(h.get('applyBrainModel').disabled,true);
  assert.deepEqual(h.writes,[]);
});
