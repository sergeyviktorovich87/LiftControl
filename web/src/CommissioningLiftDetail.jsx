import MessageReceipt from './MessageReceipt';
import React from 'react';
import {Plus,TriangleAlert,CheckCircle2} from 'lucide-react';
import CommissioningIssues from './CommissioningIssues';
function Photos({photos=[]}){return photos.length>0&&<div className="comm-photos">{photos.map((photo,i)=><a key={photo.id||i} href={photo.url} target="_blank" rel="noreferrer"><img src={photo.preview_url||photo.url} alt={'Фото работы '+(i+1)} loading="lazy"/></a>)}</div>;}
function Report({item,date,user}){return <MessageReceipt user={user} target="commissioning_progress" id={item.id} own={false}><small>{date(item.created_at)} · {item.author}</small><p>{item.description}</p><b className="comm-change">{item.before}% → {item.after}%</b><Photos photos={item.photos}/></MessageReceipt>;}
export default function CommissioningLiftDetail({user,project,lift,canManage,locked,busy,date,onReport,onAction,onResolve,onDecision}){
 const history=[...(lift.history||[])].sort((a,b)=>+new Date(b.created_at)-+new Date(a.created_at)),last=history[0];
 const needs=project.needs.filter(n=>n.lift===lift.id),extras=project.extras.filter(w=>w.lift===lift.id),general=project.needs.filter(n=>!n.lift),generalExtras=project.extras.filter(w=>!w.lift);
 const blocked=[...needs,...general].some(n=>n.blocking&&!n.resolved);
 const progress=Math.max(0,Math.min(100,Number(lift.progress)||0));
 const shared={user,canManage,locked,busy,onResolve,onDecision};
 return <div className="comm-lift-card">
  <header className="comm-lift-heading"><div><span className="eyebrow">КАРТОЧКА ЛИФТА</span><h2>{lift.label}</h2><p>Зав. № {lift.factory_number||'не указан'}</p><p>Наладчик · {lift.assignees.map(a=>a.name).join(', ')||'Не назначен'}</p></div><span className={'comm-lift-state '+(blocked?'is-blocked':'')}>{blocked?<TriangleAlert size={16}/>:<CheckCircle2 size={16}/ >}{blocked?'Есть препятствия':progress===100?'Работы выполнены':'В работе'}</span></header>
  {!canManage&&!lift.can_edit&&<p className="notice">Только просмотр. Изменения вносит назначенный наладчик.</p>}
  <div className="comm-readiness"><div><span>Готовность лифта</span><b>{progress}<small>%</small></b></div><div className="comm-meter" role="progressbar" aria-label={'Готовность '+lift.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{width:progress+'%'}}/></div><small>{blocked?'Прогресс сохранён. Для продолжения нужно устранить препятствия.':last?'Обновлено '+date(last.created_at):'Первый отчёт появится после начала работ.'}</small></div>
  <div className="comm-lift-panels">
   <section className="comm-execution" aria-label="Выполнение работ"><header className="comm-section-heading"><div><h3>Выполнение</h3><p>Что сделано и как менялась готовность.</p></div>{lift.can_edit&&!locked&&<button className="primary" onClick={onReport}><Plus size={16}/>Добавить отчёт</button>}</header>
    {last?<article className="comm-latest"><h4>Последний отчёт</h4><Report item={last} date={date} user={user}/></article>:<p className="comm-inline-empty">Отчётов пока нет. Добавьте результат работы и новый процент готовности.</p>}
    {history.length>1&&<details className="comm-fold comm-lift-history"><summary>Предыдущие отчёты · {history.length-1}</summary>{history.slice(1).map(item=><article key={item.id}><Report item={item} date={date} user={user}/></article>)}</details>}
   </section>
   <section className={'comm-lift-obstacles '+(blocked?'has-obstacles':'')} aria-label="Препятствия лифта"><CommissioningIssues {...shared} needs={needs} extras={extras} canAdd={!locked&&(canManage||lift.can_edit)} onAction={onAction}/>
    {(general.length>0||generalExtras.length>0)&&<details className="comm-fold comm-general-issues" open={general.some(n=>n.blocking&&!n.resolved)}><summary>Общие вопросы объекта{general.some(n=>n.blocking&&!n.resolved)&&<TriangleAlert size={15}/>}</summary><p className="muted">Относятся ко всему объекту. Старые записи без выбранного лифта сохранены здесь.</p><CommissioningIssues {...shared} needs={general} extras={generalExtras} canAdd={false} compact/></details>}
   </section>
  </div>
 </div>;
}
