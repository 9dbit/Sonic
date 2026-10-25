/* SONIC V0.6: true-alpha WebGL keyed rendering of the user's original particles.
   Browser-decoded MP4 carries the dynamics; black pixels are removed in the
   GPU fragment shader, not via CSS blending against a black rectangle.
   Mouse/touch focus uses fixed-position rect interpolation and restores home. */
(()=>{'use strict';
 const el=id=>document.getElementById(id);
 const math=window.SonicMotionMath;
 class SonicMotionCore {
  constructor(anchor){
   this.anchor=anchor;this.float=document.createElement('div');this.float.id='sonicMotionFloat';
   this.float.className='sonic-motion-float';this.float.dataset.state='idle';
   this.float.setAttribute('role','button');this.float.tabIndex=0;
   this.float.setAttribute('aria-label','SONIC Motion Core. Tap to enlarge. Double-tap within one second to focus in the center.');
   this.canvas=document.createElement('canvas');this.canvas.setAttribute('aria-hidden','true');this.float.append(this.canvas);
   this.video=document.createElement('video');this.video.src='/assets/sonic-particles.mp4';
   this.video.preload='auto';this.video.loop=true;this.video.muted=true;this.video.playsInline=true;
   this.video.setAttribute('playsinline','');this.video.setAttribute('webkit-playsinline','');
   this.video.setAttribute('aria-hidden','true');this.video.style.display='none';this.float.append(this.video);
   this.reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches||false;
   this.state='idle';this.speed=math.targetSpeed('idle',this.reduced);this.focused=false;this.lastTap=-Infinity;this.preview=false;
   this.context=null;this.program=null;this.ready=false;this.paused=false;this.home=null;this.running=true;
   document.body.append(this.float);
   this.makeGL();this.updateHome(true);this.attach();
   this.video.addEventListener('loadeddata',()=>{this.video.play().catch(()=>{});});
   this.video.play().catch(()=>{});
   this.raf=window.requestAnimationFrame(()=>this.frame());
  }
  makeGL(){
   const canvas=this.canvas, gl=canvas.getContext('webgl',{alpha:true,depth:false,antialias:false,premultipliedAlpha:false})||canvas.getContext('experimental-webgl',{alpha:true,depth:false,premultipliedAlpha:false});
   if(!gl){this.context=canvas.getContext('2d',{willReadFrequently:true});return;}
   const shader=(type,source)=>{const sh=gl.createShader(type);gl.shaderSource(sh,source);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error('Motion shader unavailable');return sh;};
   try{
    const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,'attribute vec2 p;varying vec2 v;void main(){v=(p+1.0)*.5;gl_Position=vec4(p,0.,1.);}'));
    gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float;varying vec2 v;uniform sampler2D image;uniform float energy;void main(){vec3 rgb=texture2D(image,vec2(v.x,1.0-v.y)).rgb;float peak=max(max(rgb.r,rgb.g),rgb.b);float a=smoothstep(.045,.22,peak);vec3 silver=mix(rgb,vec3(dot(rgb,vec3(.29,.59,.12))),.34);silver*=1.0+energy*.04;gl_FragColor=vec4(silver,a);}'));
    gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Motion shader link failed');gl.useProgram(program);
    const pos=gl.getAttribLocation(program,'p'), buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
    const tex=gl.createTexture();gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tex);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    this.gl=gl;this.tex=tex;this.program=program;this.energy=gl.getUniformLocation(program,'energy');gl.uniform1i(gl.getUniformLocation(program,'image'),0);this.ready=true;
   }catch(_){this.gl=null;this.context=canvas.getContext('2d',{willReadFrequently:true});}
  }
  attach(){
   const press=()=>{const now=performance.now();if(math.doubleTap(this.lastTap,now)){this.lastTap=-Infinity;this.setFocus(!this.focused);}else{this.lastTap=now;this.preview=true;this.float.classList.add('preview');window.setTimeout(()=>{this.preview=false;this.float.classList.remove('preview');},1300);}};
   this.float.addEventListener('click',e=>{e.stopPropagation();press();});
   this.float.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();press();}if(e.key==='Escape'){this.returnHome();}});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&this.focused)this.returnHome();});
   window.addEventListener('resize',()=>this.updateHome(!this.focused));
   window.addEventListener('scroll',()=>this.updateHome(!this.focused),{passive:true});
   document.addEventListener('visibilitychange',()=>{this.paused=document.hidden;if(!document.hidden)this.video.play().catch(()=>{});else this.video.pause();});
   this.float.addEventListener('mouseenter',()=>{if(!this.focused)this.float.classList.add('hover');});
   this.float.addEventListener('mouseleave',()=>this.float.classList.remove('hover'));
  }
  updateHome(apply=false){
   const r=this.anchor.getBoundingClientRect();if(r.width&&r.height){this.home={left:r.left,top:r.top,width:r.width,height:r.height};}
   if(apply&&!this.focused&&this.home)this.place(this.home);
  }
  place(rect){for(const key of ['left','top','width','height'])this.float.style[key]=rect[key]+'px';}
  setFocus(on){if(on===this.focused)return;this.updateHome(false);this.focused=on;this.float.classList.toggle('focused',on);this.float.classList.remove('preview');
    this.float.setAttribute('aria-pressed',String(on));
    if(on){this.place(math.focusRect(window.innerWidth,window.innerHeight,this.home?.width||160));this.float.focus({preventScroll:true});}
    else if(this.home)this.place(this.home);
  }
  returnHome(){this.setFocus(false);}
  handleCommand(text){if(math.returnIntent(text)){this.returnHome();return true;}return false;}
  setState(state){this.state=state;this.float.dataset.state=state;}
  resizeCanvas(){const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;const ratio=Math.min(window.devicePixelRatio||1,2);const width=Math.max(1,Math.round(w*ratio)),height=Math.max(1,Math.round(h*ratio));if(this.canvas.width!==width||this.canvas.height!==height){this.canvas.width=width;this.canvas.height=height;}}
  draw(){if(this.video.readyState<2)return;this.resizeCanvas();const c=this.canvas;
    if(this.gl){const gl=this.gl;gl.viewport(0,0,c.width,c.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.bindTexture(gl.TEXTURE_2D,this.tex);try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,this.video);}catch(_){return;}gl.uniform1f(this.energy,this.state==='speaking'?1:0);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);}
    else if(this.context){const ctx=this.context;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(this.video,0,0,c.width,c.height);const frame=ctx.getImageData(0,0,c.width,c.height);const d=frame.data;for(let i=0;i<d.length;i+=4){const peak=Math.max(d[i],d[i+1],d[i+2]);d[i+3]=Math.round(Math.max(0,Math.min(1,(peak-10)/45))*255);}ctx.putImageData(frame,0,0);}
  }
  frame(){if(!this.running)return;const desired=math.targetSpeed(this.state,this.reduced);this.speed+=Math.max(-0.04,Math.min(0.04,(desired-this.speed)*.09));
    if(Math.abs(this.video.playbackRate-this.speed)>.025)this.video.playbackRate=Math.max(.2,this.speed);
    if(!this.paused)this.draw();this.raf=requestAnimationFrame(()=>this.frame());
  }
  stop(){this.running=false;cancelAnimationFrame(this.raf);this.video.pause();this.float.remove();}
 }
 const init=()=>{const anchor=el('sonicMotionAnchor');if(anchor){window.sonicMotion=new SonicMotionCore(anchor);}};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
 window.SonicMotionCore=SonicMotionCore;
})();
