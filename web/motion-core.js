/* SONIC V0.7.2 Motion Core: 5880 sharp cyan-blue points on transparent Canvas2D.
   No glow, additive blending, gradients per dot, video, or WebGL dependency.
   Speed and breathing remain tied to actual application and voice states. */
(()=>{'use strict';
 const el=id=>document.getElementById(id),math=window.SonicMotionMath;
 const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
 class SonicMotionCore {
  constructor(anchor){
   this.anchor=anchor;this.float=document.createElement('div');this.float.id='sonicMotionFloat';
   this.float.className='sonic-motion-float';this.float.dataset.state='idle';this.float.tabIndex=0;
   this.float.setAttribute('role','button');this.float.setAttribute('aria-label','SONIC: double tap to center and start microphone; Escape to return');
   this.float.setAttribute('aria-pressed','false');
   this.float.title='Double tap untuk memulai mikrofon dan pemrosesan audio OpenAI';
   this.shade=document.createElement('div');this.shade.id='sonicFocusShade';this.shade.setAttribute('aria-hidden','true');
   this.focusControls=document.createElement('div');this.focusControls.className='sonic-focus-controls';this.focusControls.hidden=true;
   const hint=document.createElement('p');hint.textContent='SONIC · Double tap memulai mikrofon dan audio OpenAI';
   const home=document.createElement('button');home.type='button';home.textContent='Kembali ke posisi awal';home.addEventListener('click',()=>this.returnHome());
   this.focusControls.append(hint,home);document.body.append(this.shade,this.focusControls);
   this.canvas=document.createElement('canvas');this.canvas.setAttribute('aria-hidden','true');this.float.append(this.canvas);
   this.ctx=this.canvas.getContext('2d',{alpha:true});this.reduced=!!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
   this.state='idle';this.speed=math.targetSpeed('idle',this.reduced);this.energy=0;
   this.focused=false;this.lastTap=-Infinity;this.home=null;this.running=true;this.paused=false;this.lastTime=0;this.time=0;
   this.visual=math.PARTICLE_VISUAL;
   this.palette=Array.from({length:this.visual.paletteSteps},(_,i)=>{
     const rgb=math.cyanBlueRGB(i/(this.visual.paletteSteps-1));
     return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
   });
   const particleCount=this.visual.count;
   this.points=Array.from({length:particleCount},(_,i)=>{
     const f=i+.5,y=1-2*f/particleCount,r=Math.sqrt(Math.max(0,1-y*y)),theta=i*2.39996322972865;
     return [Math.cos(theta)*r,y,Math.sin(theta)*r,i];
   });
   document.body.append(this.float);this.updateHome(true);this.attach();
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  attach(){
   const press=()=>{const now=performance.now();if(math.doubleTap(this.lastTap,now)){this.lastTap=-Infinity;this.setFocus(true);window.dispatchEvent(new CustomEvent('sonic:invoke',{detail:{consent:'double_tap'}}));}else{this.lastTap=now;this.float.classList.add('preview');clearTimeout(this.tapTimer);this.tapTimer=setTimeout(()=>this.float.classList.remove('preview'),1100);}};
   this.float.addEventListener('click',e=>{e.stopPropagation();press();});
   this.float.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();press();}else if(e.key==='Escape')this.returnHome();});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&this.focused)this.returnHome();});
   window.addEventListener('resize',()=>{this.updateHome(!this.focused);if(this.focused)this.place(math.focusRect(innerWidth,innerHeight,this.home?.width||160));});
   window.addEventListener('scroll',()=>this.updateHome(!this.focused),{passive:true});
   document.addEventListener('visibilitychange',()=>{this.paused=document.hidden;});
   // When switching between panels, the anchor may have zero dimensions.
   const observer=new MutationObserver(()=>{if(!this.focused)this.updateHome(true);this.prioritizePanels();});
   for(const node of [this.anchor.closest('section'),el('graphInspector'),el('graphFilters')])if(node)observer.observe(node,{attributes:true,attributeFilter:['class','style']});
   // Filter content arrives asynchronously and pushes the home anchor down.
   if(el('filterList'))observer.observe(el('filterList'),{childList:true,subtree:true});
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
   document.body.classList.toggle('sonic-focused',on);this.focusControls.hidden=!on;
   if(on){this.backgroundInert=new Map();for(const node of document.querySelectorAll('.panel,.sidebar,.topbar,#nodeDetailPopup')){this.backgroundInert.set(node,node.inert);node.inert=true;}}
   else{for(const [node,prior] of this.backgroundInert||[])node.inert=prior;this.backgroundInert=null;}
   if(on){this.place(math.focusRect(innerWidth,innerHeight,this.home?.width||160));this.float.focus({preventScroll:true});}
   else this.place(this.home);
  }
  returnHome(){this.setFocus(false);}
  handleCommand(text){if(math.returnIntent(text)){this.returnHome();return true;}return false;}
  setState(state){this.state=state;this.float.dataset.state=state;}
  dimensions(){const w=this.canvas.clientWidth,h=this.canvas.clientHeight,dpr=clamp(devicePixelRatio||1,1,2),nw=Math.max(1,Math.round(w*dpr)),nh=Math.max(1,Math.round(h*dpr));
   if(this.canvas.width!==nw||this.canvas.height!==nh){this.canvas.width=nw;this.canvas.height=nh;}return [nw,nh];
  }
  draw(){
   const ctx=this.ctx;if(!ctx)return;
   const [width,height]=this.dimensions();if(width<2||height<2)return;
   ctx.clearRect(0,0,width,height);
   // Default source-over compositing, no shadows or filters: the canvas stays
   // transparent and individual tiny dots remain sharply defined.
   ctx.globalCompositeOperation='source-over';
   const radius=Math.min(width,height)*.443,centerX=width*.5,centerY=height*.5;
   const a=this.time*.38,ca=Math.cos(a),sa=Math.sin(a);
   const tilt=.12*Math.sin(this.time*.44),ct=Math.cos(tilt),st=Math.sin(tilt);
   const speaking=this.state==='speaking'?1:this.state==='listening'?.32:0;
   this.energy+=(speaking-this.energy)*.065;
   const palette=this.palette,lastColor=palette.length-1;
   // Fibonacci sphere, existing orbit, breathing waveform and concavity.
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
     // Gradient follows 3D depth and vertical position. Each point itself is
     // a single opaque-hue square, not a radial glow or blurred sprite.
     const hueT=clamp(.5-.38*z-.12*y2,0,1);
     const colorIndex=Math.min(lastColor,Math.max(0,Math.round(hueT*lastColor)));
     const size=math.particleDiameter(width,light);
     ctx.fillStyle=palette[colorIndex];
     ctx.globalAlpha=clamp(.37+.51*light+.04*z+.03*this.energy,.38,.92);
     ctx.fillRect(Math.round(px),Math.round(py),size,size);
   }
   ctx.globalAlpha=1;
  }
  frame(timestamp){if(!this.running)return;const dt=this.lastTime?clamp((timestamp-this.lastTime)/1000,0,.12):0;this.lastTime=timestamp;
   const desired=math.targetSpeed(this.state,this.reduced);this.speed+=(desired-this.speed)*clamp(dt*4,0,1);
   if(!this.paused){this.time+=dt*this.speed;this.draw();}
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  stop(){this.returnHome();this.running=false;cancelAnimationFrame(this.frameRequest);clearTimeout(this.tapTimer);this.observer?.disconnect();this.float.remove();this.shade.remove();this.focusControls.remove();}
 }
 const init=()=>{const anchor=el('sonicMotionAnchor');if(anchor)window.sonicMotion=new SonicMotionCore(anchor);};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
 window.SonicMotionCore=SonicMotionCore;
})();
