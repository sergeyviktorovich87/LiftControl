import MessageReceipt from './MessageReceipt';
import {MAX_FILE_BYTES,MAX_MULTIPART_FILES} from './uploadLimits.js';
import MediaLibrary from './MediaLibrary';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ArrowDown,ArrowLeft,Camera,ChevronRight,ClipboardList,Copy,Download,FileText,Menu,MessageSquare,MoreVertical,Paperclip,Pin,Reply,Search,Send,X} from 'lucide-react';
import {api,download,PREVIEW} from './api';
import {Dialog,Field} from './components';
import {prepareImages} from './imageCompression';
import './chat.css';

export default function ChatMedia({user,data,initialReference,onReferenceChange,onOpenReference,initialMessage,onMessageOpened,onRead,commissioning=false,onBack,onOpenMenu,menuButton,drafts,outbox}){
 const draftKey=user.id+':'+user.organization_id;
 const [messages,setMessages]=useState([]),[body,setBody]=useState(()=>drafts?.get(draftKey)||''),[reference,setReference]=useState(initialReference||null),[files,setFiles]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[exporting,setExporting]=useState(false),[showMedia,setShowMedia]=useState(false);
 const [actionMessage,setActionMessage]=useState(null);
 useEffect(()=>{setReference(initialReference||null);},[initialReference]);
 const [reply,setReply]=useState(null),[pinned,setPinned]=useState(null),[menu,setMenu]=useState(false),[linkPicker,setLinkPicker]=useState(false),[searching,setSearching]=useState(false),[query,setQuery]=useState(''),[below,setBelow]=useState(0);
 const end=useRef(),input=useRef(),textInput=useRef(),viewport=useRef(),messageId=useRef(initialMessage||new URLSearchParams(location.search).get('message')),focused=useRef(false);
 const atBottom=useRef(true),loaded=useRef(false),previousMax=useRef(0),reading=useRef(false),readThrough=useRef(0),operationId=useRef(null);
 const route=commissioning?'commissioning/chat/':'chat/';
 const selectedMessage=()=>messageId.current;
 const changeReference=value=>{setReference(value);onReferenceChange?.(value);};
 const refresh=useCallback(async()=>{try{
  let rows=await api(route);const selected=selectedMessage();
  if(/^[1-9][0-9]*$/.test(selected||'')&&!rows.some(r=>r.id===Number(selected)))rows=[await api(route+selected+'/'),...rows];
  const incoming=rows.filter(r=>r.id>previousMax.current&&r.author!==user.id).length;
  if(loaded.current&&!atBottom.current&&incoming)setBelow(n=>n+incoming);
  previousMax.current=Math.max(0,...rows.map(r=>r.id));setMessages(rows);setError('');
  if(!commissioning&&!PREVIEW&&user.chat_design_api)setPinned((await api('chat/pinned/')).message);
  if(!PREVIEW&&user.message_receipts_api&&rows.length)await api('notifications/receipts/',{method:'POST',body:{target:commissioning?'commissioning_chat':'chat',ids:rows.slice(-200).map(r=>r.id)}});
 }catch(e){if(e.status===403){setMessages([]);setPinned(null);}setError(e.message);}},[route,user.id,user.chat_design_api]);
 useEffect(()=>{if(initialMessage)onMessageOpened?.();},[]);
 useEffect(()=>{refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},5000);return()=>clearInterval(timer);},[refresh,outbox?.revision]);
 const scrollBottom=()=>{messageId.current=null;atBottom.current=true;setBelow(0);end.current?.scrollIntoView({block:'nearest'});};
 const openMessage=async id=>{try{if(!messages.some(m=>m.id===id)){const row=await api(route+id+'/');setMessages(rows=>[row,...rows]);}messageId.current=id;focused.current=false;atBottom.current=false;requestAnimationFrame(()=>document.getElementById('chat-message-'+id)?.scrollIntoView({block:'center',behavior:'smooth'}));}catch(e){setError(e.message);}};
 useEffect(()=>{const selected=selectedMessage();if(!messages.length)return;if(selected&&!focused.current){document.getElementById('chat-message-'+selected)?.scrollIntoView({block:'center'});focused.current=true;atBottom.current=false;}else if(!loaded.current||atBottom.current)end.current?.scrollIntoView({block:'nearest'});loaded.current=true;},[messages.length]);
 useEffect(()=>{
  const through=messages.reduce((last,row)=>Math.max(last,row.id),0);
  if(user.message_receipts_api||PREVIEW||!user.notification_counts_api||document.hidden||reading.current||through<=readThrough.current)return;
  reading.current=true;api('notifications/read-chat/',{method:'POST',body:{through,target:commissioning?'commissioning_chat':'chat'}}).then(()=>{readThrough.current=through;onRead?.();}).catch(()=>{}).finally(()=>{reading.current=false;});
 },[messages,commissioning,onRead,user.notification_counts_api]);
 const choose=async e=>{const selected=[...e.target.files];operationId.current=null;e.target.value='';if(selected.some(file=>file.size>MAX_FILE_BYTES)){setError('Размер файла должен быть до 100 МБ.');return;}if(selected.length+files.length>MAX_MULTIPART_FILES){setError('До 5 вложений на сообщение.');return;}setBusy(true);setError('');try{const prepared=await prepareImages(selected);setFiles(prev=>[...prev,...prepared]);}catch(e){setError(e.message);}finally{setBusy(false);}};
 const send=async e=>{e?.preventDefault();if(busy||!body.trim()&&!files.length&&!reference)return;setBusy(true);setError('');try{
  const operation=commissioning?(operationId.current??=globalThis.crypto?.randomUUID?.()):null;
  let payload={body:body.trim()};if(operation)payload.operation_id=operation;if(reply&&!commissioning)payload.reply_to=reply.id;if(reference)payload[reference.kind==='ticket'?'linked_ticket':'linked_part']=reference.id;
  if(outbox&&!PREVIEW){
    outbox.add(payload,files);
    drafts.delete(draftKey);
    setBody('');setFiles([]);setReply(null);changeReference(null);
    if(textInput.current)textInput.current.style.height='';
    requestAnimationFrame(scrollBottom);
    return;
  }
  if(files.length){const form=new FormData();for(const [key,value] of Object.entries(payload))form.append(key,String(value));for(const f of files)form.append(commissioning?'photos':'files',f);payload=form;}
  await api(route,{method:'POST',body:payload});operationId.current=null;drafts?.delete(draftKey);setBody('');setFiles([]);setReply(null);changeReference(null);if(input.current)input.current.value='';atBottom.current=true;await refresh();requestAnimationFrame(scrollBottom);
 }catch(e){setError(e.message);}finally{setBusy(false);}};
 const pin=async message=>{try{await api('chat/'+message.id+'/pin/',{method:'POST',body:{pinned:!message.pinned}});await refresh();}catch(e){setError(e.message);}};
 const copy=async message=>{try{await navigator.clipboard.writeText(message.body||'');}catch{setError('Не удалось скопировать текст.');}};
 const day=date=>new Date(date).toLocaleDateString('ru-RU',{timeZone:user.timezone,day:'numeric',month:'long',year:'numeric'});
 const visible=messages.filter(m=>!query||[m.body,m.author_name,m.reference?.title].some(v=>String(v||'').toLocaleLowerCase().includes(query.toLocaleLowerCase())));
 return <section className="messenger" aria-label="Чат">
  <header className="messenger-header">{commissioning&&<button type="button" className="icon-button" onClick={onBack} aria-label="К объектам наладки"><ArrowLeft/></button>}{onOpenMenu?<button type="button" ref={menuButton} className="icon-button messenger-nav" aria-label="Открыть боковое меню" onClick={onOpenMenu}><Menu/></button>:<span className="messenger-avatar"><MessageSquare size={23}/></span>}<div className="messenger-title"><h1>{commissioning?'Чат наладчиков':'Чат'}</h1><small>{user.organization}</small></div><button type="button" className="icon-button" aria-label="Поиск в чате" aria-expanded={searching} onClick={()=>{setSearching(v=>!v);setQuery('');}}><Search/><span className="messenger-search-label">Поиск по чату</span></button><div className="messenger-menu"><button type="button" className="icon-button" aria-label="Меню чата" aria-expanded={menu} onClick={()=>setMenu(v=>!v)}><MoreVertical/></button>{menu&&<div className="messenger-dropdown">{!commissioning&&<button onClick={()=>{setShowMedia(v=>!v);setMenu(false);}}><Paperclip size={17}/>Вложения чата</button>}{!commissioning&&user.can_export_chat&&<button onClick={()=>{setExporting(true);setMenu(false);}}><Download size={17}/>Выгрузить чат</button>}<button onClick={()=>{refresh();setMenu(false);}}>Обновить</button></div>}</div></header>
  {searching&&<div className="messenger-search"><Search size={18}/><input autoFocus value={query} onChange={e=>setQuery(e.target.value)} placeholder="Текст или автор сообщения" aria-label="Поиск по загруженным сообщениям"/><small>{visible.length}</small><button className="icon-button" aria-label="Закрыть поиск" onClick={()=>{setSearching(false);setQuery('');}}><X size={18}/></button></div>}
  {pinned&&<button type="button" className="messenger-pinned" onClick={()=>openMessage(pinned.id)}><Pin size={18}/><span><b>Закреплено</b> · {pinned.body||'Вложение'}</span></button>}
  {showMedia&&!commissioning&&<div className="messenger-library"><button onClick={()=>setShowMedia(false)}>Закрыть вложения</button><MediaLibrary user={user} source="chat"/></div>}
  <div className="messenger-body"><div ref={viewport} className="messenger-scroll" onScroll={()=>{const node=viewport.current;atBottom.current=node.scrollHeight-node.clientHeight-node.scrollTop<80;if(atBottom.current)setBelow(0);}} onLoad={()=>{if(atBottom.current)end.current?.scrollIntoView({block:'nearest'});}}><div className="messenger-feed">
   {visible.map((m,index)=>{const own=m.author===user.id;return <React.Fragment key={m.id}>{(index===0||day(visible[index-1].created_at)!==day(m.created_at))&&<div className="messenger-day"><span>{day(m.created_at)===day(Date.now())?'Сегодня':day(m.created_at)}</span></div>}<div className={'messenger-row '+(own?'own':'')}>{!own&&<span className="messenger-initial" aria-hidden="true">{m.author_name?.trim().split(/\s+/).slice(0,2).map(word=>word[0]).join('')||'?'}</span>}<MessageReceipt user={user} target={commissioning?'commissioning_chat':'chat'} id={m.id} own={own} receipt={m.receipt}><article id={'chat-message-'+m.id} className="messenger-bubble">
    {!own&&<b className="messenger-author">{m.author_name}</b>}{m.reply&&<button type="button" className="messenger-quote" onClick={()=>openMessage(m.reply.id)}><b>{m.reply.author_name}</b><span>{m.reply.body}</span></button>}
<div className="chat-attachments">{(m.attachments||[]).map(a=>a.content_type?.startsWith('video/')?<video key={a.id} src={a.url} controls playsInline preload="metadata" poster={a.preview_url||undefined}/>:a.content_type&&!a.content_type.startsWith('image/')?<a className="messenger-file" key={a.id} href={a.url} target="_blank" rel="noreferrer"><FileText/>{a.name||'Скачать файл'}</a>:<a href={a.url} key={a.id} target="_blank" rel="noreferrer"><img src={a.preview_url||a.url} alt="Фото в чате" loading="lazy"/></a>)}</div>
    {m.body&&<p>{m.body}</p>}
    {m.reference&&<button className="chat-reference" type="button" onClick={()=>onOpenReference?.(m.reference)}>
      <ClipboardList aria-hidden="true" size={20}/><span><b>{m.reference.kind==='ticket'?'Заявка':'Запчасть'} №{m.reference.id}</b><small>{[m.reference.address,m.reference.elevator&&'лифт '+m.reference.elevator].filter(Boolean).join(' · ')}</small><small>{m.reference.title}</small></span><ChevronRight size={17}/>
    </button>}
    <footer><time title={new Date(m.created_at).toLocaleString('ru-RU',{timeZone:user.timezone})}>{new Date(m.created_at).toLocaleTimeString('ru-RU',{timeZone:user.timezone,hour:'2-digit',minute:'2-digit'})}</time>{m.pinned&&<Pin size={12}/>}
    {!commissioning&&<button className="messenger-message-menu" type="button" aria-label="Действия с сообщением" aria-expanded={actionMessage===m.id} onClick={()=>setActionMessage(actionMessage===m.id?null:m.id)}><MoreVertical size={16}/></button>}</footer>
    <div className={'messenger-actions'+(actionMessage===m.id?' expanded':'')} onClick={()=>setActionMessage(null)}>{!commissioning&&user.chat_design_api&&<button type="button" aria-label="Ответить" title="Ответить" onClick={()=>{setReply(m);textInput.current?.focus();}}><Reply size={16}/></button>}{m.body&&<button type="button" aria-label="Копировать сообщение" title="Копировать" onClick={()=>copy(m)}><Copy size={16}/></button>}{!commissioning&&user.can_export_chat&&user.chat_design_api&&<button type="button" aria-label={m.pinned?'Открепить':'Закрепить'} title={m.pinned?'Открепить':'Закрепить'} onClick={()=>pin(m)}><Pin size={16}/></button>}</div>
   </article></MessageReceipt></div></React.Fragment>;})}
   {outbox?.entries.map(entry=><div key={entry.key} className="messenger-row own"><article className="messenger-bubble pending" role="status">
    <p>{entry.payload.body}</p>{entry.files.map((file,i)=><small key={i}>{file.name} </small>)}
    <footer>{entry.status==='error'?entry.error:entry.status==='sending'?'Отправляется…':'Ожидает сети'}</footer>
    {entry.status==='error'&&<div><button type="button" onClick={()=>outbox.retry(entry.key)}>Повторить</button><button type="button" onClick={()=>outbox.remove(entry.key)}>Убрать</button></div>}
   </article></div>)}
   {!visible.length&&!outbox?.entries.length&&<p className="empty">{query?'Сообщения не найдены':'Начните рабочее обсуждение'}</p>}<div ref={end}/>
  </div></div>{below>0&&<button type="button" className="messenger-down" onClick={scrollBottom} aria-label={'Новых сообщений: '+below}><ArrowDown size={20}/><span>{below}</span></button>}</div>
  {error&&<p className="error" role="alert">{error}</p>}
  <form className="messenger-compose" onSubmit={send}>
   {reply&&<div className="messenger-compose-context"><Reply size={18}/><span><b>{reply.author_name}</b><small>{reply.body||'Вложение'}</small></span><button type="button" aria-label="Отменить ответ" onClick={()=>setReply(null)}><X size={17}/></button></div>}
   {reference&&<div className="messenger-compose-context"><FileText size={18}/><span>{reference.title}</span><button type="button" aria-label="Убрать карточку" onClick={()=>changeReference(null)}><X size={17}/></button></div>}
   {files.length>0&&<div className="pending-attachments">{files.map((f,i)=><span key={i}>{f.name}<button type="button" aria-label={'Убрать '+f.name} disabled={busy} onClick={()=>{operationId.current=null;setFiles(prev=>prev.filter((_,index)=>index!==i));}}><X size={14}/></button></span>)}</div>}
   {linkPicker&&!commissioning&&<label className="messenger-link-picker">Прикрепить карточку<select aria-label="Прикрепить заявку или запчасть" value="" disabled={busy} onChange={e=>{const [kind,id]=e.target.value.split(':');const selected=(kind==='ticket'?data?.tickets:data?.parts)?.find(x=>x.id===Number(id));changeReference(selected?{kind,id:selected.id,title:kind==='ticket'?selected.title:selected.part}:null);setLinkPicker(false);}}><option value="">Выберите…</option><optgroup label="Заявки">{(data?.tickets||[]).map(t=><option key={t.id} value={'ticket:'+t.id}>#{t.id} · {t.title}</option>)}</optgroup><optgroup label="Запчасти">{(data?.parts||[]).map(p=><option key={p.id} value={'part:'+p.id}>#{p.id} · {p.part}</option>)}</optgroup></select></label>}
   <div className="messenger-input-row"><label className={'icon-button messenger-attach '+(busy?'disabled':'')} title={commissioning?'Фото':'Фото и видео'}><Paperclip size={22}/><input ref={input} type="file" accept={commissioning?'image/jpeg,image/png,image/webp':'image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm'} multiple aria-label="Прикрепить фото или видео" onChange={choose} disabled={busy||PREVIEW}/></label>
   <textarea ref={textInput} rows={1} value={body} maxLength={4000} onChange={e=>{operationId.current=null;setBody(e.target.value);if(drafts){if(e.target.value)drafts.set(draftKey,e.target.value);else drafts.delete(draftKey);}e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,140)+'px';}} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send(e);}}} placeholder="Сообщение…" aria-label="Сообщение" disabled={busy}/>{!commissioning&&<button type="button" className="icon-button" aria-label="Прикрепить карточку" title="Прикрепить карточку" onClick={()=>setLinkPicker(v=>!v)}><FileText size={20}/></button>}{!commissioning&&<label className="icon-button messenger-attach messenger-camera" title="Снять фото"><Camera size={22}/><input type="file" aria-label="Снять фото" accept="image/*" capture="environment" onChange={choose} disabled={busy||PREVIEW}/></label>}<button className="messenger-send" aria-label={busy?'Отправка…':'Отправить'} disabled={busy||!body.trim()&&!files.length&&!reference}><Send size={21}/></button></div>
  </form>
  {exporting&&<Dialog title="Выгрузить чат" onClose={()=>setExporting(false)}><form onSubmit={async e=>{e.preventDefault();const fields=new FormData(e.currentTarget);setBusy(true);try{download('LiftControl-chat.csv',await api(`chat/export/?from=${fields.get('from')}&to=${fields.get('to')}`,{blob:true}));setExporting(false);}catch(e){setError(e.message);}finally{setBusy(false);}}}><div className="form-grid"><Field label="С"><input type="date" name="from" required/></Field><Field label="По"><input type="date" name="to" required defaultValue={new Date().toLocaleDateString('en-CA',{timeZone:user.timezone})}/></Field></div><footer className="form-actions"><button type="button" onClick={()=>setExporting(false)}>Отмена</button><button className="primary" disabled={busy}>Скачать CSV</button></footer></form></Dialog>}
 </section>;
}
