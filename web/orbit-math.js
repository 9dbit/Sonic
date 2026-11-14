/* Pure, bounded motion: seconds in, visual state out. No device or media access. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;root.SonicOrbitMath=value;})(typeof window==='undefined'?globalThis:window,()=>{
 'use strict';
 const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
 function pose(seconds,reduced=false,state='idle'){
  const t=Number.isFinite(seconds)?Math.max(0,seconds):0;
  if(reduced)return {jump:0,look:0,blink:1,pulse:1};
  const phase=t%4.4;
  const jump=phase>.35&&phase<1.8?Math.sin((phase-.35)/1.45*Math.PI):0;
  const blinkPhase=t%5.3;
  const blink=blinkPhase>1.8&&blinkPhase<2.05?Math.max(.08,Math.abs((blinkPhase-1.925)/.125)):1;
  const look=Math.sin(t*.7)*Math.max(0,Math.min(1,Math.sin(t*.22)*2));
  const pulse=state==='speaking'?1+.025*Math.sin(t*8):state==='thinking'?1+.012*Math.sin(t*4):1;
  return {jump:clamp(jump,0,1),look:clamp(look,-1,1),blink:clamp(blink,.08,1),pulse};
 }
 function metric(value,suffix='',decimals=0){return typeof value==='number'&&Number.isFinite(value)?value.toFixed(decimals)+suffix:'Not available';}
 return {pose,metric};
});
