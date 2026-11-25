const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.HOME_TEST_ORIGIN||'http://127.0.0.1:5173';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HOME_CHROME_EXECUTABLE||'/usr/bin/chromium',args:['--no-sandbox']});
 let activePage;
 try{
 for(const role of ['ADMIN','MECHANIC','DIRECTOR','OFF_DUTY']){
  const mechanic=role==='MECHANIC',off=role==='OFF_DUTY',manager=!mechanic&&!off;
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});
  if(mechanic)await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));
  const page=await context.newPage();activePage=page;
  const errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  const profile={id:manager?10:mechanic?1:3,name:'Сергей Александрович',role:off?'MECHANIC':role,organization:'Мегаполис',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'home-test',can_manage:manager,can_manage_access:manager,can_create_ticket:manager||mechanic,on_duty:mechanic,technician:manager?null:mechanic?1:3,duty_shift:{id:7,technician:1,technician_name:'Александр Александрович Константинопольский',start:'2026-11-25T00:00:00Z',end:'2099-11-26T00:00:00Z',acknowledged_at:null}};
  const technicians=[{id:1,full_name:profile.duty_shift.technician_name,active:true,role:'MECHANIC'},{id:2,full_name:'Игорь Кантемиров',active:true,role:'MECHANIC'},{id:3,full_name:'Механик без дежурства',active:true,role:'MECHANIC'}];
  const elevators=[{id:1,building:1,entrance:'2',entrance_kind:'ENTRANCE',assigned_technician:1,active:true},{id:2,building:1,entrance:'20',entrance_kind:'LIFT',assigned_technician:2,active:true}];
  let tickets=[{id:248,address:'Ленина, 12',elevator:1,title:'Люди в кабине',priority:'ENTRAPMENT',status:'NEW',assigned_to:1,created_at:'2026-11-25T00:00:00Z',elevator_label:'Лифт №1'},
   {id:247,address:'50 лет Октября, 265',elevator:2,title:'Не закрываются двери',priority:'NORMAL',status:'NEW',assigned_to:2,created_at:'2026-11-25T00:02:00Z'},
   {id:246,address:'Игнатьевское шоссе, 14',elevator:1,title:'Не работает вызов с первого этажа',priority:'NORMAL',status:'IN_PROGRESS',assigned_to:1,created_at:'2026-11-24T23:00:00Z'},
   {id:245,address:'Зейская, 18',elevator:2,title:'Длительный ремонт двигателя',priority:'NORMAL',status:'LONG_REPAIR',assigned_to:2,created_at:'2026-11-24T22:00:00Z'},
   {id:244,address:'Амурская, 9',elevator:1,title:'Завершённая заявка',priority:'ENTRAPMENT',status:'DONE',assigned_to:1},
   {id:243,address:'Амурская, 9',elevator:1,title:'Отменённая заявка',priority:'NORMAL',status:'CANCELED',assigned_to:1}];
  for(let id=1;id<=50;id++)tickets.push({id,address:'Адрес '+id,elevator:1,title:'Обычная заявка '+id,priority:'NORMAL',status:'NEW',assigned_to:null,created_at:'2026-11-24T20:00:00Z'});
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.replace('/api/','');let value=[];
   if(request.method()!=='GET')posts.push(path);
   if(path==='me/')value=profile;
   else if(path==='tickets/')value=tickets;
   else if(path==='elevators/')value=elevators;
   else if(path==='technicians/')value=technicians;
   else if(path==='buildings/')value=[{id:1,name:'Дом',address:'Ленина, 12'}];
   else if(path==='duty/7/acknowledge/') {profile.duty_shift.acknowledged_at='2026-11-25T00:05:00Z';value=profile.duty_shift;}
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin+'/#home');await page.getByRole('heading',{name:'Главная',exact:true}).waitFor();
  const home=page.locator('.home-workspace'),filters=home.getByRole('group',{name:'Фильтры заявок'});
  const layout=async(label)=>{
   const value=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,outside:[...document.querySelectorAll('.home-workspace button,.home-workspace input,.topbar button')].filter(e=>e.getClientRects().length).filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(e=>e.getAttribute('aria-label')||e.textContent)}));
   assert(!value.overflow&&!value.outside.length,label+': '+JSON.stringify(value));
  };
  assert.equal(await home.locator('.metrics').count(),0,'Business statistics must leave home');
  assert.equal(await home.getByRole('button',{name:'Новая заявка',exact:true}).count(),manager||mechanic?1:0,'Keep server creation permission');
  assert.equal(await filters.getByRole('button',{name:'Мои',exact:true}).count(),manager?0:1,'No personal filter for administrator/director');
  assert.equal(await home.locator('.home-ticket').count(),25,'Paginate active queue');
  assert((await home.locator('.home-ticket').first.textContent()).includes('Люди в кабине'),'Entrapment must lead the queue');
  assert.equal(await home.getByText('Завершённая заявка',{exact:true}).count(),0);
  assert.equal(await home.getByText('Отменённая заявка',{exact:true}).count(),0);
  await page.locator('.topbar-duty .duty-acceptance.pending').getByText('Смена не принята',{exact:true}).waitFor();
  for(const [width,height] of [[2560,1440],[1440,1000],[1024,768],[768,1024],[540,900],[412,915],[360,780],[320,740]]){
   await page.setViewportSize({width,height});await layout(role+' '+width);
  }
  await page.screenshot({path:'/tmp/liftcontrol-home-'+role.toLowerCase()+'-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await home.getByRole('navigation',{name:'Страницы заявок'}).getByRole('button',{name:'Далее',exact:true}).click();
  assert(!(await home.locator('.home-ticket').first.textContent()).includes('Люди в кабине'));
  await home.getByLabel('Поиск активной заявки').fill('Игнатьевское');
  assert.equal(await home.locator('.home-ticket').count(),1);
  await home.getByLabel('Поиск активной заявки').fill('');
  await filters.getByRole('button',{name:'В работе',exact:true}).click();
  assert.equal(await home.locator('.home-ticket').count(),2);
  await filters.getByRole('button',{name:'Новые',exact:true}).click();
  assert.equal(await home.getByText('Не работает вызов с первого этажа',{exact:true}).count(),0);
  if(!manager){
   await filters.getByRole('button',{name:'Мои',exact:true}).click();
   if(mechanic){assert((await home.locator('.home-ticket').first.textContent()).includes('Люди в кабине'));assert.equal(await home.getByText('Не закрываются двери',{exact:true}).count(),0);}
   else {await home.getByRole('heading',{name:'Заявки не найдены'}).waitFor();}
  }
  await filters.getByRole('button',{name:'Все',exact:true}).click();
  if(mechanic){
   await page.getByRole('button',{name:'Принял смену',exact:true}).click();
   await page.locator('.topbar-duty .duty-acceptance.accepted').getByText('Принята в 09:05',{exact:true}).waitFor();
   assert(posts.includes('duty/7/acknowledge/'));
   assert.equal(await page.getByRole('button',{name:'Принял смену',exact:true}).count(),0);
   await page.reload();await page.locator('.topbar-duty .duty-acceptance.accepted').waitFor();
  }else assert.equal(await page.getByRole('button',{name:'Принял смену',exact:true}).count(),0);
  if(manager||mechanic){
   await home.getByRole('button',{name:'Новая заявка',exact:true}).click();
   await page.getByRole('dialog').waitFor();
   await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  }
  tickets=tickets.map(t=>t.id===248?{...t,status:'DONE'}:t);
  await home.getByRole('button',{name:'Обновить заявки',exact:true}).click();
  await home.getByText('Люди в кабине',{exact:true}).waitFor({state:'hidden'});
  tickets=[];await home.getByRole('button',{name:'Обновить заявки',exact:true}).click();
  await home.getByRole('heading',{name:'Активных заявок нет',exact:true}).waitFor();
  if(manager)assert.equal(await filters.getByRole('button',{name:'Мои',exact:true}).count(),0);
  profile.duty_shift=null;await home.getByRole('button',{name:'Обновить заявки',exact:true}).click();
  await page.locator('.topbar-duty').getByText('Не назначен',{exact:true}).waitFor();
  assert.equal(await page.locator('.topbar-duty .duty-acceptance').count(),0);
  await page.screenshot({path:'/tmp/liftcontrol-home-'+role.toLowerCase()+'-desktop.png',fullPage:true});
  await home.getByRole('button',{name:'Все заявки и история',exact:true}).click();
  await page.getByRole('heading',{name:'Заявки',exact:true}).waitFor();
  assert.deepEqual(errors,[],role+' runtime errors');
  console.log('PASS home: '+role+'; urgency, filters, 320–2560px, pagination, creation, shift acceptance, refresh and empty states');
  await context.close();
 }
 await browser.close();
 }catch(error){if(activePage&&!activePage.isClosed())await activePage.screenshot({path:'/tmp/liftcontrol-home-failed.png',fullPage:true});await browser.close();throw error;}
})().catch(error=>{console.error(error);process.exit(1);});
