/* Pure geometry and gesture semantics shared by browser and Node tests. */
(function(root,factory){const f=factory();if(typeof module==='object'&&module.exports)module.exports=f;root.SonicMotionMath=f;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const SPEED={idle:0.55,listening:0.95,thinking:1.18,speaking:1.85,saving:1.1,error:0.45};
  function targetSpeed(state,reduced=false){return reduced?0.12:(SPEED[state]??SPEED.idle);}
  function doubleTap(previous,now,threshold=1000){return Number.isFinite(previous)&&Number.isFinite(now)&&now>=previous&&now-previous<=threshold;}
  function focusRect(viewWidth,viewHeight,originWidth){const size=Math.min(viewWidth*0.76,viewHeight*0.68,560);return {left:(viewWidth-size)/2,top:(viewHeight-size)/2,width:size,height:size};}
  function returnIntent(text){const s=String(text||'').toLowerCase().trim();return /(?:\bminggir\b|kembali(?:lah)?\s+(?:ke\s+)?(?:tempat\s+semula|posisi\s+awal)|\bmove\s+aside\b|\bback\s+to\s+(?:your\s+)?place\b|\breturn\s+to\s+(?:your\s+)?(?:home|place)\b)/.test(s);}
  return {targetSpeed,doubleTap,focusRect,returnIntent};
});
