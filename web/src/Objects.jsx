import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Search,Plus,SlidersHorizontal,ChevronDown,ChevronRight,MoreHorizontal,X} from 'lucide-react';
import {entranceLabel} from './LiftDocuments';
import './objects.css';
const plural=(n,one,few,many)=>n%100>=11&&n%100<=14?many:n%10===1?one:n%10>=2&&n%10<=4?few:many;
const open=t=>!['DONE','CANCELED'].includes(t.status);
export default function Objects({data,user,search,setSearch,onEdit,onLift,onTickets}){
 const [filter,setFilter]=useState('all'),[filters,setFilters]=useState(false),[archived,setArchived]=useState(false),[mechanic,setMechanic]=useState(''),[expanded,setExpanded]=useState({}),[menu,setMenu]=useState(null);
 const root=useRef();const collator=useMemo(()=>new Intl.Collator('ru',{numeric:true,sensitivity:'base'}),[]);
 useEffect(()=>{if(!menu)return;const outside=e=>{if(!e.target.closest('.object-menu-wrap'))setMenu(null);};const key=e=>{if(e.key==='Escape'){setMenu(null);root.current?.querySelector('[data-menu="'+menu+'"]')?.focus();}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key);};},[menu]);
 const q=search.trim().toLocaleLowerCase('ru');
 const person=id=>data.technicians.find(t=>t.id===id)?.full_name||'Не назначен';
 const tasks=data.tickets.filter(open);
 const selected=useMemo(()=>{
  const result=[];
  for(const b of data.buildings){
   if(b.deleted_at)continue;
   const addressMatch=[b.address,b.name,b.street,b.house].some(v=>String(v||'').toLocaleLowerCase('ru').includes(q));
   const all=data.elevators.filter(l=>l.building===b.id&&!l.deleted_at);
   const lifts=all.filter(l=>(archived||l.active)&&(!mechanic||l.assigned_technician===Number(mechanic))&&(addressMatch||[l.factory_number,l.inventory_number,l.manufacturer,l.model,l.entrance,person(l.assigned_technician)].some(v=>String(v||'').toLocaleLowerCase('ru').includes(q))));
   const tickets=tasks.filter(t=>t.building===b.id||all.some(l=>l.id===t.elevator));
   if(q&&!addressMatch&&!lifts.length||mechanic&&!lifts.length||filter==='tickets'&&!tickets.length||filter==='stopped'&&!lifts.some(l=>l.stopped_at))continue;
   const shown=filter==='stopped'?lifts.filter(l=>l.stopped_at):lifts;
   result.push({...b,lifts:shown,total:all.length,tickets,urgent:tickets.filter(t=>t.priority==='ENTRAPMENT').length});
  }
  return result.sort((a,b)=>collator.compare(a.address,b.address));
 },[data,q,archived,mechanic,filter]);
 const groups=useMemo(()=>{const result=new Map();for(const b of selected){const street=b.street||'Другие адреса';if(!result.has(street))result.set(street,[]);result.get(street).push(b);}return [...result];},[selected]);
 const action=(type,item)=>{setMenu(null);onEdit(type,item);};
 const menuButton=(id,label,children)=><div className="object-menu-wrap"><button className="object-more" data-menu={id} aria-label={label} aria-expanded={menu===id} aria-haspopup="menu" onClick={()=>setMenu(menu===id?null:id)}><MoreHorizontal size={20}/></button>{menu===id&&<div className="object-menu" role="menu">{children}</div>}</div>;
 return <section className="objects-page" ref={root}>
  <header className="objects-heading"><div><h1>Объекты</h1><p>Дома и лифты вашей организации</p></div>{user.can_manage&&<div className="object-menu-wrap"><button className="primary" aria-haspopup="menu" aria-expanded={menu==='add'} onClick={()=>setMenu(menu==='add'?null:'add')}><Plus size={18}/><span>Добавить</span><ChevronDown size={16}/></button>{menu==='add'&&<div className="object-menu" role="menu"><button role="menuitem" onClick={()=>action('buildings',{})}>Добавить дом</button><button role="menuitem" onClick={()=>action('elevators',{})}>Добавить лифт</button></div>}</div>}</header>
  <div className="objects-search"><label className="objects-search-field"><Search size={20}/><input aria-label="Поиск лифтов" placeholder="Адрес, номер лифта или механик" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="Очистить поиск объектов" onClick={()=>setSearch('')}><X size={17}/></button>}</label><button className={filters?'selected':''} aria-label="Фильтры объектов" aria-expanded={filters} onClick={()=>setFilters(v=>!v)}><SlidersHorizontal size={18}/><span>Фильтры</span>{(archived||mechanic)&&<i className="object-filter-dot"/>}</button></div>
  <div className="object-filter-tabs" aria-label="Состояние объектов">{[['all','Все объекты'],['tickets','Есть заявки'],['stopped','Остановлены']].map(([id,label])=><button key={id} aria-pressed={filter===id} className={filter===id?'selected':''} onClick={()=>setFilter(id)}>{label}</button>)}</div>
  {filters&&<div className="objects-filters"><label>Механик<select aria-label="Механик объектов" value={mechanic} onChange={e=>setMechanic(e.target.value)}><option value="">Все механики</option>{data.technicians.filter(t=>t.active).map(t=><option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label><label className="objects-archive"><input type="checkbox" checked={archived} onChange={e=>setArchived(e.target.checked)}/>Показывать архив</label><button onClick={()=>{setFilter('all');setArchived(false);setMechanic('');setSearch('');}}>Сбросить фильтры</button></div>}
  <div className="objects-list">{groups.map(([street,buildings])=><section key={street} className="objects-street"><h2>{street}</h2>{buildings.map(b=>{
   const isOpen=!!q||(expanded[b.id]??(b.id===data.buildings[0]?.id));
   return <article className="object-house" key={b.id}>
    <header className="object-house-heading"><button className="object-house-toggle" aria-expanded={isOpen} onClick={()=>setExpanded(old=>({...old,[b.id]:!isOpen}))}>{isOpen?<ChevronDown size={19}/>:<ChevronRight size={19}/>}<span><b>{b.address}</b><small>{b.name} · {b.total} {plural(b.total,'лифт','лифта','лифтов')}</small></span></button><button className={'object-house-state '+(b.urgent?'urgent':b.tickets.length?'pending':'clear')} disabled={!b.tickets.length} onClick={()=>onTickets({building:b.id})}>{b.urgent?'Застревание · '+b.urgent:b.tickets.length?b.tickets.length+' '+plural(b.tickets.length,'открытая заявка','открытых заявки','открытых заявок'):'Без открытых заявок'}</button>{user.can_manage&&menuButton('b'+b.id,'Действия дома: '+b.address,<><button role="menuitem" onClick={()=>action('elevators',{building:b.id})}><Plus size={16}/>Добавить лифт</button><button role="menuitem" onClick={()=>action('buildings',b)}>Изменить дом</button>{user.can_manage_access&&<button role="menuitem" className="danger" onClick={()=>action('delete-building',{...b,elevators_count:b.total})}>Удалить дом</button>}</>)}</header>
    {isOpen&&<div className="object-house-content"><div className="object-lift-head"><span>Подъезд / лифт</span><span>Состояние</span><span>Механик</span><span>Заявки</span><span/></div>{b.lifts.map(l=>{
     const tickets=b.tickets.filter(t=>t.elevator===l.id),state=!l.active?'Архив':l.stopped_at?'На ремонте':'Работает';
     return <div className="object-lift-row" key={l.id}><button className="object-lift-name lift-tile" onClick={()=>onLift(l)}><span><b>{entranceLabel(l)}</b><small>{[l.factory_number&&'Зав. № '+l.factory_number,l.inventory_number&&'Учётный № '+l.inventory_number].filter(Boolean).join(' · ')||'Номер не указан'}</small></span><ChevronRight size={17}/></button><span className={'object-lift-state '+(!l.active?'archived':l.stopped_at?'stopped':'running')}><i/>{state}</span><span className="object-lift-person">{person(l.assigned_technician)}</span><div className="object-lift-tickets">{tickets.length?<button className={tickets.some(t=>t.priority==='ENTRAPMENT')?'urgent':''} onClick={()=>onTickets({elevator:l.id})}>{tickets.length} {plural(tickets.length,'заявка','заявки','заявок')}</button>:<span>—</span>}</div>{user.can_manage&&menuButton('l'+l.id,'Действия лифта: '+(l.factory_number||l.id),<><button role="menuitem" onClick={()=>action('elevators',l)}>Изменить лифт</button>{user.can_create_ticket&&l.active&&<button role="menuitem" onClick={()=>action('tickets',{building:b.id,elevator:l.id})}>Создать заявку</button>}{user.can_manage_access&&<>{l.active&&<button role="menuitem" onClick={()=>action('archive-elevators',l)}>Переместить в архив</button>}<button role="menuitem" className="danger" onClick={()=>action('delete-elevator',l)}>Удалить лифт</button></>}</>)}</div>;
    })}{!b.lifts.length&&<p className="objects-empty-inline">{b.total?'Нет лифтов по выбранным фильтрам.':'В этом доме пока нет лифтов.'}</p>}{b.tickets.some(t=>!t.elevator)&&<button className="object-inline-add" onClick={()=>onTickets({building:b.id,unidentified:true})}>Заявки без уточнённого лифта · {b.tickets.filter(t=>!t.elevator).length}</button>}{user.can_manage&&<button className="object-inline-add" onClick={()=>action('elevators',{building:b.id})}><Plus size={17}/>Добавить лифт в дом</button>}</div>}
   </article>;
  })}</section>)}{!selected.length&&<div className="objects-empty"><h2>Объекты не найдены</h2><p>Измените поиск или сбросьте фильтры.</p><button onClick={()=>{setSearch('');setFilter('all');setMechanic('');setArchived(false);}}>Показать все объекты</button></div>}</div>
 </section>;
}
