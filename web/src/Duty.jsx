import React, {useEffect, useState} from 'react';
import {ChevronLeft, ChevronRight, Settings2, Download} from 'lucide-react';
import {api, csv} from './api';
import {Dialog, Field} from './components';
import DutyRules from './DutyRules';
import DutyStatus from './DutyStatus';

const civilDate = (value, zone) => new Intl.DateTimeFormat('sv-SE', {
  timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
}).format(value);
const atDay = date => new Date(date + 'T12:00:00Z');
const addDays = (date, days) => new Date(+atDay(date) + days * 86400000).toISOString().slice(0, 10);
function monthBounds(date) {
  const start = date.slice(0, 7) + '-01';
  const end = atDay(start);
  end.setUTCMonth(end.getUTCMonth() + 1, 0);
  return [start, end.toISOString().slice(0, 10)];
}
const dateLabel = (date, options = {day: 'numeric', month: 'long'}) =>
  atDay(date).toLocaleDateString('ru-RU', {...options, timeZone: 'UTC'});

const weekdays = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

export default function Duty({data, user, onChanged}) {
  const zone = user.timezone || 'Asia/Yakutsk';
  const now = +new Date(user.server_time || Date.now());
  const today = civilDate(new Date(now), zone);
  const startTime = (user.duty_start || '09:00').slice(0, 5);
  const clock = new Intl.DateTimeFormat('sv-SE', {timeZone:zone, hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).format(new Date(now));
  const firstFuture = clock < startTime ? today : addDays(today, 1);
  const [anchor, setAnchor] = useState(today);
  const [selected, setSelected] = useState(today);
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState('');
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState('');
  const [from, to] = monthBounds(anchor);
  const key = [user.organization_id, from, to, revision].join('/');
  const technicians = data.technicians.filter(t => t.active && t.role === 'MECHANIC');
  const refresh = () => setRevision(value => value + 1);
  const timeLabel = stamp => new Date(stamp).toLocaleTimeString('ru-RU', {timeZone:zone,hour:'2-digit',minute:'2-digit'});
  const fallback = !user.duty_roster_api ? data.duty : null;

  useEffect(() => {
    const abort = new AbortController();
    setError('');
    async function load() {
      try {
        const result = user.duty_roster_api
          ? await api('duty/roster/?' + new URLSearchParams({from, to}), {signal:abort.signal})
          : Array.from({length: (atDay(to) - atDay(from)) / 86400000 + 1}, (_, index) => {
            const date = addDays(from, index);
            return {date, shifts: (fallback || []).filter(s => civilDate(new Date(s.start), zone) === date)};
          });
        if (!abort.signal.aborted) setRows(result);
      } catch (e) {
        if (!abort.signal.aborted) {
          setRows([]);
          setError(e.message);
        }
      } finally {
        if (!abort.signal.aborted) setLoaded(key);
      }
    }
    load();
    return () => abort.abort();
  }, [key, user.duty_roster_api, fallback, zone]);

  function selectDate(date) {
    setAnchor(date);
    setSelected(date);
  }

  function preparePublication(rule) {
    refresh();
    if (!rule) return;
    const start = rule.from < firstFuture ? firstFuture : rule.from;
    selectDate(start);
    setModal({type:'publish', from:start, to:rule.to || monthBounds(start)[1], replace:!!rule.people});
  }

  const leading = (atDay(from).getUTCDay() + 6) % 7;
  const row = loaded === key && rows.find(item => item.date === selected);
  const vacant = day => !day.shifts.length && !day.covered_from_previous && !day.suggested_name;
  const canEdit = shift => user.can_manage && !shift.pending_swap && +new Date(shift.start) > now;
  const person = shift => shift.technician_name || technicians.find(t => t.id === shift.technician)?.full_name || 'Дежурный';
  const canCreate = row && !row.shifts.length && !row.covered_from_previous && row.start && +new Date(row.start) > now && user.can_manage;

  return <div className="duty-roster">
    <div className="page-heading"><div><h1>Дежурства</h1><p>Суточная смена с {startTime} до {startTime} следующего дня</p></div>
      {user.can_manage && user.duty_roster_api && <button onClick={() => setModal({type:'settings'})}><Settings2 size={17}/>Настройки графика</button>}
    </div>
    <DutyStatus user={user} data={data} onChanged={async () => {await onChanged?.(); refresh();}}/>
    <section className="panel roster-panel">
      <header className="panel-heading roster-tools">
        <div className="roster-period">
          <button aria-label="Предыдущий месяц" onClick={() => selectDate(monthBounds(addDays(from,-1))[0])}><ChevronLeft size={19}/></button>
          <h2 aria-live="polite">{dateLabel(from,{month:'long',year:'numeric'})}</h2>
          <button aria-label="Следующий месяц" onClick={() => selectDate(addDays(to,1))}><ChevronRight size={19}/></button>
        </div>
        {selected !== today && <button onClick={() => selectDate(today)}>Сегодня</button>}
      </header>
      {error && <p className="error roster-message" role="alert">{error} <button onClick={refresh}>Повторить</button></p>}
      {loaded !== key ? <p className="empty" role="status">Загрузка…</p> : !error && <>
        <div className="roster-month" aria-label="Календарь дежурств">
          {weekdays.map(day => <span className="roster-weekday" key={day}>{day}</span>)}
          {Array.from({length:leading},(_, i) => <span key={'space-' + i} aria-hidden="true"/>)}
          {rows.map(day => {
            const shift = day.shifts[0];
            const name = shift ? person(shift) : day.suggested_name;
            const label = name || (day.covered_from_previous ? 'Продолжается предыдущая смена' : 'Нет дежурного');
            return <button type="button" key={day.date}
              className={'roster-cell' + (day.suggested_name ? ' roster-draft' : '') + (day.needs_assignment ? ' roster-gap' : '')}
              aria-label={dateLabel(day.date) + ' · ' + label + (day.suggested_name && !shift ? ' · Черновик' : '')}
              aria-current={day.date === today ? 'date' : undefined} aria-pressed={day.date === selected}
              onClick={() => setSelected(day.date)}>
              <time dateTime={day.date}>{atDay(day.date).getUTCDate()}</time>
              <span className="roster-full-name">{name || (day.covered_from_previous ? '↪' : '—')}</span>
              <span className="roster-short-name" aria-hidden="true">{name ? name.trim().split(/\s+/)[0].slice(0,3) : day.covered_from_previous ? '↪' : '—'}</span>
            </button>;
          })}
        </div>
        {row && <section className="roster-details" aria-labelledby="roster-selected">
          <h3 id="roster-selected">{dateLabel(row.date,{weekday:'long',day:'numeric',month:'long'})}</h3>
          {row.shifts.map(shift => <div className="roster-detail-row" key={shift.id}>
            <div><strong>{person(shift)}</strong><small>{timeLabel(shift.start)} – {timeLabel(shift.end)}{shift.pending_swap && ' · ожидается ответ на подмену'}</small></div>
            {canEdit(shift) && <button onClick={() => setModal({type:'day',row,shift})}>Изменить</button>}
          </div>)}
          {!row.shifts.length && <p>{row.covered_from_previous ? 'Продолжается предыдущая смена' : 'Дежурный пока не назначен'}</p>}
          {row.suggested_name && <p className="muted">Черновик по очереди · {row.suggested_name}</p>}
          {row.needs_assignment && !vacant(row) && <p className="error">Проверьте назначение на эту дату</p>}
          {canCreate && <button className="primary" onClick={() => setModal({type:'day',row})}>Назначить</button>}
        </section>}
      </>}
      <footer className="panel-heading roster-tools">
        {notice && <span role="status">{notice}</span>}
        {user.can_manage && user.duty_roster_api && to >= firstFuture && <button className="primary"
          onClick={() => setModal({type:'publish',from:from < firstFuture ? firstFuture : from,to})}>Проверить и опубликовать</button>}
        <button disabled={loaded !== key || !!error} onClick={() => csv('LiftControl-duty.csv', [
          ['Механик','Начало','Окончание'], ...rows.flatMap(r => r.shifts.map(s => [person(s),s.start,s.end])),
        ])}><Download size={17}/>CSV</button>
      </footer>
    </section>
    {modal?.type === 'settings' && <DutyRules technicians={technicians} today={today} onClose={() => setModal(null)} onSaved={preparePublication}/>}
    {modal?.type === 'day' && <DayEditor row={modal.row} initialShift={modal.shift} technicians={technicians} canManage={user.can_manage} timeLabel={timeLabel}
      onClose={() => setModal(null)} onSaved={message => {setNotice(message); refresh();}}/>}
    {modal?.type === 'publish' && <PublishDialog initialFrom={modal.from} initialTo={modal.to} initialReplace={modal.replace} firstFuture={firstFuture}
      onClose={() => setModal(null)} onSaved={result => {
        setNotice(`График опубликован · новых смен ${result.added}, изменено ${result.updated}`);
        refresh();
      }}/>}
  </div>;
}

function PublishDialog({initialFrom, initialTo, initialReplace = false, firstFuture, onClose, onSaved}) {
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(initialTo);
  const [replace, setReplace] = useState(initialReplace);
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const publish = event.nativeEvent.submitter?.value === 'publish';
    if (busy || publish && (!plan?.changes.length || plan.missing.length)) return;
    setBusy(true);
    setError('');
    try {
      const result = await api('duty/roster-publish/', {method:'POST',body:{
        from,to,replace_existing:replace,...(publish ? {token:plan.token} : {preview:true}),
      }});
      if (publish) {onSaved(result); onClose();}
      else setPlan(result);
    } catch (e) {setError(e.message); setPlan(null);}
    finally {setBusy(false);}
  }

  return <Dialog title="Проверить и опубликовать" onClose={() => !busy && onClose()}>
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="С даты"><input type="date" min={firstFuture} required disabled={busy} value={from} onChange={e => {setFrom(e.target.value);setPlan(null);}}/></Field>
        <Field label="По дату включительно"><input type="date" min={from || firstFuture} required disabled={busy} value={to} onChange={e => {setTo(e.target.value);setPlan(null);}}/></Field>
      </div>
      <label className="roster-replace"><input type="checkbox" checked={replace} disabled={busy} onChange={e => {setReplace(e.target.checked);setPlan(null);}}/>Пересчитать уже назначенные суточные смены</label>
      {replace && <p className="muted">В проверку попадут и ручные назначения. Смены с историей подмен сохранятся.</p>}
      {plan && <div className="plan-preview" aria-live="polite">
        <strong>Новых смен {plan.added} · замен {plan.updated}</strong>
        {plan.missing.length > 0 && <p className="error">Назначьте дежурных на даты {plan.missing.join(', ')}</p>}
        {!plan.missing.length && !plan.changes.length && <p>График уже заполнен. Изменений для публикации нет.</p>}
        {plan.changes.length > 0 && <ul className="roster-preview-list">{plan.changes.map(change =>
          <li key={change.date}><b>{dateLabel(change.date)}</b> · {change.old_name && change.old_name + ' → '}{change.new_name}</li>)}</ul>}
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions">
        <button type="button" disabled={busy} onClick={onClose}>Закрыть</button>
        <button value="preview" type="submit" className={plan ? '' : 'primary'} disabled={busy}>{busy ? 'Загрузка…' : 'Проверить даты'}</button>
        {plan?.changes.length > 0 && !plan.missing.length && <button value="publish" type="submit" className="primary" disabled={busy}>Опубликовать</button>}
      </div>
    </form>
  </Dialog>;
}

function DayEditor({row, initialShift, technicians, canManage, timeLabel, onClose, onSaved}) {
  const canCreate = canManage && !row.covered_from_previous && row.start && +new Date(row.start) > Date.now();
  const [shift, setShift] = useState(initialShift || (row.shifts.length === 1 ? row.shifts[0] : null));
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
