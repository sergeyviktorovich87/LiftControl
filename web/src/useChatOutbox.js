import {useCallback,useEffect,useState} from 'react';
import {api} from './api';

// Retain unsent files only in this open panel. Never cache work photos on a shared device.
export default function useChatOutbox(user,commissioning=false) {
  const [entries,setEntries]=useState([]);
  const [revision,setRevision]=useState(0);
  const scope=user && (commissioning?'commissioning:':'')+user.id+':'+user.organization_id;
  const first=entries.find(entry=>entry.scope===scope);
  const add=useCallback((payload,files)=>{
    const bytes=crypto.getRandomValues(new Uint8Array(16));
    bytes[6]=(bytes[6] & 15) | 64;
    bytes[8]=(bytes[8] & 63) | 128;
    const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
    const key=[hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
    setEntries(list=>[...list,{scope,key,payload,files,status:'waiting'}]);
  },[scope]);
  const remove=key=>setEntries(list=>list.filter(entry=>entry.key!==key));
  const retry=key=>setEntries(list=>list.map(entry=>entry.key===key?{...entry,status:'waiting'}:entry));
  useEffect(()=>{
    if(!first||first.status==='error'||commissioning&&!user?.can_commissioning)return;
    const controller=new AbortController();
    let running=false;
    let timer;
    function update(status,error=''){
      setEntries(list=>list.map(entry=>entry.key===first.key&&entry.status!==status?{...entry,status,error}:entry));
    }
    async function transmit(){
      if(running||controller.signal.aborted||!navigator.onLine)return;
      running=true;
      update('sending');
      try{
        let body={...first.payload,...(commissioning?{operation_id:first.key}:{client_id:first.key}),expected_sender:user.id};
        if(first.files.length){
          const form=new FormData();
          for(const [name,value] of Object.entries(body))form.append(name,value);
          for(const file of first.files)form.append(commissioning?'photos':'files',file);
          body=form;
        }
        await api(commissioning?'commissioning/chat/':'chat/',{method:'POST',body,organization:user.organization_id,signal:controller.signal});
        if(controller.signal.aborted)return;
        remove(first.key);
        setRevision(n=>n+1);
      }catch(error){
        if(controller.signal.aborted)return;
        if(error.status && error.status<500 && error.status!==429){
          update('error',error.message);
        }else{
          update('waiting');
          timer=setTimeout(transmit,error.status===429?60000:8000);
        }
      }finally{running=false;}
    }
    transmit();
    window.addEventListener('online',transmit);
    return ()=>{
      clearTimeout(timer);
      controller.abort();
      window.removeEventListener('online',transmit);
    };
  },[first?.key,first?.status==='error',scope,commissioning,user?.can_commissioning]);
  useEffect(()=>{
    if(!entries.length)return;
    const warn=event=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',warn);
    return ()=>window.removeEventListener('beforeunload',warn);
  },[entries.length]);
  return {entries:entries.filter(entry=>entry.scope===scope),add,remove,retry,revision};
}
