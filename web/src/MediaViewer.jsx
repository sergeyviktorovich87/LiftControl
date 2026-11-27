import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowLeft,ChevronLeft,ChevronRight,Download,ImageOff} from 'lucide-react';
import {record} from './api';
import './media-viewer.css';
function Stage({asset}){
 const [state,setState]=useState('loading');
 return <div className="photo-stage">{state==='loading'&&<p role="status">Загрузка фото…</p>}{state==='error'?<div className="photo-error" role="alert"><ImageOff size={32}/><p>Не удалось открыть фото</p><small>Проверьте подключение и доступ к файлу.</small><button type="button" onClick={()=>setState('loading')}>Повторить</button></div>:<img src={asset.url} alt={asset.name} onLoad={()=>setState('ready')} onError={()=>{setState('error');record('media','viewer','load-error');}}/>}</div>;
}
export default function MediaViewer(){
 const [view,setView]=useState(null),[index,setIndex]=useState(0);
 const current=useRef(null),sessions=useRef(new Map()),dialog=useRef(null),closing=useRef(false);
 const apply=value=>{current.current=value;setView(value);setIndex(value?.index||0);closing.current=false;};
 useEffect(()=>{
  const click=event=>{
   if(event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||current.current)return;
   const anchor=event.target.closest?.('a');if(!anchor||anchor.hasAttribute('download')||anchor.closest('.photo-viewer')||!anchor.querySelector('img')||anchor.querySelector('.ticket-play'))return;
   const url=new URL(anchor.href,location.href);if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return;
   const gallery=anchor.closest('.ticket-gallery,.chat-attachments,.comm-photos,.media-grid,.nameplate-grid,.messenger-photo-library,.nameplate-photos')||anchor.parentElement;
   const anchors=[...gallery.querySelectorAll('a')].filter(a=>{const u=new URL(a.href,location.href);return a.querySelector('img')&&!a.querySelector('.ticket-play')&&u.origin===location.origin&&u.pathname.startsWith('/api/');});
   const items=anchors.map(a=>({url:a.href,preview:a.querySelector('img').src,name:a.querySelector('img').alt||a.title||'Фото'}));
   if(!items.length)return;
   event.preventDefault();event.stopPropagation();
   const token=crypto.randomUUID(),value={token,items,index:Math.max(0,anchors.indexOf(anchor)),focus:anchor};sessions.current.set(token,value);
   history.pushState({...history.state,lcPhoto:token},'',location.href);apply(value);
  };
  const pop=event=>{
   const saved=sessions.current.get(event.state?.lcPhoto);
   if(current.current||saved){event.stopImmediatePropagation();apply(saved||null);}
  };
  document.addEventListener('click',click,true);window.addEventListener('popstate',pop,true);
  return()=>{document.removeEventListener('click',click,true);window.removeEventListener('popstate',pop,true);if(sessions.current.has(history.state?.lcPhoto)){const state={...history.state};delete state.lcPhoto;history.replaceState(state,'',location.href);}sessions.current.clear();};
 },[]);
 useEffect(()=>{
  if(!view)return;
  const root=document.getElementById('root'),wasInert=root?.inert;const overflow=document.body.style.overflow;document.body.style.overflow='hidden';if(root)root.inert=true;dialog.current?.querySelector('button')?.focus({preventScroll:true});
  return()=>{document.body.style.overflow=overflow;if(root)root.inert=wasInert;view.focus?.focus({preventScroll:true});};
 },[view]);
 if(!view)return null;
 const asset=view.items[index],close=()=>{if(closing.current)return;closing.current=true;if(history.state?.lcPhoto===view.token)history.back();else apply(null);};
 const move=delta=>{const next=(index+delta+view.items.length)%view.items.length;setIndex(next);view.index=next;};
 const keydown=event=>{
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();move(event.key==='ArrowLeft'?-1:1);}
  if(event.key==='Tab'){
   const buttons=[...dialog.current.querySelectorAll('button,a')].filter(e=>!e.disabled&&e.getClientRects().length),first=buttons[0],last=buttons.at(-1);
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
   event.stopPropagation();
  }
 };
 return createPortal(<section className="photo-viewer" ref={dialog} role="dialog" aria-modal="true" aria-label="Просмотр фото" onKeyDown={keydown}>
  <header><button type="button" className="photo-back" onClick={close}><ArrowLeft size={23}/>Назад</button><div><b>Просмотр фото</b><small>{index+1} из {view.items.length}</small></div><a href={asset.url} download aria-label="Скачать фото"><Download size={22}/></a></header>
  <div className="photo-content"><Stage key={asset.url} asset={asset}/>{view.items.length>1&&<><button type="button" className="photo-prev" aria-label="Предыдущее фото" onClick={()=>move(-1)}><ChevronLeft size={28}/></button><button type="button" className="photo-next" aria-label="Следующее фото" onClick={()=>move(1)}><ChevronRight size={28}/></button></>}</div>
  <footer><p>{asset.name}</p>{view.items.length>1&&<div className="photo-thumbnails">{view.items.map((item,i)=><button type="button" key={item.url+':'+i} aria-label={'Фото '+(i+1)} aria-pressed={i===index} onClick={()=>{setIndex(i);view.index=i;}}><img src={item.preview} alt=""/></button>)}</div>}</footer>
 </section>,document.body);
}
