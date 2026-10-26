const {test}=require('node:test');const assert=require('node:assert/strict');
const {grouped}=require('../../web/graph-layout.js');
test('category islands remain distinct, bounded and stable under input order',()=>{
 const cats=['system','topic','tool','device','integration','memory'];
 const nodes=cats.flatMap((category,c)=>Array.from({length:c*12+1},(_,i)=>({id:category+':'+i,category})));
 const a=grouped(nodes),b=grouped([...nodes].reverse());
 assert.equal(a.positions.size,nodes.length);assert.equal(a.groups.length,6);
 for(const n of nodes){assert.deepEqual(a.positions.get(n.id),b.positions.get(n.id));const g=a.groups.find(g=>g.category===n.category);const p=a.positions.get(n.id);assert.ok(Math.hypot(p[0]-g.center[0],p[1]-g.center[1])<=g.radius);}
 for(const g of a.groups)for(const h of a.groups)if(g!==h)assert.ok(Math.hypot(g.center[0]-h.center[0],g.center[1]-h.center[1])>g.radius+h.radius+20);
});
test('empty graph contains no decorative nodes or groups',()=>{const a=grouped([]);assert.equal(a.positions.size,0);assert.deepEqual(a.groups,[]);});
