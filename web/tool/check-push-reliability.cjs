const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PUSH_CHROME||'/usr/bin/chromium',args:['--no-sandbox']});let page;
 try{
  const context=await browser.newContext({viewport:{width:412,height:915}});
  await context.addInitScript(()=>{
   const key=new Uint8Array(65);key[0]=4;const publicKey=btoa(String.fromCharCode(...key)).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');
   window.__pushFixture={publicKey,renewed:0,unsubscribed:0,current:null};
   const make=applicationServerKey=>({endpoint:'https://fcm.googleapis.com/fcm/send/browser-fixture',expirationTime:null,options:{applicationServerKey},toJSON(){return {endpoint:this.endpoint,keys:{p256dh:'abcdefghijklmnop',auth:'abcdefghijklmnop'}};},async unsubscribe(){window.__pushFixture.unsubscribed++;window.__pushFixture.current=null;return true;}});
   window.__pushFixture.current=make(key.buffer);
   const registration={active:{},addEventListener(){},removeEventListener(){},async update(){},async showNotification(){},pushManager:{async getSubscription(){return window.__pushFixture.current;},async subscribe(options){window.__pushFixture.renewed++;return window.__pushFixture.current=make(options.applicationServerKey.buffer||options.applicationServerKey);}}};
   Object.defineProperty(navigator,'serviceWorker',{configurable:true,value:{controller:null,ready:Promise.resolve(registration),async register(){return registration;},async getRegistration(){return registration;},addEventListener(){},removeEventListener(){}}});
   Object.defineProperty(window,'PushManager',{value:class PushManager{},configurable:true});
   Object.defineProperty(Notification,'permission',{get:()=> 'granted',configurable:true});Notification.requestPermission=async()=> 'granted';
  });
  page=await context.newPage();let revision=1,signals=0,revisionRequests=0;const subscriptions=[],probes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const req=route.request(),path=new URL(req.url()).pathname.replace('/api/','');let value=[];
   if(path==='me/')value={id:1,name:'Сергей',role:'ADMIN',organization:'Эверест',organization_id:1,organizations:[],timezone:'Asia/Chita',csrf:'test',can_manage:true,can_manage_access:true,can_create_ticket:true,notification_live_api:1,notification_counts_api:1,notification_preferences_api:1};
   else if(path==='notifications/revision/'){revisionRequests++;value={revision:String(revision)};}
   else if(path==='notifications/counts/')value={unread:0,sections:{}};
   else if(path==='push/public-key/')value={enabled:true,public_key:await page.evaluate(()=>window.__pushFixture.publicKey)};
   else if(path==='push/subscription/'){if(req.method()==='POST'){subscriptions.push(req.postDataJSON());assert.equal(subscriptions.at(-1).expected_user,1);}value={ok:true};}
   else if(path==='push/status/')value={devices:1,last_24h:{DISPLAYED:2}};
   else if(path==='push/test/'){probes.push(req.postDataJSON());value={id:7};}
   else if(path==='push/test/7/')value={states:['DISPLAYED']};
   else if(path==='notifications/preferences/')value={ordinary:true,urgent:true,entrapment:true,updates:true,tasks:true,only_mine:false,quiet_enabled:false,quiet_start:'22:00',quiet_end:'08:00',muted_weekdays:[]};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto((process.env.PUSH_ORIGIN||'http://127.0.0.1:5173')+'/#home');await page.getByRole('heading',{name:'Главная',exact:true}).waitFor();
  await page.waitForFunction(()=>window.localStorage.getItem('liftcontrol-push-enabled:1')==='1');assert(subscriptions.length>0,'Existing subscription must resync on app open without visiting settings');
  await page.waitForResponse(response=>response.url().includes('/api/notifications/revision/'));
  await page.evaluate(()=>{window.__liveSignals=0;window.addEventListener('liftcontrol-notifications-changed',()=>window.__liveSignals++);});
  revision=2;const started=Date.now();await page.waitForFunction(()=>window.__liveSignals>0,{},{timeout:6000});assert(Date.now()-started<6000,'New events must wake the open PWA promptly');assert(revisionRequests>=2);
  await page.evaluate(async()=>{const mod=await import('/src/pushSubscription.js');window.__pushFixture.current.options.applicationServerKey=new Uint8Array([1,2]).buffer;await mod.syncPush({id:1,organization_id:1});});assert.equal(await page.evaluate(()=>window.__pushFixture.renewed),1,'VAPID rotation renews an incompatible browser subscription');
  await page.evaluate(()=>location.hash='settings/notifications');await page.getByRole('heading',{name:'Включение уведомлений',exact:true}).waitFor();
  const controls=page.locator('.setting-row').filter({has:page.getByRole('heading',{name:'Включение уведомлений',exact:true})});await controls.getByRole('button',{name:'Проверить доставку с сервера',exact:true}).click();await controls.getByText('Браузер подтвердил показ уведомления, отправленного сервером.',{exact:true}).waitFor();assert.equal(probes.length,1);assert(probes[0].endpoint.includes('browser-fixture'));
  await controls.getByRole('button',{name:'Отключить уведомления',exact:true}).click();await controls.getByText('Уведомления отключены на этом устройстве.',{exact:true}).waitFor();const before=subscriptions.length;
  const disabled=await page.evaluate(async()=>{window.dispatchEvent(new Event('online'));const mod=await import('/src/pushSubscription.js');return mod.syncPush({id:1,organization_id:1});});assert.equal(disabled,false);assert.equal(subscriptions.length,before,'Reconnect must respect a deliberate opt-out');
  assert.deepEqual(errors,[]);console.log('PASS WebPush: automatic account-bound re-registration, VAPID rotation, scoped server probe and persistent opt-out, prompt live signal');await browser.close();
 }catch(e){if(page&&!page.isClosed())await page.screenshot({path:'/tmp/lift-push-reliability-failed.png',fullPage:true});await browser.close();throw e;}
})().catch(e=>{console.error(e);process.exit(1);});
