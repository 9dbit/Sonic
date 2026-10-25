const test=require('node:test');
const assert=require('node:assert/strict');
const {PARTICLE_VISUAL: v,targetSpeed}=require('../../web/motion-math.js');

test('emissive cyan renderer triples the existing 980-particle density',()=>{
  assert.equal(v.baseCount,980);
  assert.equal(v.densityMultiplier,3);
  assert.equal(v.count,v.baseCount*v.densityMultiplier);
  assert.equal(v.count,2940);
  assert.ok(Object.isFrozen(v));
});

test('every sprite gradient stop is cyan-emissive and ends transparent',()=>{
  assert.match(v.coreCyan,/^#[0-9a-f]{6}$/i);
  assert.match(v.glowCyan,/^#[0-9a-f]{6}$/i);
  assert.ok(v.stops.length>=5);
  let last=-1,lastAlpha=2;
  for(const [offset,color] of v.stops){
    assert.ok(offset>last && offset<=1);
    const match=/^rgba\((\d+),(\d+),(\d+),([\d.]+)\)$/.exec(color);
    assert.ok(match,color);
    const [r,g,b,a]=match.slice(1).map(Number);
    assert.ok(b>=g && g>=r,`not cyan: ${color}`);
    assert.ok(a<=lastAlpha && a>=0 && a<=1,`alpha gradient inverted: ${color}`);
    last=offset;lastAlpha=a;
  }
  assert.equal(v.stops.at(-1)[0],1);
  assert.equal(v.stops.at(-1)[1].endsWith(',0)'),true);
});

test('bold cores retain bounded pre-rendered glow and speech motion',()=>{
  assert.ok(v.coreSizeMultiplier>1.5);
  assert.ok(v.haloSizeMultiplier>3 && v.haloSizeMultiplier<6);
  assert.ok(v.spritePixels>=48 && v.spritePixels<=128);
  assert.ok(targetSpeed('speaking')>targetSpeed('idle'));
  assert.equal(targetSpeed('speaking',true),0.12);
});
