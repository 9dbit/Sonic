/* SONIC Orbit V1.4: expression-driven orb; legacy gesture API retained.
   Previous renderer: 5880 sharp cyan-blue points on transparent Canvas2D.
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
   const hint=document.createElement('p');hint.id='sonicVoiceFocusHint';
    hint.setAttribute('role','status');hint.setAttribute('aria-live','polite');
    hint.textContent='SONIC: Double tap untuk berbicara lewat OpenAI.';this.voiceHint=hint;hint.textContent='SONIC · Double tap memulai mikrofon dan audio OpenAI';
   const home=document.createElement('button');home.type='button';home.textContent='Kembali ke posisi awal';home.addEventListener('click',()=>this.returnHome());
   this.retryVoice=document.createElement('button');this.retryVoice.type='button';this.retryVoice.id='sonicVoiceRetry';
    this.retryVoice.textContent='Coba suara lagi';this.retryVoice.hidden=true;
    this.retryVoice.addEventListener('click',()=>{
      this.retryVoice.hidden=true;this.voiceHint.textContent='Menyambungkan kembali suara...';
      window.dispatchEvent(new CustomEvent('sonic:invoke',{detail:{consent:'manual_retry'}}));
    });
    this.resumeVoiceAudio=document.createElement('button');this.resumeVoiceAudio.type='button';
    this.resumeVoiceAudio.id='sonicVoiceResumeAudio';this.resumeVoiceAudio.textContent='Aktifkan audio';
    this.resumeVoiceAudio.hidden=true;
    this.resumeVoiceAudio.addEventListener('click',()=>{
      window.dispatchEvent(new CustomEvent('sonic:resume-audio'));
    });
    this.stopVoice=document.createElement('button');this.stopVoice.type='button';
    this.stopVoice.id='sonicVoiceFocusStop';this.stopVoice.textContent='Stop mikrofon';this.stopVoice.hidden=true;
    this.stopVoice.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('sonic:stop-voice')));
    this.focusControls.append(hint,this.retryVoice,this.resumeVoiceAudio,this.stopVoice,home);
    document.body.append(this.shade,this.focusControls);
   this.canvas=document.createElement('canvas');this.canvas.setAttribute('aria-hidden','true');this.float.append(this.canvas);
   this.ctx=this.canvas.getContext('2d',{alpha:true});this.reduced=!!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
   this.state='idle';this.speed=math.targetSpeed('idle',this.reduced);this.energy=0;
   this.focused=false;this.lastTap=-Infinity;this.home=null;this.running=true;this.paused=false;this.lastTime=0;this.time=0;
   this.renderer='orb-v140';
   document.body.append(this.float);this.updateHome(true);this.attach();
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  attach(){
   const press=()=>{const now=performance.now();if(math.doubleTap(this.lastTap,now)){this.lastTap=-Infinity;this.setFocus(true);window.dispatchEvent(new CustomEvent('sonic:invoke',{detail:{consent:'double_tap'}}));}else{this.lastTap=now;this.float.classList.add('preview');clearTimeout(this.tapTimer);this.tapTimer=setTimeout(()=>this.float.classList.remove('preview'),1100);}};
   this.float.addEventListener('click',e=>{e.stopPropagation();press();});
   el('sonicHeaderOrb')?.addEventListener('click',e=>{e.stopPropagation();press();});
   this.float.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();press();}else if(e.key==='Escape')this.returnHome();});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&this.focused)this.returnHome();});
   window.addEventListener('resize',()=>{this.updateHome(!this.focused);if(this.focused)this.place(math.focusRect(innerWidth,innerHeight,this.home?.width||160));});
   window.addEventListener('scroll',()=>this.updateHome(!this.focused),{passive:true});
   document.addEventListener('visibilitychange',()=>{this.paused=document.hidden;});
   window.matchMedia?.('(prefers-reduced-motion: reduce)')?.addEventListener('change',e=>{this.reduced=e.matches;this.draw();});
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
   if(on){this.backgroundInert=new Map();for(const node of document.querySelectorAll('.panel,.sidebar,.topbar,.orbit-overview,#nodeDetailPopup')){this.backgroundInert.set(node,node.inert);node.inert=true;}}
   else{for(const [node,prior] of this.backgroundInert||[])node.inert=prior;this.backgroundInert=null;}
   window.dispatchEvent(new CustomEvent('sonic:focus',{detail:{focused:on}}));
   if(on){this.place(math.focusRect(innerWidth,innerHeight,this.home?.width||160));this.float.focus({preventScroll:true});}
   else this.place(this.home);
  }
  returnHome(){this.setFocus(false);}
  voiceFeedback(message,{retry=false,audio=false,stop=false}={}){
    if(this.voiceHint&&message)this.voiceHint.textContent=String(message).slice(0,240);
    if(this.retryVoice)this.retryVoice.hidden=!retry;
    if(this.resumeVoiceAudio)this.resumeVoiceAudio.hidden=!audio;
    if(this.stopVoice)this.stopVoice.hidden=!stop;
  }
  handleCommand(text){if(math.returnIntent(text)){this.returnHome();return true;}return false;}
  setState(state){this.state=state;this.float.dataset.state=state;window.dispatchEvent(new CustomEvent('sonic:activity',{detail:{state}}));}
  dimensions(){const w=this.canvas.clientWidth,h=this.canvas.clientHeight,dpr=clamp(devicePixelRatio||1,1,2),nw=Math.max(1,Math.round(w*dpr)),nh=Math.max(1,Math.round(h*dpr));
   if(this.canvas.width!==nw||this.canvas.height!==nh){this.canvas.width=nw;this.canvas.height=nh;}return [nw,nh];
  }
  draw(){
   const ctx=this.ctx;if(!ctx)return;
   const [w,h]=this.dimensions();if(w<2||h<2)return;
   const pose=window.SonicOrbitMath.pose(this.reduced?0:this.time,this.reduced,this.state);
   ctx.clearRect(0,0,w,h);ctx.save();
   const scale=Math.min(w,h)/200,r=65*scale;
   const cx=w/2,cy=h*.48-(this.focused?0:pose.jump*7*scale);
   ctx.translate(cx,cy);ctx.scale(pose.pulse,pose.pulse);
   const circle=(radius,fill)=>{ctx.beginPath();ctx.arc(0,0,radius,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();};
   const halo=ctx.createRadialGradient(0,0,r*.75,0,0,r*1.4);
   halo.addColorStop(0,'rgba(109,86,255,0)');halo.addColorStop(.55,'rgba(108,92,244,.26)');halo.addColorStop(1,'rgba(89,127,255,0)');circle(r*1.4,halo);
   const rim=ctx.createLinearGradient(-r,-r,r,r);rim.addColorStop(0,'#d4e1ff');rim.addColorStop(.3,'#9e8aff');rim.addColorStop(.62,'#7754c0');rim.addColorStop(.85,'#55b2e1');rim.addColorStop(1,'#b47fe9');circle(r,rim);
   const face=ctx.createRadialGradient(-r*.35,-r*.65,0,r*.25,r*.3,r*1.55);face.addColorStop(0,'#a0b4df');face.addColorStop(.28,'#353e62');face.addColorStop(.49,'#111525');face.addColorStop(.73,'#100b1e');face.addColorStop(1,'#5e225d');circle(r*.9,face);
   const blush=ctx.createRadialGradient(r*.55,r*.6,0,r*.25,r*.3,r*1.1);blush.addColorStop(0,'rgba(135,47,119,.5)');blush.addColorStop(1,'rgba(135,47,119,0)');circle(r*.89,blush);
   ctx.beginPath();ctx.arc(0,0,r*.98,Math.PI*1.05,Math.PI*1.72);ctx.strokeStyle='rgba(230,233,255,.55)';ctx.lineWidth=scale*.7;ctx.stroke();
   ctx.save();ctx.translate(pose.look*8*scale,-r*.13);ctx.scale(1,pose.blink);
   const eye=ctx.createLinearGradient(0,-23*scale,0,23*scale);eye.addColorStop(0,'#f7f9ff');eye.addColorStop(1,'#acb9e5');ctx.fillStyle=eye;
   for(const x of [-24,7]){ctx.beginPath();ctx.roundRect(x*scale,-19*scale,15*scale,39*scale,8*scale);ctx.fill();}ctx.restore();
   ctx.fillStyle='#bfd0ff';for(const [x,y,size] of [[76,-70,1.4],[-79,35,1.1],[56,78,.85]]){ctx.beginPath();ctx.arc(x*scale,y*scale,size*scale,0,Math.PI*2);ctx.fill();}
   ctx.restore();
  }
  frame(timestamp){if(!this.running)return;const dt=this.lastTime?clamp((timestamp-this.lastTime)/1000,0,.12):0;this.lastTime=timestamp;
   const desired=math.targetSpeed(this.state,this.reduced);this.speed+=(desired-this.speed)*clamp(dt*4,0,1);
   if(!this.paused&&!this.reduced)this.time+=dt*this.speed;
   if(!this.paused&&this.float.offsetWidth>0&&(!this.lastDraw||timestamp-this.lastDraw>=(this.reduced?500:33))){this.draw();this.lastDraw=timestamp;}
   this.frameRequest=requestAnimationFrame(t=>this.frame(t));
  }
  stop(){this.returnHome();this.running=false;cancelAnimationFrame(this.frameRequest);clearTimeout(this.tapTimer);this.observer?.disconnect();this.float.remove();this.shade.remove();this.focusControls.remove();}
 }
 const init=()=>{const anchor=el('sonicMotionAnchor');if(anchor)window.sonicMotion=new SonicMotionCore(anchor);};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
 window.SonicMotionCore=SonicMotionCore;
})();
