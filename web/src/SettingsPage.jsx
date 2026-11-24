import React,{useEffect,useRef,useState} from 'react';
import {UserRound,Bell,Palette,Building2,Users,Smartphone,Activity,ChevronRight,ArrowLeft,Download,Copy,LogOut,ShieldCheck} from 'lucide-react';
import {PREVIEW,diagnosticEvents,download,record} from './api';
import {roles} from './demo';
import {version} from '../package.json';
import OrganizationControls from './OrganizationControls';
import NotificationPreferences from './NotificationPreferences';
import PushControls from './PushControls';
import SoundControls from './SoundControls';
import PwaControls from './PwaControls';
import UpdateControls from './UpdateControls';
import './settings.css';

const sections=[
 {id:'profile',title:'Профиль',description:'Ваша учётная запись и выход',icon:UserRound},
 {id:'notifications',title:'Уведомления',description:'Включение, звуки и тихие часы',icon:Bell},
 {id:'appearance',title:'Оформление',description:'Тема и внешний вид',icon:Palette},
 {id:'organizations',title:'Организации',description:'Выбор компании и приглашения',icon:Building2},
 {id:'team',title:'Сотрудники и доступ',description:'Добавление сотрудников и права',icon:Users,manager:true},
 {id:'application',title:'Приложение и обновления',description:'PWA и обновление из GitHub',icon:Smartphone},
 {id:'diagnostics',title:'Диагностика',description:'Журнал для решения проблем',icon:Activity},
];
function route(){return location.hash.startsWith('#settings/')?location.hash.slice('#settings/'.length).split('/')[0]:'';}
export default function SettingsPage({user,data,onChanged,theme,onTheme,themes,onNotice,onLogout,onPreviewRole}){
 const visible=sections.filter(section=>!section.manager||user.can_manage_access);
 const resolve=id=>visible.some(section=>section.id===id)?id:'profile';
 const [active,setActive]=useState(()=>resolve(route())),[detail,setDetail]=useState(()=>!!route());
 const heading=useRef(),navigation=useRef(),initial=useRef(true);
 useEffect(()=>{
  const change=()=>{setActive(resolve(route()));setDetail(!!route());};
  change();
  window.addEventListener('hashchange',change);window.addEventListener('popstate',change);
  return()=>{window.removeEventListener('hashchange',change);window.removeEventListener('popstate',change);};
 },[user.can_manage_access]);
 useEffect(()=>{
  if(initial.current){initial.current=false;return;}
  if(detail)heading.current?.focus({preventScroll:true});
  else navigation.current?.querySelector('[aria-current=page]')?.focus({preventScroll:true});
  window.scrollTo({top:0});
 },[active,detail]);
 const choose=id=>{location.hash='settings/'+id;record('settings','section',id);};
 const current=visible.find(section=>section.id===active)||visible[0];
 const copyLogs=async()=>{
  try{await navigator.clipboard.writeText(JSON.stringify({version,events:diagnosticEvents},null,2));onNotice('Логи скопированы');}
  catch{onNotice('Не удалось скопировать. Используйте «Скачать».');}
 };
 const panel=(id,children)=><section key={id} hidden={id!==active} className="settings-section" aria-label={sections.find(section=>section.id===id).title}>{children}</section>;
 return <div className={'settings-page '+(detail?'settings-detail':'')}>
  <header className="settings-heading"><div><span className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>Настройки</h1><p>Личные параметры, работа команды и приложение</p></div><span className="settings-version">Версия {version}</span></header>
  <div className="settings-layout">
   <nav ref={navigation} className="settings-navigation" aria-label="Разделы настроек">
    {visible.map(({id,title,description,icon:Icon})=><button key={id} aria-current={active===id?'page':undefined} onClick={()=>choose(id)}>
     <span className="settings-menu-icon"><Icon size={20}/></span><span className="settings-menu-text"><b>{title}</b><small>{description}</small></span><ChevronRight size={17}/>
    </button>)}
   </nav>
   <div className="settings-content">
    <button className="settings-back" onClick={()=>{location.hash='settings';}}><ArrowLeft size={17}/>Все настройки</button>
    <div className="settings-section-heading"><h2 ref={heading} tabIndex={-1}>{current.title}</h2><p>{current.description}</p></div>
    <div className="settings-section-body">
     {panel('profile',<>
      <div className="setting-row"><div><div className="settings-profile"><span className="avatar">{user.name.slice(0,1)}</span><div><h2>{user.name}</h2><p>{roles[user.role]||user.role}</p></div></div><dl className="settings-facts"><div><dt>Организация</dt><dd>{user.organization}</dd></div><div><dt>Часовой пояс</dt><dd>{user.timezone||'По организации'}</dd></div></dl><p>Права и рабочие данные зависят от выбранной организации.</p><button className="settings-inline-link" onClick={()=>choose('organizations')}>Перейти к организациям<ChevronRight size={15}/></button></div></div>
      {PREVIEW&&<div className="setting-row"><div><h2>Проверка ролей в макете</h2><p>В рабочей версии права назначаются администратором.</p><label className="field">Роль в макете<select value={user.role} onChange={e=>onPreviewRole(e.target.value)}>{Object.entries(roles).map(([id,title])=><option key={id} value={id}>{title}</option>)}</select></label></div></div>}
      <div className="setting-row"><div className="settings-account-exit"><div><h2>{PREVIEW?'Предпросмотр':'Вход в систему'}</h2><p>{PREVIEW?'Вы работаете с демонстрационными данными.':'Выход завершит текущий сеанс на этом устройстве.'}</p></div>{!PREVIEW&&<button className="danger" onClick={onLogout}><LogOut size={17}/>Выйти</button>}</div></div>
     </>)}
     {panel('notifications',<><PushControls user={user}/><SoundControls user={user}/><NotificationPreferences key={user.organization_id} user={user}/></>)}
     {panel('appearance',<div className="setting-row"><div><h2>Тема оформления</h2><p>Выбор сохраняется на этом устройстве и действует во всех разделах панели.</p><label className="field settings-theme-field">Тема оформления<select aria-label="Тема оформления" value={theme} onChange={e=>onTheme(e.target.value)}>{Object.entries(themes).map(([id,title])=><option key={id} value={id}>{title}</option>)}</select></label><div className="settings-theme-preview" aria-hidden="true"><div/><span><b>Так выглядит ваша тема</b><small>Карточки, поля и кнопки используют единое оформление</small></span><span className="settings-theme-pill">Пример</span></div></div></div>)}
     {panel('organizations',<OrganizationControls section="organizations" user={user} data={data} onChanged={onChanged}/>)}
     {user.can_manage_access&&panel('team',<><OrganizationControls section="team" user={user} data={data} onChanged={onChanged}/>{!PREVIEW&&user.is_superuser&&<div className="setting-row"><div><h2>Расширенное управление доступом</h2><p>Служебное управление учётными записями владельцем сервера.</p><a className="button" href="/admin/auth/user/"><ShieldCheck size={17}/>Управление доступом</a></div></div>}</>)}
     {panel('application',<><PwaControls/><UpdateControls user={user}/></>)}
     {panel('diagnostics',<div className="setting-row"><div><h2>Диагностические логи</h2><p>При проблеме скачайте журнал и передайте его для разбора. В журнале — до 200 событий текущего сеанса, без паролей, фотографий и текста сообщений.</p><div className="settings-diagnostic-info"><Activity size={20}/><span>Лифт Контроль · {version}<small>{PREVIEW?'Демонстрационный режим':'Веб-панель и PWA'}</small></span></div><div className="actions"><button onClick={()=>download('LiftControl-diagnostics.json',JSON.stringify({version,preview:PREVIEW,events:diagnosticEvents},null,2))}><Download size={17}/>Скачать</button><button onClick={copyLogs}><Copy size={17}/>Копировать</button></div></div></div>)}
    </div>
   </div>
  </div>
 </div>;
}
