/* Network-only business data. IndexedDB contains successful-display cursors only. */
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(clients.claim()));
const displayJobs=new Map(),memoryCursors=new Map();
function ticketURL(data){
 const personal=data.target==='task',o=Number(data.organization_id),t=Number(personal?data.task_id:data.ticket_id);
 return Number.isSafeInteger(o)&&o>0&&Number.isSafeInteger(t)&&t>0?`/?organization=${o}&${personal?'task':'ticket'}=${t}#${personal?'tasks':'tickets'}`:null;
}
function safeURL(raw){
 if(typeof raw!=='string'||!raw.startsWith('/?organization='))return false;
 try{const u=new URL(raw,self.location.origin);return u.origin===self.location.origin&&/^[1-9][0-9]*$/.test(u.searchParams.get('organization')||'')&&[...u.searchParams].every(([key,value])=>['organization','ticket','task'].includes(key)&&/^[1-9][0-9]*$/.test(value))&&/^#(?:tickets|tasks|notifications|parts|chat|commissioning-chat|commissioning\/project\/[1-9][0-9]*|vacations\/request\/[1-9][0-9]*|duty)$/.test(u.hash);}catch{return false;}
}
function cursor(key,value){return new Promise(resolve=>{
 const fallback=()=>{if(value!==undefined)memoryCursors.set(key,Math.max(memoryCursors.get(key)||0,value));resolve(memoryCursors.get(key)||0);};
 let open;try{open=indexedDB.open('liftcontrol-push-cursors',1);}catch{fallback();return;}
 open.onupgradeneeded=()=>open.result.createObjectStore('events');open.onerror=fallback;
 open.onsuccess=()=>{const db=open.result;let tx;try{tx=db.transaction('events',value===undefined?'readonly':'readwrite');const store=tx.objectStore('events'),get=store.get(key);let result=0;get.onsuccess=()=>{result=Math.max(get.result||0,memoryCursors.get(key)||0);if(value!==undefined){result=Math.max(result,value);store.put(result,key);}};tx.oncomplete=()=>{db.close();memoryCursors.set(key,result);resolve(result);};tx.onerror=()=>{db.close();fallback();};tx.onabort=()=>{db.close();fallback();};}catch{db.close();fallback();}};
 });}
async function privateFetch(url){const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),4000);try{return await fetch(url,{credentials:'same-origin',cache:'no-store',signal:abort.signal});}finally{clearTimeout(timer);}}
async function receipt(data){if(typeof data.receipt_token!=='string')return;const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),4000);try{await fetch('/api/push/received/',{method:'POST',credentials:'omit',cache:'no-store',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({token:data.receipt_token})});}catch{}finally{clearTimeout(timer);}}
async function foreground(company){
 let windows=[];try{windows=await clients.matchAll({type:'window'});}catch{return false;}
 const states=await Promise.all(windows.map(client=>new Promise(resolve=>{
  let channel;try{channel=new MessageChannel();}catch{resolve(false);return;}
  const timer=setTimeout(()=>{channel.port1.close();resolve(false);},300);channel.port1.onmessage=e=>{clearTimeout(timer);channel.port1.close();resolve(e.data?.active===true);};
  try{client.postMessage({type:'liftcontrol-sound-state',organization:company},[channel.port2]);}catch{clearTimeout(timer);channel.port1.close();resolve(false);}
 })));return states.some(Boolean);
}
function display(tag,id,data,title,body,url,critical){
 const previous=displayJobs.get(tag)||Promise.resolve();
 const job=previous.catch(()=>{}).then(async()=>{
  if(await cursor(tag)>=id){await receipt(data);return;}
  const active=await foreground(Number(data.organization_id));
  await self.registration.showNotification(title.slice(0,120),{body:body.slice(0,1000),icon:'/pwa-icon-192.png',tag,silent:active,renotify:critical,requireInteraction:critical,...(active?{}:{vibrate:critical?[600,120,600,120,600]:[250,100,250]}),data:{url,event_id:id}});
  // Commit only AFTER successful display. Storage failures cannot drop a push.
  await cursor(tag,id);await receipt(data);
 });displayJobs.set(tag,job);job.finally(()=>{if(displayJobs.get(tag)===job)displayJobs.delete(tag);}).catch(()=>{});return job;
}
async function handlePush(data){
 if(!data)return;
 const company=Number(data.organization_id),id=Number(data.event_id);
 if(!Number.isSafeInteger(company)||company<1||!Number.isSafeInteger(id)||id<1)return;
 if(data.target==='planning'||data.target==='inbox'){
  const inbox=Number(data.inbox_id);if(!Number.isSafeInteger(inbox)||inbox<1)return;
  let title='Лифт Контроль',body='Новое уведомление. Откройте приложение для просмотра.',url=`/?organization=${company}#notifications`;
  try{const response=await privateFetch(`/api/${data.target==='planning'?'planning/notifications':'push/inbox'}/${inbox}/?organization=${company}`);
   if(response.status===404)return;
   // Expired browser sessions can also return 403. Keep the notification
   // generic on 401/403: never disclose the encrypted business body here.
   if(response.ok){const item=await response.json();if(item.read||item.id!==inbox||!safeURL(item.url)||Number(new URL(item.url,self.location.origin).searchParams.get('organization'))!==company)return;title=String(item.title||title);body=String(item.body||body);url=item.url;}
  }catch{}
  await display(`org-${company}-${data.target}-${inbox}`,id,data,title,body,url,false);return;
 }
 const url=ticketURL(data);if(!url)return;
 const personal=data.target==='task',objectId=Number(personal?data.task_id:data.ticket_id),tag=`org-${company}-${personal?'task':'ticket'}-${objectId}`;
 let title='Лифт Контроль',body='Новое уведомление. Откройте приложение для просмотра.',critical=!personal&&data.priority==='ENTRAPMENT'&&['created','reassigned','escalated'].includes(data.kind);
 try{const result=await privateFetch(`/api/${personal?'tasks':'tickets'}/${objectId}/?organization=${company}`);
  if(result.status===404)return;
  if(result.ok){const current=await result.json();critical=!personal&&current.priority==='ENTRAPMENT'&&['created','reassigned','escalated'].includes(data.kind);if(current.status!==data.status){for(const n of await self.registration.getNotifications({tag}))n.close();return;}title=typeof data.title==='string'?data.title:title;body=typeof data.body==='string'?data.body:body;}
 }catch{}
 await display(tag,id,data,title,body,url,critical);
}
self.addEventListener('push',event=>event.waitUntil((async()=>{let data;try{data=event.data?.json();}catch{return;}await handlePush(data);})()));
self.addEventListener('notificationclick',event=>{
 event.notification.close();const raw=event.notification.data?.url,url=safeURL(raw)?raw:'/#notifications';
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(windows=>{for(const tab of windows)if(new URL(tab.url).origin===self.location.origin)return tab.navigate(url).then(next=>(next||tab).focus());return clients.openWindow(url);}));
});
self.addEventListener('pushsubscriptionchange',event=>event.waitUntil((async()=>{
 // Renew while the app is closed when the browser still has a valid session.
 // Account binding and CSRF are checked just as in a visible app; no anonymous
 // subscription transfer and no credentials are cached in the worker.
 try{
  const response=await privateFetch('/api/push/public-key/');if(!response.ok)return;const config=await response.json();if(!config.enabled||!config.public_key)return;
  const raw=atob((config.public_key+'='.repeat((4-config.public_key.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/')),key=Uint8Array.from(raw,c=>c.charCodeAt(0));
  let sub=event.newSubscription||await self.registration.pushManager.getSubscription();
  if(sub?.options?.applicationServerKey&&String(new Uint8Array(sub.options.applicationServerKey))!==String(key)){await sub.unsubscribe();sub=null;}
  if(!sub)sub=await self.registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
  const current=await privateFetch('/api/me/');if(!current.ok)return;const user=await current.json();if(!user.id||!user.csrf||!user.organization_id)return;
  await fetch('/api/push/subscription/',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRFToken':user.csrf,'X-Organization-ID':String(user.organization_id)},body:JSON.stringify({...sub.toJSON(),expected_user:user.id})});
 }catch{}
})()));

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
