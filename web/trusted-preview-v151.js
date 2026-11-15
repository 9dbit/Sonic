/* SONIC personal-guest iPhone pairing. Token stays in location fragment,
   never sent in GET URL, referer or third-party requests. */
(() => {
  "use strict";
  async function claim(token){
    const session=await fetch("/api/session",{credentials:"same-origin",cache:"no-store"}).then(r=>r.json());
    if(session.preview!==true || typeof session.preview_csrf!=="string")throw Error("SONIC preview is unavailable");
    const r=await fetch("/api/preview/trusted/claim",{
      method:"POST",credentials:"same-origin",cache:"no-store",
      headers:{"Content-Type":"application/json","X-Sonic-Preview-CSRF":session.preview_csrf},
      body:JSON.stringify({token})
    });
    const response=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(typeof response.detail==="string"?response.detail:"Pairing unsuccessful");
    if(response.paired!==true)throw Error("Pairing not confirmed");
  }
  let pairing=false;
  async function attemptPair(){
    const value=location.hash||"";
    if(!value.startsWith("#sonic-pair=")||pairing)return;
    pairing=true;
    const token=value.substring("#sonic-pair=".length);
    const notice=document.createElement("div");
    notice.id="sonicTrustedPairStatus";
    notice.setAttribute("role","status");
    notice.style.cssText="position:fixed;z-index:10001;top:max(20px,env(safe-area-inset-top));left:12px;right:12px;max-width:420px;margin:auto;background:#20202a;color:#f3f2ff;border-radius:20px;padding:18px;font:14px/1.5 system-ui;box-shadow:0 10px 40px #0008";
    notice.textContent="Pairing your iPhone for read-only SONIC uptime…";
    document.body.appendChild(notice);
    // Never persist, print, or send the pairing token to analytics.
    if(!/^[a-zA-Z0-9_-]{32,128}$/.test(token)){
      history.replaceState(null,"",location.pathname+location.search);
      notice.textContent="Pairing link format invalid. Request a new trusted link.";
      return;
    }
    try{
      await claim(token);
      history.replaceState(null,"",location.pathname+location.search+"#uptime");
      notice.textContent="iPhone paired. Opening SONIC uptime…";
      location.reload();
    }catch(err){
      history.replaceState(null,"",location.pathname+location.search);
      notice.textContent="Pairing failed or link expired. Request a new link from your authorized TRADEVICEPC.";
    }
  }
  if(document.readyState==="loading")window.addEventListener("DOMContentLoaded",attemptPair);
  else attemptPair();
  window.addEventListener("hashchange",attemptPair);
  // Navigate directly to uptime after a successful pairing or PWA reopen.
  function openUptime(){
    if(location.hash!=="#uptime")return;
    const show=()=>{
      if(!document.body.classList.contains("sonic-open-preview"))return false;
      document.querySelector('.nav[data-tab="devices"]')?.click();
      return true;
    };
    if(show())return;
    const watcher=new MutationObserver(()=>{if(show())watcher.disconnect();});
    watcher.observe(document.body,{attributes:true,attributeFilter:["class"]});
    setTimeout(()=>watcher.disconnect(),12000);
  }
  if(document.readyState==="loading")window.addEventListener("DOMContentLoaded",openUptime);
  else openUptime();
})();
