import React,{useMemo,useState} from 'react';
import {Plus,Search,Camera,ChevronRight,RefreshCw} from 'lucide-react';
import {entranceLabel} from './LiftDocuments';
import './parts.css';
const labels={NEW:'Новый запрос',APPROVED:'Согласовано',ORDERED:'Заказано',RECEIVED:'Получено',ISSUED:'Выдано',CANCELED:'Отменено'};
const closed=new Set(['ISSUED','CANCELED']);
export default function PartsList({user,data,onCreate,onOpen,onRefresh,refreshing=false}){
 const [query,setQuery]=useState(''),[filter,setFilter]=useState('all'),[history,setHistory]=useState(false),[page,setPage]=useState(0);
 const lifts=useMemo(()=>new Map(data.elevators.map(lift=>[lift.id,lift])),[data.elevators]);
 const parts=useMemo(()=>data.parts.filter(part=>{
  if(closed.has(part.status)!==history||filter!=='all'&&part.status!==filter)return false;
  const lift=lifts.get(part.elevator);
  return [part.id,part.part,part.address,part.elevator_label,part.elevator_factory_number,part.author_name,part.notes,lift?.entrance].filter(value=>value!==null&&value!==undefined).join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'));
 }).sort((a,b)=>new Date(b.created_at)-new Date(a.created_at)||b.id-a.id),[data.parts,filter,history,query,lifts]);
 const last=Math.max(0,Math.ceil(parts.length/25)-1),current=Math.min(page,last),rows=parts.slice(current*25,(current+1)*25);
 const choose=id=>{setFilter(id);setPage(0);};
 const showHistory=()=>{setHistory(!history);setFilter('all');setPage(0);};
 const date=value=>new Date(value).toLocaleDateString('ru-RU',{timeZone:user.timezone||'Asia/Chita',day:'2-digit',month:'short'});
 return <section className="parts-workspace">
  <header className="page-heading parts-heading"><div><span className="eyebrow">СНАБЖЕНИЕ</span><h1>Запчасти</h1><p>{history?'Выданные и отменённые запросы':'Запросы, закупка и выдача'}</p></div><div className="actions"><button type="button" className="primary" onClick={onCreate}><Plus size={18}/>Запросить запчасть</button></div></header>
  <div className="parts-toolbar"><label className="parts-search"><Search size={18} aria-hidden="true"/><input type="search" aria-label="Поиск запчасти" placeholder="Название, адрес или номер" value={query} onChange={event=>{setQuery(event.target.value);setPage(0);}}/></label>
   <div className="parts-filters" role="group" aria-label="Статусы запросов запчастей">{[['all','Все'],...(history?[['ISSUED','Выданы'],['CANCELED','Отменены']]:[['NEW','Новые'],['APPROVED','Согласованы'],['ORDERED','Заказаны'],['RECEIVED','Получены']])].map(([id,label])=><button type="button" key={id} aria-pressed={filter===id} onClick={()=>choose(id)}>{label}</button>)}</div>
   <button type="button" className="icon-button parts-refresh" aria-label="Обновить запчасти" title="Обновить запчасти" disabled={refreshing} onClick={onRefresh}><RefreshCw size={18}/></button>
  </div>
  <div className="parts-list" aria-label={history?'История запросов запчастей':'Активные запросы запчастей'}><div className="parts-list-heading" aria-hidden="true"><span>Запчасть / объект</span><span>Кол-во</span><span>Кто запросил</span><span>Статус</span><span/></div>
   {rows.map(part=>{
    const lift=lifts.get(part.elevator),photos=part.photos?.length||0;
    return <button type="button" className="parts-row" key={part.id} onClick={()=>onOpen(part)}>
     <span className="parts-row-detail"><b>{part.part}</b><small>№{part.id} · {[part.address,lift?entranceLabel(lift):null,part.elevator_label||part.elevator_factory_number].filter(Boolean).join(' · ')}</small><span className="parts-row-meta">{photos>0&&<span><Camera size={13} aria-hidden="true"/>Фото {photos}</span>}{part.created_at&&<time dateTime={part.created_at}>{date(part.created_at)}</time>}</span></span>
     <span className="parts-row-quantity">{part.quantity} шт.</span><span className="parts-row-author">{part.author_name||'Не указан'}</span>
     <span className={'parts-status parts-status-'+part.status}>{labels[part.status]||part.status}</span><ChevronRight className="parts-row-arrow" size={17} aria-hidden="true"/>
    </button>;
   })}
   {!rows.length&&<div className="parts-empty"><h2>{query||filter!=='all'?'Запросы не найдены':history?'История пока пуста':'Активных запросов пока нет'}</h2><p>{query||filter!=='all'?'Измените поиск или выберите другой статус.':history?'Здесь будут выданные и отменённые запросы.':'Создайте запрос и укажите нужную запчасть и лифт.'}</p>{(query||filter!=='all')&&<button type="button" onClick={()=>{setQuery('');choose('all');}}>Сбросить фильтры</button>}</div>}
  </div>
  <footer className="parts-list-footer"><span role="status">{parts.length>25?`Показано ${current*25+1}–${Math.min(parts.length,(current+1)*25)} из ${parts.length}`:`Запросов: ${parts.length}`}</span>
   {last>0&&<nav className="parts-pagination" aria-label="Страницы запросов запчастей"><button type="button" disabled={current===0} onClick={()=>setPage(current-1)}>Назад</button><span>{current+1} / {last+1}</span><button type="button" disabled={current===last} onClick={()=>setPage(current+1)}>Далее</button></nav>}
   <button type="button" className="parts-history" aria-pressed={history} onClick={showHistory}>{history?'Вернуться к активным запросам':'Показать выданные и отменённые'}<ChevronRight size={16}/></button>
  </footer>
 </section>;
}
