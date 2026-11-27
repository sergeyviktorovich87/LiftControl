import TicketCreate from './TicketCreate';
import MessageReceipt from './MessageReceipt';
import {MAX_FILE_BYTES} from './uploadLimits.js';
import MediaLibrary from './MediaLibrary';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { Badge, Dialog, Field, LocationFields } from './components';
import {prepareImages} from './imageCompression';

/* Reuses existing LiftControl 0.4 components and CSS, without a redesign. */
export default function TicketWorkflow({ item = {}, data, user, onClose, onSaved, onOpenLift, onDiscuss }) {
  const existing = Boolean(item.id);
  const [ticket, setTicket] = useState(item);
  const delivery = ticket.delivery;
  const [history, setHistory] = useState({ events: [], comments: [] });
  const [form, setForm] = useState({
    elevator: item.elevator || '',
    title: item.title || '',
    description: item.description || '',
    priority: item.priority || 'NORMAL',
  });
  const [note, setNote] = useState('');
  const [repair, setRepair] = useState('');
  const [files, setFiles] = useState([]);
  const [reason, setReason] = useState('');
  const [stopReason, setStopReason] = useState('');
  const [repairDelay, setRepairDelay] = useState({reason: '', expected_date: ''});
  const [assigned, setAssigned] = useState(item.assigned_to || '');
  const eligible = data.technicians.filter(t => t.active && t.can_receive_tasks !== false);
  const [assignReason, setAssignReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showMedia,setShowMedia]=useState(false);
  const [info, setInfo] = useState('');

  const refresh = useCallback(async () => {
    if (!existing) return;
    const [t, h] = await Promise.all([
      api('tickets/' + item.id + '/'),
      api('tickets/' + item.id + '/history/'),
    ]);
    setTicket(t);
    setHistory(h);
    if(user.message_receipts_api){
      await api('notifications/receipts/',{method:'POST',body:{target:'ticket',ids:[item.id]}});
      if(h.comments.length)await api('notifications/receipts/',{method:'POST',body:{target:'ticket_comment',ids:h.comments.slice(-200).map(c=>c.id)}});
    }
    setAssigned(current=>current || t.assigned_to || '');
  }, [existing, item.id]);

  useEffect(() => {
    if (!existing) return;
    refresh().catch(e => setError(e.message));
    const interval = window.setInterval(() => {
      if (!document.hidden) refresh().catch(() => {});
    }, 10000);
    return () => window.clearInterval(interval);
  }, [existing, refresh]);

  const run = async fn => {
    if (busy) return;
    setBusy(true);
    setError('');
    setInfo('');
    try {
      const next = await fn();
      if (!existing) { await onSaved(); onClose(); return; }
      await refresh();
      await onSaved();
      if (next) setInfo(next);
    } catch (e) {
      setError(e.message || 'Операция не выполнена');
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    await run(async () => {
      if (repair.trim().length < 3) throw Error('Заполните выполненные работы.');
      if (files.length + (ticket.photos || []).length > 8) throw Error('Допускается максимум 8 фотографий.');
      // Upload first: a failed upload must never falsely mark the ticket complete.
      for (const file of files) {
        if (file.size > MAX_FILE_BYTES) throw Error('Фотография больше 100 МБ.');
        const body = new FormData();
        body.append('file', file);
        await api('tickets/' + ticket.id + '/photos/', { method: 'POST', body });
        // Never upload the same successful attachment again on a retry.
        setFiles(previous => previous.filter(candidate => candidate !== file));
      }
      await api('tickets/' + ticket.id + '/complete/', {
        method: 'POST', body: { work_description: repair.trim() },
      });
      setRepair('');
      return 'Работы сохранены, заявка выполнена.';
    });
  };

  const canComment = ['NEW', 'IN_PROGRESS', 'STOPPED', 'LONG_REPAIR'].includes(ticket.status)
    && (user.can_manage || user.on_duty || ticket.can_complete);

  if(!existing)return <TicketCreate item={item} data={data} user={user} onClose={onClose} onSaved={onSaved}/>;

  return <Dialog wide title={existing ? 'Заявка #' + ticket.id : 'Новая заявка'} onClose={onClose}>
    <>
      <div className="panel">
        <div className="panel-heading">
          <div><h2>{ticket.title}</h2><p>{ticket.address} · {ticket.elevator_label||ticket.elevator_factory_number||'Лифт не уточнён'}</p></div>
          <Badge value={ticket.status} />
          {ticket.priority==='ENTRAPMENT'&&<Badge value="ENTRAPMENT">Застревание — люди в кабине</Badge>}
        </div>
        <div className="dialog-content">
          <p>{ticket.description || 'Описание не указано.'}</p>
          {ticket.elevator&&<button type="button" onClick={()=>onOpenLift?.(ticket.elevator)}>Открыть карточку лифта</button>} {onDiscuss&&<button type="button" onClick={onDiscuss}>Обсудить в чате</button>}
          <p className="muted small">Автор: {ticket.created_by_name || 'Ранее созданная заявка'} ·
            Исполнитель: {ticket.technician_name || 'Не назначен'}</p>
          {delivery&&<MessageReceipt user={user} target="ticket" id={ticket.id} own={false}><p>
            {{pending:'Ожидает подтверждения доставки',no_recipient:'У заявки нет получателя',received:'✓✓ Доставлено на устройство',read:'✓✓ Прочитано механиком',unconfirmed:'Нет подтверждения доставки'}[delivery.state]}
            {(delivery.read_at||delivery.received_at)&&' · '+new Date(delivery.read_at||delivery.received_at).toLocaleString('ru-RU',{timeZone:user.timezone})}
          </p></MessageReceipt>}
          {ticket.repair && <div className="notice"><b>Выполненные работы:</b> {ticket.repair}</div>}
          {ticket.stopped_at && <div className="notice"><b>{ticket.status==='DONE'?'Остановка в истории:':'Лифт остановлен:'}</b> {ticket.stop_reason}
            <small>{new Date(ticket.stopped_at).toLocaleString('ru-RU',{timeZone:user.timezone})}</small></div>}
          {ticket.status==='LONG_REPAIR'&&<div className="notice">
            <b>Длительный ремонт</b> <p>{ticket.long_repair_reason}</p>
            {ticket.expected_repair_date&&<small>Ожидаемая дата · {ticket.expected_repair_date.split('-').reverse().join('.')}</small>}
          </div>}
          {ticket.cancellation_reason && <div className="notice">
            <b>Причина отмены:</b> {ticket.cancellation_reason}</div>}
        </div>
      </div>

      {(ticket.entrance_hint||ticket.floor_hint)&&<p className="notice">{[ticket.entrance_hint&&'Подъезд '+ticket.entrance_hint,ticket.floor_hint&&'Этаж '+ticket.floor_hint].filter(Boolean).join(' · ')}</p>}
      {(ticket.contact_name||ticket.contact_phone)&&<p className="muted">Заявитель: {ticket.contact_name} {ticket.contact_phone}</p>}
      {ticket.can_identify_lift&&<section className="panel dialog-content"><h2>Уточнить лифт</h2><p className="muted">Номер заявки, фотографии и история сохранятся.</p><Field label="Лифт в доме заявки"><select value={form.elevator} onChange={e=>setForm(f=>({...f,elevator:e.target.value}))}><option value="">Выберите лифт</option>{data.elevators.filter(l=>l.active&&l.building===ticket.building).map(l=><option key={l.id} value={l.id}>{l.display_number||l.factory_number||l.inventory_number} · {l.entrance||'—'}</option>)}</select></Field><button type="button" disabled={busy||!form.elevator} onClick={()=>run(async()=>{await api(`tickets/${ticket.id}/identify-lift/`,{method:'POST',body:{elevator:Number(form.elevator)}});return 'Лифт уточнён. История заявки сохранена.';})}>Сохранить лифт</button></section>}
      <button type="button" onClick={()=>setShowMedia(v=>!v)}>Вложения: фото и видео</button>{showMedia&&<MediaLibrary user={user} ticket={ticket.id}/>}
      {ticket.entrapment_acknowledged && <p className="muted">Дежурный подтвердил застревание</p>}
      {ticket.can_acknowledge_entrapment && !ticket.entrapment_acknowledged && <div className="form-actions">
        <button type="button" className="danger" disabled={busy} onClick={() => run(async () => {
          await api('tickets/' + ticket.id + '/acknowledge-entrapment/', {method: 'POST'});
        })}>Подтвердить застревание</button>
      </div>}
      {ticket.can_accept && <div className="form-actions">
        <button className="primary" disabled={busy}
          onClick={() => run(async () => {
            await api('tickets/' + ticket.id + '/accept/', { method: 'POST' });
            return 'Заявка принята вами в работу.';
          })}>Принять заявку</button>
      </div>}

      {ticket.can_stop && <section className="panel dialog-content">
        <h2>Не удалось восстановить работу</h2>
        <Field label="Причина остановки"><textarea maxLength={1000} value={stopReason} onChange={e=>setStopReason(e.target.value)} placeholder="Почему лифт остаётся остановленным и что требуется для ремонта"/></Field>
        <footer className="form-actions"><button type="button" className="danger" disabled={busy||stopReason.trim().length<5}
          onClick={()=>run(async()=>{await api(`tickets/${ticket.id}/stop/`,{method:'POST',body:{reason:stopReason.trim()}});setStopReason('');return 'Остановка сохранена. Заявка остаётся открытой.';})}>Лифт остановлен</button></footer>
      </section>}
      {ticket.can_resume && <div className="form-actions"><button disabled={busy} onClick={()=>run(async()=>{await api(`tickets/${ticket.id}/resume/`,{method:'POST'});return 'Ремонт продолжен.';})}>Продолжить ремонт</button></div>}

      {ticket.can_complete&&<details className="panel dialog-content">
        <summary>Длительный ремонт</summary>
        <Field label="Причина длительного ремонта"><textarea maxLength={1000} value={repairDelay.reason} onChange={e=>setRepairDelay({...repairDelay,reason:e.target.value})}/></Field>
        <Field label="Ожидаемая дата (необязательно)"><input type="date" value={repairDelay.expected_date} onChange={e=>setRepairDelay({...repairDelay,expected_date:e.target.value})}/></Field>
        <button type="button" disabled={busy||repairDelay.reason.trim().length<5} onClick={()=>run(async()=>{
          await api(`tickets/${ticket.id}/long-repair/`,{method:'POST',body:repairDelay});
          setRepairDelay({reason:'',expected_date:''});
          return 'Длительный ремонт сохранён.';
        })}>Сохранить длительный ремонт</button>
      </details>}

      {ticket.can_complete && <section className="panel dialog-content">
        <h2>Завершение ремонта</h2>
        <Field label="Выполненные работы">
          <textarea value={repair} maxLength={4000} onChange={e => setRepair(e.target.value)}
            placeholder="Что сделано и как восстановлена работа лифта" />
        </Field>
        <Field label="Фотографии ремонта (необязательно)">
          <input type="file" multiple accept="image/jpeg,image/png,image/webp" disabled={busy}
            onChange={async e => {const selected=Array.from(e.target.files||[]);e.target.value='';if(selected.length>8){setError('До 8 фотографий.');return;}setBusy(true);try{setFiles(await prepareImages(selected));setError('');}catch(e){setError(e.message);}finally{setBusy(false);}}} />
        </Field>
        <small>{files.length} фотографий выбрано. После завершения записи нельзя удалять.</small>
        <footer className="form-actions"><button type="button" className="primary"
          disabled={busy || repair.trim().length < 3} onClick={complete}>Выполнено</button></footer>
      </section>}

      {canComment && <section className="panel dialog-content">
        <h2>Добавить комментарий</h2>
        <Field label="Запись остаётся в истории и не редактируется">
          <textarea maxLength={4000} value={note} onChange={e => setNote(e.target.value)} />
        </Field>
        <footer className="form-actions"><button type="button" disabled={busy || !note.trim()}
          onClick={() => run(async () => {
            await api('tickets/' + ticket.id + '/comment/', { method: 'POST', body: { body: note.trim() } });
            setNote('');
            return 'Комментарий сохранён.';
          })}>Добавить комментарий</button></footer>
      </section>}

      {ticket.status === 'NEW' && (user.can_manage || user.on_duty) && <section className="panel dialog-content">
        <h2>Назначить замену</h2>
        <Field label="Механик">
          <select value={assigned} onChange={e => setAssigned(e.target.value)}>
            <option value="">Выберите механика</option>
            {eligible.map(t =>
              <option key={t.id} value={t.id}>{t.full_name}</option>)}
          </select>
        </Field>
        <Field label="Причина переназначения">
          <textarea value={assignReason} maxLength={1000}
            onChange={e => setAssignReason(e.target.value)} />
        </Field>
        <footer className="form-actions"><button type="button" disabled={busy || !assigned || assignReason.trim().length < 5}
          onClick={() => run(async () => {
            await api('tickets/' + ticket.id + '/assign/', { method: 'POST',
              body: { assigned_to: Number(assigned), reason: assignReason.trim() } });
            setAssignReason('');
            return 'Исполнитель изменён с записью причины.';
          })}>Назначить</button></footer>
      </section>}

      {ticket.can_cancel && <section className="panel dialog-content">
        <h2>Отменить заявку</h2>
        <p className="muted small">Заявка, комментарии и фотографии останутся в истории лифта.</p>
        <Field label="Обязательная причина">
          <textarea value={reason} maxLength={1000}
            onChange={e => setReason(e.target.value)} />
        </Field>
        <footer className="form-actions"><button type="button" disabled={busy || reason.trim().length < 5}
          onClick={() => run(async () => {
            await api('tickets/' + ticket.id + '/cancel/', { method: 'POST', body: { reason: reason.trim() } });
            setReason('');
            return 'Заявка отменена. Причина сохранена.';
          })}>Отменить с причиной</button></footer>
      </section>}

      {!!(ticket.photos || []).length && <section className="panel dialog-content">
        <h2>Фотографии</h2><div className="photos">
          {ticket.photos.map(p => <figure key={p.id}>
            <a href={p.url} target="_blank" rel="noreferrer">
              <img src={p.url} alt={'Фото ремонта ' + p.id} />
            </a>
            <figcaption><small>{p.uploaded_by || 'Исполнитель'} ·
              {p.created_at ? ' ' + new Date(p.created_at).toLocaleString('ru-RU') : ''}</small></figcaption>
          </figure>)}
        </div>
        <small>Фото являются частью истории заявки, удаление запрещено.</small>
      </section>}

      <section className="panel dialog-content">
        <h2>История заявки</h2>
        {[...(history.events || [])].reverse().map(ev =>
          <div className="list-row" key={'ev-' + ev.id}>
            <span><b>{({
              created: 'Создана', lift_identified: 'Уточнён лифт', escalated: 'Приоритет повышен до застревания',
              entrapment_acknowledged: 'Дежурный подтвердил застревание', accepted: 'Принята в работу', completed: 'Выполнена',
              canceled: 'Отменена', reassigned: 'Переназначена', commented: 'Комментарий',
              stopped: 'Лифт остановлен', resumed: 'Ремонт продолжен', long_repair: 'Длительный ремонт',
            })[ev.action] || ev.action}</b>
              <small>{ev.actor} · {new Date(ev.created_at).toLocaleString('ru-RU')}</small>
              {ev.reason && <p>{ev.reason}</p>}
            </span>
          </div>)}
        {(history.comments || []).map(c =>
          <MessageReceipt key={'comment-'+c.id} user={user} target="ticket_comment" id={c.id} own={c.author_id===user.id} receipt={c.receipt}><div className="list-row">
            <span><b>{c.kind === 'RESULT' ? 'Результат ремонта' : 'Комментарий'}</b>
              <small>{c.author} · {new Date(c.created_at).toLocaleString('ru-RU')}</small>
              <p>{c.body}</p>
            </span>
          </div></MessageReceipt>)}
        {!history.events?.length && !history.comments?.length && <p className="muted">Записей пока нет.</p>}
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      {info && <p className="notice" role="status">{info}</p>}
      <footer className="form-actions"><button onClick={onClose}>Закрыть</button></footer>
    </>
  </Dialog>;
}

