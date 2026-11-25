import React,{useMemo,useState} from 'react';
import {Plus,Search,ChevronRight,RefreshCw} from 'lucide-react';
import {Badge} from './components';
import {entranceLabel} from './LiftDocuments';
import './home.css';
const active=ticket=>!['DONE','CANCELED'].includes(ticket.status);
const priority={ENTRAPMENT:0,EMERGENCY:1,HIGH:2,NORMAL:3,LOW:4};
export default function HomeTickets({user,data,onOpen,onCreate,onRefresh,onAll,refreshing=false}){
 const [filter,setFilter]=useState('all'),[query,setQuery]=useState(''),[page,setPage]=useState(0);
 const canMine=user.role==='MECHANIC'&&!!user.technician;
 const currentFilter=filter==='mine'&&!canMine?'all':filter;
 const technicians=useMemo(()=>new Map(data.technicians.map(t=>[t.id,t.full_name])),[data.technicians]);
 const elevators=useMemo(()=>new Map(data.elevators.map(l=>[l.id,l])),[data.elevators]);
 const tickets=useMemo(()=>data.tickets.filter(ticket=>{
  if(!active(ticket))return false;
  if(currentFilter==='new'&&ticket.status!=='NEW')return false;
  if(currentFilter==='progress'&&!['IN_PROGRESS','STOPPED','LONG_REPAIR'].includes(ticket.status))return false;
  const lift=elevators.get(ticket.elevator);
  if(currentFilter==='mine'&&Number(ticket.assigned_to||lift?.assigned_technician)!==Number(user.technician))return false;
  const text=[ticket.id,ticket.title,ticket.address,ticket.elevator_label,ticket.elevator_factory_number,lift?.entrance,technicians.get(ticket.assigned_to)].filter(v=>v!==undefined&&v!==null).join(' ').toLocaleLowerCase('ru');
  return text.includes(query.trim().toLocaleLowerCase('ru'));
 }).sort((a,b)=>{
  const urgency=(priority[a.priority]??3)-(priority[b.priority]??3);
  return urgency||Number(b.status==='NEW')-Number(a.status==='NEW')||new Date(b.created_at)-new Date(a.created_at)||b.id-a.id;
 }),[data.tickets,currentFilter,query,elevators,technicians,user.technician]);
 const last=Math.max(0,Math.ceil(tickets.length/25)-1),currentPage=Math.min(page,last),rows=tickets.slice(currentPage*25,(currentPage+1)*25);
 const date=value=>new Date(value).toLocaleString('ru-RU',{timeZone:user.timezone||'Asia/Chita',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
 return <section className="home-workspace">
  <div className="page-heading home-heading"><div><span className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>Главная</h1><p>Заявки и текущая работа</p></div><div className="actions">{user.can_create_ticket&&<button type="button" className="primary" onClick={onCreate}><Plus size={18}/>Новая заявка</button>}</div></div>
  <div className="home-toolbar"><label className="home-search"><Search size={18} aria-hidden="true"/><input type="search" aria-label="Поиск активной заявки" placeholder="Адрес, номер или проблема" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/></label>
   <div className="home-filters" role="group" aria-label="Фильтры заявок">{[['all','Все'],['new','Новые'],['progress','В работе'],...(canMine?[['mine','Мои']]:[])].map(([id,label])=><button key={id} type="button" aria-pressed={currentFilter===id} onClick={()=>{setFilter(id);setPage(0);}}>{label}</button>)}</div>
   <button type="button" className="icon-button home-refresh" aria-label="Обновить заявки" title="Обновить заявки" disabled={refreshing} onClick={onRefresh}><RefreshCw size={18}/></button>
  </div>
  <div className="home-list" aria-label="Активные заявки">
   <div className="home-list-heading" aria-hidden="true"><span>Заявка / адрес</span><span>Проблема</span><span>Исполнитель</span><span>Статус</span><span/></div>
   {rows.map(ticket=>{
    const lift=elevators.get(ticket.elevator),urgent=ticket.priority==='ENTRAPMENT';
    return <button type="button" className={'home-ticket'+(urgent?' home-ticket-critical':'')} key={ticket.id} onClick={()=>onOpen(ticket)}>
     <span className="home-ticket-address"><b>№{ticket.id} · {ticket.address||'Адрес не указан'}</b><small>{[lift?entranceLabel(lift):null,ticket.elevator_label||ticket.elevator_factory_number].filter(Boolean).join(' · ')}</small>{urgent&&<span className="home-urgent">Застревание</span>}</span>
     <span className="home-ticket-problem">{ticket.title}</span>
     <span className="home-ticket-person">{ticket.technician_name||technicians.get(ticket.assigned_to)||'Не назначен'}</span>
     <span className="home-ticket-status"><Badge value={ticket.status}/><time dateTime={ticket.created_at}>{ticket.created_at?date(ticket.created_at):''}</time></span>
     <ChevronRight className="home-ticket-arrow" size={17} aria-hidden="true"/>
    </button>;
   })}
   {!rows.length&&<div className="home-empty"><h2>{query||currentFilter!=='all'?'Заявки не найдены':'Активных заявок нет'}</h2><p>{query||currentFilter!=='all'?'Измените поиск или выберите другой фильтр.':'Новые обращения появятся здесь автоматически.'}</p>{(query||currentFilter!=='all')&&<button type="button" onClick={()=>{setQuery('');setFilter('all');setPage(0);}}>Сбросить фильтры</button>}</div>}
  </div>
  <footer className="home-list-footer"><span role="status">{tickets.length>25?`${currentPage*25+1}–${Math.min(tickets.length,(currentPage+1)*25)} из ${tickets.length}`:`Активных заявок: ${tickets.length}`}</span>{last>0&&<nav className="home-pagination" aria-label="Страницы заявок"><button type="button" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Назад</button><span>{currentPage+1} / {last+1}</span><button type="button" disabled={currentPage===last} onClick={()=>setPage(currentPage+1)}>Далее</button></nav>}<button type="button" className="home-history" onClick={onAll}>Все заявки и история <ChevronRight size={16}/></button></footer>
 </section>;
}
