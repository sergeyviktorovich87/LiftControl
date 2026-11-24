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
