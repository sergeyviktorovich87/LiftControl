import React,{useEffect,useRef,useState} from 'react';
import {api} from './api';
import {prepareImages} from './imageCompression';
import {MAX_FILE_BYTES,MAX_MULTIPART_FILES} from './uploadLimits.js';

export default function Nameplates({project,lift,archived=false}) {
 const [rows,setRows]=useState([]),[description,setDescription]=useState(''),[files,setFiles]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);
 const input=useRef(),operation=useRef(null),route=`commissioning/${project}/lifts/${lift.id}/nameplates/`;
 const load=async()=>{setRows(await api(route));setLoaded(true);};
 useEffect(()=>{let alive=true;api(route).then(rows=>{if(alive){setRows(rows);setLoaded(true);}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[route]);
 async function submit(e){e.preventDefault();if(busy||!files.length||!description.trim())return;setBusy(true);setError('');try{
  if(files.length>MAX_MULTIPART_FILES||files.some(f=>f.size>MAX_FILE_BYTES))throw Error('До 5 фотографий по 100 МБ.');
  const images=await prepareImages(files),form=new FormData();
  operation.current??=crypto.randomUUID();form.append('operation_id',operation.current);form.append('description',description.trim());images.forEach(f=>form.append('photos',f));
  await api(route,{method:'POST',body:form});setDescription('');setFiles([]);operation.current=null;if(input.current)input.current.value='';await load();
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <section className="nameplates"><h3>{lift.label}</h3>{error&&<p className="error" role="alert">{error}</p>}
  {loaded&&!rows.length&&<p className="muted">Шильдики ещё не добавлены.</p>}
  <div className="nameplate-grid">{rows.map(row=><figure key={row.id}><a href={row.url} target="_blank" rel="noreferrer"><img loading="lazy" src={row.preview_url||row.url} alt={row.description}/></a><figcaption><b>{row.description}</b><small>{row.author} · {new Date(row.created_at).toLocaleString('ru-RU')}</small></figcaption></figure>)}</div>
  {lift.can_edit&&!archived&&<form onSubmit={submit} className="nameplate-form"><label className="field">Что за шильдик<textarea placeholder="Например: ограничитель скорости, модель…" value={description} maxLength={1000} required disabled={busy} onChange={e=>{operation.current=null;setDescription(e.target.value);}}/></label><label className="button attachment-picker">Прикрепить фото<input ref={input} type="file" multiple accept="image/jpeg,image/png,image/webp" disabled={busy} required onChange={e=>{operation.current=null;setFiles([...e.target.files]);}}/></label>{files.length>0&&<small>{files.length} фото выбрано</small>}<button className="primary" disabled={busy||!files.length||!description.trim()}>{busy?'Сохранение…':'Сохранить шильдик'}</button></form>}
 </section>;
}
