import {PREVIEW,record} from './api.js';
let installPrompt=null;
let started=false;
let workerStatus='pending';
const listeners=new Set();
const notify=()=>listeners.forEach(fn=>fn());
export const subscribePwa=fn=>{listeners.add(fn);return()=>listeners.delete(fn);};
export const pwaState=()=>({canInstall:!!installPrompt,workerStatus,standalone:window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true});
export function startPwa(){
 if(PREVIEW||started)return;
 started=true;
 window.addEventListener('beforeinstallprompt',event=>{
  event.preventDefault();installPrompt=event;record('pwa','install','available');notify();
 });
 window.addEventListener('appinstalled',()=>{installPrompt=null;record('pwa','install','installed');notify();});
 window.addEventListener('online',()=>{record('pwa','connection','online');notify();});
 window.addEventListener('offline',()=>{record('pwa','connection','offline');notify();});
 if(!window.isSecureContext||!('serviceWorker' in navigator)){
  workerStatus='unsupported';record('pwa','worker','unsupported');notify();return;
 }
 navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'}).then(()=>{
  workerStatus='registered';record('pwa','worker','registered');notify();
 }).catch(()=>{workerStatus='error';record('pwa','worker','error');notify();});
}
export async function installPwa(){
 const prompt=installPrompt;
 if(!prompt)return;
 installPrompt=null;notify();
 try{await prompt.prompt();const choice=await prompt.userChoice;record('pwa','install',choice.outcome==='accepted'?'accepted':'dismissed');}
 catch{record('pwa','install','error');}
}
