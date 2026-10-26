/* SONIC Command Deck interface only. Never controls tools, voice sessions, or files. */
(()=>{
  'use strict';
  const subtitles={
    'Neural Brain':'A living map of your connected knowledge.',
    'Chat':'Your intelligence, in one conversation.',
    'Command Center':'Your intelligence, in one conversation.',
    'Workspace':'Files, notes and authorized device storage.',
    'Memory Vault':'What you choose to remember, always inspectable.',
    'Devices':'Connected hardware and approved operations.',
    'Device Hub':'Connected hardware and approved operations.',
    'SONIC Setup':'System readiness, voice and personalized settings.',
    'Setup':'System readiness, voice and personalized settings.'
  };
  function initialize(){
    const title=document.getElementById('pageTitle');
    const subtitle=document.getElementById('pageSubtitle');
    if(title&&subtitle){
      const update=()=>{
        subtitle.textContent=subtitles[title.textContent?.trim()]||
          'Your private intelligence workspace.';
        document.title='SONIC | '+(title.textContent?.trim()||'Intelligence Console');
      };
      update();
      // The application owns route changes; this observes the existing heading
      // rather than shadowing route state or replacing core navigation handlers.
      new MutationObserver(update).observe(title,{childList:true,characterData:true,subtree:true});
    }
    const shortcuts=[
      ['goToWorkspace','workspace'],
      ['goToDevices','devices']
    ];
    for(const [id,tab] of shortcuts){
      const trigger=document.getElementById(id);
      trigger?.addEventListener('click',()=>{
        document.querySelector('.nav[data-tab="'+tab+'"]')?.click();
      });
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initialize,{once:true});
  else initialize();
})();
