const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.PARTS_TEST_ORIGIN||'http://127.0.0.1:5173';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PARTS_CHROME_EXECUTABLE||'/usr/bin/chromium',args:['--no-sandbox']});let activePage;
 try{
 for(const role of ['ADMIN','MECHANIC']){
  const admin=role==='ADMIN',context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});
  if(!admin)await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));
  const page=await context.newPage();activePage=page;const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  const profile={id:1,name:'Сергей Александрович',role,organization:'Мегаполис',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'parts-fixture',can_manage:admin,can_manage_access:admin,technician:admin?null:1,on_duty:!admin,can_create_ticket:true,duty_shift:{id:7,technician:1,technician_name:'Александр Александрович Константинопольский',start:'2026-11-25T00:00:00Z',end:'2099-11-26T00:00:00Z',acknowledged_at:'2026-11-25T00:03:00Z'}};
  let parts=[{id:84,part:'Фотозавеса универсальная',address:'Ленина, 12',elevator:1,elevator_label:'Лифт №1',quantity:1,author_name:'И. Кантемиров',requested_by:1,status:'NEW',notes:'24 В, универсальная',created_at:'2026-11-25T00:00:00Z',can_edit:true,photos:[{id:1,url:'/part-photo/1.png',name:'Маркировка'}]},
   {id:83,part:'Ролик замка двери',address:'50 лет Октября, 265',elevator:2,quantity:4,author_name:'С. Николаев',requested_by:2,status:'APPROVED',notes:'',created_at:'2026-11-24T23:00:00Z',can_edit:admin,photos:[]},
   {id:82,part:'Канат тяговый 8 мм',address:'Игнатьевское шоссе, 14',elevator:1,quantity:240,author_name:'В. Шатравка',requested_by:2,status:'ORDERED',notes:'',created_at:'2026-11-24T22:00:00Z',can_edit:false,photos:[]},
   {id:81,part:'Кнопка вызова 24 В',address:'Зейская, 18',elevator:1,quantity:2,author_name:'С. Андросов',requested_by:2,status:'RECEIVED',notes:'',created_at:'2026-11-24T21:00:00Z',can_edit:false,photos:[]},
   {id:80,part:'Выданный вкладыш',address:'Амурская, 9',elevator:1,quantity:8,author_name:'И. Кантемиров',requested_by:2,status:'ISSUED',notes:'',created_at:'2026-11-24T20:00:00Z',can_edit:false,photos:[]},
   {id:79,part:'Отменённый контактор',address:'Ленина, 12',elevator:1,quantity:1,author_name:'С. Николаев',requested_by:2,status:'CANCELED',notes:'',created_at:'2026-11-24T19:00:00Z',can_edit:false,photos:[]}];
  for(let id=1;id<=50;id++)parts.push({id,part:'Запчасть '+id,address:'Адрес '+id,elevator:1,quantity:id,author_name:'С. Николаев',requested_by:2,status:'NEW',notes:'',created_at:'2026-11-24T18:00:00Z',can_edit:admin,photos:[]});
  await page.route('**/part-photo/*.png',route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=','base64')}));
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.replace('/api/','');let value=[];
   if(request.method()!=='GET')writes.push({path,body:request.postDataJSON()});
   if(path==='me/')value=profile;
   else if(path==='parts/'){
    if(request.method()==='POST'){const part={...request.postDataJSON(),id:Math.max(99,...parts.map(part=>part.id))+1,requested_by:1,author_name:profile.name,address:request.postDataJSON().elevator?'Ленина, 12':'Без привязки к лифту',created_at:new Date().toISOString(),can_edit:true,photos:[]};parts=[part,...parts];value=part;}else value=parts;
   }else if(/^parts\/\d+\/$/.test(path)){
    const id=Number(path.split('/')[1]);if(request.method()==='PATCH')parts=parts.map(part=>part.id===id?{...part,...request.postDataJSON()}:part);value=parts.find(part=>part.id===id);
   }else if(path==='elevators/')value=[{id:1,building:1,entrance:'2',entrance_kind:'ENTRANCE',factory_number:'TEST-1',active:true},{id:2,building:1,entrance:'20',entrance_kind:'LIFT',factory_number:'TEST-2',active:true}];
   else if(path==='buildings/')value=[{id:1,address:'Ленина, 12',name:'Дом'}];
   else if(path==='technicians/')value=[{id:1,full_name:profile.duty_shift.technician_name,active:true,role:'MECHANIC'}];
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin+'/#parts');await page.getByRole('heading',{name:'Запчасти',exact:true}).waitFor();
  const list=page.locator('.parts-workspace'),filters=list.getByRole('group',{name:'Статусы запросов запчастей'});
  await list.getByText('Фотозавеса универсальная',{exact:true}).waitFor();
  const layout=async label=>{
   const result=await page.evaluate(()=>{
    const outside=[...document.querySelectorAll('.parts-workspace button,.parts-workspace input,.topbar button')].filter(el=>el.getClientRects().length).filter(el=>{const r=el.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(el=>el.getAttribute('aria-label')||el.textContent);
    const name=document.querySelector('.topbar-duty-text').getBoundingClientRect(),state=document.querySelector('.duty-acceptance').getBoundingClientRect();
    const overlap=Math.min(name.right,state.right)-Math.max(name.left,state.left)>1&&Math.min(name.bottom,state.bottom)-Math.max(name.top,state.top)>1;
    const clipped=state.width+1<state.scrollWidth;
    return {overflow:document.documentElement.scrollWidth>innerWidth+1,outside,overlap,clipped,inline:Math.abs(name.bottom-state.bottom)<3};
   });
   assert(!result.overflow&&!result.outside.length&&!result.overlap&&!result.clipped,label+': '+JSON.stringify(result));
   if(page.viewportSize().width>=412)assert(result.inline,label+': duty name and state should be alongside');
  };
  assert.equal(await list.locator('.parts-row').count(),25);
  assert.equal(await list.locator('img,.part-card,.parts-grid').count(),0,'List must not load photo thumbnails or tiles');
  assert.equal(await filters.getByRole('button',{name:'Мои',exact:true}).count(),0);
  assert.equal(await list.getByText('Выданный вкладыш',{exact:true}).count(),0);
  for(const [width,height] of [[2560,1440],[1440,1000],[1024,768],[768,1024],[540,900],[412,915],[390,844],[360,780],[320,740]]){
   await page.setViewportSize({width,height});await layout(role+' '+width);
  }
  await page.setViewportSize({width:412,height:915});await page.screenshot({path:'/tmp/liftcontrol-parts-'+role.toLowerCase()+'-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:'/tmp/liftcontrol-parts-'+role.toLowerCase()+'-desktop.png',fullPage:true});
  await list.getByRole('navigation',{name:'Страницы запросов запчастей'}).getByRole('button',{name:'Далее',exact:true}).click();
  assert.equal(await list.getByText('Фотозавеса универсальная',{exact:true}).count(),0);
  await list.getByLabel('Поиск запчасти').fill('фотозавеса');assert.equal(await list.locator('.parts-row').count(),1);
  await list.getByLabel('Поиск запчасти').fill('');
  for(const [name,text] of [['Согласованы','Ролик замка двери'],['Заказаны','Канат тяговый 8 мм'],['Получены','Кнопка вызова 24 В']]){
   await filters.getByRole('button',{name,exact:true}).click();assert.equal(await list.locator('.parts-row').count(),1);await list.getByText(text,{exact:true}).waitFor();
  }
  await filters.getByRole('button',{name:'Все',exact:true}).click();
  await list.getByRole('button',{name:'Показать выданные и отменённые',exact:true}).click();
  assert.equal(await list.locator('.parts-row').count(),2);await list.getByText('Выданный вкладыш',{exact:true}).waitFor();
  await filters.getByRole('button',{name:'Отменены',exact:true}).click();assert.equal(await list.locator('.parts-row').count(),1);
  await list.getByRole('button',{name:'Вернуться к активным запросам',exact:true}).click();
  await list.getByText('Фотозавеса универсальная',{exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'Заявка на запчасть #84',exact:true});await dialog.waitFor();
  await dialog.getByRole('img',{name:'Маркировка',exact:true}).waitFor();
  assert.equal(await dialog.getByLabel('Статус',{exact:true}).isDisabled(),!admin);
  if(admin){
   await dialog.getByLabel('Статус',{exact:true}).selectOption('ORDERED');await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();await dialog.waitFor({state:'hidden'});
   assert(writes.some(write=>write.path==='parts/84/'&&write.body.status==='ORDERED'));
  }else{await dialog.getByRole('button',{name:'Закрыть',exact:true}).click();}
  await list.getByRole('button',{name:'Запросить запчасть',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'Запросить запчасть',exact:true});await dialog.waitFor();
  await dialog.getByRole('checkbox',{name:/Привязать к лифту/}).check();
  await dialog.getByLabel('Адрес',{exact:true}).selectOption('1');await dialog.getByLabel('Лифт',{exact:true}).selectOption('1');
  await dialog.getByLabel('Нужная запчасть',{exact:true}).fill('Проверка компактного списка');await dialog.getByLabel('Количество',{exact:true}).fill('3');
  await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await list.getByText('Проверка компактного списка',{exact:true}).waitFor();assert(writes.some(write=>write.path==='parts/'&&write.body.quantity===3));
  await list.getByRole('button',{name:'Запросить запчасть',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'Запросить запчасть',exact:true});
  assert.equal(await dialog.getByLabel('Адрес',{exact:true}).count(),0);
  await dialog.getByLabel('Нужная запчасть',{exact:true}).fill('Для склада без лифта');
  await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await list.getByText('Для склада без лифта',{exact:true}).waitFor();
  assert(writes.some(write=>write.path==='parts/'&&write.body.elevator===null&&write.body.part==='Для склада без лифта'));
  await list.getByRole('button').filter({hasText:'Для склада без лифта'}).getByText(/№\d+ · Без привязки к лифту/).waitFor();
  profile.duty_shift.acknowledged_at=null;await list.getByRole('button',{name:'Обновить запчасти',exact:true}).click();
  await page.locator('.topbar-duty .duty-acceptance.pending').getByText('Смена не принята',{exact:true}).waitFor();
  await page.setViewportSize({width:320,height:740});await layout('Pending duty on narrow phone');
  parts=[];await list.getByRole('button',{name:'Обновить запчасти',exact:true}).click();await list.getByRole('heading',{name:'Активных запросов пока нет',exact:true}).waitFor();
  await list.getByLabel('Поиск запчасти').fill('нет такой детали');await list.getByRole('heading',{name:'Запросы не найдены',exact:true}).waitFor();
  await list.getByRole('button',{name:'Сбросить фильтры',exact:true}).click();
  assert.deepEqual(errors,[],role+' browser errors');console.log('PASS parts '+role+': compact rows, 320–2560, header, filters, history, pagination, detail photos, create and existing permissions');
  await context.close();
 }
 await browser.close();
 }catch(error){if(activePage&&!activePage.isClosed())await activePage.screenshot({path:'/tmp/liftcontrol-parts-failed.png',fullPage:true});await browser.close();throw error;}
})().catch(error=>{console.error(error);process.exit(1);});
