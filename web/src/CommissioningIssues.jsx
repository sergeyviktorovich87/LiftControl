import MessageReceipt from './MessageReceipt';
import React from 'react';
import {Plus,TriangleAlert,CheckCircle2} from 'lucide-react';
import {needNames} from './CommissioningForms';
const amount=value=>Number(value||0).toLocaleString('ru-RU',{style:'currency',currency:'RUB'});
function Need({user,item,canManage,locked,busy,onResolve}){
 return <MessageReceipt as="article" user={user} target="commissioning_action" ids={item.receipt_events||[]} className={'comm-record comm-issue '+(item.blocking&&!item.resolved?'comm-blocking':'')}><div><b>{item.blocking&&!item.resolved?<TriangleAlert size={16}/>:item.resolved?<CheckCircle2 size={16}/>:null}{needNames[item.category]||item.category}</b><p>{item.description}</p><small>{item.resolved?'Решено':item.blocking?'Наладка заблокирована':'Ожидает решения'}</small></div>{canManage&&!item.resolved&&!locked&&<button disabled={busy} onClick={()=>onResolve(item.id)}>Отметить решённым</button>}</MessageReceipt>;
}
export default function CommissioningIssues({user,needs=[],extras=[],canManage,canAdd,locked,busy,onAction,onResolve,onDecision,compact=false}){
 const open=needs.filter(n=>!n.resolved).sort((a,b)=>Number(b.blocking)-Number(a.blocking)),closed=needs.filter(n=>n.resolved);
 return <div className={'comm-issues '+(compact?'comm-issues-compact':'')}>
  <header className="comm-section-heading"><div><h3>Что мешает работе{open.length>0&&<span className="comm-count">{open.length}</span>}</h3><p>Препятствия и всё, что нужно для продолжения.</p></div>{canAdd&&<button onClick={()=>onAction('need')}><Plus size={16}/>Добавить препятствие</button>}</header>
  {open.map(item=><Need key={item.id} {...{user,item,canManage,locked,busy,onResolve}}/>)}
  {!open.length&&<div className="comm-clear-state"><CheckCircle2 size={20}/><div><b>Открытых препятствий нет</b><small>Добавленные вопросы появятся здесь.</small></div></div>}
  {closed.length>0&&<details className="comm-fold"><summary>Решённые вопросы · {closed.length}</summary>{closed.map(item=><Need key={item.id} {...{user,item,canManage,locked,busy,onResolve}}/>)}</details>}
  <details className="comm-fold comm-extra-fold"><summary>Дополнительные работы <span>{extras.length?`· ${extras.length}`:''}{extras.some(w=>w.status==='PENDING')?' · На согласовании':''}</span></summary><p className="muted">Работы сверх основного объёма, их стоимость и согласование.</p>{canAdd&&<button onClick={()=>onAction('extra')}><Plus size={16}/>Предложить работу</button>}{extras.map(w=><MessageReceipt as="article" className="comm-record" key={w.id} user={user} target="commissioning_action" ids={w.receipt_events||[]}><div><b>{w.description}</b><small>{amount(w.price)} · {{PENDING:'Ожидает согласования',APPROVED:'Согласовано',REJECTED:'Отклонено'}[w.status]||w.status}</small></div>{canManage&&w.status==='PENDING'&&!locked&&<div className="actions"><button disabled={busy} onClick={()=>onDecision(w.id,true)}>Согласовать</button><button disabled={busy} onClick={()=>onDecision(w.id,false)}>Отклонить</button></div>}</MessageReceipt>)}{!extras.length&&<p className="comm-inline-empty">Дополнительных работ пока нет.</p>}</details>
 </div>;
}
