import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowUpRight, Building2, ClipboardList, Gauge,
  LayoutDashboard, LoaderCircle, RefreshCw, Search, ShieldCheck, Users, Wrench,
} from 'lucide-react';

const BASE = '/api';
const ADMIN = '/admin/core';
const SECTIONS = [
  { id: 'overview', title: 'Обзор', icon: LayoutDashboard },
  { id: 'elevators', title: 'Лифты', icon: Gauge },
  { id: 'tickets', title: 'Заявки', icon: ClipboardList },
  { id: 'maintenance', title: 'ТО', icon: Wrench },
  { id: 'technicians', title: 'Сотрудники', icon: Users },
  { id: 'buildings', title: 'Объекты', icon: Building2 },
];

const SCHEMAS = {
  buildings: {
    label: 'Объекты', model: 'building',
    columns: [['Адрес', x => x.address], ['Название', x => x.name],
      ['УК', x => x.management_company || '—'], ['Лифтов', x => x.elevators_count ?? 0]],
    search: x => [x.address, x.name, x.management_company],
  },
  elevators: {
    label: 'Лифты', model: 'elevator',
    columns: [['Адрес', x => x.address], ['Заводской №', x => x.factory_number],
      ['Модель', x => [x.manufacturer, x.model].filter(Boolean).join(' ') || '—'],
      ['Механик', x => x.technician_name || 'Не назначен'],
      ['Обслуживание', x => x.active ? 'Да' : 'Нет']],
    search: x => [x.address, x.factory_number, x.manufacturer, x.model, x.technician_name],
  },
  tickets: {
    label: 'Заявки', model: 'ticket',
    columns: [['Адрес', x => x.address], ['Лифт', x => x.elevator_factory_number],
      ['Заявка', x => x.title], ['Приоритет', x => x.priority_display || x.priority],
      ['Статус', x => x.status_display || x.status]],
    search: x => [x.address, x.elevator_factory_number, x.title, x.status_display],
  },
  maintenance: {
    label: 'Техническое обслуживание', model: 'maintenance',
    columns: [['Дата ТО', x => dateText(x.planned_date)], ['Адрес', x => x.address],
      ['Лифт', x => x.elevator_factory_number], ['Вид', x => x.kind_display || x.kind],
      ['Механик', x => x.technician_name || 'Не назначен']],
    search: x => [x.planned_date, x.address, x.elevator_factory_number, x.kind_display, x.technician_name],
  },
  technicians: {
    label: 'Сотрудники', model: 'technician',
    columns: [['Сотрудник', x => x.full_name], ['Должность', x => x.role_display || x.role],
      ['Статус', x => x.active ? 'Работает' : 'Неактивен']],
    search: x => [x.full_name, x.role_display],
  },
};

const dateText = value => value ? new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU') : '—';
const asRows = value => Array.isArray(value) ? value : Array.isArray(value?.results) ? value.results : [];

function Metric({ title, value, icon: Icon, danger = false }) {
  return <div className="metric">
    <div className="metric-heading"><span>{title}</span><Icon size={19} aria-hidden="true" /></div>
    <strong className={danger && value ? 'metric-danger' : ''}>{value ?? '—'}</strong>
  </div>;
}

function DataTable({ name, rows, compact = false }) {
  const schema = SCHEMAS[name];
  if (!schema) return null;
  return <div className="table-scroll"><table>
    <thead><tr>{schema.columns.map(([heading]) => <th key={heading}>{heading}</th>)}<th>Действие</th></tr></thead>
    <tbody>
      {rows.map(item => <tr key={item.id}>
        {schema.columns.map(([heading, render]) => <td key={heading}>{render(item) ?? '—'}</td>)}
        <td><a className="edit-link" href={`${ADMIN}/${schema.model}/${encodeURIComponent(item.id)}/change/`} title="Открыть в Django Admin">
          Изменить <ArrowUpRight size={13} aria-hidden="true" /></a></td>
      </tr>)}
      {rows.length === 0 && <tr><td colSpan={schema.columns.length + 1} className="empty-cell">
        {compact ? 'Пока нет записей' : 'Записей не найдено'}
      </td></tr>}
    </tbody>
  </table></div>;
}

export default function App() {
  const [page, setPage] = useState('overview');
  const [data, setData] = useState({ dashboard: null, buildings: [], elevators: [], tickets: [], maintenance: [], technicians: [] });
  const [search, setSearch] = useState('');
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState('');
  const [diagOpen, setDiagOpen] = useState(false);
  const [events, setEvents] = useState([]);

  const record = useCallback((kind, endpoint, code = '') => {
    const entry = { time: new Date().toISOString(), kind, endpoint, code: String(code) };
    setEvents(old => [...old.slice(-29), entry]);
    if (kind === 'error') console.warn('[LiftControl diagnostic]', kind, endpoint, code);
  }, []);

  const reload = useCallback(async () => {
    setFetching(true);
    setError('');
    const names = ['dashboard', 'buildings', 'elevators', 'tickets', 'maintenance', 'technicians'];
    try {
      const results = await Promise.all(names.map(async name => {
        const response = await fetch(`${BASE}/${name}/`, { credentials: 'same-origin', cache: 'no-store' });
        if (response.status === 401 || response.status === 403) throw { kind: 'auth', status: response.status, name };
        if (!response.ok) throw { kind: 'http', status: response.status, name };
        return [name, await response.json()];
      }));
      const next = {};
      for (const [name, result] of results) next[name] = name === 'dashboard' ? result : asRows(result);
      setData(next);
      record('ok', 'all-read-endpoints', '200');
    } catch (err) {
      const status = err?.status || 'network';
      record('error', err?.name || 'all-read-endpoints', status);
      if (err?.kind === 'auth') {
        setError('Сессия закончилась или недостаточно прав. Войдите через Django Admin.');
      } else {
        setError('Не удалось обновить данные. Проверьте соединение с Django API и повторите запрос.');
      }
    } finally {
      setFetching(false);
    }
  }, [record]);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    const onError = () => record('error', 'browser-script', 'runtime');
    const onRejection = () => record('error', 'browser-promise', 'rejection');
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, [record]);

  const schema = SCHEMAS[page];
  const filtered = useMemo(() => {
    if (!schema) return [];
    const q = search.trim().toLocaleLowerCase('ru');
    return data[page].filter(item =>
      !q || schema.search(item).filter(Boolean).some(v => String(v).toLocaleLowerCase('ru').includes(q))
    );
  }, [data, page, search, schema]);

  const go = value => { setPage(value); setSearch(''); };
  const addUrl = schema ? `${ADMIN}/${schema.model}/add/` : `${ADMIN}/ticket/add/`;
  const copyDiagnostics = () => {
    const report = JSON.stringify({ service: 'LiftControl Web', version: '0.1', events }, null, 2);
    navigator.clipboard?.writeText(report).then(() => record('ok', 'copy-diagnostics'));
  };

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><Gauge size={21} /></div>
        <div><strong>LiftControl</strong><small>Управление лифтами</small></div>
      </div>
      <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav aria-label="Разделы LiftControl">
        {SECTIONS.map(({ id, title, icon: Icon }) => <button type="button" key={id}
          className={page === id ? 'nav-item active' : 'nav-item'} onClick={() => go(id)}
          aria-current={page === id ? 'page' : undefined}><Icon size={18} aria-hidden="true" />{title}</button>)}
      </nav>
      <div className="sidebar-bottom">
        <ShieldCheck size={18} aria-hidden="true" />
        <span>Закрытый тестовый доступ<br/><small>Через SSH-туннель</small></span>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <div className="topbar-brand">LiftControl <span>/</span> {SECTIONS.find(x => x.id === page)?.title}</div>
        <div className="top-actions">
          <button type="button" className="ghost-btn" onClick={reload} disabled={fetching}>
            <RefreshCw size={16} className={fetching ? 'spin' : ''}/> Обновить
          </button>
          <a className="ghost-btn" href="/admin/" aria-label="Открыть администрирование">
            <ShieldCheck size={16}/> Админка
          </a>
        </div>
      </header>
      <main>
        <div className="hero">
          <div>
            <div className="eyebrow"><span className={error ? 'live-dot warn' : 'live-dot'}></span>
              {error ? 'НЕТ СОЕДИНЕНИЯ С API' : 'LIFTCONTROL • ТЕСТОВЫЙ КОНТУР'}
            </div>
            <h1>{page === 'overview' ? 'Панель управления' : SCHEMAS[page]?.label}</h1>
            <p>{page === 'overview' ? 'Состояние объектов, заявки и техническое обслуживание' : 'Данные из PostgreSQL через Django API'}</p>
          </div>
          <a className="primary-btn" href={addUrl}>+ {page === 'overview' ? 'Новая заявка' : 'Добавить запись'} <ArrowUpRight size={16}/></a>
        </div>

        {error && <div className="alert" role="alert"><AlertTriangle size={19}/><span>{error}</span>
          <a href="/admin/login/?next=/">Войти</a><button onClick={reload}>Повторить</button></div>}

        {page === 'overview' && <>
          <section className="metrics" aria-label="Основные показатели">
            <Metric title="Лифтов на ТО" value={data.dashboard?.elevators} icon={Gauge}/>
            <Metric title="Сотрудников" value={data.dashboard?.technicians} icon={Users}/>
            <Metric title="Открытых заявок" value={data.dashboard?.open_tickets} icon={Activity}/>
            <Metric title="Аварийных заявок" value={data.dashboard?.emergency_tickets} icon={AlertTriangle} danger/>
            <Metric title="ТО сегодня" value={data.dashboard?.maintenance_today} icon={Wrench}/>
          </section>
          <section className="block">
            <div className="block-heading"><div><h2>Последние заявки</h2><p>Обращения и текущие статусы</p></div>
              <button className="text-btn" onClick={() => go('tickets')}>Все заявки →</button></div>
            <DataTable name="tickets" rows={data.tickets.slice(0, 8)} compact/>
          </section>
          <section className="block">
            <div className="block-heading"><div><h2>Лифты</h2><p>Реестр оборудования</p></div>
              <button className="text-btn" onClick={() => go('elevators')}>Все лифты →</button></div>
            <DataTable name="elevators" rows={data.elevators.slice(0, 8)} compact/>
          </section>
        </>}
        {schema && <section className="block">
          <div className="block-heading"><div><h2>Список: {schema.label.toLowerCase()}</h2>
            <p>Записей: {filtered.length} · Редактирование открывается в Django Admin</p></div>
            <label className="search"><Search size={17}/><input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Поиск по списку" aria-label="Поиск"/></label>
          </div>
          <DataTable name={page} rows={filtered}/>
        </section>}
        <div className="diagnostics">
          <button type="button" className="diag-toggle" onClick={() => setDiagOpen(!diagOpen)}>
            <Activity size={15}/> Журнал тестовой версии {diagOpen ? '▴' : '▾'}
          </button>
          {diagOpen && <div className="diag-body">
            <p>Только время, тип запроса и код ошибки. Пароли и содержимое заявок не записываются.</p>
            <button className="ghost-btn" onClick={copyDiagnostics}>Скопировать диагностику</button>
            <pre>{JSON.stringify(events.slice(-12), null, 2)}</pre>
          </div>}
        </div>
        <footer>LiftControl Web 0.1 · Пилотная версия · Данные доступны только авторизованному персоналу</footer>
      </main>
    </div>
  </div>;
}
