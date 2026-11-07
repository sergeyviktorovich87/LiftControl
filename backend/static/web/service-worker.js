/* LiftControl Web Push worker. This file must be served at /sw.js (root scope). */
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const title = typeof data.title === 'string' ? data.title.slice(0, 120) : 'LiftControl';
  const text = typeof data.body === 'string' ? data.body.slice(0, 240) : 'Есть обновление заявки';
  const tag = typeof data.tag === 'string' ? data.tag.slice(0, 80) : 'liftcontrol';
  event.waitUntil(self.registration.showNotification(title, {
    body: text,
    tag: tag,
    icon: '/static/web/favicon.ico',
    badge: '/static/web/favicon.ico',
    data: {url: '/#tickets'},
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(windows => {
    for (const tab of windows) {
      if (new URL(tab.url).origin === self.location.origin) {
        tab.focus();
        return tab.navigate('/#tickets');
      }
    }
    return clients.openWindow('/#tickets');
  }));
});
