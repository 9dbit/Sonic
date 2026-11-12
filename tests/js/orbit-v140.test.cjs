const test=require('node:test');
const assert=require('node:assert/strict');
const {pose,metric}=require('../../web/orbit-math.js');
test('reduced motion is entirely static, including eyes and bounce',()=>{for(const t of [0,1.925,100,Infinity,NaN])assert.deepEqual(pose(t,true,'speaking'),{jump:0,look:0,blink:1,pulse:1});});
test('expressions are bounded for all states over 60 seconds',()=>{for(const state of ['idle','listening','thinking','speaking','muted','error'])for(let t=0;t<60;t+=.05){const p=pose(t,false,state);assert.ok(p.jump>=0&&p.jump<=1);assert.ok(p.look>=-1&&p.look<=1);assert.ok(p.blink>=.08&&p.blink<=1);assert.ok(p.pulse>=.97&&p.pulse<=1.03);}});
test('the orb blinks rather than permanently displaying a listening face',()=>{assert.equal(pose(0).blink,1);assert.equal(pose(1.925).blink,.08);assert.equal(pose(2.2).blink,1);});
test('non-finite timestamps do not poison renderer geometry',()=>{for(const t of [NaN,Infinity,-Infinity,undefined,-10])for(const v of Object.values(pose(t)))assert.ok(Number.isFinite(v));});
test('missing metrics are unavailable, never converted to zero',()=>{for(const x of [null,undefined,'50',NaN,Infinity])assert.equal(metric(x,'%'),'Not available');assert.equal(metric(0,'%'),'0%');assert.equal(metric(12.6,'%'),'13%');});
test('voice speaking animation differs from idle without inventing audio amplitudes',()=>{assert.equal(pose(1,false,'idle').pulse,1);assert.notEqual(pose(1,false,'speaking').pulse,1);});
