import {useLiveRefresh} from './liveRefresh';
import React, {useCallback, useEffect, useState} from 'react';
import {FileText, Trash2} from 'lucide-react';
import {api} from './api';
import {Field,Dialog} from './components';
import Documentation from './Documentation';

const categories = {
  CONTRACT: 'Договоры',
  ORDER: 'Приказы о назначении',
  INSPECTION: 'Освидетельствование',
};

export function entranceLabel(lift) {
  const entrance = lift.entrance?.trim();
  if (lift.entrance_kind==='LIFT') return entrance ? (/^лифт/i.test(entrance)?entrance:'Лифт №'+entrance) : 'Номер лифта не указан';
  if (!entrance) return 'Подъезд не указан';
  return /^подъезд/i.test(entrance) ? entrance : 'Подъезд '+entrance;
}

function dateLabel(date) {
  return date ? date.split('-').reverse().join('.') : 'Не назначено';
}

function fileRows(rows, remove, busy) {
  return rows.map(row => <div className="list-row" key={row.id}>
    <a href={row.url} target="_blank" rel="noreferrer"><FileText size={16}/> {row.title}</a>
    {remove&&<button type="button" disabled={busy} onClick={()=>remove(row)} aria-label={'Удалить '+row.title}>
      <Trash2 size={16}/>
    </button>}
  </div>);
}

export function LiftInspections({lift}) {
  const [inspection,setInspection] = useState(null), [error,setError] = useState('');
  const [attempt,setAttempt] = useState(0);
  useEffect(()=>{
    const abort = new AbortController();
    api('lift-inspections/'+lift.id+'/',{signal:abort.signal})
      .then(value=>{if(!abort.signal.aborted)setInspection(value);})
      .catch(err=>{if(!abort.signal.aborted)setError(err.message);});
    return ()=>abort.abort();
  },[lift.id,attempt]);
  useLiveRefresh(async signal=>{const value=await api('lift-inspections/'+lift.id+'/',{signal});if(!signal.aborted)setInspection(value);},lift.id);
  const acts = inspection?.acts ?? [];
  return <section>
    {error ? <>
      <p role="alert" className="error">{error}</p>
      <button type="button" onClick={()=>{setError('');setAttempt(value=>value+1);}}>Повторить</button>
    </> : !inspection ? <p role="status">Загрузка актов…</p> : <>
      <p>Следующее освидетельствование <strong>{dateLabel(inspection.date)}</strong></p>
      {fileRows(acts)}
      {!acts.length&&<p className="empty">Актов пока нет.</p>}
    </>}
  </section>;
}

function LiftDocumentList({lift,category,user}) {
  const [rows,setRows] = useState([]), [date,setDate] = useState(''), [next,setNext] = useState(null);
  const [busy,setBusy] = useState(false), [loading,setLoading] = useState(true), [error,setError] = useState('');
  const path = 'lift-inspections/'+lift.id+'/';
  const today = new Intl.DateTimeFormat('sv-SE',{timeZone:user.timezone}).format(new Date());
  const load = useCallback(async (signal,quiet=false)=>{
    const requests = [api('lift-documents/?elevator='+lift.id+'&category='+category,{signal}),
      category==='INSPECTION' ? api(path,{signal}) : null];
    const [documents,inspection] = await Promise.all(requests);
    if (signal?.aborted) return;
    setRows(documents);
    setNext(inspection?.date ?? null);
    if(!quiet)setDate(inspection?.date ?? '');
  },[category,lift.id,path]);
  useEffect(()=>{
    const abort = new AbortController();
    load(abort.signal)
      .catch(err=>{if(!abort.signal.aborted)setError(err.message);})
      .finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return ()=>abort.abort();
  },[load]);

  useLiveRefresh(signal=>busy?null:load(signal,true),user.organization_id+':'+lift.id+':'+category);

  async function run(action) {
    setBusy(true);
    setError('');
    try {await action();await load();}
    catch(err) {setError(err.message);}
    finally {setBusy(false);}
  }

  function upload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set('elevator',String(lift.id));
    body.set('category',category);
    run(async()=>{
      await api('lift-documents/',{method:'POST',body});
      form.reset();
    });
  }

  function remove(row) {
    if (window.confirm('Удалить PDF «'+row.title+'»?')) {
      run(()=>api('lift-documents/'+row.id+'/',{method:'DELETE'}));
    }
  }

  function saveDate(value) {
    return run(()=>api(path,{method:'PATCH',body:{date:value}}));
  }

  return <section className="panel settings-panel">
    <h2>{categories[category]}</h2>
    {category==='INSPECTION'&&<>
      <p>Следующее освидетельствование <strong>{dateLabel(next)}</strong></p>
      {lift.active&&<form className="actions" onSubmit={event=>{event.preventDefault();saveDate(date);}}>
        <Field label="Дата освидетельствования"><input required type="date" min={today}
          value={date} onChange={event=>setDate(event.target.value)} disabled={busy||loading}/></Field>
        <button disabled={busy||loading||!date}>Сохранить дату</button>
        {next&&<button type="button" disabled={busy||loading} onClick={()=>saveDate(null)}>Снять дату</button>}
      </form>}
    </>}
    {error&&<p role="alert" className="error">{error}</p>}
    <form className="actions" onSubmit={upload}>
      <Field label="Название"><input name="title" required maxLength={200}/></Field>
      <Field label="Файл PDF"><input name="file" required type="file" accept="application/pdf,.pdf"/></Field>
      <button className="primary" disabled={busy||loading}>Добавить PDF</button>
    </form>
    {fileRows(rows,remove,busy)}
    {!loading&&rows.length===0&&<p>Документов пока нет.</p>}
  </section>;
}

function LegacyLiftDocuments({user,lifts}) {
  const [query,setQuery] = useState(''), [selected,setSelected] = useState(''), [category,setCategory] = useState('CONTRACT');
  const lift = lifts.find(row=>String(row.id)===selected);
  const label = row=>[row.address,entranceLabel(row),row.inventory_number||row.factory_number||'#'+row.id].join(' · ');
  const choices = lifts.filter(row=>row.id===lift?.id||label(row).toLowerCase().includes(query.toLowerCase().trim()));
  return <>
    <div className="page-heading"><h1>Документы</h1></div>
    <div className="toolbar">
      <Field label="Найти лифт"><input type="search" value={query} onChange={event=>setQuery(event.target.value)}/></Field>
      <Field label="Лифт"><select value={selected} onChange={event=>setSelected(event.target.value)}>
        <option value="">Выберите лифт</option>
        {choices.map(row=><option key={row.id} value={row.id}>{label(row)}</option>)}
      </select></Field>
    </div>
    <div className="tabs">
      {Object.entries(categories).map(([id,name])=>
        <button key={id} className={category===id?'selected':''} type="button"
          aria-pressed={category===id} onClick={()=>setCategory(id)}>{name}</button>)}
    </div>
    {lift&&<LiftDocumentList key={lift.id+':'+category} user={user} lift={lift} category={category}/>}
  </>;
}

export default function LiftDocuments({user,lifts,data}) {
 const [legacy,setLegacy]=useState(false);
 return <><button className="legal-legacy" onClick={()=>setLegacy(true)}>Сроки освидетельствования и прежние документы</button><Documentation user={user} data={data||{elevators:lifts,buildings:[]}} legal/>{legacy&&<Dialog title="Документы и сроки по лифту" onClose={()=>setLegacy(false)} wide><LegacyLiftDocuments user={user} lifts={lifts}/></Dialog>}</>;
}
