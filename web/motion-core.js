/* SONIC Motion Core: transparent procedural silver particles inspired by the
   owner's looping reference. No codec, GPU or autoplay dependency is required.
   Motion responds to actual application voice states, never simulated speech. */
(()=>{'use strict';
 const el=id=>document.getElementById(id),math=window.SonicMotionMath;
 const TAU=Math.PI*2;
 const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
 class SonicMotionCore {
  constructor(anchor){
   this.anchor=anchor;this.float=document.createElement('div');this.float.id='sonicMotionFloat';
   this.float.className='sonic-motion-float';this.float.dataset.state='idle';this.float.tabIndex=0;
   this.float.setAttribute('role','button');this.float.setAttribute('aria-label','SONIC Motion Core: tap once to enlarge 10%, twice within one second to center, Escape to return');
   this.canvas=document.createElement('canvas');this.canvas.setAttribute('aria-hidden','true');this.float.append(this.canvas);
   this.ctx=this.canvas.getContext('2d',{alpha:true});this.reduced=!!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
   this.state='idle';this.speed=math.targetSpeed('idle',this.reduced);this.energy=0;
   this.focused=false;this.lastTap=-Infinity;this.home=null;this.running=true;this.paused=false;this.lastTime=0;this.time=0;
   this.visual=math.PARTICLE_VISUAL;
   this.sprite=this.makeGlowSprite();
   const particleCount=this.visual.count;
   this.points=Array.from({length:particleCount},(_,i)=>{
     const f=i+.5,y=1-2*f/particleCount,r=Math.sqrt(Math.max(0,1-y*y)),theta=i*2.39996322972865;
     return [Math.cos(theta)*r,y,Math.sin(theta)*r,i];
   });
   document.body.append(this.float);this.updateHome(true);this.attach();
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  attach(){
   const press=()=>{const now=performance.now();if(math.doubleTap(this.lastTap,now)){this.lastTap=-Infinity;this.setFocus(!this.focused);}else{this.lastTap=now;this.float.classList.add('preview');clearTimeout(this.tapTimer);this.tapTimer=setTimeout(()=>this.float.classList.remove('preview'),1100);}};
   this.float.addEventListener('click',e=>{e.stopPropagation();press();});
   this.float.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();press();}else if(e.key==='Escape')this.returnHome();});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&this.focused)this.returnHome();});
   window.addEventListener('resize',()=>this.updateHome(!this.focused));
   window.addEventListener('scroll',()=>this.updateHome(!this.focused),{passive:true});
   document.addEventListener('visibilitychange',()=>{this.paused=document.hidden;});
   // When switching between panels, the anchor may have zero dimensions.
   const observer=new MutationObserver(()=>{if(!this.focused)this.updateHome(true);this.prioritizePanels();});
   for(const node of [this.anchor.closest('section'),el('graphInspector'),el('graphFilters')])if(node)observer.observe(node,{attributes:true,attributeFilter:['class','style']});
   this.observer=observer;this.prioritizePanels();
   this.float.addEventListener('mouseenter',()=>{if(!this.focused)this.float.classList.add('hover');});
   this.float.addEventListener('mouseleave',()=>this.float.classList.remove('hover'));
  }
  prioritizePanels(){const inspector=el('graphInspector'),filters=el('graphFilters');
   const open=!!(inspector?.classList.contains('open')||filters?.classList.contains('open'));
   this.float.classList.toggle('under-panel',open&&!this.focused);
  }
  updateHome(apply=false){const r=this.anchor.getBoundingClientRect();
   if(r.width>10&&r.height>10)this.home={left:r.left,top:r.top,width:r.width,height:r.height};
   else if(!this.home)this.home={left:Math.max(6,innerWidth-205),top:Math.min(innerHeight-160,142),width:152,height:152};
   if(apply&&!this.focused)this.place(this.home);
  }
  place(rect){for(const key of ['left','top','width','height'])this.float.style[key]=rect[key]+'px';}
  setFocus(on){if(on===this.focused)return;this.updateHome(false);this.focused=on;
   this.float.classList.toggle('focused',on);this.float.classList.remove('preview');this.float.setAttribute('aria-pressed',String(on));
   if(on){this.place(math.focusRect(innerWidth,innerHeight,this.home?.width||160));this.float.focus({preventScroll:true});}
   else this.place(this.home);
  }
  returnHome(){this.setFocus(false);}
  handleCommand(text){if(math.returnIntent(text)){this.returnHome();return true;}return false;}
  setState(state){this.state=state;this.float.dataset.state=state;}
  dimensions(){const w=this.canvas.clientWidth,h=this.canvas.clientHeight,dpr=clamp(devicePixelRatio||1,1,2),nw=Math.max(1,Math.round(w*dpr)),nh=Math.max(1,Math.round(h*dpr));
   if(this.canvas.width!==nw||this.canvas.height!==nh){this.canvas.width=nw;this.canvas.height=nh;}return [nw,nh];
  }
  makeGlowSprite(){
   // Pre-bake the cyan bloom once. 2940 drawImage calls remain inexpensive
   // compared with creating thousands of gradients or per-dot shadowBlur.
   const size=this.visual.spritePixels,sprite=document.createElement('canvas');
   sprite.width=sprite.height=size;
   const sc=sprite.getContext('2d',{alpha:true});
   if(!sc)return sprite;
   const center=size/2,gradient=sc.createRadialGradient(center,center,0,center,center,center);
   for(const [stop,color] of this.visual.stops)gradient.addColorStop(stop,color);
   sc.fillStyle=gradient;sc.fillRect(0,0,size,size);
   return sprite;
  }
  draw(){const ctx=this.ctx;if(!ctx)return;const [width,height]=this.dimensions();if(width<2||height<2)return;
   ctx.clearRect(0,0,width,height);
   ctx.save();
   // Additive blending makes cyan bloom emissive without replacing the
   // transparent background with a dark or colored canvas.
   ctx.globalCompositeOperation='lighter';
   const radius=Math.min(width,height)*.443,centerX=width*.5,centerY=height*.5;
   const a=this.time*.38,ca=Math.cos(a),sa=Math.sin(a),tilt=.12*Math.sin(this.time*.44),ct=Math.cos(tilt),st=Math.sin(tilt);
   const speaking=this.state==='speaking'?1:this.state==='listening'?.32:0;
   this.energy+=(speaking-this.energy)*.065;
   // Preserve the existing Fibonacci sphere, breathing ripples and concavity.
   // Density is exactly 2940 points versus 980 in SONIC V0.7.
   for(let i=0;i<this.points.length;i++){
     const [ox,oy,oz]=this.points[i];
     const swirl=ox*ca-oz*sa,depth=ox*sa+oz*ca;
     const z=depth*ct+oy*st,y=oy*ct-depth*st;
     const wave=Math.sin(ox*8.2+this.time*1.18+oy*3.7)*Math.cos(oy*7.2-this.time*.71+oz*2.5);
     const warp=1+.135*wave+.042*Math.sin(this.time*.7+ox*5)+this.energy*.065*Math.sin(this.time*2.6+oy*9);
     const contour=1-.12*Math.pow(Math.max(0,y),2);
     const x=swirl*warp*contour,y2=y*warp;
     const perspective=1+.15*z,px=centerX+x*radius*perspective,py=centerY+y2*radius*perspective;
     if(px<0||py<0||px>=width||py>=height)continue;
     const light=clamp(.48+.27*z+.31*(x*.55-y2*.65),.12,1);
     // Bright, granular cyan cores with a soft shared sprite halo. Scale with
     // DPR and focused view, but cap large glow surfaces for mobile GPUs.
     const core=clamp((width/190)*(.72+.66*light)*this.visual.coreSizeMultiplier,.95,9.5);
     const halo=clamp(core*this.visual.haloSizeMultiplier*(1+this.energy*.13),3,48);
     const alpha=clamp(.20+.42*light+.07*z+this.energy*.08,.22,.78);
     ctx.globalAlpha=alpha;
     ctx.drawImage(this.sprite,px-halo*.5,py-halo*.5,halo,halo);
   }
   ctx.restore();
  }
  frame(timestamp){if(!this.running)return;const dt=this.lastTime?clamp((timestamp-this.lastTime)/1000,0,.12):0;this.lastTime=timestamp;
   const desired=math.targetSpeed(this.state,this.reduced);this.speed+=(desired-this.speed)*clamp(dt*4,0,1);
   if(!this.paused){this.time+=dt*this.speed;this.draw();}
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  stop(){this.running=false;cancelAnimationFrame(this.frameRequest);clearTimeout(this.tapTimer);this.observer?.disconnect();this.float.remove();}
 }
 const init=()=>{const anchor=el('sonicMotionAnchor');if(anchor)window.sonicMotion=new SonicMotionCore(anchor);};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
 window.SonicMotionCore=SonicMotionCore;
})();
