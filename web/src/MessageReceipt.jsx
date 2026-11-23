import React,{useEffect,useRef} from 'react';
import {api,PREVIEW} from './api';

export function receiptLabel(receipt){
  if(!receipt)return '';
  if(!receipt.total)return '✓ Отправлено';
  if(receipt.read)return `✓✓ Прочитали ${receipt.read} из ${receipt.total}`;
  if(receipt.delivered)return `✓✓ Доставлено ${receipt.delivered} из ${receipt.total}`;
  return '✓ Отправлено · ожидает доставки';
}

export default function MessageReceipt({user,target,id,own,receipt,children}){
  const node=useRef(null);
  useEffect(()=>{
    if(PREVIEW||own||!user.message_receipts_api)return;
    let visible=false,pending=false,done=false;
    const abort=new AbortController();
    const mark=async()=>{
      if(done||pending||!visible||document.hidden||!document.hasFocus())return;
      pending=true;
      try{await api('notifications/receipts/',{method:'POST',signal:abort.signal,body:{target,ids:[id],read:true}});done=true;}
      catch{}finally{pending=false;}
    };
    const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;mark();});
    observer.observe(node.current);
    const timer=setInterval(mark,1500);
    window.addEventListener('focus',mark);
    document.addEventListener('visibilitychange',mark);
    return()=>{abort.abort();observer.disconnect();clearInterval(timer);window.removeEventListener('focus',mark);document.removeEventListener('visibilitychange',mark);};
  },[id,target,own,user.id,user.organization_id,user.message_receipts_api]);
  return <div ref={node}>{children}{own&&receipt&&<small className={'message-receipt '+(receipt.read?'read':'')}>{receiptLabel(receipt)}</small>}</div>;
}
