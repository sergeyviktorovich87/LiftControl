import MessageReceipt from './MessageReceipt';
import {MAX_MULTIPART_FILES} from './uploadLimits.js';
import MediaLibrary from './MediaLibrary';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Download,Paperclip,Send,X} from 'lucide-react';
import {api,download,PREVIEW} from './api';
import {Dialog,Field} from './components';
import {prepareImages} from './imageCompression';

export default function ChatMedia({user,data,initialReference,onReferenceChange,onOpenReference,initialMessage,onMessageOpened,onRead,commissioning=false,onBack}){
 const [messages,setMessages]=useState([]),[body,setBody]=useState(''),[reference,setReference]=useState(initialReference||null),[files,setFiles]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[exporting,setExporting]=useState(false),[showMedia,setShowMedia]=useState(false);
 const end=useRef(),input=useRef(),messageId=useRef(initialMessage);
 const readThrough=useRef(0),reading=useRef(false),operationId=useRef(null);
 const route=commissioning?'commissioning/chat/':'chat/';
 const selectedMessage=()=>messageId.current||(!commissioning&&new URLSearchParams(location.search).get('message'));
 const changeReference=value=>{setReference(value);onReferenceChange?.(value);};
 const refresh=useCallback(async()=>{try{let rows=await api(route);const selected=selectedMessage();if(/^[1-9][0-9]*$/.test(selected||'')&&!rows.some(r=>r.id===Number(selected))){rows=[await api(route+selected+'/'),...rows];}setMessages(rows);if(!PREVIEW&&user.message_receipts_api&&rows.length)await api('notifications/receipts/',{method:'POST',body:{target:commissioning?'commissioning_chat':'chat',ids:rows.slice(-200).map(r=>r.id)}});}catch(e){if(e.status===403)setMessages([]);setError(e.message);}},[route]);
 useEffect(()=>{if(initialMessage)onMessageOpened?.();},[]);
 useEffect(()=>{refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},5000);return()=>clearInterval(timer);},[refresh]);
 useEffect(()=>{const selected=selectedMessage();if(selected){document.getElementById('chat-message-'+selected)?.scrollIntoView({block:'center'});}else end.current?.scrollIntoView({block:'nearest'});},[messages.length]);
 useEffect(()=>{
   const through=messages.reduce((last,row)=>Math.max(last,row.id),0);
   if(user.message_receipts_api||PREVIEW||!user.notification_counts_api||document.hidden||reading.current||through<=readThrough.current)return;
   reading.current=true;
   api('notifications/read-chat/',{method:'POST',body:{through,target:commissioning?'commissioning_chat':'chat'}})
     .then(()=>{readThrough.current=through;onRead?.();})
     .catch(()=>{}).finally(()=>{reading.current=false;});
 },[messages,commissioning,onRead,user.notification_counts_api]);
 const choose=async e=>{const selected=[...e.target.files];operationId.current=null;e.target.value='';if(selected.length>MAX_MULTIPART_FILES){setError('До 5 вложений на сообщение.');return;}
  setBusy(true);setError('');try{const next=await prepareImages(selected);setFiles(next);}catch(e){setError(e.message);}finally{setBusy(false);}};
 const send=async e=>{e.preventDefault();if(busy||!body.trim()&&!files.length&&!reference)return;setBusy(true);setError('');try{
  const operation=commissioning?(operationId.current??=globalThis.crypto?.randomUUID?.()):null;
  let payload={body:body.trim()};if(operation)payload.operation_id=operation;if(reference)payload[reference.kind==='ticket'?'linked_ticket':'linked_part']=reference.id;if(files.length){const form=new FormData();form.append('body',body.trim());if(operation)form.append('operation_id',operation);if(reference)form.append(reference.kind==='ticket'?'linked_ticket':'linked_part',String(reference.id));for(const f of files)form.append(commissioning?'photos':'files',f);payload=form;}
  await api(route,{method:'POST',body:payload});operationId.current=null;setBody('');setFiles([]);changeReference(null);if(input.current)input.current.value='';await refresh();
 }catch(e){setError(e.message);}finally{setBusy(false);}};
 return <><div className="page-heading"><div><h1>{commissioning?'Чат наладчиков':'Чат команды'}</h1></div>{commissioning?<button onClick={onBack}>К объектам наладки</button>:user.can_export_chat&&<button onClick={()=>setExporting(true)}><Download size={17}/>Выгрузить чат</button>}</div>
  {!commissioning&&<><button onClick={()=>setShowMedia(v=>!v)}>Вложения чата по месяцам</button>{showMedia&&<MediaLibrary user={user} source="chat"/>}</>}
  <section className="panel chat-panel"><header className="panel-heading"><div><b>{user.organization}</b><small>Последние 200 сообщений</small></div><span className="badge DONE">Общий чат</span></header>
   <div className="messages">{messages.map(m=><MessageReceipt key={m.id} user={user} target={commissioning?'commissioning_chat':'chat'} id={m.id} own={m.author===user.id} receipt={m.receipt}><article id={'chat-message-'+m.id} className={'message '+(m.author===user.id?'own':'')} key={m.id}><header><b>{m.author_name}</b><time>{new Date(m.created_at).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'})}</time></header>
    {m.reference&&<button className="chat-reference" type="button" onClick={()=>onOpenReference?.(m.reference)}><b>{m.reference.kind==='ticket'?'Заявка':'Запчасть'} #{m.reference.id} · {m.reference.title}</b><small>{m.reference.address} · лифт {m.reference.elevator} · {m.reference.status}</small></button>}{m.body&&<p>{m.body}</p>}<div className="chat-attachments">{(m.attachments||[]).map(a=>a.content_type.startsWith('video/')?<div key={a.id} className="chat-video"><video src={a.url} controls playsInline preload="metadata" poster={a.preview_url||undefined} aria-label="Видео в чате"/><a href={a.url} download={"video-"+a.id+(a.content_type==="video/webm"?".webm":a.content_type==="video/quicktime"?".mov":".mp4")}>Скачать видео</a></div>:<a href={a.url} key={a.id} target="_blank" rel="noreferrer"><img src={a.preview_url||a.url} alt="Фото в чате" loading="lazy"/></a>)}</div></article></MessageReceipt>)}{!messages.length&&<p className="empty">Начните рабочее обсуждение</p>}<div ref={end}/></div>
   {error&&<p className="error" role="alert">{error}</p>}<form className="composer media-composer" onSubmit={send}>{!commissioning&&<div className="chat-link-pick"><label>Приложить карточку: <select aria-label="Прикрепить заявку или запчасть" value={reference?reference.kind+':'+reference.id:''} disabled={busy} onChange={e=>{const [kind,id]=e.target.value.split(':');const selected=(kind==='ticket'?data?.tickets:data?.parts)?.find(x=>x.id===Number(id));changeReference(selected?{kind,id:selected.id,title:kind==='ticket'?selected.title:selected.part}:null);}}><option value="">Без карточки</option><optgroup label="Заявки">{(data?.tickets||[]).map(t=><option key={'t'+t.id} value={'ticket:'+t.id}>#{t.id} · {t.title}</option>)}</optgroup><optgroup label="Запчасти">{(data?.parts||[]).map(p=><option key={'p'+p.id} value={'part:'+p.id}>#{p.id} · {p.part}</option>)}</optgroup></select></label>{reference&&<button type="button" onClick={()=>changeReference(null)}>Убрать ссылку</button>}</div>}<textarea value={body} maxLength={4000} onChange={e=>{operationId.current=null;setBody(e.target.value);}} placeholder="Написать команде…" aria-label="Сообщение команде" required={!files.length&&!reference} disabled={busy}/>
    <label className={'button attachment-picker '+(busy?'disabled':'')}><Paperclip size={20}/><span>{commissioning?'Фото':'Фото / видео'}</span><input ref={input} type="file" accept={commissioning?'image/jpeg,image/png,image/webp':'image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm'} multiple aria-label={commissioning?'Фото для чата':'Фото и видео для чата'} onChange={choose} disabled={busy||PREVIEW}/></label>
    <button className="primary" aria-label={busy?'Отправка…':'Отправить'} disabled={busy||!body.trim()&&!files.length&&!reference}><Send size={19}/><span>{busy?'Отправка…':'Отправить'}</span></button>
    {files.length>0&&<div className="pending-attachments">{files.map((f,i)=><span key={i}>{f.name} <small>{(f.size/1024/1024).toFixed(1)} МБ</small><button type="button" aria-label={'Убрать '+f.name} disabled={busy} onClick={()=>{operationId.current=null;setFiles(prev=>prev.filter((_,index)=>index!==i));}}><X size={14}/></button></span>)}</div>}</form>
  </section><p className="muted small">До 5 вложений по 100 МБ каждое. {!commissioning&&'Видео MP4/MOV или WebM до 3 минут.'}</p>
  {exporting&&<Dialog title="Выгрузить чат" onClose={()=>setExporting(false)}><form onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);setBusy(true);try{download('LiftControl-chat.csv',await api(`chat/export/?from=${data.get('from')}&to=${data.get('to')}`,{blob:true}));setExporting(false);}catch(e){setError(e.message);}finally{setBusy(false);}}}><div className="form-grid"><Field label="С"><input type="date" name="from" required/></Field><Field label="По"><input type="date" name="to" required defaultValue={new Date().toLocaleDateString('en-CA',{timeZone:user.timezone})}/></Field></div><p className="muted">CSV сообщений за период до 366 дней. Вложения остаются в чате.</p><footer className="form-actions"><button type="button" onClick={()=>setExporting(false)}>Отмена</button><button className="primary" disabled={busy}>Скачать CSV</button></footer></form></Dialog>}
 </>;
}
