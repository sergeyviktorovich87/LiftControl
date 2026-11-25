import React,{useEffect,useState} from 'react';
import {Camera,ImagePlus,X} from 'lucide-react';
import {Dialog,Field} from './components';
import {MAX_FILE_BYTES,MAX_MULTIPART_FILES} from './uploadLimits';
function Preview({file,onRemove,disabled}){
 const [url,setUrl]=useState('');useEffect(()=>{const next=URL.createObjectURL(file);setUrl(next);return()=>URL.revokeObjectURL(next);},[file]);
 return <figure><img src={url} alt={file.name}/><button type="button" aria-label={'Убрать '+file.name} disabled={disabled} onClick={onRemove}><X size={15}/></button></figure>;
}
export default function CommissioningReport({project,lift,draft,onDraft,onSave,onClose,onReload,busy,error}){
 const [localError,setLocalError]=useState('');
 const add=files=>{const photos=[...(draft.photos||[]),...files];if(photos.length>MAX_MULTIPART_FILES||photos.some(file=>file.size>MAX_FILE_BYTES)){setLocalError('До 5 фотографий по 100 МБ.');return;}setLocalError('');onDraft({...draft,photos});};
 const changed=Number(draft.progress)!==draft.baseProgress;
 return <Dialog title="Новый отчёт" onClose={onClose}>
 <form className="comm-report-form" onSubmit={event=>{event.preventDefault();if(changed&&draft.description.trim())onSave();}}>
  <p className="muted">{project.name} · {lift.label}</p>
  <Field label="Готовность лифта"><div className="comm-report-progress"><input aria-label="Готовность, процентов" type="number" min="0" max="100" step="1" required value={draft.progress} disabled={busy} onChange={e=>onDraft({...draft,progress:e.target.value})}/><b>%</b><small>Сейчас сохранено: {draft.baseProgress}%</small></div></Field>
  <input className="comm-progress-slider" aria-label="Изменить готовность ползунком" type="range" min="0" max="100" step="1" value={draft.progress} disabled={busy} onChange={e=>onDraft({...draft,progress:e.target.value})}/>
  <Field label="Что сделано"><textarea value={draft.description} required maxLength={4000} rows={4} disabled={busy} placeholder="Опишите выполненную работу" onChange={e=>onDraft({...draft,description:e.target.value})}/></Field>
  <div><h3>Фото с объекта</h3><div className="comm-report-photos">{(draft.photos||[]).map((file,index)=><Preview key={index+':'+file.name} file={file} disabled={busy} onRemove={()=>onDraft({...draft,photos:draft.photos.filter((_,i)=>i!==index)})}/>)}</div>
   <div className="actions"><label className="button attachment-picker"><Camera size={18}/>Снять фото<input aria-label="Снять фото отчёта" type="file" capture="environment" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e=>{add([...e.target.files]);e.target.value='';}}/></label><label className="button attachment-picker"><ImagePlus size={18}/>Из галереи<input aria-label="Фотографии отчёта" type="file" multiple accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e=>{add([...e.target.files]);e.target.value='';}}/></label></div>
  </div>
  <small className="muted">Укажите новый процент и описание. Прогресс сохранится вместе с отчётом.</small>
  {(error||localError)&&<div role="alert" className="error">{localError||error}{error&&<button type="button" disabled={busy} onClick={onReload}>Загрузить актуальные данные</button>}</div>}
  <footer className="form-actions"><button type="button" disabled={busy} onClick={onClose}>Отмена</button><button className="primary" disabled={busy||!changed||!draft.description.trim()}>{busy?'Сохранение…':'Сохранить отчёт'}</button></footer>
 </form></Dialog>;
}
