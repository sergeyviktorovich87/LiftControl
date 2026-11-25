const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.COMMISSIONING_ORIGIN||'http://127.0.0.1:5173';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=','base64');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.COMMISSIONING_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let current;
 try{
 for(const role of ['ADMIN','ADJUSTER','MECHANIC']){
  const admin=role==='ADMIN',context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});if(!admin)await context.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));
  const page=await context.newPage();current=page;const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  let expenses=[],failedExpense=false,nameplates=[],counter=10;
  const members=[{user:1,name:'Алексей Алексеев',can_commissioning:true},{user:2,name:'Владимир Шатравка',can_commissioning:true},{user:3,name:'Александр Александрович Константинопольский',can_commissioning:false}];
  const lifts=[1,2,3,4].map((id,index)=>({id,label:'Лифт №'+id,factory_number:'AM-204'+id,progress:[72,100,45,60][index],revision:4,can_edit:!admin&&id!==2&&id!==4,can_view_nameplates:admin||id!==2&&id!==4,assignees:[{user:id%2?1:2,name:id%2?'Алексей Алексеев':'Владимир Шатравка'}],history:[{id,author:id%2?'Алексей Алексеев':'Владимир Шатравка',before:50,after:[72,100,45,60][index],description:['Настроены двери кабины','Испытания завершены','Проверка цепей безопасности','Требуется регулировка'][index],created_at:'2026-11-25T01:24:00Z',photos:id===1?[{id:1,url:'/fixture.png'}]:[]}]}));
  const project={id:1,name:'ЖК «Амурский»',address:'Игнатьевское шоссе, 14',archived:false,can_manage:admin,lifts,needs:[{id:1,category:'WATER',description:'Вода в приямке',blocking:true,resolved:false}],extras:[{id:1,description:'Регулировка дополнительных дверей',price:'2000',status:'PENDING'}],lift_requests:[{id:1,label:'Лифт №5',status:'PENDING'}]};
  const detail=id=>({...project,id,name:id===2?'Архивный объект':project.name,archived:id===2,progress:lifts.reduce((n,l)=>n+l.progress,0)/4,lift_count:4,expenses:admin?[...expenses,{id:999,author:'Другой наладчик',amount:'200',description:'Чужой личный расход',has_receipt:false,spent_on:'2026-11-25'}]:expenses});
  await page.route('**/fixture.png',route=>route.fulfill({contentType:'image/png',body:png}));
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.replace('/api/','');let value=[];
   const json=(request.headers()['content-type']||'').includes('application/json'),body=request.method()==='GET'?null:json?request.postDataJSON():request.postData();
   if(body!==null)writes.push({path,body});
   if(path==='me/')value={id:admin?10:1,name:admin?'Сергей':'Алексей Алексеев',role,organization:'Мегаполис',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'commission-fixture',can_manage:admin,can_manage_access:admin,can_commissioning:true,commissioning_only:role==='ADJUSTER',notification_counts_api:1};
   else if(path==='notifications/counts/')value={unread:2,sections:{},commissioning_chat:2};
   else if(path==='commissioning/')value=[detail(1),detail(2)];
   else if(path==='commissioning/assignees/')value=members;
   else if(/^commissioning\/[12]\/$/.test(path))value=detail(Number(path.split('/')[1]));
   else if(path==='commissioning/1/lifts/1/progress/'){
    const fields=json?body:Object.fromEntries(['progress','revision','description'].map(key=>[key,body.match(new RegExp('name="'+key+'"\\r\\n\\r\\n([^\\r]+)'))?.[1]]));
    assert.equal(Number(fields.revision),lifts[0].revision,'Report must send the original snapshot revision');
    const before=lifts[0].progress;lifts[0].progress=Number(fields.progress);lifts[0].revision++;lifts[0].history.unshift({id:100,author:'Алексей Алексеев',before,after:lifts[0].progress,description:fields.description,created_at:new Date().toISOString(),photos:[{id:2,url:'/fixture.png'}]});value={progress:lifts[0].progress,revision:lifts[0].revision};
   }else if(path==='commissioning/1/sync/'){
    const command=body;let existing=expenses.find(e=>e.operation===command.id);
    if(!existing){existing={...command.body,id:counter++,operation:command.id,author:'Алексей Алексеев',has_receipt:false};expenses.push(existing);}
    if(!failedExpense){failedExpense=true;await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Проверка потери ответа сервера'})});return;}
    value={ok:true};
   }else if(path==='commissioning/1/lifts/1/nameplates/'){
    if(request.method()==='POST'){nameplates.push({id:1,description:'Ограничитель скорости',author:'Алексей Алексеев',created_at:new Date().toISOString(),url:'/fixture.png'});}
    value=nameplates;
   }else if(/^commissioning\/1\/lifts\/\d+\/assign\/$/.test(path)){
    const lift=lifts.find(l=>l.id===Number(path.split('/')[3]));if(body.active===false)lift.assignees=lift.assignees.filter(a=>a.user!==body.user);else{lift.assignees.push({user:body.user,name:members.find(m=>m.user===body.user).name});members.find(m=>m.user===body.user).can_commissioning=true;}value={ok:true};
   }else if(path==='commissioning/1/extra-work/1/decision/'){project.extras[0].status=body.approve?'APPROVED':'REJECTED';value={ok:true};}
   else if(path==='commissioning/1/needs/1/resolve/'){project.needs[0].resolved=true;value={ok:true};}
   else if(path==='commissioning/1/expenses/10/reimburse/'){expenses[0].reimbursed_at=new Date().toISOString();value={ok:true};}
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin+'/#commissioning');await page.getByRole('heading',{name:'Объекты наладки',exact:true}).waitFor();
  const workspace=page.locator('.comm-workspace');
  await workspace.locator('.comm-project-row').filter({hasText:'ЖК «Амурский»'}).waitFor();
  assert.equal(await workspace.locator('.comm-project-row').count(),1,'Archive is hidden by default');
  assert.equal(await workspace.getByRole('form').count(),0,'No creation forms on the landing page');
  const layout=async label=>{
   const result=await page.evaluate(()=>{
    const visible=[...document.querySelectorAll('.comm-workspace input,.comm-workspace select,.comm-workspace textarea,.comm-workspace button')].filter(e=>e.getClientRects().length),outside=visible.filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(e=>e.getAttribute('aria-label')||e.textContent);
    return {overflow:document.documentElement.scrollWidth>innerWidth+1,outside};
   });assert(!result.overflow&&!result.outside.length,label+': '+JSON.stringify(result));
  };
  for(const width of [2560,1440,1024,768,540,412,360,320]){await page.setViewportSize({width,height:915});await layout(role+' projects '+width);}
  await page.setViewportSize({width:1440,height:1000});await workspace.locator('.comm-project-row').filter({hasText:'ЖК «Амурский»'}).click();
  await workspace.getByRole('heading',{name:'ЖК «Амурский»',exact:true}).waitFor();await workspace.locator('.comm-lift-row').first().waitFor();
  assert.equal(await workspace.locator('.comm-lift-row').count(),4);
  for(const width of [2560,1440,1024,768,540,412,360,320]){
   await page.setViewportSize({width,height:915});
   for(const tab of ['Лифты','Допработы','Расходы','Шильдики','История']){await workspace.getByRole('tab',{name:tab,exact:true}).click();await layout(role+' '+width+' '+tab);}
  }
  await workspace.getByRole('tab',{name:'Лифты',exact:true}).click();
  await page.setViewportSize({width:412,height:915});await page.screenshot({path:'/tmp/lift-commission-'+role.toLowerCase()+'-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:'/tmp/lift-commission-'+role.toLowerCase()+'-desktop.png',fullPage:true});
  if(admin){
   assert.equal(await workspace.getByRole('button',{name:'Добавить отчёт',exact:true}).count(),0,'Managers do not post worker progress');
   await workspace.getByRole('button',{name:'Участники',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Участники объекта'});await dialog.waitFor();
   await dialog.getByLabel('Исполнитель · Лифт №1',{exact:true}).selectOption('3');await dialog.getByRole('button',{name:'Выдать роль и назначить',exact:true}).click();
   await dialog.getByText('Александр Александрович Константинопольский',{exact:true}).waitFor();assert(writes.some(w=>w.path.endsWith('/assign/')&&w.body.grant_commissioning===true));
   await page.setViewportSize({width:320,height:740});await layout('Members phone');await dialog.getByRole('button',{name:'Закрыть',exact:true}).click();
   await workspace.getByRole('tab',{name:'Расходы',exact:true}).click();assert.equal(await workspace.getByRole('button',{name:'Записать расход',exact:true}).count(),0,'Managers cannot create worker expenses');
   await workspace.getByText('Чужой личный расход',{exact:false}).waitFor();
   await workspace.getByRole('tab',{name:'Допработы',exact:true}).click();await workspace.getByRole('button',{name:'Согласовать',exact:true}).click();assert(writes.some(w=>w.path.includes('extra-work/1/decision/')&&w.body.approve));
  }else{
   await page.setViewportSize({width:412,height:915});await workspace.locator('.comm-lift-row').filter({hasText:'Лифт №2'}).click();
   await workspace.locator('.comm-lift-detail').getByRole('heading',{name:'Лифт №2',exact:true}).waitFor();assert.equal(await workspace.getByRole('button',{name:'Добавить отчёт',exact:true}).count(),0,'Other worker lift is read-only');
   await workspace.getByRole('button',{name:'К списку лифтов',exact:true}).click();await workspace.getByRole('button',{name:'Добавить отчёт',exact:true}).click();
   let dialog=page.getByRole('dialog',{name:'Новый отчёт',exact:true});await dialog.waitFor();
   await dialog.getByLabel('Готовность, процентов',{exact:true}).fill('80');await dialog.getByLabel('Что сделано',{exact:true}).fill('Отрегулированы двери, проверена точность остановок.');
   await dialog.getByLabel('Фотографии отчёта',{exact:true}).setInputFiles({name:'report.png',mimeType:'image/png',buffer:png});
   for(const width of [1440,768,412,360,320]){await page.setViewportSize({width,height:915});await layout('Report '+width);}
   await page.setViewportSize({width:412,height:915});await page.screenshot({path:'/tmp/lift-commission-'+role.toLowerCase()+'-report.png',fullPage:true});
   await page.goBack();await dialog.waitFor({state:'hidden'});await workspace.locator('.comm-lift-detail').getByRole('button',{name:'Добавить отчёт',exact:true}).click();dialog=page.getByRole('dialog',{name:'Новый отчёт',exact:true});
   assert.equal(await dialog.getByLabel('Что сделано',{exact:true}).inputValue(),'Отрегулированы двери, проверена точность остановок.','Back preserves the draft');
   await dialog.getByRole('button',{name:'Сохранить отчёт',exact:true}).click();await dialog.waitFor({state:'hidden'});
   await workspace.getByText('Отчёт сохранён',{exact:true}).waitFor();assert.equal(lifts[0].progress,80);assert.equal(lifts[0].revision,5);
   await page.reload();await workspace.getByRole('heading',{name:'ЖК «Амурский»',exact:true}).waitFor();await workspace.locator('.comm-lift-detail').getByRole('heading',{name:'Лифт №1',exact:true}).waitFor();
   await workspace.getByRole('tab',{name:'Расходы',exact:true}).click();assert.equal(await workspace.getByText('Чужой личный расход',{exact:false}).count(),0);
   await workspace.getByRole('button',{name:'Записать расход',exact:true}).click();dialog=page.getByRole('dialog',{name:'Записать расход',exact:true});await dialog.waitFor();
   await dialog.getByLabel('Сумма, ₽',{exact:true}).fill('321.50');await dialog.getByLabel('Описание расхода',{exact:true}).fill('Проверочный инструмент');await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();
   await dialog.getByRole('alert').waitFor();await dialog.getByRole('button',{name:'Отмена',exact:true}).click();await dialog.waitFor({state:'hidden'});
   await workspace.getByRole('button',{name:'Записать расход',exact:true}).click();dialog=page.getByRole('dialog',{name:'Записать расход',exact:true});await dialog.getByRole('button',{name:'Повторить сохранение',exact:true}).click();await dialog.waitFor({state:'hidden'});
   const attempts=writes.filter(w=>w.path==='commissioning/1/sync/');assert.equal(attempts.length,2);assert.equal(attempts[0].body.id,attempts[1].body.id);assert.equal(expenses.length,1,'Lost response must not duplicate an expense');
   await workspace.getByRole('tab',{name:'Шильдики',exact:true}).click();await workspace.getByLabel('Что за шильдик',{exact:true}).fill('Ограничитель скорости');await workspace.getByLabel('Снять фото шильдика',{exact:true}).setInputFiles({name:'plate.png',mimeType:'image/png',buffer:png});
   await workspace.getByRole('button',{name:'Сохранить шильдик',exact:true}).click();await workspace.locator('figcaption').getByText('Ограничитель скорости',{exact:true}).waitFor();
  }
  await workspace.getByRole('button',{name:'Все объекты',exact:true}).click();await workspace.getByLabel('Показывать архив',{exact:true}).check();await workspace.locator('.comm-project-row').filter({hasText:'Архивный объект'}).click();
  await workspace.getByText('Архив: изменения запрещены, история сохранена.',{exact:true}).waitFor();assert.equal(await workspace.getByRole('button',{name:'Добавить отчёт',exact:true}).count(),0);await workspace.getByRole('tab',{name:'Расходы',exact:true}).click();assert.equal(await workspace.getByRole('button',{name:'Записать расход',exact:true}).count(),0);
  assert.deepEqual(errors,[],role+' runtime errors');console.log('PASS commissioning '+role+': 320–2560, tabs, roles, archive, mobile navigation, report photos and expense replay');await context.close();
 }
 await browser.close();
 }catch(e){if(current&&!current.isClosed())await current.screenshot({path:'/tmp/lift-commission-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
