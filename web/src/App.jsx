import React, {useEffect, useState} from 'react';
import { Activity, Building2, CircleAlert, Gauge, Users, Wrench } from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

function Card({title, value, icon:Icon, danger=false}) { return <div className="card"><div className="card-top"><span>{title}</span><Icon size={20}/></div><strong className={danger?'danger':''}>{value ?? '—'}</strong></div> }

export default function App(){
  const [stats,setStats]=useState(null); const [tickets,setTickets]=useState([]); const [elevators,setElevators]=useState([]); const [error,setError]=useState('');
  useEffect(()=>{ Promise.all([fetch(`${API}/dashboard/`).then(r=>r.json()),fetch(`${API}/tickets/`).then(r=>r.json()),fetch(`${API}/elevators/`).then(r=>r.json())]).then(([s,t,e])=>{setStats(s);setTickets(t.results||t);setElevators(e.results||e)}).catch(()=>setError('Не удалось подключиться к серверу LiftControl')); },[]);
  return <div className="shell">
    <aside><div className="brand"><Gauge/> LiftControl</div><nav><b>Обзор</b><span>Лифты</span><span>Заявки</span><span>ТО</span><span>Механики</span><span>Объекты</span></nav></aside>
    <main><header><div><h1>Панель управления</h1><p>Лифты, заявки и техническое обслуживание</p></div><button>+ Новая заявка</button></header>
      {error&&<div className="error">{error}</div>}
      <section className="grid"><Card title="Лифтов" value={stats?.elevators} icon={Building2}/><Card title="Механиков" value={stats?.technicians} icon={Users}/><Card title="Открытых заявок" value={stats?.open_tickets} icon={Activity}/><Card title="Аварийных" value={stats?.emergency_tickets} icon={CircleAlert} danger/><Card title="ТО сегодня" value={stats?.maintenance_today} icon={Wrench}/></section>
      <section className="panel"><h2>Последние заявки</h2><div className="table"><div className="row head"><span>Адрес</span><span>Лифт</span><span>Заявка</span><span>Статус</span></div>{tickets.slice(0,8).map(t=><div className="row" key={t.id}><span>{t.address}</span><span>{t.elevator_factory_number}</span><span>{t.title}</span><span className={`status ${t.status?.toLowerCase()}`}>{t.status_display||t.status}</span></div>)}</div></section>
      <section className="panel"><h2>Лифты</h2><div className="table"><div className="row head"><span>Адрес</span><span>Зав. №</span><span>Модель</span><span>Механик</span></div>{elevators.slice(0,8).map(e=><div className="row" key={e.id}><span>{e.address}</span><span>{e.factory_number}</span><span>{e.manufacturer} {e.model}</span><span>{e.technician_name||'Не назначен'}</span></div>)}</div></section>
    </main></div>
}
