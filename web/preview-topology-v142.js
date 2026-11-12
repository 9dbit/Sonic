/* Public topology only. No simulated memories, private PC telemetry or owner graph data. */
(()=>{
  'use strict';
  const details=[
    ['core','SONIC','system','The SONIC orchestration shell and interface'],
    ['neural','Neural Brain','system','Native 3D WebGL/Canvas knowledge renderer'],
    ['brain-chat','Prompt Composer','system','Chat UI for text prompts'],
    ['graph','Orbit Map','system','Perspective nodes, edges, pan, zoom and selection'],
    ['model-router','AI Model Router','tool','Local preview model selection; owner settings are unchanged'],
    ['model','Chat AI','tool','Selected configured provider, limited public preview'],
    ['deepseek','DeepSeek','tool','Chat Completions provider. No tools in open preview'],
    ['openai','OpenAI','tool','Responses provider. Also hosts Realtime voice'],
    ['voice','Voice Realtime','tool','OpenAI audio over user-started WebRTC'],
    ['transcribe','Speech to Text','tool','Transient voice transcription, not stored'],
    ['listening','Microphone','tool','Starts only from a direct user gesture'],
    ['audio','Audio Output','tool','Speaker playback, mute and stop controls'],
    ['workspace','Workspace','topic','Owner files are protected in open preview'],
    ['files','Cloud Files','topic','Private files are never sent to anonymous clients'],
    ['memory','Memory Vault','topic','Owner-approved personal memory is protected'],
    ['knowledge','Knowledge Graph','topic','Only public architecture nodes appear in this preview'],
    ['device','TRADEVICEPC','device','Registered Windows device; connection and telemetry are private'],
    ['broker','Software Manager','topic','Windows software operations require owner authorization'],
    ['approval','Operator Approval','topic','No anonymous Windows actions or approval bypass'],
    ['integrations','Integration Registry','topic','Connections need explicit authorization'],
    ['settings','Setup','system','Configuration and secrets remain private'],
    ['security','Safety Boundary','system','Unauthenticated requests cannot access the owner engine'],
    ['quota','Preview Limits','system','Global and per-network paid-provider budgets'],
    ['provider','API Gateway','system','Separate guest text and audio routes'],
  ];
  const pairs=[
    ['core','neural'],['core','brain-chat'],['core','voice'],['core','workspace'],
    ['core','device'],['core','settings'],['core','security'],['core','integrations'],
    ['neural','graph'],['neural','knowledge'],['graph','knowledge'],['graph','memory'],
    ['brain-chat','model-router'],['brain-chat','model'],['model-router','deepseek'],
    ['model-router','openai'],['model-router','model'],['model','provider'],
    ['provider','security'],['provider','quota'],['provider','deepseek'],['provider','openai'],
    ['voice','transcribe'],['voice','listening'],['voice','audio'],['voice','openai'],
    ['voice','provider'],['workspace','files'],['workspace','memory'],['workspace','device'],
    ['device','broker'],['device','approval'],['broker','approval'],
    ['integrations','device'],['integrations','provider'],['security','approval'],
    ['security','files'],['security','memory'],['security','device'],['quota','security'],
    ['settings','model-router'],['settings','provider'],['neural','model'],
  ];
  function build(selection){
    const modelName=selection?.model||'model not selected';
    const nodes=details.map(([id,label,category,detail])=>({
      id:'preview:'+id,label:id==='model'?modelName:label,
      category,detail,source:'SONIC architecture preview (no owner data)',
      state:'preview',degree:0
    }));
    const byId=new Map(nodes.map(n=>[n.id,n]));
    const edges=pairs.map(([a,b],i)=>{
      const source='preview:'+a,target='preview:'+b;
      byId.get(source).degree++;byId.get(target).degree++;
      return {id:'preview:edge:'+i,source,target,label:'module relationship',kind:'preview'};
    });
    const categories={};
    for(const n of nodes)categories[n.category]=(categories[n.category]||0)+1;
    return {nodes,edges,counts:{nodes:nodes.length,edges:edges.length,categories,
                memories:0,displayed_memories:0},truncated:false,limits:{topics:0},
            preview:true};
  }
  window.SonicPreviewTopology={build};
})();
