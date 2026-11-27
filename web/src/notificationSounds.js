import {useEffect} from 'react';
import {api,PREVIEW,record} from './api';
export const tones={bell:'Колокольчик',double:'Двойной сигнал',alarm:'Тревожный сигнал',off:'Без звука'};
const defaults={enabled:false,ordinary:'bell',important:'alarm',volume:50};
const key=user=>'liftcontrol-sounds:'+user.id+':'+user.organization_id;
export function soundSettings(user){
 try{const value=JSON.parse(localStorage.getItem(key(user))||'{}');return {enabled:value.enabled===true,ordinary:tones[value.ordinary]?value.ordinary:defaults.ordinary,important:tones[value.important]?value.important:defaults.important,volume:Number.isFinite(value.volume)?Math.max(0,Math.min(100,value.volume)):50};}catch{return {...defaults};}
}
export function saveSounds(user,value){localStorage.setItem(key(user),JSON.stringify(value));window.dispatchEvent(new Event('liftcontrol-sounds'));record('notification','sound-settings',value.enabled?'on':'off');}
let audio;
export async function playTone(tone,volume=50){
 if(tone==='off'||volume===0)return;
 const Audio=window.AudioContext||window.webkitAudioContext;
 if(!Audio)throw new Error('Этот браузер не поддерживает звук приложения.');
 audio??=new Audio();
 await audio.resume();
 if(audio.state!=='running')throw new Error('Нажмите «Прослушать», чтобы разрешить звук в этом окне.');
 const notes=tone==='alarm'?[880,660,880,660]:tone==='double'?[660,880]:[880];
 notes.forEach((frequency,index)=>{
  const oscillator=audio.createOscillator(),gain=audio.createGain(),start=audio.currentTime+index*0.19;
  oscillator.frequency.value=frequency;oscillator.type='sine';
  gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(volume/100*0.15,start+0.015);gain.gain.exponentialRampToValueAtTime(0.001,start+0.17);
  oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(start);oscillator.stop(start+0.18);
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
 });
}
export function useNotificationSounds(user){
 useEffect(()=>{
  if(PREVIEW||!user?.id)return;
  const abort=new AbortController();let cursor=null,busy=false;
  const unlock=()=>{if(soundSettings(user).enabled&&audio?.state==='suspended')audio.resume().catch(()=>{});};
  const reset=()=>{cursor=null;};
  const poll=async()=>{
   const settings=soundSettings(user);
   if(document.hidden||!settings.enabled){cursor=null;return;}
   if(busy)return;busy=true;
   try{
    const value=await api('notifications/sounds/'+(cursor===null?'':'?after='+cursor),{signal:abort.signal});
    if(abort.signal.aborted)return;
    const bootstrap=cursor===null;cursor=value.after;
    if(bootstrap||!value.events?.length||!audio||audio.state!=='running'||document.hidden||!soundSettings(user).enabled)return;
    const announce=async()=>{
     const latest=Math.max(...value.events.map(event=>event.id)),dedup=key(user)+':played';
     if(latest<=Number(localStorage.getItem(dedup)||0))return;
     localStorage.setItem(dedup,String(latest));
     await playTone(value.events.some(event=>event.important)?settings.important:settings.ordinary,settings.volume);
    };
    if(navigator.locks)await navigator.locks.request(key(user),announce);else await announce();
   }catch(error){if(!abort.signal.aborted)record('notification','foreground',error.name||'error');}finally{busy=false;}
  };
  const respond=event=>{if(event.data?.type==='liftcontrol-sound-state'&&event.ports?.[0])event.ports[0].postMessage({active:!document.hidden&&Number(event.data.organization)===user.organization_id&&soundSettings(user).enabled&&audio?.state==='running'});};
  navigator.serviceWorker?.addEventListener('message',respond);
  const activate=()=>{const settings=soundSettings(user);if(settings.enabled&&!audio){const Audio=window.AudioContext||window.webkitAudioContext;if(Audio)audio=new Audio();}unlock();};
  document.addEventListener('pointerdown',activate);document.addEventListener('keydown',activate);
  document.addEventListener('visibilitychange',reset);window.addEventListener('liftcontrol-sounds',reset);
  window.addEventListener('liftcontrol-notifications-changed',poll);
  const timer=setInterval(poll,15000);poll();
  return()=>{abort.abort();navigator.serviceWorker?.removeEventListener('message',respond);clearInterval(timer);window.removeEventListener('liftcontrol-notifications-changed',poll);document.removeEventListener('pointerdown',activate);document.removeEventListener('keydown',activate);document.removeEventListener('visibilitychange',reset);window.removeEventListener('liftcontrol-sounds',reset);};
 },[user?.id,user?.organization_id]);
}
