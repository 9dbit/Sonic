/* SONIC knowledge renderer. Original, dependency-free, same-origin WebGL.
 * Real xyz coordinates + perspective camera; Canvas2D fallback, not a bitmap.
 * The server supplies every node/link. No decorative or seeded knowledge nodes.
 */
(() => {
  'use strict';
  const PALETTE = {system:'#d9e7ec',memory:'#489ffa',topic:'#f1bd36',tool:'#dc58b1',device:'#35d5ad'};
  const hex = s => [1,3,5].map(i=>parseInt(s.slice(i,i+2),16)/255);
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
  const seed = s => {let h=2166136261;for(const c of s){h^=c.charCodeAt(0);h=Math.imul(h,16777619);}return h>>>0;};
  const random = s => () => {s^=s<<13;s^=s>>>17;s^=s<<5;return (s>>>0)/4294967296;};
  function shortestPath(start,end,edges,visible){
    const adjacency=new Map();
    for(const e of edges){if(visible&&(!visible.has(e.source)||!visible.has(e.target)))continue;
      if(!adjacency.has(e.source))adjacency.set(e.source,[]);if(!adjacency.has(e.target))adjacency.set(e.target,[]);
      adjacency.get(e.source).push(e.target);adjacency.get(e.target).push(e.source);}
    const parents=new Map([[start,null]]),queue=[start];
    for(let i=0;i<queue.length;i++){const id=queue[i];if(id===end){const path=[];for(let x=end;x!==null;x=parents.get(x))path.unshift(x);return path;}
      for(const next of adjacency.get(id)||[]){if(!parents.has(next)){parents.set(next,id);queue.push(next);}}}
    return [];
  }
  class SonicGraph {
    constructor(stage, callbacks={}){
      this.stage=stage;this.callbacks=callbacks;this.nodes=[];this.edges=[];this.lookup=new Map();this.positions=new Map();
      this.filters=new Set(Object.keys(PALETTE));this.selected=null;this.path=[];this.depth=1;this.visible=false;
      this.yaw=-0.15;this.pitch=0.08;this.distance=700;this.target=[0,0,0];this.pan=[0,0];this.is3D=true;this.autoRotate=false;
      this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;this.pointers=new Map();this.lastFrame=0;
      this.canvas=document.createElement('canvas');this.canvas.setAttribute('aria-hidden','true');
      this.labels=document.createElement('canvas');this.labels.className='graph-labels';this.labels.setAttribute('aria-hidden','true');
      stage.append(this.canvas,this.labels);this.ctx=this.labels.getContext('2d');
      this.tooltip=document.createElement('div');this.tooltip.className='node-tooltip hidden';stage.append(this.tooltip);
      this.initGL();
      this.canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.gl=null;this.engine='Canvas fallback';this.invalidate();});
      this.canvas.addEventListener('webglcontextrestored',()=>{this.initGL();this.invalidate();});
      this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(stage);
      this.attachInput();
      document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(this.frame);this.frame=null;}else if(this.visible)this.invalidate();});
      this.resize();
    }
    initGL(){
      try{
        // RGB is accumulated premultiplied, with a separate source-alpha factor.
        // This avoids multiplying faint edge opacity twice during compositing.
        const gl=this.canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:true,powerPreference:'low-power'});
        if(!gl)throw Error('WebGL unavailable');
        const vs=`attribute vec3 a_position;attribute vec4 a_color;attribute float a_size;varying vec4 v_color;void main(){gl_Position=vec4(a_position,1.);gl_PointSize=a_size;v_color=a_color;}`;
        const fs=`precision mediump float;varying vec4 v_color;uniform float u_points;void main(){if(u_points<.5){gl_FragColor=v_color;return;}vec2 p=gl_PointCoord*2.-1.;float r=dot(p,p);if(r>1.)discard;float z=sqrt(max(0.,1.-r));vec3 n=vec3(p.x,-p.y,z);float light=.30+.70*max(0.,dot(n,normalize(vec3(-.45,.6,1.))));float spec=pow(max(0.,dot(n,normalize(vec3(-.35,.45,1.)))),18.)*.3;float a=(1.-smoothstep(.78,1.,sqrt(r)))*v_color.a;gl_FragColor=vec4(v_color.rgb*light+vec3(spec),a);}`;
        const compile=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('Shader compile failed');return s;};
        const v=compile(gl.VERTEX_SHADER,vs),f=compile(gl.FRAGMENT_SHADER,fs),p=gl.createProgram();gl.attachShader(p,v);gl.attachShader(p,f);gl.linkProgram(p);
        if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error('Program link failed');
        gl.deleteShader(v);gl.deleteShader(f);gl.useProgram(p);this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
        for(const [name,size,offset] of [['a_position',3,0],['a_color',4,12],['a_size',1,28]]){const loc=gl.getAttribLocation(p,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,32,offset);}
        this.pointUniform=gl.getUniformLocation(p,'u_points');this.program=p;this.gl=gl;this.engine='WebGL / perspective 3D';
        this.maxPoint=gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1];gl.enable(gl.BLEND);
        gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.disable(gl.DEPTH_TEST);
      }catch(_){this.gl=null;this.engine='Canvas / perspective 3D';}
    }
    resize(){
      const rect=this.stage.getBoundingClientRect();this.width=Math.max(1,rect.width);this.height=Math.max(1,rect.height);
      this.dpr=Math.min(window.devicePixelRatio||1,2);
      for(const c of [this.canvas,this.labels]){c.width=Math.round(this.width*this.dpr);c.height=Math.round(this.height*this.dpr);}
      this.ctx.setTransform(this.dpr,0,0,this.dpr,0,0);if(this.gl)this.gl.viewport(0,0,this.canvas.width,this.canvas.height);this.invalidate();
    }
    setData(data){
      this.nodes=data.nodes.map(n=>({...n,color:PALETTE[n.category]||'#8193a7'}));this.lookup=new Map(this.nodes.map(n=>[n.id,n]));
      this.edges=data.edges.filter(e=>this.lookup.has(e.source)&&this.lookup.has(e.target));
      this.layout();if(this.selected&&!this.lookup.has(this.selected))this.selected=null;
      if(!this.initialized){this.fit();this.initialized=true;}this.updateHighlight();this.invalidate();
      this.stage.dataset.nodes=String(this.nodes.length);this.stage.dataset.edges=String(this.edges.length);
    }
    layout(){
      const rng=random(141),count=this.nodes.length,radius=70+Math.sqrt(count)*16;
      if(!count){this.positions.clear();return;}
      const positions=this.nodes.map((n,i)=>{
        if(this.positions.has(n.id))return [...this.positions.get(n.id)];
        const r=random(seed(n.id));let x=(r()-.5)*radius*2,y=(r()-.5)*radius*1.7,z=(r()-.5)*radius*1.5;
        if(n.category==='tool')x+=radius*.8;
        if(n.category==='memory')x-=radius*.35;
        if(n.id==='system:sonic'){x=0;y=0;z=0;}
        return [x,y,z];});
      const index=new Map(this.nodes.map((n,i)=>[n.id,i]));
      const edges=this.edges.map(e=>[index.get(e.source),index.get(e.target),e.kind]);
      // Bounded repulsion; sampling prevents quadratic cost on large vaults.
      const samples=Math.min(count,90),iterations=this.initialized?24:90;
      for(let step=0;step<iterations;step++){
        const forces=positions.map(()=>[0,0,0]);
        for(let i=0;i<count;i++)for(let k=0;k<samples;k++){
          const j=count<=90?k:Math.floor(rng()*count);if(i===j)continue;
          const d=positions[i].map((v,a)=>v-positions[j][a]);const d2=d.reduce((a,v)=>a+v*v,0)+70;
          const force=Math.min(2.3,1000/d2)/Math.sqrt(d2);
          for(let a=0;a<3;a++)forces[i][a]+=d[a]*force;
        }
        for(const [i,j,kind] of edges){const delta=positions[j].map((v,a)=>v-positions[i][a]);const len=Math.hypot(...delta)||1;
          const ideal=kind==='lexical'?66:kind==='owner_link'?80:110;const strength=(len-ideal)*.012/len;
          for(let a=0;a<3;a++){forces[i][a]+=delta[a]*strength;forces[j][a]-=delta[a]*strength;}}
        for(let i=0;i<count;i++)for(let a=0;a<3;a++)positions[i][a]+=clamp(forces[i][a]-positions[i][a]*.001,-5,5);
      }
      this.positions=new Map(this.nodes.map((n,i)=>[n.id,positions[i]]));
    }
    fit(){
      this.target=[0,0,0];this.pan=[0,0];this.yaw=-.15;this.pitch=.08;
      const points=this.nodes.filter(n=>this.filters.has(n.category)).map(n=>this.positions.get(n.id));
      if(points.length){this.target=[0,1,2].map(a=>points.reduce((s,p)=>s+p[a],0)/points.length);}
      const radius=Math.max(100,...points.map(p=>Math.hypot(...p.map((v,a)=>v-this.target[a]))));
      this.distance=radius*(this.width<650?3.0:3.2);this.invalidate();
    }
    select(id,{focus=false,trace=false}={}){
      if(id&&!this.lookup.has(id))return;
      if(trace&&this.selected&&id){this.path=shortestPath(this.selected,id,this.edges,new Set(this.nodes.filter(n=>this.filters.has(n.category)).map(n=>n.id)));}
      else{this.path=[];this.selected=id;}
      if(focus&&id){this.target=[...this.positions.get(id)];this.distance=Math.max(240,this.distance*.72);this.pan=[0,0];}
      this.stage.dataset.selected=this.selected||'';this.updateHighlight();this.invalidate();this.callbacks.onSelect?.(this.lookup.get(this.selected)||null,this.path);
    }
    clear(){this.select(null);this.fit();}
    setFilters(filters){this.filters=new Set(filters);if(this.selected&&!this.filters.has(this.lookup.get(this.selected)?.category))this.select(null);this.updateHighlight();this.invalidate();}
    setDepth(depth){this.depth=depth;this.path=[];this.updateHighlight();this.invalidate();}
    updateHighlight(){
      if(this.path.length){this.highlight=new Set(this.path);return;}
      if(!this.selected){this.highlight=null;return;}
      const visible=new Set(this.nodes.filter(n=>this.filters.has(n.category)).map(n=>n.id));
      const all=new Set([this.selected]);let frontier=new Set([this.selected]);
      for(let i=0;i<this.depth;i++){const next=new Set();for(const e of this.edges){if(!visible.has(e.source)||!visible.has(e.target))continue;
        if(frontier.has(e.source)&&!all.has(e.target))next.add(e.target);if(frontier.has(e.target)&&!all.has(e.source))next.add(e.source);}
        for(const id of next)all.add(id);frontier=next;}
      this.highlight=all;
    }
    setVisible(visible){this.visible=visible;if(visible){this.resize();this.invalidate();}else{cancelAnimationFrame(this.frame);this.frame=null;}}
    setDimension(is3D){this.is3D=is3D;this.invalidate();}
    invalidate(){this.dirty=true;if(this.visible&&!document.hidden&&!this.frame)this.frame=requestAnimationFrame(t=>this.tick(t));}
    tick(time){this.frame=null;if(!this.visible||document.hidden)return;
      if(time-this.lastFrame>=32){if(this.autoRotate&&this.is3D&&!this.reduced&&!this.pointers.size){this.yaw+=.002;this.dirty=true;}
        if(this.dirty){this.render();this.dirty=false;}this.lastFrame=time;}
      if(this.dirty||(this.autoRotate&&!this.reduced))this.frame=requestAnimationFrame(t=>this.tick(t));
    }
    project(p){
      let [x,y,z]=p.map((v,a)=>v-this.target[a]);
      if(this.is3D){const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
        const nx=x*cy+z*sy,nz=-x*sy+z*cy;x=nx;z=y*sp+nz*cp;y=y*cp-nz*sp;}else z=0;
      const focal=Math.min(this.width,this.height)*1.08;const k=focal/Math.max(60,this.distance-z);
      const mobile=this.width<650;const cx=this.width*(mobile?.48:.54),cy=this.height*(mobile?.40:.43);
      return {x:cx+x*k+this.pan[0],y:cy+y*k+this.pan[1],z,k};
    }
    render(){
      const {ctx,width:w,height:h}=this;ctx.clearRect(0,0,w,h);
      if(this.gl){this.gl.clearColor(0,0,0,0);this.gl.clear(this.gl.COLOR_BUFFER_BIT);}
      const visible=this.nodes.filter(n=>this.filters.has(n.category));
      const projected=new Map();
      for(const n of visible){const p=this.project(this.positions.get(n.id));p.r=clamp((6+Math.sqrt(n.degree||0)*2)*(n.category==='system'?1.2:1)*p.k,3,28);p.node=n;projected.set(n.id,p);}
      const active=id=>!this.highlight||this.highlight.has(id);
      const lines=[];const vertex=(arr,p,c,a,size)=>arr.push(p.x/w*2-1,1-p.y/h*2,0,...c,a,size);
      const drawSegment=(a,b,c,alpha)=>{if(this.gl){vertex(lines,a,c,alpha,1);vertex(lines,b,c,alpha,1);}else{ctx.strokeStyle=`rgba(${c.map(x=>Math.round(x*255)).join(',')},${alpha})`;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}};
      for(const e of this.edges){const a=projected.get(e.source),b=projected.get(e.target);if(!a||!b)continue;
        const both=active(e.source)&&active(e.target),alpha=both?(this.highlight?.66:.30):.05;
        const c=e.kind==='owner_link'?[.92,.72,.28]:[.22,.69,.61];
        if(e.kind==='lexical'){const distance=Math.hypot(a.x-b.x,a.y-b.y),parts=Math.max(2,Math.ceil(distance/8));
          for(let i=0;i<parts;i+=2){let t=i/parts,u=Math.min(1,(i+1)/parts);drawSegment({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t},{x:a.x+(b.x-a.x)*u,y:a.y+(b.y-a.y)*u},c,alpha);}}
        else drawSegment(a,b,c,alpha);
      }
      if(this.gl&&lines.length)this.drawGL(lines,false);
      const dots=[],ordered=[...projected.values()].sort((a,b)=>a.z-b.z);
      for(const p of ordered){const n=p.node,on=active(n.id),c=hex(n.color),alpha=on?.96:.13;
        if(n.id===this.selected){ctx.strokeStyle='#a5f3e3';ctx.lineWidth=1;ctx.beginPath();ctx.arc(p.x,p.y,p.r+5,0,Math.PI*2);ctx.stroke();}
        if(this.gl)vertex(dots,p,c,alpha,Math.min(this.maxPoint,p.r*2*this.dpr));
        else{const grad=ctx.createRadialGradient(p.x-p.r*.3,p.y-p.r*.3,p.r*.05,p.x,p.y,p.r);grad.addColorStop(0,on?'#d5ebed':n.color);grad.addColorStop(.3,n.color);grad.addColorStop(1,'#13252d');ctx.globalAlpha=alpha;ctx.fillStyle=grad;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
      }
      if(this.gl&&dots.length)this.drawGL(dots,true);
      const labels=ordered.filter(p=>active(p.node.id)).sort((a,b)=>(b.node.id===this.selected?9999:b.node.degree)-(a.node.id===this.selected?9999:a.node.degree)).slice(0,visible.length<45?45:24);
      const occupied=[];
      for(const p of labels){const n=p.node;if(p.x<15||p.x>w-15||p.y<10||p.y>h-15)continue;
        ctx.font=(n.id===this.selected?'600 12px':'10px')+' -apple-system,Segoe UI,sans-serif';ctx.textAlign='center';ctx.fillStyle=n.id===this.selected?'#d5eee8':'#89a9b6';
        const label=n.label.length>31?n.label.slice(0,29)+'...':n.label,tw=ctx.measureText(label).width;
        let place=null;for(const y of [p.y+p.r+15,p.y-p.r-7]){const rect={l:p.x-tw/2-4,r:p.x+tw/2+4,t:y-11,b:y+4};
          if(rect.l<4||rect.r>w-4)continue;
          if(!occupied.some(o=>rect.l<o.r&&rect.r>o.l&&rect.t<o.b&&rect.b>o.t)){place={rect,y};break;}}
        if(!place&&n.id!==this.selected)continue;
        place=place||{rect:{l:p.x-tw/2,r:p.x+tw/2,t:p.y+p.r+4,b:p.y+p.r+19},y:p.y+p.r+15};occupied.push(place.rect);
        ctx.shadowColor='#000';ctx.shadowBlur=4;ctx.fillText(label,p.x,place.y);ctx.shadowBlur=0;
      }
      this.projected=projected;this.stage.dataset.renderedNodes=String(visible.length);this.stage.dataset.engine=this.engine;
      this.callbacks.onRender?.({engine:this.engine,nodes:visible.length});
    }
    drawGL(values,points){const gl=this.gl;gl.useProgram(this.program);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(values),gl.DYNAMIC_DRAW);gl.uniform1f(this.pointUniform,points?1:0);gl.drawArrays(points?gl.POINTS:gl.LINES,0,values.length/8);}
    pick(x,y){let best=null,score=Infinity;for(const p of this.projected?.values()||[]){const d=Math.hypot(p.x-x,p.y-y);if(d<Math.max(p.r+7,13)&&d<score){score=d;best=p.node;}}return best;}
    attachInput(){
      const stage=this.stage,coord=e=>{const r=stage.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
      stage.addEventListener('contextmenu',e=>e.preventDefault());
      stage.addEventListener('wheel',e=>{e.preventDefault();this.distance=clamp(this.distance*Math.exp(e.deltaY*.0012),120,6000);this.invalidate();},{passive:false});
      stage.addEventListener('pointerdown',e=>{if(e.target!==this.canvas)return;stage.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,coord(e));this.down=coord(e);this.moved=false;stage.classList.add('dragging');this.tooltip.classList.add('hidden');});
      stage.addEventListener('pointermove',e=>{
        const pos=coord(e),old=this.pointers.get(e.pointerId);
        if(old){const dx=pos[0]-old[0],dy=pos[1]-old[1];if(Math.hypot(pos[0]-this.down[0],pos[1]-this.down[1])>5)this.moved=true;
          if(this.pointers.size>=2){const other=[...this.pointers.entries()].find(([id])=>id!==e.pointerId)?.[1];if(other){const before=Math.hypot(old[0]-other[0],old[1]-other[1]),after=Math.hypot(pos[0]-other[0],pos[1]-other[1]);if(after>8&&before>8)this.distance=clamp(this.distance*before/after,120,6000);this.pan[0]+=dx*.5;this.pan[1]+=dy*.5;}}
          else if(e.shiftKey||e.buttons===2||!this.is3D){this.pan[0]+=dx;this.pan[1]+=dy;}
          else{this.yaw+=dx*.006;this.pitch=clamp(this.pitch+dy*.006,-1.4,1.4);}
          this.pointers.set(e.pointerId,pos);this.invalidate();
        }else if(e.pointerType!=='touch'){const n=this.pick(...pos);this.tooltip.classList.toggle('hidden',!n);if(n){this.tooltip.textContent=n.label;this.tooltip.style.left=clamp(pos[0]+15,8,this.width-250)+'px';this.tooltip.style.top=(pos[1]+15)+'px';}}
      });
      const end=e=>{const pos=coord(e);if(this.pointers.has(e.pointerId)&&!this.moved&&this.pointers.size===1){const n=this.pick(...pos);if(n){const trace=e.shiftKey||this.traceArmed;this.traceArmed=false;this.select(n.id,{trace});}}
        this.pointers.delete(e.pointerId);if(!this.pointers.size)stage.classList.remove('dragging');};
      stage.addEventListener('pointerup',end);stage.addEventListener('pointercancel',e=>{this.pointers.delete(e.pointerId);stage.classList.remove('dragging');});
      stage.addEventListener('pointerleave',()=>this.tooltip.classList.add('hidden'));
      stage.addEventListener('dblclick',e=>{const n=this.pick(...coord(e));if(n)this.select(n.id,{focus:true});});
      stage.addEventListener('keydown',e=>{if(e.target!==stage)return;let handled=true;switch(e.key){case 'ArrowLeft':this.yaw-=.12;break;case 'ArrowRight':this.yaw+=.12;break;case 'ArrowUp':this.pitch-=.12;break;case 'ArrowDown':this.pitch+=.12;break;case '+':case '=':this.distance*=.88;break;case '-':this.distance*=1.12;break;case 'Escape':this.clear();break;default:handled=false;}if(handled){e.preventDefault();this.invalidate();}});
    }
  }
  SonicGraph.palette=PALETTE;SonicGraph.shortestPath=shortestPath;window.SonicGraph=SonicGraph;
})();
