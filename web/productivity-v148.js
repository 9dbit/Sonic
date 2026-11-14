/* SONIC Productivity 1.4.8: owner-only Mission + Project Memory + Diagnostics. */
(() => {
  "use strict";
  const q=id=>document.getElementById(id);
  const base="/api/productivity";
  let csrf=null;
  let project="sonic";
  const tag=(name,text,cls="")=>{const e=document.createElement(name);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
  const div=(cls="")=>tag("div",undefined,cls);
  async function api(path,options={}){
    const headers={"Content-Type":"application/json",...(csrf?{"X-Sonic-CSRF":csrf}:{})};
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
      const card=div("prod-item");card.append(tag("strong",m.goal),tag("p","Status: "+m.status+" | revision "+m.revision));
      const ol=tag("ol");for(const step of m.steps)ol.append(tag("li",step));card.append(ol);
      const next={draft:"approved",approved:"in_progress",in_progress:"completed"}[m.status];
      if(next)card.append(button(next==="approved"?"Approve plan":next==="in_progress"?"Start manual work":"Mark completed",async()=>{
        let evidence="";
        if(next==="completed"){
          const result=prompt("Evidence of work completed (min 10 characters):");
          if(result===null)return;
          evidence=result;
        }
        await api(base+"/missions/"+m.id+"/transition",{method:"POST",
          body:JSON.stringify({status:next,expected_revision:m.revision,evidence})});
        status("Mission status changed. No commands were executed.");await refreshMissions();
      }));
      if(["draft","approved","in_progress"].includes(m.status)){
        card.append(button("Cancel",async()=>{if(!confirm("Cancel this mission?"))return;
          await api(base+"/missions/"+m.id+"/transition",{method:"POST",
            body:JSON.stringify({status:"cancelled",expected_revision:m.revision})});
          await refreshMissions();
        }));
      }
      if(m.evidence)card.append(tag("p","Evidence: "+m.evidence));
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
  async function refreshAll(){
    await Promise.all([refreshFacts(),refreshMissions(),refreshTools()]);
    status("Project "+project+" loaded. No automatic device changes.");
  }
  async function access(){
    setup();
    if(!q("productivityHub"))return;
    const r=await fetch("/api/session",{credentials:"same-origin",cache:"no-store"});
    const session=r.ok?await r.json().catch(()=>({})):{};
    const authenticated=session.authenticated===true&&session.preview!==true;
    q("productivityHub").hidden=!authenticated;
    csrf=authenticated?session.csrf:null;
    if(authenticated)await refreshAll();
  }
  window.addEventListener("sonic:tab",e=>{if(e.detail?.tab==="devices")access().catch(err=>status(err.message));});
  window.addEventListener("DOMContentLoaded",()=>{setup();});
})();
