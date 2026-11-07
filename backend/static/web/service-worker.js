/* No data caching: every company and private attachment is authorized by the server. */
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(clients.claim()));
function ticketURL(data) {
  const organization=Number(data.organization_id),ticket=Number(data.ticket_id);
  if(Number.isSafeInteger(organization)&&organization>0&&Number.isSafeInteger(ticket)&&ticket>0)
    return '/?organization='+organization+'&ticket='+ticket+'#tickets';
  return '/#tickets';
}
self.addEventListener('push', event => {
  let data={};
  try {data=event.data?event.data.json():{};} catch {}
  if(!data||typeof data!=='object')data={};
  event.waitUntil(self.registration.showNotification(
    typeof data.title==='string'?data.title.slice(0,120):'Лифт Контроль',{
      body:typeof data.body==='string'?data.body.slice(0,240):'Есть обновление заявки',
      tag:typeof data.tag==='string'?data.tag.slice(0,80):'liftcontrol',
      silent:false, renotify:true, vibrate:[250,100,250], requireInteraction:true,
      data:{url:ticketURL(data)},
    }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const raw=event.notification.data?.url;
  const url=typeof raw==='string'&&/^\/\?organization=[1-9][0-9]*&ticket=[1-9][0-9]*#tickets$/.test(raw)?raw:'/#tickets';
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(windows=>{
    for(const tab of windows)if(new URL(tab.url).origin===self.location.origin){
      return tab.navigate(url).then(next=>(next||tab).focus());
    }
    return clients.openWindow(url);
  }));
});
