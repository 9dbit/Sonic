/* SONIC Productivity 1.5.1: owner-only Mission + Project Memory + Diagnostics. */
(() => {
  "use strict";
  const q=id=>document.getElementById(id);
  const base="/api/productivity";
  let csrf=null;
  let personalPreview=false;
  let project="sonic";
  const tag=(name,text,cls="")=>{const e=document.createElement(name);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
  const div=(cls="")=>tag("div",undefined,cls);
  async function api(path,options={}){
    const headers={"Content-Type":"application/json",...(csrf?{[personalPreview?"X-Sonic-Preview-CSRF":"X-Sonic-CSRF"]:csrf}:{})};
    const r=await fetch(path,{credentials:"same-origin",cache:"no-store",...options,headers});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"HTTP "+r.status);
    return data;
  }
  const status=(value)=>{const node=q("prodStatus");if(node)node.textContent=value;};
  const input=(id,hint,max=200)=>{const e=tag("input");e.id=id;e.placeholder=hint;e.maxLength=max;e.autocomplete="off";return e;};
  const button=(label,fn)=>{const b=tag("button",label,"prod-btn");b.type="button";b.addEventListener("click",async()=>{b.disabled=true;try{await fn();}catch(e){status(e.message);}finally{b.disabled=false;}});return b;};
  function setup(){
    if(q("productivityHub")||!q("devicesPanel"))return;
    const root=div("prod-hub");root.id="productivityHub";root.hidden=true;
    const intro=div("prod-header");
    intro.append(tag("h3","SONIC Missions & Productivity"),tag("p","Owner-only • project knowledge • reviewed missions • read-only diagnostics"));
    root.append(intro);
    const projectRow=div("prod-row");
    projectRow.append(tag("label","Project key"),input("prodProject","sonic",48),
      button("Open project",async()=>{project=q("prodProject").value.trim();await refreshAll();}));
    root.append(projectRow);
    const cols=div("prod-grid");
    const memory=div("prod-card");
    memory.append(tag("h4","Project Memory"));
    memory.append(input("prodFactTitle","Fact title",120));
    const note=tag("textarea");note.id="prodFactText";note.maxLength=3000;note.rows=3;note.placeholder="Verified project decision or fact";memory.append(note);
    memory.append(button("Save to project",async()=>{
      const r=await api(base+"/facts",{method:"POST",body:JSON.stringify({project_key:project,title:q("prodFactTitle").value,content:q("prodFactText").value})});
      q("prodFactTitle").value="";q("prodFactText").value="";status("Fact saved: "+r.fact.id.slice(0,8));await refreshFacts();
    }));
    const facts=div("prod-items");facts.id="prodFacts";memory.append(facts);
    const mission=div("prod-card");mission.append(tag("h4","Mission Plan"));
    mission.append(input("prodGoal","Mission goal",280));
    const steps=tag("textarea");steps.id="prodSteps";steps.rows=4;steps.placeholder="One step per line, up to 12 steps";mission.append(steps);
    mission.append(button("Create draft mission",async()=>{
      const lines=q("prodSteps").value.split("\n").map(x=>x.trim()).filter(Boolean);
      await api(base+"/missions",{method:"POST",body:JSON.stringify({project_key:project,goal:q("prodGoal").value,steps:lines})});
      q("prodGoal").value="";q("prodSteps").value="";status("Draft mission created. No PC action was executed.");await refreshMissions();
    }));
    const missions=div("prod-items");missions.id="prodMissions";mission.append(missions);
    cols.append(memory,mission);root.append(cols);
    const insights=div("prod-card");insights.append(tag("h4","Daily Briefing & Universal Search"));
    insights.append(button("Generate briefing",async()=>{
      const b=await api(base+"/briefing");
      q("prodInsights").textContent=JSON.stringify(b,null,2);
      status("Briefing from internal SONIC data only. No external inbox or calendar queried.");
    }));
    const searchRow=div("prod-row");
    searchRow.append(input("prodSearchQuery","Search SONIC cloud & project memory",80),
      button("Search",async()=>{
        const text=q("prodSearchQuery").value;
        const r=await api(base+"/search?q="+encodeURIComponent(text));
        q("prodInsights").textContent=JSON.stringify(r,null,2);
      }));
    insights.append(searchRow);
    const insightResults=tag("pre","Internal SONIC data only.","prod-result");
    insightResults.id="prodInsights";insights.append(insightResults);root.append(insights);
    const uptime=div("prod-card");uptime.id="prodInternetUptime";
    uptime.append(tag("h4","Internet Uptime Monitor • Last 24 hours"));
    const uptimeHead=div("prod-uptime-header");
    const uptimePct=tag("strong","NO DATA","prod-uptime-value");uptimePct.id="prodUptimePct";
    const uptimeState=tag("span","Waiting for Windows samples","prod-uptime-state");uptimeState.id="prodUptimeState";
    uptimeHead.append(uptimePct,uptimeState);
    uptime.append(uptimeHead);
    const uptimeStat=div("prod-grid");
    for(const [id,label] of [["prodUptimeCoverage","Measured coverage"],["prodUptimeDown","Observed downtime"],
                             ["prodUptimeUnknown","Unknown / PC offline"],["prodUptimeLatency","Avg HTTPS response"],
                             ["prodUptimeOutages","Observed interruptions"],["prodUptimeProbe","HTTPS probes passed"]]){
      const group=div("prod-uptime-stat");const value=tag("strong","--");value.id=id;
      group.append(tag("span",label),value);uptimeStat.append(group);
    }
    uptime.append(uptimeStat);
    const timeline=div("prod-uptime-timeline");timeline.id="prodUptimeTimeline";uptime.append(timeline);
    const outageList=div("prod-items");outageList.id="prodUptimeOutagesList";uptime.append(outageList);
    uptime.append(tag("p","30-second checks from TRADEVICEPC to two fixed HTTPS endpoints. Unknown time is never counted as uptime. This is reachability, not ISP SLA or packet loss."));
    uptime.append(button("Refresh 24h report",async()=>{await refreshUptime();status("Internet uptime report refreshed from real stored samples.");}));
    const unpair=button("Unpair this iPhone",async()=>{
      if(!confirm("Remove personal uptime access from this iPhone?"))return;
      await api("/api/preview/trusted/unpair",{method:"POST",body:"{}"});
      location.reload();
    });
    unpair.id="prodUnpairIphone";unpair.hidden=true;uptime.append(unpair);
    root.append(uptime);
    const diagnostic=div("prod-card");
    diagnostic.append(tag("h4","Read-only PC diagnostics"));
    const diagBtns=div("prod-row");diagBtns.id="prodDiagButtons";
    for(const [id,label] of [["diagnostics.clock","Clock / timezone"],["diagnostics.ping","Ping internet"],
      ["diagnostics.processes","Running apps"],["diagnostics.events","Windows errors"]]){
      const b=button(label,async()=>{
        const result=await api(base+"/diagnostics",{method:"POST",body:JSON.stringify({action:id})});
        status(label+" queued. Awaiting Companion."); await poll(result.poll);
      });b.dataset.capability=id;diagBtns.append(b);
    }
    diagnostic.append(diagBtns);
    const output=tag("pre","No diagnostic requested yet.","prod-result");output.id="prodResult";
    diagnostic.append(output);
    const tools=tag("details");tools.append(tag("summary","Tool Registry / capability status"));
    const toolList=div("prod-items");toolList.id="prodTools";tools.append(toolList);diagnostic.append(tools);
    root.append(diagnostic);
    const statusNode=tag("p","Owner authentication required.","prod-status");statusNode.id="prodStatus";root.append(statusNode);
    q("devicesPanel").append(root);
    q("prodProject").value=project;
  }
  async function poll(path){
    for(let i=0;i<15;i++){
      const data=await api(path);
      if(["done","failed","expired"].includes(data.state)){
        q("prodResult").textContent=JSON.stringify({state:data.state,action:data.action,result:data.result},null,2);
        status("Diagnostic "+data.state);return;
      }
      await new Promise(r=>setTimeout(r,1200));
    }
    status("Still queued. Refresh diagnostics later. No automatic re-run.");
  }
  async function refreshFacts(){
    const data=await api(base+"/projects/"+encodeURIComponent(project)+"/facts");
    const list=q("prodFacts");list.replaceChildren();
    if(!data.facts.length)list.append(tag("p","No project facts saved yet."));
    for(const f of data.facts){
      const card=div("prod-item");
      card.append(tag("strong",f.title),tag("p",f.content));
      card.append(button("Delete",async()=>{if(!confirm("Delete this saved project fact?"))return;await api(base+"/facts/"+f.id,{method:"DELETE"});await refreshFacts();}));
      list.append(card);
    }
  }
  async function refreshMissions(){
    const r=await api(base+"/missions?project_key="+encodeURIComponent(project));
    const list=q("prodMissions");list.replaceChildren();
    if(!r.missions.length)list.append(tag("p","No missions. Create a draft first."));
    for(const m of r.missions){
      const progress=m.step_progress||{total:m.steps.length,completed:0,checkpoints:[]};
      const card=div("prod-item");
      card.append(tag("strong",m.goal),
        tag("p","Status: "+m.status+" | revision "+m.revision+
            " | checkpoints "+progress.completed+"/"+progress.total));
      const ol=tag("ol");
      for(let i=0;i<m.steps.length;i++){
        const isDone=progress.checkpoints[i]?.done===true;
        const li=tag("li",(isDone?"✓ ":"○ ")+m.steps[i]);
        if(m.status==="in_progress"&&!isDone&&i===progress.completed){
          li.append(button("Complete step",async()=>{
            const evidence=prompt("Evidence for checkpoint "+(i+1)+" (10-600 characters):");
            if(evidence===null)return;
            await api(base+"/missions/"+m.id+"/steps/"+i+"/complete",{
              method:"POST",body:JSON.stringify({expected_revision:m.revision,evidence})});
            status("Checkpoint saved as owner-entered evidence. No PC action executed.");
            await refreshMissions();
          }));
        }
        if(m.status==="in_progress"&&isDone&&i===progress.completed-1){
          li.append(button("Reopen",async()=>{
            const evidence=prompt("Reason to reopen checkpoint "+(i+1)+" (10-600 characters):");
            if(evidence===null)return;
            await api(base+"/missions/"+m.id+"/steps/"+i+"/reopen",{
              method:"POST",body:JSON.stringify({expected_revision:m.revision,evidence})});
            status("Checkpoint reopened; audit preserved.");await refreshMissions();
          }));
        }
        ol.append(li);
      }
      card.append(ol);
      const next={draft:"approved",approved:"in_progress",in_progress:"completed"}[m.status];
      if(next){
        const advance=button(next==="approved"?"Approve plan":
          next==="in_progress"?"Start manual work":"Mark completed",async()=>{
          let evidence="";
          if(next==="completed"){
            const result=prompt("Final mission evidence (minimum 10 characters):");
            if(result===null)return;
            evidence=result;
          }
          await api(base+"/missions/"+m.id+"/transition",{method:"POST",
            body:JSON.stringify({status:next,expected_revision:m.revision,evidence})});
          status("Mission status changed. No commands were executed.");await refreshMissions();
        });
        if(next==="completed"&&progress.completed<progress.total){
          advance.disabled=true;
          advance.title="Complete all checkpoints before closing this mission";
        }
        card.append(advance);
      }
      if(["draft","approved","in_progress"].includes(m.status)){
        card.append(button("Cancel",async()=>{if(!confirm("Cancel this mission?"))return;
          await api(base+"/missions/"+m.id+"/transition",{method:"POST",
            body:JSON.stringify({status:"cancelled",expected_revision:m.revision})});
          await refreshMissions();
        }));
      }
      card.append(button("Audit log",async()=>{
        const receipt=await api(base+"/missions/"+m.id+"/audit");
        const output=tag("pre",JSON.stringify(receipt,null,2),"prod-result");
        card.append(output);
      }));
      if(m.evidence)card.append(tag("p","Final evidence (owner-entered): "+m.evidence));
      list.append(card);
    }
  }
  async function refreshTools(){
    const r=await api(base+"/capabilities");
    const tools=q("prodTools");tools.replaceChildren();
    for(const t of r.tools)tools.append(tag("p",t.id+" • "+(t.ready?"ready":t.status)+" • "+t.kind));
    for(const btn of q("prodDiagButtons").querySelectorAll("button")){
      const item=r.tools.find(t=>t.id===btn.dataset.capability);
      btn.disabled=!item?.ready;
      btn.title=item?.ready?"Authenticated companion":"Requires updated Companion";
    }
  }
  function uptimeDuration(seconds){
    if(seconds>=3600)return (seconds/3600).toFixed(1)+" h";
    return Math.round(seconds/60)+" min";
  }
  async function refreshUptime(){
    const data=await api(personalPreview?"/api/preview/trusted/uptime":"/api/uptime/summary?hours=24");
    q("prodUptimePct").textContent=data.uptime_pct===null?"COLLECTING":data.uptime_pct.toFixed(2)+"%";
    q("prodUptimeState").textContent=data.status==="ready"?"24-hour report ready":
      data.status==="no_data"?"No samples recorded yet":"Partial 24-hour coverage";
    q("prodUptimeCoverage").textContent=data.coverage_pct.toFixed(2)+"%";
    q("prodUptimeDown").textContent=uptimeDuration(data.approx_down_seconds);
    q("prodUptimeUnknown").textContent=uptimeDuration(data.unknown_seconds);
    q("prodUptimeLatency").textContent=data.avg_https_latency_ms===null?"--":
      data.avg_https_latency_ms.toFixed(1)+" ms";
    q("prodUptimeOutages").textContent=data.samples_recorded===0?"--":String(data.outage_count);
    q("prodUptimeProbe").textContent=data.https_probe_success_pct===null?"--":
      data.https_probe_success_pct.toFixed(2)+"%";
    const chart=q("prodUptimeTimeline");
    chart.replaceChildren();
    for(const bar of data.timeline){
      const n=div("prod-uptime-bar prod-uptime-"+bar.state);
      n.title=bar.at_utc+" • "+bar.state+" • "+bar.samples+" samples / "+bar.missing+" unknown";
      chart.append(n);
    }
    const incidents=q("prodUptimeOutagesList");incidents.replaceChildren();
    if(!data.outages.length){
      incidents.append(tag("p",data.samples_recorded===0?"No monitoring samples yet.":
        "No simultaneous endpoint failures recorded in available samples."));
    }else{
      for(const incident of data.outages.slice(-5).reverse()){
        const when=new Date(incident.started_at_utc).toLocaleString("id-ID",{timeZone:"Asia/Jakarta",
          day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"});
        incidents.append(tag("p",when+" WIB • about "+uptimeDuration(incident.approx_duration_seconds)+" unavailable"));
      }
    }
  }
  async function refreshAll(){
    await Promise.all([refreshFacts(),refreshMissions(),refreshTools(),refreshUptime()]);
    status("Project "+project+" loaded. No automatic device changes.");
  }
  async function access(){
    setup();
    if(!q("productivityHub"))return;
    const r=await fetch("/api/session",{credentials:"same-origin",cache:"no-store"});
    const session=r.ok?await r.json().catch(()=>({})):{};
    const authenticated=session.authenticated===true&&session.preview!==true;
    personalPreview=session.preview===true&&session.trusted_uptime===true;
    const visible=authenticated||personalPreview;
    q("productivityHub").hidden=!visible;
    q("productivityHub").classList.toggle("preview-uptime-only",personalPreview);
    q("prodUnpairIphone").hidden=!personalPreview;
    document.body.classList.toggle("sonic-trusted-uptime",personalPreview);
    csrf=authenticated?session.csrf:personalPreview?session.preview_csrf:null;
    if(authenticated)await refreshAll();
    else if(personalPreview)await refreshUptime();
  }
  window.addEventListener("sonic:tab",e=>{if(e.detail?.tab==="devices")access().catch(err=>status(err.message));});
  window.addEventListener("DOMContentLoaded",()=>{setup();});
})();
