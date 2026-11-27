import React,{useEffect,useRef,useState} from 'react';
import {Camera,Paperclip,X,TriangleAlert,Check} from 'lucide-react';
import {Dialog,Field,AddressPicker} from './components';
import {api,record} from './api';
import {prepareImages} from './imageCompression';
import {MAX_FILE_BYTES} from './uploadLimits';
import './tickets.css';
export default function TicketCreate({item={},data,user,onClose,onSaved}){
 const lift=data.elevators.find(e=>e.id===item.elevator);
 const [form,setForm]=useState({building:lift?.building||'',elevator:lift?.id||'',unknown:!lift,title:'',description:'',priority:'NORMAL',kind:'fault',entrance_hint:'',floor_hint:'',contact_name:'',contact_phone:'',assigned_to:''});
 const [files,setFiles]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[stage,setStage]=useState('');
 const op=useRef(null),working=useRef(false),created=useRef(null),uploads=useRef(new Map()),[locked,setLocked]=useState(false);
 const set=(key,value)=>{if(!locked)setForm(f=>({...f,[key]:value}));};
 const lifts=data.elevators.filter(e=>e.active&&e.building===Number(form.building));
 const eligible=data.technicians.filter(t=>t.active&&t.can_receive_tasks!==false);
 const add=async selected=>{if(locked||working.current)return;if(selected.length+files.length>8||selected.some(f=>f.size>MAX_FILE_BYTES)){setError('До 8 вложений по 100 МБ.');return;}working.current=true;setBusy(true);try{const images=await prepareImages(selected);setFiles(old=>[...old,...images]);setError('');}catch(e){setError(e.message);}finally{working.current=false;setBusy(false);}};
 useEffect(()=>{const warning=e=>{if(op.current){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warning);return()=>window.removeEventListener('beforeunload',warning);},[]);
 const close=()=>{if(!working.current)onClose();};
 const submit=async event=>{event.preventDefault();if(working.current||!user.can_create_ticket)return;working.current=true;setBusy(true);setError('');
  try{
   if(!op.current){
    if(!form.building||!form.unknown&&!form.elevator)throw Error('Выберите дом и укажите лифт либо отметьте, что он пока неизвестен.');
    const description=form.description.trim();if(!description)throw Error('Опишите, что случилось.');
    const title=form.title.trim()||(form.kind==='other'?'Обращение':form.priority==='ENTRAPMENT'?'Застревание':'Неисправность')+': '+description.split('\n')[0].slice(0,170);
    op.current={id:crypto.randomUUID(),type:'create',occurred_at:new Date().toISOString(),body:{building:Number(form.building),elevator:form.unknown?null:Number(form.elevator),title,description,priority:form.priority,entrance_hint:form.entrance_hint.trim(),floor_hint:form.floor_hint.trim(),contact_name:form.contact_name.trim(),contact_phone:form.contact_phone.trim(),...(form.assigned_to?{assigned_to:Number(form.assigned_to)}:{})}};setLocked(true);
   }
   if(!created.current){setStage('Создание заявки…');try{const result=await api('mobile/sync/',{method:'POST',body:op.current});created.current=result.ticket;}catch(e){if(e.status>=400&&e.status<500&&e.status!==409){op.current=null;setLocked(false);}throw e;}}
   for(const [index,file]of files.entries()){
    let upload=uploads.current.get(index);if(upload?.done)continue;if(!upload){upload={id:crypto.randomUUID(),done:false};uploads.current.set(index,upload);}
    setStage(`Заявка №${created.current.id} создана. Загрузка вложения ${index+1} из ${files.length}…`);
    const body=new FormData();body.append('kind','ticket');body.append('target_id',created.current.id);body.append('category','OTHER');body.append('upload_id',upload.id);body.append('file',file);await api('media/uploads/',{method:'POST',body});upload.done=true;
   }
   record('tickets','create','ok');op.current=null;await onSaved();onClose();
  }catch(e){record('tickets','create',e.status||'error');setError((created.current?`Заявка №${created.current.id} уже создана. Повтор завершит загрузку без новой заявки. `:'')+(e.message||'Не удалось сохранить заявку.'));}finally{working.current=false;setBusy(false);setStage('');}
 };
 return <div className="ticket-create"><Dialog wide title="Новая заявка" onClose={close}><form className="ticket-create-form" onSubmit={submit}>
  <p className="ticket-intro">Укажите адрес и что случилось</p>
  {!user.can_create_ticket&&<p className="notice">Создание доступно диспетчеру или дежурному механику.</p>}
  <fieldset disabled={busy||locked||!user.can_create_ticket}>
   <section className="ticket-form-section ticket-location"><AddressPicker buildings={data.buildings} value={form.building} label="Адрес дома *" onChange={value=>setForm(f=>({...f,building:value,elevator:'',unknown:true,assigned_to:''}))}/>
    <div className="ticket-field"><span>Лифт</span><div className="ticket-lift-choice"><button type="button" aria-pressed={!form.unknown} onClick={()=>set('unknown',false)}>Выбрать лифт</button><button type="button" aria-pressed={form.unknown} onClick={()=>setForm(f=>({...f,unknown:true,elevator:'',assigned_to:''}))}>{form.unknown&&<Check size={16}/>}Лифт пока неизвестен</button></div></div>
    {form.unknown?<p className="ticket-hint">Лифт можно уточнить после создания заявки.</p>:<Field label="Лифт в выбранном доме"><select required value={form.elevator} onChange={e=>{const selected=lifts.find(l=>l.id===Number(e.target.value));setForm(f=>({...f,elevator:e.target.value,assigned_to:''}));}}><option value="">Выберите лифт</option>{lifts.map(e=><option key={e.id} value={e.id}>{[e.display_number||e.factory_number||e.inventory_number, e.entrance_kind==='LIFT'?'Лифт '+e.entrance:e.entrance?'Подъезд '+e.entrance:''].filter(Boolean).join(' · ')}</option>)}</select></Field>}
    <div className="ticket-two-fields"><Field label="Подъезд, если известен"><input maxLength={50} value={form.entrance_hint} onChange={e=>set('entrance_hint',e.target.value)}/></Field><Field label="Этаж"><input maxLength={30} value={form.floor_hint} onChange={e=>set('floor_hint',e.target.value)}/></Field></div>
   </section>
   <section className="ticket-form-section"><h3>Что случилось</h3><div className="ticket-kind" role="group" aria-label="Тип обращения">{[['fault','Неисправность'],['entrapment','Застревание'],['other','Другой вопрос']].map(([kind,label])=><button key={kind} type="button" aria-pressed={form.kind===kind} className={kind==='entrapment'?'ticket-urgent-choice':''} onClick={()=>setForm(f=>({...f,kind,priority:kind==='entrapment'?'ENTRAPMENT':'NORMAL'}))}>{kind==='entrapment'&&<TriangleAlert size={16}/ >}{label}</button>)}</div>
    {form.kind==='entrapment'&&<p className="ticket-urgent-note">Люди в кабине. По умолчанию исполнитель — текущий дежурный механик.</p>}
    <Field label="Описание *"><textarea required maxLength={2000} rows={4} placeholder="Что произошло и что сообщил заявитель" value={form.description} onChange={e=>set('description',e.target.value)}/></Field>
    <div className="actions"><label className="button attachment-picker"><Camera size={17}/>Снять фото<input type="file" aria-label="Снять фото заявки" capture="environment" accept="image/jpeg,image/png,image/webp" onChange={e=>{add([...e.target.files]);e.target.value='';}}/></label><label className="button attachment-picker"><Paperclip size={17}/>Прикрепить файл<input type="file" aria-label="Вложения новой заявки" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm" onChange={e=>{add([...e.target.files]);e.target.value='';}}/></label></div><small className="ticket-hint">Фото и видео · до 8 файлов по 100 МБ</small>
    {files.length>0&&<ul className="ticket-file-list">{files.map((file,index)=><li key={index}><span>{file.name}</span><button type="button" aria-label={'Убрать '+file.name} onClick={()=>setFiles(old=>old.filter((_,i)=>i!==index))}><X size={15}/></button></li>)}</ul>}
   </section>
   <details className="ticket-form-section"><summary>Контакт заявителя · необязательно</summary><div className="ticket-two-fields"><Field label="Имя заявителя"><input maxLength={150} value={form.contact_name} onChange={e=>set('contact_name',e.target.value)}/></Field><Field label="Телефон заявителя"><input type="tel" maxLength={50} value={form.contact_phone} onChange={e=>set('contact_phone',e.target.value)}/></Field></div></details>
   <details className="ticket-form-section"><summary>Исполнитель и другие настройки</summary><Field label="Исполнитель"><select value={form.assigned_to} onChange={e=>set('assigned_to',e.target.value)}><option value="">{form.priority==='ENTRAPMENT'?'Автоматически — текущий дежурный механик':'Автоматически — механик лифта'}</option>{eligible.map(t=><option key={t.id} value={t.id}>{t.full_name}</option>)}</select></Field><Field label="Приоритет"><select value={form.priority} onChange={e=>set('priority',e.target.value)}>{[['NORMAL','Обычный'],['HIGH','Высокий'],['ENTRAPMENT','Застревание'],['EMERGENCY','Аварийный'],['LOW','Низкий']].map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></Field><Field label="Краткое название — необязательно"><input maxLength={200} value={form.title} onChange={e=>set('title',e.target.value)}/></Field></details>
  </fieldset>
  {error&&<p className="error" role="alert">{error}</p>}{stage&&<p role="status">{stage}</p>}
  <footer className="ticket-create-footer"><small>* Обязательные поля</small><button type="button" disabled={busy} onClick={close}>Отмена</button><button className="primary" disabled={busy||!user.can_create_ticket}>{busy?'Сохранение…':locked?'Повторить сохранение':'Создать заявку'}</button></footer>
 </form></Dialog></div>;
}
