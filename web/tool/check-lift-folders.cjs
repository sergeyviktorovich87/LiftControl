const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.LIFT_FOLDERS_ORIGIN||'http://127.0.0.1:5173';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.LIFT_FOLDERS_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let page;
 try{
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU'});page=await context.newPage();const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 let role='ADMIN';
 const buildings=[{id:1,address:'Ленина, 12',street:'Ленина',house:'12',name:'Ленина, 12'},{id:2,address:'50 лет Октября, 265',street:'50 лет Октября',house:'265',name:'Дом'}];
 const elevators=[1,2,3].map(id=>({id,building:id===3?2:1,address:id===3?buildings[1].address:buildings[0].address,entrance:String(id),entrance_kind:'ENTRANCE',factory_number:'TEST-'+id,inventory_number:'INV-'+id,active:true,assigned_technician:1}));
 let folders=[{id:1,name:'Ленина, 12',parent_id:null,elevator_ids:[1,2],deleted_at:null,updated_at:'2026-11-25T00:00:00Z'},{id:2,name:'Освидетельствование',parent_id:1,elevator_ids:[],deleted_at:null,updated_at:'2026-11-25T00:00:00Z'}];
 let documents=[{id:11,title:'Прежний договор.pdf',elevator_id:1,folder:null,category:'CONTRACT',url:'/api/lift-documents/11/pdf/',updated_at:'2026-11-25T00:00:00Z'},{id:12,title:'Акт.pdf',folder:2,category:'INSPECTION',url:'/api/lift-documents/12/pdf/',updated_at:'2026-11-25T00:00:00Z'}];
 const effective=f=>{const ids=new Set(),seen=new Set();while(f&&!seen.has(f.id)){seen.add(f.id);if(f.deleted_at)return [];for(const id of f.elevator_ids)ids.add(id);f=folders.find(p=>p.id===f.parent_id);}return [...ids];};
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.replace('/api/','');let value=[];
  if(path==='me/')value={id:1,name:'Сергей',role,organization:'Мегаполис',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'fixture',technician:role==='MECHANIC'?1:null,can_manage:role==='ADMIN',can_manage_access:role==='ADMIN',can_manage_lift_documents:role==='ADMIN',can_create_ticket:true};
  else if(path==='buildings/')value=buildings;
  else if(path==='elevators/')value=elevators;
  else if(path==='technicians/')value=[{id:1,full_name:'Механик',active:true}];
  else if(path==='lift-document-folders/'){
   if(req.method()==='POST'){
    const body=req.postDataJSON();writes.push(body);
    if(body.action==='create'){const f={id:folders.length+1,parent_id:body.parent_id||null,elevator_ids:body.elevator_ids||[],name:body.name,deleted_at:null,updated_at:new Date().toISOString()};folders.push(f);value=f;}
    else if(body.action==='edit'){folders=folders.map(f=>f.id===body.id?{...f,...body}:f);value=folders.find(f=>f.id===body.id);}
    else if(body.action==='delete'||body.action==='restore'){for(const id of body.folders||[])folders=folders.map(f=>f.id===id?{...f,deleted_at:body.action==='delete'?'2026-11-25T01:00:00Z':null}:f);value={ok:true};}
   }else{
    const lift=Number(url.searchParams.get('elevator')),trash=url.searchParams.get('trash')==='1';
    const visible=folders.filter(f=>!!f.deleted_at===trash&&(!lift||effective(f).includes(lift))).map(f=>({...f,effective_elevator_ids:effective(f)}));
    value={folders:visible,documents:documents.filter(d=>!trash&&(!lift||visible.some(f=>f.id===d.folder)||!d.folder&&d.elevator_id===lift&&(role==='ADMIN'||d.category==='INSPECTION')))};
   }
  }else if(path==='lift-documents/'&&req.method()==='POST'){
   const raw=req.postData(),folder=Number(raw.match(/name="folder"\r\n\r\n(\d+)/)?.[1]),category=raw.match(/name="category"\r\n\r\n([^\r]+)/)?.[1];
   value={id:20,title:'Новый акт.pdf',folder,category,url:'/api/lift-documents/20/pdf/',updated_at:new Date().toISOString()};documents.push(value);writes.push({upload:true,folder,category});
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
 });
 await page.goto(origin+'/#lift-documents');const explorer=page.locator('.legal-explorer');await explorer.getByRole('heading',{name:'Документы',exact:true}).waitFor();
 await explorer.locator('.doc-filename').filter({hasText:'Ленина, 12'}).click();
 await explorer.getByRole('button',{name:'Настройки папки',exact:true}).click();let dialog=page.getByRole('dialog');await dialog.waitFor();
 assert.equal(await dialog.getByLabel('Теги папки через запятую').count(),0);
 const layout=async label=>{
  const data=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,outside:[...document.querySelectorAll('.legal-explorer input,.legal-explorer select,.legal-explorer button')].filter(e=>e.getClientRects().length).filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(e=>e.getAttribute('aria-label')||e.textContent)}));
  assert(!data.overflow&&!data.outside.length,label+': '+JSON.stringify(data));
 };
 for(const width of [2560,1440,1024,768,540,412,360,320]){await page.setViewportSize({width,height:915});await layout('folder editor '+width);}
 await page.setViewportSize({width:412,height:915});await page.screenshot({path:'/tmp/lift-legal-folders-mobile.png',fullPage:true});
 await dialog.getByLabel('Подъезд 2 · TEST-2',{exact:true}).uncheck();
 await dialog.getByRole('button',{name:'› 50 лет Октября, 265',exact:true}).click();
 await dialog.getByLabel('Подъезд 3 · TEST-3',{exact:true}).check();
 await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();await dialog.waitFor({state:'hidden'});
 assert(writes.some(w=>w.action==='edit'&&w.elevator_ids.includes(1)&&w.elevator_ids.includes(3)&&!w.elevator_ids.includes(2)));
 await explorer.getByRole('button',{name:'Новая папка',exact:true}).click();dialog=page.getByRole('dialog');await dialog.getByLabel('Название',{exact:true}).fill('Дополнительные акты');
 assert.equal(await dialog.getByLabel('Подъезд 1 · TEST-1 · унаследовано',{exact:true}).isDisabled(),true);
 await dialog.getByRole('button',{name:'Сохранить',exact:true}).click();await dialog.waitFor({state:'hidden'});
 await explorer.locator('.doc-filename').filter({hasText:'Дополнительные акты'}).click();
 await explorer.getByLabel('Тип загружаемых документов').selectOption('INSPECTION');
 await explorer.locator('input[type=file]').setInputFiles({name:'Новый акт.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.7\nfixture')});
 await explorer.locator('.doc-filename').filter({hasText:'Новый акт.pdf'}).waitFor();
 assert(writes.some(w=>w.upload&&w.folder===3&&w.category==='INSPECTION'));
 await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:'/tmp/lift-legal-folders-desktop.png',fullPage:true});
 role='MECHANIC';await page.goto(origin+'/#objects');await page.getByRole('textbox',{name:'Поиск лифтов',exact:true}).fill('TEST-1');await page.getByRole('button').filter({hasText:'TEST-1'}).click();
 const card=page.getByRole('dialog');await card.waitFor();await card.locator('.tabs').getByRole('button',{name:'Документы',exact:true}).click();
 const attached=card.locator('.legal-explorer');await attached.locator('.doc-filename').filter({hasText:'Ленина, 12'}).click();
 await attached.locator('.doc-filename').filter({hasText:'Дополнительные акты'}).click();await attached.locator('.doc-filename').filter({hasText:'Новый акт.pdf'}).waitFor();
 assert.equal(await attached.getByRole('button',{name:'Новая папка',exact:true}).count(),0);assert.equal(await attached.getByRole('button',{name:'Удалить',exact:true}).count(),0);
 assert.equal(await attached.getByText('Прежний договор.pdf',{exact:true}).count(),0);
 await page.setViewportSize({width:320,height:740});await layout('read-only lift card 320');
 assert.deepEqual(errors,[]);console.log('PASS legal folders: explicit multi-lift picker, inheritance, upload, read-only card, no tags, 320–2560px');
 await browser.close();
 }catch(e){if(page&&!page.isClosed())await page.screenshot({path:'/tmp/lift-legal-folders-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
