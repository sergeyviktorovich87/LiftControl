import {useEffect} from 'react';
import {api,PREVIEW,record} from './api';
export function decodeVapidKey(value){const raw=atob((value+'='.repeat((4-value.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(raw,c=>c.charCodeAt(0));}
const pref=user=>'liftcontrol-push-enabled:'+user.id;
export function preferPush(user,enabled){try{localStorage.setItem(pref(user),enabled?'1':'0');}catch{}}
export async function syncPush(user,{signal,force=false}={}){
 if(!user||PREVIEW||!window.isSecureContext||!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window)||Notification.permission!=='granted')return false;
 let preference;try{preference=localStorage.getItem(pref(user));}catch{}
 if(preference==='0'&&!force)return false;
 const config=await api('push/public-key/',{signal,organization:user.organization_id});if(!config.enabled||!config.public_key)return false;
 const registration=await navigator.serviceWorker.getRegistration('/');if(!registration)return false;
 let sub=await registration.pushManager.getSubscription();const expected=decodeVapidKey(config.public_key);
 if(sub){const key=sub.options?.applicationServerKey;const mismatched=key&&String(new Uint8Array(key))!==String(expected);if(mismatched||sub.expirationTime&&sub.expirationTime<=Date.now()){await sub.unsubscribe();sub=null;force=true;}}
 // Never re-enable a deliberate opt-out or ask for permission in background.
 if(!sub&&(force||preference==='1'))sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:expected});
 if(!sub||signal?.aborted)return false;
 await api('push/subscription/',{method:'POST',signal,organization:user.organization_id,body:{...sub.toJSON(),expected_user:user.id}});preferPush(user,true);record('push','subscription','synced');return true;
}
export function usePushSubscription(user){
 useEffect(()=>{
  if(!user)return;const abort=new AbortController();let active=false;
  const sync=async()=>{if(active||abort.signal.aborted||document.hidden)return;active=true;try{await syncPush(user,{signal:abort.signal});}catch(e){if(!abort.signal.aborted)record('push','subscription',e.status||e.name||'error');}finally{active=false;}};
  sync();const timer=setInterval(sync,60000);window.addEventListener('online',sync);window.addEventListener('focus',sync);document.addEventListener('visibilitychange',sync);navigator.serviceWorker?.addEventListener('controllerchange',sync);
  return()=>{abort.abort();clearInterval(timer);window.removeEventListener('online',sync);window.removeEventListener('focus',sync);document.removeEventListener('visibilitychange',sync);navigator.serviceWorker?.removeEventListener('controllerchange',sync);};
 },[user?.id,user?.organization_id]);
}
