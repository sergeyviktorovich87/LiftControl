const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.TICKET_ORIGIN||'http://127.0.0.1:5173';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.TICKET_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let page;
 try{
 for(const role of ['ADMIN','MECHANIC']){
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true,configurable:true}));page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const ago=n=>new Date(Date.now()-n*60000).toISOString();
  const rows=[
   {id:245,address:'50 лет Октября, 265',title:'Не работает кнопка вызова',elevator:10,status:'NEW',priority:'NORMAL',created_at:ago(1)},
   {id:246,address:'Игнатьевское шоссе, 14/10, корпус с длинным обозначением',title:'Шум при движении',elevator:11,status:'IN_PROGRESS',priority:'NORMAL',assigned_to:2,created_at:ago(35)},
   {id:247,address:'Ленина, 17',title:'Не закрываются двери',elevator:10,status:'IN_PROGRESS',priority:'NORMAL',assigned_to:1,created_at:ago(18)},
   {id:248,address:'50 лет Октября, 265/2',title:'Люди в кабине, 5 этаж',description:'Заявка на дом, застревание на 5 этаже',elevator:null,entrance_hint:'2',status:'NEW',priority:'ENTRAPMENT',assigned_to:1,created_at:ago(4)},
   {id:240,address:'Архивный адрес',title:'Выполненная заявка',elevator:10,status:'DONE',priority:'NORMAL',created_at:ago(240)},
   {id:241,address:'Архивный адрес',title:'Отменённая заявка',elevator:null,status:'CANCELED',priority:'NORMAL',created_at:ago(250)},
  ].map(t=>({building:1,created_by:9,photos:[],...t}));
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname.replace('/api/','');let value=[];
   if(path==='me/')value={id:1,name:'Сергей',role,organization:'Эверест',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'fixture',technician:role==='MECHANIC'?1:null,can_create_ticket:role==='ADMIN',can_manage:role==='ADMIN',can_manage_access:role==='ADMIN',notification_counts_api:1};
   else if(path==='tickets/')value=rows;
   else if(/^tickets\/\d+\/$/.test(path))value=rows.find(t=>t.id===Number(path.split('/')[1]));
   else if(path.endsWith('/history/'))value={events:[],comments:[]};
   else if(path==='buildings/')value=[{id:1,address:'50 лет Октября, 265/2',name:'Дом'}];
   else if(path==='elevators/')value=[{id:10,building:1,active:true,factory_number:'AM-2041',entrance:'1',assigned_technician:1},{id:11,building:1,active:true,entrance_kind:'LIFT',entrance:'20',factory_number:'LONG-FACTORY-12345678901234567890',assigned_technician:2}];
   else if(path==='technicians/')value=[{id:1,full_name:'Владимир Шатравка',active:true,can_receive_tasks:true},{id:2,full_name:'Иван Кантемиров',active:true,can_receive_tasks:true}];
   else if(path==='notifications/counts/')value={unread:0,sections:{}};
   else if(path==='media/')value={results:[],count:0,next:null};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin+'/#tickets');await page.getByRole('heading',{name:'Заявки',exact:true}).waitFor();const list=page.locator('.tickets-mobile-list');const mobileRows=list.locator('.ticket-mobile-row');
  assert.equal(await mobileRows.count(),4);assert((await mobileRows.first().getAttribute('aria-label')).includes('248'),'Entrapment must precede a newer ordinary ticket');assert((await mobileRows.first().innerText()).includes('Подъезд 2 · лифт не уточнён'));
  for(const [width,height] of [[2560,1440],[1440,1000],[1100,768],[1024,768],[926,430],[768,1024],[412,915],[390,844],[360,780],[320,640]]){
   await page.setViewportSize({width,height});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Ticket viewport overflow '+width);
   if(width<=1100){assert(await list.isVisible(),'Mobile list must replace the table '+width);assert(!(await page.locator('.tickets-desktop-table').isVisible()));for(const row of await mobileRows.all()){const box=await row.boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);}}
   else{assert(await page.locator('.tickets-desktop-table').isVisible());assert(!(await list.isVisible()));assert.equal(await page.getByRole('button',{name:'Открыть',exact:true}).count(),6,'Desktop keeps the complete existing table');}
  }
  await page.getByRole('button',{name:'Новые 2',exact:true}).click();assert.equal(await mobileRows.count(),2);await page.getByRole('button',{name:'В работе 2',exact:true}).click();assert.equal(await mobileRows.count(),2);await page.getByRole('button',{name:'Все 4',exact:true}).click();
  await page.getByRole('textbox',{name:'Поиск заявок',exact:true}).fill('248');assert.equal(await mobileRows.count(),1);await mobileRows.first().click();const ticket=page.getByRole('dialog',{name:'Заявка #248',exact:true});await ticket.waitFor();await ticket.getByRole('button',{name:'Закрыть',exact:true}).click();await page.getByRole('button',{name:'Очистить поиск заявок',exact:true}).click();
  await page.getByRole('button',{name:'Дополнительные фильтры заявок',exact:true}).click();
  assert.equal(await page.getByLabel('Только мои заявки',{exact:true}).count(),role==='ADMIN'?0:1);
  if(role==='MECHANIC'){await page.getByLabel('Только мои заявки',{exact:true}).check();assert.equal(await mobileRows.count(),3);await page.getByLabel('Только мои заявки',{exact:true}).uncheck();}
  await page.getByLabel('Тип в списке заявок',{exact:true}).selectOption('ENTRAPMENT');assert.equal(await mobileRows.count(),1);await page.getByRole('button',{name:'Сбросить фильтры',exact:true}).click();await page.getByRole('button',{name:'Дополнительные фильтры заявок',exact:true}).click();
  await page.getByRole('button',{name:'Архив',exact:true}).click();assert.equal(await mobileRows.count(),2);await page.getByRole('button',{name:'Выполнены 1',exact:true}).click();assert.equal(await mobileRows.count(),1);await page.getByRole('button',{name:'Отменены 1',exact:true}).click();assert.equal(await mobileRows.count(),1);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Archive filters must fit 320px');await page.getByRole('button',{name:'К открытым',exact:true}).click();assert.equal(await mobileRows.count(),4);
  assert.equal(await page.getByRole('button',{name:'Новая заявка',exact:true}).count(),role==='ADMIN'?1:0);
  if(role==='ADMIN'){
   await page.getByRole('button',{name:'Новая заявка',exact:true}).click();const form=page.getByRole('dialog',{name:'Новая заявка',exact:true});await form.waitFor();await form.getByRole('button',{name:'Закрыть',exact:true}).click();
   await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/lift-tickets-list-mobile.png',fullPage:true});await page.setViewportSize({width:320,height:740});await page.screenshot({path:'/tmp/lift-tickets-list-narrow.png',fullPage:true});
   for(let i=0;i<100;i++)rows.push({...rows[0],id:1000+i,title:'Проверка большого списка '+i});await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.getByRole('button',{name:/^Показать ещё/}).waitFor();assert.equal(await mobileRows.count(),30);await page.getByRole('button',{name:/^Показать ещё/}).click();assert.equal(await mobileRows.count(),60);await page.getByRole('textbox',{name:'Поиск заявок',exact:true}).fill('1001');assert.equal(await mobileRows.count(),1);
  }
  assert.deepEqual(errors,[],role+' runtime errors');console.log('PASS tickets mobile '+role+': 320–2560, urgency, wrapped addresses, whole-row detail, filters, archive, role-aware creation and bounded long list');await context.close();
 }
 await browser.close();
 }catch(e){if(page&&!page.isClosed())await page.screenshot({path:'/tmp/lift-tickets-list-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
