import React,{useEffect,useState} from 'react';
import {PREVIEW} from './api.js';
import {pwaState,subscribePwa,installPwa} from './pwa.js';
export default function PwaControls(){
 const [state,setState]=useState(pwaState);
 useEffect(()=>{const refresh=()=>setState(pwaState());const unsubscribe=subscribePwa(refresh);refresh();return unsubscribe;},[]);
 if(PREVIEW)return null;
 return <div className="setting-row"><div><h2>Приложение Лифт Контроль</h2>
 <p>{state.standalone?'Панель открыта как установленное приложение.':state.workerStatus==='unsupported'?'Для установки откройте доверенный HTTPS-адрес в поддерживаемом браузере.':state.workerStatus==='error'?'Не удалось подключить PWA. Обновите страницу и проверьте диагностические логи.':'Установите панель на рабочий стол или главный экран. Данные остаются на сервере.'}</p>
 {!state.standalone&&state.workerStatus!=='unsupported'&&!state.canInstall&&<small>iPhone: Safari → Поделиться → На экран «Домой». Android и компьютер: меню браузера → Установить приложение, если доступно.</small>}
 <p>{navigator.onLine?'Сеть доступна':'Нет сети. Для операций с данными нужно подключение.'}</p>
 {state.canInstall&&!state.standalone&&<button className="primary" type="button" onClick={installPwa}>Установить приложение</button>}</div></div>;
}
