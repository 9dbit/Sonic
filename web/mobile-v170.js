/* SONIC v1.7 iPhone interaction layer. Existing SONIC handlers remain authoritative. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  function go(tab) {
    const button=document.querySelector('.sidebar .nav[data-tab="'+tab+'"]');
    button?.click();
  }
  function more(open) {
    if (!$('mobileMoreMenu')) return;
    $('mobileMoreMenu').hidden=!open;
    $('mobileMoreNav')?.setAttribute('aria-expanded',String(open));
  }
  function adjust() {
    const small=matchMedia('(max-width:720px)').matches;
    const h=window.visualViewport?.height;
    if(small && h && h>240){
      document.documentElement.style.setProperty('--sonic-visual-vh',h+'px');
    } else {
      document.documentElement.style.removeProperty('--sonic-visual-vh');
    }
    const focused=document.activeElement?.matches('input,textarea,[contenteditable=true]');
    const keyboard=small&&focused&&h&&h<window.innerHeight*.78;
    document.body.classList.toggle('mobile-keyboard-open',Boolean(keyboard));
  }
  function init() {
    const moreNav=$('mobileMoreNav'),menu=$('mobileMoreMenu');
    moreNav?.addEventListener('click',()=>more(menu?.hidden));
    menu?.querySelectorAll('[data-mobile-go]').forEach(button=>{
      button.addEventListener('click',()=>{more(false);go(button.dataset.mobileGo);});
    });
    document.addEventListener('pointerdown',event=>{
      if(menu&&!menu.hidden&&!menu.contains(event.target)&&!moreNav?.contains(event.target))more(false);
    });
    window.addEventListener('sonic:tab',()=>more(false));
    const form=$('chatForm'),extras=$('chatExtras');
    extras?.addEventListener('click',()=>{
      const open=!form.classList.contains('show-extras');
      form.classList.toggle('show-extras',open);
      extras.setAttribute('aria-expanded',String(open));
    });
    const input=$('message');
    input?.addEventListener('input',()=>{
      // Keep the send button visible as the user types, even on small Safari viewports.
      input.style.height='auto';
      input.style.height=Math.min(115,Math.max(45,input.scrollHeight))+'px';
    });
    window.visualViewport?.addEventListener('resize',adjust);
    window.visualViewport?.addEventListener('scroll',adjust);
    window.addEventListener('resize',adjust);
    document.addEventListener('focusin',adjust);
    document.addEventListener('focusout',()=>requestAnimationFrame(adjust));
    adjust();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();