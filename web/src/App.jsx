import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bell,
  Building2,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Clock3,
  FileBarChart,
  Gauge,
  History,
  KeyRound,
  LayoutDashboard,
  MapPinned,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  UserCog,
  Users,
  Wrench,
  X,
} from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

const ROLE_META = {
  director: {
    label: 'Руководитель',
    short: 'Руководитель',
    defaultPage: 'overview',
    menu: [
      ['overview', 'Обзор', LayoutDashboard],
      ['objects', 'Объекты', Building2],
      ['elevators', 'Лифты', Gauge],
      ['tickets', 'Заявки', ClipboardList],
      ['maintenance', 'ТО', Wrench],
      ['technicians', 'Механики', Users],
      ['map', 'Карта', MapPinned],
      ['reports', 'Отчёты', FileBarChart],
    ],
  },
  dispatcher: {
    label: 'Диспетчер',
    short: 'Диспетчерская',
    defaultPage: 'dispatch',
    menu: [
      ['dispatch', 'Диспетчерская', Activity],
      ['tickets', 'Заявки', ClipboardList],
      ['elevators', 'Лифты', Gauge],
      ['technicians', 'Механики', Users],
      ['map', 'Карта', MapPinned],
      ['history', 'Журнал', History],
    ],
  },
  admin: {
    label: 'Администратор',
    short: 'Администратор',
    defaultPage: 'system',
    menu: [
      ['system', 'Система', Server],
      ['users', 'Пользователи', UserCog],
      ['roles', 'Роли и права', KeyRound],
      ['objects', 'Объекты', Building2],
      ['elevators', 'Лифты', Gauge],
      ['settings', 'Настройки', Settings],
      ['logs', 'Журнал системы', History],
    ],
  },
};

const PAGE_TITLES = {
  overview: ['Обзор организации', 'Состояние лифтов, заявок и обслуживания'],
  dispatch: ['Диспетчерская', 'Заявки, механики и оперативная работа в одном окне'],
  system: ['Система LiftControl', 'Пользователи, данные и состояние сервера'],
  objects: ['Объекты', 'Дома и комплексы на обслуживании'],
  elevators: ['Лифты', 'Единая база оборудования'],
  tickets: ['Заявки', 'Все обращения и аварийные работы'],
  maintenance: ['Техническое обслуживание', 'План и факт выполнения ТО'],
  technicians: ['Механики', 'Сотрудники и текущая загрузка'],
  map: ['Оперативная карта', 'Объекты, заявки и сотрудники'],
  reports: ['Отчёты', 'Ключевые показатели организации'],
  history: ['Журнал событий', 'Хронология действий диспетчерской'],
  users: ['Пользователи', 'Учётные записи сотрудников'],
  roles: ['Роли и права', 'Доступ к функциям LiftControl'],
  settings: ['Настройки', 'Параметры организации и системы'],
  logs: ['Журнал системы', 'События и технический контроль'],
};

function listify(value) {
  if (Array.isArray(value)) return value;
  return value?.results || [];
}

function formatDate(value, withTime = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ru-RU', withTime
    ? { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
}

function ticketTone(ticket) {
  if (ticket.priority === 'EMERGENCY') return 'red';
  if (ticket.priority === 'HIGH') return 'orange';
  if (ticket.status === 'DONE') return 'green';
  if (ticket.status === 'IN_PROGRESS') return 'blue';
  return 'slate';
}

function statusLabel(status) {
  const map = {
    NEW: 'Новая',
    ASSIGNED: 'Назначена',
    IN_PROGRESS: 'В работе',
    DONE: 'Выполнена',
    CANCELED: 'Отменена',
  };
  return map[status] || status || '—';
}

function StatCard({ title, value, icon: Icon, tone = 'blue', hint }) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <div className="stat-icon"><Icon size={19} /></div>
      <div className="stat-copy">
        <span>{title}</span>
        <strong>{value ?? '—'}</strong>
        {hint && <small>{hint}</small>}
      </div>
    </div>
  );
}

function Section({ title, action, children, className = '' }) {
  return (
    <section className={`surface ${className}`}>
      <div className="section-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Badge({ tone = 'slate', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function Empty({ text = 'Данных пока нет' }) {
  return <div className="empty-state">{text}</div>;
}

function TicketTable({ tickets, compact = false }) {
  if (!tickets.length) return <Empty text="Заявок пока нет" />;
  return (
    <div className="data-table">
      <div className={`data-row data-head ${compact ? 'ticket-compact' : 'ticket-full'}`}>
        {!compact && <span>№</span>}
        <span>Адрес</span>
        <span>Лифт</span>
        <span>Заявка</span>
        {!compact && <span>Механик</span>}
        <span>Статус</span>
      </div>
      {tickets.map((ticket) => (
        <div className={`data-row ${compact ? 'ticket-compact' : 'ticket-full'}`} key={ticket.id}>
          {!compact && <span className="muted">#{ticket.id}</span>}
          <span className="strong-cell">{ticket.address || '—'}</span>
          <span>{ticket.elevator_factory_number || '—'}</span>
          <span className="ellipsis">{ticket.title}</span>
          {!compact && <span>{ticket.technician_name || 'Не назначен'}</span>}
          <span><Badge tone={ticketTone(ticket)}>{ticket.status_display || statusLabel(ticket.status)}</Badge></span>
        </div>
      ))}
    </div>
  );
}

function ElevatorTable({ elevators }) {
  if (!elevators.length) return <Empty text="Лифты не добавлены" />;
  return (
    <div className="data-table">
      <div className="data-row elevator-row data-head">
        <span>Адрес</span><span>Подъезд</span><span>Зав. №</span><span>Модель</span><span>Механик</span><span>Статус</span>
      </div>
      {elevators.map((elevator) => (
        <div className="data-row elevator-row" key={elevator.id}>
          <span className="strong-cell">{elevator.address}</span>
          <span>{elevator.entrance || '—'}</span>
          <span>{elevator.factory_number}</span>
          <span>{[elevator.manufacturer, elevator.model].filter(Boolean).join(' ') || '—'}</span>
          <span>{elevator.technician_name || 'Не назначен'}</span>
          <span><Badge tone={elevator.active ? 'green' : 'slate'}>{elevator.active ? 'На обслуживании' : 'Отключён'}</Badge></span>
        </div>
      ))}
    </div>
  );
}

function MaintenanceTable({ maintenance }) {
  if (!maintenance.length) return <Empty text="План ТО пока пуст" />;
  return (
    <div className="data-table">
      <div className="data-row maintenance-row data-head">
        <span>Дата</span><span>Адрес</span><span>Лифт</span><span>Работа</span><span>Механик</span><span>Статус</span>
      </div>
      {maintenance.map((item) => (
        <div className="data-row maintenance-row" key={item.id}>
          <span>{formatDate(item.planned_date)}</span>
          <span className="strong-cell">{item.address || '—'}</span>
          <span>{item.elevator_factory_number || '—'}</span>
          <span>{item.kind_display || item.kind}</span>
          <span>{item.technician_name || 'Не назначен'}</span>
          <span><Badge tone={item.completed_at ? 'green' : 'orange'}>{item.completed_at ? 'Выполнено' : 'Запланировано'}</Badge></span>
        </div>
      ))}
    </div>
  );
}

function TechnicianGrid({ technicians, tickets }) {
  if (!technicians.length) return <Empty text="Сотрудники не добавлены" />;
  return (
    <div className="technician-grid">
      {technicians.map((tech, index) => {
        const current = tickets.find((ticket) => ticket.assigned_to === tech.id && ['ASSIGNED', 'IN_PROGRESS'].includes(ticket.status));
        const tone = !tech.active ? 'slate' : current ? 'orange' : 'green';
        return (
          <div className="tech-card" key={tech.id}>
            <div className="avatar">{tech.full_name?.split(' ').map((part) => part[0]).slice(0, 2).join('') || index + 1}</div>
            <div className="tech-main">
              <strong>{tech.full_name}</strong>
              <span>{tech.role_display || tech.role}</span>
              <small>{current ? `${current.address || ''} · ${current.title}` : tech.active ? 'Свободен' : 'Не на линии'}</small>
            </div>
            <Badge tone={tone}>{current ? 'На заявке' : tech.active ? 'Свободен' : 'Неактивен'}</Badge>
          </div>
        );
      })}
    </div>
  );
}

function MapBoard({ buildings, technicians, tickets }) {
  const emergency = tickets.filter((t) => t.priority === 'EMERGENCY' && t.status !== 'DONE').length;
  return (
    <div className="map-board">
      <div className="map-grid" />
      {buildings.slice(0, 5).map((building, index) => (
        <div className={`map-pin building-pin pin-${index + 1}`} key={building.id} title={building.address}>
          <Building2 size={16} />
        </div>
      ))}
      {technicians.slice(0, 4).map((tech, index) => (
        <div className={`map-pin tech-pin tech-${index + 1}`} key={tech.id} title={tech.full_name}>
          {tech.full_name?.[0] || 'М'}
        </div>
      ))}
      {emergency > 0 && <div className="map-pin emergency-pin"><AlertTriangle size={17} /></div>}
      <div className="map-caption">
        <strong>Оперативная карта</strong>
        <span>В V1 показана схема. Реальную карту и GPS подключим следующим этапом.</span>
      </div>
      <div className="map-legend">
        <span><i className="legend-dot object" /> Объекты</span>
        <span><i className="legend-dot mechanic" /> Механики</span>
        <span><i className="legend-dot emergency" /> Аварии</span>
      </div>
    </div>
  );
}

function TicketModal({ elevators, technicians, onClose, onCreated }) {
  const [form, setForm] = useState({ elevator: '', title: '', description: '', priority: 'NORMAL', assigned_to: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    if (!form.elevator || !form.title.trim()) {
      setError('Выберите лифт и укажите неисправность.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = {
        elevator: Number(form.elevator),
        title: form.title.trim(),
        description: form.description.trim(),
        priority: form.priority,
        status: form.assigned_to ? 'ASSIGNED' : 'NEW',
        assigned_to: form.assigned_to ? Number(form.assigned_to) : null,
      };
      const response = await fetch(`${API}/tickets/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await response.json();
      onCreated();
      onClose();
    } catch (e) {
      setError('Не удалось создать заявку. Проверьте, что Django-сервер запущен.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div><span className="eyebrow">Диспетчерская</span><h2>Новая заявка</h2></div>
          <button className="icon-button" onClick={onClose}><X size={20} /></button>
        </div>
        <form onSubmit={submit}>
          <label>Лифт
            <select value={form.elevator} onChange={(e) => setForm({ ...form, elevator: e.target.value })}>
              <option value="">Выберите адрес и лифт</option>
              {elevators.map((elevator) => <option key={elevator.id} value={elevator.id}>{elevator.address} · {elevator.entrance ? `подъезд ${elevator.entrance} · ` : ''}{elevator.factory_number}</option>)}
            </select>
          </label>
          <label>Что произошло
            <input autoFocus value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Например: не закрываются двери" />
          </label>
          <label>Описание
            <textarea rows="3" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Дополнительная информация от заявителя" />
          </label>
          <div className="form-grid">
            <label>Приоритет
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="LOW">Низкий</option><option value="NORMAL">Обычный</option><option value="HIGH">Высокий</option><option value="EMERGENCY">Аварийный</option>
              </select>
            </label>
            <label>Механик
              <select value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}>
                <option value="">Назначить позже</option>
                {technicians.filter((tech) => tech.active).map((tech) => <option key={tech.id} value={tech.id}>{tech.full_name}</option>)}
              </select>
            </label>
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="button secondary" onClick={onClose}>Отмена</button>
            <button className="button primary" disabled={saving}>{saving ? 'Создаём…' : 'Создать заявку'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DirectorOverview({ stats, tickets, elevators, buildings, technicians, maintenance }) {
  const openTickets = tickets.filter((t) => !['DONE', 'CANCELED'].includes(t.status));
  const emergencies = openTickets.filter((t) => t.priority === 'EMERGENCY');
  const pendingMaintenance = maintenance.filter((m) => !m.completed_at);
  return (
    <>
      <div className="stat-grid six">
        <StatCard title="Лифтов" value={stats?.elevators ?? elevators.length} icon={Gauge} tone="blue" hint="на обслуживании" />
        <StatCard title="Объектов" value={buildings.length} icon={Building2} tone="violet" />
        <StatCard title="Механиков" value={stats?.technicians ?? technicians.length} icon={Users} tone="cyan" />
        <StatCard title="Открытых заявок" value={stats?.open_tickets ?? openTickets.length} icon={ClipboardList} tone="orange" />
        <StatCard title="Аварийных" value={stats?.emergency_tickets ?? emergencies.length} icon={AlertTriangle} tone="red" />
        <StatCard title="ТО в плане" value={pendingMaintenance.length} icon={Wrench} tone="green" />
      </div>
      <div className="dashboard-grid director-grid">
        <Section title="Последние заявки" className="span-2"><TicketTable tickets={tickets.slice(0, 6)} compact /></Section>
        <Section title="Состояние объектов">
          <div className="object-health">
            {buildings.slice(0, 6).map((building, index) => {
              const count = building.elevators_count || elevators.filter((e) => e.building === building.id).length;
              const issueCount = tickets.filter((t) => elevators.some((e) => e.id === t.elevator && e.building === building.id) && !['DONE', 'CANCELED'].includes(t.status)).length;
              return <div className="health-row" key={building.id}><div><strong>{building.address}</strong><span>{count} лифт.</span></div><Badge tone={issueCount ? 'orange' : 'green'}>{issueCount ? `${issueCount} заяв.` : 'Норма'}</Badge></div>;
            })}
            {!buildings.length && <Empty />}
          </div>
        </Section>
        <Section title="Ближайшее ТО"><MaintenanceTable maintenance={maintenance.slice(0, 5)} /></Section>
        <Section title="Механики" className="span-2"><TechnicianGrid technicians={technicians.slice(0, 4)} tickets={tickets} /></Section>
      </div>
    </>
  );
}

function DispatcherOverview({ stats, tickets, elevators, buildings, technicians, onNewTicket }) {
  const queue = tickets.filter((t) => !['DONE', 'CANCELED'].includes(t.status));
  const emergency = queue.filter((t) => t.priority === 'EMERGENCY');
  const assigned = queue.filter((t) => ['ASSIGNED', 'IN_PROGRESS'].includes(t.status));
  const busyIds = new Set(assigned.map((t) => t.assigned_to).filter(Boolean));
  const freeTechs = technicians.filter((t) => t.active && !busyIds.has(t.id));
  return (
    <>
      <div className="dispatch-strip">
        <div><span className="pulse red" /><strong>{emergency.length}</strong><span>аварийных</span></div>
        <div><span className="pulse blue" /><strong>{queue.filter((t) => t.status === 'NEW').length}</strong><span>новых</span></div>
        <div><span className="pulse orange" /><strong>{assigned.length}</strong><span>в работе</span></div>
        <div><span className="pulse green" /><strong>{freeTechs.length}</strong><span>механиков свободно</span></div>
        <button className="button danger-action" onClick={onNewTicket}><Plus size={18} /> Новая заявка</button>
      </div>
      <div className="dispatch-layout">
        <Section title="Очередь заявок" className="dispatch-queue">
          <div className="ticket-stack">
            {queue.slice(0, 8).map((ticket) => (
              <div className={`dispatch-ticket priority-${ticketTone(ticket)}`} key={ticket.id}>
                <div className="ticket-priority"><AlertTriangle size={17} /><span>{ticket.priority_display || (ticket.priority === 'EMERGENCY' ? 'Аварийная' : 'Заявка')}</span><small>{formatDate(ticket.created_at, true)}</small></div>
                <strong>{ticket.address || 'Адрес не указан'}</strong>
                <span>Лифт {ticket.elevator_factory_number || '—'} · {ticket.title}</span>
                <div className="ticket-foot"><Badge tone={ticketTone(ticket)}>{ticket.status_display || statusLabel(ticket.status)}</Badge><small>{ticket.technician_name || 'Механик не назначен'}</small></div>
              </div>
            ))}
            {!queue.length && <Empty text="Открытых заявок нет" />}
          </div>
        </Section>
        <Section title="Карта" className="dispatch-map"><MapBoard buildings={buildings} technicians={technicians} tickets={tickets} /></Section>
        <Section title="Механики" className="dispatch-tech"><TechnicianGrid technicians={technicians} tickets={tickets} /></Section>
      </div>
    </>
  );
}

function AdminOverview({ buildings, elevators, technicians, tickets, serverOk }) {
  const roles = [
    ['Руководитель', 'Полный обзор и отчёты', 'director'],
    ['Диспетчер', 'Заявки и оперативная работа', 'dispatcher'],
    ['Администратор', 'Пользователи и настройки', 'admin'],
    ['Механик', 'Мобильное приложение', 'mechanic'],
  ];
  return (
    <>
      <div className="stat-grid four">
        <StatCard title="Состояние сервера" value={serverOk ? 'Работает' : 'Нет связи'} icon={Server} tone={serverOk ? 'green' : 'red'} />
        <StatCard title="Объектов" value={buildings.length} icon={Building2} tone="violet" />
        <StatCard title="Лифтов в базе" value={elevators.length} icon={Gauge} tone="blue" />
        <StatCard title="Сотрудников" value={technicians.length} icon={Users} tone="cyan" />
      </div>
      <div className="dashboard-grid admin-grid">
        <Section title="Роли системы">
          <div className="role-cards">
            {roles.map(([name, description, code]) => <div className="role-card" key={code}><div className="role-icon"><ShieldCheck size={18} /></div><div><strong>{name}</strong><span>{description}</span></div><Badge tone="green">Включена</Badge></div>)}
          </div>
        </Section>
        <Section title="Состав данных">
          <div className="database-list">
            <div><Building2 /><span>Объекты</span><strong>{buildings.length}</strong></div>
            <div><Gauge /><span>Лифты</span><strong>{elevators.length}</strong></div>
            <div><Users /><span>Сотрудники</span><strong>{technicians.length}</strong></div>
            <div><ClipboardList /><span>Заявки</span><strong>{tickets.length}</strong></div>
          </div>
        </Section>
        <Section title="Что подключаем следующим" className="span-2">
          <div className="roadmap-mini">
            <div className="done"><CheckCircle2 /> <strong>Панель V1</strong><span>Роли и основные экраны</span></div>
            <div><Clock3 /> <strong>Учётные записи</strong><span>JWT, реальные права и пароли</span></div>
            <div><Clock3 /> <strong>PostgreSQL</strong><span>Рабочая база на физическом сервере</span></div>
            <div><Clock3 /> <strong>Realtime</strong><span>WebSocket и обновления заявок</span></div>
          </div>
        </Section>
      </div>
    </>
  );
}

function GenericPage({ page, data }) {
  const { buildings, elevators, tickets, technicians, maintenance } = data;
  if (page === 'objects') return <Section title="Объекты на обслуживании"><div className="object-cards">{buildings.map((b) => <div className="object-card" key={b.id}><div className="object-icon"><Building2 /></div><div><strong>{b.address}</strong><span>{b.name}</span><small>{b.management_company || 'Управляющая организация не указана'}</small></div><Badge tone="blue">{b.elevators_count ?? elevators.filter((e) => e.building === b.id).length} лифт.</Badge></div>)}</div>{!buildings.length && <Empty />}</Section>;
  if (page === 'elevators') return <Section title={`Лифты · ${elevators.length}`}><ElevatorTable elevators={elevators} /></Section>;
  if (page === 'tickets') return <Section title={`Заявки · ${tickets.length}`}><TicketTable tickets={tickets} /></Section>;
  if (page === 'maintenance') return <Section title={`План ТО · ${maintenance.length}`}><MaintenanceTable maintenance={maintenance} /></Section>;
  if (page === 'technicians') return <Section title={`Сотрудники · ${technicians.length}`}><TechnicianGrid technicians={technicians} tickets={tickets} /></Section>;
  if (page === 'map') return <Section title="Карта"><MapBoard buildings={buildings} technicians={technicians} tickets={tickets} /></Section>;
  if (page === 'reports') return <div className="stat-grid four"><StatCard title="Заявок всего" value={tickets.length} icon={ClipboardList} tone="blue" /><StatCard title="Выполнено" value={tickets.filter((t) => t.status === 'DONE').length} icon={CheckCircle2} tone="green" /><StatCard title="Аварийных" value={tickets.filter((t) => t.priority === 'EMERGENCY').length} icon={AlertTriangle} tone="red" /><StatCard title="ТО выполнено" value={maintenance.filter((m) => m.completed_at).length} icon={Wrench} tone="violet" /></div>;
  if (page === 'history' || page === 'logs') return <Section title="Последние события"><div className="timeline">{tickets.slice(0, 10).map((t) => <div className="timeline-item" key={t.id}><i /><div><strong>{t.title}</strong><span>{t.address} · {t.status_display || statusLabel(t.status)}</span></div><time>{formatDate(t.updated_at || t.created_at, true)}</time></div>)}</div></Section>;
  if (page === 'users') return <Section title="Учётные записи"><div className="notice-card"><UserCog size={24} /><div><strong>Модуль учётных записей подготовлен к следующему этапу</strong><span>В V1 роли можно переключать вручную для проверки интерфейсов. Далее подключим реальных пользователей и JWT.</span></div></div></Section>;
  if (page === 'roles') return <Section title="Модель доступа"><div className="permissions-grid"><div><strong>Руководитель</strong><span>Обзор · отчёты · объекты · заявки · ТО</span></div><div><strong>Диспетчер</strong><span>Заявки · механики · карта · журнал</span></div><div><strong>Администратор</strong><span>Пользователи · роли · настройки · справочники</span></div><div><strong>Механик</strong><span>Только мобильное приложение и свои задания</span></div></div></Section>;
  if (page === 'settings') return <Section title="Настройки"><div className="settings-list"><div><SlidersHorizontal /><div><strong>Организация</strong><span>Название, реквизиты, рабочее время</span></div><ChevronDown /></div><div><Bell /><div><strong>Уведомления</strong><span>Аварии, новые заявки, просроченное ТО</span></div><ChevronDown /></div><div><Server /><div><strong>Сервер</strong><span>API, резервные копии, синхронизация</span></div><ChevronDown /></div></div></Section>;
  return <Empty text="Раздел появится в следующей версии" />;
}

export default function App() {
  const [role, setRole] = useState(() => localStorage.getItem('liftcontrol_role') || 'director');
  const [page, setPage] = useState(() => ROLE_META[localStorage.getItem('liftcontrol_role') || 'director']?.defaultPage || 'overview');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [serverOk, setServerOk] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState({ stats: null, tickets: [], elevators: [], technicians: [], buildings: [], maintenance: [] });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const endpoints = ['dashboard', 'tickets', 'elevators', 'technicians', 'buildings', 'maintenance'];
      const responses = await Promise.all(endpoints.map(async (endpoint) => {
        const response = await fetch(`${API}/${endpoint}/`);
        if (!response.ok) throw new Error(`${endpoint}: ${response.status}`);
        return response.json();
      }));
      const [stats, tickets, elevators, technicians, buildings, maintenance] = responses;
      setData({ stats, tickets: listify(tickets), elevators: listify(elevators), technicians: listify(technicians), buildings: listify(buildings), maintenance: listify(maintenance) });
      setServerOk(true);
      setError('');
    } catch (e) {
      setServerOk(false);
      setError('Нет связи с Django API. Панель открыта, но живые данные недоступны.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const changeRole = (nextRole) => {
    setRole(nextRole);
    setPage(ROLE_META[nextRole].defaultPage);
    localStorage.setItem('liftcontrol_role', nextRole);
  };

  const meta = ROLE_META[role];
  const [title, subtitle] = PAGE_TITLES[page] || ['LiftControl', ''];
  const openTickets = useMemo(() => data.tickets.filter((t) => !['DONE', 'CANCELED'].includes(t.status)).length, [data.tickets]);

  const content = (() => {
    if (page === 'overview') return <DirectorOverview {...data} />;
    if (page === 'dispatch') return <DispatcherOverview {...data} onNewTicket={() => setModalOpen(true)} />;
    if (page === 'system') return <AdminOverview {...data} serverOk={serverOk} />;
    return <GenericPage page={page} data={data} />;
  })();

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark"><Gauge size={23} /></div>
          <div><strong>LIFTCONTROL</strong><span>Эверест</span></div>
        </div>
        <div className="role-caption">{meta.short}</div>
        <nav className="side-nav">
          {meta.menu.map(([key, label, Icon]) => (
            <button key={key} className={page === key ? 'active' : ''} onClick={() => { setPage(key); setSidebarOpen(false); }}>
              <Icon size={18} /><span>{label}</span>
              {key === 'tickets' && openTickets > 0 && <b>{openTickets}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className={`server-dot ${serverOk ? 'online' : 'offline'}`} />
          <div><strong>{serverOk ? 'Сервер работает' : 'Сервер недоступен'}</strong><span>{API.replace(/^https?:\/\//, '')}</span></div>
        </div>
      </aside>

      {sidebarOpen && <div className="mobile-overlay" onClick={() => setSidebarOpen(false)} />}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setSidebarOpen(true)}><Menu /></button>
          <div className="page-heading"><span className="eyebrow">{meta.label}</span><h1>{title}</h1><p>{subtitle}</p></div>
          <div className="top-actions">
            <button className="icon-button notification"><Bell size={19} />{openTickets > 0 && <i />}</button>
            <button className="icon-button" onClick={loadData} title="Обновить данные"><RefreshCw size={19} className={loading ? 'spin' : ''} /></button>
            <label className="role-switcher">
              <span>Режим</span>
              <select value={role} onChange={(e) => changeRole(e.target.value)}>
                <option value="director">Руководитель</option>
                <option value="dispatcher">Диспетчер</option>
                <option value="admin">Администратор</option>
              </select>
            </label>
            {role === 'dispatcher' && <button className="button primary top-new" onClick={() => setModalOpen(true)}><Plus size={17} /> Новая заявка</button>}
          </div>
        </header>

        <div className="content-area">
          {error && <div className="connection-warning"><AlertTriangle size={18} /><span>{error}</span><button onClick={loadData}>Повторить</button></div>}
          {loading && !data.stats ? <div className="loading-screen"><RefreshCw className="spin" /><span>Загружаем LiftControl…</span></div> : content}
        </div>
      </main>

      {modalOpen && <TicketModal elevators={data.elevators} technicians={data.technicians} onClose={() => setModalOpen(false)} onCreated={loadData} />}
    </div>
  );
}
