/* Pure geometry and gesture semantics shared by browser and Node tests. */
(function(root,factory){const f=factory();if(typeof module==='object'&&module.exports)module.exports=f;root.SonicMotionMath=f;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const SPEED={idle:0.55,listening:0.95,thinking:1.18,speaking:1.85,saving:1.1,error:0.45};
  // V0.7.2: sharp 50%-size dots, exactly twice V0.7.1 density, no bloom.
  // "Gradient" denotes the color across the sphere, not a blurry sprite.
  const PARTICLE_VISUAL=Object.freeze({
    baseCount:980,
    previousCount:2940,
    densityMultiplier:6,
    count:5880,
    pointScale:.5,
    previousCoreMultiplier:1.68,
    paletteSteps:48,
    glowEnabled:false,
    colors:Object.freeze({cyan:'#43f0ff',blue:'#1c7dff'})
  });
  const clamp=(x,low,high)=>Math.min(high,Math.max(low,x));
  // Exact half of the diameter used for the V0.7.1 particle core at the
  // same width and light value, even where the old renderer was clamped.
  function particleDiameter(width,light){
    const oldDiameter=clamp((width/190)*(.72+.66*clamp(light,0,1))*PARTICLE_VISUAL.previousCoreMultiplier,.95,9.5);
    return oldDiameter*PARTICLE_VISUAL.pointScale;
  }
  function cyanBlueRGB(t){
    const mix=clamp(t,0,1);
    return [Math.round(28+39*mix),Math.round(125+115*mix),255];
  }

  function targetSpeed(state,reduced=false){return reduced?0.12:(SPEED[state]??SPEED.idle);}
  function doubleTap(previous,now,threshold=1000){return Number.isFinite(previous)&&Number.isFinite(now)&&now>=previous&&now-previous<=threshold;}
  function focusRect(viewWidth,viewHeight,originWidth){const size=Math.min(viewWidth*0.76,viewHeight*0.68,560);return {left:(viewWidth-size)/2,top:(viewHeight-size)/2,width:size,height:size};}
  function returnIntent(text){const s=String(text||'').toLowerCase().trim();return /(?:\bminggir\b|kembali(?:lah)?\s+(?:ke\s+)?(?:tempat\s+semula|posisi\s+awal)|\bmove\s+aside\b|\bback\s+to\s+(?:your\s+)?place\b|\breturn\s+to\s+(?:your\s+)?(?:home|place)\b)/.test(s);}
  return {targetSpeed,doubleTap,focusRect,returnIntent,PARTICLE_VISUAL,particleDiameter,cyanBlueRGB};
});
