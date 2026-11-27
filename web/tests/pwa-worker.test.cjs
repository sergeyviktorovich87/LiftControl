const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../backend/static/web/service-worker.js'),'utf8');
function worker(fetch){
 const handlers={};
 vm.runInNewContext(source,{self:{location:{origin:'https://lift.example'},addEventListener:(name,fn)=>handlers[name]=fn},URL,Response,fetch});
 return handlers;
}
function dispatch(handlers,pathname,method='GET',mode='navigate',origin='https://lift.example'){
 let promise;
 handlers.fetch({request:{url:origin+pathname,method,mode},respondWith:value=>promise=value});
 return promise;
}
test('offline home displays a non-cached offline page',async()=>{
 const handlers=worker(async()=>{throw Error('offline');});
 const response=await dispatch(handlers,'/?organization=5');
 assert.equal(response.status,503);
 assert.equal(response.headers.get('cache-control'),'no-store');
 assert.match(await response.text(),/Нет связи с сервером/);
 assert.equal(typeof handlers.push,'function');
});
test('online navigation uses the network and preserves server response',async()=>{
 const handlers=worker(async(request,options)=>{assert.equal(options.cache,'no-store');return new Response('fresh',{status:200});});
 assert.equal(await (await dispatch(handlers,'/')).text(),'fresh');
});
test('API, files, cross-origin and mutations are not intercepted',()=>{
 const handlers=worker(()=>{throw Error('unexpected fetch');});
 for(const args of [['/api/tickets/'],['/media/x.pdf'],['/static/web/assets/app.js'],['/login/','POST'],['/','GET','cors'],['/','GET','navigate','https://other.example']]){
  assert.equal(dispatch(handlers,...args),undefined);
 }
});

function pushWorker(network,{failShow=0}={}){
 const handlers={},shown=[],receipts=[],closed=[],opened=[];let calls=0;
 const context={self:{location:{origin:'https://lift.example'},registration:{showNotification:async(title,options)=>{calls++;if(calls<=failShow)throw Error('OS temporarily unavailable');shown.push({title,...options});},getNotifications:async()=>[{close:()=>closed.push(true)}]},addEventListener:(name,fn)=>handlers[name]=fn},clients:{matchAll:async()=>[],openWindow:async url=>opened.push(url)},URL,Response,AbortController,atob,setTimeout,clearTimeout,fetch:async(url,options)=>{if(url==='/api/push/received/'){receipts.push(JSON.parse(options.body));return new Response('{}');}return network(url,options);}};
 vm.runInNewContext(source,context);
 const push=async data=>{let done;handlers.push({data:{json:()=>data},waitUntil:value=>done=value});return done;};
 return {push,handlers,shown,receipts,closed,opened,get calls(){return calls;}};
}
const pushData={organization_id:1,ticket_id:4,event_id:12,status:'NEW',kind:'created',priority:'NORMAL',title:'Новая заявка',body:'Закрытое описание',receipt_token:'signed-token'};
test('a received push is shown and confirmed even when IndexedDB is unavailable',async()=>{
 const p=pushWorker(async()=>new Response(JSON.stringify({status:'NEW',priority:'NORMAL'})));
 await p.push(pushData);assert.equal(p.shown.length,1);assert.equal(p.shown[0].body,'Закрытое описание');assert.equal(p.receipts.length,1);
 await p.push(pushData);assert.equal(p.shown.length,1);assert.equal(p.receipts.length,2,'Replays can recover a lost receipt without a second notification');
});
test('network failure produces a generic notification without exposing payload content',async()=>{
 const p=pushWorker(async()=>{throw Error('offline');});await p.push(pushData);assert.equal(p.shown.length,1);assert(!p.shown[0].body.includes('Закрытое'));assert.equal(p.shown[0].title,'Лифт Контроль');
});
test('explicit authentication failure and stale state never display private content',async()=>{
 const unauthorized=pushWorker(async()=>new Response('{}',{status:403}));await unauthorized.push(pushData);assert.equal(unauthorized.shown.length,0);
 const stale=pushWorker(async()=>new Response(JSON.stringify({status:'DONE'})));await stale.push(pushData);assert.equal(stale.shown.length,0);assert.equal(stale.closed.length,1);
});
test('dedup cursor is committed after successful display, not before',async()=>{
 const p=pushWorker(async()=>new Response(JSON.stringify({status:'NEW'})),{failShow:1});await assert.rejects(p.push(pushData));assert.equal(p.receipts.length,0);await p.push(pushData);assert.equal(p.shown.length,1);assert.equal(p.calls,2);
});
test('concurrent duplicate events produce one notification',async()=>{
 const p=pushWorker(async()=>new Response(JSON.stringify({status:'NEW'})));await Promise.all([p.push(pushData),p.push(pushData)]);assert.equal(p.shown.length,1);
});
test('chat and commissioning inbox pushes use authenticated current content',async()=>{
 const p=pushWorker(async url=>{assert.match(url,/\/api\/push\/inbox\/18/);return new Response(JSON.stringify({id:18,read:false,title:'Чат наладчиков',body:'Новая запись',url:'/?organization=1#commissioning-chat'}));});await p.push({target:'inbox',organization_id:1,inbox_id:18,event_id:18});assert.equal(p.shown[0].title,'Чат наладчиков');assert.equal(p.shown[0].data.url,'/?organization=1#commissioning-chat');
});
test('notification click cannot navigate to another origin',async()=>{
 const p=pushWorker(async()=>new Response('{}'));let done;p.handlers.notificationclick({notification:{close(){},data:{url:'https://evil.example/'}},waitUntil:value=>done=value});await done;assert.deepEqual(p.opened,['/#notifications']);
});

test('subscription rotation re-registers with current account and CSRF while app is closed',async()=>{
 let saved;const publicKey=Buffer.alloc(65,4).toString('base64url');
 const p=pushWorker(async(url,options)=>{if(url==='/api/push/public-key/')return new Response(JSON.stringify({enabled:true,public_key:publicKey}));if(url==='/api/me/')return new Response(JSON.stringify({id:3,organization_id:2,csrf:'csrf-current'}));if(url==='/api/push/subscription/'){saved={body:JSON.parse(options.body),headers:options.headers};return new Response('{}');}throw Error('unexpected path');});
 let done;p.handlers.pushsubscriptionchange({newSubscription:{toJSON:()=>({endpoint:'https://fcm.googleapis.com/fcm/send/new'})},waitUntil:value=>done=value});await done;assert.equal(saved.body.expected_user,3);assert.equal(saved.headers['X-CSRFToken'],'csrf-current');assert.equal(saved.headers['X-Organization-ID'],'2');
});
