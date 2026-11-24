import React,{useEffect,useState} from 'react';
import {api,PREVIEW} from './api';
const labels={idle:'Проверка ещё не выполнена',checking:'Проверяем GitHub…',available:'Доступна новая версия',current:'Установлена последняя версия',installing:'Устанавливаем обновление…',installed:'Обновление установлено',deferred:'Отложено: есть заявка о застревании',migration_approval:'Изменение базы: требуется подтверждение через терминал',blocked:'Предыдущая установка не удалась. Проверьте журнал сервера.',failed:'Ошибка обновления. Проверьте журнал сервера.',changed:'Релиз изменился. Проверьте обновления заново.'};
export default function UpdateControls({user}){
 const [value,setValue]=useState(null),[legacy,setLegacy]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[sent,setSent]=useState(0);
 const owner=user.is_superuser&&!PREVIEW;
 const refresh=async()=>{try{const data=await api(owner?'updates/system/':'updates/');if(owner){setValue(data);setSent(id=>id&&data.host?.request_id>=id?0:id);}else setLegacy(data);setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{refresh();if(!owner)return;const timer=setInterval(()=>{if(!document.hidden)refresh();},5000);return()=>clearInterval(timer);},[owner,user.id]);
 const host=value?.host;
 const running=busy||!!value?.pending||!!sent||['checking','installing'].includes(host?.state);
 const ready=host?.reachable&&!running;
 const send=async(action,target='')=>{
  if(action==='install'&&!window.confirm('Установить версию '+target+'? Панель ненадолго будет недоступна. Сохраните рабочие данные.'))return;
  setBusy(true);setError('');
  try{const response=await api('updates/system/',{method:'POST',body:{action,target}});setSent(response.request_id);await refresh();}
  catch(e){setError(e.message);}finally{setBusy(false);}
 };
 return <div className="setting-row"><div><h2>Обновление системы</h2>
 <p>Установленная версия: <b>{value?.installed||legacy?.installed?.panel||'—'}</b></p>
 <p>Основной клиент: PWA. Новая версия загружается при повторном открытии панели.</p>
 {owner&&<><p>Автообновление ночью: {host?host.auto_enabled?'Включено':'Выключено':'Не определено'}</p>
 <p>Доступная версия: <b>{host?.target||'—'}</b></p>
 <p role="status">{!host?.reachable?'Служба VPS недоступна или ещё не настроена.':sent||value?.pending?'Запрос передан службе VPS.':labels[host.state]}</p>
 <small>Подписанный релиз, резервная копия и проверка после установки. Миграции требуют отдельного разрешения.</small>
 <div className="actions"><button disabled={!ready} onClick={()=>send('check')}>Проверить обновления</button><button className="primary" disabled={!ready||host?.state!=='available'} onClick={()=>send('install',host.target)}>Установить обновление</button></div></>}
 {!owner&&<small>Обновлением всей системы управляет владелец сервера.</small>}
 {error&&<p className="error" role="alert">{error}</p>}
 </div></div>;
}
