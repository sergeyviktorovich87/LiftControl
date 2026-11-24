const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.SETTINGS_TEST_ORIGIN||'http://127.0.0.1:5173';
const sectionTitles={profile:'Профиль',notifications:'Уведомления',appearance:'Оформление',organizations:'Организации',team:'Сотрудники и доступ',application:'Приложение и обновления',diagnostics:'Диагностика'};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.SETTINGS_CHROME_EXECUTABLE||'/usr/bin/chromium',args:['--no-sandbox']});
 try{
 for(const role of ['ADMIN','MECHANIC','ADJUSTER']){
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU',permissions:['clipboard-read','clipboard-write']});
  if(role==='MECHANIC')await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));
  await context.addInitScript(()=>{
   let subscription=null;const worker={pushManager:{getSubscription:async()=>subscription,subscribe:async()=>subscription={endpoint:'https://fcm.googleapis.com/fcm/send/test',toJSON:()=>({endpoint:'https://fcm.googleapis.com/fcm/send/test',keys:{p256dh:'abcdefghijklm',auth:'abcdefghijklm'}}),unsubscribe:async()=>{subscription=null;return true;}}},showNotification:async()=>{}};
   Object.defineProperty(window,'Notification',{value:{permission:'default',requestPermission:async()=>{window.Notification.permission='granted';return 'granted';}},configurable:true});
   Object.defineProperty(window,'PushManager',{value:function(){},configurable:true});
   Object.defineProperty(navigator,'serviceWorker',{value:{getRegistration:async()=>worker,register:async()=>worker,ready:Promise.resolve(worker),addEventListener:()=>{},removeEventListener:()=>{}},configurable:true});
  });
  const page=await context.newPage(),errors=[],posted=[];
  const longName='Александр Александрович Константинопольский — механик и наладчик';
  const organization='Мегаполис — обслуживание лифтов и инженерного оборудования';
  const admin=role==='ADMIN';
  const organizations=[{id:1,name:organization,role},{id:2,name:'Эверест — монтаж и обслуживание',role:admin?'ADMIN':'MECHANIC'}];
  const profile={id:1,name:'Сергей Александрович',role,organization,organization_id:1,organizations,timezone:'Asia/Chita',csrf:'settings-fixture',can_manage:admin,can_manage_access:admin,is_superuser:admin,can_commissioning:false,commissioning_only:role==='ADJUSTER'};
  let preferences={only_mine:false,quiet_enabled:true,quiet_start:'22:00',quiet_end:'08:00',muted_weekdays:[5,6]};
  let host={state:'current',reachable:true,target:'0.13.22',request_id:0,auto_enabled:true};
  const members=[{id:1,user:1,name:'Сергей Александрович',role:'ADMIN',active:true},{id:2,user:2,name:longName,role:'MECHANIC',active:true,technician:2,can_commissioning:true,password_setup_pending:true}];
  for(let id=3;id<=100;id++)members.push({id,user:id,name:'Сотрудник '+String(id).padStart(3,'0'),role:'MECHANIC',active:id%4!==0});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.replace('/api/','');
   let value=[];
   if(request.method()!=='GET')posted.push({path,body:request.postDataJSON()});
   if(path==='me/')value=profile;
   else if(path==='organizations/')value={csrf:'settings-fixture',organizations};
   else if(path==='organizations/members/')value=members;
   else if(path==='organizations/invites/')value=[{id:9,role:'MECHANIC',expires_at:'2099-01-01T00:00:00Z',used_at:null,revoked_at:null}];
   else if(path==='organizations/members/create/')value={username:'new-worker',setup_url:origin+'/employee-password/?token='+('very-long-test-token-'.repeat(12)),expires_at:'2099-01-01'};
   else if(path==='notification-preferences/'){
    if(request.method()==='PATCH')preferences={...preferences,...request.postDataJSON()};
    value=preferences;
   }else if(path==='updates/system/'){
    if(request.method()==='POST'){host={...host,state:'available',target:'0.13.23',request_id:1};value={request_id:1};}
    else value={installed:'0.13.22',host,pending:null};
   }else if(path==='updates/')value={installed:{panel:'0.13.22'}};
   else if(path==='push/public-key/')value={enabled:true,public_key:btoa('a'.repeat(65))};
   else if(path==='push/subscription/')value={ok:true};
   else if(path==='technicians/')value=members.map(m=>({id:m.id,full_name:m.name,active:m.active,role:'MECHANIC'}));
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin+'/#settings');
  await page.getByRole('heading',{name:'Настройки',exact:true}).waitFor();
  const root=page.locator('.settings-page'),nav=page.getByRole('navigation',{name:'Разделы настроек'});
  const open=async id=>{
   if(!await nav.isVisible())await root.getByRole('button',{name:'Все настройки',exact:true}).click();
   await nav.getByRole('button').filter({hasText:sectionTitles[id]}).click();
   await root.locator(`.settings-section[aria-label="${sectionTitles[id]}"]`).waitFor();
  };
  const layout=async label=>{
   const result=await page.evaluate(()=>{
    const overflow=document.documentElement.scrollWidth>innerWidth+1;
    const outside=[...document.querySelectorAll('.settings-page input,.settings-page select,.settings-page button,.settings-page textarea')].filter(el=>el.getClientRects().length).filter(el=>{const r=el.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(el=>el.getAttribute('aria-label')||el.textContent||el.tagName);
    const overlap=[];
    for(const form of document.querySelectorAll('.settings-page .access-form,.settings-page .member-access,.settings-page .range')){
     const items=[...form.querySelectorAll('input,select,button')].filter(el=>el.getClientRects().length).map(el=>el.getBoundingClientRect());
     for(let a=0;a<items.length;a++)for(let b=a+1;b<items.length;b++){const x=items[a],y=items[b];if(Math.min(x.right,y.right)-Math.max(x.left,y.left)>2&&Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top)>2)overlap.push([a,b]);}
    }
    return {overflow,outside,overlap};
   });
   assert(!result.overflow&&result.outside.length===0&&result.overlap.length===0,label+': '+JSON.stringify(result));
  };
  const ids=Object.keys(sectionTitles).filter(id=>admin||id!=='team');
  for(const [width,height] of [[2560,1440],[1440,1000],[1024,768],[768,1024],[412,915],[360,780],[320,640]]){
   await page.setViewportSize({width,height});
   for(const id of ids){await open(id);await layout(role+' '+width+' '+id);}
  }
  if(admin){
   await page.setViewportSize({width:1440,height:1000});
   await open('team');
   assert.equal(await page.locator('.staff-row:visible').count(),20,'100 employees render only 20 compact rows');
   assert.equal(await page.locator('.member-access:visible').count(),0,'No expanded employee editors by default');
   await page.getByRole('navigation',{name:'Страницы сотрудников'}).getByRole('button',{name:'Далее',exact:true}).click();
   await page.getByLabel('Поиск сотрудника',{exact:true}).fill('Сотрудник 100');
   assert.equal(await page.locator('.staff-row:visible').count(),1);
   await page.getByLabel('Поиск сотрудника',{exact:true}).fill(longName);
   await page.getByRole('button',{name:'Изменить доступ: '+longName,exact:true}).click();
   await page.getByRole('dialog',{name:'Доступ сотрудника'}).waitFor();
   await page.setViewportSize({width:320,height:740});await layout('Employee access dialog 320');
   await page.getByRole('button',{name:'Закрыть',exact:true}).click();
   await page.setViewportSize({width:1440,height:1000});
   await page.getByLabel('Поиск сотрудника',{exact:true}).fill('');
   await page.locator('#employee-create summary').click();
   await page.getByLabel('ФИО сотрудника',{exact:true}).fill('Черновик имени сотрудника');
   await open('notifications');
   await page.getByRole('button',{name:'Включить уведомления',exact:true}).click();
   await page.getByRole('button',{name:'Отключить уведомления',exact:true}).waitFor();
   assert(posted.some(r=>r.path==='push/subscription/'),'Administrator can register Web Push without mechanic role');
   await page.getByRole('button',{name:'Отключить уведомления',exact:true}).click();
   await page.getByRole('button',{name:'Включить уведомления',exact:true}).waitFor();
   await page.getByLabel('Звук уведомлений в приложении',{exact:true}).check();
   await page.getByLabel('Обычные уведомления',{exact:true}).selectOption('double');
   await page.getByRole('button',{name:'Прослушать: Обычные уведомления',exact:true}).click();
   await page.getByText('Сигнал воспроизведён.',{exact:true}).waitFor();
   await page.getByLabel('Начало тихих часов',{exact:true}).fill('21:30');
   await open('team');
   assert.equal(await page.getByLabel('ФИО сотрудника',{exact:true}).inputValue(),'Черновик имени сотрудника','Switching sections must preserve staff draft');
   await open('notifications');
   assert.equal(await page.getByLabel('Начало тихих часов',{exact:true}).inputValue(),'21:30','Switching sections must preserve notification draft');
   await page.getByRole('button',{name:'Сохранить настройки push',exact:true}).click();
   await page.getByText('Настройки сохранены.',{exact:true}).waitFor();
   assert(posted.some(r=>r.path==='notification-preferences/'&&r.body.quiet_start==='21:30'));
   await open('appearance');await page.getByLabel('Тема оформления',{exact:true}).selectOption('dark');
   assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
   await open('team');await layout('Dark team');
   await page.screenshot({path:'/tmp/liftcontrol-settings-desktop.png',fullPage:true});
   await page.getByLabel('Логин',{exact:true}).fill('new-worker');
   await page.getByRole('button',{name:'Создать сотрудника и ссылку',exact:true}).click();
   await page.getByRole('button',{name:'Копировать ссылку',exact:true}).waitFor();
   await page.setViewportSize({width:320,height:740});await layout('Long setup URL 320');
   await open('notifications');await layout('Dark mobile notifications');
   await page.screenshot({path:'/tmp/liftcontrol-settings-mobile.png',fullPage:true});
   await open('application');await page.getByRole('button',{name:'Проверить обновления',exact:true}).click();
   assert(posted.some(r=>r.path==='updates/system/'&&r.body.action==='check'));
   await page.goBack();
   await nav.waitFor();
   await open('notifications');
   await page.reload();await root.locator('.settings-section[aria-label="Уведомления"]').waitFor();
   assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
   assert.equal(await page.getByLabel('Обычные уведомления',{exact:true}).inputValue(),'double','Sound preferences survive reload');
  }else{
   assert.equal(await root.locator('#employee-create').count(),0,'Staff editor must not mount for non-managers');
   await open('application');
   if(role==='MECHANIC')await page.getByText('Панель открыта как установленное приложение.',{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Проверить обновления',exact:true}).count(),0,'Only server owner can update');
  }
  if(admin){
   await page.goto(origin+'/#technicians');await page.getByRole('heading',{name:'Механики',exact:true}).waitFor();
   assert.equal(await page.locator('.staff-row').count(),20);
   await page.getByLabel('Поиск сотрудника',{exact:true}).fill('Сотрудник 099');
   assert.equal(await page.locator('.staff-row').count(),1);
   await page.setViewportSize({width:320,height:740});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Compact staff directory 320');
  }
  assert.deepEqual(errors,[],role+' browser errors');
  console.log('PASS settings: '+role+'; 7 sections and viewport sizes 320–2560; no overflow or overlapping controls');
  await context.close();
 }
 await browser.close();
 }catch(e){await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
