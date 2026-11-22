import React, {useEffect, useState} from 'react';
import {api} from './api';
import {Dialog, Field} from './components';

const labels = {cycle:'Очередь сотрудников', temp:'Временная очередь', leave:'Отпуск', replace:'Подмена на период'};
const empty = {cycles:[], periods:[]};

export default function DutyRules({technicians, today, onClose, onSaved}) {
  const [rules, setRules] = useState(null);
  const [entry, setEntry] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const names = ids => ids.map(id => technicians.find(t => t.id === id)?.full_name || 'Архивный сотрудник').join(' → ');
  const tomorrow = new Date(+new Date(today + 'T12:00:00Z') + 86400000).toISOString().slice(0,10);
  useEffect(() => {
    let active = true;
    api('duty/roster-settings/').then(data => { if (active) setRules(data); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  async function save(key, value, index) {
    setBusy(true);
    setError('');
    const list = [...rules[key]];
    if (index == null) list.push(value);
    else if (value == null) list.splice(index, 1);
    else list[index] = value;
    try {
      const response = await api('duty/roster-settings/', {method:'PUT',body:{previous:rules,config:{...rules,[key]:list}}});
      setRules(response);
      setEntry(null);
      onSaved();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  function begin(type, value, index) {
    setError('');
    setEntry({type, index, value: value || {from:tomorrow,to:tomorrow,people:technicians.map(t => t.id),worker:technicians[0]?.id,target:technicians[1]?.id}});
  }
  return <Dialog title={entry ? labels[entry.type] : 'Настройки графика'} onClose={() => { if (!busy) onClose(); }}>
    {error && <p className="error" role="alert">{error}</p>}
    {!rules && !error && <p>Загрузка…</p>}
    {entry && <RuleEditor key={entry.type} entry={entry} technicians={technicians} names={names} minDate={tomorrow} busy={busy}
      onCancel={() => {setError('');setEntry(null);}} onSave={rule => save(entry.type === 'cycle' ? 'cycles' : 'periods',rule,entry.index)}/>}
    {rules && !entry && <>
      <p>Очередь заполняет будущие смены. Изменения применяются при публикации месяца.</p>
      <div className="actions">{Object.keys(labels).map(type => <button key={type} onClick={() => begin(type)}>{labels[type]}</button>)}</div>
      <div className="roster-settings-list">
        {Object.keys(empty).map(key => rules[key].map((rule,index) => {
          const type = key === 'cycles' ? 'cycle' : rule.type;
          return <div className="roster-settings-row" key={key + index}><div>
            <strong>{labels[type]}</strong><div>{rule.from}{rule.to && ' – ' + rule.to}</div>
            <small>{names(rule.people || [rule.worker,rule.target].filter(Boolean))}</small></div>
            {rule.from > today && <div className="actions"><button disabled={busy} onClick={() => begin(type,rule,index)}>Изменить</button>
              <button disabled={busy} onClick={() => save(key,null,index)}>Убрать из плана</button></div>}
          </div>;
        }))}
      </div>
    </>}
  </Dialog>;
}

function RuleEditor({entry, technicians, names, minDate, busy, onCancel, onSave}) {
  const [rule, setRule] = useState(entry.value);
  const type = entry.type;
  const rotation = type === 'cycle' || type === 'temp';
  const change = (field,value) => setRule(current => ({...current,[field]:value}));
  function submit(event) {
    event.preventDefault();
    const dates = type === 'cycle' ? {from:rule.from} : {type,from:rule.from,to:rule.to};
    onSave({...dates,...(rotation ? {people:rule.people} : {worker:rule.worker,...(type === 'replace' && {target:rule.target})})});
  }
  return <form onSubmit={submit}>
    <div className="form-grid">
      <Field label="С даты"><input type="date" required min={minDate} value={rule.from} onChange={e => change('from',e.target.value)}/></Field>
      {type !== 'cycle' && <Field label="По дату включительно"><input type="date" required min={rule.from} value={rule.to} onChange={e => change('to',e.target.value)}/></Field>}
    </div>
    {rotation ? <>
      <div className="rotation">{rule.people.map((id,index) => <div key={id}>
        <span>{index + 1}. {names([id])}</span>
        <button type="button" disabled={index === 0} aria-label="Раньше" onClick={() => {
          const order = [...rule.people];
          [order[index - 1],order[index]] = [order[index],order[index - 1]];
          change('people',order);
        }}>↑</button>
        <button type="button" aria-label="Убрать из очереди" onClick={() => change('people',rule.people.filter(item => item !== id))}>×</button>
      </div>)}</div>
      <Field label="Добавить механика"><select value="" onChange={e => change('people',[...rule.people,Number(e.target.value)])}>
        <option value="" disabled>Выбрать сотрудника</option>{technicians.filter(t => !rule.people.includes(t.id)).map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}
      </select></Field>
    </> : <div className="form-grid">
      <Field label="Сотрудник"><select required value={rule.worker ?? ''} onChange={e => change('worker',Number(e.target.value))}>
        <option value="" disabled>Выбрать</option>{technicians.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}
      </select></Field>
      {type === 'replace' && <Field label="Кто подменяет"><select required value={rule.target === rule.worker ? '' : rule.target ?? ''} onChange={e => change('target',Number(e.target.value))}>
        <option value="" disabled>Выбрать</option>{technicians.filter(t => t.id !== rule.worker).map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}
      </select></Field>}
    </div>}
    <div className="form-actions"><button type="button" disabled={busy} onClick={onCancel}>Назад</button><button className="primary" disabled={busy || (rotation && !rule.people.length)}>Сохранить</button></div>
  </form>;
}
