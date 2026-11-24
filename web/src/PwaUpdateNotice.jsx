import React,{useEffect,useRef,useState} from 'react';
import {version} from '../package.json';
import {PREVIEW,record} from './api.js';
export default function PwaUpdateNotice(){
 const [available,setAvailable]=useState('');
 const dismissed=useRef('');
 useEffect(()=>{
  if(PREVIEW)return;
  let active=true,controller;
  const check=async()=>{
   if(document.visibilityState!=='visible'||controller)return;
   controller=new AbortController();
   try{
    const r=await fetch('/api/health/',{cache:'no-store',credentials:'same-origin',signal:controller.signal});
    if(!r.ok)return;
    const data=await r.json();
    if(!active||!/^\d+\.\d+\.\d+$/.test(data.version))return;
    const a=data.version.split('.').map(Number),b=version.split('.').map(Number);
    const different=a.some((n,i)=>n!==b[i]&&a.slice(0,i).every((v,j)=>v===b[j])&&n>b[i]);
    if(different&&dismissed.current!==data.version){setAvailable(data.version);record('pwa','version','new');}
    else setAvailable('');
   }catch(e){if(active&&e.name!=='AbortError')record('pwa','version','network');}
   finally{controller=null;}
  };
  check();const timer=setInterval(check,60000);
  document.addEventListener('visibilitychange',check);window.addEventListener('online',check);
  return()=>{active=false;clearInterval(timer);controller?.abort();document.removeEventListener('visibilitychange',check);window.removeEventListener('online',check);};
 },[]);
 if(!available)return null;
 return <aside role="status" className="pwa-update-notice"><span>Доступна версия {available}. Сохраните открытые формы перед обновлением.</span><button type="button" onClick={()=>{if(window.confirm('Перезагрузить панель? Несохранённые изменения будут потеряны.'))location.reload();}}>Обновить</button><button type="button" aria-label="Скрыть уведомление" onClick={()=>{dismissed.current=available;setAvailable('');}}>×</button></aside>;
}
