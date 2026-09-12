/* UI ownership and navigation checks. API responses are isolated in the browser;
   the running town is only read to obtain a representative v4 snapshot.
   Run: node tests/ui_page_purposes.cjs [http://127.0.0.1:3003] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.argv[2]||'http://127.0.0.1:3003';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1366,height:768}});
 const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const s=await response.json();assert.equal(s.modelVersion,4);
 s.cash=100000;s.breakfastEvent={status:'new',reward:5};s.gateOpen=false;s.checklist.quiz=false;
 s.buildings.forEach(b=>Object.values(b.upgrades).forEach(u=>{u.canBuy=true;u.cost=100;u.why='';}));
 s.contracts.offers.forEach(o=>{o.canFulfill=true;o.why='';o.requirements.forEach(g=>g.owned=g.quantity);});
 const quiz=JSON.parse(fs.readFileSync('config/quiz.json','utf8'));
 let serial=0;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==base)return route.abort();
  if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
  const endpoint=url.pathname.slice('/api/game/econ/'.length);
  if(endpoint==='quiz'&&route.request().method()==='GET')return route.fulfill({json:quiz});
  if(route.request().method()==='POST'&&endpoint!=='login'){
   const data=route.request().postDataJSON();calls.push({endpoint,data});delete s.receipt;
   const b=s.buildings.find(b=>b.slot===data.slot);
   if(endpoint==='upgrade'){b.upgrades[data.kind].level++;s.receipt={kind:'upgrade'};}
   if(endpoint==='reserve')b.reserve=data.reserve;
   if(endpoint==='processing')b.processing=data.enabled;
   if(endpoint==='orders/commit')s.contracts.offers[data.offerIndex].committed=data.committed;
   if(endpoint==='orders/fulfill'||endpoint==='orders/replace'){
    assert.equal(data.orderId,s.contracts.offers[data.offerIndex].id);
    s.contracts.offers[data.offerIndex].id='ui-order-'+(++serial);s.receipt={kind:'order',reward:50,materials:1};
   }
   if(endpoint==='sell'){b.clearableQuantity=0;s.receipt={kind:'sell',net:100};}
   if(endpoint==='quiz'){assert.equal(data.answers.length,quiz.questions.length);s.checklist.quiz=true;s.quiz={passed:true};}
   if(endpoint==='keep')s.keepPercent=data.percent;
  }
  return route.fulfill({json:s});
 });
 const pages={buildings:['expand','reserve','sell','processing','upgrade:production','upgrade:sales','upgrade:storage'],warehouse:['reserve','upgrade:storage'],marketplace:['fulfill','replace','commit','sell','upgrade:sales'],'advanced-hq':['processing','upgrade:production'],license:[]};
 async function go(file){await page.goto(base+'/'+file+'.html');await page.locator('.game-wallet,.game-resources').waitFor();if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();}
 async function act(action){const before=calls.length;await page.locator('[data-econ-action="'+action+'"]').click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));assert.equal(calls.length,before+1);}
 for(const [file,allowed] of Object.entries(pages)){
  await go(file);
  const actions=await page.locator('.game-workspace [data-econ-action]').evaluateAll(es=>es.map(e=>e.dataset.econAction));
  for(const action of actions){const parts=action.split(':');const family=parts[0]==='upgrade'?'upgrade:'+parts[2]:parts[0];assert(allowed.includes(family),file+' contains misplaced '+action);}
  assert.equal(await page.locator('[data-game-deliveries]').count(),0);
 }
 await go('buildings');assert.equal(await page.locator('#econ-building [data-econ-action^="reserve:"]').count(),0);
 const next=s.frontier[s.frontier.length-1];await page.selectOption('#game-expansion-choice',String(next.tier));
 assert.equal(await page.locator('.game-next-art').getAttribute('data-preview-business'),next.id);
 assert((await page.locator('.game-next-art .k-art').evaluate(e=>getComputedStyle(e).filter)).includes('grayscale(1)'));
 await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('.game-next-art').getAttribute('data-preview-business'),next.id);
 while(await page.locator('.game-pager[data-page="Buildings"] button:first-child:not(:disabled)').count())await page.locator('.game-pager[data-page="Buildings"] button:first-child').click();
 await page.locator('[data-select-building="2"]').click();
 await page.locator('[data-game-breakfast]').click();assert(await page.locator('#game-breakfast').evaluate(e=>e.open));await page.keyboard.press('Escape');assert(await page.locator('[data-game-breakfast]').evaluate(e=>e===document.activeElement));
 for(const [file,kind] of [['warehouse','storage'],['marketplace','sales'],['advanced-hq','production']]){
  await go(file);assert.equal(await page.locator('#game-business-choice').inputValue(),'2');const level=s.buildings[2].upgrades[kind].level;await act('upgrade:2:'+kind);assert.equal(s.buildings[2].upgrades[kind].level,level+1);
 }
 await act('processing:2:'+String(s.buildings[2].processing===false));
 await go('warehouse');await act('reserve:2:'+String(!s.buildings[2].reserve));
 await go('marketplace');await act('fulfill:0:'+s.contracts.offers[0].id);await act('replace:1:'+s.contracts.offers[1].id);
 s.buildings[2].clearableQuantity=10;s.buildings[2].clearStockValue=100;await page.evaluate(()=>window.YomamaEcon.refresh());await act('sell:2');
 await page.selectOption('#game-business-choice','0');await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('#game-business-choice').inputValue(),'0');
 await go('advanced-hq');assert.equal(await page.locator('.game-processing').count(),0);assert(await page.getByText('No ingredients needed').count());
 await go('license');assert.equal(await page.locator('.game-invest').count(),0);
 for(let i=0;i<quiz.questions.length;i++){
  await page.locator('input[name="q'+i+'"][value="1"]').check();await page.evaluate(()=>window.YomamaEcon.refresh());assert(await page.locator('input[name="q'+i+'"][value="1"]').isChecked());
  if(i<quiz.questions.length-1)await page.locator('[data-quiz-step="1"]').click();
 }
 await act('quiz');s.gateOpen=true;await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('.game-invest').count(),1);assert.equal(await page.locator('#econ-keep-range').count(),0);assert(await page.getByText('Your trading desk uses a separate practice portfolio. Your town keeps its cash.').count());
 const sizes=[];
 for(const width of [1366,1024,768,390]){
  await page.setViewportSize({width,height:width===390?844:768});
  for(const file of Object.keys(pages)){
   await go(file);assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),file+' overflow '+width);
   const bottom=await page.locator('.game-workspace').evaluate(e=>e.getBoundingClientRect().bottom);sizes.push({file,width,bottom});
   if(width===1366)assert(bottom<=768,file+' requires desktop scrolling: '+bottom);
  }
 }
 s.gateOpen=false;s.checklist.quiz=false;
 await go('license');assert.equal(await page.locator('.game-view-tabs [role=tab]').count(),2);
 s.buildings=s.buildings.slice(0,1);s.buildingsOwned=1;s.board=s.board.filter(g=>g.slot===0);
 for(const file of ['buildings','warehouse','marketplace','advanced-hq']){
  await go(file);assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),'starter '+file+' overflow');
  if(file==='buildings')assert.equal(await page.locator('[data-select-building]').count(),1);
  else assert.equal(await page.locator('#game-business-choice').inputValue(),'0');
 }
 assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'passed',actions:calls.length,sizes},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
