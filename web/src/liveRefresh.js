import {useEffect,useRef} from 'react';
import {record} from './api';

// One in-flight request, paused in hidden tabs, refreshed immediately on return.
export function useLiveRefresh(callback, scope, enabled=true, delay=8000) {
  const latest=useRef(callback);
  latest.current=callback;
  useEffect(()=>{
    if(!enabled)return;
    let pending=false;
    const abort=new AbortController();
    const tick=async()=>{
      if(pending||document.hidden||abort.signal.aborted)return;
      pending=true;
      try{await latest.current(abort.signal);}catch(e){if(!abort.signal.aborted)record('error','panel/refresh',e.status||'network');}
      finally{pending=false;}
    };
    const timer=setInterval(tick,delay);
    window.addEventListener('focus',tick);
    window.addEventListener('liftcontrol-notifications-changed',tick);
    document.addEventListener('visibilitychange',tick);
    return()=>{abort.abort();clearInterval(timer);window.removeEventListener('focus',tick);window.removeEventListener('liftcontrol-notifications-changed',tick);document.removeEventListener('visibilitychange',tick);};
  },[scope,enabled,delay]);
}
