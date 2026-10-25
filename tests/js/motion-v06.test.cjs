const test=require('node:test');const assert=require('node:assert/strict');
const m=require('../../web/motion-math.js');
test('idle slow, speaking fast, thinking between',()=>{assert.ok(m.targetSpeed('idle')<m.targetSpeed('thinking'));assert.ok(m.targetSpeed('thinking')<m.targetSpeed('speaking'));});
test('reduced motion limits speed for all states',()=>{assert.equal(m.targetSpeed('speaking',true),.12);});
test('second tap at <=1000ms focuses',()=>{assert.equal(m.doubleTap(1000,2000),true);assert.equal(m.doubleTap(1000,2001),false);assert.equal(m.doubleTap(-Infinity,900),false);});
test('focus rectangle centered and finite for mobile',()=>{for(const [w,h] of [[390,844],[1440,900]]){const r=m.focusRect(w,h,120);assert.equal(r.left,(w-r.width)/2);assert.ok(r.height<=h*.68+.1);}});
test('only explicit return phrases trigger reset',()=>{for(const s of ['Sonic, minggir','kembali ke tempat semula','move aside','return to your place'])assert.ok(m.returnIntent(s),s);for(const s of ['lihat node','memori bakso','ingat bahwa saya suka datang kembali'])assert.equal(m.returnIntent(s),false);});
