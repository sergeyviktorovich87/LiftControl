import React, {useEffect, useState} from 'react';
import {CalendarDays, ChevronLeft, ChevronRight, Settings2, Download} from 'lucide-react';
import {api, csv} from './api';
import {Dialog} from './components';
import DutyRules from './DutyRules';

const civilDate = (value, zone) => new Intl.DateTimeFormat('sv-SE', {
  timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
}).format(value);
const atDay = date => new Date(date + 'T12:00:00Z');
const addDays = (date, days) => new Date(+atDay(date) + days * 86400000).toISOString().slice(0, 10);
const beginningOfWeek = date => addDays(date, -(atDay(date).getUTCDay() + 6) % 7);
function monthBounds(date) {
  const start = date.slice(0, 7) + '-01';
  const end = atDay(start);
  end.setUTCMonth(end.getUTCMonth() + 1, 0);
  return [start, end.toISOString().slice(0, 10)];
}
const dateLabel = (date, options = {day: 'numeric', month: 'long'}) =>
  atDay(date).toLocaleDateString('ru-RU', {...options, timeZone: 'UTC'});

export default function Duty({data, user}) {
  const zone = user.timezone || 'Asia/Yakutsk';
  const today = civilDate(new Date(user.server_time || Date.now()), zone);
  const [anchor, setAnchor] = useState(today);
  const [mode, setMode] = useState('week');
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState('');
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState('');
  const [monthStart, monthEnd] = monthBounds(anchor);
  const first = beginningOfWeek(anchor);
  const [from, to] = mode === 'week' ? [first, addDays(first, 6)] : [monthStart, monthEnd];
  const key = [user.organization_id, from, to, revision].join('/');
  const technicians = data.technicians.filter(t => t.active && t.role === 'MECHANIC');
  const refresh = () => setRevision(value => value + 1);
  const timeLabel = stamp => new Date(stamp).toLocaleTimeString('ru-RU', {timeZone: zone, hour: '2-digit', minute: '2-digit'});

  useEffect(() => {
    let current = true;
    setError('');
    async function load() {
      try {
        const result = user.duty_roster_api
          ? await api('duty/roster/?' + new URLSearchParams({from, to}))
          : Array.from({length: (atDay(to) - atDay(from)) / 86400000 + 1}, (_, index) => {
            const date = addDays(from, index);
            return {date, shifts: (data.duty || []).filter(s => civilDate(new Date(s.start), zone) === date)};
          });
        if (current) setRows(result);
      } catch (e) {
        if (current) {
          setRows([]);
          setError(e.message);
        }
      } finally {
        if (current) setLoaded(key);
      }
    }
    load();
    return () => { current = false; };
  }, [key, user.duty_roster_api]);

  function move(direction) {
    setAnchor(mode === 'week' ? addDays(anchor, 7 * direction) :
      direction < 0 ? addDays(monthStart, -1) : addDays(monthEnd, 1));
  }

  function rowAction(row) {
    const future = row.start && +new Date(row.start) > Date.now();
    if (row.shifts.length !== 1) return row.shifts.length || row.covered_from_previous || !user.can_manage || !future ? 'Открыть' : 'Назначить';
    const shift = row.shifts[0];
    return user.can_manage && !shift.pending_swap && +new Date(shift.start) > Date.now() ? 'Изменить' : 'Открыть';
  }

  const title = mode === 'week' ? dateLabel(from) + ' – ' + dateLabel(to) : dateLabel(from, {month:'long', year:'numeric'});
  return <div className="duty-roster">
    <div className="page-heading"><div><h1>Дежурства</h1><p>Суточная смена с {(user.duty_start || '09:00').slice(0,5)} до следующего дня</p></div>
      {user.can_manage && user.duty_roster_api && <button onClick={() => setModal({type: 'settings'})}><Settings2 size={17}/>Настройки графика</button>}
    </div>
    <section className="panel roster-panel">
      <header className="panel-heading roster-tools">
        <div className="segments">
          <button aria-pressed={mode === 'week'} className={mode === 'week' ? 'selected' : ''} onClick={() => setMode('week')}>Неделя</button>
          <button aria-pressed={mode === 'month'} className={mode === 'month' ? 'selected' : ''} onClick={() => setMode('month')}>Месяц</button>
        </div>
        <div className="roster-period">
          <button aria-label="Предыдущий период" onClick={() => move(-1)}><ChevronLeft size={19}/></button>
          <h2 aria-live="polite">{title}</h2>
          <button aria-label="Следующий период" onClick={() => move(1)}><ChevronRight size={19}/></button>
        </div>
        {anchor !== today && <button onClick={() => setAnchor(today)}>К текущей дате</button>}
      </header>
      {error && <p className="error" role="alert">{error} <button onClick={refresh}>Повторить</button></p>}
      {loaded !== key ? <p className="empty">Загрузка…</p> :
        <ul className="roster-days">{rows.map(row => {
          const action = rowAction(row);
          const shift = row.shifts[0];
          const worker = shift?.technician_name || technicians.find(t => t.id === shift?.technician)?.full_name;
          const title = worker || row.suggested_name || (row.covered_from_previous ? 'Продолжается предыдущая смена' : 'Нет дежурного');
          const note = row.needs_assignment && shift ? 'Требуется замена' : row.replacement && row.suggested_name ? 'Подмена по плану' :
            row.suggested_name ? 'По очереди · до публикации' : shift ? timeLabel(shift.start) + ' – ' + timeLabel(shift.end) : '';
          return <li key={row.date}>
            <button className={'roster-day ' + (!shift && !row.suggested_name && !row.covered_from_previous || row.needs_assignment ? 'vacant' : '')}
              aria-label={action + ' · ' + dateLabel(row.date) + ' · ' + title} onClick={() => setModal({type:'day', row})}>
              <time dateTime={row.date}><strong>{atDay(row.date).getUTCDate()}</strong><small>{dateLabel(row.date, {weekday:'short'})}</small></time>
              <span><strong>{title}{row.shifts.length > 1 ? ' и ещё ' + (row.shifts.length - 1) : ''}</strong>{note && <small>{note}</small>}</span>
              <span className="roster-action">{action}</span>
            </button>
          </li>;
        })}</ul>}
      <footer className="panel-heading roster-tools">
        {notice && <span role="status">{notice}</span>}
        {user.can_manage && user.duty_roster_api && monthEnd >= today &&
          <button onClick={() => setModal({type:'publish'})}>Опубликовать месяц</button>}
        <button disabled={loaded !== key} onClick={() => csv('LiftControl-duty.csv', [
          ['Механик','Начало','Окончание'], ...rows.flatMap(r => r.shifts.map(s => [s.technician_name,s.start,s.end])),
        ])}><Download size={17}/>CSV</button>
      </footer>
    </section>
    {modal?.type === 'settings' && <DutyRules technicians={technicians} today={today} onClose={() => setModal(null)} onSaved={refresh}/>}
    {modal?.type === 'day' && <DayEditor row={modal.row} technicians={technicians} canManage={user.can_manage} timeLabel={timeLabel}
      onClose={() => setModal(null)} onSaved={message => { setNotice(message); refresh(); }}/>}
    {modal?.type === 'publish' && <ActionDialog title={'Опубликовать график · ' + dateLabel(monthStart,{month:'long',year:'numeric'})}
      action="Опубликовать" onClose={() => setModal(null)} run={async () => {
        const result = await api('duty/roster-publish/', {method:'POST',body:{from:monthStart,to:monthEnd}});
        setNotice(`График опубликован · новых смен ${result.added}, изменено ${result.updated}`);
        refresh();
      }}>Назначения по очереди вступят в силу. Ручные назначения и история подмен сохранятся.</ActionDialog>}
  </div>;
}

function DayEditor({row, technicians, canManage, timeLabel, onClose, onSaved}) {
  const canCreate = canManage && !row.covered_from_previous && row.start && +new Date(row.start) > Date.now();
  const [shift, setShift] = useState(row.shifts.length === 1 ? row.shifts[0] : null);
  const [technician, setTechnician] = useState(shift?.technician || row.suggested || null);
  const editable = row.shifts.length || shift ?
    canManage && shift && !shift.pending_swap && +new Date(shift.start) > Date.now() : canCreate;
  const title = (editable ? 'Кто дежурит ' : 'Дежурства · ') + dateLabel(row.date) + (editable ? '?' : '');
  const otherShifts = row.shifts.filter(item => item.id !== shift?.id);
  const shiftList = otherShifts.length > 0 && <ul className="roster-shifts">
    {otherShifts.map(item => <li key={item.id}><button type="button" onClick={() => {setShift(item);setTechnician(item.technician);}}>
      {item.technician_name} · {timeLabel(item.start)} – {timeLabel(item.end)}
    </button></li>)}</ul>;
  if (!editable) return <Dialog title={title} onClose={onClose}>{shift ?
    <p>{shift.technician_name} · {timeLabel(shift.start)} – {timeLabel(shift.end)}{shift.pending_swap && ' · ожидается ответ на подмену'}</p> :
    !otherShifts.length && <p>{row.covered_from_previous ? 'Продолжается предыдущая смена.' : 'Дежурный пока не назначен.'}</p>}
    {shiftList}</Dialog>;
  return <ActionDialog title={title} action="Сохранить" onClose={onClose}
    disabled={!technician || technician === shift?.technician || row.unavailable?.includes(technician)} run={async () => {
      await api(shift ? `duty/${shift.id}/` : 'duty/', {method: shift ? 'PATCH' : 'POST',
        body: {technician, ...(!shift && {start:row.start,end:row.end,kind:'daily'})}});
      onSaved(shift ? 'Дежурный изменён' : 'Дежурный назначен');
    }}>
    {shift && <p className="muted">Сейчас назначен {shift.technician_name}</p>}
    <fieldset className="roster-picks"><legend>Дежурный механик</legend>
      {technicians.map(worker => {
        const off = row.unavailable?.includes(worker.id);
        return <label key={worker.id}><input type="radio" name="technician" checked={technician === worker.id}
          onChange={() => setTechnician(worker.id)} disabled={off}/>{worker.full_name}{off && <small>В отпуске</small>}</label>;
      })}
    </fieldset>
    {shiftList}
  </ActionDialog>;
}

function ActionDialog({title, action, onClose, run, disabled, children}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <Dialog title={title} onClose={() => { if (!busy) onClose(); }}><form onSubmit={async event => {
    event.preventDefault();
    if (busy || disabled) return;
    setBusy(true);
    setError('');
    try { await run(); onClose(); }
    catch (e) { setError(e.message); setBusy(false); }
  }}>{children}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="form-actions"><button type="button" disabled={busy} onClick={onClose}>Отмена</button><button
      className="primary" disabled={busy || disabled}>{busy ? 'Сохранение…' : action}</button></div>
  </form></Dialog>;
}
