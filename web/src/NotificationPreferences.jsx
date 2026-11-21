import React, {useEffect, useState} from 'react';
import {api, PREVIEW} from './api';

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const defaults = {
  only_mine: false,
  quiet_enabled: false,
  quiet_start: '22:00',
  quiet_end: '08:00',
  muted_weekdays: [],
};
const endpoint = 'notification-preferences/';

export default function NotificationPreferences({user}) {
  const [values, setValues] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    if (PREVIEW) setValues(defaults);
    else api(endpoint, {signal: request.signal}).then(data => {
      if (!request.signal.aborted) setValues({...defaults, ...data});
    }).catch(exception => {
      if (!request.signal.aborted) setError(exception.message);
    });
    return () => request.abort();
  }, [retry]);

  function change(key, value) {
    setValues(previous => ({...previous, [key]: value}));
    setSaved(false);
    setError('');
  }

  async function save(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    setSaved(false);
    try {
      const body = Object.fromEntries(Object.keys(defaults).map(key => [key, values[key]]));
      const next = PREVIEW ? body : await api(endpoint, {method:'PATCH', body});
      setValues({...defaults, ...next});
      setSaved(true);
    } catch (exception) {
      setError(exception.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="setting-row">
    <div>
      <h2>Настройки push</h2>
      <p>Действуют на всех ваших устройствах в организации «{user.organization}». Время — по часовому поясу организации.</p>
      {!values && !error && <p>Загрузка…</p>}
      {!values && error && <button onClick={() => {setError(''); setRetry(value => value + 1);}}>Повторить</button>}
      {values && <form onSubmit={save}>
        <fieldset disabled={busy} className="push-preference-fields">
          <label className="notification-choice">
            <input type="checkbox" checked={values.only_mine} onChange={event => change('only_mine', event.target.checked)}/>
            <span><b>Только мои push</b><small>Мои заявки и задания, заявки дежурной смены и моя пусконаладка.</small></span>
          </label>
          <label className="notification-choice">
            <input type="checkbox" checked={values.quiet_enabled} onChange={event => change('quiet_enabled', event.target.checked)}/>
            <span><b>Тихие часы</b><small>Ежедневный интервал без push. Можно задать время через полночь.</small></span>
          </label>
          {values.quiet_enabled && <div className="range">
            <label className="field">Начало тихих часов
              <input type="time" required value={values.quiet_start} onChange={event => change('quiet_start', event.target.value)}/>
            </label>
            <label className="field">Конец тихих часов
              <input type="time" required value={values.quiet_end} onChange={event => change('quiet_end', event.target.value)}/>
            </label>
          </div>}
          <fieldset className="push-preference-fields">
            <legend>Дни без push целиком</legend>
            <div className="push-weekdays">
              {weekdays.map((day, index) => <label key={day}>
                <input type="checkbox" checked={values.muted_weekdays.includes(index)} onChange={event => change(
                  'muted_weekdays', event.target.checked ? [...values.muted_weekdays, index] : values.muted_weekdays.filter(value => value !== index),
                )}/> {day}
              </label>)}
            </div>
          </fieldset>
          <button className="primary" type="submit">{busy ? 'Сохранение…' : 'Сохранить настройки push'}</button>
        </fieldset>
      </form>}
      {saved && <p role="status">Настройки сохранены.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <small>Все доступные события сохраняются в центре уведомлений.</small>
    </div>
  </section>;
}
