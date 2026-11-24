import {useLiveRefresh} from './liveRefresh';
import MediaLibrary from './MediaLibrary';
import Commissioning from './Commissioning';
import Notifications from './Notifications';
import LiftDocuments,{entranceLabel,LiftInspections} from './LiftDocuments';
import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ArrowUp,LayoutDashboard,CalendarDays,Building2,Users,ClipboardList,Wrench,BookOpen,Package,MessageSquare,BarChart3,Bell,Settings,Menu,Search,Plus,ChevronRight,ChevronDown,RefreshCw,Download,Send,LogOut,ShieldCheck,Copy} from 'lucide-react';
import {api,PREVIEW,diagnosticEvents,record,download,csv} from './api';
import {roles,previewRole} from './demo';
import {Badge,Dialog,Editor,Field} from './components';
import Duty from './Duty';
import TicketWorkflow from './TicketWorkflow';
import PushControls from './PushControls';
import PwaControls from './PwaControls.jsx';
import NotificationPreferences from './NotificationPreferences';
import OrganizationControls, {switchOrganization} from './OrganizationControls';
import DutyStatus from './DutyStatus';
import UpdateControls from './UpdateControls';
import ArchiveDialog from './ArchiveDialog';
import Tasks from './Tasks';
import ChatMedia from './ChatMedia';
import MaintenanceJournal from './MaintenanceJournal';
const nav=[['home','Главная',LayoutDashboard],['duty','Графики дежурств',CalendarDays],['objects','Объекты',Building2],['technicians','Механики',Users],['tickets','Заявки',ClipboardList],['tasks','Личные задания',ClipboardList],['commissioning','Пусконаладка',Wrench],['commissioning-chat','Чат наладчиков',MessageSquare],['notifications','Уведомления',Bell],['documents','Документация',BookOpen],['lift-documents','Документы',BookOpen],['parts','Запчасти',Package],['media','Медиаматериалы',BookOpen],['chat','Чат',MessageSquare],['reports','Отчёты и аналитика',BarChart3],['settings','Настройки',Settings]];
const commissioningPages=['commissioning','commissioning-chat'];
function UnreadBadge({count}){
 return count>0?<span className="unread-count" aria-label={count+' непрочитанных'}>{count>99?'99+':count}</span>:null;
}
const pageFromHash=()=>location.hash==='#maintenance'?'objects':location.hash.slice(1);
const initialData={buildings:[],elevators:[],technicians:[],tickets:[],maintenance:[],documents:[],parts:[],tasks:[]};
const inventoryLabel=lift=>lift.inventory_number_missing?'Нет':lift.inventory_number;
const fmt=d=>d?new Date(d.length===10?d+'T12:00:00Z':d).toLocaleDateString('ru-RU'):'—';
function Heading({kicker,title,description,children}){return <div className="page-heading"><div><span className="eyebrow">{kicker}</span><h1>{title}</h1><p>{description}</p></div><div className="actions">{children}</div></div>;}
const themes={light:'Светлая',dark:'Тёмная',auto:'Как в системе',blue:'Синяя',graphite:'Графитовая',green:'Зелёная',purple:'Фиолетовая'};
function initialTheme(){try{const value=localStorage.getItem('liftcontrol-theme');return Object.hasOwn(themes,value)?value:'light';}catch{return 'light';}}
export default function App(){
 const [user,setUser]=useState(null),[data,setData]=useState(initialData),[page,setPage]=useState(nav.some(n=>n[0]===pageFromHash())?pageFromHash():'home'),[menu,setMenu]=useState(false),[theme,setTheme]=useState(initialTheme),[search,setSearch]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true),[modal,setModal]=useState(null),[notice,setNotice]=useState('');
 const [taskCreateRequested,setTaskCreateRequested]=useState(false);
 const [chatQuote,setChatQuote]=useState(null);
 const [notificationTarget,setNotificationTarget]=useState(null);
 const [countState,setCountState]=useState(null),[countRevision,setCountRevision]=useState(0);
 const countsChanged=useCallback(()=>setCountRevision(n=>n+1),[]);
 const countScope=user?.id+':'+user?.organization_id;
 const counts=countState?.scope===countScope?countState.value:{};
 const sectionCount=id=>id==='notifications'?counts.unread:counts.sections?.[id==='objects'?'elevators':id];
 const inCommissioning=user?.commissioning_only||commissioningPages.includes(page);
 useEffect(()=>{
   if(PREVIEW||!user?.notification_counts_api)return;
   const abort=new AbortController();
   let request=0;
   const loadCounts=async()=>{
     if(document.hidden)return;
     const serial=++request;
     try{
       const value=await api('notifications/counts/',{signal:abort.signal});
       if(!abort.signal.aborted&&serial===request)setCountState({scope:countScope,value});
     }catch(error){if(!abort.signal.aborted)record('error','notifications/counts',error.status||'network');}
   };
   loadCounts();
   const timer=setInterval(loadCounts,15000);
   document.addEventListener('visibilitychange',loadCounts);
   return()=>{abort.abort();clearInterval(timer);document.removeEventListener('visibilitychange',loadCounts);};
 },[countScope,countRevision,user?.notification_counts_api]);
 const [streets,setStreets]=useState({}),[houses,setHouses]=useState({}),[showArchived,setShowArchived]=useState(false);const menuButton=useRef(),sidebar=useRef(),ticketIds=useRef(null);
 const load=useCallback(async()=>{setLoading(true);try{const profile=await api('me/');setUser(profile);const names=profile.commissioning_only?[]:Object.keys(initialData);const result=await Promise.all(names.map(async name=>[name,await api(name+'/')]));setData(profile.commissioning_only?initialData:Object.fromEntries(result));if(profile.commissioning_only)setPage(current=>profile.can_commissioning?(current==='commissioning-chat'?current:'commissioning'):'settings');setError('');}catch(e){setError(e.message);}finally{setLoading(false);}},[]);
 useEffect(()=>{load();const onError=()=>record('error','browser','runtime');const onReject=()=>record('error','browser','promise');window.addEventListener('error',onError);window.addEventListener('unhandledrejection',onReject);return()=>{window.removeEventListener('error',onError);window.removeEventListener('unhandledrejection',onReject);};},[load]);
 useEffect(()=>{
   const preference=window.matchMedia('(prefers-color-scheme: dark)');
   const apply=()=>{document.documentElement.dataset.theme=theme==='auto'?(preference.matches?'dark':'light'):theme;};
   apply();try{localStorage.setItem('liftcontrol-theme',theme);}catch{}
   if(theme==='auto')preference.addEventListener('change',apply);
   return()=>preference.removeEventListener('change',apply);
 },[theme]);
 useEffect(()=>{const handler=()=>{const next=pageFromHash();if(nav.some(n=>n[0]===next)&&(!commissioningPages.includes(next)||user?.can_commissioning)&&(next!=='lift-documents'||user?.can_manage_lift_documents)&&(!user?.commissioning_only||[...commissioningPages,'notifications','settings'].includes(next))){setPage(next);setSearch('');setMenu(false);setModal(null);}};window.addEventListener('hashchange',handler);return()=>window.removeEventListener('hashchange',handler);},[user?.commissioning_only,user?.can_commissioning,user?.can_manage_lift_documents]);
 useEffect(()=>{if(!menu)return;const prev=document.activeElement;sidebar.current?.querySelector('.active')?.focus();const overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{document.body.style.overflow=overflow;prev?.focus();};},[menu]);
 useEffect(()=>{let start=null;const begin=e=>{if(innerWidth>860||e.touches.length!==1||modal)return;const t=e.touches[0];if(t.clientX<=28||menu&&e.target.closest('.sidebar'))start={x:t.clientX,y:t.clientY};};const move=e=>{if(!start||e.touches.length!==1)return;const t=e.touches[0],dx=t.clientX-start.x,dy=t.clientY-start.y;if(Math.abs(dy)>35&&Math.abs(dy)>Math.abs(dx)){start=null;return;}if(Math.abs(dx)>20&&Math.abs(dx)>Math.abs(dy)*1.6){if(e.cancelable)e.preventDefault();if(!menu&&dx>65){setMenu(true);start=null;}else if(menu&&dx< -65){setMenu(false);start=null;}}};const end=()=>start=null;document.addEventListener('touchstart',begin,{passive:true});document.addEventListener('touchmove',move,{passive:false});document.addEventListener('touchend',end);document.addEventListener('touchcancel',end);return()=>{document.removeEventListener('touchstart',begin);document.removeEventListener('touchmove',move);document.removeEventListener('touchend',end);document.removeEventListener('touchcancel',end);};},[menu,modal]);
 useLiveRefresh(async signal=>{
   const names=user.commissioning_only?[]:Object.keys(initialData);
   const result=await Promise.all(names.map(async name=>[name,await api(name+'/',{signal})]));
   if(signal.aborted)return;
   const next=Object.fromEntries(result);
   const before=ticketIds.current;
   if(next.tickets){
     const newest=next.tickets.find(t=>t.status==='NEW'&&before&&!before.has(t.id));
     if(newest)setNotice('Новая заявка #'+newest.id+' · '+newest.address);
     ticketIds.current=new Set(next.tickets.map(t=>t.id));
   }
   setData(current=>({...current,...next}));
 },countScope,!!user&&!PREVIEW);
 useEffect(()=>{
   if(!user||PREVIEW||user.commissioning_only)return;
   const abort=new AbortController();
   let pending=false;
   const updateDuty=async()=>{
     if(pending||document.hidden)return;
     pending=true;
     try{
       const profile=await api('me/',{signal:abort.signal});
       if(!abort.signal.aborted)setUser(current=>current?.organization_id===profile.organization_id?profile:current);
     }catch{/* API diagnostics retain poll failures. */}
     finally{pending=false;}
   };
   const period=setInterval(updateDuty,15000);
   const boundaries=[user.duty_shift?.end,user.next_duty_shift?.start].filter(Boolean).map(x=>+new Date(x)).filter(x=>x>Date.now());
   const delay=boundaries.length?Math.min(...boundaries)-Date.now()+100:Infinity;
   const boundary=delay<=2147483647?setTimeout(updateDuty,delay):null;
   window.addEventListener('focus',updateDuty);
   document.addEventListener('visibilitychange',updateDuty);
   return()=>{
     abort.abort();
     clearInterval(period);
     clearTimeout(boundary);
     window.removeEventListener('focus',updateDuty);
     document.removeEventListener('visibilitychange',updateDuty);
   };
 },[user?.id,user?.organization_id,user?.commissioning_only,user?.duty_shift?.end,user?.next_duty_shift?.start]);
 const openedTicket=useRef(null);
 useEffect(()=>{
   const id=new URLSearchParams(location.search).get('ticket');
   if(!id||openedTicket.current===id||loading)return;
   const ticket=data.tickets.find(t=>String(t.id)===id);
   if(ticket){openedTicket.current=id;setPage('tickets');setModal({type:'tickets',item:ticket});}
 },[data.tickets,loading]);
 useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),6500);return()=>clearTimeout(timer);},[notice]);
 const go=p=>{if(pageFromHash()!==p)history.pushState(null,'','#'+p);setPage(p);setMenu(false);setSearch('');setModal(null);window.scrollTo({top:0});};
 const discuss=(kind,row)=>{setChatQuote({kind,id:row.id,title:kind==='ticket'?row.title:row.part});go('chat');};
 const openReference=ref=>{const kind=ref?.kind;const row=(kind==='ticket'?data.tickets:data.parts).find(v=>v.id===ref?.id);if(!row)return;go(kind==='ticket'?'tickets':'parts');setModal({type:kind==='ticket'?'tickets':'parts',item:row});};
 const logoutNow=async()=>{try{
   let sub=null;
   try{
     if('serviceWorker' in navigator){
       const registration=await navigator.serviceWorker.getRegistration('/');
       sub=await registration?.pushManager.getSubscription();
     }
   }catch{}
   await api('logout/',{method:'POST',body:{push_endpoint:sub?.endpoint||''}});
   if(sub)await sub.unsubscribe().catch(()=>{});
   location.href='/login/';
 }catch(e){setError(e.message);}};
 const open=(type,item={})=>setModal({type,item});const q=search.toLocaleLowerCase('ru').trim();const matches=(...texts)=>!q||texts.some(t=>String(t||'').toLocaleLowerCase('ru').includes(q));
 const grouped=useMemo(()=>{const groups={};for(const b of data.buildings){const lifts=data.elevators.filter(e=>e.building===b.id&&(showArchived||e.active));const shown=matches(b.street,b.house,b.address,b.name)?lifts:lifts.filter(e=>matches(e.factory_number,e.inventory_number,e.manufacturer,e.model));if(!shown.length&&q)continue;const key=b.street||'Адреса без указанной улицы';(groups[key]||=[]).push({...b,lifts:shown});}return Object.entries(groups).sort(([a],[b])=>a.localeCompare(b,'ru'));},[data,q,showArchived]);
 const employee=id=>data.technicians.find(t=>t.id===Number(id))?.full_name||'Не назначен';const elevator=id=>data.elevators.find(e=>e.id===Number(id));
 const heading=nav.find(n=>n[0]===page)?.[1]||'Главная';
 if(!user&&loading)return <div className="boot"><ArrowUp/><h1>Лифт Контроль</h1><p>Загрузка рабочего пространства…</p></div>;
 if(!user)return <div className="boot"><h1>Вход в Лифт Контроль</h1><p className="error">{error||'Нет доступа к организации.'}</p><a className="button primary" href="/login/">Войти</a><button onClick={load}>Повторить</button><section className="panel settings-panel"><OrganizationControls/></section></div>;
 return <><div className={'shade '+(menu?'open':'')} onClick={()=>setMenu(false)}/><aside ref={sidebar} className={'sidebar '+(menu?'open':'')} aria-label="Боковое меню" onKeyDown={e=>{if(e.key==='Escape')setMenu(false);}}><a className="brand" href="#home"><span className="brand-icon"><ArrowUp size={28}/></span><span><b>Лифт Контроль</b><small>СИСТЕМА УПРАВЛЕНИЯ</small></span></a><div className="organization"><Building2 size={24}/><div><b>{user.organization}</b><small>Благовещенск</small>{user.organizations?.length>1&&<select aria-label="Организация" value={user.organization_id} onChange={e=>switchOrganization(e.target.value).catch(err=>setError(err.message))}>{user.organizations.map(o=><option value={o.id} key={o.id}>{o.name}</option>)}</select>}</div></div><button className="side-profile" onClick={()=>go('settings')}><span className="avatar">{user.name.slice(0,1)}</span><span><b>{user.name}</b><small>{user.role==='MECHANIC'&&user.on_duty?'Дежурный механик':(roles[user.role]||user.role)}</small>{PREVIEW&&<em>Демонстрационный профиль</em>}</span><ChevronRight size={16}/></button><span className="nav-caption">УПРАВЛЕНИЕ</span><nav>{nav.filter(n=>!['settings','commissioning-chat'].includes(n[0])&&(n[0]!=='lift-documents'||user.can_manage_lift_documents)&&(n[0]==='commissioning'?user.can_commissioning:(n[0]==='notifications'||!user.commissioning_only))).map(([id,label,Icon])=><button className={page===id||(id==='commissioning'&&page==='commissioning-chat')?'active':''} key={id} onClick={()=>go(id)}><Icon size={20}/><span>{label}</span><UnreadBadge count={sectionCount(id)}/></button>)}</nav><div className="side-bottom"><button className={page==='settings'?'active':''} onClick={()=>go('settings')}><Settings size={20}/>Настройки</button><small>{PREVIEW?'Предпросмотр интерфейса':'Лифт Контроль Web'} · 0.13.18</small></div></aside>
 <div className="shell" inert={menu&&innerWidth<=860?true:undefined}><header className="topbar"><button ref={menuButton} className="icon-button hamburger" aria-label="Открыть боковое меню" aria-expanded={menu} onClick={()=>setMenu(true)}><Menu size={23}/></button>{!user.commissioning_only?<button type="button" className="topbar-duty" onClick={()=>go('duty')} aria-label={user.duty_shift?'Дежурный: '+user.duty_shift.technician_name:'Дежурный не назначен'}><span className={'duty-indicator '+(user.duty_shift?'assigned':'')} aria-hidden="true"/><span className="topbar-duty-text"><small>{user.on_duty?'Вы дежурите':'Дежурный механик'}</small><b>{user.duty_shift?.technician_name||'Не назначен'}</b>{user.duty_shift&&<small className="topbar-duty-end">До {new Date(user.duty_shift.end).toLocaleString('ru-RU',{timeZone:user.timezone||'Asia/Chita',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</small>}</span></button>:<span className="topbar-spacer"/>}{!PREVIEW&&<button className="icon-button quick-chat unread-shortcut" aria-label="Центр уведомлений" title="Центр уведомлений" onClick={()=>go('notifications')}><Bell size={23}/><UnreadBadge count={counts.unread}/></button>}{(!inCommissioning||user.can_commissioning&&user.notification_counts_api===1)&&<button className="icon-button quick-chat unread-shortcut" aria-label={inCommissioning?'Открыть чат наладчиков':'Открыть чат'} title={inCommissioning?'Чат наладчиков':'Чат'} onClick={()=>go(inCommissioning?'commissioning-chat':'chat')}><MessageSquare size={23}/><UnreadBadge count={inCommissioning?counts.commissioning_chat:sectionCount('chat')}/></button>}</header><main>
 {error&&<div className="error" role="alert">{error} <button onClick={load}>Повторить</button> <a href="/login/">Войти</a></div>}
 {!PREVIEW&&['home','tickets'].includes(page)&&<DutyStatus key={user.organization_id} user={user} data={data} onChanged={load} compact/>}
 {page==='home'&&<><Heading kicker="РАБОЧЕЕ ПРОСТРАНСТВО" title="Главная" description="Обслуживание лифтов и работа команды"><button onClick={load}><RefreshCw size={17}/>Обновить</button>{(PREVIEW||user.can_create_ticket)&&<button className="primary" onClick={()=>open('tickets')}><Plus size={17}/>Новая заявка</button>}{user.can_manage&&<button onClick={()=>{go('tasks');setTaskCreateRequested(true);}}><Plus size={17}/>Доп. задание</button>}<button onClick={()=>go('tasks')}><ClipboardList size={17}/>Личные задания</button></Heading><div className="metrics">{[['Лифтов на обслуживании',data.elevators.filter(e=>e.active).length,'objects'],['Открытых заявок',data.tickets.filter(t=>!['DONE','CANCELED'].includes(t.status)).length,'tickets'],['Запросов запчастей',data.parts.filter(p=>p.status==='NEW').length,'parts'],['Механиков',data.technicians.filter(t=>t.active).length,'technicians']].map(([label,value,id])=><button key={id} onClick={()=>go(id)}><small>{label}</small><strong>{value}</strong><ChevronRight size={18}/></button>)}</div><div className="dashboard-columns"><section className="panel"><header className="panel-heading"><h2>Требуют внимания</h2><button onClick={()=>go('tickets')}>Все заявки →</button></header>{data.tickets.filter(t=>!['DONE','CANCELED'].includes(t.status)).slice(0,5).map(t=><button className="list-row" onClick={()=>open('tickets',t)} key={t.id}><span className="ticket-num">#{t.id}</span><span><b>{t.title}</b><small>{t.address} · {(t.elevator_label||t.elevator_factory_number)}</small></span><Badge value={t.status}/>{t.priority==='ENTRAPMENT'&&<Badge value="ENTRAPMENT">Застревание</Badge>}</button>)}{!data.tickets.length&&<p className="empty">Открытых заявок пока нет</p>}</section><section className="panel"><header className="panel-heading"><h2>Планирование</h2></header><button className="feature-link" onClick={()=>go('duty')}><CalendarDays/><div><b>График дежурств</b><p>План на месяц, очередь механиков, сутки и подмены</p></div><ChevronRight/></button><button className="feature-link" onClick={()=>go('parts')}><Package/><div><b>Заявки на запчасти</b><p>От запроса механика до выдачи</p></div><ChevronRight/></button><button className="feature-link" onClick={()=>go('chat')}><MessageSquare/><div><b>Чат</b><p>Рабочие вопросы и передача информации</p></div><ChevronRight/></button></section></div></>}
 {page==='objects'&&<><Heading kicker="ОБЪЕКТЫ" title="Лифты" description="Улица → дом → лифт"><>{user.can_manage&&<><button onClick={()=>open('buildings')}><Plus size={17}/>Добавить дом</button><button className="primary" onClick={()=>open('elevators')}><Plus size={17}/>Добавить лифт</button></>}</></Heading><div className="toolbar"><div className="search-box"><Search size={19}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Улица, дом, заводской номер" aria-label="Поиск лифтов"/></div><small>{data.buildings.length} домов · {data.elevators.length} лифтов</small><label><input type="checkbox" checked={showArchived} onChange={e=>setShowArchived(e.target.checked)}/>Показывать архив</label></div><div className="address-tree">{grouped.map(([street,buildings])=><section className="panel street" key={street}><button className="street-heading" aria-expanded={!!streets[street]||!!q} onClick={()=>setStreets(s=>({...s,[street]:!s[street]}))}><span className="street-icon"><Building2/></span><span><b>{street}</b><small>{buildings.length} домов · {buildings.reduce((n,b)=>n+b.lifts.length,0)} лифтов</small></span>{streets[street]||q?<ChevronDown/>:<ChevronRight/>}</button>{(streets[street]||q)&&<div className="houses">{buildings.map(b=><div className="house" key={b.id}><button className="house-heading" aria-expanded={!!houses[b.id]||!!q} onClick={()=>setHouses(s=>({...s,[b.id]:!s[b.id]}))}><span><b>{b.street&&b.house?'Дом '+b.house:b.address}</b><small>{b.name} · {b.lifts.length} лифтов</small></span>{houses[b.id]||q?<ChevronDown size={18}/>:<ChevronRight size={18}/>}</button>{(houses[b.id]||q)&&user.can_manage&&<div className="actions"><button onClick={()=>open('buildings',b)}>Изменить дом</button><button className="danger" onClick={()=>open('delete-building',b)}>Удалить дом</button></div>}{(houses[b.id]||q)&&<div className="lift-grid">{b.lifts.map(l=><button className="lift-tile" key={l.id} onClick={()=>open('lift',l)}><span className="lift-glyph">↕</span><span><b className="lift-entrance">{entranceLabel(l)}</b><small>Учётный номер · {inventoryLabel(l)||'Не указан'}</small><small>{[l.factory_number&&('Зав. '+l.factory_number),l.manufacturer,l.model].filter(Boolean).join(' · ')}</small><small>{employee(l.assigned_technician)}</small></span><Badge value={l.stopped_at?'STOPPED':l.active?'DONE':'CANCELED'}>{l.stopped_at?'Лифт остановлен':l.active?'На обслуживании':'Архив'}</Badge></button>)}</div>}</div>)}</div>}</section>)}{!grouped.length&&<p className="empty">Лифты не найдены</p>}</div></>}
 {page==='duty'&&<Duty key={user.organization_id} data={data} user={user} onChanged={load}/>}
 {page==='tickets'&&<><Heading kicker="ДИСПЕТЧЕРСКАЯ" title="Заявки" description="Обращения, выполненные работы и фотографии ремонта">{(PREVIEW||user.can_create_ticket)&&<button className="primary" onClick={()=>open('tickets')}><Plus size={17}/>Новая заявка</button>}</Heading><section className="panel"><div className="table-wrap"><table><thead><tr><th>Заявка</th><th>Адрес и лифт</th><th>Исполнитель</th><th>Статус</th><th/></tr></thead><tbody>{data.tickets.filter(t=>matches(t.title,t.id,t.address,(t.elevator_label||t.elevator_factory_number))).map(t=><tr key={t.id}><td><b>#{t.id} · {t.title}</b><small>{fmt(t.created_at)}</small></td><td>{t.address}<small>{(t.elevator_label||t.elevator_factory_number)}</small></td><td>{employee(t.assigned_to)}</td><td><Badge value={t.status}/>{t.priority==='ENTRAPMENT'&&<Badge value="ENTRAPMENT">Застревание</Badge>}</td><td><button onClick={()=>open('tickets',t)}>Открыть</button></td></tr>)}</tbody></table></div>{!data.tickets.length&&<p className="empty">Заявок пока нет</p>}</section></>}
 {page==='parts'&&<><Heading kicker="СНАБЖЕНИЕ" title="Запчасти" description="Заявки механиков: адрес, лифт, нужная деталь и статус"><button className="primary" onClick={()=>open('parts')}><Plus size={17}/>Запросить запчасть</button></Heading><div className="parts-grid">{data.parts.filter(p=>matches(p.part,p.address,(p.elevator_label||p.elevator_factory_number))).map(p=><button className="panel part-card" key={p.id} onClick={()=>open('parts',p)}><header><small>ЗАПРОС #{p.id}</small><Badge value={p.status}/></header><h2>{p.part}</h2><strong className="quantity">{p.quantity} шт.</strong><p>{p.address}</p><p className="muted">Лифт {(p.elevator_label||p.elevator_factory_number)}</p><footer><span>{p.author_name}</span><small>{fmt(p.created_at)}</small></footer></button>)}{!data.parts.length&&<div className="panel empty">Запросов пока нет. Механик выбирает дом и лифт, затем указывает нужную деталь.</div>}</div></>}
 {page==='chat'&&!user.commissioning_only&&<ChatMedia key={user.organization_id} user={user} onRead={countsChanged} data={data} initialMessage={notificationTarget?.type==='chat'?notificationTarget.id:null} onMessageOpened={()=>setNotificationTarget(null)} initialReference={chatQuote} onReferenceChange={setChatQuote} onOpenReference={openReference}/>}
 {page==='tasks'&&<Tasks data={data} user={user} initialTask={notificationTarget?.type==='task'?notificationTarget.id:null} onTaskOpened={()=>setNotificationTarget(null)} onChanged={load} createRequested={taskCreateRequested} onCreateHandled={()=>setTaskCreateRequested(false)}/>}
 {page==='technicians'&&<><Heading kicker="КОМАНДА" title="Механики" description="Сотрудники и закреплённые лифты"><label><input type="checkbox" checked={showArchived} onChange={e=>setShowArchived(e.target.checked)}/>Показывать архив</label>{user.can_manage_access&&<button onClick={()=>{go('settings');setTimeout(()=>document.getElementById('employee-create')?.scrollIntoView({block:'start'}),100);}}><Plus size={17}/>Добавить сотрудника</button>}</Heading><div className="people-grid">{data.technicians.filter(t=>(showArchived||t.active)&&matches(t.full_name)).map(t=><section className="panel person-card" key={t.id}><span className="avatar">{t.full_name.split(' ').map(x=>x[0]).slice(0,2).join('')}</span><h2>{t.full_name}</h2><p>{t.role_display||t.role}</p><Badge value={t.active?'DONE':'CANCELED'}>{t.active?'Работает':'Неактивен'}</Badge><p>{data.elevators.filter(l=>l.assigned_technician===t.id).length} закреплённых лифтов</p>{user.can_manage_access&&<div className="actions"><button onClick={()=>open('technicians',t)}>Изменить</button>{t.active&&<button className="danger" onClick={()=>open('archive-technicians',t)}>Удалить из списка</button>}</div>}</section>)}</div></>}
 {page==='commissioning'&&user.can_commissioning&&<Commissioning key={user.organization_id} user={user} onOpenChat={user.notification_counts_api===1?()=>go('commissioning-chat'):null} chatCount={counts.commissioning_chat} initialProject={notificationTarget?.type==='commissioning'?notificationTarget.id:null} onProjectOpened={()=>setNotificationTarget(null)}/>}
 {page==='commissioning-chat'&&user.can_commissioning&&<ChatMedia key={'commissioning-'+user.organization_id} user={user} commissioning onRead={countsChanged} onBack={()=>go('commissioning')} initialMessage={notificationTarget?.type==='commissioning_chat'?notificationTarget.id:null} onMessageOpened={()=>setNotificationTarget(null)}/>}
  {page==='notifications'&&<Notifications key={user.organization_id} user={user} initialEntrapment={counts.entrapment>0} onRead={countsChanged} onOpen={async(type,id)=>{
   if(type==='ticket'||type==='ticket_delivery'){
     go('tickets');setModal({type:'tickets',item:data.tickets.find(t=>t.id===id)||{id}});
   }else if(type==='inspection'){
     try{const lift=elevator(id)||await api('elevators/'+id+'/');
       go('objects');setModal({type:'lift',item:lift,initialTab:'inspections'});}
     catch(error){setError(error.message);}
   }else if(type==='part'){
     try{const part=await api('parts/'+id+'/');go('parts');setModal({type:'parts',item:part});}
     catch(error){setError(error.message);}
   }else if(type==='commissioning_chat'){
     go('commissioning-chat');setNotificationTarget({type,id});
   }else if(['commissioning','chat','task'].includes(type)){
     go(type==='task'?'tasks':type);setNotificationTarget({type,id});
   }
 }}/>}
 {page==='lift-documents'&&user.can_manage_lift_documents&&<LiftDocuments key={user.organization_id} user={user} lifts={data.elevators}/>}
 {page==='documents'&&<><Heading kicker="ОБЩАЯ БИБЛИОТЕКА" title="Документация" description="Единая библиотека с автоматическим подбором для лифтов">{user.can_manage&&<button className="primary" onClick={()=>open('documents')}><Plus size={17}/>Добавить документ</button>}</Heading><div className="document-grid">{data.documents.filter(d=>matches(d.title,d.manufacturer,d.model,d.documentation_tags)).map(d=><section className="panel document" key={d.id}><BookOpen size={28}/><h2>{d.title}</h2>{user.can_manage&&<button onClick={()=>open('documents',d)}>Редактировать</button>}{user.can_manage_access&&<button className="danger" onClick={()=>open('archive-documents',d)}>Удалить документ</button>}<p>{d.documentation_tags||[d.manufacturer,d.model||'Все модели производителя'].filter(Boolean).join(' · ')}</p>{d.url?<a className="button" href={d.url} target="_blank" rel="noreferrer">Скачать PDF</a>:<small>Демонстрационная карточка без файла</small>}</section>)}</div></>}
 {page==='media'&&<MediaLibrary key={user.organization_id} user={user} onTicket={id=>open('tickets',data.tickets.find(t=>t.id===id)||{id})}/>}
 {page==='reports'&&<><Heading kicker="АНАЛИТИКА" title="Отчёты" description="Показатели по загруженным данным организации"><button onClick={()=>csv('LiftControl-tickets.csv',[['Заявка','Адрес','Лифт','Статус','Выполненные работы'],...data.tickets.map(t=>[t.id,t.address,(t.elevator_label||t.elevator_factory_number),t.status,t.repair])])}><Download size={17}/>Выгрузить заявки</button></Heading><div className="metrics">{[['Всего заявок',data.tickets.length],['Выполнено',data.tickets.filter(t=>t.status==='DONE').length],['Работ ТО выполнено',data.maintenance.filter(t=>t.completed_at).length],['Запчастей ожидается',data.parts.filter(t=>['NEW','APPROVED','ORDERED'].includes(t.status)).length]].map(([n,v])=><div key={n}><small>{n}</small><strong>{v}</strong></div>)}</div><p className="notice">Журнал отдельного лифта доступен в его карточке. Для печати выберите нужный период.</p></>}
 {page==='settings'&&<><Heading kicker="РАБОЧЕЕ ПРОСТРАНСТВО" title="Настройки" description="Оформление, учётная запись и диагностика"/><section className="panel settings-panel"><OrganizationControls user={user} data={data} onChanged={load}/>{!user.commissioning_only&&<PushControls user={user}/>}<PwaControls/><NotificationPreferences key={user.organization_id} user={user}/><UpdateControls user={user}/><div className="setting-row"><div><h2>Тема оформления</h2><p>Выбор сохраняется на этом устройстве</p></div><select aria-label="Тема оформления" value={theme} onChange={e=>setTheme(e.target.value)}>{Object.entries(themes).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div><div className="setting-row"><div><h2>{user.name}</h2><p>{roles[user.role]} · {user.organization}</p></div><span className="avatar">{user.name[0]}</span></div>{PREVIEW&&<div className="setting-row"><div><h2>Проверка ролей в макете</h2><p>В рабочей версии права назначаются на сервере.</p></div><select aria-label="Роль в макете" value={user.role} onChange={e=>setUser(previewRole(e.target.value))}>{Object.entries(roles).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></div>}<div className="setting-row"><div><h2>Выгрузка чата</h2><p>Доступна только администратору. Остальные сотрудники читают и пишут сообщения.</p></div><ShieldCheck/></div><div className="setting-row"><div><h2>Диагностические логи</h2><p>До 200 событий текущего сеанса, без паролей, фото и текста сообщений.</p></div><div className="actions"><button onClick={()=>download('LiftControl-diagnostics.json',JSON.stringify({version:'0.13.18',preview:PREVIEW,events:diagnosticEvents},null,2))}><Download size={17}/>Скачать</button><button onClick={async()=>{try{await navigator.clipboard.writeText(JSON.stringify({version:'0.13.18',events:diagnosticEvents},null,2));setNotice('Логи скопированы');}catch{setNotice('Не удалось скопировать. Используйте «Скачать».');}}}><Copy size={17}/>Копировать</button></div></div>{!PREVIEW&&user.is_superuser&&<div className="setting-row"><div><h2>Создание учётной записи</h2><p>Создайте сотруднику логин. Доступ к компании выдаётся приглашением выше.</p></div><a className="button" href="/admin/auth/user/">Управление доступом</a></div>}<div className="setting-row"><div><h2>{PREVIEW?'Предпросмотр':'Рабочая система'}</h2><p>{PREVIEW?'Демонстрационные данные. Записи, фото и сообщения сбрасываются после перезагрузки.':'Данные и вложения сохраняются на сервере организации.'}</p></div>{!PREVIEW&&<button onClick={logoutNow}><LogOut size={17}/>Выйти</button>}</div></section></>}
 <footer className="page-footer">{PREVIEW?'Макет интерфейса · демоданные · изменения до перезагрузки':'Лифт Контроль · '+user.organization} <span>Web 0.13.18</span></footer></main></div>
 {modal?.type==='delete-building'
   ? <DeleteBuilding building={modal.item} onClose={()=>setModal(null)} onSaved={load}/>
   : modal&&modal.type==='lift'
   ? <LiftCard key={modal.item.id+':'+(modal.initialTab||'passport')} initialTab={modal.initialTab} lift={modal.item} data={data} user={user} onClose={()=>setModal(null)} onEdit={open}/>
   : modal&&modal.type==='tickets'&&!PREVIEW
     ? <TicketWorkflow key={'ticket-'+(modal.item?.id||'new')} item={modal.item} data={data} user={user}
         onClose={()=>setModal(null)} onSaved={load} onDiscuss={()=>discuss('ticket',modal.item)} onOpenLift={id=>{const lift=elevator(id);if(lift)open('lift',lift);}}/>
     : modal?.type.startsWith('archive-')?<ArchiveDialog type={modal.type.slice(8)} item={modal.item} data={data} onClose={()=>setModal(null)} onSaved={load}/>
     : modal&&<Editor key={modal.type+'-'+(modal.item?.id||'new')} type={modal.type} item={modal.item}
         data={data} user={user} onClose={()=>setModal(null)} onSaved={load} onDiscuss={row=>discuss('part',row)}/>}
 {notice&&<button className="toast" onClick={()=>setNotice('')}>{notice}</button>}
 </>;
}
const maintenanceNames={TO1:'ТО-1',TO2:'ТО-2',REPAIR:'Ремонт',INSPECTION:'Осмотр'};

function MaintenancePlan({lift, rows, onEdit}) {
 return <>
   {lift.active && <div className="actions"><button onClick={()=>onEdit('maintenance',{elevator:lift.id,technician:lift.assigned_technician})}><Plus size={16}/>Запланировать работу</button></div>}
   {rows.map(row=><button className="list-row" key={row.id} onClick={()=>onEdit('maintenance',row)}>
     <span><b>{maintenanceNames[row.kind] || row.kind} · {fmt(row.planned_date)}</b><small>{row.technician_name || 'Исполнитель не назначен'}</small></span>
     <ChevronRight size={16}/>
   </button>)}
   {!rows.length && <p className="empty">Запланированных работ нет.</p>}
 </>;
}
function DeleteBuilding({building,onClose,onSaved}) {
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function remove() {
   setBusy(true);
   try {
     await api('buildings/'+building.id+'/',{method:'DELETE'});
     await onSaved();
     onClose();
   } catch (err) {
     setError(err.message);
     setBusy(false);
   }
 }
 const occupied=building.elevators_count ?? building.lifts?.length ?? 0;
 return <Dialog title="Удалить дом" onClose={onClose}>
   <p>{building.address}</p>
   {occupied>0&&<p className="notice">Сначала перенесите лифты на другой адрес, включая архивные.</p>}
   {error&&<p role="alert" className="error">{error}</p>}
   <div className="actions">
     <button type="button" disabled={busy} onClick={onClose}>Отмена</button>
     <button type="button" disabled={busy||occupied>0} className="danger" onClick={remove}>Удалить дом</button>
   </div>
 </Dialog>;
}
function LiftCard({lift,data,user,onClose,onEdit,initialTab='passport'}){
 const [tab,setTab]=useState(initialTab),[docs,setDocs]=useState([]),[error,setError]=useState('');
 useEffect(()=>{api('elevators/'+lift.id+'/documents/').then(setDocs).catch(e=>setError(e.message));},[lift.id]);
 const maintenance=data.maintenance.filter(row=>row.elevator===lift.id);
 const openJournalSource=row=>{
   const type=row.source==='ticket'?'tickets':'maintenance';
   const item=(type==='tickets'?data.tickets:maintenance).find(entry=>entry.id===row.source_id);
   if(item){onEdit(type,item);return;}
   api(type+'/'+row.source_id+'/').then(entry=>onEdit(type,entry)).catch(e=>setError(e.message));
 };
 const tabs=[
   ['passport','Паспорт'],
   ['tickets','Заявки'],
   ['plan','План ТО'],
   ['journal','Журнал ТО'],
   ['documents','Документация'],
   ['inspections','Освидетельствование'],
   ['media','Фото и видео'],
 ];
 const passport=[
   ['Учётный номер',inventoryLabel(lift)],
   ['Заводской номер',lift.factory_number],
   ['Производитель',lift.manufacturer],
   ['Модель',lift.model],
   ['Остановок',lift.floors],
   ['Этажность здания',lift.building_floors],
   ['Грузоподъёмность',lift.capacity_kg],
   ['Механик',data.technicians.find(t=>t.id===lift.assigned_technician)?.full_name],
   ...(lift.documentation_tags?[['Теги документации',lift.documentation_tags]]:[]),
 ];
 return <Dialog title={'Лифт '+(lift.factory_number||lift.inventory_number||lift.id)} onClose={onClose} wide>
   <p className="subtitle">{lift.address}</p>
   <div className="tabs" aria-label="Разделы карточки лифта">
     {tabs.map(([id,label])=><button className={tab===id?'selected':''} key={id}
       aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}
   </div>
   {error&&<p className="error">{error}</p>}
   {tab==='passport'&&<>
     {lift.stopped_at&&<div className="notice"><Badge value="STOPPED"/><p>{lift.stop_reason}</p></div>}
     <h2 className="lift-entrance">{entranceLabel(lift)}</h2>
     <div className="detail-grid">{passport.map(([label,value])=><div key={label}>
       <small>{label}</small><b>{value||'—'}</b>
     </div>)}</div>
     {lift.notes&&<p className="notice">{lift.notes}</p>}
     <div className="actions">
       {user.can_manage&&<button onClick={()=>onEdit('elevators',lift)}>Изменить сведения</button>}
       {(PREVIEW||user.can_create_ticket)&&<button onClick={()=>onEdit('tickets',{elevator:lift.id})}><Plus size={16}/>Создать заявку</button>}
       <button onClick={()=>onEdit('parts',{elevator:lift.id})}><Package size={16}/>Нужна запчасть</button>
       {user.can_manage_access&&lift.active&&<button className="danger" onClick={()=>onEdit('archive-elevators',lift)}>Удалить из списка</button>}
     </div>
   </>}
   {tab==='tickets'&&data.tickets.filter(t=>t.elevator===lift.id).map(t=>
     <button className="list-row" key={t.id} onClick={()=>onEdit('tickets',t)}>
       <b>#{t.id} · {t.title}</b><Badge value={t.status}/>
       {t.priority==='ENTRAPMENT'&&<Badge value="ENTRAPMENT">Застревание</Badge>}
     </button>)}
   {tab==='plan'&&<MaintenancePlan lift={lift} rows={maintenance.filter(row=>!row.completed_at)} onEdit={onEdit}/>}
   {tab==='inspections'&&<LiftInspections lift={lift}/>}
   {tab==='journal'&&<MaintenanceJournal lift={lift} onOpenSource={openJournalSource}/>}
   {tab==='media'&&<MediaLibrary key={lift.id} user={user} elevator={lift.id}
     onTicket={id=>onEdit('tickets',data.tickets.find(t=>t.id===id)||{id})}/>}
   {tab==='documents'&&<>
     <p className="notice">Подобрано из общей библиотеки по тегам документа или производителю и модели. Загрузка документов доступна в разделе «Документация».</p>
     {docs.map(d=><div className="list-row" key={d.id}>
       <BookOpen/><span><b>{d.title}</b><small>{d.documentation_tags||[d.manufacturer,d.model||'Все модели'].filter(Boolean).join(' · ')}</small></span>
       {d.url?<a className="button" href={d.url} target="_blank" rel="noreferrer">PDF</a>:<small>Демо</small>}
     </div>)}
     {!docs.length&&<p className="empty">Подходящих документов пока нет</p>}
   </>}
 </Dialog>;
}
function Chat({user}){
 const [messages,setMessages]=useState([]),[text,setText]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[exporting,setExporting]=useState(false);const today=new Date().toLocaleDateString('en-CA',{timeZone:user.timezone});const end=useRef();
 const refresh=useCallback(async()=>{try{setMessages(await api('chat/'));setError('');}catch(e){setError(e.message);}},[]);
 useEffect(()=>{refresh();const id=setInterval(()=>{if(!document.hidden)refresh();},5000);return()=>clearInterval(id);},[refresh]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'});},[messages.length]);
 const send=async e=>{e.preventDefault();if(!text.trim()||busy)return;setBusy(true);try{await api('chat/',{method:'POST',body:{body:text.trim()}});setText('');await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <><Heading kicker="ОБЩЕНИЕ" title="Чат" description="Общий рабочий чат организации">{user.can_export_chat&&<button onClick={()=>setExporting(true)}><Download size={17}/>Выгрузить чат</button>}</Heading><section className="panel chat-panel"><header className="panel-heading"><div><b>{user.organization}</b><small>Последние 200 сообщений · обновление каждые 5 секунд</small></div><Badge value="DONE">Общий чат</Badge></header><div className="messages">{messages.map(m=><article className={'message '+(m.author===user.id?'own':'')} key={m.id}><header><b>{m.author_name}</b><time>{new Date(m.created_at).toLocaleString('ru-RU',{timeZone:user.timezone,dateStyle:'short',timeStyle:'short'})}</time></header><p>{m.body}</p></article>)}{!messages.length&&<p className="empty">Начните рабочее обсуждение</p>}<div ref={end}/></div>{error&&<p className="error" role="alert">{error}</p>}<form className="composer" onSubmit={send}><textarea value={text} maxLength={4000} onChange={e=>setText(e.target.value)} placeholder="Написать команде…" aria-label="Сообщение команде" required/><button className="primary" disabled={busy||!text.trim()}><Send size={19}/><span>Отправить</span></button></form></section><p className="muted small">Выгрузка переписки доступна только администратору.</p>{exporting&&<Dialog title="Выгрузить чат" onClose={()=>setExporting(false)}><form onSubmit={async e=>{e.preventDefault();const fd=new FormData(e.currentTarget);setBusy(true);try{download('LiftControl-chat.csv',await api(`chat/export/?from=${fd.get('from')}&to=${fd.get('to')}`,{blob:true}));setExporting(false);}catch(err){setError(err.message);}finally{setBusy(false);}}}><div className="form-grid"><Field label="С"><input type="date" name="from" defaultValue={today.slice(0,7)+'-01'} required/></Field><Field label="По"><input type="date" name="to" defaultValue={today} required/></Field></div><p className="muted">CSV за выбранные даты, до 366 дней за выгрузку.</p><footer className="form-actions"><button type="button" onClick={()=>setExporting(false)}>Отмена</button><button className="primary" disabled={busy}>Скачать CSV</button></footer></form></Dialog>}</>;
}

