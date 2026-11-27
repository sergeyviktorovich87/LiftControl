const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=','base64');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.TICKET_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let active;
 try{for(const role of ['ADMIN','MECHANIC']){
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));const page=await context.newPage();active=page;const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const tickets=[],commands=[],uploads=[],identified=[], operations=new Map();let lostCreate=false,lostUpload=false;
  const buildings=[{id:1,address:'Игнатьевское шоссе, 14',name:'Дом'},{id:2,address:'Другая улица, 1',name:'Другой дом'}];
  const lifts=[{id:10,building:1,active:true,factory_number:'AM-123',display_number:'Лифт №1',entrance:'2',assigned_technician:null},{id:20,building:2,active:true,factory_number:'OTHER',display_number:'Другой лифт',entrance:'1'}];
  await page.route('**/api/**',async route=>{
   const req=route.request(),path=new URL(req.url()).pathname.replace('/api/','');let value=[];const post=req.method()==='POST',body=post&&req.headers()['content-type']?.includes('application/json')?req.postDataJSON():post?req.postData():null;
   if(path==='me/')value={id:1,name:'Сергей',role,organization:'Эверест',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'ticket-test',can_create_ticket:true,can_manage:role==='ADMIN',can_manage_access:role==='ADMIN',on_duty:role==='MECHANIC',technician:role==='MECHANIC'?1:null,notification_counts_api:1};
   else if(path==='notifications/counts/')value={unread:0,sections:{}};
   else if(path==='buildings/')value=buildings;
   else if(path==='elevators/')value=lifts;
   else if(path==='technicians/')value=[{id:1,full_name:'Владимир Шатравка',role:'MECHANIC',active:true,can_receive_tasks:true}];
   else if(path==='tickets/')value=tickets;
   else if(path==='mobile/sync/'){
    commands.push(body);let row=operations.get(body.id);if(!row){assert.equal(body.body.building,1);row={id:tickets.length+1,...body.body,status:'NEW',address:buildings[0].address,elevator_label:body.body.elevator?'Лифт №1':'Лифт не уточнён',created_at:new Date().toISOString(),can_identify_lift:!body.body.elevator,photos:[]};operations.set(body.id,row);tickets.unshift(row);}
    if(!lostCreate){lostCreate=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Ответ сервера потерян'})});return;}
    value={ticket:row,replayed:true};
   }else if(path==='media/uploads/'){
    const id=body.match(/name="upload_id"\r\n\r\n([^\r]+)/)?.[1];assert(id);assert(body.includes('name="target_id"\r\n\r\n1'));uploads.push(id);
    if(!lostUpload){lostUpload=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Ответ загрузки потерян'})});return;}
    value={asset:{id:'fixture'},replayed:true};
   }else if(/^tickets\/\d+\/$/.test(path))value=tickets.find(t=>t.id===Number(path.split('/')[1]));
   else if(/^tickets\/\d+\/history\/$/.test(path))value={events:[],comments:[]};
   else if(path==='tickets/1/identify-lift/'){
    assert.equal(body.elevator,10);identified.push(body.elevator);const row=tickets.find(t=>t.id===1);row.elevator=10;row.elevator_label='Лифт №1';row.can_identify_lift=false;value=row;
   }
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  const open=async()=>{await page.getByRole('button',{name:'Новая заявка',exact:true}).click();await page.getByRole('dialog',{name:'Новая заявка',exact:true}).waitFor();};
  await page.goto((process.env.TICKET_ORIGIN||'http://127.0.0.1:5173')+'/#tickets');await page.getByRole('heading',{name:'Заявки',exact:true}).waitFor();await open();let form=page.locator('.ticket-create-form');
  assert.equal(await form.getByText('Где нужна помощь',{exact:true}).count(),0);assert.equal(await form.getByText('Заявка на дом',{exact:true}).count(),0);
  await form.getByLabel('Адрес дома *',{exact:true}).fill('Игнатьевское шоссе, 14');
  assert.equal(await form.getByRole('button',{name:'Лифт пока неизвестен',exact:true}).getAttribute('aria-pressed'),'true');
  await form.getByLabel('Подъезд, если известен',{exact:true}).fill('2');await form.getByLabel('Этаж',{exact:true}).fill('1');await form.getByLabel('Описание *',{exact:true}).fill('Житель сообщил, что лифт не вызывается. Какой именно — неизвестно.');
  await form.getByLabel('Вложения новой заявки',{exact:true}).setInputFiles({name:'request.png',mimeType:'image/png',buffer:png});await form.getByRole('button',{name:'Создать заявку',exact:true}).waitFor({state:'visible'});
  for(const width of [2560,1920,1440,1024,900,768,540,412,360,320]){
   await page.setViewportSize({width,height:915});
   const result=await page.locator('.ticket-create').evaluate(root=>{const elements=[...root.querySelectorAll('input,select,textarea,button')].filter(e=>e.getClientRects().length);return elements.filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(e=>e.getAttribute('aria-label')||e.textContent);});assert.deepEqual(result,[],role+' '+width+' horizontal overflow');
   if(width===1920||width===412)await page.screenshot({path:`/tmp/lift-ticket-create-${role.toLowerCase()}-${width===412?'mobile':'desktop'}.png`,fullPage:true});
  }
  await form.getByRole('button',{name:'Создать заявку',exact:true}).click();await form.getByRole('alert').waitFor();await form.getByRole('button',{name:'Повторить сохранение',exact:true}).click();await form.getByRole('alert').filter({hasText:'уже создана'}).waitFor();
  await form.getByRole('button',{name:'Повторить сохранение',exact:true}).click();await form.waitFor({state:'hidden'});
  assert.equal(tickets.length,1);assert.equal(commands.length,2);assert.equal(commands[0].id,commands[1].id);assert.equal(commands[0].body.elevator,null);assert.equal(commands[0].body.entrance_hint,'2');assert.equal(uploads.length,2);assert.equal(uploads[0],uploads[1]);
  await page.locator('.tickets-mobile-list').getByRole('button',{name:/^Открыть заявку №/}).click();let dialog=page.getByRole('dialog',{name:'Заявка #1',exact:true});await dialog.waitFor();
  assert.equal(await dialog.getByRole('button',{name:'Открыть карточку лифта',exact:true}).count(),0);
  await dialog.getByRole('button',{name:'Уточнить лифт',exact:true}).click();dialog=page.getByRole('dialog',{name:'Уточнить лифт',exact:true});
  await dialog.getByLabel('Лифт в доме заявки',{exact:true}).selectOption('10');assert.equal(await dialog.getByLabel('Лифт в доме заявки',{exact:true}).locator('option[value="20"]').count(),0);
  await dialog.getByRole('button',{name:'Сохранить лифт',exact:true}).click();await dialog.waitFor({state:'hidden'});dialog=page.getByRole('dialog',{name:'Заявка #1',exact:true});await dialog.getByText('Лифт уточнён. История заявки сохранена.',{exact:true}).waitFor();assert.equal(identified.length,1);assert.equal(tickets[0].id,1);await dialog.getByRole('button',{name:'Закрыть',exact:true}).last().click();
  await open();form=page.locator('.ticket-create-form');await form.getByLabel('Адрес дома *',{exact:true}).fill('Игнатьевское шоссе, 14');await form.getByRole('button',{name:'Выбрать лифт',exact:true}).click();await form.getByLabel('Лифт в выбранном доме',{exact:true}).selectOption('10');await form.getByRole('button',{name:'Застревание',exact:true}).click();assert(!(await form.getByLabel('Описание · необязательно',{exact:true}).evaluate(el=>el.required)));await form.getByRole('button',{name:'Создать заявку',exact:true}).click();await form.waitFor({state:'hidden'});assert.equal(commands.at(-1).body.elevator,10);assert.equal(commands.at(-1).body.priority,'ENTRAPMENT');assert.equal(commands.at(-1).body.description,'');assert.equal(tickets.length,2);
  assert.deepEqual(errors,[],role+' runtime errors');console.log('PASS ticket creation '+role+': 320–2560, house without lift, exact lift, entrapment, creation and upload replay, identify same ticket');await context.close();
 }
 await browser.close();}catch(e){if(active&&!active.isClosed())await active.screenshot({path:'/tmp/lift-ticket-create-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
