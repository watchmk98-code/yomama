/* Selected-business live data and responsive fit. Every API response is
   intercepted; no purchase or other mutation can reach the preview save. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.argv[2]||'http://127.0.0.1:3094';
const clone=value=>structuredClone(value);
const number=value=>Number(value).toLocaleString('en-US',{maximumFractionDigits:1});
const rate=value=>Number(value).toLocaleString('en-US',{maximumFractionDigits:2});
const output=path.resolve('.checks/business-live');

(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok,'Use a signed-in local preview');
 const metadata=await response.json();assert.equal(metadata.modelVersion,4);
 assert(metadata.buildings.length>=2,'Use the full-town preview for selection checks');
 let state=clone(metadata),stateReads=0,failState=false;
 const errors=[],mutations=[],sizes=[],fitProblems=[];
 state.paused=false;state.overnightReport=null;state.receipt=null;state.classCompetition=false;
 state.buildings.forEach((b,index)=>{
  b.incomePerMinute=120.04+index;b.potentialIncomePerMinute=b.incomePerMinute;
  b.productionPerMinute=654321;b.salesPerMinute=543210;
  b.productionCapacityPerMinute=50+index;b.customerCapacityPerMinute=40+index;
  b.activity={windowSeconds:60,observedSeconds:60,producedUnits:12+index,soldUnits:7+index};
  b.earnings={...b.earnings,operatingIncome:20+index,bySource:{...b.earnings.bySource,walkIns:15,regularBuyers:5+index}};
  b.stored=35+index;b.capacity=360;b.reserve=false;b.processing=true;b.status='Working';
 });
 const updateTownIncome=()=>{
  state.incomePerMinute=state.buildings.reduce((total,b)=>total+b.incomePerMinute,0);state.potentialIncomePerMinute=state.incomePerMinute;
  state.buildings.forEach((b,index)=>{
   const sales=b.earnings.operatingIncome,costs=3+index,profit=sales-costs;
   b.operatingStatement={...b.operatingStatement,enabled:true,sales,costs,profit,margin:sales>0?profit/sales*100:null};
  });
  state.operatingStatement={...state.operatingStatement,enabled:true,sales:state.buildings.reduce((total,b)=>total+b.operatingStatement.sales,0)};
 };
 updateTownIncome();
 const farm=state.buildings[0],other=state.buildings[1];
 const browser=await chromium.launch({headless:true});
 try{
  fs.mkdirSync(output,{recursive:true});
  const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'no-preference'});
  page.setDefaultTimeout(10000);
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/game/'))return route.continue();
   try{
    if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
    if(url.pathname==='/api/game/state')return route.fulfill({json:state});
    assert(url.pathname.startsWith('/api/game/econ/'),'Unexpected API '+url.pathname);
    const endpoint=url.pathname.slice('/api/game/econ/'.length);
    if(endpoint==='quiz')return route.fulfill({json:{questions:[],passMark:4}});
    if(request.method()!=='GET'&&endpoint!=='login'){
     mutations.push(endpoint);assert.fail('Live display must not mutate a save: '+endpoint);
    }
    if(endpoint==='state'){
     stateReads++;
     if(failState)return route.fulfill({status:503,json:{error:'Simulated preview connection interruption'}});
    }
    return route.fulfill({json:state});
   }catch(error){errors.push(error.stack||String(error));return route.fulfill({status:500,json:{error:'Isolated live-panel check rejected the request'}});}
  });
  const panel=page.locator('.game-site.game-business-live');
  const metric=name=>panel.locator('[data-business-metric="'+name+'"] .game-live-value');
  const stock=page.locator('.game-building-stock');
  async function refresh(){updateTownIncome();await page.evaluate(()=>window.YomamaEcon.refresh());await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());}
  async function select(slot){
   const picker=page.locator('.game-fit-picker');
   if(await picker.isVisible())await picker.selectOption(String(slot));
   else{
    const button=page.locator('[data-select-building="'+slot+'"]');
    for(let attempt=0;!await button.isVisible()&&attempt<20;attempt++){
     const first=Number(await page.locator('.game-roster-list [data-select-building]:visible').first().getAttribute('data-select-building'));
     await page.getByRole('button',{name:(slot<first?'Previous':'Next')+' buildings page',exact:true}).click();
    }
    await button.click();
   }
  }
  async function values(b,label){
   assert.equal(await panel.locator('[data-business-metric]').count(),6,label+' displays four finance metrics and two capacity metrics');
   assert.equal((await metric('income').textContent()).trim(),rate(b.operatingStatement.sales)+' YM',label+' actual customer sales');
   assert.equal((await metric('cost').textContent()).trim(),'−'+rate(b.operatingStatement.costs)+' YM',label+' actual costs');
   assert.equal((await metric('profit').textContent()).trim(),rate(b.operatingStatement.profit)+' YM',label+' actual profit');
   assert.equal((await page.locator('[data-build-metric="income"] dd').textContent()).replace(/\s+/g,''),rate(state.operatingStatement.sales)+'YM',label+' town customer sales');
   assert.equal((await metric('produced').textContent()).trim(),rate(b.productionCapacityPerMinute),label+' current production capacity');
   assert.equal((await metric('sold').textContent()).trim(),rate(b.customerCapacityPerMinute),label+' current customer demand');
   assert.equal(await panel.locator('.game-live-rate').count(),0,label+' omits recorded-history captions');
   assert.equal(await panel.locator('[data-business-metric="stock"]').count(),0,label+' stock stays in its separate table');
   assert.deepEqual(await stock.locator('[data-stock-count]').allTextContents(),b.goods.map(g=>number(g.quantity)+' / '+number(g.capacity || 0)),label+' actual stock per product');
   assert.equal(await panel.locator('.game-production-loop,.game-income-detail').count(),0,label+' does not retain tutorial or forecast');
   assert.equal(await panel.locator('.k-art img').count(),1,label+' retains upgraded business sprite');
  }
  await page.goto(base+'/buildings.html');await panel.waitFor();await select(0);
  await values(farm,'Initial');
  assert.equal(await panel.locator('.game-live-title').count(),0,'Cashflow heading is removed');
  assert.doesNotMatch(await panel.locator('.game-live-heading').textContent(),/Customer cashflow|last 60 game seconds|AUTO-SALES/);
  assert.equal(await panel.locator('.game-building-stock').count(),1,'Stock occupies the desktop space below metrics');
  assert.equal(await page.locator('.game-business-shipment,.game-business-limit').count(),0,'Obsolete shipment and status sections are removed');
  assert.deepEqual(await stock.locator('[data-stock-good]').evaluateAll(rows=>rows.map(row=>row.dataset.stockGood)),farm.goods.map(g=>g.goodId),'Only selected-business goods appear');
  state.paused=true;await refresh();
  assert.equal(await panel.locator('[data-business-feed]').getAttribute('data-state'),'paused');
  assert.match(await panel.locator('.game-panel-head').textContent(),/Paused/);
  await values(farm,'Class pause retains current rates and actual totals');
  state.paused=false;await refresh();
  assert.equal(await panel.locator('[data-business-feed]').getAttribute('data-state'),'live');

  // Offline data remain readable; reconnect must fetch and show current totals.
  failState=true;await refresh();
  assert.equal(await panel.locator('[data-business-feed]').getAttribute('data-state'),'offline');
  await values(farm,'Disconnected snapshot');
  failState=false;farm.stored++;
  await refresh();
  assert.equal(await panel.locator('[data-business-feed]').getAttribute('data-state'),'live');
  assert.doesNotMatch(await page.locator('[data-econ-status]').first().textContent(),/Connection lost/,'Recovery clears the connection error');
  await values(farm,'Reconnect refreshes totals');

  await page.evaluate(()=>{
   Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
   document.dispatchEvent(new Event('visibilitychange'));
  });
  const readsBeforeVisible=stateReads;
  farm.earnings.operatingIncome++;updateTownIncome();
  await page.evaluate(()=>{
   Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
   document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForFunction(sales=>document.querySelector('[data-business-metric="income"] .game-live-value')?.textContent.trim()===sales,rate(farm.operatingStatement.sales)+' YM');
  assert(stateReads>readsBeforeVisible,'Returning to the visible page fetches a fresh snapshot');
  await values(farm,'Visibility recovery');
  await page.evaluate(()=>{delete document.visibilityState;});

  // These changes arrive from the actual poll interval, without an explicit refresh.
  const readsBefore=stateReads;
  Object.assign(farm,{incomePerMinute:120.05,potentialIncomePerMinute:120.05,stored:41,productionCapacityPerMinute:farm.productionCapacityPerMinute+1.25,customerCapacityPerMinute:farm.customerCapacityPerMinute+1.5});
  farm.earnings.operatingIncome=37;farm.earnings.bySource.walkIns=32;
  updateTownIncome();
  Object.assign(farm.activity,{producedUnits:21,soldUnits:13});
  await page.waitForFunction(()=>document.querySelector('[data-business-metric="income"] .game-live-value')?.textContent.trim()==='37 YM',null,{timeout:6500});
  assert(stateReads>readsBefore,'BUILD polls automatically within a few seconds');
  await values(farm,'Polled changes');
  // Large live values react to capacity changes.
  assert.equal(await panel.locator('.game-live-value.is-updated').count(),5,'Sales, profit, margin and both changed capacities highlight');
  assert.equal(await panel.locator('.game-live-rate.is-updated').count(),0,'Removed history captions do not reappear');
  await refresh();
  assert.equal(await panel.locator('.game-live-value.is-updated').count(),0,'Unchanged poll does not highlight values');
  await select(1);await values(other,'Other business');
  assert.deepEqual(await stock.locator('[data-stock-good]').evaluateAll(rows=>rows.map(row=>row.dataset.stockGood)),other.goods.map(g=>g.goodId),'Selecting another business replaces its stock rows');
  assert.equal(await panel.locator('.game-live-value.is-updated').count(),0,'Changing selection does not invent metric movement');
  await select(0);await values(farm,'Reselected business');
  assert.equal(await panel.locator('.game-live-value.is-updated').count(),0,'Returning to a business does not highlight unchanged values');

  const activity=clone(farm.activity);
  delete farm.activity;await refresh();await values(farm,'Missing history');
  assert.doesNotMatch(await panel.textContent(),/654,321|543,210/,'Missing observed goods totals never fall back to flow estimates');
  farm.activity={windowSeconds:60,observedSeconds:0,producedUnits:0,soldUnits:0};
  farm.earnings.operatingIncome=0;farm.earnings.bySource.walkIns=0;farm.earnings.bySource.regularBuyers=0;
  await refresh();await values(farm,'Cold start');
  assert(farm.incomePerMinute>0,'A business can have a current earning rate before any receipts arrive');
  farm.activity=activity;
  farm.earnings.operatingIncome=37;farm.earnings.bySource.walkIns=32;farm.earnings.bySource.regularBuyers=5;
  await page.emulateMedia({reducedMotion:'reduce'});farm.stored++;
  await refresh();
  assert(await metric('income').evaluate(el=>getComputedStyle(el).animationName==='none'),'Reduced motion disables value highlight animation');

  const fullTown=clone(state);
  async function fit(label){
   await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());await page.evaluate(()=>document.fonts.ready);
   const problems=await page.locator('#econ-building').evaluate(root=>{
    const boundary=root.getBoundingClientRect(),issues=[],margin=2;
    const visible=el=>el.getClientRects().length&&!el.closest('[hidden],.game-view-hidden');
    const identify=el=>el.className||el.tagName;
    for(const el of root.querySelectorAll('[data-business-metric],.game-live-metrics dt,.game-live-metrics dd,.game-live-value,.game-inventory-row,.game-inventory-good strong,[data-stock-count],[data-stock-saved],.game-stock-controls button,.game-stock-controls a,.game-site .k-art')){
     if(!visible(el))continue;
     const r=el.getBoundingClientRect();
     if(r.left<Math.max(0,boundary.left)-margin||r.right>Math.min(innerWidth,boundary.right)+margin||r.top<Math.max(0,boundary.top)-margin||r.bottom>Math.min(innerHeight,boundary.bottom)+margin)issues.push(identify(el)+' outside panel or viewport');
     if(el.matches('dt,dd,.game-live-value,.game-inventory-good strong,[data-stock-count],[data-stock-saved],button,a')&&(el.scrollWidth>el.clientWidth+margin||el.scrollHeight>el.clientHeight+margin))issues.push(identify(el)+' text clipped');
    }
    const children=[...root.querySelectorAll('.game-site > *, .game-building-stock > *')].filter(visible).filter(el=>getComputedStyle(el).position!=='absolute');
    for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){
     if(children[i].contains(children[j])||children[j].contains(children[i]))continue;
     const a=children[i].getBoundingClientRect(),b=children[j].getBoundingClientRect();
     if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>margin&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>margin)issues.push('Overlapping sections '+identify(children[i])+' / '+identify(children[j]));
    }
    if(document.documentElement.scrollWidth>innerWidth+1||document.documentElement.scrollHeight>innerHeight+1)issues.push('Page scrolling');
    return [...new Set(issues)];
   });
   await page.screenshot({path:path.join(output,label+'.png'),animations:'disabled'});
   if(problems.length)fitProblems.push({view:label,problems});
   sizes.push(label);
  }
  for(const [width,height] of [[1366,768],[1366,650],[1728,694],[1920,1080],[1024,768],[768,768],[390,844],[844,390]]){
   await page.setViewportSize({width,height});
   state=clone(fullTown);await refresh();await select(0);
   const stockTab=page.getByRole('tab',{name:'Stock',exact:true});
   if(await stockTab.isVisible())await page.getByRole('tab',{name:'Building',exact:true}).click();
   await fit('full-town-'+width+'x'+height);
   if(await stockTab.isVisible()){await stockTab.click();assert(await stock.isVisible());await fit('full-town-stock-'+width+'x'+height);}
   else assert(await stock.isVisible(),'Desktop shows individual stock below metrics');
   state.buildings=state.buildings.slice(0,1);state.buildingsOwned=1;state.board=state.board.filter(g=>g.slot===0);
   state.nextStep={title:'Deliver your first town project',detail:'Send a small shipment to earn materials for your next business.',href:'./marketplace.html#town-project',actionLabel:'View town project'};
   state.customerContracts.active=[];
   await refresh();
   if(await stockTab.isVisible())await page.getByRole('tab',{name:'Building',exact:true}).click();
   await fit('opening-'+width+'x'+height);
   if(await stockTab.isVisible()){await stockTab.click();await fit('opening-stock-'+width+'x'+height);}
   assert(await stock.isVisible(),'Opening guide does not hide business stock');
  }
  assert.deepEqual(mutations,[]);assert.deepEqual(errors,[]);
  assert.deepEqual(fitProblems,[],'Metrics, stock rows and controls fit every panel and viewport');
  console.log(JSON.stringify({result:'passed',metrics:6,pollReads:stateReads,viewports:8,layouts:sizes.length,checks:['cashflow heading removed','actual business and town sales','polling','change highlights','selection','missing history','zero receipts','individual stock','class pause','reconnect recovery','visibility recovery','reduced motion']},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
