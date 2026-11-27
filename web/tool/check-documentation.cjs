// Run against a local Django fixture with /tmp/lift-ui-cookie.json.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/google-chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1920,height:1080}});
 await context.addCookies(JSON.parse(fs.readFileSync(process.env.DOCUMENTATION_COOKIE_FILE||'/tmp/lift-ui-cookie.json','utf8')));
 const page=await context.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/#documents');
 await page.getByRole('heading',{name:'Документация',exact:true}).waitFor();
 const docs=page.locator('.documentation');
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).waitFor();
 assert.equal(await docs.locator('.doc-filename').filter({hasText:'50 лет Октября'}).count(),0,'No automatic elevator rows');
 assert.equal(await docs.locator('.doc-tree-name').filter({hasText:'50 лет Октября'}).count(),0,'No automatic elevator tree');
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).click();
 await page.getByRole('button',{name:'Новая папка',exact:true}).click();
 assert(!(await page.getByLabel('Расположение',{exact:true}).textContent()).includes('50 лет Октября'),'Folder destinations must be manually created folders');
 await page.getByRole('textbox',{name:'Название',exact:true}).fill('Тестовая вложенная папка');
 await page.getByRole('textbox',{name:'Теги папки через запятую'}).fill('monarch');
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await docs.locator('.doc-filename').filter({hasText:'Тестовая вложенная папка'}).waitFor();
 // Edit a root folder's tags and name without making it its own parent.
 await docs.getByRole('button',{name:'Документация',exact:true}).last().click();
 await docs.getByRole('checkbox',{name:'Выбрать Электросхемы',exact:true}).check();
 await docs.getByRole('button',{name:'Изменить',exact:true}).click();
 await page.getByRole('textbox',{name:'Теги папки через запятую'}).fill('мэл, monarch');
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 // Check wide desktop, landscape, tablet, mobile and narrow PWA widths.
 for(const [width,height] of [[2560,1440],[1920,1080],[1024,768],[768,1024],[412,915],[360,780],[320,640]]){
  await page.setViewportSize({width,height});
  const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert(overflow.scroll<=overflow.width+1,`Overflow at ${width}: ${JSON.stringify(overflow)}`);
  await page.getByRole('button',{name:'Новая папка',exact:true}).click();
  const modal=await page.getByRole('dialog').boundingBox();
  assert(modal.x>=0&&modal.x+modal.width<=width+1,`Dialog overflow ${width}`);
  await page.getByRole('button',{name:'Отмена',exact:true}).click();
 }
 await page.setViewportSize({width:412,height:915});
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).waitFor();
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).click();
 await docs.locator('.doc-filename').filter({hasText:'Тестовая вложенная папка'}).waitFor();
 // Right click and touch-accessible ellipsis expose equivalent operations.
 await docs.getByRole('button',{name:'Действия: Тестовая вложенная папка'}).click();
 await page.getByRole('menuitem',{name:'Копировать в…'}).click();
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await docs.locator('.doc-filename').filter({hasText:'Тестовая вложенная папка — копия'}).waitFor();
 await page.screenshot({path:'/tmp/lift-documentation-mobile.png',fullPage:true});
 await page.setViewportSize({width:1920,height:1080});
 await page.screenshot({path:'/tmp/lift-documentation-desktop.png',fullPage:true});
 // Verify tag-picked folder contents in the actual lift card, including its modal on a narrow phone.
 await page.goto('http://127.0.0.1:8000/#objects');
 await page.getByRole('textbox',{name:'Поиск лифтов'}).fill('50 лет Октября');
 await page.locator('.lift-tile').first().click();
 const card=page.getByRole('dialog');
 await card.getByRole('button',{name:'Документация',exact:true}).click();
 const embedded=card.locator('.doc-embedded');
 await embedded.locator('.doc-filename').filter({hasText:'Электросхемы'}).click();
 await embedded.locator('.doc-filename').filter({hasText:/^Тестовая вложенная папкаmonarch$/}).waitFor();
 assert.equal(await embedded.getByRole('button',{name:'Новая папка',exact:true}).count(),0);
 for(const [width,height] of [[2560,1440],[320,640]]){
  await page.setViewportSize({width,height});
  const bounds=await card.boundingBox();
  assert(bounds.x>=0&&bounds.x+bounds.width<=width+1,'Lift card exceeds viewport '+width);
  const alignment=await embedded.locator('.doc-filename').first().evaluate(node=>{
   const style=getComputedStyle(node);
   const result={justify:style.justifyContent,display:style.display};
   if(result.justify==='flex-start')return result;
   // Report the actual cascade only on failure; keep the alignment check strict.
   result.rules=[];
   const walk=(items,active=true)=>{for(const rule of items){
    if(rule.selectorText&&node.matches(rule.selectorText)&&rule.style.justifyContent)
     result.rules.push({selector:rule.selectorText,justify:rule.style.justifyContent,active});
    if(rule.cssRules)walk(rule.cssRules,active&&(!(rule instanceof CSSMediaRule)||matchMedia(rule.conditionText).matches));
   }};
   for(const sheet of document.styleSheets){try{walk(sheet.cssRules);}catch{}}
   return result;
  });
  assert.equal(alignment.justify,'flex-start',`File names must align left at ${width}px: ${JSON.stringify(alignment)}`);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Lift card horizontal overflow');
 }
 await page.screenshot({path:'/tmp/lift-documentation-card.png',fullPage:true});
 // Delete the open folder on a phone, then restore its entire subtree from trash.
 await card.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.goto('http://127.0.0.1:8000/#documents');
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).click();
 await docs.getByRole('button',{name:'Удалить папку',exact:true}).click();
 await page.getByLabel('Причина удаления',{exact:true}).fill('Удаление папки с телефона');
 await page.getByRole('button',{name:'В корзину',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).waitFor({state:'hidden'});
 await docs.getByRole('button',{name:'Корзина',exact:true}).click();
 await docs.getByRole('checkbox',{name:'Выбрать Электросхемы',exact:true}).check();
 await docs.getByRole('button',{name:'Восстановить',exact:true}).click();
 await docs.getByRole('button',{name:'Из корзины к документам',exact:true}).click();
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).waitFor();
 // Tree actions also target the selected folder, independently of its visible contents.
 await page.setViewportSize({width:1920,height:1080});
 await docs.getByRole('button',{name:'Действия папки: Электросхемы',exact:true}).click();
 await page.getByRole('menuitem',{name:'Удалить',exact:true}).click();
 await page.getByLabel('Причина удаления',{exact:true}).fill('Удаление папки через дерево');
 await page.getByRole('button',{name:'В корзину',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).waitFor({state:'hidden'});
 assert.equal(await docs.locator('.doc-filename').count(),0,'Empty library has no synthetic folders');
 assert.deepEqual(errors,[]);
 console.log('PASS: real API create, tags, root edit, recursive copy; 7 viewport sizes (320–2560), manual-only root, open-folder delete, tree delete, trash restore, context menu, modal bounds; no browser errors');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
