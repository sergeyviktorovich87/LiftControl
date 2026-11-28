import React,{useState} from 'react';
import {ShieldCheck} from 'lucide-react';
import {api,record} from './api';
import './duty-assignment.css';
export function AssignmentOptions({value,onChange,disabled=false}){
 return <fieldset className="assignment-options" disabled={disabled}><legend>Кому назначать новые заявки</legend>{[['LIFT','По закреплённым лифтам','Каждому механику — его участок'],['DUTY','Все заявки дежурному','На эту смену, независимо от участка']].map(([mode,title,description])=><label key={mode} className={value===mode?'is-selected':''}><input type="radio" name="assignment-mode" value={mode} checked={value===mode} onChange={()=>onChange(mode)}/><span><b>{title}</b><small>{description}</small></span></label>)}</fieldset>;
}
export default function DutyAssignment({shift,user,onSaved}){
 const [mode,setMode]=useState(shift.assignment_mode||'LIFT'),[stamp,setStamp]=useState(shift.updated_at),[saved,setSaved]=useState(shift.assignment_mode||'LIFT'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[stale,setStale]=useState(false);
 const save=async e=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{const result=await api(`duty/${shift.id}/assignment/`,{organization:user.organization_id,method:'POST',body:{assignment_mode:mode,expected_updated_at:stamp}});setStamp(result.updated_at);setSaved(result.assignment_mode);record('duty','assignment','ok');await onSaved();}catch(e){setStale(e.status===409);record('duty','assignment',e.status||'error');setError(e.message);}finally{setBusy(false);}};
 return <form className="duty-assignment" aria-label="Распределение заявок на смену" onSubmit={save}><AssignmentOptions value={mode} onChange={setMode} disabled={busy}/><p className="assignment-summary">{mode==='DUTY'?`Новые заявки получит ${shift.technician_name}.`:'Новые заявки будут распределяться по обычным правилам.'}<small>Уже назначенные заявки останутся у исполнителей.</small></p><footer><small>Режим действует до конца смены.</small><button type="button" disabled={busy||mode===saved} onClick={()=>{setMode(saved);setError('');}}>Отмена</button><button className="primary" disabled={busy||mode===saved}>{busy?'Сохранение…':'Сохранить смену'}</button></footer>{error&&<p role="alert" className="error">{error}</p>}{stale&&<button type="button" disabled={busy} onClick={async()=>{setBusy(true);try{const row=await api(`duty/${shift.id}/`,{organization:user.organization_id});setStamp(row.updated_at);setMode(row.assignment_mode);setSaved(row.assignment_mode);setError('');setStale(false);}catch(e){setError(e.message);}finally{setBusy(false);}}}>Обновить настройку</button>}</form>;
}
export function DutyAssignmentBanner({user}){
 const shift=user.duty_shift;
 if(shift?.assignment_mode!=='DUTY')return null;
 return <section className="assignment-banner" aria-label="Распределение заявок"><ShieldCheck size={28}/><div><b>{user.on_duty&&shift.technician===user.technician?'Все новые заявки — вам':'Все новые заявки — дежурному'}</b><p>{shift.technician_name} · До {new Date(shift.end).toLocaleString('ru-RU',{timeZone:user.timezone,day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</p></div></section>;
}
