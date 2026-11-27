import React,{useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,CheckCheck,Clock,RefreshCw,Users,Search,ChevronRight} from 'lucide-react';
import {Dialog} from './components';
import {api,record} from './api';
import MessageReceipt from './MessageReceipt';
import './delivery-details.css';
const state=row=>row.read_at?'read':row.delivered_at?'delivered':'pending';
const labels={read:'Прочитано',delivered:'Доставлено',pending:'Ожидает подтверждения'};
function People({rows,user}){
 const [filter,setFilter]=useState('all'),[query,setQuery]=useState('');
 const date=value=>new Date(value).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'});
 const counts={all:rows.length,read:rows.filter(r=>state(r)==='read').length,delivered:rows.filter(r=>state(r)==='delivered').length,pending:rows.filter(r=>state(r)==='pending').length};
 const visible=rows.filter(r=>(filter==='all'||state(r)===filter)&&r.name.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru')));
 return <><div className="delivery-filters" aria-label="Фильтр получателей">{[['all','Все'],['read','Прочитали'],['delivered','Доставлено'],['pending','Ожидаем']].map(([id,label])=><button key={id} type="button" aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}<span>{counts[id]}</span></button>)}</div>
 {rows.length>8&&<label className="delivery-search"><Search size={17}/><input type="search" aria-label="Найти получателя" placeholder="Найти сотрудника" value={query} onChange={e=>setQuery(e.target.value)}/></label>}
 <ul className="delivery-people">{visible.map(r=><li key={r.id}><span className={'delivery-avatar '+state(r)} aria-hidden="true">{r.name.trim().split(/\s+/).slice(0,2).map(w=>w[0]).join('')}</span><div><b>{r.name}</b><span className={'delivery-status '+state(r)}>{state(r)==='read'?<CheckCheck size={15}/>:state(r)==='delivered'?<Check size={15}/>:<Clock size={15}/>} {labels[state(r)]}</span>{r.delivered_at&&<small>Доставлено {date(r.delivered_at)}</small>}{r.read_at&&<small>Прочитано {date(r.read_at)}</small>}</div></li>)}</ul>
 {!rows.length&&<p className="delivery-empty">Получателей нет. Для старых сообщений подтверждения могли не сохраняться.</p>}{rows.length>0&&!visible.length&&<p className="delivery-empty">Сотрудники не найдены.</p>}</>;
}
export function DeliveryPanel({target,id,user,onClose}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0),[more,setMore]=useState(null);
 useEffect(()=>{
  const abort=new AbortController();let loading=false;
  const load=async()=>{if(loading)return;loading=true;setBusy(true);try{const result=await api(`notifications/receipts/details/?target=${target}&id=${id}${more?'&before='+more:''}`,{signal:abort.signal,organization:user.organization_id});if(!abort.signal.aborted){setData(old=>more?{...result,events:[...(old?.events||[]),...result.events]}:result);setError('');}}catch(e){if(!abort.signal.aborted){setError(e.message||'Не удалось получить подтверждения.');record('receipts','details',e.status||'error');}}finally{loading=false;if(!abort.signal.aborted)setBusy(false);}};
  load();return()=>abort.abort();
 },[target,id,user.organization_id,revision,more]);
 return createPortal(<div className="delivery-dialog"><Dialog title="Доставка и прочтение" onClose={onClose}>
  <div className="delivery-heading"><span className="delivery-heading-icon"><Users size={23}/></span><div><b>Кто получил сообщение</b><p>Подтверждения от устройств и сотрудников</p></div><button className="icon-button" type="button" aria-label="Обновить подтверждения" disabled={busy} onClick={()=>(setMore(null),setRevision(v=>v+1))}><RefreshCw size={18}/></button></div>
  <p className="delivery-explainer">Доставлено — устройство подтвердило получение. Прочитано — сотрудник открыл сообщение. Принятие заявки в работу отображается отдельно.</p>
  {error&&<p className="error" role="alert">{error}<button type="button" onClick={()=>(setMore(null),setRevision(v=>v+1))}>Повторить</button></p>}{busy&&!data&&<p role="status">Загружаем подтверждения…</p>}
  {data?.accepted_at&&<p className="delivery-accepted"><CheckCheck size={18}/>Принял в работу: {data.accepted_by} · {new Date(data.accepted_at).toLocaleString('ru-RU',{timeZone:user.timezone})}</p>}
  {data?.events.map((event,index)=>{const content=<><div className="delivery-event-text">{event.body&&<p>{event.body}</p>}<small>{new Date(event.created_at).toLocaleString('ru-RU',{timeZone:user.timezone})}</small></div><People rows={event.recipients} user={user}/></>;return <details className="delivery-event" key={event.id} open={data.events.length===1||undefined}><summary><ChevronRight size={16}/><b>{event.title}</b><span>{event.recipients.filter(r=>r.read_at).length}/{event.recipients.length} прочитали</span></summary>{event.target?<MessageReceipt user={user} target={event.target} id={event.event_id} own={false}>{content}</MessageReceipt>:content}</details>;})}
  {data&&!data.events.length&&<p className="delivery-empty">Отправленных уведомлений пока нет.</p>}{data?.next&&<button type="button" disabled={busy} onClick={()=>setMore(data.next)}>Более ранние события</button>}
 </Dialog></div>,document.body);
}
export default function DeliveryDetails({target,id,user,label='Доставка и прочтение'}){
 const [open,setOpen]=useState(false);
 return <><button type="button" className="delivery-trigger" onClick={()=>setOpen(true)}><CheckCheck size={16}/>{label}<ChevronRight size={14}/></button>{open&&<DeliveryPanel key={user.organization_id+':'+target+':'+id} target={target} id={id} user={user} onClose={()=>setOpen(false)}/>}</>;
}
