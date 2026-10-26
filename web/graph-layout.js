/* Stable category islands. Cross-category links never pull colors together. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.SonicGraphLayout=api;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const CATEGORIES=['system','topic','tool','device','integration','memory'];
  const NAMES={system:'SYSTEM',memory:'MEMORIES',topic:'TOPICS',tool:'TOOLS',device:'DEVICES',integration:'INTEGRATION'};
  function grouped(nodes){
    const buckets=new Map(CATEGORIES.map(c=>[c,[]]));
    for(const n of nodes){if(!buckets.has(n.category))buckets.set(n.category,[]);buckets.get(n.category).push(n);}
    const groups=[...buckets].filter(([,items])=>items.length).map(([category,items])=>({category,items:items.sort((a,b)=>a.id.localeCompare(b.id)),radius:Math.max(34,Math.sqrt(items.length)*20)}));
    const orbit=Math.max(150,...groups.map(g=>g.radius*2.4+40)),positions=new Map();
    groups.forEach((g,index)=>{
      const slot=CATEGORIES.indexOf(g.category),angle=-Math.PI/2+(slot<0?index:slot)*Math.PI/3;
      g.center=[Math.cos(angle)*orbit,Math.sin(angle)*orbit,0];
      g.items.forEach((n,i)=>{const a=i*2.39996322972865,r=g.items.length===1?0:Math.sqrt(i+.5)*20;
        positions.set(n.id,[g.center[0]+Math.cos(a)*r,g.center[1]+Math.sin(a)*r,Math.sin(a*.7)*Math.min(r*.22,20)]);
      });
      g.count=g.items.length;g.label=NAMES[g.category]||g.category.toUpperCase();delete g.items;
    });
    return {positions,groups};
  }
  return {grouped};
});
