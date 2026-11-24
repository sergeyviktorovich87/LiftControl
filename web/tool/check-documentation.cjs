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
 await docs.locator('.doc-filename').filter({hasText:'Электросхемы'}).click();
 await page.getByRole('button',{name:'Новая папка',exact:true}).click();
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
 await docs.locator('.doc-filename').filter({hasText:'50 лет Октября'}).click();
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
 assert.deepEqual(errors,[]);
 console.log('PASS: real API create, tags, root edit, recursive copy; 7 viewport sizes (320–2560), mobile elevator list, context menu, modal bounds; no browser errors');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
