import React,{useState} from 'react';
export default function ElevatorFolderPicker({data,selected,onChange,inherited=[]}){
 const [query,setQuery]=useState(''),[opened,setOpened]=useState(()=>new Set((data.elevators||[]).filter(l=>selected.includes(l.id)||inherited.includes(l.id)).map(l=>String(l.building||l.address||'Адрес не указан'))));
 const groups=new Map(),search=query.trim().toLocaleLowerCase('ru');
 const label=lift=>`${lift.entrance_kind==='LIFT'?'Лифт №':'Подъезд '}${lift.entrance||'не указан'} · ${lift.factory_number||lift.inventory_number||'Запись '+lift.id}`;
 for(const lift of data.elevators||[]){
  const building=(data.buildings||[]).find(b=>b.id===lift.building),address=building?.address||lift.address||'Адрес не указан';
  if(search&&![address,label(lift)].join(' ').toLocaleLowerCase('ru').includes(search))continue;
  const key=String(lift.building||address);if(!groups.has(key))groups.set(key,{address,lifts:[]});groups.get(key).lifts.push(lift);
 }
 const count=new Set([...selected,...inherited]).size;
 return <fieldset className="lift-folder-picker"><legend>Привязка к лифтам</legend><p>Выберите лифты, в карточках которых появятся папка и её содержимое.</p>
 <input type="search" aria-label="Адрес или номер лифта" placeholder="Адрес или номер лифта" value={query} onChange={e=>setQuery(e.target.value)}/>
 <div className="lift-picker-groups">{[...groups].sort((a,b)=>a[1].address.localeCompare(b[1].address,'ru',{numeric:true})).map(([key,group])=>{
  const expanded=!!search||opened.has(key);
  return <div className="lift-picker-group" key={key}><button type="button" aria-expanded={expanded} onClick={()=>setOpened(prev=>{const next=new Set(prev);if(next.has(key))next.delete(key);else next.add(key);return next;})}>{expanded?'⌄':'›'} {group.address}</button>
   {expanded&&group.lifts.map(lift=><label key={lift.id}><input type="checkbox" checked={selected.includes(lift.id)||inherited.includes(lift.id)} disabled={inherited.includes(lift.id)} onChange={e=>onChange(e.target.checked?[...selected,lift.id]:selected.filter(id=>id!==lift.id))}/><span>{label(lift)}{!lift.active?' · архив':''}{inherited.includes(lift.id)?' · унаследовано':''}</span></label>)}
  </div>;
 })}{!groups.size&&<p>Лифты не найдены.</p>}</div>
 <small>Выбрано: {count}. Вложенные папки и файлы наследуют привязку.</small>{inherited.length>0&&<p className="muted">Унаследованные связи меняются в настройках родительской папки.</p>}
 </fieldset>;
}
