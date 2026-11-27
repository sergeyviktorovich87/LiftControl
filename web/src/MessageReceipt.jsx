import React,{useEffect,useRef} from 'react';
import {api,PREVIEW} from './api';
import DeliveryDetails from './DeliveryDetails';

export function receiptLabel(receipt){
  if(!receipt)return '';
  if(!receipt.total)return '✓ Отправлено';
  if(receipt.read)return `✓✓ Прочитали ${receipt.read} из ${receipt.total}`;
  if(receipt.delivered)return `✓✓ Доставлено ${receipt.delivered} из ${receipt.total}`;
  return '✓ Отправлено · ожидает доставки';
}

export default function MessageReceipt({user,target,id,ids,own,receipt,children,as:Tag='div',...props}){
  const node=useRef(null);
  const idsKey=JSON.stringify(ids||[id]);
  useEffect(()=>{
    if(PREVIEW||own||!user?.message_receipts_api||!JSON.parse(idsKey).length)return;
    let visible=false,pending=false,done=false;
    const abort=new AbortController();
    const mark=async()=>{
      if(done||pending||!visible||document.hidden||!document.hasFocus())return;
      pending=true;
      try{await api('notifications/receipts/',{method:'POST',organization:user.organization_id,signal:abort.signal,body:{target,ids:JSON.parse(idsKey),read:true}});done=true;}
      catch{}finally{pending=false;}
    };
    const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;mark();});
    observer.observe(node.current);
    const timer=setInterval(mark,1500);
    window.addEventListener('focus',mark);
    document.addEventListener('visibilitychange',mark);
    return()=>{abort.abort();observer.disconnect();clearInterval(timer);window.removeEventListener('focus',mark);document.removeEventListener('visibilitychange',mark);};
  },[idsKey,target,own,user?.id,user?.organization_id,user?.message_receipts_api]);
  return <Tag ref={node} {...props}>{children}{own&&user.message_receipts_api&&<small className={'message-receipt '+(receipt?.read?'read':'')}><DeliveryDetails target={target} id={id} user={user} label={receiptLabel(receipt)||'✓ Отправлено'}/></small>}</Tag>;
}
