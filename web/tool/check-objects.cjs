const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/google-chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.addCookies(JSON.parse(fs.readFileSync('/tmp/lift-objects-cookie.json')));
 const fixture=JSON.parse(fs.readFileSync('/tmp/lift-objects-fixture.json'));const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8000/#objects');await page.getByRole('heading',{name:'Объекты',exact:true}).waitFor();const objects=page.locator('.objects-page');
 await objects.getByRole('textbox',{name:'Поиск лифтов'}).fill('50 лет Октября');await objects.locator('.object-lift-name').filter({hasText:'OBJ-A'}).waitFor();assert.equal(await objects.locator('.object-lift-name').filter({hasText:'OBJ-B'}).count(),0);assert.equal((await objects.locator('.object-lift-state').first().innerText()).trim(),'Застревание');
 for(const [width,height] of [[2560,1440],[1920,1080],[1024,768],[900,900],[860,900],[768,1024],[412,915],[360,780],[320,640]]){
  await page.setViewportSize({width,height});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Object list overflow '+width);
  const add=objects.getByRole('button',{name:'Добавить',exact:true});await add.click();await objects.getByRole('menuitem',{name:'Добавить дом',exact:true}).waitFor();await page.keyboard.press('Escape');assert(await add.evaluate(node=>node===document.activeElement),'Add menu restores keyboard focus');
  await objects.getByRole('button',{name:'Действия дома: 50 лет Октября, 265/2',exact:true}).click();
  const menu=objects.getByRole('menu');const bounds=await menu.boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=width+1,'Menu overflow '+width);
  await menu.getByRole('menuitem',{name:'Добавить лифт',exact:true}).click();const form=page.getByRole('dialog');assert.equal(await form.getByLabel('Дом',{exact:true}).inputValue(),'50 лет Октября, 265/2');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Prefilled editor overflow '+width);await form.getByRole('button',{name:'Закрыть',exact:true}).click();
 }
 await page.getByRole('button',{name:'Фильтры объектов',exact:true}).click();await page.getByLabel('Показывать архив',{exact:true}).check();await objects.locator('.object-lift-name').filter({hasText:'OBJ-B'}).waitFor();
 await objects.getByRole('textbox',{name:'Поиск лифтов'}).fill('Шатравка');assert.equal(await objects.locator('.object-lift-name').count(),1);await objects.getByRole('textbox',{name:'Поиск лифтов'}).fill('50 лет Октября');
 await page.screenshot({path:'/tmp/lift-objects-mobile.png',fullPage:true});await page.setViewportSize({width:1920,height:1080});await page.screenshot({path:'/tmp/lift-objects-desktop.png',fullPage:true});
 await page.setViewportSize({width:360,height:780});await objects.getByRole('button',{name:'Действия лифта: OBJ-B',exact:true}).click();await objects.getByRole('menuitem',{name:'Удалить лифт',exact:true}).click();
 const removal=page.getByRole('dialog',{name:'Удалить лифт',exact:true});await removal.getByLabel('Причина удаления',{exact:true}).fill('Удаление архивного тестового лифта');assert(await removal.getByRole('button',{name:'Удалить лифт',exact:true}).isDisabled());await removal.getByLabel('Подтверждаю удаление лифта',{exact:true}).check();await removal.getByRole('button',{name:'Удалить лифт',exact:true}).click();await removal.waitFor({state:'hidden'});
 const removed=await (await page.request.get('http://127.0.0.1:8000/api/elevators/'+fixture.archived+'/')).json();assert(removed.deleted_at&&!removed.active,'Archived removal is persistent and retains history retrieval');
 await objects.getByRole('button',{name:'Действия дома: 50 лет Октября, 265/2',exact:true}).click();await objects.getByRole('menuitem',{name:'Удалить дом',exact:true}).click();const homeRemoval=page.getByRole('dialog',{name:'Удалить дом',exact:true});await homeRemoval.getByLabel('Причина удаления',{exact:true}).fill('Удаление дома с сохранением истории');await homeRemoval.getByLabel('Подтверждаю удаление дома и всех его лифтов',{exact:true}).check();await homeRemoval.getByRole('button',{name:'Удалить дом',exact:true}).click();await homeRemoval.waitFor({state:'hidden'});
 assert.equal(await objects.locator('.object-house').filter({hasText:'265/2'}).count(),0);
 const ticket=await (await page.request.get('http://127.0.0.1:8000/api/tickets/'+fixture.ticket+'/')).json();assert.equal(ticket.status,'NEW');assert.equal(ticket.address,'50 лет Октября, 265/2');assert.equal(ticket.elevator,fixture.lift);
 assert.deepEqual(errors,[]);console.log('PASS objects: 320–2560 layouts, house menus, prefilled add lift, mechanic search, archive visibility, archived lift deletion, house deletion and retained open-ticket history');
 }catch(e){await page.screenshot({path:'/tmp/lift-objects-failed.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
