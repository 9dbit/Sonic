/* Login visual/focus isolation only. Server session and CSRF remain authoritative. */
(() => {
  'use strict';
  function init() {
    const overlay=document.getElementById('loginOverlay');
    if (!overlay) return;
    const previous=new Map();
    let locked=null;
    overlay.setAttribute('role','dialog');
    overlay.setAttribute('aria-label','SONIC owner login');
    function isolate(element) {
      if (!(element instanceof HTMLElement) || element===overlay ||
          ['SCRIPT','STYLE','LINK'].includes(element.tagName)) return;
      if (!previous.has(element)) previous.set(element,{
        inert:element.inert, aria:element.getAttribute('aria-hidden')
      });
      element.inert=true;
      element.setAttribute('aria-hidden','true');
    }
    function sync() {
      const next=!overlay.classList.contains('hidden') && !overlay.hidden;
      const changed=locked!==next;
      locked=next;
      document.body.classList.toggle('sonic-auth-locked',locked);
      overlay.setAttribute('aria-modal',String(locked));
      if (locked) {
        for (const child of document.body.children) isolate(child);
        const focused=document.activeElement;
        if (focused instanceof HTMLElement && focused!==document.body && !overlay.contains(focused)) focused.blur();
      } else {
        for (const [element,state] of previous) {
          if (!element.isConnected) continue;
          element.inert=state.inert;
          if (state.aria===null) element.removeAttribute('aria-hidden');
          else element.setAttribute('aria-hidden',state.aria);
        }
        previous.clear();
        if (changed) requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
      }
    }
    new MutationObserver(sync).observe(overlay,{attributes:true,attributeFilter:['class','hidden']});
    new MutationObserver(records=>{
      if (!locked) return;
      for (const record of records) for (const child of record.addedNodes) isolate(child);
    }).observe(document.body,{childList:true});
    document.addEventListener('keydown',event=>{
      if (!locked || event.key!=='Tab') return;
      const items=[...overlay.querySelectorAll('input:not(:disabled),button:not(:disabled),a[href],[tabindex="0"]')]
        .filter(node=>node.getClientRects().length && getComputedStyle(node).visibility!=='hidden');
      if (!items.length) return;
      const first=items[0], last=items[items.length-1];
      if (!overlay.contains(document.activeElement)) {
        event.preventDefault();(event.shiftKey?last:first).focus();
      } else if (event.shiftKey && document.activeElement===first) {
        event.preventDefault();last.focus();
      } else if (!event.shiftKey && document.activeElement===last) {
        event.preventDefault();first.focus();
      }
    },true);
    sync();
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
