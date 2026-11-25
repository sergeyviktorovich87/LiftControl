import {useEffect,useState} from 'react';
export const dayDate=value=>new Date(value+'T12:00:00Z');
export const addDay=(value,n)=>new Date(+dayDate(value)+n*86400000).toISOString().slice(0,10);
export const dayLabel=(value,options={day:'numeric',month:'long'})=>dayDate(value).toLocaleDateString('ru-RU',{...options,timeZone:'UTC'});
export function bounds(value){const from=value.slice(0,7)+'-01',d=dayDate(from);d.setUTCMonth(d.getUTCMonth()+1,0);return [from,d.toISOString().slice(0,10)];}
export function usePlanningHash(){const [hash,setHash]=useState(location.hash);useEffect(()=>{const update=()=>setHash(location.hash);window.addEventListener('hashchange',update);window.addEventListener('popstate',update);return()=>{window.removeEventListener('hashchange',update);window.removeEventListener('popstate',update);};},[]);return hash;}
export const vacationLabels={DRAFT:'Черновик',PENDING:'На согласовании',APPROVED:'Согласован',REJECTED:'Отклонён',CHANGES:'Предложены даты',CANCELLED:'Отменён'};
