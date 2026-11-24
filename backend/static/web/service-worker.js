/* No business-data cache. IndexedDB stores only notification event cursors. */
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(clients.claim()));
function ticketURL(data){
 const personal=data.target==='task';
 const o=Number(data.organization_id),t=Number(personal?data.task_id:data.ticket_id);
 return Number.isSafeInteger(o)&&o>0&&Number.isSafeInteger(t)&&t>0?`/?organization=${o}&${personal?'task':'ticket'}=${t}#${personal?'tasks':'tickets'}`:null;
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
 const personal=data.target==='task';
 const objectId=Number(personal?data.task_id:data.ticket_id);
 const tag=`org-${Number(data.organization_id)}-${personal?'task':'ticket'}-${objectId}`;
 let critical=false;
 try{
  const result=await fetch(`/api/${personal?'tasks':'tickets'}/${objectId}/?organization=${Number(data.organization_id)}`,{credentials:'same-origin',cache:'no-store'});
  if(!result.ok)return;
  const current=await result.json();
  critical=!personal&&current.priority==='ENTRAPMENT'&&['created','reassigned','escalated'].includes(data.kind);
  if(current.status!==data.status){for(const n of await self.registration.getNotifications({tag}))n.close();return;}
 }catch{return;}
 if(!await once(tag,data.event_id))return;
 await self.registration.showNotification(typeof data.title==='string'?data.title.slice(0,120):'Лифт Контроль',{
  body:typeof data.body==='string'?data.body.slice(0,240):'Есть обновление заявки',
  tag,silent:false,renotify:critical,vibrate:critical?[600,120,600,120,600]:[250,100,250],requireInteraction:critical,
  data:{url:ticketURL(data),event_id:data.event_id},
 });
})()));
self.addEventListener('notificationclick',event=>{
 event.notification.close();const raw=event.notification.data?.url;
 const url=typeof raw==='string'&&/^\/\?organization=[1-9][0-9]*&(?:ticket=[1-9][0-9]*#tickets|task=[1-9][0-9]*#tasks)$/.test(raw)?raw:'/#tickets';
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(windows=>{
  for(const tab of windows)if(new URL(tab.url).origin===self.location.origin)return tab.navigate(url).then(next=>(next||tab).focus());
  return clients.openWindow(url);
 }));
});

/* Network-only app navigation. Never cache authenticated HTML, API, or uploads.
 * Existing push handling above remains unchanged. */
const offlinePage='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#18372b"><title>Лифт Контроль — нет связи</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#eef2ee;font:16px system-ui;color:#18372b}main{max-width:340px;padding:28px}a{display:inline-block;padding:12px 18px;background:#237451;color:white;border-radius:10px;text-decoration:none}</style></head><body><main><h1>Нет связи с сервером</h1><p>Проверьте интернет. Данные не загружены. Офлайн-отправка заявок не поддерживается.</p><a href="/">Повторить подключение</a></main></body></html>';
self.addEventListener('fetch',event=>{
 const request=event.request;
 if(request.method!=='GET'||request.mode!=='navigate')return;
 const url=new URL(request.url);
 if(url.origin!==self.location.origin||!['/','/login/'].includes(url.pathname))return;
 event.respondWith(fetch(request,{cache:'no-store'}).catch(()=>new Response(offlinePage,{
  status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
 })));
});
