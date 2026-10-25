/* Pure geometry and gesture semantics shared by browser and Node tests. */
(function(root,factory){const f=factory();if(typeof module==='object'&&module.exports)module.exports=f;root.SonicMotionMath=f;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const SPEED={idle:0.55,listening:0.95,thinking:1.18,speaking:1.85,saving:1.1,error:0.45};
  // V0.7.1: exactly 3x the earlier 980-point sphere. One shared immutable
  // configuration keeps the browser renderer and regression tests in sync.
  const PARTICLE_VISUAL=Object.freeze({
    baseCount:980,
    densityMultiplier:3,
    count:2940,
    spritePixels:64,
    coreSizeMultiplier:1.68,
    haloSizeMultiplier:4.25,
    coreCyan:'#baffff',
    glowCyan:'#00ddff',
    stops:Object.freeze([
      Object.freeze([0,   'rgba(186,255,255,1)']),
      Object.freeze([.10, 'rgba(99,252,255,.98)']),
      Object.freeze([.23, 'rgba(12,232,255,.72)']),
      Object.freeze([.44, 'rgba(0,217,255,.17)']),
      Object.freeze([.72, 'rgba(0,210,255,.035)']),
      Object.freeze([1,   'rgba(0,205,255,0)'])
    ])
  });

  function targetSpeed(state,reduced=false){return reduced?0.12:(SPEED[state]??SPEED.idle);}
  function doubleTap(previous,now,threshold=1000){return Number.isFinite(previous)&&Number.isFinite(now)&&now>=previous&&now-previous<=threshold;}
  function focusRect(viewWidth,viewHeight,originWidth){const size=Math.min(viewWidth*0.76,viewHeight*0.68,560);return {left:(viewWidth-size)/2,top:(viewHeight-size)/2,width:size,height:size};}
  function returnIntent(text){const s=String(text||'').toLowerCase().trim();return /(?:\bminggir\b|kembali(?:lah)?\s+(?:ke\s+)?(?:tempat\s+semula|posisi\s+awal)|\bmove\s+aside\b|\bback\s+to\s+(?:your\s+)?place\b|\breturn\s+to\s+(?:your\s+)?(?:home|place)\b)/.test(s);}
  return {targetSpeed,doubleTap,focusRect,returnIntent,PARTICLE_VISUAL};
});
