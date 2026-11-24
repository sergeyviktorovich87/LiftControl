import React,{useState} from 'react';
import {Field} from './components';
export default function StaffDirectory({technicians,elevators,canManage,onEdit,onArchive}){
 const [query,setQuery]=useState(''),[page,setPage]=useState(0);
 const filtered=technicians.filter(t=>[t.full_name,t.phone,t.role_display||t.role].filter(Boolean).join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')));
 const last=Math.max(0,Math.ceil(filtered.length/20)-1),current=Math.min(page,last);
 const counts=new Map();for(const lift of elevators)counts.set(lift.assigned_technician,(counts.get(lift.assigned_technician)||0)+1);
 return <section className="panel staff-directory"><Field label="Поиск сотрудника"><input type="search" value={query} placeholder="Имя, телефон или профессия" onChange={e=>{setQuery(e.target.value);setPage(0);}}/></Field>
 <p className="muted" role="status">Найдено: {filtered.length} · Показано {filtered.length?current*20+1:0}–{Math.min(filtered.length,(current+1)*20)}</p>
 <div className="staff-list">{filtered.slice(current*20,(current+1)*20).map(t=><div className="staff-row" key={t.id}><div><b>{t.full_name}</b><small>{t.role_display||t.role} · {t.active?'Работает':'Неактивен'} · Лифтов: {counts.get(t.id)||0}{t.phone&&<> · <a href={'tel:'+t.phone}>{t.phone}</a></>}</small></div>{canManage&&<div className="staff-row-actions"><button onClick={()=>onEdit(t)}>Изменить</button>{t.active&&<button className="danger" aria-label={'Удалить из списка: '+t.full_name} onClick={()=>onArchive(t)}>Удалить</button>}</div>}</div>)}</div>
 {!filtered.length&&<p>Сотрудники не найдены.</p>}
 {last>0&&<nav className="staff-pagination" aria-label="Страницы сотрудников"><button disabled={current===0} onClick={()=>setPage(current-1)}>Назад</button><span>{current+1} / {last+1}</span><button disabled={current===last} onClick={()=>setPage(current+1)}>Далее</button></nav>}
 </section>;
}
