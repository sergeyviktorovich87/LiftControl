import React,{useCallback,useEffect,useState} from 'react';
import {api} from './api';

/** Durable per-organization inbox. Reading never accepts a ticket or task. */
export default function Notifications({user,onOpen=()=>{},onRead,initialEntrapment=false}) {
  const [items,setItems]=useState([]),[unread,setUnread]=useState(0);
  const [category,setCategory]=useState(initialEntrapment?'entrapment':'ordinary');
  const [categoryCounts,setCategoryCounts]=useState({});
  const [onlyNew,setOnlyNew]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);

  const load=useCallback(async(signal)=>{
    try{
      const filter=user.lift_documents_api?'&category='+category:'';
      const data=await api('notifications/?unread='+(onlyNew?'1':'0')+'&limit=100'+filter,{signal});
      if(signal?.aborted)return;
      setItems(data.results||[]);setUnread(data.unread||0);setError('');
      setCategoryCounts(data.unread_by_category||{});
    }catch(e){if(!signal?.aborted)setError(e.message);}
  },[onlyNew,category,user.organization_id,user.lift_documents_api]);

  useEffect(()=>{
    const abort=new AbortController();
    load(abort.signal);
    const timer=setInterval(()=>{if(!document.hidden)load(abort.signal);},15000);
    return()=>{abort.abort();clearInterval(timer);};
  },[load]);

  async function open(item) {
    if(busy)return;
    setBusy(true);
    try{
      if(!item.read_at){
        await api('notifications/'+item.id+'/read/',{method:'POST',body:{}});
        onRead?.();
      }
      await load();
      onOpen(item.target_type,item.target_id);
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  return <>
    <div className="page-heading"><div>
      <span className="eyebrow">ЦЕНТР УВЕДОМЛЕНИЙ</span>
      <h1>Уведомления</h1>
      <p>Непрочитанных {unread}</p>
    </div>
    <div className="actions"><label><input type="checkbox" checked={onlyNew}
      onChange={e=>setOnlyNew(e.target.checked)}/> Только непрочитанные</label>
      <button disabled={busy} onClick={()=>load()}>Обновить</button></div></div>
    {user.lift_documents_api===1&&<div className="tabs" aria-label="Тип уведомлений">
      {[['ordinary','Обычные'],['entrapment','Застревания']].map(([id,label])=>
        <button key={id} type="button" disabled={busy} aria-pressed={category===id}
          className={category===id?'selected':''} onClick={()=>{if(category!==id){setItems([]);setCategory(id);}}}>
          {label}{categoryCounts[id]>0&&<span className="unread-count" aria-label={categoryCounts[id]+' непрочитанных'}>{categoryCounts[id]>99?'99+':categoryCounts[id]}</span>}
        </button>)}
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}
    <section className="panel">
      {items.map(item=><button type="button" className={'list-row '+(item.category==='entrapment'?'entrapment-notification':'')}
        disabled={busy} key={item.id} onClick={()=>open(item)}>
        <span style={{flex:1,textAlign:'left'}}>
          <b>{item.read_at?'':'● '}{item.title}</b>
          {item.preview&&<small>{item.preview}</small>}
          <small>{new Date(item.created_at).toLocaleString('ru-RU')}</small>
        </span><span>{item.read_at?'Прочитано':'Новое'}</span>
      </button>)}
      {!items.length&&<p className="empty">Новых записей нет.</p>}
    </section>
  </>;
}
