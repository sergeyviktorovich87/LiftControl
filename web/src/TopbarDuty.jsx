import React from 'react';
export default function TopbarDuty({user,onOpen}){
 const shift=user.duty_shift,accepted=!!shift?.acknowledged_at;
 const zone=user.timezone||'Asia/Chita';
 const time=value=>new Date(value).toLocaleTimeString('ru-RU',{timeZone:zone,hour:'2-digit',minute:'2-digit'});
 const full=value=>new Date(value).toLocaleString('ru-RU',{timeZone:zone,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
 const label=shift?'Дежурный: '+shift.technician_name:'Дежурный не назначен';
 return <button type="button" className="topbar-duty" onClick={onOpen} aria-label={label} aria-describedby={shift?'current-duty-ack':undefined} title={shift?`${label}. ${accepted?'Смена принята '+full(shift.acknowledged_at):'Смена не принята'}. До ${full(shift.end)}`:label}>
  <span className={'duty-indicator '+(shift?(accepted?'accepted':'pending'):'')} aria-hidden="true"/>
  <span className="topbar-duty-text"><small>{user.on_duty?'Вы дежурите':'Дежурный механик'}</small><b>{shift?.technician_name||'Не назначен'}</b>
   {shift&&<><small id="current-duty-ack" className={'duty-acceptance '+(accepted?'accepted':'pending')}>{accepted?<time dateTime={shift.acknowledged_at}>Принята в {time(shift.acknowledged_at)}</time>:'Смена не принята'}</small><small className="topbar-duty-end">До {full(shift.end)}</small></>}
  </span>
 </button>;
}
