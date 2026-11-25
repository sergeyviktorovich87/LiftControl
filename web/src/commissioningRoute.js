import {useEffect,useState} from 'react';
const tabs=new Set(['lifts','work','expenses','nameplates','history']);
export function commissioningRoute(){
 const parts=location.hash.slice(1).split('/');let project=null,lift=null,tab='lifts',action=null;
 for(let i=1;i<parts.length;i+=2){const [key,value]=[parts[i],parts[i+1]];
  if(key==='project'&&Number.isSafeInteger(Number(value))&&Number(value)>0)project=Number(value);
  if(key==='lift'&&Number.isSafeInteger(Number(value))&&Number(value)>0)lift=Number(value);
  if(key==='tab'&&tabs.has(value))tab=value;
  if(key==='action')action=value;
 }
 return {project,lift,tab,action};
}
export function useCommissioningRoute(){
 const [route,setRoute]=useState(commissioningRoute);
 useEffect(()=>{const update=()=>setRoute(commissioningRoute());window.addEventListener('hashchange',update);window.addEventListener('popstate',update);return()=>{window.removeEventListener('hashchange',update);window.removeEventListener('popstate',update);};},[]);
 const go=(path='',replace=false)=>{history[replace?'replaceState':'pushState']({commissioning:true},'','#commissioning'+path);setRoute(commissioningRoute());};
 const close=fallback=>{if(history.state?.commissioning)history.back();else go(fallback,true);};
 return [route,go,close];
}
