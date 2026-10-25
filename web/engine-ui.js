/* Narrow browser adapter for server-validated graph plans. No arbitrary JS execution. */
(() => {
  'use strict';
  window.applySonicGraphActions=async function(actions,context){
    if(!Array.isArray(actions))return [];
    const outcomes=[];await context.refresh();
    for(const action of actions.slice(0,6)){
      if(!action||typeof action!=='object')continue;
      const graph=context.graph;
      try{
        if(action.type==='graph.reset'){context.show();context.enableAll();graph.clear();context.search('');}
        else if(action.type==='graph.search'){
          const ids=Array.isArray(action.node_ids)?action.node_ids.filter(id=>graph.lookup.has(id)):[];
          context.show();context.search(String(action.query||'').slice(0,150));
          context.enableAll();graph.select(null);graph.highlight=new Set(ids);graph.invalidate();context.showSearch();
        }else if(['graph.focus','graph.neighbors'].includes(action.type)){
          if(!graph.lookup.has(action.node_id))throw Error('Node tidak tersedia lagi. Refresh dan cari kembali.');
          context.show();context.enableAll();
          if(action.type==='graph.neighbors'){
            if(!Number.isInteger(action.depth)||action.depth<1||action.depth>3)throw Error('Invalid depth');
            graph.setDepth(action.depth);context.depth(action.depth);
          }
          context.select(action.node_id,true);
        }else{throw Error('Navigation action not allowed');}
        outcomes.push({type:action.type,status:'applied'});
      }catch(error){outcomes.push({type:action.type,status:'rejected'});context.notify(error.message);}
    }
    return outcomes;
  };
})();
