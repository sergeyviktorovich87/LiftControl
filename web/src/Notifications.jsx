import React, {useCallback, useEffect, useRef, useState} from 'react';
import {api} from './api';

export default function Notifications({user, onOpen = () => {}, onRead, initialEntrapment = false}) {
  const [category, setCategory] = useState(initialEntrapment ? 'entrapment' : 'ordinary');
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [nextBefore, setNextBefore] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const request = useRef(0);
  const loadingRequest = useRef(0);
  const historyExtended = useRef(false);
  const busy = useRef(false);

  const load = useCallback(async ({signal, before = null, quiet = false} = {}) => {
    if (quiet && (loadingRequest.current || busy.current || historyExtended.current)) return;
    const serial = ++request.current;
    if (!quiet) {
      loadingRequest.current = serial;
      setLoading(true);
      setError('');
    }
    try {
      const params = new URLSearchParams({limit: '30'});
      if (user.lift_documents_api || user.commissioning_notification_tabs) params.set('category', user.commissioning_only?'commissioning':category);
      if (user.commissioning_notification_tabs && user.can_commissioning) params.set('group_commissioning','1');
      if (before !== null) params.set('before', before);
      const data = await api('notifications/?' + params, {signal});
      if (signal?.aborted || serial !== request.current) return;
      setItems(current => before === null ? data.results : [...current, ...data.results]);
      setCounts(data.unread_by_category || {});
      setNextBefore(data.next_before ?? null);
      historyExtended.current = before !== null;
      setError('');
    } catch (e) {
      if (!quiet && !signal?.aborted && serial === request.current) setError(e.message);
    } finally {
      if (loadingRequest.current === serial) {
        loadingRequest.current = 0;
        if (!signal?.aborted && serial === request.current) setLoading(false);
      }
    }
  }, [category, user.organization_id, user.lift_documents_api, user.commissioning_notification_tabs, user.can_commissioning, user.commissioning_only]);

  useEffect(() => {
    const abort = new AbortController();
    load({signal: abort.signal});
    const timer = setInterval(() => {
      if (!document.hidden) load({signal: abort.signal, quiet: true});
    }, 15000);
    return () => {
      ++request.current;
      abort.abort();
      clearInterval(timer);
    };
  }, [load]);

  async function open(item) {
    if (busy.current || loading) return;
    ++request.current;
    busy.current = true;
    setOpening(true);
    try {
      if (!item.read_at) {
        const result = await api('notifications/' + item.id + '/read/', {method: 'POST', body: {}});
        setItems(current => current.map(row => row.id === item.id ? {...row, read_at: result.read_at} : row));
        setCounts(current => ({...current, [item.category]: Math.max(0, (current[item.category] || 0) - 1)}));
        onRead?.();
      }
      onOpen(item.target_type, item.target_id);
    } catch (e) {
      setError(e.message);
    } finally {
      busy.current = false;
      setOpening(false);
    }
  }

  return <>
    <div className="page-heading">
      <h1>Уведомления</h1>
      <div className="actions"><button onClick={()=>{location.hash='settings/notifications';}}>Настройки уведомлений</button><button disabled={loading || opening} onClick={() => load()}>Обновить</button></div>
    </div>
    {user.lift_documents_api === 1 && <div className="tabs" aria-label="Тип уведомлений">
      {[['entrapment', 'Важные'], ['ordinary', 'Обычные'],
        ...(user.commissioning_notification_tabs && user.can_commissioning ? [['commissioning','Пусконаладка']] : [])].map(([id, label]) =>
        <button key={id} type="button" disabled={opening || loading} aria-pressed={category === id}
          className={category === id ? 'selected' : ''} onClick={() => {
            if (category === id) return;
            ++request.current;
            setItems([]);
            setNextBefore(null);
            setCategory(id);
          }}>
          {label}{counts[id] > 0 && <span className="unread-count" aria-label={counts[id] + ' непрочитанных'}>{counts[id] > 99 ? '99+' : counts[id]}</span>}
        </button>)}
    </div>}
    {error && <p className="error" role="alert">{error}</p>}
    <section className="panel" aria-busy={loading}>
      {items.map(item => <button type="button" className={'list-row ' + (item.category === 'entrapment' ? 'entrapment-notification' : '')}
        disabled={loading || opening} key={item.id} onClick={() => open(item)}>
        <span style={{flex: 1, textAlign: 'left', minWidth: 0}}>
          <b>{item.title}</b>
          {item.body&&<p className="notification-body">{item.body}</p>}
          <small>{new Date(item.created_at).toLocaleString('ru-RU', {dateStyle: 'short', timeStyle: 'short'})}</small>
        </span>{!item.read_at && <span aria-label="Непрочитанное">●</span>}
      </button>)}
      {!items.length && !loading && !error && <p className="empty">Уведомлений нет</p>}
      {nextBefore !== null && <button type="button" className="button"
        disabled={loading || opening} onClick={() => load({before: nextBefore})}>Загрузить ещё</button>}
    </section>
  </>;
}
