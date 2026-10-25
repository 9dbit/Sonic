// Latest motion contract, retained under the historical v071 test filename.
const test=require('node:test');
const assert=require('node:assert/strict');
const {PARTICLE_VISUAL: v,particleDiameter,cyanBlueRGB,targetSpeed}=require('../../web/motion-math.js');

test('V0.7.2 exactly doubles the 2940-point V0.7.1 sphere',()=>{
  assert.equal(v.baseCount,980);
  assert.equal(v.previousCount,2940);
  assert.equal(v.densityMultiplier,6);
  assert.equal(v.count,5880);
  assert.equal(v.count,v.previousCount*2);
  assert.ok(Object.isFrozen(v));
});

test('V0.7.2 point diameter is half the previous core across all layouts',()=>{
  assert.equal(v.pointScale,.5);
  for(const width of [70,90,138,178,300,560]){
    for(const light of [.12,.35,.7,1]){
      const old=Math.min(9.5,Math.max(.95,(width/190)*(.72+.66*light)*1.68));
      assert.ok(Math.abs(particleDiameter(width,light)-old*.5)<1e-10);
    }
  }
});

test('sharp cyan-to-blue palette has no white, red/orange, or glow',()=>{
  assert.equal(v.glowEnabled,false);
  assert.equal(v.paletteSteps,48);
  assert.equal(v.colors.cyan,'#43f0ff');
  assert.equal(v.colors.blue,'#1c7dff');
  assert.deepEqual(cyanBlueRGB(0),[28,125,255]);
  assert.deepEqual(cyanBlueRGB(1),[67,240,255]);
  for(let i=0;i<=100;i++){
    const [r,g,b]=cyanBlueRGB(i/100);
    assert.ok(r>=28&&r<=67&&g>=125&&g<=240&&b===255);
    assert.ok(b>=g&&g>=r);
  }
  assert.equal('spritePixels' in v,false);
  assert.equal('haloSizeMultiplier' in v,false);
  assert.equal('stops' in v,false);
});

test('orbit animation preserves speaking states and accessibility',()=>{
  assert.ok(targetSpeed('speaking')>targetSpeed('thinking'));
  assert.ok(targetSpeed('thinking')>targetSpeed('idle'));
  assert.equal(targetSpeed('speaking',true),.12);
});
