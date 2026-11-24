import React, {useEffect,useState} from 'react';
import {api,selectOrganization} from './api';
import {Field,Dialog} from './components';
const labels={ADMIN:'Администратор',DIRECTOR:'Директор',DISPATCHER:'Диспетчер',MECHANIC:'Механик',ADJUSTER:'Внешний наладчик'};
export async function switchOrganization(id){
  await api('organizations/switch/',{method:'POST',body:{organization:Number(id)}});
  selectOrganization(Number(id));
  location.href='/?organization='+Number(id)+'#home';
}
export default function OrganizationControls({user,data={technicians:[]},onChanged=async()=>{},section='all'}){
  const [name,setName]=useState(''),[code,setCode]=useState(''),[role,setRole]=useState('MECHANIC'),[tech,setTech]=useState('');
  const [staffName,setStaffName]=useState(''),[staffLogin,setStaffLogin]=useState(''),[staffPhone,setStaffPhone]=useState(''),[staffRole,setStaffRole]=useState('MECHANIC'),[existingStaff,setExistingStaff]=useState(''),[staffMode,setStaffMode]=useState('account');
  const [alsoAdjuster,setAlsoAdjuster]=useState(false);
  const [setupLink,setSetupLink]=useState(null);
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[invite,setInvite]=useState(null),[members,setMembers]=useState([]),[invites,setInvites]=useState([]),[available,setAvailable]=useState([]);
  const [query,setQuery]=useState(''),[status,setStatus]=useState('all'),[page,setPage]=useState(0),[editing,setEditing]=useState(null),[createOpen,setCreateOpen]=useState(false);
  useEffect(()=>{const open=()=>{if(location.hash==='#settings/team/add')setCreateOpen(true);};open();window.addEventListener('hashchange',open);return()=>window.removeEventListener('hashchange',open);},[]);
  const filtered=members.filter(m=>(status==='all'||(status==='active'?m.active:!m.active))&&[m.name,m.username,m.phone,labels[m.role],m.can_commissioning?'наладчик':''].filter(Boolean).join(' ').toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')));
  const lastPage=Math.max(0,Math.ceil(filtered.length/20)-1),currentPage=Math.min(page,lastPage);
  const selected=members.find(m=>m.id===editing);
  const refresh=async()=>{
    if(user?.can_manage_access&&section!=='organizations'){const [rows,codes]=await Promise.all([api('organizations/members/'),api('organizations/invites/')]);setMembers(rows);setInvites(codes);}
  };
  useEffect(()=>{setSetupLink(null);(section==='team'?refresh():api('organizations/').then(result=>{setAvailable(result.organizations);return refresh();})).catch(e=>setError(e.message));},[user?.organization_id,section]);
  const run=async fn=>{setBusy(true);setError('');setMessage('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}};
  const join=e=>{e.preventDefault();run(async()=>{const result=await api('organizations/join/',{method:'POST',body:{code:code.trim()}});await switchOrganization(result.organization_id);});};
  return <>
    {section!=='team'&&<div className="setting-row"><div><h2>Выбор организации</h2><p>Одна учётная запись для основной работы и совместительства. Права, заявки, чат и график отдельные в каждой компании.</p>
      <div className="settings-organization-list">{(user?.organizations||available).map(o=><button type="button" disabled={busy||o.id===user?.organization_id} aria-pressed={o.id===user?.organization_id} key={o.id} onClick={()=>run(()=>switchOrganization(o.id))}>{o.name} · {labels[o.role]}{o.id===user?.organization_id?' · выбрана':''}</button>)}</div>
      <form className="access-form" onSubmit={join}><Field label="Код приглашения в организацию"><input value={code} required maxLength={43} autoComplete="off" onChange={e=>setCode(e.target.value)}/></Field><button disabled={busy||!code.trim()}>Присоединиться</button></form>
    </div></div>}
    {user?.can_manage_access&&<>
      {section!=='team'&&<div className="setting-row"><div><h2>Добавить организацию</h2><p>Вы станете её администратором. Новая компания создаётся с пустым списком объектов.</p><form className="access-form" onSubmit={e=>{e.preventDefault();run(async()=>{const next=await api('organizations/',{method:'POST',body:{name,timezone:user.timezone}});await switchOrganization(next.id);});}}><Field label="Название организации"><input required minLength={2} maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></Field><button disabled={busy}>Создать</button></form></div></div>}
      {section!=='organizations'&&<>
      <details className="setting-row staff-disclosure" id="employee-create" open={createOpen} onToggle={e=>setCreateOpen(e.currentTarget.open)}><summary><h2>Добавить сотрудника</h2></summary><div><p>Укажите логин и роль. Сотрудник установит пароль по ссылке, которую вы ему отправите. Для существующего аккаунта используйте приглашение в организацию ниже.</p>
      <form className="access-form" onSubmit={e=>{e.preventDefault();run(async()=>{
        if(staffMode==='account'){
          const result=await api('organizations/members/create/',{method:'POST',body:{username:staffLogin.trim(),full_name:staffName.trim(),phone:staffPhone.trim(),role:staffRole,technician:existingStaff?Number(existingStaff):null,...(staffRole==='MECHANIC'?{can_commissioning:alsoAdjuster}:{})}});
          setSetupLink({...result,memberId:null});
        }else{
          await api('technicians/',{method:'POST',body:{full_name:staffName.trim(),phone:staffPhone.trim(),role:'MECHANIC',active:true}});
          setMessage('Карточка создана без доступа. Для входа создайте аккаунт или приглашение.');
        }
        setStaffLogin('');setStaffName('');setStaffPhone('');setExistingStaff('');setAlsoAdjuster(false);
        await refresh();await onChanged();
      });}}>
        <Field label="Тип записи"><select value={staffMode} onChange={e=>{setStaffMode(e.target.value);setExistingStaff('');}}><option value="account">Сотрудник с учётной записью</option><option value="card">Только карточка (без входа)</option></select></Field>
        {staffMode==='account'&&<Field label="Карточка сотрудника"><select value={existingStaff} onChange={e=>{const id=e.target.value;setExistingStaff(id);const item=data.technicians.find(t=>String(t.id)===id);if(item)setStaffName(item.full_name);}}><option value="">Создать новую карточку</option>{data.technicians.filter(t=>t.active&&!members.some(m=>m.technician===t.id)).map(t=><option key={t.id} value={t.id}>{t.full_name} · без логина</option>)}</select></Field>}
        <Field label="ФИО сотрудника"><input required minLength={2} maxLength={200} value={staffName} onChange={e=>setStaffName(e.target.value)}/></Field>
        <Field label="Телефон"><input type="tel" maxLength={50} value={staffPhone} onChange={e=>setStaffPhone(e.target.value)}/></Field>
        {staffMode==='account'&&<>
          <Field label="Логин"><input required minLength={3} maxLength={150} autoComplete="off" value={staffLogin} onChange={e=>setStaffLogin(e.target.value)}/></Field>
          <Field label="Роль в организации"><select value={staffRole} onChange={e=>setStaffRole(e.target.value)}>{Object.entries(labels).filter(([id])=>id!=='ADMIN'||user.role==='ADMIN').map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></Field>
          {staffRole==='MECHANIC'&&<label><input type="checkbox" checked={alsoAdjuster} onChange={e=>setAlsoAdjuster(e.target.checked)}/> Также наладчик</label>}
        </>}
        <button disabled={busy}>{staffMode==='account'?'Создать сотрудника и ссылку':'Создать карточку'}</button>
      </form>
      {setupLink?.memberId===null&&<SetupLink key={setupLink.setup_url} link={setupLink}/>}
      </div></details>
      <details className="setting-row staff-disclosure"><summary><h2>Пригласить сотрудника</h2></summary><div><p>Выберите роль и карточку механика. Одноразовый код действует 7 дней. Сотрудник вводит его после входа в свою учётную запись.</p><form className="access-form" onSubmit={e=>{e.preventDefault();run(async()=>{setInvite(await api('organizations/invites/',{method:'POST',body:{role,technician:tech?Number(tech):null}}));await refresh();});}}><Field label="Роль в организации"><select value={role} onChange={e=>setRole(e.target.value)}>{Object.entries(labels).filter(([id])=>id!=='ADMIN'||user.role==='ADMIN').map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></Field><Field label="Карточка сотрудника"><select value={tech} required={role==='MECHANIC'} onChange={e=>setTech(e.target.value)}><option value="">Без карточки</option>{data.technicians.filter(t=>t.active&&!members.some(m=>m.technician===t.id)).map(t=><option key={t.id} value={t.id}>{t.full_name}</option>)}</select></Field><button disabled={busy}>Создать код</button></form>
      {invite&&<div className="notice"><b>Код: </b><code>{invite.code}</code><button type="button" onClick={()=>run(async()=>{await navigator.clipboard.writeText(invite.code);setMessage('Код скопирован');})}>Копировать код</button><small>Показывается один раз. Передайте сотруднику лично.</small></div>}
      {invites.filter(i=>!i.used_at&&!i.revoked_at&&new Date(i.expires_at)>new Date()).map(i=><div className="list-row" key={i.id}><span>Приглашение #{i.id} · {labels[i.role]}</span><button disabled={busy} onClick={()=>run(async()=>{await api(`organizations/invites/${i.id}/revoke/`,{method:'POST'});await refresh();setInvite(null);})}>Отозвать</button></div>)}
      </div></details>
      <div className="setting-row"><div><h2>Доступ сотрудников <small className="muted">{members.length}</small></h2>
        <div className="staff-filters">
          <Field label="Поиск сотрудника"><input type="search" placeholder="Имя или роль" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/></Field>
          <Field label="Доступ"><select value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="all">Все сотрудники</option><option value="active">С доступом</option><option value="inactive">Без доступа</option></select></Field>
        </div>
        <p role="status">Найдено: {filtered.length}. Показано {filtered.length?currentPage*20+1:0}–{Math.min(filtered.length,(currentPage+1)*20)}.</p>
        <div className="staff-list">{filtered.slice(currentPage*20,(currentPage+1)*20).map(m=><div className="staff-row" key={m.id}>
          <div><b>{m.name}</b><small>{m.role==='MECHANIC'&&m.can_commissioning?'Механик и наладчик':labels[m.role]}{m.user===user.id?' · Вы':''}{!m.active?' · Доступ отключён':m.password_setup_pending?' · Ожидает пароль':''}</small></div>
          <button type="button" aria-label={'Изменить доступ: '+m.name} onClick={()=>setEditing(m.id)}>Изменить</button>
        </div>)}</div>
        {!filtered.length&&<p>Сотрудники не найдены. Измените поиск или фильтр.</p>}
        {lastPage>0&&<nav className="staff-pagination" aria-label="Страницы сотрудников"><button disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Назад</button><span>{currentPage+1} / {lastPage+1}</span><button disabled={currentPage===lastPage} onClick={()=>setPage(currentPage+1)}>Далее</button></nav>}
      </div></div>
      {selected&&<Dialog title="Доступ сотрудника" onClose={()=>{if(!busy)setEditing(null);}}>
        <Member key={selected.id} member={selected} user={user} technicians={data.technicians} busy={busy}
          save={body=>run(async()=>{await api(`organizations/members/${selected.id}/`,{method:'PATCH',body});await refresh();setMessage('Доступ сотрудника сохранён.');setEditing(null);})}
          reissue={()=>run(async()=>{const result=await api(`organizations/members/${selected.id}/password-setup/`,{method:'POST'});setSetupLink({...result,memberId:selected.id});})}/>
        {setupLink?.memberId===selected.id&&<SetupLink key={setupLink.setup_url} link={setupLink}/>}
        {error&&<p className="error" role="alert">{error}</p>}
      </Dialog>}
      </>}
    </>}
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </>;
}
function SetupLink({link}){
 const [copyStatus,setCopyStatus]=useState('');
 const copy=async()=>{
   try{await navigator.clipboard.writeText(link.setup_url);setCopyStatus('Ссылка скопирована.');}
   catch{setCopyStatus('Выделите и скопируйте ссылку вручную.');}
 };
 return <div className="notice">
   <p>Ссылка для сотрудника с логином <b>{link.username}</b>. Действует 24 часа.</p>
   <code>{link.setup_url}</code> <button type="button" onClick={copy}>Копировать ссылку</button>
   {copyStatus&&<p role="status">{copyStatus}</p>}
 </div>;
}
function Member({member,user,technicians,busy,save,reissue}){
 const [role,setRole]=useState(member.role),[tech,setTech]=useState(member.technician||''),[commissioning,setCommissioning]=useState(member.can_commissioning===true);
 const savedRoles=member.role==='MECHANIC'&&member.can_commissioning?'Механик и наладчик':labels[member.role];
 return <div className="member-access">
   <b>{member.name}<small className="muted"> · {savedRoles}{member.active?'':' · доступ отключён'}{member.password_setup_pending?' · пароль ещё не установлен':''}</small></b>
   <select aria-label={'Основная роль '+member.name} value={role} onChange={e=>setRole(e.target.value)}>
     {Object.entries(labels).filter(([r])=>r!=='ADMIN'||user.role==='ADMIN'||member.role==='ADMIN').map(([r,l])=><option key={r} value={r}>{l}</option>)}
   </select>
   <select aria-label={'Карточка '+member.name} value={tech} onChange={e=>setTech(e.target.value)}>
     <option value="">Без карточки</option>{technicians.map(t=><option key={t.id} value={t.id}>{t.full_name}</option>)}
   </select>
   <label><input type="checkbox" checked={commissioning} onChange={e=>setCommissioning(e.target.checked)}/> {role==='MECHANIC'?'Роль «Наладчик»':'Доступ к наладке'}</label>
   <button disabled={busy||member.user===user.id} onClick={()=>save({role,technician:role==='ADJUSTER'?null:tech?Number(tech):null,can_commissioning:commissioning})}>Сохранить</button>
   <button disabled={busy||member.user===user.id} onClick={()=>save({active:!member.active})}>{member.active?'Отключить доступ':'Вернуть доступ'}</button>
   {member.password_setup_pending&&member.active&&(member.role!=='ADMIN'||user.role==='ADMIN')&&<button type="button" disabled={busy} onClick={reissue}>Выпустить новую ссылку</button>}
 </div>;
}
