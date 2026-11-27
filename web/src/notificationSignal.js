import {useEffect} from 'react';
import {api,PREVIEW,record} from './api';

// Content-free signal, with one request at a time and no background polling.
export function useNotificationSignal(user){
 useEffect(()=>{
  if(PREVIEW||!user?.notification_live_api)return;
  let stopped=false,timer,active=null,cursor=null,failures=0;
  const scope=user.id+':'+user.organization_id;
  const announce=()=>window.dispatchEvent(new CustomEvent('liftcontrol-notifications-changed',{detail:{scope}}));
  const tick=async()=>{
   clearTimeout(timer);
   if(stopped||document.hidden||active)return;
   const request=new AbortController();active=request;
   const timeout=setTimeout(()=>request.abort(),8000);
   try{
    const result=await api('notifications/revision/',{signal:request.signal});
    if(stopped||request.signal.aborted)return;
    if(cursor!==null&&cursor!==result.revision)announce();
    cursor=result.revision;failures=0;
   }catch(error){if(!stopped){failures=Math.min(failures+1,4);record('notification','live-signal',error.status||error.name);}}
   finally{
    clearTimeout(timeout);active=null;
    if(!stopped&&!document.hidden)timer=setTimeout(tick,Math.min(30000,2000*2**failures));
   }
  };
  const resume=()=>{
   clearTimeout(timer);
   if(document.hidden){active?.abort();return;}
   // Refresh even without a new inbox row: assignments can change while away.
   announce();tick();
  };
  tick();
  document.addEventListener('visibilitychange',resume);
  window.addEventListener('online',resume);
  window.addEventListener('focus',resume);
  return()=>{stopped=true;clearTimeout(timer);active?.abort();document.removeEventListener('visibilitychange',resume);window.removeEventListener('online',resume);window.removeEventListener('focus',resume);};
 },[user?.id,user?.organization_id,user?.notification_live_api]);
}
