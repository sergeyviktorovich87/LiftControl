import React,{useEffect,useState} from 'react';
import {api,record} from './api';
import {decodeVapidKey,syncPush,preferPush} from './pushSubscription';
export default function PushControls({user}){
 const [config,setConfig]=useState(null),[enabled,setEnabled]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const eligible=true;
 const [probe,setProbe]=useState(null),[health,setHealth]=useState(null);
 const available=window.isSecureContext&&'serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;
 const denied=available&&Notification.permission==='denied';
 useEffect(()=>{
   if(!eligible)return;
   api('push/public-key/').then(async next=>{
     setConfig(next);
     if(!available)return;
     const reg=await navigator.serviceWorker.getRegistration('/');
     const sub=await reg?.pushManager.getSubscription();
     // Re-link the existing browser subscription to the current signed-in person.
     if(sub&&next.enabled&&Notification.permission==='granted'){
       setEnabled(await syncPush(user));
     }else setEnabled(false);
   }).catch(e=>{setEnabled(false);setMessage(e.message||'Не удалось проверить push.');});
 },[user.id,user.organization_id,eligible]);

 const readyWorker=async()=>{
   const permission=await Notification.requestPermission();
   record('notification','permission',permission);
   if(permission!=='granted')throw new Error('Разрешите уведомления для этого сайта в настройках браузера и телефона.');
   await navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'});
   return navigator.serviceWorker.ready;
 };
 const run=async fn=>{if(busy)return;setBusy(true);setMessage('');try{await fn();}catch(e){record('notification','setup',e.name||'error');setMessage(e.message||'Не удалось подключить уведомления.');}finally{setBusy(false);}};
 const enable=()=>run(async()=>{
   const ready=await readyWorker();let sub=await ready.pushManager.getSubscription();
   if(!sub)sub=await ready.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decodeVapidKey(config.public_key)});
   await api('push/subscription/',{method:'POST',body:{...sub.toJSON(),expected_user:user.id}});preferPush(user,true);setEnabled(true);
   setMessage('Системные уведомления подключены. Они приходят по всем вашим организациям, к которым у вас есть доступ.');
 });
 const disable=()=>run(async()=>{
   const reg=await navigator.serviceWorker.getRegistration('/');const sub=await reg?.pushManager.getSubscription();
   preferPush(user,false);
   if(sub){try{await api('push/subscription/',{method:'DELETE',body:{endpoint:sub.endpoint}});}finally{await sub.unsubscribe();}}
   preferPush(user,false);setEnabled(false);setMessage('Уведомления отключены на этом устройстве.');
 });
 const test=()=>run(async()=>{
   const ready=await readyWorker();
   await ready.showNotification('Лифт Контроль — проверка',{
     body:'Проверка системного уведомления и настроек звука телефона.',
     tag:'liftcontrol-test',silent:false,renotify:true,vibrate:[250,100,250],data:{url:'/#tickets'},
   });
   setMessage('Отправлено системное уведомление. Если звука нет, проверьте звук уведомлений браузера в Android и режим «Не беспокоить». Эта кнопка проверяет телефон. Для проверки всего пути используйте «Проверить доставку с сервера».');
 });
 useEffect(()=>{api('push/status/').then(setHealth).catch(()=>{});},[user.id,user.organization_id]);
 useEffect(()=>{if(!probe)return;const abort=new AbortController();let attempts=0;const timer=setInterval(async()=>{if(++attempts>15){clearInterval(timer);setMessage('За 45 секунд подтверждение показа не получено. Проверьте состояние очереди и разрешения телефона.');return;}try{const result=await api('push/test/'+probe+'/',{signal:abort.signal});if(result.states?.includes('DISPLAYED')){clearInterval(timer);setMessage('Браузер подтвердил показ уведомления, отправленного сервером.');setProbe(null);setHealth(await api('push/status/'));}else if(result.states?.some(s=>['FAILED','DISABLED'].includes(s))){clearInterval(timer);setMessage('Серверная проверка: '+result.states.join(', ')+'. Требуется проверка очереди и настроек.');}}catch{}},3000);return()=>{abort.abort();clearInterval(timer);};},[probe]);
 const serverTest=()=>run(async()=>{await readyWorker();const active=await syncPush(user,{force:true});if(!active)throw Error('Не удалось зарегистрировать это устройство. Включите уведомления и повторите.');setEnabled(true);const registration=await navigator.serviceWorker.getRegistration('/');const subscription=await registration.pushManager.getSubscription();const result=await api('push/test/',{method:'POST',body:{endpoint:subscription.endpoint}});setProbe(result.id);setMessage('Проверка поставлена в серверную очередь. Ожидаю подтверждение показа на устройстве.');});
 return <div className="setting-row"><div><h2>Включение уведомлений</h2><p>Новая заявка, принятие и завершение — в уведомлениях телефона, включая фон приложения.</p>
 <p>{!eligible?'Фоновые push по заявкам доступны сотрудникам эксплуатации. Наладчикам доступны центр уведомлений и звуки открытого приложения.':!available?'Браузер не поддерживает push по этому адресу. Откройте поддерживаемый безопасный адрес.':denied?'Разрешение заблокировано. Разрешите уведомления для сайта в настройках браузера.':!config?.enabled?'Доставка с сервера пока не подключена. Сообщения внутри приложения продолжают работать.':enabled?'Подключено на этом устройстве.':'Для этого телефона уведомления ещё не включены.'}</p>
 {health&&<p className="muted">За сутки на ваших устройствах: без подтверждения показа {health.last_24h?.SENT||0}, показ подтверждён {health.last_24h?.DISPLAYED||0}, ошибок {health.last_24h?.FAILED||0}. Принятие провайдером ещё не подтверждает показ.</p>}
 <small>Звук и разрешения уведомлений настраиваются на телефоне. Для доставки нужно подключение к интернету.</small>
 {message&&<p role="status">{message}</p>}<div className="actions"><button type="button" disabled={busy||!eligible||!available||(!enabled&&!config?.enabled)} onClick={enabled?disable:enable}>{busy?'Обработка…':enabled?'Отключить уведомления':'Включить уведомления'}</button><button type="button" disabled={busy||!available||denied||!config?.enabled} onClick={serverTest}>Проверить доставку с сервера</button><button type="button" disabled={busy||!eligible||!available||denied} onClick={test}>Проверить системное уведомление</button></div></div></div>;
}
