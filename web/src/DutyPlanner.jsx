import React,{useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowUp,ArrowDown,Plus,GripVertical,X,RefreshCw,CheckCircle2,TriangleAlert} from 'lucide-react';
import {api,record} from './api';
import {Field} from './components';
import {bounds,dayLabel,addDay} from './planningShared';
import './planning.css';
export default function DutyPlanner({user,technicians,firstFuture,onPublished}){
 const [draft,setDraft]=useState(null),[revision,setRevision]=useState(0),[plan,setPlan]=useState(null),[stage,setStage]=useState('queue'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false),[legacy,setLegacy]=useState(0);
 const working=useRef(false),dragged=useRef(null),initialized=useRef(false);
 useEffect(()=>{const abort=new AbortController();api('duty/planner/',{signal:abort.signal}).then(data=>{
  if(abort.signal.aborted)return;let value=data.draft&&Object.keys(data.draft).length?data.draft:{from:firstFuture,to:bounds(firstFuture)[1],start_time:data.duty_start,mode:'daily',people:data.queue.filter(id=>technicians.some(t=>t.id===id)),overrides:{},replace_existing:false};
  if(!value.people.length)value.people=technicians.map(t=>t.id);
  if(value.to<firstFuture)value={...value,from:firstFuture,to:bounds(firstFuture)[1],overrides:{}};
  const params=new URLSearchParams(location.hash.split('?')[1]||'');if(params.get('from')&&params.get('to'))value={...value,from:params.get('from'),to:params.get('to'),replace_existing:true,overrides:{}};
  setDraft(value);setRevision(data.revision);setSaved(!data.draft?.published&&!!data.draft?.from);setLegacy(data.legacy_periods);initialized.current=true;
 }).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();},[user.organization_id]);
 const change=(key,value)=>{setDraft(d=>({...d,[key]:value,...(['from','to','mode','start_time','people'].includes(key)?{overrides:{}}:{})}));setPlan(null);setSaved(false);setNotice('');};
 const move=(index,by)=>{const people=[...draft.people],target=index+by;if(target<0||target>=people.length)return;[people[index],people[target]]=[people[target],people[index]];change('people',people);};
 async function action(kind,fn){if(working.current)return;working.current=true;setBusy(true);setError('');try{await fn();record('planning',kind,'ok');}catch(e){setError(e.message);record('planning',kind,e.status||'error');}finally{working.current=false;setBusy(false);}}
 const calculate=value=>action('preview',async()=>{const result=await api('duty/planner-preview/',{method:'POST',body:{draft:value||draft}});setPlan(result);setStage('preview');});
 const save=()=>action('draft',async()=>{const result=await api('duty/planner/',{method:'PUT',body:{draft,revision}});setRevision(result.revision);setSaved(true);setPlan(null);setNotice('Черновик сохранён. Сотрудники его пока не видят.');});
 const publish=()=>action('publish',async()=>{if(!plan||plan.missing)return;const result=await api('duty/planner-publish/',{method:'POST',body:{draft,token:plan.token}});setRevision(result.revision);setNotice(`График опубликован · новых смен ${result.added}, изменено ${result.updated}`);setPlan(null);setSaved(true);onPublished?.();});
 const name=id=>technicians.find(t=>t.id===id)?.full_name||'Недоступный сотрудник';
 const stamp=value=>new Date(value).toLocaleTimeString('ru-RU',{timeZone:user.timezone,hour:'2-digit',minute:'2-digit'});
 return <div className={'planning-page duty-planner plan-stage-'+stage}>
  <a href="#duty" className="plan-back"><ArrowLeft size={17}/>К графику</a>
  <header className="page-heading"><div><h1>Настроить дежурства</h1><p>Настройте очередь, проверьте даты и опубликуйте график</p></div><span className="plan-status">{saved?'Черновик сохранён':'Изменения не опубликованы'}</span></header>
  {error&&<p className="error" role="alert">{error} <button disabled={busy} onClick={()=>location.reload()}>Загрузить актуальные данные</button></p>}{notice&&<p className="plan-success" role="status">{notice}</p>}
  {!draft&&!error&&<p role="status">Загрузка настроек…</p>}
  {draft&&<><div className="plan-mobile-steps"><button aria-pressed={stage==='queue'} onClick={()=>setStage('queue')}>Очередь</button><button aria-pressed={stage==='preview'} onClick={()=>setStage('preview')}>Распределение</button></div>
  <div className="plan-columns"><section className="plan-setup plan-panel"><h2>1. Параметры смен</h2><fieldset disabled={busy}>
   <div className="plan-fields"><Field label="С даты"><input type="date" required value={draft.from} onChange={e=>change('from',e.target.value)}/></Field><Field label="По дату включительно"><input type="date" min={draft.from} required value={draft.to} onChange={e=>change('to',e.target.value)}/></Field></div>
   <div className="plan-fields"><Field label="Начало смены"><input type="time" required value={draft.start_time} onChange={e=>change('start_time',e.target.value)}/></Field><Field label="Режим смен"><select value={draft.mode} onChange={e=>change('mode',e.target.value)}><option value="daily">Сутки · 24 часа</option><option value="split">День и ночь · по 12 часов</option></select></Field></div>
   <p className="plan-hint">{draft.mode==='daily'?'Смена заканчивается на следующий день в то же время.':'Очередь переходит к следующему механику каждые 12 часов.'} Часовой пояс: {user.timezone}.</p>
   <h2>2. Очередь механиков</h2><p className="plan-hint">Перетащите строку или используйте стрелки</p>
   <ol className="plan-queue">{draft.people.map((id,index)=><li key={id} draggable={!busy} onDragStart={e=>{dragged.current=index;e.dataTransfer.effectAllowed='move';}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const source=dragged.current;if(source==null||source===index)return;const people=[...draft.people];people.splice(index,0,people.splice(source,1)[0]);change('people',people);dragged.current=null;}}><GripVertical className="plan-grip" size={16}/><span className="plan-rank">{index+1}</span><b>{name(id)}</b><button type="button" className="icon-button" aria-label={'Поднять '+name(id)} disabled={index===0} onClick={()=>move(index,-1)}><ArrowUp size={16}/></button><button type="button" className="icon-button" aria-label={'Опустить '+name(id)} disabled={index===draft.people.length-1} onClick={()=>move(index,1)}><ArrowDown size={16}/></button><button type="button" className="icon-button" aria-label={'Убрать из очереди '+name(id)} onClick={()=>change('people',draft.people.filter(p=>p!==id))}><X size={15}/></button></li>)}</ol>
   <Field label="Добавить механика"><select value="" onChange={e=>{if(e.target.value)change('people',[...draft.people,Number(e.target.value)]);}}><option value="">+ Выберите сотрудника</option>{technicians.filter(t=>!draft.people.includes(t.id)).map(t=><option key={t.id} value={t.id}>{t.full_name}</option>)}</select></Field>
   <Field label="Первый дежурный"><select value={draft.people[0]||''} onChange={e=>{const i=draft.people.indexOf(Number(e.target.value));change('people',[...draft.people.slice(i),...draft.people.slice(0,i)]);}}><option value="" disabled>Выберите очередь</option>{draft.people.map(id=><option key={id} value={id}>{name(id)}</option>)}</select></Field>
   <p className="plan-hint">Далее — по очереди. Отпуска проверим при распределении.</p>
   <label className="plan-check"><input type="checkbox" checked={draft.replace_existing} onChange={e=>change('replace_existing',e.target.checked)}/>Разрешить пересчёт опубликованных назначений</label>
   <p className="plan-hint">Смены с историей подмен, принятые и уже начавшиеся сохраняются. Все замены будут видны перед публикацией.</p>
   {legacy>0&&<p className="plan-hint">Прежние правила сохранены в базе. На выбранный период действует показанный здесь план после публикации.</p>}
  </fieldset><button className="primary plan-next" disabled={busy||!draft.people.length} onClick={()=>calculate()}>{busy?'Расчёт…':'Далее: распределение'}</button></section>
  <section className="plan-preview-panel plan-panel"><header className="plan-section-heading"><h2>3. Распределение по датам</h2><button disabled={busy||!draft.people.length} onClick={()=>calculate()}><RefreshCw size={16}/>Пересчитать</button></header>
   {!plan?<div className="plan-empty"><p>Проверьте очередь и нажмите «Пересчитать».</p><p>Опубликованные смены пока не меняются.</p></div>:<>
   <div className={'plan-summary '+(plan.missing?'warning':'')} role="status">{plan.missing?<><TriangleAlert size={18}/><span>Проверьте смены: {plan.missing}</span></>:<><CheckCircle2 size={18}/><span>Отпуска учтены · новых смен {plan.added}, замен {plan.updated}</span></>}</div>
   <div className="plan-shift-list">{plan.rows.map(row=><article className={'plan-shift '+(row.error?'has-error':row.replacement?'has-replacement':'')} key={row.key}><div><time>{dayLabel(row.date,{day:'numeric',month:'long',weekday:'short'})}</time><small>{row.kind==='day'?'День':row.kind==='night'?'Ночь':'Сутки'} · {stamp(row.start)} → {stamp(row.end)}{row.start.slice(0,10)!==row.end.slice(0,10)?' след. дня':''}</small></div><div className="plan-assignee"><b>{row.name||'Не назначен'}</b>{row.changed&&row.old_name&&<small>Было: {row.old_name}</small>}{row.note&&<small>{row.note}</small>}{row.error&&<small className="error">{row.error}</small>}</div>{!row.protected&&(!row.shift||draft.replace_existing)&&<select aria-label={'Дежурный '+row.key} value={row.technician||''} disabled={busy} onChange={e=>{const next={...draft,overrides:{...draft.overrides,[row.key]:Number(e.target.value)}};setDraft(next);setSaved(false);calculate(next);}}><option value="" disabled>Выбрать подмену</option>{technicians.map(t=><option key={t.id} value={t.id} disabled={row.unavailable.includes(t.id)}>{t.full_name}{row.unavailable.includes(t.id)?' · отпуск':''}</option>)}</select>}</article>)}</div>
   <div className="plan-distribution"><b>{plan.rows.length} смен · {draft.people.length} механиков</b><div>{plan.summary.map(p=><span key={p.id}>{p.name}<b>{p.count}</b></span>)}</div></div>
   {!plan.added&&!plan.updated&&!plan.missing&&<p className="plan-hint">Изменений для публикации нет. Если нужно заменить будущие назначения, разрешите пересчёт и проверьте план ещё раз.</p>}
   </>}
  </section></div>
  <footer className="plan-actionbar"><small>Сотрудники увидят изменения после публикации</small><button disabled={busy||!draft.people.length} onClick={save}>Сохранить черновик</button><button className="primary" disabled={busy||!plan||!!plan.missing||(!plan.added&&!plan.updated)} onClick={publish}>{busy?'Подождите…':'Опубликовать график'}</button></footer>
  </>}
 </div>;
}
