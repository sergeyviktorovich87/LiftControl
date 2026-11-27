const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PUSH_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let page;
 try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});page=await context.newPage();const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 let attempts=0,releasePost,arrived;const arrival=new Promise(r=>arrived=r);
 const rows=Array.from({length:34},(_,i)=>({id:i+1,kind:'created',title:'Входящее №'+(i+1),body:'Текст уведомления',target_type:'ticket',target_id:i+1,category:i<3?'entrapment':'ordinary',created_at:new Date().toISOString(),read_at:null}));
 const counts=()=>({ordinary:rows.filter(r=>!r.read_at&&r.category==='ordinary').length,entrapment:rows.filter(r=>!r.read_at&&r.category==='entrapment').length});
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.replace('/api/','');let value=[];
  if(req.method()==='POST')writes.push(path);
  if(path==='me/')value={id:1,name:'Сергей',role:'ADMIN',organization:'Эверест',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'fixture',can_manage:true,can_create_ticket:true,notification_counts_api:1,lift_documents_api:1};
  else if(path==='notifications/counts/'){const c=counts();value={unread:c.ordinary+c.entrapment,entrapment:c.entrapment,sections:{tickets:c.ordinary+c.entrapment}};}
  else if(path==='notifications/'){
   const category=url.searchParams.get('category'),before=Number(url.searchParams.get('before')||Number.MAX_SAFE_INTEGER);
   const items=rows.filter(r=>(!category||r.category===category)&&r.id<before).sort((a,b)=>b.id-a.id);const c=counts();value={results:items.slice(0,30),unread_by_category:c,unread:category?c[category]:c.ordinary+c.entrapment,next_before:items.length>30?items[29].id:null};
  }else if(path==='notifications/read-all/'){
   assert.equal(req.method(),'POST');assert.equal(req.headers()['x-organization-id'],'1');assert.deepEqual(req.postDataJSON(),{});attempts++;
   if(attempts===1){arrived();await new Promise(r=>releasePost=r);await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Временный сбой'})});return;}
   const through=Math.max(...rows.map(r=>r.id)),read_at=new Date().toISOString();let updated=0;for(const row of rows)if(!row.read_at&&row.id<=through){row.read_at=read_at;updated++;}
   if(attempts===2)rows.push({id:35,kind:'message',title:'Пришло во время операции',body:'Оставить непрочитанным',target_type:'chat',target_id:35,category:'ordinary',created_at:new Date().toISOString(),read_at:null});
   value={through,updated,read_at};
  }
  await route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
 });
 await page.goto((process.env.PUSH_ORIGIN||'http://127.0.0.1:5173')+'/#notifications');await page.getByRole('heading',{name:'Уведомления',exact:true}).waitFor();
 const action=page.getByRole('button',{name:'Отметить всё как прочитанное',exact:true});await action.waitFor();
 await page.getByRole('button',{name:/^Обычные/}).click();await page.getByRole('button',{name:'Загрузить ещё',exact:true}).waitFor();assert.equal(await page.getByLabel('Непрочитанное',{exact:true}).count(),30);
 for(const [width,height] of [[2560,1440],[1440,1000],[1024,768],[900,900],[768,1024],[412,915],[360,780],[320,640]]){
  await page.setViewportSize({width,height});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Notification header overflow '+width);
  for(const label of ['Отметить всё как прочитанное','Настройки уведомлений','Обновить']){const box=await page.getByRole('button',{name:label,exact:true}).boundingBox();assert(box&&box.x>=0&&box.x+box.width<=width+1,'Action out of bounds '+label+' '+width);}
 }
 await action.click();await arrival;await page.getByRole('button',{name:'Отмечаю…',exact:true}).waitFor();assert(await page.getByRole('button',{name:'Обновить',exact:true}).isDisabled());releasePost();await page.getByRole('alert').filter({hasText:'Временный сбой'}).waitFor();assert.equal(rows.filter(r=>!r.read_at).length,34);assert(!(await action.isDisabled()));
 await action.click();await page.getByRole('status').filter({hasText:'Уведомления отмечены как прочитанные.'}).waitFor();await page.getByText('Пришло во время операции',{exact:true}).waitFor();assert.equal(await page.getByLabel('Непрочитанное',{exact:true}).count(),1);assert.equal(rows.filter(r=>!r.read_at).length,1);assert(!(await action.isDisabled()));
 await action.click();await page.waitForFunction(()=>{const button=document.querySelector('button.notification-mark-all');return button?.disabled&&button.textContent.includes('Отметить всё как прочитанное');});assert.equal(await page.getByLabel('Непрочитанное',{exact:true}).count(),0);assert.equal(rows.filter(r=>!r.read_at).length,0);assert.equal(attempts,3);assert(writes.every(path=>path==='notifications/read-all/'),'Bulk read must not invoke business actions');
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/lift-notifications-read-all-mobile.png',fullPage:true});assert.deepEqual(errors,[]);console.log('PASS read all: 320–2560, paginated/category inbox, scoped POST, busy state, retry, later arrivals remain unread, counters refresh and zero business actions');await browser.close();
 }catch(e){if(page&&!page.isClosed())await page.screenshot({path:'/tmp/lift-notifications-read-all-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
