import MessageReceipt from './MessageReceipt';
import DeliveryDetails from './DeliveryDetails';
import Nameplates from './Nameplates';
import CommissioningLiftDetail from './CommissioningLiftDetail';
import CommissioningIssues from './CommissioningIssues';
import CommissioningReport from './CommissioningReport';
import CommissioningForms from './CommissioningForms';
import {useCommissioningRoute,commissioningRoute} from './commissioningRoute';
import {useLiveRefresh} from './liveRefresh';
import {MAX_FILE_BYTES,MAX_MULTIPART_FILES} from './uploadLimits';
import React,{useEffect,useRef,useState} from 'react';
import {Plus,Search,ChevronRight,ArrowLeft,MessageSquare,Users,RefreshCw,CheckCircle2,TriangleAlert,Camera} from 'lucide-react';
import {api,record} from './api';
import {Dialog,Field} from './components';
import {prepareImages} from './imageCompression';
import './commissioning.css';
const tabs=[['lifts','Лифты'],['work','По объекту'],['expenses','Расходы'],['nameplates','Шильдики'],['history','История']];
const forms=new Set(['project','lift','expense','need','extra','request','archive']);
const latest=lift=>[...(lift.history||[])].sort((a,b)=>+new Date(b.created_at)-+new Date(a.created_at))[0];
const percent=value=>Math.max(0,Math.min(100,Number(value)||0));
const amount=value=>Number(value||0).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function Meter({value,label}){return <div className="comm-meter" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent(value)}><span style={{width:percent(value)+'%'}}/></div>;}
function Photos({photos=[]}){return photos.length>0&&<div className="comm-photos">{photos.map((photo,i)=><a key={photo.id||i} href={photo.url} target="_blank" rel="noreferrer"><img src={photo.preview_url||photo.url} alt={'Фото работы '+(i+1)} loading="lazy"/></a>)}</div>;}
function Empty({children}){return <p className="comm-empty">{children}</p>;}
export default function Commissioning({user,initialProject,onProjectOpened,onOpenChat,chatCount=0}){
 const [route,go,close]=useCommissioningRoute();
 const [projects,setProjects]=useState([]),[selected,setSelected]=useState(null),[loaded,setLoaded]=useState(false),[opening,setOpening]=useState(false);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[query,setQuery]=useState(''),[liftQuery,setLiftQuery]=useState(''),[archive,setArchive]=useState(false);
 const [members,setMembers]=useState([]),[membersError,setMembersError]=useState(''),[assignment,setAssignment]=useState({}),[,renderDrafts]=useState(0);
 const activeRequest=useRef(0),working=useRef(false),drafts=useRef(new Map()),lastLift=useRef(new Map()),expenses=useRef(new Map());
 const canManage=selected?.can_manage??user.can_manage_access;
 const project=selected?.id===route.project?selected:null;
 const lifts=project?.lifts||[],editable=lifts.filter(l=>l.can_edit),chosen=lifts.find(l=>l.id===(route.lift||lastLift.current.get(project?.id)))||lifts[0];
 const locked=!!project?.archived;
 const date=value=>new Date(value).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'});
 const base=id=>'/project/'+id;
 const tabPath=(tab=route.tab)=>project?base(project.id)+(tab==='lifts'?'':'/tab/'+tab):'';
 const newAction=kind=>{setError('');go(tabPath()+'/action/'+kind);};
 const backFromAction=()=>{if(!working.current){setError('');close(route.lift?base(route.project)+'/lift/'+route.lift:route.project?base(route.project)+(route.tab==='lifts'?'':'/tab/'+route.tab):'');}};
 useEffect(()=>{const abort=new AbortController();setLoaded(false);setProjects([]);api('commissioning/',{signal:abort.signal}).then(rows=>{if(!abort.signal.aborted){setProjects(rows);setLoaded(true);}}).catch(e=>{if(!abort.signal.aborted){setError(e.message);setLoaded(true);}});return()=>abort.abort();},[user.organization_id]);
 useEffect(()=>{if(initialProject){go(base(initialProject),true);onProjectOpened?.();}},[initialProject,user.organization_id]);
 useEffect(()=>{
  const abort=new AbortController(),serial=++activeRequest.current;setError('');setLiftQuery('');
  if(!route.project){setSelected(null);setOpening(false);return()=>abort.abort();}
  setOpening(true);setSelected(null);
  api('commissioning/'+route.project+'/',{signal:abort.signal}).then(value=>{if(!abort.signal.aborted&&serial===activeRequest.current){setSelected(value);setOpening(false);}}).catch(e=>{if(!abort.signal.aborted){setError(e.message);setOpening(false);}});
  return()=>abort.abort();
 },[route.project,user.organization_id]);
 useEffect(()=>{window.scrollTo({top:0});},[route.project,route.lift,route.tab]);
 async function refresh(signal){
  const id=commissioningRoute().project;
  const [list,detail]=await Promise.all([api('commissioning/',{signal}),id?api('commissioning/'+id+'/',{signal}):null]);
  if(signal?.aborted)return;
  setProjects(list);setLoaded(true);if(detail&&commissioningRoute().project===detail.id)setSelected(detail);
 }
 useLiveRefresh(signal=>working.current||route.action?null:refresh(signal),user.organization_id+':'+route.project,true,15000);
 async function run(kind,action,after){
  if(working.current)return false;working.current=true;setBusy(true);setError('');
  try{const result=await action();await refresh();record('commissioning',kind,'ok');after?.(result);return true;}
  catch(e){setError(e.message||String(e));record('commissioning',kind,e.status||'error');return false;}
  finally{working.current=false;setBusy(false);}
 }
 const post=(path,body)=>api(path,{method:'POST',body});
 async function loadMembers(){setMembersError('');try{setMembers(await api('commissioning/assignees/'));}catch(e){setMembersError(e.message);}}
 const participants=()=>{newAction('members');loadMembers();};
 const openLift=lift=>{lastLift.current.set(project.id,lift.id);go(base(project.id)+'/lift/'+lift.id);};
 const startReport=lift=>{
  if(!lift?.can_edit||locked)return;
  const key=project.id+':'+lift.id;
  if(!drafts.current.has(key))drafts.current.set(key,{progress:lift.progress,baseProgress:lift.progress,revision:lift.revision,description:'',photos:[]});
  setError('');if(route.lift!==lift.id)go(base(project.id)+'/lift/'+lift.id);go(base(project.id)+'/lift/'+lift.id+'/action/report');
 };
 const reportLift=route.action==='report'?lifts.find(l=>l.id===route.lift):null;
 const reportKey=project?.id+':'+reportLift?.id;
 const draft=reportLift?(drafts.current.get(reportKey)||{progress:reportLift.progress,baseProgress:reportLift.progress,revision:reportLift.revision,description:'',photos:[]}):null;
 const updateDraft=value=>{drafts.current.set(reportKey,value);renderDrafts(n=>n+1);};
 const saveReport=()=>run('report',async()=>{
  if(!reportLift?.can_edit||locked)throw Error('Нет права изменять этот лифт.');
  const fields={progress:Number(draft.progress),revision:draft.revision,description:draft.description.trim()},photos=draft.photos||[];
  if(photos.length>MAX_MULTIPART_FILES||photos.some(f=>f.size>MAX_FILE_BYTES))throw Error('До 5 фотографий по 100 МБ.');
  let body=fields;
  if(photos.length){const images=await prepareImages(photos);body=new FormData();for(const [key,value]of Object.entries(fields))body.append(key,value);images.forEach(file=>body.append('photos',file));}
  await post(`commissioning/${project.id}/lifts/${reportLift.id}/progress/`,body);
 },()=>{drafts.current.delete(reportKey);setNotice('Отчёт сохранён');if(commissioningRoute().action==='report')close(base(project.id)+'/lift/'+reportLift.id);});
 const reloadReport=async()=>{if(busy)return;setBusy(true);try{const detail=await api('commissioning/'+project.id+'/'),fresh=detail.lifts.find(l=>l.id===reportLift.id);setSelected(detail);if(fresh?.can_edit){updateDraft({...draft,baseProgress:fresh.progress,revision:fresh.revision});setError('');}else setError('Назначение изменилось. Отчёт доступен только вашему лифту.');}catch(e){setError(e.message);}finally{setBusy(false);}};
 const history=lifts.flatMap(l=>(l.history||[]).map(h=>({...h,lift:l.label,liftId:l.id}))).sort((a,b)=>+new Date(b.created_at)-+new Date(a.created_at));
 const chat=<>{onOpenChat&&<button type="button" onClick={onOpenChat}><MessageSquare size={17}/>Чат наладчиков{chatCount>0&&<span className="unread-count">{chatCount>99?'99+':chatCount}</span>}</button>}</>;
 const activeForms=route.action&&forms.has(route.action);
 const writable=route.action==='project'?!!user.can_manage_access:!!project&&!locked&&(['lift','archive'].includes(route.action)?canManage:route.action==='expense'?!canManage:true);
 if(route.action==='expense'&&project&&!expenses.current.has(project.id))expenses.current.set(project.id,{});
 const changeTab=tab=>{setError('');go(base(project.id)+(tab==='lifts'?'':'/tab/'+tab));};
 const liftAction=(lift,kind)=>{setError('');lastLift.current.set(project.id,lift.id);go(base(project.id)+'/lift/'+lift.id+'/action/'+kind);};
 const resolveNeed=id=>run('need-resolve',()=>post(`commissioning/${project.id}/needs/${id}/resolve/`,{}));
 const decideExtra=(id,approve)=>run(approve?'extra-approve':'extra-reject',()=>post(`commissioning/${project.id}/extra-work/${id}/decision/`,{approve}));
 const reportView=lift=><CommissioningLiftDetail user={user} project={project} lift={lift} canManage={canManage} locked={locked} busy={busy} date={date} onReport={()=>startReport(lift)} onAction={kind=>liftAction(lift,kind)} onResolve={resolveNeed} onDecision={decideExtra}/>;
 return <div className={'commissioning comm-workspace '+(route.action?'comm-dialog-open ':'')+(route.action==='report'?'comm-report-open':'')}>
  {notice&&<p role="status" className="comm-notice">{notice}</p>}{error&&(!route.action||!project&&route.action!=='project')&&<p className="error" role="alert">{error}</p>}
  {!route.project&&<>
   <header className="page-heading"><div><span className="eyebrow">ПУСКОНАЛАДКА</span><h1>Объекты наладки</h1><p>Выберите объект и продолжите работу</p></div><div className="actions">{chat}{user.can_manage_access&&<button className="primary" onClick={()=>newAction('project')}><Plus size={17}/>Добавить объект</button>}</div></header>
   <div className="comm-toolbar"><label className="comm-search"><Search size={18}/><input type="search" aria-label="Поиск объекта наладки" placeholder="Название или адрес" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="comm-checkbox"><input type="checkbox" checked={archive} onChange={e=>setArchive(e.target.checked)}/>Показывать архив</label><button className="icon-button" aria-label="Обновить объекты" disabled={busy} onClick={()=>run('refresh',()=>refresh())}><RefreshCw size={18}/></button></div>
   {!loaded?<p role="status">Загрузка объектов…</p>:<div className="comm-projects">{projects.filter(p=>(archive||!p.archived)&&[p.name,p.address].join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'))).map(p=><button className="comm-project-row" key={p.id} onClick={()=>go(base(p.id))}><span><b>{p.name}</b><small>{p.address}</small><small>{p.lift_count} лифтов{p.archived?' · Архив':''}</small></span><span className="comm-project-progress"><b>{p.progress}%</b><Meter value={p.progress} label={'Готовность '+p.name}/></span><ChevronRight size={18}/></button>)}</div>}
   {loaded&&!projects.some(p=>(archive||!p.archived)&&[p.name,p.address].join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')))&&<Empty>Объекты не найдены. Проверьте поиск и доступ к организации.</Empty>}
  </>}
  {route.project&&<><button className="comm-back" onClick={()=>go('')}><ArrowLeft size={17}/>Все объекты</button>{opening&&<p role="status">Загрузка объекта…</p>}{project&&<>
   <header className="comm-project-heading"><div><span className="eyebrow">ПУСКОНАЛАДКА</span><h1>{project.name}</h1><p>{project.address}</p></div><div className="actions">{canManage&&<button onClick={participants}><Users size={17}/>Участники</button>}{chat}<button className="icon-button" aria-label="Обновить объект" disabled={busy} onClick={()=>run('refresh',()=>refresh())}><RefreshCw size={18}/></button></div></header>
   <DeliveryDetails target="commissioning" id={project.id} user={user} label="Доставка событий объекта"/><div className="comm-object-progress"><b>Готовность объекта {project.progress}%</b><span>{lifts.length} лифтов</span><Meter value={project.progress} label="Готовность объекта"/></div>
   {locked&&<p className="notice">Архив: изменения запрещены, история сохранена.</p>}
   <div className="comm-tabs" role="tablist" aria-label="Разделы объекта">{tabs.map(([id,title])=><button key={id} type="button" role="tab" aria-label={title} aria-selected={route.tab===id} onClick={()=>changeTab(id)}>{title}{id==='work'&&project.needs.some(n=>!n.lift&&n.blocking&&!n.resolved)&&<span aria-label="Есть препятствия" className="comm-alert-dot"/>}</button>)}</div>
   {route.tab==='lifts'&&<div className={'comm-lifts-layout '+(route.lift?'comm-show-detail':'')}>
    <section className="comm-lift-list"><div className="comm-toolbar"><label className="comm-search"><Search size={17}/><input type="search" aria-label="Найти лифт наладки" placeholder="Найти лифт" value={liftQuery} onChange={e=>setLiftQuery(e.target.value)}/></label>{!locked&&<button onClick={()=>newAction(canManage?'lift':'request')}><Plus size={16}/>{canManage?'Добавить лифт':'Запросить лифт'}</button>}</div>
     {lifts.filter(l=>[l.label,l.factory_number,...l.assignees.map(a=>a.name)].join(' ').toLocaleLowerCase('ru').includes(liftQuery.trim().toLocaleLowerCase('ru'))).map(l=>{const last=latest(l);return <button key={l.id} className={'comm-lift-row '+(chosen?.id===l.id?'selected':'')} onClick={()=>openLift(l)}><span className="comm-lift-icon">↕</span><span className="comm-lift-copy"><b>{l.label}{l.can_edit&&<em>Ваш лифт</em>}</b><small>{l.assignees.map(a=>a.name).join(', ')||'Исполнитель не назначен'}</small><span>{last?.description||'Отчётов пока нет'}</span><Meter value={l.progress} label={'Готовность '+l.label}/></span><span className="comm-lift-percent">{l.progress}%{project.needs.some(n=>!n.resolved&&n.blocking&&(n.lift===l.id||!n.lift))&&<TriangleAlert size={15} className="comm-row-warning" aria-label="Есть препятствия"/>}{l.progress===100&&<CheckCircle2 size={15}/>}</span><ChevronRight size={17}/></button>;})}
     {!lifts.length&&<Empty>Лифты ещё не добавлены.</Empty>}
     {!locked&&!canManage&&editable.length>0&&<div className="comm-mobile-action"><button className="primary" onClick={()=>startReport(editable[0])}><Plus size={18}/>Добавить отчёт</button></div>}
     {project.lift_requests.some(r=>r.status==='PENDING')&&<div className="comm-request-summary"><button onClick={()=>newAction('requests')}>Запросы новых лифтов · {project.lift_requests.filter(r=>r.status==='PENDING').length}</button></div>}
    </section>
    <aside className="comm-lift-detail"><button className="comm-mobile-back comm-back" onClick={()=>go(base(project.id))}><ArrowLeft size={17}/>К списку лифтов</button>{chosen?reportView(chosen):<Empty>Выберите лифт.</Empty>}</aside>
   </div>}
   {route.tab==='work'&&<section className="comm-section comm-project-issues"><header className="comm-section-heading"><div><h2>Общие вопросы объекта</h2><p>Здесь записи для всего объекта, в том числе ранее созданные без привязки. Препятствия конкретного лифта — внутри его карточки.</p></div></header><CommissioningIssues user={user} needs={project.needs.filter(n=>!n.lift)} extras={project.extras.filter(w=>!w.lift)} canManage={canManage} canAdd={!locked} locked={locked} busy={busy} onAction={newAction} onResolve={resolveNeed} onDecision={decideExtra}/></section>}
   {route.tab==='expenses'&&<section className="comm-section"><header className="comm-section-heading"><div><h2>{canManage?'Расходы наладчиков':'Мои личные расходы'}</h2><p>Личные расходы и чеки доступны автору и руководителю.</p></div>{!canManage&&!locked&&<button className="primary" onClick={()=>newAction('expense')}><Plus size={17}/>Записать расход</button>}</header>{project.expenses.map(e=><MessageReceipt as="article" className="comm-record" key={e.id} user={user} target="commissioning_action" ids={e.receipt_events||[]}><div><b>{amount(e.amount)} · {e.description}</b><small>{e.author} · {e.spent_on||date(e.created_at)} · {e.reimbursed_at?'Возмещён':'Ожидает возмещения'}</small></div><div className="actions">{e.has_receipt&&<a className="button" href={`/api/commissioning/${project.id}/expenses/${e.id}/receipt/?organization=${user.organization_id}`} target="_blank" rel="noreferrer">Чек</a>}{canManage&&!e.reimbursed_at&&!locked&&<button disabled={busy} onClick={()=>run('reimburse',()=>post(`commissioning/${project.id}/expenses/${e.id}/reimburse/`,{}))}>Возместить</button>}</div></MessageReceipt>)}{!project.expenses.length&&<Empty>Расходов пока нет.</Empty>}</section>}
   {route.tab==='nameplates'&&<section className="comm-section"><Field label="Лифт для шильдиков"><select value={(lifts.find(l=>l.id===route.lift&&l.can_view_nameplates)||lifts.find(l=>l.id===lastLift.current.get(project.id)&&l.can_view_nameplates)||lifts.find(l=>l.can_view_nameplates))?.id||''} onChange={e=>{lastLift.current.set(project.id,Number(e.target.value));renderDrafts(n=>n+1);}}>{lifts.filter(l=>l.can_view_nameplates).map(l=><option key={l.id} value={l.id}>{l.label}</option>)}</select></Field>{(()=>{const lift=lifts.find(l=>l.id===lastLift.current.get(project.id)&&l.can_view_nameplates)||lifts.find(l=>l.can_view_nameplates);return lift?<Nameplates key={project.id+':'+lift.id} project={project.id} lift={lift} archived={locked}/>:<Empty>Шильдики доступны по назначенным лифтам.</Empty>;})()}</section>}
   {route.tab==='history'&&<section className="comm-section"><h2>История работ</h2>{history.map(h=><article className="comm-history-row" key={h.liftId+':'+h.id}><header><b>{h.lift}</b><span className="comm-change">{h.before}% → {h.after}%</span></header><small>{date(h.created_at)} · {h.author}</small><p>{h.description}</p><Photos photos={h.photos}/></article>)}{!history.length&&<Empty>Отчётов пока нет.</Empty>}</section>}
   {canManage&&!locked&&<div className="comm-project-footer"><button className="comm-quiet-danger" onClick={()=>newAction('archive')}>Архивировать объект</button></div>}
  </>}</>}
  {route.action==='report'&&project&&(reportLift?.can_edit&&!locked?<CommissioningReport project={project} lift={reportLift} draft={draft} onDraft={updateDraft} onSave={saveReport} onClose={backFromAction} onReload={reloadReport} busy={busy} error={error}/>:<Dialog title="Отчёт недоступен" onClose={backFromAction}><p>Добавлять отчёт можно только по своему действующему назначению.</p></Dialog>)}
  {activeForms&&writable&&<CommissioningForms key={route.action+':'+project?.id+':'+route.lift} kind={route.action} project={project} user={user} initialLift={route.lift} busy={busy} error={error} pending={route.action==='expense'?expenses.current.get(project.id):undefined} onClose={backFromAction} onSubmit={action=>run(route.action,()=>action(post),result=>{if(route.action==='expense')expenses.current.delete(project.id);if(route.action==='project')go(base(result.id),true);else if(commissioningRoute().action===route.action)close(route.lift?base(project.id)+'/lift/'+route.lift:tabPath());setNotice('Изменения сохранены');})}/>}
  {activeForms&&!writable&&!opening&&<Dialog title="Изменения недоступны" onClose={backFromAction}><p>Проверьте права доступа и состояние объекта.</p></Dialog>}
  {route.action==='members'&&project&&canManage&&<Dialog title="Участники объекта" onClose={backFromAction} wide><div className="comm-members">{membersError&&<p className="error" role="alert">{membersError}<button onClick={loadMembers}>Повторить</button></p>}{error&&<p className="error" role="alert">{error}</p>}{lifts.map(l=>{const available=members.filter(m=>!m.can_commissioning||!l.assignees.some(a=>a.user===m.user)),member=available.find(m=>String(m.user)===assignment[l.id]);return <section key={l.id}><h3>{l.label}</h3>{l.assignees.map(a=><div className="comm-record" key={a.user}><span>{a.name}</span>{!locked&&<button disabled={busy} onClick={()=>run('unassign',()=>post(`commissioning/${project.id}/lifts/${l.id}/assign/`,{user:a.user,active:false}))}>Снять назначение</button>}</div>)}{!locked&&<div className="comm-assignment"><select aria-label={'Исполнитель · '+l.label} value={assignment[l.id]||''} disabled={busy} onChange={e=>setAssignment(prev=>({...prev,[l.id]:e.target.value}))}><option value="">Выберите исполнителя</option>{available.map(m=><option key={m.user} value={m.user}>{m.name}{!m.can_commissioning?' · без роли наладчика':''}</option>)}</select><button disabled={busy||!member} onClick={()=>run('assign',()=>post(`commissioning/${project.id}/lifts/${l.id}/assign/`,{user:member.user,grant_commissioning:!member.can_commissioning}),()=>{setAssignment(prev=>({...prev,[l.id]:''}));loadMembers();})}>{member&&!member.can_commissioning?'Выдать роль и назначить':'Назначить'}</button></div>}</section>;})}</div></Dialog>}
  {route.action==='requests'&&project&&<Dialog title="Запросы новых лифтов" onClose={backFromAction}><div className="comm-requests">{project.lift_requests.map(r=><MessageReceipt as="article" className="comm-record" key={r.id} user={user} target="commissioning_action" ids={r.receipt_events||[]}><div><b>{r.label}</b><small>{{PENDING:'Ожидает решения',APPROVED:'Одобрен',REJECTED:'Отклонён'}[r.status]||r.status}</small></div>{canManage&&r.status==='PENDING'&&!locked&&<div className="actions"><button disabled={busy} onClick={()=>run('lift-approve',()=>post(`commissioning/${project.id}/lift-requests/${r.id}/decision/`,{approve:true}))}>Одобрить</button><button disabled={busy} onClick={()=>run('lift-reject',()=>post(`commissioning/${project.id}/lift-requests/${r.id}/decision/`,{approve:false}))}>Отклонить</button></div>}</MessageReceipt>)}{error&&<p className="error" role="alert">{error}</p>}</div></Dialog>}
 </div>;
}
