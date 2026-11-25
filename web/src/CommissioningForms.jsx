import React,{useRef,useState} from 'react';
import {Dialog,Field} from './components';
import {compressImage} from './imageCompression';
const titles={'project':'Новый объект наладки','lift':'Добавить лифт','expense':'Записать расход','need':'Добавить препятствие или потребность','extra':'Предложить допработу','request':'Запросить новый лифт','archive':'Архивировать объект'};
const needs=[['OTHER','Прочее'],['WATER','Вода в приямке'],['POWER','Электричество'],['TOOL','Инструмент'],['MATERIAL','Материалы'],['ACCESS','Доступ'],['DOCUMENT','Документы'],['INSTALLATION','Монтажные работы']];
export const needNames=Object.fromEntries(needs);
export default function CommissioningForms({kind,project,user,onClose,onSubmit,busy,error,pending={},initialLift=null}){
 const [values,setValues]=useState(pending.values||{name:'',address:'',label:'',factory_number:'',amount:'',description:'',spent_on:new Intl.DateTimeFormat('sv-SE',{timeZone:user.timezone}).format(new Date()),lift:initialLift?String(initialLift):'',category:'OTHER',blocking:false,price:'0',reason:''}),[receipt,setReceipt]=useState(pending.receipt||null),[locked,setLocked]=useState(!!pending.operation);
 const operation=useRef(pending.operation||null),set=(key,value)=>setValues(prev=>({...prev,[key]:value}));
 const input=(key,label,type='text',required=true,maxLength=200)=><Field label={label}><input type={type} value={values[key]} required={required} maxLength={maxLength} {...(type==='number'?{min:key==='amount'?'0.01':'0',step:'0.01'}:{})} onChange={e=>set(key,e.target.value)}/></Field>;
 const text=(key,label,maxLength=2000)=><Field label={label}><textarea value={values[key]} required maxLength={maxLength} rows={3} onChange={e=>set(key,e.target.value)}/></Field>;
 const submit=async event=>{
  event.preventDefault();if(busy)return;
  await onSubmit(async post=>{
   if(kind==='project')return post('commissioning/',{name:values.name.trim(),address:values.address.trim()});
   else if(kind==='lift')await post(`commissioning/${project.id}/lifts/`,{label:values.label.trim(),factory_number:values.factory_number.trim()});
   else if(kind==='expense'){
    let saved=operation.current;
    if(!saved){saved={command:{id:crypto.randomUUID(),type:'expense',body:{amount:values.amount,description:values.description.trim(),spent_on:values.spent_on,lift:values.lift?Number(values.lift):null}},image:receipt?await compressImage(receipt):null};operation.current=saved;pending.operation=saved;pending.values=values;pending.receipt=receipt;setLocked(true);}
    let body=saved.command;if(saved.image){body=new FormData();body.append('command',JSON.stringify(saved.command));body.append('receipt',saved.image);}
    try{await post(`commissioning/${project.id}/sync/`,body);}catch(e){if(e.status>=400&&e.status<500){operation.current=null;pending.operation=null;setLocked(false);}throw e;}
   }else if(kind==='need')await post(`commissioning/${project.id}/needs/`,{lift:values.lift?Number(values.lift):null,category:values.category,description:values.description.trim(),blocking:values.blocking});
   else if(kind==='extra')await post(`commissioning/${project.id}/extra-work/`,{lift:values.lift?Number(values.lift):null,description:values.description.trim(),price:values.price});
   else if(kind==='request')await post(`commissioning/${project.id}/lift-requests/`,{label:values.label.trim()});
   else if(kind==='archive')await post(`commissioning/${project.id}/archive/`,{reason:values.reason.trim()});
  });
 };
 return <Dialog title={titles[kind]} onClose={()=>{if(!busy)onClose();}}><form className="comm-form" onSubmit={submit}>
  <fieldset disabled={busy||locked}>
   {kind==='project'&&<>{input('name','Название')}{input('address','Адрес','text',true,300)}</>}
   {kind==='lift'&&<>{input('label','Лифт / обозначение')}{input('factory_number','Заводской номер','text',false)}</>}
   {kind==='expense'&&<>{input('amount','Сумма, ₽','number')}{text('description','Описание расхода')}{input('spent_on','Дата расхода','date')}<Field label="Лифт"><select value={values.lift} onChange={e=>set('lift',e.target.value)}><option value="">Весь объект</option>{project.lifts.filter(l=>l.can_edit).map(l=><option key={l.id} value={l.id}>{l.label}</option>)}</select></Field><Field label="Фото чека"><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setReceipt(e.target.files?.[0]||null)}/></Field></>}
   {['need','extra'].includes(kind)&&<Field label="Относится к"><select value={values.lift} onChange={e=>set('lift',e.target.value)}><option value="">Весь объект</option>{project.lifts.filter(l=>project.can_manage||l.can_edit).map(l=><option key={l.id} value={l.id}>{l.label}</option>)}</select></Field>}
   {kind==='need'&&<><Field label="Категория потребности"><select value={values.category} onChange={e=>set('category',e.target.value)}>{needs.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></Field>{text('description','Что требуется')}<label className="comm-checkbox"><input type="checkbox" checked={values.blocking} onChange={e=>set('blocking',e.target.checked)}/>Блокирует наладку</label></>}
   {kind==='extra'&&<>{text('description','Описание допработы')}{input('price','Сумма, ₽','number')}</>}
   {kind==='request'&&input('label','Запрос на новый лифт')}
   {kind==='archive'&&<><p>Объект останется в архиве с историей работ. Изменения будут закрыты.</p>{text('reason','Причина архивации',1000)}</>}
  </fieldset>
  {kind==='expense'&&<small className="muted">Расход и чек доступны вам и руководителю. {locked?'Запрос уже отправлялся. Повтор проверит результат без создания копии.':''}</small>}
  {error&&<p className="error" role="alert">{error}</p>}
  <footer className="form-actions"><button type="button" disabled={busy} onClick={onClose}>Отмена</button><button className={kind==='archive'?'danger':'primary'} disabled={busy}>{busy?'Сохранение…':kind==='expense'&&locked?'Повторить сохранение':titles[kind]==='Новый объект наладки'?'Создать объект':kind==='archive'?'Архивировать':'Сохранить'}</button></footer>
 </form></Dialog>;
}
