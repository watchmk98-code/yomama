/* UI ownership and navigation checks. API responses are isolated in the browser;
   the running town is only read to obtain a representative v4 snapshot.
   Run: node tests/ui_page_purposes.cjs [http://127.0.0.1:3003] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=process.argv[2]||'http://127.0.0.1:3003';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const metadata=await response.json();assert.equal(metadata.modelVersion,4);
 // A fresh, isolated three-business sample always has a roastery and room to
 // expand, regardless of which businesses the preview currently owns.
 const sample=JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import json
import production_economy as E
import breakfast_event as B
cfg=E.load_config()
st=E.new_state(cfg,seed=37)
st['b']=[E._building(ti,lv=3,sales=2) for ti in range(3)]
st['tierOf']=list(range(3))
st['cash']=100000
st=E.migrate_state(cfg,st)
st['offers']=None
E.offer_contracts(cfg,st,st['tick'])
s=E.payload(cfg,st,E.new_class(cfg),dict(paused=False))
s['breakfastEvent']=B.payload(st,st['tick']*cfg['global']['tick'],cfg=cfg)
print(json.dumps(s))
`],{cwd:root,encoding:'utf8'}));
 const s=Object.assign(metadata,sample,{overnightReport:null,classCompetition:false});
 s.gateOpen=false;s.checklist.quiz=false;
 s.buildings.forEach(b=>Object.values(b.upgrades).forEach(u=>{u.canBuy=true;u.cost=100;u.why='';u.level=Math.min(u.level,8);}));
 s.contracts.offers.forEach(o=>{o.canFulfill=true;o.why='';o.requirements.forEach(g=>g.owned=g.quantity);});
 const quiz=JSON.parse(fs.readFileSync('config/quiz.json','utf8'));
 let serial=0;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==base)return route.abort();
  if(url.pathname==='/api/game/state')return route.fulfill({json:s});
  if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
  if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
  const endpoint=url.pathname.slice('/api/game/econ/'.length);
  if(endpoint==='quiz'&&route.request().method()==='GET')return route.fulfill({json:quiz});
  if(route.request().method()==='POST'&&endpoint!=='login'){
   const data=route.request().postDataJSON();calls.push({endpoint,data});delete s.receipt;
   const b=s.buildings.find(b=>b.slot===data.slot);
   if(endpoint==='upgrade'){b.upgrades[data.kind].level++;s.receipt={kind:'upgrade'};}
   if(endpoint==='reserve')b.reserve=data.reserve;
   if(endpoint==='processing')b.processing=data.enabled;
   if(endpoint==='focus')b.focus=data.focus;
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
 const pages={buildings:['expand','upgrade:production','upgrade:sales','upgrade:storage','reserve','sell'],marketplace:['fulfill','replace','commit','customer'],'advanced-hq':['processing','business','workforce'],license:['quiz']};
 const owners=new Map();
 async function showTab(name){const tab=page.getByRole('tab',{name,exact:true});if(await tab.isVisible())await tab.click();}
 async function go(file){await page.goto(base+'/'+file+'.html');await page.locator('.game-wallet,.game-resources').waitFor();if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();await page.waitForFunction(()=>window.YomamaEcon&&window.YomamaEcon.state()&&!document.querySelector('[aria-busy="true"]'));await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());if(file==='buildings')await showTab('Building');else if(file==='advanced-hq')await showTab('Recipes');assert.deepEqual(errors,[]);}
 async function act(action){
  const family=action.split(':')[0],tab={upgrade:'Upgrades',expand:'Expand',reserve:'Stock',sell:'Stock',processing:'Recipes',business:'Team',fulfill:'Orders',replace:'Orders',commit:'Orders',quiz:'Quiz'}[family];
  if(tab)await showTab(tab);
  const control=page.locator('[data-econ-action="'+action+'"]');
  if(['fulfill','replace','commit'].includes(family))for(let i=0;!await control.isVisible()&&i<3;i++){
   const next=page.getByRole('button',{name:'Next orders page',exact:true});
   if(await next.isEnabled())await next.click();
   else while(await page.getByRole('button',{name:'Previous orders page',exact:true}).isEnabled())await page.getByRole('button',{name:'Previous orders page',exact:true}).click();
  }
  const before=calls.length;await control.click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));assert.equal(calls.length,before+1);
 }
 for(const [file,allowed] of Object.entries(pages)){
  await go(file);
  const readActions=()=>page.locator('.game-workspace [data-econ-action]').evaluateAll(es=>es.map(e=>e.dataset.econAction));
  const actions=await readActions();
  if(file==='advanced-hq' && await page.locator('.wf-workspace').count()){
   for(const key of ['focus','team','hq']){
    await page.locator('#game-wf-tab-'+key).click();
    actions.push(...await readActions());
    if(key==='team'){
     await page.locator('#game-wf-team-business').click();
     actions.push(...await readActions());
    }
   }
   await showTab('Recipes');
  }
  for(const action of actions){
   const parts=action.split(':');const family=parts[0]==='upgrade'?'upgrade:'+parts[2]:parts[0];
   assert(allowed.includes(family),file+' contains misplaced '+action);
   assert(!owners.has(family)||owners.get(family)===file,family+' is repeated across screens');owners.set(family,file);
  }
  assert.equal(await page.locator('[data-business-focus]').count(),file==='advanced-hq'&&s.buildings.at(-1).focusUnlocked?1:0,file+' has misplaced or missing specialty selection');
  for(const [selector,owner] of Object.entries({'.game-specialty':'advanced-hq','.game-recipe':'advanced-hq','.game-inventory-table':'buildings','.game-order-grid':'marketplace','.game-customer-contracts':'marketplace'}))if(file!==owner)assert.equal(await page.locator(selector).count(),0,file+' repeats '+selector);
  assert.equal(await page.locator('.game-stock').count(),0,file+' repeats the old stock panel');
  if(file==='marketplace')assert.equal(await page.locator('#game-business-choice').count(),0,'Orders and customers belong to the whole town');
  assert.equal(await page.locator('[data-game-deliveries]').count(),0);
  assert.equal(await page.locator('.hero .tabs a').filter({hasText:/warehouse/i}).count(),0,file+' retains a Warehouse tab');
  assert.equal(await page.locator('#game-section-menu option').filter({hasText:/warehouse/i}).count(),0,file+' retains Warehouse in compact navigation');
 }
 for(const [file,families] of Object.entries(pages))for(const family of families.filter(f=>f!=='quiz'))assert.equal(owners.get(family),file,'Missing '+family+' on '+file);
 await go('buildings');assert.equal(await page.locator('#econ-building [data-econ-action^="reserve:"]').count(),1);
 const next=s.frontier[s.frontier.length-1];await showTab('Expand');await page.selectOption('#game-expansion-choice',String(next.tier));
 assert.deepEqual(errors,[]);
 assert.equal(await page.locator('.game-next-art').getAttribute('data-preview-business'),next.id);
 assert((await page.locator('.game-next-art .k-art').evaluate(e=>getComputedStyle(e).filter)).includes('grayscale(1)'));
 await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('.game-next-art').getAttribute('data-preview-business'),next.id);
 await showTab('Building');
 while(await page.locator('.game-pager[data-page="Buildings"] button:first-child:not(:disabled)').count())await page.locator('.game-pager[data-page="Buildings"] button:first-child').click();
 await page.locator('[data-select-building="2"]').click();
 assert.equal(await page.locator('[data-business-focus],.game-specialty').count(),0,'Build repeats the Operations specialty control');
 await page.locator('[data-building-activities="quests"]').click();
 assert.deepEqual(await page.locator('#game-activities [data-game-quest]').evaluateAll(items=>items.map(item=>item.dataset.gameQuest)),['roastery-plan','roastery-signature']);
 await page.locator('[data-game-quest="roastery-signature"]').click();
 await page.locator('[data-related-breakfast]').click();assert(await page.locator('#game-breakfast').evaluate(e=>e.open));
 await page.keyboard.press('Escape');assert(await page.locator('[data-related-breakfast]').evaluate(e=>e===document.activeElement));
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');
 assert(await page.locator('[data-building-activities="quests"]').evaluate(e=>e===document.activeElement));
 for(const kind of ['production','sales','storage']){
  const level=s.buildings[2].upgrades[kind].level;await act('upgrade:2:'+kind);assert.equal(s.buildings[2].upgrades[kind].level,level+1);
 }
 s.buildings[2].upgrades.production.canBuy=false;s.buildings[2].upgrades.production.why='Need 100 YM';await page.evaluate(()=>window.YomamaEcon.refresh());
 const blocked=page.locator('[data-econ-action="upgrade:2:production"]');assert(await blocked.isDisabled());assert.equal(await blocked.getAttribute('title'),'Need 100 YM');
 const blocker=page.locator('#'+await blocked.getAttribute('aria-describedby'));assert(await blocker.isVisible());assert.equal(await blocker.textContent(),'Need 100 YM');
 const beforeBlocked=calls.length;await blocked.evaluate(e=>e.click());assert.equal(calls.length,beforeBlocked,'Disabled upgrades must not send purchases');
 await go('advanced-hq');assert.equal(await page.locator('#game-business-choice').inputValue(),'2');
 await act('processing:2:'+String(s.buildings[2].processing===false));
 const focus=s.buildings[2].focusOptions.find(o=>o.id!==s.buildings[2].focus).id;const beforeFocus=calls.length;
 const specialty=page.locator('[data-business-focus="2"]');await specialty.focus();await specialty.selectOption(focus);await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));assert.equal(calls.length,beforeFocus+1);assert.equal(s.buildings[2].focus,focus);
 assert(await specialty.evaluate(e=>e===document.activeElement),'Specialty loses keyboard focus after changing');
 await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await specialty.inputValue(),focus);assert(await specialty.evaluate(e=>e===document.activeElement),'Polling loses specialty keyboard focus');
 await go('buildings');
 const stock=page.locator('.game-building-stock');
 assert.equal(await page.locator('[data-select-building="2"]').getAttribute('aria-pressed'),'true','Build retains the business selected in Operations');
 assert.equal(await page.locator('.game-site .game-building-stock').count(),1,'Stock uses the space below business metrics on desktop');
 assert.equal(await page.locator('.game-business-shipment,.game-business-limit').count(),0,'Stock replaces shipment and status sections');
 async function stockValues(b){
  assert.deepEqual(await stock.locator('[data-stock-good]').evaluateAll(rows=>rows.map(row=>row.dataset.stockGood)),b.goods.map(g=>g.goodId),'Only selected-business goods appear');
  if(!await page.evaluate(()=>document.body.classList.contains('game-compact')))assert.equal(await stock.locator('[data-stock-good]:visible').count(),b.goods.length,'Desktop shows every good in the business stock area');
  for(const good of b.goods){
   const row=stock.locator('[data-stock-good="'+good.goodId+'"]');
   assert.equal((await row.locator('.game-inventory-good strong').textContent()).trim(),good.name);
   assert.equal((await row.locator('[data-stock-count]').textContent()).replace(/\s+/g,' ').trim(),good.quantity+' / '+good.capacity,'Per-good stock and capacity');
   assert.equal((await row.locator('[data-stock-saved]').textContent()).trim(),String(good.reserved||0),'Per-good reserved stock');
  }
 }
 s.buildings[2].goods.forEach((g,index)=>{g.quantity=17+index;g.capacity=120+index;g.reserved=3+index;});
 await page.evaluate(()=>window.YomamaEcon.refresh());await stockValues(s.buildings[2]);
 s.buildings[2].goods[0].quantity=29;s.buildings[2].goods[0].reserved=8;
 await page.evaluate(()=>window.YomamaEcon.refresh());await stockValues(s.buildings[2]);
 s.buildings[2].reserve=false;await page.evaluate(()=>window.YomamaEcon.refresh());
 await act('reserve:2:true');assert.equal(calls.at(-1).data.slot,2);assert.equal(s.buildings[2].reserve,true);
 assert.equal(await stock.locator('[data-econ-action="reserve:2:false"]').getAttribute('aria-pressed'),'true');
 await act('reserve:2:false');assert.equal(s.buildings[2].reserve,false);
 s.buildings[2].clearableQuantity=10;s.buildings[2].clearStockValue=100;await page.evaluate(()=>window.YomamaEcon.refresh());await act('sell:2');
 assert.equal(calls.at(-1).data.slot,2);assert(await stock.locator('[data-econ-action="sell:2"]').isDisabled(),'No surplus disables selling');
 const beforeEmpty=calls.length;await stock.locator('[data-econ-action="sell:2"]').evaluate(button=>button.click());
 assert.equal(calls.length,beforeEmpty,'Disabled selling sends no request');
 await go('marketplace');await act('fulfill:0:'+s.contracts.offers[0].id);await act('replace:1:'+s.contracts.offers[1].id);await act('commit:0:'+s.contracts.offers[0].id);
 await go('warehouse');await page.waitForURL('**/buildings.html#stock');
 assert.equal(await page.locator('[data-select-building="2"]').getAttribute('aria-pressed'),'true','Warehouse bookmarks retain the selected building');
 while(await page.locator('.game-pager[data-page="Buildings"] button:first-child:not(:disabled)').count())await page.locator('.game-pager[data-page="Buildings"] button:first-child').click();
 await page.locator('[data-select-building="0"]').click();await page.evaluate(()=>window.YomamaEcon.refresh());
 assert.equal(await page.locator('[data-select-building="0"]').getAttribute('aria-pressed'),'true');
 assert.deepEqual(await stock.locator('[data-stock-good]').evaluateAll(rows=>rows.map(row=>row.dataset.stockGood)),s.buildings[0].goods.map(g=>g.goodId),'Changing business replaces its individual goods');
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
 for(const [file,labels] of Object.entries({buildings:['Building','Stock','Upgrades','Expand'],marketplace:['Orders','Contracts'],'advanced-hq':['Focus tree','Team','Recipes','Quests','Advanced HQ']})){
  const selector=file==='advanced-hq'?'.wf-tabs [role=tab]':'.game-view-tabs [role=tab]';
  await go(file);assert.deepEqual(await page.locator(selector).allTextContents(),labels,file+' has incorrect panels');
  if(!labels.length)continue;
  await page.locator(selector).first().focus();
  for(const [key,index] of [['End',labels.length-1],['ArrowRight',0],['ArrowLeft',labels.length-1],['Home',0]]){
   await page.keyboard.press(key);
   const active=page.locator(selector).nth(index);assert.equal(await active.getAttribute('aria-selected'),'true');assert(await active.evaluate(e=>e===document.activeElement));
   const panel=page.locator('#'+await active.getAttribute('aria-controls'));assert(await panel.isVisible());assert.equal(await panel.getAttribute('role'),'tabpanel');assert.equal(await panel.getAttribute('aria-labelledby'),await active.getAttribute('id'));
  }
 }
 await go('warehouse');await page.waitForURL('**/buildings.html#stock');
 const stockTab=page.getByRole('tab',{name:'Stock',exact:true});
 assert.equal(await stockTab.getAttribute('aria-selected'),'true','Warehouse bookmark opens compact Stock');
 await page.locator('.game-fit-picker').selectOption('2');
 await page.evaluate(()=>window.YomamaEcon.refresh());
 assert.equal(await page.locator('.game-fit-picker').inputValue(),'2','Compact picker persists through polling');
 assert.equal(await stockTab.getAttribute('aria-selected'),'true','Stock remains open after selection and polling');
 await stockValues(s.buildings[2]);
 await page.reload();await stock.waitFor();
 assert.equal(await stockTab.getAttribute('aria-selected'),'true','Reload preserves the Stock destination');
 assert.equal(await page.locator('.game-fit-picker').inputValue(),'2');
 await page.setViewportSize({width:1366,height:900});await page.evaluate(()=>window.YomamaFit.render());
 assert.equal(await page.locator('.game-site .game-building-stock').count(),1,'Stock returns below metrics on desktop resize');
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.YomamaFit.render());
 assert.equal(await stockTab.getAttribute('aria-selected'),'true','Resize retains compact Stock selection');
 s.buildings=s.buildings.slice(0,1);s.buildingsOwned=1;s.board=s.board.filter(g=>g.slot===0);
 for(const file of ['buildings','marketplace','advanced-hq']){
  await go(file);assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),'starter '+file+' overflow');
  if(file==='buildings')assert.equal(await page.locator('[data-select-building]').count(),1);
  else if(file==='marketplace')assert.equal(await page.locator('#game-business-choice').count(),0);
  else assert.equal(await page.locator('#game-business-choice').inputValue(),'0');
 }
 assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'passed',actions:calls.length,sizes},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
