/* SONIC V0.8 PC Command Center: exact approval, stdout/stderr stream,
 * cancellation and Task Manager. No third-party libraries or credential storage.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const READY = new Set(['done','failed','cancelled','expired']);
  const TERMINATE_BLOCKED = new Set([
    'system','registry','smss.exe','csrss.exe','wininit.exe','services.exe',
    'lsass.exe','winlogon.exe','svchost.exe','dwm.exe','msmpeng.exe',
    'securityhealthservice.exe','python.exe','pythonw.exe',
    'powershell.exe','pwsh.exe','terminal64.exe','terminal.exe','metatrader5.exe'
  ]);
  const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
  const format = (v,suffix='') => Number.isFinite(v)
    ? (Math.round(v*10)/10).toLocaleString('id-ID')+suffix : 'N/A';
  const mib = b => Number.isFinite(b) ? format(b/1048576,' MiB') : 'N/A';
  const compact = b => Number.isFinite(b) ? format(b/1024,' KiB/s') : 'N/A';
  function node(tag,cls,text){
    const el=document.createElement(tag);
    if(cls)el.className=cls;
    if(text!==undefined)el.textContent=String(text);
    return el;
  }

  class SonicPCCommand {
    constructor(){
      this.pending=null;this.active=null;this.capabilities=[];this.lastSample='';
      this.samples=[];this.cursor=0;this.polling=false;this.busy=false;
      this.canvas=$('pcTrend');this.dialog=$('pcApproval');
      if(!this.canvas||!$('pcCommandCenter'))return;
      $('pcReview').addEventListener('click',()=>this.reviewPowerShell());
      $('pcStop').addEventListener('click',()=>this.stopActive());
      $('pcClear').addEventListener('click',()=>{$('pcOutput').textContent='';});
      $('pcRefreshHistory').addEventListener('click',()=>this.history());
      $('pcApprovalConfirm').addEventListener('click',()=>this.approve());
      $('pcApprovalCancel').addEventListener('click',()=>this.reject());
      this.dialog.addEventListener('cancel',e=>{e.preventDefault();this.reject();});
      for(const btn of document.querySelectorAll('[data-pc-example]')){
        btn.addEventListener('click',()=>{
          $('pcScript').value=btn.dataset.pcExample;
          $('pcScript').focus();
        });
      }
      this.timer=setInterval(()=>{
        if(!document.hidden && !$('devicesPanel').classList.contains('hidden')){
          this.refresh().catch(error=>this.status(error.message,'failed'));
        }
      },9000);
      this.drawChart();
    }
    async api(path,opts={}){
      const session=await fetch('/api/session',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
      if(!session.authenticated)throw Error('Owner login required');
      const headers={'Content-Type':'application/json',...(opts.headers||{})};
      if(opts.method&&opts.method!=='GET')headers['X-Sonic-CSRF']=session.csrf;
      const response=await fetch(path,{credentials:'same-origin',cache:'no-store',...opts,headers});
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'HTTP '+response.status);
      return body;
    }
    status(text,state='idle'){
      $('pcExecState').textContent=text;
      $('pcExecState').dataset.state=state;
    }
    append(text){
      const target=$('pcOutput');
      target.textContent=(target.textContent+text).slice(-58000);
      target.scrollTop=target.scrollHeight;
    }
    async refresh(){
      const [telemetry,cap]=await Promise.all([
        this.api('/api/device/metrics'),
        this.api('/api/operator/capabilities')
      ]);
      this.capabilities=cap.capabilities||[];
      const online=telemetry.connected&&telemetry.metrics_available;
      const broker=cap.powershell_enabled&&this.capabilities.includes('powershell.exec');
      $('pcBrokerStatus').textContent=!telemetry.connected?'PC offline':
        broker?'PowerShell ready':'PowerShell not enabled on both sides';
      $('pcBrokerStatus').classList.toggle('online',broker);
      $('pcBrokerStatus').classList.toggle('offline',!broker);
      $('pcReview').disabled=!broker||this.busy;
      if(!this.busy&&!READY.has($('pcExecState').dataset.state))this.status(broker?'Ready for owner review':'PowerShell disabled until local and Railway opt-in');
      const metrics=online?(telemetry.metrics||{}):{};
      $('pcSampleTime').textContent=online?('Authenticated sample · '+telemetry.metrics_age_seconds+'s ago'):'Telemetry unavailable';
      $('pcCPU').textContent=format(metrics.cpu_usage_percent,'%');
      $('pcRAM').textContent=format(metrics.ram_used_percent,'%');
      $('pcNet').textContent=compact(metrics.network_rx_bytes_per_second)+' ↓ / '+
        compact(metrics.network_tx_bytes_per_second)+' ↑';
      const gpu=(metrics.gpus||[])[0];
      $('pcGPU').textContent=gpu?(gpu.name+' · '+format(gpu.usage_percent,'%')):'Not reported';
      const sample=telemetry.sampled_at;
      if(online&&sample&&sample!==this.lastSample){
        this.lastSample=sample;
        this.samples.push({
          cpu:Number.isFinite(metrics.cpu_usage_percent)?metrics.cpu_usage_percent:null,
          ram:Number.isFinite(metrics.ram_used_percent)?metrics.ram_used_percent:null
        });
        if(this.samples.length>60)this.samples.shift();
        this.drawChart();
      }
      this.processes(metrics.processes||[],this.capabilities.includes('process.terminate')&&online);
    }
    processes(items,canTerminate){
      const target=$('pcProcessList');target.replaceChildren();
      if(!items.length){
        target.append(node('p','small-note','No fresh authenticated processes.'));return;
      }
      const header=node('div','pc-process-row pc-process-heading');
      for(const h of ['Process','PID','CPU','RAM','Control'])header.append(node('span','',h));
      target.append(header);
      for(const p of items.slice(0,18)){
        const row=node('div','pc-process-row');
        row.append(node('span','',p.name||'Unknown'),node('span','',p.pid),
          node('span','',format(p.cpu_percent,'%')),node('span','',mib(p.ram_bytes)));
        const end=node('button','', 'End task');end.type='button';
        const blocked=TERMINATE_BLOCKED.has(String(p.name||'').toLowerCase()) ||
          !/^[a-zA-Z0-9_. -]{1,100}$/.test(String(p.name||'')) || p.pid<=4;
        end.disabled=!canTerminate||blocked||this.busy;
        end.title=blocked?'Protected Windows/SONIC process':'Review exact PID and executable before termination';
        end.addEventListener('click',()=>this.propose('process.terminate',{
          pid:p.pid,expected_name:p.name
        }));
        row.append(end);target.append(row);
      }
    }
    drawChart(){
      const canvas=this.canvas;if(!canvas)return;
      const dpr=Math.min(2,devicePixelRatio||1),w=Math.max(40,canvas.clientWidth||600),
        h=Math.max(40,canvas.clientHeight||150);
      canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
      const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
      ctx.fillStyle='#000000';ctx.fillRect(0,0,w,h);
      const series=[{key:'cpu',color:'#156bff'},{key:'ram',color:'#ff9f2f'}];
      if(this.samples.length<2){
        ctx.fillStyle='#4da3ff';ctx.font='12px sans-serif';
        ctx.fillText('Waiting for two verified Windows readings...',14,h/2);
        return;
      }
      for(const spec of series){
        ctx.beginPath();ctx.lineWidth=2;ctx.strokeStyle=spec.color;
        let drawing=false;
        this.samples.forEach((sample,index)=>{
          if(!Number.isFinite(sample[spec.key])){drawing=false;return;}
          const x=8+(w-16)*index/Math.max(1,this.samples.length-1);
          const y=h-10-(h-20)*Math.min(100,Math.max(0,sample[spec.key]))/100;
          if(!drawing)ctx.moveTo(x,y);else ctx.lineTo(x,y);
          drawing=true;
        });
        ctx.stroke();
      }
    }
    async reviewPowerShell(){
      const command=$('pcScript').value.trim();
      const timeout_seconds=Number($('pcTimeout').value);
      if(!command)return this.status('Enter a PowerShell command first','failed');
      return this.propose('powershell.exec',{command,timeout_seconds});
    }
    async propose(action,payload){
      if(this.busy||this.pending)return;
      try{
        const receipt=await this.api('/api/operator/requests',{
          method:'POST',body:JSON.stringify({action,payload})
        });
        this.pending=receipt;
        const windowNotice=receipt.action.startsWith('window.')
          ? receipt.action==='window.close'&&receipt.payload.app==='metatrader5'
            ? 'PERINGATAN: menutup MetaTrader 5 dapat menghentikan EA atau trailing stop lokal. Posisi broker tidak otomatis ditutup. WM_CLOSE tanpa force-kill.'
            : receipt.action==='window.close'
              ? 'Penutupan normal mungkin membuka dialog Simpan. Tidak ada force-kill.'
              : 'Hanya aplikasi allowlisted, tanpa shell atau order trading.'
          : null;
        $('pcApprovalText').textContent=JSON.stringify({
          device_id:'TRADEVICEPC',
          action:receipt.action,payload:receipt.payload,
          ...(windowNotice?{warning:windowNotice}:{}),
          digest:receipt.digest,expires_at:receipt.expires_at
        },null,2);
        this.dialog.showModal();
        this.status('Waiting for explicit owner approval');
      }catch(error){this.status('Review failed: '+error.message,'failed');}
    }
    async reject(){
      if(this.dialog.open)this.dialog.close();
      const pending=this.pending;this.pending=null;
      if(pending){
        try{await this.api('/api/operator/requests/'+pending.id,{method:'DELETE'});}
        catch(error){this.status('Review expired: '+error.message,'failed');return;}
      }
      if(!this.busy)this.status('Approval declined');
    }
    async approve(){
      const request=this.pending;if(!request)return;
      $('pcApprovalConfirm').disabled=true;
      try{
        await this.api('/api/operator/requests/'+request.id+'/confirm',{
          method:'POST',body:JSON.stringify({confirm:true,digest:request.digest})
        });
        this.pending=null;this.dialog.close();this.busy=true;
        this.active=request;this.cursor=0;
        $('pcStop').disabled=false;$('pcReview').disabled=true;
        $('pcOutput').textContent='> '+request.action+'\n'+
          (request.action==='powershell.exec'?request.payload.command:
           request.action.startsWith('window.')?JSON.stringify(request.payload,null,2):
           'PID '+request.payload.pid+'\n')+'\n';
        this.status('Queued for TRADEVICEPC','queued');
        await this.watch(request.id);
      }catch(error){
        this.pending=null;this.dialog.close();
        this.status('Approval failed: '+error.message,'failed');
      }finally{
        $('pcApprovalConfirm').disabled=false;
        this.active=null;this.busy=false;
        $('pcStop').disabled=true;
        this.refresh().catch(()=>{});
        this.history().catch(()=>{});
      }
    }
    async watch(id){
      for(let attempt=0;attempt<200;attempt++){
        try{
          const [stream,request]=await Promise.all([
            this.api('/api/operator/requests/'+id+'/stream?after='+this.cursor),
            this.api('/api/operator/requests/'+id)
          ]);
          for(const e of stream.events||[]){
            if(e.sequence<=this.cursor)continue;
            this.cursor=e.sequence;
            this.append((e.channel==='stderr'?'[stderr] ':
                         e.channel==='system'?'[system] ':'')+e.text);
          }
          this.status('State: '+request.state,request.state);
          if(READY.has(request.state)){
            this.append('\n[SONIC] '+request.state+' / '+
              JSON.stringify(request.result||{})+'\n');
            return;
          }
        }catch(error){
          this.status('Connection issue: '+error.message,'failed');
        }
        await sleep(1000);
      }
      this.status('Polling ended; inspect command history','expired');
    }
    async stopActive(){
      const request=this.active;
      if(!request)return;
      $('pcStop').disabled=true;
      this.status('Cancellation requested','cancelled');
      try{
        await this.api('/api/operator/requests/'+request.id,{method:'DELETE'});
        this.append('\n[SONIC] Cancel requested. Device will stop its command process tree.\n');
      }catch(error){
        this.append('\n[SONIC] Could not cancel: '+error.message+'\n');
      }
    }
    async history(){
      try{
        const result=await this.api('/api/operator/history?limit=18');
        const target=$('pcHistory');target.replaceChildren();
        if(!result.requests.length){
          target.append(node('p','small-note','No approved or proposed operations yet.'));
          return;
        }
        for(const record of result.requests){
          const row=node('div','pc-audit-row');
          const stamp=node('time','',record.created_at?.slice(0,19)||'');
          const sample=record.action==='powershell.exec'?
            (record.payload?.command||'').replace(/\s+/g,' ').slice(0,150):
            record.action+' '+JSON.stringify(record.payload||{}).slice(0,100);
          const snippet=node('code','',sample);
          const state=node('span','pc-audit-state',record.state);
          state.dataset.state=record.state;
          row.append(stamp,snippet,state);target.append(row);
        }
      }catch(error){
        if($('pcHistory'))$('pcHistory').textContent='History unavailable: '+error.message;
      }
    }
  }
  const init=()=>{if($('pcCommandCenter'))window.sonicPC=new SonicPCCommand();};
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',init,{once:true});
  }else init();
})();
