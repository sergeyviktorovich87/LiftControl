import React,{useState} from 'react';
import {Field} from './components';
import {tones,soundSettings,saveSounds,playTone} from './notificationSounds';
export default function SoundControls({user}){
 const [values,setValues]=useState(()=>soundSettings(user)),[message,setMessage]=useState('');
 const change=async(key,value)=>{
  const next={...values,[key]:value};setMessage('');
  try{saveSounds(user,next);setValues(next);if(key==='enabled'&&value)await playTone(next.ordinary,next.volume);setMessage('Сохранено на этом устройстве.');}catch(e){setMessage(e.message);}
 };
 const preview=async tone=>{try{await playTone(tone,values.volume);setMessage(tone==='off'?'Для этого типа выбран режим без звука.':'Сигнал воспроизведён.');}catch(e){setMessage(e.message);}};
 return <div className="setting-row"><div><h2>Звуки в открытом приложении</h2><p>Отдельные сигналы для обычных уведомлений и застреваний. Применяются на этом устройстве; тихие часы учитываются.</p>
 <label className="notification-choice"><input type="checkbox" aria-label="Звук уведомлений в приложении" checked={values.enabled} onChange={e=>change('enabled',e.target.checked)}/><span><b>Звук уведомлений в приложении</b><small>После открытия нажмите на экран, чтобы браузер разрешил звук.</small></span></label>
 <div className="sound-options">{[['ordinary','Обычные уведомления'],['important','Застревания']].map(([key,label])=><div className="sound-option" key={key}><Field label={label}><select value={values[key]} onChange={e=>change(key,e.target.value)}>{Object.entries(tones).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></Field><button type="button" aria-label={'Прослушать: '+label} onClick={()=>preview(values[key])}>Прослушать</button></div>)}</div>
 <Field label={'Громкость · '+values.volume+'%'}><input type="range" min="0" max="100" step="10" value={values.volume} onChange={e=>change('volume',Number(e.target.value))}/></Field>
 {message&&<p role="status">{message}</p>}
 <p>Когда PWA свёрнуто или закрыто, звуком системных push управляет телефон. На Android: Настройки телефона → Приложения → Лифт Контроль или браузер → Уведомления → Звук. Названия пунктов могут отличаться.</p>
 </div></div>;
}
