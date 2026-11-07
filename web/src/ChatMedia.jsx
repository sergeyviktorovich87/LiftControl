import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Download,Paperclip,Send,X} from 'lucide-react';
import {api,download,PREVIEW} from './api';
import {Dialog,Field} from './components';

export default function ChatMedia({user}){
 const [messages,setMessages]=useState([]),[body,setBody]=useState(''),[files,setFiles]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[exporting,setExporting]=useState(false);
 const end=useRef(),input=useRef();
 const refresh=useCallback(async()=>{try{setMessages(await api('chat/'));}catch(e){setError(e.message);}},[]);
 useEffect(()=>{refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},5000);return()=>clearInterval(timer);},[refresh]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'});},[messages.length]);
 const choose=e=>{const next=[...e.target.files];if(next.length>5||next.reduce((n,f)=>n+f.size,0)>20*1024*1024||next.some(f=>f.type.startsWith('image/')&&f.size>10*1024*1024)){
  setError('До 5 вложений и 20 МБ на сообщение; фото до 10 МБ.');e.target.value='';return;}setFiles(next);setError('');};
 const send=async e=>{e.preventDefault();if(busy||!body.trim()&&!files.length)return;setBusy(true);setError('');try{
  let data={body:body.trim()};if(files.length){data=new FormData();data.append('body',body.trim());for(const f of files)data.append('files',f);}
  await api('chat/',{method:'POST',body:data});setBody('');setFiles([]);if(input.current)input.current.value='';await refresh();
 }catch(e){setError(e.message);}finally{setBusy(false);}};
 return <><div className="page-heading"><div><span className="eyebrow">ОБЩЕНИЕ</span><h1>Чат команды</h1><p>Рабочий чат организации: текст, фото и видео.</p></div>{user.can_export_chat&&<button onClick={()=>setExporting(true)}><Download size={17}/>Выгрузить чат</button>}</div>
  <section className="panel chat-panel"><header className="panel-heading"><div><b>{user.organization}</b><small>Последние 200 сообщений</small></div><span className="badge DONE">Общий чат</span></header>
   <div className="messages">{messages.map(m=><article className={'message '+(m.author===user.id?'own':'')} key={m.id}><header><b>{m.author_name}</b><time>{new Date(m.created_at).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'})}</time></header>
    {m.body&&<p>{m.body}</p>}<div className="chat-attachments">{(m.attachments||[]).map(a=>a.content_type.startsWith('video/')?<div key={a.id} className="chat-video"><video src={a.url} controls playsInline preload="metadata" aria-label="Видео в чате"/><a href={a.url} download={"video-"+a.id+(a.content_type==="video/webm"?".webm":a.content_type==="video/quicktime"?".mov":".mp4")}>Скачать видео</a></div>:<a href={a.url} key={a.id} target="_blank" rel="noreferrer"><img src={a.url} alt="Фото в чате" loading="lazy"/></a>)}</div></article>)}{!messages.length&&<p className="empty">Начните рабочее обсуждение</p>}<div ref={end}/></div>
   {error&&<p className="error" role="alert">{error}</p>}<form className="composer media-composer" onSubmit={send}><textarea value={body} maxLength={4000} onChange={e=>setBody(e.target.value)} placeholder="Написать команде…" aria-label="Сообщение команде" required={!files.length} disabled={busy}/>
    <label className={'button attachment-picker '+(busy?'disabled':'')}><Paperclip size={20}/><span>Фото / видео</span><input ref={input} type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm" multiple aria-label="Фото и видео для чата" onChange={choose} disabled={busy||PREVIEW}/></label>
    <button className="primary" disabled={busy||!body.trim()&&!files.length}><Send size={19}/><span>{busy?'Отправка…':'Отправить'}</span></button>
    {files.length>0&&<div className="pending-attachments">{files.map((f,i)=><span key={i}>{f.name} <small>{(f.size/1024/1024).toFixed(1)} МБ</small><button type="button" aria-label={'Убрать '+f.name} disabled={busy} onClick={()=>setFiles(prev=>prev.filter((_,index)=>index!==i))}><X size={14}/></button></span>)}</div>}</form>
  </section><p className="muted small">Фото до 10 МБ. Видео MP4/MOV или WebM до 20 МБ и 3 минут. До 5 вложений, всего до 20 МБ на сообщение. Файлы доступны только сотрудникам этой организации.</p>
  {exporting&&<Dialog title="Выгрузить чат" onClose={()=>setExporting(false)}><form onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);setBusy(true);try{download('LiftControl-chat.csv',await api(`chat/export/?from=${data.get('from')}&to=${data.get('to')}`,{blob:true}));setExporting(false);}catch(e){setError(e.message);}finally{setBusy(false);}}}><div className="form-grid"><Field label="С"><input type="date" name="from" required/></Field><Field label="По"><input type="date" name="to" required defaultValue={new Date().toLocaleDateString('en-CA',{timeZone:user.timezone})}/></Field></div><p className="muted">CSV сообщений за период до 366 дней. Вложения остаются в чате.</p><footer className="form-actions"><button type="button" onClick={()=>setExporting(false)}>Отмена</button><button className="primary" disabled={busy}>Скачать CSV</button></footer></form></Dialog>}
 </>;
}
