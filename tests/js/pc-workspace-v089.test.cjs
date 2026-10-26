const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('web/pc-workspace-v089.js','utf8');

function harness({allow=false,connected=true}={}){
  const elements=new Map(), calls=[], messages=[];
  class FakeElement{
    constructor(tag='div'){
      this.tagName=tag;
      this.textContent='';
      this.value='';
      this.disabled=false;
      this.children=[];
      this.attributes={};
      this.events={};
      const classes=new Set();
      this.classList={
        add:name=>classes.add(name),
        remove:name=>classes.delete(name),
        contains:name=>classes.has(name),
        toggle:(name,force)=>{
          if(force===undefined)force=!classes.has(name);
          if(force)classes.add(name);else classes.delete(name);
          return force;
        }
      };
    }
    addEventListener(type,fn){this.events[type]=fn;}
    setAttribute(name,value){this.attributes[name]=String(value);}
    replaceChildren(...children){this.children=children;}
    append(...children){this.children.push(...children);}
  }
  const doc={
    createElement:tag=>new FakeElement(tag),
    getElementById:id=>{
      if(!elements.has(id))elements.set(id,new FakeElement());
      return elements.get(id);
    }
  };
  const window={};
  vm.runInNewContext(source,{window,document:doc,confirm:()=>allow,
    Promise,Date,JSON,Set,Error,Number,String,Math,RegExp,
    setTimeout,clearTimeout});
  const api=async(path,opts)=>{
    calls.push({path,method:opts?.method||'GET',body:opts?.body?JSON.parse(opts.body):null});
    if(path==='/api/integrations'){
      return {adapters:[{id:'windows-native',state:connected?'online':'offline',
        connected,current_capabilities:connected?['file.list','file.read']:[]}]};
    }
    if(path==='/api/operator/requests'){
      const body=JSON.parse(opts.body);
      return {id:'10000000-0000-4000-8000-000000000001',state:'pending',
        action:body.action,payload:body.payload,digest:'a'.repeat(64)};
    }
    if(path.includes('/confirm'))return {state:'queued'};
    if(path.startsWith('/api/operator/requests/')&&opts?.method==='DELETE')return {state:'cancelled'};
    if(path.startsWith('/api/operator/requests/')){
      return {state:'done',action:'file.list',payload:{path:'.'},
        result:{directory:'D:\\Sonic\\work',items:[
          {name:'Readme.md',kind:'file',bytes:14},
          {name:'Proyek',kind:'directory',bytes:null},
          {name:'secrets',kind:'directory',bytes:null}
        ],truncated:false}};
    }
    throw Error('Unexpected endpoint: '+path);
  };
  const pc=new window.SonicPCWorkspace({
    api,notify:message=>messages.push(message),
    cloud:{canLeave:()=>true,closePreview(){},async refresh(){}}
  });
  return {window,pc,elements,calls,messages,api};
}

test('Windows path is relative, bounded and never has secret or reserved segments',()=>{
  const {window}=harness();
  const {cleanRelative,joinPath}=window.SonicPCPath;
  assert.equal(cleanRelative('.'),' .'.trim());
  assert.equal(cleanRelative('Proyek/2026'),'Proyek/2026');
  assert.equal(joinPath('Proyek','Catatan.md','file'),'Proyek/Catatan.md');
  for(const value of ['..','../x','/root','C:/Users','foo\\bar','a//b',
                      'CON','folder/.ssh','folder/credentials','test.','file%20','a/$HOME']){
    assert.throws(()=>cleanRelative(value));
  }
  assert.throws(()=>cleanRelative('Proyek/malware.exe','file'));
  assert.throws(()=>cleanRelative('Proyek/token.md','file'));
  assert.throws(()=>joinPath('Proyek','../../other.md','file'));
  assert.throws(()=>cleanRelative('a/b/c/d/e/f'));
});

test('Receipt evidence matches only absolute Windows paths and requested suffix',()=>{
  const {window}=harness();
  const {pathEvidenceMatches}=window.SonicPCPath;
  assert.equal(pathEvidenceMatches('D:\\Sonic\\work\\Proyek\\Rapat.md','Proyek/Rapat.md'),true);
  assert.equal(pathEvidenceMatches('D:\\Sonic\\work\\Other.md','Proyek/Rapat.md'),false);
  assert.equal(pathEvidenceMatches('relative\\Rapat.md','Proyek/Rapat.md'),false);
  assert.equal(pathEvidenceMatches('\\\\srv\\share\\Rapat.md','Proyek/Rapat.md'),false);
  assert.equal(pathEvidenceMatches('D:\\Sonic\\work\\..\\Rapat.md','Rapat.md'),false);
});

test('Opening PC mode is metadata-only: no file data without a separate owner gesture',async()=>{
  const {pc,calls,elements}=harness({allow:false});
  await pc.switchMode('pc');
  assert.equal(pc.ready,true);
  assert.equal(pc.mode,'pc');
  assert.deepEqual(calls.map(c=>c.path),['/api/integrations']);
  await pc.run('file.list','.');
  assert.equal(calls.some(c=>c.path==='/api/operator/requests'),false);
  assert.match(elements.get('wsPcStatus').textContent,/online/);
  pc.clear();
  assert.equal(pc.mode,'cloud');
  assert.equal(elements.get('wsPcText').textContent,'');
});

test('Unavailable or stale companion cannot queue a PC file action',async()=>{
  const {pc,calls}=harness({connected:false,allow:true});
  await pc.switchMode('pc');
  await pc.run('file.list','.');
  assert.equal(calls.some(c=>c.path==='/api/operator/requests'),false);
});

test('User-confirmed read only listing queues exactly one request and uses authenticated receipt',async()=>{
  const {pc,calls,elements}=harness({allow:true});
  await pc.switchMode('pc');
  await pc.run('file.list','.');
  const submissions=calls.filter(c=>c.path==='/api/operator/requests');
  assert.equal(submissions.length,1);
  assert.deepEqual(submissions[0].body,{action:'file.list',payload:{path:'.'}});
  assert.equal(calls.filter(c=>c.path.endsWith('/confirm')).length,1);
  assert.equal(pc.path,'.');
  assert.equal(elements.get('wsPcList').children.length,3);
  assert.equal(elements.get('wsPcStatus').textContent.includes('agent-reported'),true);
  pc.clear();
  assert.equal(elements.get('wsPcList').children.length,0);
});
