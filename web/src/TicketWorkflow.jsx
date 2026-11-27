import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ArrowLeft,MoreHorizontal,Camera,Clock,TriangleAlert,Send,Paperclip,CheckCircle2,Play,Plus,MessageSquare} from 'lucide-react';
import TicketCreate from './TicketCreate';
import TicketAction from './TicketAction';
import MessageReceipt from './MessageReceipt';
import {Badge,Dialog} from './components';
import {entranceLabel} from './LiftDocuments';
import {api,record} from './api';
import {prepareImages} from './imageCompression';
import {MAX_FILE_BYTES} from './uploadLimits';
import './ticket-detail.css';
const eventNames={type_changed:'Тип заявки изменён',created:'Заявка создана',lift_identified:'Уточнён лифт',escalated:'Приоритет повышен до застревания',entrapment_acknowledged:'Дежурный подтвердил застревание',accepted:'Принята в работу',completed:'Выполнена',canceled:'Отменена',reassigned:'Исполнитель изменён',stopped:'Лифт остановлен',resumed:'Ремонт продолжен',long_repair:'Длительный ремонт',corrected:'Сведения уточнены'};
const priorityNames={NORMAL:'Ремонт',HIGH:'Высокий',LOW:'Низкий',EMERGENCY:'Аварийный',ENTRAPMENT:'Застревание'};
const openStates=new Set(['NEW','IN_PROGRESS','STOPPED','LONG_REPAIR']);
export default function TicketWorkflow(props){return props.item?.id?<TicketDetail {...props}/>:<TicketCreate {...props}/>;}
function TicketDetail({item,data,user,onClose,onSaved,onOpenLift,onDiscuss}){
 const [ticket,setTicket]=useState(item),[history,setHistory]=useState({events:[],comments:[]}),[media,setMedia]=useState({results:[],count:0,next:null});
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[info,setInfo]=useState(''),[mediaError,setMediaError]=useState(''),[action,setAction]=useState(null),[menu,setMenu]=useState(false),[note,setNote]=useState(''),[files,setFiles]=useState([]);
 const [values,setValues]=useState({repair:'',reason:'',stopReason:'',delayReason:'',expectedDate:'',assigned:item.assigned_to||'',assignReason:'',elevator:'',priority:item.priority||'NORMAL',typeReason:'',peopleReleased:false});
 const working=useRef(false),uploads=useRef(new Map()),sequence=useRef(0),mounted=useRef(true);
 const request=useCallback((path,options={})=>api(path,{...options,organization:user.organization_id}),[user.organization_id]);
 const date=value=>value?new Date(value).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'}):'—';
 const set=(key,value)=>setValues(old=>({...old,[key]:value}));
 const loadMedia=useCallback(async(signal,more=false,offset=null)=>{
  try{const result=await request(`media/?ticket=${item.id}${more?'&offset='+offset:''}`,{signal});if(!mounted.current||signal?.aborted)return;setMedia(old=>({...result,results:more?[...new Map([...old.results,...(result.results||[])].map(row=>[String(row.id),row])).values()]:(result.results||[]),count:result.count||0,next:result.next??null}));setMediaError('');}catch(e){if(!signal?.aborted&&mounted.current)setMediaError('Не удалось загрузить медиатеку. '+e.message);}
 },[request,item.id]);
 const refresh=useCallback(async signal=>{
  const id=++sequence.current;
  const [row,log]=await Promise.all([request(`tickets/${item.id}/`,{signal}),request(`tickets/${item.id}/history/`,{signal})]);
  if(!mounted.current||signal?.aborted||id!==sequence.current)return;
  setTicket(row);setHistory({events:log.events||[],comments:log.comments||[]});
  if(user.message_receipts_api){request('notifications/receipts/',{method:'POST',signal,body:{target:'ticket',ids:[item.id]}}).catch(()=>{});if(log.comments?.length)request('notifications/receipts/',{method:'POST',signal,body:{target:'ticket_comment',ids:log.comments.slice(-200).map(c=>c.id)}}).catch(()=>{});}
 },[request,item.id,user.message_receipts_api]);
 useEffect(()=>{mounted.current=true;const abort=new AbortController();refresh(abort.signal).catch(e=>{if(!abort.signal.aborted)setError(e.message);});loadMedia(abort.signal);const timer=setInterval(()=>{if(!document.hidden&&!working.current){refresh(abort.signal).catch(()=>{});loadMedia(abort.signal);}},10000);return()=>{mounted.current=false;abort.abort();clearInterval(timer);};},[refresh,loadMedia]);
 const canComment=openStates.has(ticket.status)&&(user.can_manage||user.on_duty||ticket.can_complete);
 const canUpload=!!(user.can_manage||ticket.can_complete||(ticket.status==='NEW'&&ticket.created_by===user.id&&user.can_create_ticket));
 const permissions={type:ticket.can_change_type,result:ticket.can_complete,attachments:canUpload,stop:ticket.can_stop,delay:ticket.can_complete,assign:ticket.can_assign??(ticket.status==='NEW'&&(user.can_manage||user.on_duty)),cancel:ticket.can_cancel,identify:ticket.can_identify_lift};
 useEffect(()=>{if(action&&!permissions[action])setAction(null);},[ticket,action]);
 const close=()=>{if(!working.current)onClose();};
 const openAction=kind=>{if(working.current||!permissions[kind])return;setMenu(false);setError('');if(kind==='type')setValues(old=>({...old,priority:ticket.priority,typeReason:'',peopleReleased:false}));setAction(kind);};
 const run=async(fn,{closeAction=false}={})=>{
  if(working.current)return;working.current=true;setBusy(true);setError('');setInfo('');
  try{const message=await fn();await refresh();await loadMedia();await onSaved();if(closeAction)setAction(null);if(message)setInfo(message);record('ticket_action',action||'transition','ok');}
  catch(e){record('ticket_action',action||'transition',e.status||'error');setError(e.message||'Не удалось сохранить. Введённые данные остались в форме.');await refresh().catch(()=>{});await loadMedia();}
  finally{working.current=false;if(mounted.current)setBusy(false);}
 };
 const addFiles=async selected=>{
  if(working.current)return;if(files.length+selected.length>8||selected.some(f=>f.size>MAX_FILE_BYTES)){setError('До 8 вложений за раз, по 100 МБ.');return;}
  working.current=true;setBusy(true);try{const prepared=await prepareImages(selected);setFiles(old=>[...old,...prepared]);setError('');}catch(e){setError(e.message);}finally{working.current=false;setBusy(false);}
 };
 const uploadFiles=async category=>{
  for(const file of files){let saved=uploads.current.get(file);if(!saved){saved={id:crypto.randomUUID(),done:false};uploads.current.set(file,saved);}if(!saved.done){const body=new FormData();body.append('kind','ticket');body.append('target_id',ticket.id);body.append('category',category);body.append('upload_id',saved.id);body.append('file',file);await request('media/uploads/',{method:'POST',body});saved.done=true;}setFiles(old=>old.filter(f=>f!==file));}
 };
 const saveAction=()=>run(async()=>{
  const path=`tickets/${ticket.id}/`;
  if(action==='result'){await uploadFiles('RESULT');await request(path+'complete/',{method:'POST',body:{work_description:values.repair.trim()}});set('repair','');return 'Работы сохранены, заявка выполнена.';}
  if(action==='attachments'){await uploadFiles('OTHER');return 'Вложения сохранены.';}
  const operations={type:['change-type/',{priority:values.priority,reason:values.typeReason.trim(),people_released:values.peopleReleased},'Тип заявки изменён. История сохранена.'],stop:['stop/',{reason:values.stopReason.trim()},'Остановка сохранена. Заявка остаётся открытой.'],delay:['long-repair/',{reason:values.delayReason.trim(),expected_date:values.expectedDate||null},'Длительный ремонт сохранён.'],assign:['assign/',{assigned_to:Number(values.assigned),reason:values.assignReason.trim()},'Исполнитель изменён с записью причины.'],cancel:['cancel/',{reason:values.reason.trim()},'Заявка отменена. Причина сохранена.'],identify:['identify-lift/',{elevator:Number(values.elevator)},'Лифт уточнён. История заявки сохранена.']};
  const [route,body,message]=operations[action];await request(path+route,{method:'POST',body});return message;
 },{closeAction:true});
 const sendComment=()=>{if(!note.trim())return;run(async()=>{await request(`tickets/${ticket.id}/comment/`,{method:'POST',body:{body:note.trim()}});setNote('');return 'Комментарий сохранён.';});};
 const transition=async route=>run(async()=>{await request(`tickets/${ticket.id}/${route}/`,{method:'POST'});return route==='accept'?'Заявка принята вами в работу.':route==='resume'?'Ремонт продолжен.':'Застревание подтверждено.';});
 const primary=ticket.can_acknowledge_entrapment&&!ticket.entrapment_acknowledged?['Подтвердить застревание',()=>transition('acknowledge-entrapment')]:ticket.can_accept?['Принять заявку',()=>transition('accept')]:ticket.can_resume?['Продолжить ремонт',()=>transition('resume')]:ticket.can_complete?['Добавить результат',()=>openAction('result')]:null;
 const lift=data.elevators.find(l=>l.id===ticket.elevator),location=[lift?entranceLabel(lift):ticket.entrance_hint?'Подъезд '+ticket.entrance_hint:null,ticket.elevator?'Зав. № '+(ticket.elevator_factory_number||ticket.elevator_label||ticket.elevator):'Лифт не уточнён',ticket.floor_hint?'Этаж '+ticket.floor_hint:null].filter(Boolean).join(' · ');
 const assets=new Set(media.results.map(m=>String(m.id))),legacy=(ticket.photos||[]).filter(p=>!p.asset_id||!assets.has(String(p.asset_id))),gallery=[...media.results,...legacy.map(p=>({id:'legacy-'+p.id,url:p.url,preview_url:p.url,content_type:'image/jpeg',name:'Фото заявки '+p.id}))];
 const timeline=[...history.events.filter(e=>!['commented','photo_added'].includes(e.action)).map(e=>({...e,key:'event-'+e.id,type:'event'})),...history.comments.map(c=>({...c,key:'comment-'+c.id,type:'comment'}))].sort((a,b)=>+new Date(b.created_at)-+new Date(a.created_at)||b.key.localeCompare(a.key));
 const secondary=<>{permissions.type&&<button disabled={busy} onClick={()=>openAction('type')}>Изменить тип заявки</button>}{permissions.stop&&<button disabled={busy} onClick={()=>openAction('stop')}><TriangleAlert size={16}/>Лифт остановлен</button>}{permissions.delay&&<button disabled={busy} onClick={()=>openAction('delay')}><Clock size={16}/>Длительный ремонт</button>}{ticket.can_resume&&permissions.result&&<button disabled={busy} onClick={()=>openAction('result')}>Добавить результат</button>}</>;
 return <>
 <div className="ticket-detail-page"><Dialog wide title={'Заявка #'+ticket.id} onClose={close}>
  <div className="ticket-detail-workspace">
   <header className="ticket-detail-heading"><div><button className="ticket-detail-back" onClick={close}><ArrowLeft size={16}/>К заявкам</button><h1>{ticket.address||'Адрес не указан'}</h1><p>{location}</p><p className="ticket-mobile-assignee">{ticket.technician_name||data.technicians.find(t=>t.id===ticket.assigned_to)?.full_name||'Исполнитель не назначен'}{ticket.accepted_at&&' · принял '+date(ticket.accepted_at)}</p><div className="ticket-location-actions">{ticket.elevator&&<button onClick={()=>onOpenLift?.(ticket.elevator)}>Открыть карточку лифта</button>}{permissions.identify&&<button onClick={()=>openAction('identify')}>Уточнить лифт</button>}</div></div><div className="ticket-status-actions"><Badge value={ticket.status}/><span className={'ticket-priority '+(ticket.priority==='ENTRAPMENT'?'is-urgent':'')}>{priorityNames[ticket.priority]||ticket.priority}</span><button className="icon-button" aria-label="Действия заявки" aria-expanded={menu} onClick={()=>setMenu(v=>!v)}><MoreHorizontal size={22}/></button></div></header>
   {ticket.priority==='ENTRAPMENT'&&openStates.has(ticket.status)&&<p className="ticket-alert"><TriangleAlert size={18}/>{ticket.entrapment_acknowledged?'Застревание подтверждено дежурным.':'Застревание — люди в кабине.'}</p>}
   {info&&<p className="ticket-detail-notice" role="status">{info}</p>}{error&&!action&&<p role="alert" className="error">{error}</p>}
   <div className="ticket-detail-columns"><div className="ticket-detail-main">
    <section className="ticket-detail-section"><h2>{ticket.title}</h2><p className="ticket-description">{ticket.description||'Описание не указано.'}</p><small>Создана {date(ticket.created_at)} · {ticket.created_by_name||'Ранее созданная заявка'}</small>
     {ticket.delivery&&<MessageReceipt user={user} target="ticket" id={ticket.id} own={false}><p className="ticket-delivery">{{pending:'Ожидает подтверждения доставки',no_recipient:'Исполнитель не назначен',received:'✓✓ Доставлено на устройство',read:'✓✓ Прочитано механиком',unconfirmed:'Нет подтверждения доставки'}[ticket.delivery.state]}{(ticket.delivery.read_at||ticket.delivery.received_at)&&' · '+date(ticket.delivery.read_at||ticket.delivery.received_at)}</p></MessageReceipt>}
     {(ticket.contact_name||ticket.contact_phone)&&<details className="ticket-contact"><summary>Контакт заявителя</summary><p>{ticket.contact_name} {ticket.contact_phone}</p></details>}
    </section>
    {ticket.repair&&<section className="ticket-detail-section ticket-result"><h2><CheckCircle2 size={19}/>Выполненные работы</h2><p className="ticket-description">{ticket.repair}</p><small>{date(ticket.completed_at)}</small></section>}
    {ticket.stopped_at&&<section className="ticket-detail-section ticket-stopped"><h2>{ticket.status==='DONE'?'Остановка в истории':'Лифт остановлен'}</h2><p className="ticket-description">{ticket.stop_reason}</p><small>{date(ticket.stopped_at)}</small></section>}
    {ticket.status==='LONG_REPAIR'&&<section className="ticket-detail-section"><h2>Длительный ремонт</h2><p className="ticket-description">{ticket.long_repair_reason}</p>{ticket.expected_repair_date&&<small>Ожидаемая дата: {ticket.expected_repair_date.split('-').reverse().join('.')}</small>}</section>}
    {ticket.cancellation_reason&&<section className="ticket-detail-section"><h2>Причина отмены</h2><p className="ticket-description">{ticket.cancellation_reason}</p></section>}
    <section className="ticket-detail-section"><header className="ticket-section-heading"><h2>Фото и видео · {Math.max(media.count,gallery.length)}</h2>{canUpload&&<button disabled={busy} onClick={()=>openAction('attachments')}><Camera size={16}/>Добавить фото</button>}</header>
     <div className="ticket-gallery">{gallery.map(asset=><a key={asset.id} href={asset.url} target="_blank" rel="noreferrer" title={asset.name}>{asset.preview_url||asset.content_type?.startsWith('image/')?<img src={asset.preview_url||asset.url} alt={asset.name||'Фото заявки'} loading="lazy"/>:<Play size={30}/ >}{asset.content_type?.startsWith('video/')&&<span className="ticket-play"><Play size={18}/></span>}</a>)}</div>{!gallery.length&&!mediaError&&<p className="ticket-empty">Вложений пока нет.</p>}{mediaError&&<p className="ticket-empty">{mediaError}<button onClick={()=>loadMedia()}>Повторить загрузку</button></p>}{media.next!==null&&<button onClick={()=>loadMedia(undefined,true,media.next)}>Показать ещё</button>}
    </section>
    <section className="ticket-detail-section"><h2>История заявки</h2><div className="ticket-timeline">{timeline.map(row=><article className={'ticket-timeline-row '+(row.type==='comment'?'is-comment':'')} key={row.key}><time dateTime={row.created_at}>{date(row.created_at)}</time><span className="ticket-timeline-dot"/><div>{row.type==='comment'?<MessageReceipt user={user} target="ticket_comment" id={row.id} own={row.author_id===user.id} receipt={row.receipt}><b>{row.kind==='RESULT'?'Результат ремонта · ':''}{row.author}</b><p>{row.body}</p></MessageReceipt>:<><b>{eventNames[row.action]||row.action}</b><small>{row.actor||'Система'}</small>{row.action==='type_changed'&&<p>{priorityNames[row.before]||row.before} → {priorityNames[row.after]||row.after}</p>}{row.reason&&<p>{row.reason}</p>}</>}</div></article>)}</div>{!timeline.length&&<p className="ticket-empty">Записей пока нет.</p>}
     {canComment&&<form className="ticket-comment" onSubmit={e=>{e.preventDefault();sendComment();}}>{canUpload&&<button type="button" aria-label="Прикрепить к заявке" disabled={busy} onClick={()=>openAction('attachments')}><Paperclip size={18}/></button>}<textarea aria-label="Добавить комментарий" placeholder="Добавить комментарий…" maxLength={4000} rows={2} value={note} disabled={busy} onChange={e=>setNote(e.target.value)}/><button aria-label="Отправить комментарий" disabled={busy||!note.trim()}><Send size={18}/></button></form>}
    </section>
   </div><aside className="ticket-detail-aside"><section className="ticket-detail-section"><h2>Исполнитель</h2><div className="ticket-assignee"><span className="avatar">{(ticket.technician_name||'—').split(' ').slice(0,2).map(w=>w[0]).join('')}</span><div><b>{ticket.technician_name||data.technicians.find(t=>t.id===ticket.assigned_to)?.full_name||'Не назначен'}</b><small>{ticket.accepted_at?'Принял '+date(ticket.accepted_at):'Ожидает принятия'}</small></div></div>{onDiscuss&&<button onClick={onDiscuss}><MessageSquare size={17}/>Обсудить в чате</button>}</section>
    <section className="ticket-detail-section ticket-detail-next"><h2>{primary?'Следующее действие':openStates.has(ticket.status)?'Ход заявки':'Заявка закрыта'}</h2><p>{ticket.can_complete?'Опишите результат и приложите фото ремонта.':ticket.can_accept?'Примите заявку, когда готовы приступить к работе.':ticket.can_acknowledge_entrapment&&!ticket.entrapment_acknowledged?'Подтвердите получение срочного обращения.':openStates.has(ticket.status)?'Изменения появятся в истории заявки.':'Результаты и история сохранены.'}</p>{primary&&<button className="primary ticket-desktop-primary" disabled={busy} onClick={primary[1]}>{primary[0]}</button>}<div className="ticket-secondary-actions">{secondary}</div></section>
   </aside></div>
   {menu&&<div className="ticket-more-menu"><div className="ticket-mobile-secondary">{secondary}</div>{permissions.assign&&<button onClick={()=>openAction('assign')}>Назначить исполнителя</button>}{permissions.cancel&&<button className="ticket-menu-danger" onClick={()=>openAction('cancel')}>Отменить заявку</button>}{onDiscuss&&<button onClick={()=>{setMenu(false);onDiscuss();}}>Обсудить в чате</button>}<button onClick={()=>setMenu(false)}>Скрыть меню</button></div>}
   <footer className="ticket-detail-mobile-bar">{primary&&<button className="primary" disabled={busy} onClick={primary[1]}>{primary[0]}</button>}<button aria-label="Ещё действия" aria-expanded={menu} onClick={()=>setMenu(v=>!v)}><MoreHorizontal size={20}/>Ещё</button></footer>
  </div>
 </Dialog></div>
 {action&&permissions[action]&&<TicketAction {...{action,busy,error,values,set,files,ticket,data}} eligible={data.technicians.filter(t=>t.active&&t.can_receive_tasks!==false)} onClose={()=>{if(!working.current)setAction(null);}} onFiles={addFiles} onRemove={file=>setFiles(old=>old.filter(f=>f!==file))} onSave={saveAction}/>}
 </>;
}
