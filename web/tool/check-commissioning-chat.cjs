const {chromium}=require('playwright');const assert=require('node:assert/strict');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=','base64');
(async()=>{const browser=await chromium.launch({executablePath:process.env.COMMISSIONING_CHAT_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let current;
try{for(const role of ['ADMIN','ADJUSTER']){
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});await context.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.__copiedChatText=text;}}}));
 const page=await context.newPage();current=page;const errors=[],posted=[],gets=[];page.on('pageerror',e=>errors.push(e.message));
 let rows=Array.from({length:35},(_,i)=>({id:i+1,body:'Проверка наладки: сообщение '+(i+1),author:i%3===0?1:2,author_name:i%3===0?'Алексей':'Александр Александрович Константинопольский',created_at:'2026-11-25T01:'+String(i).padStart(2,'0')+':00Z',receipt:{total:2,delivered:2,read:1},attachments:i===0?[{id:1,url:'/fixture.png',content_type:'image/png'}]:[]}));let failure=false;const operations=new Map();
 await page.route('**/fixture.png',r=>r.fulfill({contentType:'image/png',body:png}));
 await page.route('**/api/**',async route=>{const req=route.request(),path=new URL(req.url()).pathname.replace('/api/','');let value=[];
 if(req.method()==='GET')gets.push(path);
 if(path==='me/')value={id:1,name:'Алексей',role,organization:'Очень длинное название организации Лифт Контроль',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'commissioning-chat-fixture',can_manage:role==='ADMIN',can_manage_access:role==='ADMIN',can_commissioning:true,commissioning_only:role==='ADJUSTER',notification_counts_api:1,message_receipts_api:1,chat_design_api:1,can_export_chat:role==='ADMIN'};
 else if(path==='commissioning/chat/'&&req.method()==='POST'){
  const json=(req.headers()['content-type']||'').includes('application/json'),raw=req.postData()||'',body=json?req.postDataJSON():Object.fromEntries(['body','operation_id','expected_sender'].map(k=>[k,raw.match(new RegExp('name="'+k+'"\\r\\n\\r\\n([^\\r]*)'))?.[1]]));posted.push({path,body,photos:!json&&raw.includes('name="photos"'),wrongFiles:!json&&raw.includes('name="files"')});
  assert.equal(Number(body.expected_sender),1);assert(body.operation_id);assert(!body.client_id);
  if(!operations.has(body.operation_id)){const row={id:rows.length+1,body:body.body,author:1,author_name:'Алексей',created_at:new Date().toISOString(),attachments:json?[]:[{id:100,url:'/fixture.png',content_type:'image/png'}]};rows.push(row);operations.set(body.operation_id,row.id);}
  if(!failure){failure=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Потерян ответ сервера'})});return;}
  value={id:operations.get(body.operation_id)};
 }else if(path==='commissioning/chat/')value=rows;
 else if(path==='chat/')value=[{id:1,body:'Чат механиков',author:2,author_name:'Механик',created_at:'2026-11-25T01:00:00Z',attachments:[]}];
 else if(path==='chat/pinned/')value={message:null};else if(path==='notifications/counts/')value={unread:0,commissioning_chat:0,sections:{}};
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
 });
 await page.goto('http://127.0.0.1:5173/#commissioning-chat');await page.getByRole('heading',{name:'Чат наладчиков',exact:true}).waitFor();await page.locator('.messenger-bubble').last().waitFor();
 assert.equal(await page.locator('.chat-shell .messenger').count(),1,'Commissioning chat must use the same page shell');assert.equal(await page.locator('.topbar:visible').count(),0);assert.equal(await page.locator('.page-footer:visible').count(),0);
 const layout=async label=>{const b=await page.locator('.messenger-compose').boundingBox(),viewport=page.viewportSize();assert(b&&Math.abs(b.y+b.height-viewport.height)<2,label+' composer at viewport bottom');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' horizontal overflow');assert(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),label+' outer page must not scroll');};
 for(const width of [2560,1440,1024,860,768,540,412,360,320]){await page.setViewportSize({width,height:915});await layout(role+' '+width);}
 await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:'/tmp/lift-commissioning-chat-'+role.toLowerCase()+'-desktop.png'});await page.setViewportSize({width:360,height:800});await page.screenshot({path:'/tmp/lift-commissioning-chat-'+role.toLowerCase()+'-mobile.png'});
 await page.getByRole('button',{name:'Поиск в чате',exact:true}).click();await page.getByLabel('Поиск по загруженным сообщениям',{exact:true}).fill('сообщение 35');assert.equal(await page.locator('.messenger-bubble').count(),1);await layout('Search');await page.getByRole('button',{name:'Закрыть поиск',exact:true}).click();
 await page.getByRole('button',{name:'Действия с сообщением',exact:true}).last().click();await page.locator('.messenger-actions.expanded').getByRole('button',{name:'Копировать сообщение',exact:true}).click();assert((await page.evaluate(()=>window.__copiedChatText)).includes('сообщение 35'));
 await page.getByRole('button',{name:'Меню чата',exact:true}).click();await page.getByRole('button',{name:'Вложения чата',exact:true}).click();await page.locator('.messenger-photo-library img').first().waitFor();await layout('Photo gallery');await page.getByRole('button',{name:'Закрыть вложения',exact:true}).click();
 const compose=()=>page.getByRole('textbox',{name:'Сообщение',exact:true});await compose().fill('Черновик наладчика');
 if(role==='ADMIN'){
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();await page.locator('.sidebar nav').getByRole('button',{name:'Чат',exact:true}).click();await page.getByRole('heading',{name:'Чат',exact:true}).waitFor();assert.equal(await compose().inputValue(),'','Commissioning draft must not appear in mechanics chat');await compose().fill('Черновик механика');
  await page.getByRole('button',{name:'Открыть боковое меню',exact:true}).click();await page.locator('.sidebar nav').getByRole('button',{name:'Пусконаладка',exact:true}).click();
 }else await page.getByRole('button',{name:'К объектам наладки',exact:true}).click();
 await page.getByRole('heading',{name:'Объекты наладки',exact:true}).waitFor();await page.getByRole('button',{name:'Открыть чат наладчиков',exact:true}).click();await page.getByRole('heading',{name:'Чат наладчиков',exact:true}).waitFor();assert.equal(await compose().inputValue(),'Черновик наладчика');
 await context.setOffline(true);await compose().fill('Из очереди наладчиков');await compose().press('Enter');await page.getByText('Ожидает сети',{exact:true}).waitFor();assert.equal(posted.length,0);
 await context.setOffline(false);await page.waitForFunction(()=>!document.querySelector('.messenger-bubble.pending'),{timeout:25000});assert.equal(posted.length,2);assert.equal(posted[0].body.operation_id,posted[1].body.operation_id);assert.equal(rows.filter(r=>r.body==='Из очереди наладчиков').length,1);
 await page.getByLabel('Снять фото',{exact:true}).setInputFiles({name:'commission.png',mimeType:'image/png',buffer:png});await page.getByRole('button',{name:'Отправить',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.messenger-bubble.pending'));assert.equal(posted.length,3);assert(posted[2].photos&&!posted[2].wrongFiles,'Commissioning attachments must use photos field');
 assert(!gets.some(p=>p==='media/'||p.startsWith('media/assets/')),'Commissioning gallery must not query maintenance media');assert.deepEqual(errors,[],role+' runtime errors');console.log('PASS commissioning chat '+role+': shared full-page shell, 320–2560, camera, copy, gallery, isolated drafts and idempotent queue');await context.close();
}await browser.close();}catch(e){if(current&&!current.isClosed())await current.screenshot({path:'/tmp/lift-commissioning-chat-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
