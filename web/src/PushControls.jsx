import React, { useEffect, useState } from 'react';
import { api } from './api';

/* A settings row, reusing the existing LiftControl 0.4 visual system. */
function decodeVapidKey(value) {
  const padded = (value + '='.repeat((4 - value.length % 4) % 4))
    .replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

export default function PushControls({ user }) {
  const [config, setConfig] = useState(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user.role !== 'MECHANIC') return;
    api('push/public-key/').then(async next => {
      setConfig(next);
      if (!next.enabled || !('serviceWorker' in navigator)) return;
      const registration = await navigator.serviceWorker.getRegistration('/');
      const sub = await registration?.pushManager.getSubscription();
      setEnabled(Boolean(sub));
    }).catch(() => setMessage('Не удалось получить настройки уведомлений.'));
  }, [user.role]);

  if (user.role !== 'MECHANIC') return null;

  const available = typeof window !== 'undefined' && window.isSecureContext
    && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

  const enable = async () => {
    if (!config?.enabled || !available || busy) return;
    setBusy(true);
    setMessage('');
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setMessage('Для push-уведомлений разрешите уведомления в браузере.');
        return;
      }
      const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      const ready = await navigator.serviceWorker.ready;
      let sub = await ready.pushManager.getSubscription();
      if (!sub) {
        sub = await ready.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: decodeVapidKey(config.public_key),
        });
      }
      await api('push/subscription/', { method: 'POST', body: sub.toJSON() });
      setEnabled(true);
      setMessage('Уведомления подключены на этом устройстве.');
    } catch (err) {
      setMessage(err.message || 'Не удалось подключить уведомления.');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    if (busy) return;
    setBusy(true);
    setMessage('');
    try {
      const reg = await navigator.serviceWorker.getRegistration('/');
      const sub = await reg?.pushManager.getSubscription();
      if (sub) {
        await api('push/subscription/', { method: 'DELETE', body: { endpoint: sub.endpoint } });
        await sub.unsubscribe();
      }
      setEnabled(false);
      setMessage('Уведомления отключены на этом устройстве.');
    } catch (err) {
      setMessage(err.message || 'Не удалось отключить уведомления.');
    } finally {
      setBusy(false);
    }
  };

  return <div className="setting-row">
    <div>
      <h2>Push-уведомления о заявках</h2>
      <p>Новые заявки и изменения статуса. Подписка включается отдельно на каждом телефоне.</p>
      {!config?.enabled && <small>Администратору необходимо настроить VAPID и HTTPS.</small>}
      {!available && <small>На этом устройстве или в браузере push недоступен.</small>}
      {message && <p role="status">{message}</p>}
    </div>
    <button type="button" disabled={busy || !available || !config?.enabled}
      onClick={enabled ? disable : enable}>
      {busy ? 'Обработка…' : enabled ? 'Отключить' : 'Включить push'}
    </button>
  </div>;
}
