const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/software-manager.js','utf8');
const id='10000000-0000-4000-8000-000000000001';
const now=Date.now();
const plan={package_id:'Example.Editor',version:'1.2.3',source:'winget',scope:'user',
  accept_source_agreements:true,accept_package_agreements:true,allow_reboot:false};
const hash='a'.repeat(64);
const cap={connected:true,metrics_available:true,
  capabilities:['software.search','software.inspect','software.inventory','software.install'],
  software:{discovery_enabled:true,installation_enabled:true}};
const receipt=(action,payload,state='pending',result=null)=>({id,action,payload,state,result,digest:'b'.repeat(64),
  created_at:new Date(now).toISOString(),expires_at:new Date(now+300000).toISOString()});
const installResult=(p=plan)=>({status:'succeeded',installed:{package_id:p.package_id,version:p.version,source:p.source},
  evidence:{kind:'winget_export_json',packages:[{package_id:p.package_id,version:p.version,source:p.source}]},
  verification:{status:'agent_verified',method:'winget_export_json'}});

function harness(handler){
  const elements=new Map(),calls=[];
  let current=now;
  class FakeElement {
    constructor(){this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;
      this.textContent='';this.dataset={};this.children=[];this.events={};
      this.classList={contains:()=>false};}
    addEventListener(type,handler){this.events[type]=handler;}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    showModal(){this.open=true;}
    close(){this.open=false;}
    set innerHTML(value){throw Error('Untrusted data must never be rendered as HTML');}
  }
  const document={readyState:'loading',hidden:false,addEventListener(){},
    getElementById(name){if(!elements.has(name))elements.set(name,new FakeElement());return elements.get(name);},
    createElement(){return new FakeElement();}};
  const window={};
  vm.runInNewContext(source,{window,document,Date,Set,Array,Number,String,Boolean,JSON,Error,Promise,
    setTimeout,clearTimeout,setInterval,clearInterval});
  const api=async(path,options={})=>{
    const call={path,method:options.method||'GET',body:options.body?JSON.parse(options.body):null};
    calls.push(call);
    if(handler){const handled=await handler(call);if(handled!==undefined)return handled;}
    if(path==='/api/operator/capabilities')return cap;
    if(path==='/api/operator/history?limit=40')return {requests:[]};
    if(path.includes('/stream?'))return {events:[]};
    throw Error('Unexpected API call '+path);
  };
  const manager=new window.SonicSoftware.SoftwareManager({api,autoRefresh:false,now:()=>current,
    pause:async(ms)=>{current+=ms;}});
  function setPlan(p=plan){
    elements.get('softwarePackage').value=p.package_id;
    elements.get('softwareVersion').value=p.version;
    elements.get('softwareSourceAgreement').checked=p.accept_source_agreements;
    elements.get('softwarePackageAgreement').checked=p.accept_package_agreements;
    manager.inspection={plan:p,plan_sha256:hash,expires_at:current+1800000,metadata:'Publisher metadata'};
    manager.cap=cap;manager.controls();
  }
  return {window,manager,elements,calls,setPlan,setClock:value=>{current=value;}};
}

test('plan requires fixed source and scope, exact version and explicit booleans',()=>{
  const {window}=harness();const {validPlan}=window.SonicSoftware;
  assert.equal(validPlan(plan),true);
  for(const changed of [{...plan,scope:'machine'},{...plan,source:'custom'},
    {...plan,version:'latest'},{...plan,allow_reboot:true},
    {...plan,installer_url:'https://untrusted.invalid/setup.exe'},
    {...plan,accept_package_agreements:'true'}])assert.equal(validPlan(changed),false);
});

test('success text requires installed ID, version, source and matching inventory evidence',()=>{
  const {window}=harness();const {receiptLabel,installedEvidenceMatches}=window.SonicSoftware;
  const record=receipt('software.install',{plan,plan_sha256:hash},'done',installResult());
  assert.equal(installedEvidenceMatches(record),true);
  assert.match(receiptLabel(record),/terverifikasi/);
  const missing=receipt('software.install',{plan,plan_sha256:hash},'done',{status:'succeeded',exit_code:0});
  assert.equal(installedEvidenceMatches(missing),false);
  assert.match(receiptLabel(missing),/belum terverifikasi/);
  const changed=JSON.parse(JSON.stringify(record));changed.result.evidence.packages[0].version='9.0';
  assert.equal(installedEvidenceMatches(changed),false);
  const failed=receipt('software.install',{plan},'failed',{status:'reconciliation_required'});
  assert.match(receiptLabel(failed),/belum pasti/);
});

test('initialization does not submit operations or preaccept agreements',()=>{
  const {calls,elements}=harness();
  assert.equal(calls.length,0);
  assert.equal(elements.get('softwareSourceAgreement').checked,false);
  assert.equal(elements.get('softwarePackageAgreement').checked,false);
  assert.equal(elements.get('softwareReviewInstall').disabled,true);
});

test('double search click before capability response creates and confirms one readonly job',async()=>{
  let release;const gate=new Promise(resolve=>{release=resolve;});
  const payload={query:'video editor',accept_source_agreements:false};
  const {manager,calls}=harness(async call=>{
    if(call.path==='/api/operator/capabilities'){await gate;return cap;}
    if(call.path==='/api/operator/requests')return receipt('software.search',call.body.payload);
    if(call.path.endsWith('/confirm'))return {state:'queued'};
    if(call.path==='/api/operator/requests/'+id)return receipt('software.search',payload,'done',
      {status:'succeeded',evidence:{kind:'winget_search_raw',stdout:'Example.Editor 1.2.3'}});
  });
  const first=manager.runRead('software.search',payload);
  const second=manager.runRead('software.search',payload);
  release();await Promise.all([first,second]);
  assert.equal(calls.filter(call=>call.path==='/api/operator/requests').length,1);
  assert.equal(calls.filter(call=>call.path.endsWith('/confirm')).length,1);
  assert.deepEqual(calls.find(call=>call.path==='/api/operator/requests').body,{action:'software.search',payload});
});

test('install preview creates a pending request; explicit final click alone queues it',async()=>{
  const installPayload={plan,plan_sha256:hash};
  const {manager,calls,elements,setPlan}=harness(call=>{
    if(call.path==='/api/operator/requests')return receipt('software.install',installPayload);
    if(call.path.endsWith('/confirm'))return {state:'queued'};
    if(call.path==='/api/operator/requests/'+id)return receipt('software.install',installPayload,'done',installResult());
  });
  setPlan();await manager.reviewInstall();
  assert.equal(elements.get('softwareApproval').open,true);
  assert.equal(calls.filter(call=>call.path.endsWith('/confirm')).length,0);
  await Promise.all([manager.approveInstall(),manager.approveInstall()]);
  assert.equal(calls.filter(call=>call.path.endsWith('/confirm')).length,1);
  assert.equal(calls.filter(call=>call.path==='/api/operator/requests').length,1);
  assert.match(elements.get('softwareStatus').textContent,/terverifikasi/);
});

test('changing selected package or agreements invalidates installation plan',async()=>{
  const {manager,elements,setPlan,calls}=harness();setPlan();
  elements.get('softwarePackageAgreement').checked=false;
  elements.get('softwarePackageAgreement').events.change();
  assert.equal(manager.currentPlan(),false);
  assert.equal(elements.get('softwareReviewInstall').disabled,true);
  await manager.reviewInstall();
  assert.equal(calls.some(call=>call.method==='POST'),false);
});

test('lost confirmation response reconciles same request without resubmitting installer',async()=>{
  const installPayload={plan,plan_sha256:hash};let checks=0;
  const {manager,setPlan,calls}=harness(call=>{
    if(call.path==='/api/operator/requests')return receipt('software.install',installPayload);
    if(call.path.endsWith('/confirm'))throw Error('connection interrupted after server accepted');
    if(call.path==='/api/operator/requests/'+id){checks++;return checks===1?
      receipt('software.install',installPayload,'leased'):
      receipt('software.install',installPayload,'done',installResult());}
  });
  setPlan();await manager.reviewInstall();await manager.approveInstall();
  assert.equal(calls.filter(call=>call.path==='/api/operator/requests').length,1);
  assert.equal(calls.filter(call=>call.path.endsWith('/confirm')).length,1);
  assert.equal(checks,2);
  assert.equal(manager.active,null);
});

test('unconfirmed request after network error stays pending and is not silently reapproved',async()=>{
  const payload={plan,plan_sha256:hash};
  const {manager,setPlan,calls,elements}=harness(call=>{
    if(call.path==='/api/operator/requests')return receipt('software.install',payload);
    if(call.path.endsWith('/confirm'))throw Error('network');
    if(call.path==='/api/operator/requests/'+id)return receipt('software.install',payload);
  });
  setPlan();await manager.reviewInstall();await manager.approveInstall();
  assert.equal(calls.filter(call=>call.path.endsWith('/confirm')).length,1);
  assert.equal(manager.needsReconcile,true);
  assert.match(elements.get('softwareStatus').textContent,/belum disetujui/);
});

test('untrusted metadata is rendered as text and historic inspections do not renew validity',()=>{
  const {manager,elements}=harness();
  const record=receipt('software.inspect',{},'done',{plan,plan_sha256:hash,
    evidence:{kind:'winget_show_raw',stdout:'<img src=x onerror=alert(1)>\nPublisher: Example'}});
  record.created_at=new Date(now-31*60*1000).toISOString();
  manager.showResult(record);
  assert.match(elements.get('softwareOutput').textContent,/<img src=x/);
  assert.equal(manager.currentPlan(),false);
});

test('history recovery of pending install reopens exact review and never confirms automatically',async()=>{
  const payload={plan,plan_sha256:hash};
  const {manager,calls,elements}=harness(call=>{
    if(call.path==='/api/operator/requests/'+id)return receipt('software.install',payload);
  });
  await manager.openHistory(receipt('software.install',payload));
  assert.equal(elements.get('softwareApproval').open,true);
  assert.equal(calls.some(call=>call.path.endsWith('/confirm')),false);
});

test('old companions and disabled software flags cannot submit even from direct method calls',async()=>{
  const {manager,calls}=harness(call=>{
    if(call.path==='/api/operator/capabilities')return {...cap,capabilities:['file.list'],
      software:{discovery_enabled:false,installation_enabled:false}};
  });
  await manager.runRead('software.inventory',{});
  assert.equal(calls.some(call=>call.method==='POST'),false);
});

test('late installation evidence keeps cancellation visible instead of reviving completed status',()=>{
  const {manager,window,elements}=harness();
  const record=receipt('software.install',{plan,plan_sha256:hash},'cancelled',installResult());
  assert.match(window.SonicSoftware.receiptLabel(record),/dibatalkan/);
  assert.match(window.SonicSoftware.receiptLabel(record),/bukti akhir/);
  manager.showResult(record);
  assert.equal(elements.get('softwareStatus').dataset.state,'unknown');
});
