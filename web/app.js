(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let csrf = null;
  let voiceOn = false;
  let waiting = false;
  let speech = null;
  const tabs = {chat:"chatPanel",memory:"memoryPanel",devices:"devicesPanel"};
  const API = async (path, opts={}) => {
    const headers = {"Content-Type":"application/json", ...(opts.headers || {})};
    if (csrf && opts.method && opts.method !== "GET") headers["X-Sonic-CSRF"] = csrf;
    const response = await fetch(path, {credentials:"same-origin",...opts,headers});
    const body = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(body.detail || body.error || "Request failed ("+response.status+")");
    return body;
  };
  const showError = (message) => { $("notice").textContent = message; };
  const setTab = tab => {
    Object.entries(tabs).forEach(([name,id])=>$(id).classList.toggle("hidden",name!==tab));
    document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
    $("pageTitle").textContent = ({chat:"Command Center",memory:"Memory Vault",devices:"Device Hub"})[tab];
    if(tab==="memory") loadMemory();
    if(tab==="devices") loadDevice();
  };
  function line(role, content, error=false) {
    $("hero")?.remove();
    const wrapper=document.createElement("div");
    wrapper.className = "message "+role+(error?" error":"");
    const speaker=document.createElement("span");
    speaker.className="speaker";
    speaker.textContent=role==="user"?"YOU":"SONIC";
    const body=document.createElement("div");
    body.className="body";
    body.textContent=content;
    wrapper.append(speaker,body);
    $("chatFeed").append(wrapper);
    $("chatFeed").scrollTop=$("chatFeed").scrollHeight;
    return wrapper;
  }
  function speak(text) {
    if(!voiceOn || !("speechSynthesis" in window))return;
    window.speechSynthesis.cancel();
    const voice = new SpeechSynthesisUtterance(text.slice(0,1600));
    voice.lang = /[^\x00-\x7F]/.test(text) ? "id-ID" : "id-ID";
    voice.rate=1.03;
    window.speechSynthesis.speak(voice);
  }
  async function send() {
    const msg=$("message").value.trim();
    if(!msg || waiting)return;
    waiting=true;$("send").disabled=true;
    $("message").value="";line("user",msg);
    const placeholder=line("assistant","SONIC is thinking…");
    try {
      const result=await API("/api/chat",{method:"POST",body:JSON.stringify({message:msg})});
      placeholder.querySelector(".body").textContent=result.reply;
      speak(result.reply);
    } catch(e) {
      placeholder.classList.add("error");
      placeholder.querySelector(".body").textContent=e.message;
    } finally {waiting=false;$("send").disabled=false;$("message").focus();}
  }
  async function loadHistory(){
    try {
      const data=await API("/api/history");
      if(data.messages.length) {
        $("chatFeed").replaceChildren();
        data.messages.forEach(m=>line(m.role,m.content));
      }
    } catch(e){showError(e.message);}
  }
  async function loadMemory(){
    const list=$("memoryList");
    try{
      const data=await API("/api/memories");
      list.replaceChildren();
      if(!data.memories.length){list.textContent="No memories saved yet.";return;}
      data.memories.forEach(m=>{
        const item=document.createElement("div");item.className="memory-item";
        const text=document.createElement("span");text.textContent=m.text;
        const remove=document.createElement("button");remove.textContent="Delete";
        remove.addEventListener("click",async()=>{
          if(!window.confirm("Delete this SONIC memory?"))return;
          try{await API("/api/memories/"+m.id,{method:"DELETE"});loadMemory();}catch(e){showError(e.message);}
        });
        item.append(text,remove);list.append(item);
      });
    }catch(e){list.textContent=e.message;}
  }
  async function loadDevice(){
    try{
      const d=await API("/api/device/status");
      $("deviceName").textContent=d.hostname||d.device_id||"TRADEVICEPC";
      $("deviceDetail").textContent=d.connected?"Last seen "+d.last_seen_seconds_ago+" seconds ago": "Waiting for companion pairing or heartbeat";
      $("deviceBadge").textContent=d.connected?"Online":"Offline";
      $("devicePill").textContent=d.connected?"● PC online":"● PC offline";
      $("snapshotDevice").disabled=!d.connected;
    }catch(e){$("deviceDetail").textContent=e.message;}
  }
  async function snapshot(){
    $("snapshotDevice").disabled=true;
    try{
      const job=await API("/api/device/jobs",{method:"POST",body:JSON.stringify({action:"system.status"})});
      $("deviceResult").textContent="Waiting for Windows companion…";
      for(let i=0;i<12;i++){
        await new Promise(resolve=>setTimeout(resolve,1500));
        const latest=await API("/api/device/jobs/"+job.id);
        if(latest.state==="done"||latest.state==="failed"){
          $("deviceResult").textContent=JSON.stringify(latest.result,null,2);
          break;
        }
      }
    }catch(e){$("deviceResult").textContent=e.message;}finally{loadDevice();}
  }
  async function initialize(){
    const result=await API("/api/session");
    $("loginOverlay").classList.toggle("hidden",result.authenticated!==false);
    if(result.authenticated){
      csrf=result.csrf;
      $("brainPill").textContent="Model: "+result.model;
      await Promise.all([loadHistory(),loadDevice()]);
    }
  }
  $("loginForm").addEventListener("submit",async event=>{
    event.preventDefault();
    $("loginError").textContent="";
    const token=$("ownerToken").value;
    $("ownerToken").value="";
    try{
      const r=await API("/api/login",{method:"POST",body:JSON.stringify({token})});
      csrf=r.csrf;
      await initialize();
    }catch(e){$("loginError").textContent=e.message;}
  });
  $("logout").addEventListener("click",async()=>{
    try{await API("/api/logout",{method:"POST"});}catch(e){}
    csrf=null;window.speechSynthesis?.cancel();window.location.reload();
  });
  $("send").addEventListener("click",send);
  $("message").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}});
  document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>setTab(b.dataset.tab)));
  document.querySelectorAll("[data-prompt]").forEach(b=>b.addEventListener("click",()=>{
    $("message").value=b.dataset.prompt;send();
  }));
  $("memoryForm").addEventListener("submit",async e=>{
    e.preventDefault();
    try{await API("/api/memories",{method:"POST",body:JSON.stringify({text:$("memoryInput").value})});
      $("memoryInput").value="";loadMemory();
    }catch(err){showError(err.message);}
  });
  $("refreshDevice").addEventListener("click",loadDevice);
  $("snapshotDevice").addEventListener("click",snapshot);
  $("voice").addEventListener("click",()=>{
    voiceOn=!voiceOn;
    $("voice").classList.toggle("on",voiceOn);
    $("voice").textContent=voiceOn?"◉ Voice on":"◌ Voice off";
    $("voice").setAttribute("aria-pressed",String(voiceOn));
    if(!voiceOn)window.speechSynthesis?.cancel();
  });

  async function sendVision(dataUrl, kind) {
    if(waiting){showError("SONIC is still answering. Try again after the response.");return;}
    const [header,base64]=dataUrl.split(",",2);
    const mimeType=header.match(/^data:(image\/(?:png|jpeg|webp));base64$/)?.[1];
    if(!mimeType || !base64){showError("Unsupported image format.");return;}
    const question=$("message").value.trim().slice(0,500)||"Describe and analyze what you can see in this image.";
    $("message").value="";
    setTab("chat");
    const text="["+kind+" snapshot] "+question;
    line("user",text);
    const pending=line("assistant","SONIC is looking at your image…");
    waiting=true;$("send").disabled=true;
    try{
      const response=await API("/api/vision",{
        method:"POST",body:JSON.stringify({mimeType,base64,question})
      });
      pending.querySelector(".body").textContent=response.reply;
      speak(response.reply);
    }catch(err){
      pending.classList.add("error");
      pending.querySelector(".body").textContent=err.message;
    }finally{waiting=false;$("send").disabled=false;}
  }
  async function captureOnce(kind) {
    const isScreen=kind==="Screen";
    if(!window.confirm(
      "SONIC will capture one "+(isScreen?"screen":"camera")+" frame and send it to the configured OpenAI vision provider. No continuous recording and no local saving. Continue?"
    ))return;
    let stream;
    try {
      stream=isScreen
        ? await navigator.mediaDevices.getDisplayMedia({video:true,audio:false})
        : await navigator.mediaDevices.getUserMedia({video:true,audio:false});
      const video=document.createElement("video");
      video.muted=true;video.playsInline=true;video.srcObject=stream;
      await video.play();
      await new Promise(resolve=>setTimeout(resolve,350));
      if(!video.videoWidth||!video.videoHeight)throw new Error("No video frame available.");
      const width=Math.min(1280,video.videoWidth);
      const height=Math.round(width*video.videoHeight/video.videoWidth);
      const canvas=document.createElement("canvas");canvas.width=width;canvas.height=height;
      canvas.getContext("2d").drawImage(video,0,0,width,height);
      const dataUrl=canvas.toDataURL("image/jpeg",0.76);
      stream.getTracks().forEach(track=>track.stop());stream=null;
      await sendVision(dataUrl,kind);
    }catch(error){showError("Vision capture cancelled or unavailable: "+error.message);}
    finally{stream?.getTracks().forEach(track=>track.stop());}
  }
  $("camera").addEventListener("click",()=>captureOnce("Camera"));
  $("screen").addEventListener("click",()=>captureOnce("Screen"));
  $("image").addEventListener("click",()=>$("imageFile").click());
  $("imageFile").addEventListener("change",async e=>{
    const file=e.target.files?.[0];
    e.target.value="";
    if(!file)return;
    if(file.size>3*1024*1024){showError("Image exceeds the 3 MB limit.");return;}
    if(!["image/jpeg","image/png","image/webp"].includes(file.type)){showError("Use JPG, PNG or WebP.");return;}
    const reader=new FileReader();
    reader.onerror=()=>showError("Could not read the selected image.");
    reader.onload=()=>{sendVision(String(reader.result),"Image");};
    reader.readAsDataURL(file);
  });

  $("mic").addEventListener("click",()=>{
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
    if(!Recognition){showError("Voice recognition is unavailable in this browser. Text chat still works.");return;}
    if(speech){speech.stop();speech=null;return;}
    const recognizer=new Recognition();
    recognizer.lang="id-ID";recognizer.interimResults=false;
    recognizer.onresult=e=>{$("message").value=e.results[0][0].transcript;$("message").focus();};
    recognizer.onerror=()=>{showError("Microphone unavailable or permission denied.");};
    recognizer.onend=()=>{speech=null;$("mic").textContent="◉";};
    speech=recognizer;$("mic").textContent="■";recognizer.start();
  });
  initialize().catch(e=>showError(e.message));
  setInterval(()=>{if(csrf)loadDevice();},30000);
})();
