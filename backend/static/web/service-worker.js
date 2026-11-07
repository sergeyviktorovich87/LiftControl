/* No business-data cache. IndexedDB stores only notification event cursors. */
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(clients.claim()));
function ticketURL(data){
 const o=Number(data.organization_id),t=Number(data.ticket_id);
 return Number.isSafeInteger(o)&&o>0&&Number.isSafeInteger(t)&&t>0?`/?organization=${o}&ticket=${t}#tickets`:null;
}
function once(key,id){return new Promise(resolve=>{
 const open=indexedDB.open('liftcontrol-push-cursors',1);
 open.onupgradeneeded=()=>open.result.createObjectStore('events');
 open.onerror=()=>resolve(false);
 open.onsuccess=()=>{
  const db=open.result,tx=db.transaction('events','readwrite'),store=tx.objectStore('events'),get=store.get(key);let fresh=false;
  get.onsuccess=()=>{if((get.result||0)<id){store.put(id,key);fresh=true;}};
  tx.oncomplete=()=>{db.close();resolve(fresh);};tx.onerror=()=>{db.close();resolve(false);};
 };
});}
self.addEventListener('push',event=>event.waitUntil((async()=>{
 let data;try{data=event.data?.json();}catch{return;}
 if(!data||!ticketURL(data)||!Number.isSafeInteger(data.event_id)||data.event_id<1)return;
 const tag=`org-${Number(data.organization_id)}-ticket-${Number(data.ticket_id)}`;
 try{
  const result=await fetch(`/api/tickets/${Number(data.ticket_id)}/?organization=${Number(data.organization_id)}`,{credentials:'same-origin',cache:'no-store'});
  if(!result.ok)return;
  const current=await result.json();
  if(current.status!==data.status){for(const n of await self.registration.getNotifications({tag}))n.close();return;}
 }catch{return;}
 if(!await once(tag,data.event_id))return;
 await self.registration.showNotification(typeof data.title==='string'?data.title.slice(0,120):'Лифт Контроль',{
  body:typeof data.body==='string'?data.body.slice(0,240):'Есть обновление заявки',
  tag,silent:false,renotify:false,vibrate:[250,100,250],requireInteraction:false,
  data:{url:ticketURL(data),event_id:data.event_id},
 });
})()));
self.addEventListener('notificationclick',event=>{
 event.notification.close();const raw=event.notification.data?.url;
 const url=typeof raw==='string'&&/^\/\?organization=[1-9][0-9]*&ticket=[1-9][0-9]*#tickets$/.test(raw)?raw:'/#tickets';
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(windows=>{
  for(const tab of windows)if(new URL(tab.url).origin===self.location.origin)return tab.navigate(url).then(next=>(next||tab).focus());
  return clients.openWindow(url);
 }));
});
