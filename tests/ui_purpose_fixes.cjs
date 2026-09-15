/* Purpose and progression UI regression checks. Engine-generated snapshots are
   served only by Playwright interception. The preview is read once; every API
   mutation is intercepted, and no town or database is changed by these checks.
   Run: node tests/ui_purpose_fixes.cjs [http://127.0.0.1:3014] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=new URL(process.argv[2]||'http://127.0.0.1:3014').origin;
const output=path.join(root,'.checks','purpose-fixes');
const viewportFilter=process.env.YOMAMA_UI_VIEWPORT || null;
assert(!viewportFilter || ['desktop','mobile','landscape'].includes(viewportFilter),'Unknown YOMAMA_UI_VIEWPORT');
const clone=value=>JSON.parse(JSON.stringify(value));
const incomeRate=value=>Number(value).toLocaleString('en-US',{maximumFractionDigits:2})+' YM';

// Use real settled payments, project deliveries and construction grants. Keep
// these in process memory: no preview POST, seed file or development save write.
function engineSnapshots(){
 return JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import copy, json
import production_economy as E
import breakfast_event as B
cfg=E.load_config()
# Preserve coverage of saved third-slot town projects and workshop handoffs.
cfg['businessDesign']['connectedProgression']=False
st=E.new_state(cfg,seed=37)
cls=E.new_class(cfg)
result={}
def pack():
    payload=E.payload(cfg,st,cls,dict(paused=False))
    payload['breakfastEvent']=B.payload(st,st['tick']*cfg['global']['tick'],cfg=cfg)
    payload['classCompetition']=False
    payload['overnightReport']=None
    return payload
def advance(ticks):
    start=st['tick']
    E.advance_class(cfg,cls,[st],start,start+ticks)
def deliver_project():
    order=st['offers'][2]
    assert order.get('project')
    assert E.commit_order(cfg,st,2,order['id'],True)['ok']
    for _ in range(80):
        if pack()['contracts']['offers'][2]['canFulfill']:
            break
        advance(1)
    assert E.fulfill_order(cfg,st,2,order['id'])['ok']
def build_grant():
    step=pack()['nextStep']
    assert step['action'].startswith('expand:')
    tier=int(step['action'].split(':')[1])
    before=(st['cash'],st['materials'])
    assert E.expand(cfg,st,tier,st['tick'])['ok']
    assert (st['cash'],st['materials'])==before
    return tier
result['fresh']=pack()
assert E.manage_customer_contract(cfg,st,0,'accept',customer_id='corner_grocer')['ok']
advance(8)
result['income']=pack()
assert result['income']['earnings']['bySource']['regularBuyers']>0
assert result['income']['earnings']['bySource']['walkIns']>0
deliver_project()
result['grant']=pack()
result['grantTier']=build_grant()
result['building']=pack()
advance(st['build']['t']-st['tick']+1)
advance(8)
result['twoShops']=pack()
assert len(result['twoShops']['buildings'])==2
assert len({b['incomePerMinute'] for b in result['twoShops']['buildings']})==2
deliver_project()
build_grant()
advance(st['build']['t']-st['tick']+1)
result['unlocked']=pack()
assert result['unlocked']['breakfastEvent']['locked'] is False
cfg['businessDesign']['enabled']=False
result['legacyWorkshop']=pack()
cfg['businessDesign']['enabled']=True
assert B.act(st,st['tick']*cfg['global']['tick'],dict(action='start'),cfg=cfg)['ok']
result['playing']=pack()
now=st['tick']*cfg['global']['tick']
def workshop(action, **kwargs):
    assert B.act(st,now,dict(action=action,**kwargs),cfg=cfg)['ok']
for order_id in ('first','coffee','mixed','final'):
    if order_id=='final':
        workshop('upgrade',recipe='coffee')
    order=next(o for o in B.payload(st,now,cfg=cfg)['orders'] if o['id']==order_id)
    for recipe,quantity in order['needs'].items():
        while st['breakfastEvent']['stock'][recipe]<quantity:
            workshop('make',recipe=recipe)
            while st['breakfastEvent']['active'] or st['breakfastEvent']['queued']:
                now+=15
                B.advance(st,now)
                assert now < 3600
    workshop('deliver',orderId=order_id)
result['completedWorkshop']=pack()
assert result['completedWorkshop']['breakfastEvent']['status']=='done'
print(json.dumps(result))
`],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024}));
}

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const response=await fetch(base+'/api/game/econ/state');
 assert(response.ok,'Use a local signed-in preview server');
 const metadata=await response.json();
 assert.equal(metadata.modelVersion,4);
 const samples=engineSnapshots();
 const browser=await chromium.launch({headless:true});
 const allErrors=[],fitProblems=[],observations=[];
 let currentPage,currentLabel='startup';
 try{
  for(const viewport of [{name:'desktop',width:1366,height:768},
                         {name:'mobile',width:390,height:844},
                         {name:'landscape',width:844,height:390}].filter(view=>!viewportFilter || view.name===viewportFilter)){
   const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height}});
   currentPage=page;
   page.setDefaultTimeout(10000);
   await page.emulateMedia({reducedMotion:'reduce'});
   const calls=[],errors=[];
   let state,serial=0;
   function use(name){state=Object.assign(clone(metadata),clone(samples[name]),{receipt:null,overnightReport:null,classCompetition:false});}
   use('fresh');
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==base)return route.abort();
    if(!url.pathname.startsWith('/api/game/'))return route.continue();
    try{
     if(url.pathname==='/api/game/state')return route.fulfill({json:state});
     // yomama-net keeps an old display-blob save on navigation. Acknowledge it
     // locally as well; it must never write to the preview during this test.
     if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
     assert(url.pathname.startsWith('/api/game/econ/'),'Unexpected API: '+url.pathname);
     const endpoint=url.pathname.slice('/api/game/econ/'.length);
     if(route.request().method()==='POST'&&endpoint!=='login'){
      const data=route.request().postDataJSON();
      calls.push({endpoint,data});
      delete state.receipt;
      if(endpoint==='orders/replace'||endpoint==='orders/commit'){
       assert([0,1,2].includes(data.offerIndex));
       const order=state.contracts.offers[data.offerIndex];
       assert.equal(data.orderId,order.id,'A control must send its current order ID');
       if(endpoint==='orders/replace'){
        assert(!order.project,'Town projects cannot be rerolled');
        order.id='isolated-ui-order-'+(++serial);
        order.committed=false;
        state.receipt={kind:'order_replace'};
       }else{
        order.committed=data.committed;
        state.receipt={kind:'order_commit',committed:data.committed};
       }
      }else if(endpoint==='expand'){
       assert.equal(data.tier,samples.grantTier);
       assert(state.frontier.some(b=>b.tier===data.tier&&b.constructionGrant&&b.cost===0));
       use('building');
       state.receipt={kind:'expand'};
      }else if(endpoint==='event/breakfast'){
       assert.equal(data.action,'start');
       assert.equal(state.breakfastEvent.locked,false);
       use('playing');
       state.receipt={kind:'breakfast',message:'Workshop opened'};
      }else assert.fail('Unexpected mutation (intercepted): '+endpoint);
     }
     return route.fulfill({json:state});
    }catch(error){
     errors.push(error.stack||String(error));
     return route.fulfill({status:500,json:{error:'Isolated UI test rejected this request'}});
    }
   });

   async function settle(){
    await page.waitForFunction(()=>window.YomamaEcon&&window.YomamaEcon.state()&&!document.querySelector('[aria-busy="true"]'));
    await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());
    await page.waitForTimeout(100);
   }
   async function go(file){
    await page.goto(base+'/'+file+'.html');
    await page.locator('.game-wallet,.game-resources').waitFor();
    if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();
    await settle();
   }
   async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await settle();}
   async function fit(label){
    currentLabel=viewport.name+'-'+label;
    await settle();
    const issues=await page.evaluate(()=>{
     const problems=[],margin=2;
     const visible=el=>el.getClientRects().length&&!el.closest('[hidden]')&&getComputedStyle(el).visibility!=='hidden';
     const identify=el=>(el.id?'#'+el.id:el.className||el.tagName)+' '+(el.textContent||'').trim().replace(/\s+/g,' ').slice(0,65);
     const dialog=document.activeElement.closest('dialog[open]')||Array.from(document.querySelectorAll('dialog[open]')).at(-1);
     if(document.documentElement.scrollWidth>innerWidth+1)problems.push('Document horizontal overflow');
     if(!dialog&&document.documentElement.scrollHeight>innerHeight+1)problems.push('Document vertical overflow');
     const scope=dialog||document.querySelector('.game-workspace');
     if(!scope)return ['Workspace missing'];
     const selectors='button,select,a[href],.game-output,.game-eyebrow,[data-business-metric],.game-business-shipment,.game-business-limit,.game-opening-guide,.game-upgrade-reason,.game-upgrade-impact,.game-order-name,.game-order-tier,.game-project-reward,.econ-good-line';
     for(const el of scope.querySelectorAll(selectors)){
      if(!visible(el))continue;
      const r=el.getBoundingClientRect();
      if(r.left < -margin||r.right>innerWidth+margin||(!dialog&&(r.top < -margin||r.bottom>innerHeight+margin)))problems.push('Outside viewport: '+identify(el));
      if(el.matches('button,select')&&el.scrollWidth>el.clientWidth+margin)problems.push('Control text clipped horizontally: '+identify(el));
      const panel=el.closest('.game-panel,.game-order,.game-opening-guide');
      if(panel&&panel!==el&&!dialog){
       const p=panel.getBoundingClientRect();
       if(r.left<p.left-margin||r.right>p.right+margin||r.top<p.top-margin||r.bottom>p.bottom+margin)problems.push('Outside own panel: '+identify(el));
      }
      // Scrollable workshop content is intentionally reachable by scrolling.
      // Hidden/clip containers on the fitted game page must never hide controls.
      for(let ancestor=el.parentElement;ancestor&&ancestor!==scope.parentElement;ancestor=ancestor.parentElement){
       const style=getComputedStyle(ancestor),a=ancestor.getBoundingClientRect();
       if(['hidden','clip'].includes(style.overflowX)&&(r.left<a.left-margin||r.right>a.right+margin))problems.push('Horizontally clipped by '+identify(ancestor)+': '+identify(el));
       if(!dialog&&['hidden','clip'].includes(style.overflowY)&&(r.top<a.top-margin||r.bottom>a.bottom+margin))problems.push('Vertically clipped by '+identify(ancestor)+': '+identify(el));
      }
     }
     for(const card of scope.querySelectorAll('.game-order,.game-site')){
      if(!visible(card))continue;
      const children=Array.from(card.children).filter(visible).filter(el=>getComputedStyle(el).position!=='absolute');
      for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){
       const a=children[i].getBoundingClientRect(),b=children[j].getBoundingClientRect();
       if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>margin&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>margin)problems.push('Overlapping panel sections: '+identify(children[i])+' / '+identify(children[j]));
      }
     }
     return [...new Set(problems)];
    });
    if(issues.length)fitProblems.push({view:currentLabel,issues});
    await page.screenshot({path:path.join(output,currentLabel+'.png')});
   }
   async function selectShop(slot){
    const buildingTab=page.getByRole('tab',{name:'Building',exact:true});
    if(await buildingTab.isVisible()){await buildingTab.click();await settle();}
    const picker=page.locator('.game-fit-picker');
    if(state.buildings.length===1){
     assert.equal(state.buildings[0].slot,slot);
     assert.equal(await page.locator('[data-select-building="'+slot+'"]').getAttribute('aria-pressed'),'true');
     assert((await page.locator('.game-site .game-panel-head').textContent()).includes(state.buildings[0].name));
     return;
    }
    if(await picker.isVisible())await picker.selectOption(String(slot));
    else await page.locator('[data-select-building="'+slot+'"]').click();
    await settle();
   }
   async function showOrder(slot){
    const card=page.locator('[data-order-slot="'+slot+'"]');
    for(let i=0;!(await card.isVisible())&&i<3;i++){
     const next=page.getByRole('button',{name:'Next orders page',exact:true});
     if(await next.isEnabled())await next.click();
     else while(await page.getByRole('button',{name:'Previous orders page',exact:true}).isEnabled())await page.getByRole('button',{name:'Previous orders page',exact:true}).click();
    }
    assert(await card.isVisible(),'Order '+slot+' is reachable');
    return card;
   }

   await go('buildings');
   assert.equal(state.breakfastEvent.locked,true);
   const projectsButton=page.locator('[data-building-activities="projects"]');
   assert.equal(await page.locator('.game-opening-guide').count(),1,'Build keeps the next opening goal visible');
   assert.match(await page.locator('[data-activity-kind="projects"]').textContent(),/Feed the neighborhood/);
   await fit('fresh-build');
   if(await page.getByRole('tab',{name:'Building',exact:true}).isVisible())for(const name of ['Upgrades','Expand','Building']){
    await page.getByRole('tab',{name,exact:true}).click();await settle();
    assert(await page.locator('.game-opening-guide').isVisible(),'The opening goal remains visible from every Build tab');
    await fit('fresh-build-'+name.toLowerCase());
   }
   await projectsButton.click();
   assert.deepEqual(await page.locator('#game-activities [data-game-project]').evaluateAll(items=>items.map(item=>item.dataset.gameProject)),['farm_neighbors']);
   await page.locator('[data-game-project="farm_neighbors"]').click();
   await page.locator('#game-project[open]').waitFor();
   assert.match(await page.locator('#game-project').textContent(),/Fully funded Harbor Fish Stall construction/);
   await fit('farm-project');
   await page.locator('#game-project-save').click();await settle();
   assert.equal(calls.at(-1).endpoint,'orders/commit');
   assert.equal(calls.at(-1).data.orderId,state.contracts.offers[2].id);
   assert.equal(await page.locator('#game-project-save').getAttribute('aria-pressed'),'true');
   await page.keyboard.press('Escape');await page.keyboard.press('Escape');
   await page.goto(base+'/marketplace.html#town-project');await settle();
   assert.equal(await page.locator('.game-order-grid > .game-order').first().getAttribute('data-order-slot'),'2');
   const project=page.locator('[data-order-slot="2"]');
   assert(await project.isVisible(),'The project must be the first visible market card, including mobile');
   assert.equal(await project.getAttribute('data-rarity'),null);
   assert.equal(await project.locator('[data-econ-action^="replace:"]').count(),0);
   assert.equal(await project.locator('.game-order-reaction').count(),0);
   assert.match(await project.textContent(),/Fully funded Harbor Fish Stall construction/);
   await fit('project-market');
   // Release the goods saved in Build, then exercise the same save on Market.
   assert.equal(await project.locator('.game-order-commit').getAttribute('aria-pressed'),'true');
   await project.locator('.game-order-commit').click();await settle();
   await project.locator('.game-order-commit').click();await settle();
   assert.equal(calls.at(-1).endpoint,'orders/commit');
   assert.equal(calls.at(-1).data.offerIndex,2);
   assert.equal(await project.locator('.game-order-commit').getAttribute('aria-pressed'),'true');
   assert.equal(await project.locator('[data-saved-order="2"]').count(),1);
   assert.match(await project.locator('[data-saved-order="2"] img').getAttribute('src'),/thumbs-up-pixel\.svg$/);

   // Both original random jobs retain their free reroll, save and reaction paths.
   for(const slot of [0,1]){
    Object.assign(state.contracts.offers[slot],{rarity:'jackpot',rarityLabel:'Jackpot',canFulfill:false,committed:false});
    await refresh();
    const card=await showOrder(slot);
    assert.equal(await card.getAttribute('data-rarity'),'jackpot');
    assert(await card.locator('[data-econ-action^="replace:"]').isEnabled());
    await fit('random-job-'+slot);
    await card.locator('.game-order-commit').click();
    await page.locator('[data-saved-order="'+slot+'"]').waitFor();
    assert.equal(calls.at(-1).endpoint,'orders/commit');
    assert.equal(await card.locator('.game-order-commit').getAttribute('aria-pressed'),'true');
    await page.waitForTimeout(650);
    await card.locator('[data-econ-action^="replace:"]').click();
    await page.locator('[data-missed-order="'+slot+'"]').waitFor();
    assert.equal(calls.at(-1).endpoint,'orders/replace');
    assert.equal(calls.at(-1).data.offerIndex,slot);
    assert.equal(await project.locator('.game-order-reaction').count(),0);
    assert.equal(await card.locator('.game-order-reaction').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
    await page.waitForTimeout(650);
   }

   use('fresh');await go('buildings');
   const beforePreview=calls.length;
   await page.locator('[data-building-activities="quests"]').click();
   assert.equal(await page.locator('#game-activities [data-game-breakfast]').count(),0,'Breakfast Club belongs to the roastery');
   assert.deepEqual(await page.locator('#game-activities [data-game-quest]').evaluateAll(items=>items.map(item=>item.dataset.gameQuest)),['farm-plan','farm-signature']);
   await page.locator('[data-game-quest="farm-signature"]').click();
   await page.locator('#game-quest[open]').waitFor();
   assert.equal(await page.locator('#game-quest [data-econ-action]').count(),0,'A locked quest cannot start or craft');
   assert.match(await page.locator('#game-quest').textContent(),/Complete .* first/i);
   await fit('quest-locked');
   assert.equal(calls.length,beforePreview);
   await page.keyboard.press('Escape');await page.keyboard.press('Escape');

   use('income');await refresh();await selectShop(0);
   async function checkIncome(slot){
    const b=state.buildings.find(item=>item.slot===slot);
    assert.equal(b.incomePerMinute,b.potentialIncomePerMinute,'Income/min shows the selected business current earning rate');
    assert.equal(b.earnings.operatingIncome,b.earnings.bySource.walkIns+b.earnings.bySource.regularBuyers,'Historical operating income still counts only settled sales');
    assert.equal(state.incomePerMinute,state.potentialIncomePerMinute,'Town income uses the current earning rate');
    assert.equal((await page.locator('.game-site .game-output').textContent()).trim(),incomeRate(b.earnings.operatingIncome));
    assert.equal((await page.locator('[data-build-metric="income"] dd').textContent()).replace(/\s+/g,''),incomeRate(state.earnings.operatingIncome).replace(/\s+/g,''));
    const metric=name=>page.locator('.game-site [data-business-metric="'+name+'"] .game-live-value');
    assert.equal(await page.locator('.game-site [data-business-metric]').count(),state.operations.enabled?6:4);
    assert.match(await page.locator('.game-site').textContent(),/last 60s/i);
    assert.equal((await metric('produced').textContent()).trim(),String(b.productionCapacityPerMinute));
    assert.equal((await metric('sold').textContent()).trim(),String(b.customerCapacityPerMinute));
    if(state.operations.enabled){
     assert.equal((await metric('cost').textContent()).trim(),'−'+incomeRate(b.operatingCostPerMinute));
     assert.equal((await metric('profit').textContent()).trim(),incomeRate(b.earnings.operatingIncome-b.operatingCostPerMinute));
    }else assert.equal((await metric('stock').textContent()).trim(),b.stored.toLocaleString('en-US',{maximumFractionDigits:1})+' / '+b.capacity.toLocaleString('en-US',{maximumFractionDigits:1}));
    assert.equal(await page.locator('.game-site .game-production-loop,.game-site .game-income-detail').count(),0,'Live business metrics stay in the main panel');
    assert.equal(await page.locator('.game-building-stock').count(),1);
    assert.equal(await page.locator('.game-business-shipment').count(),0);
    observations.push({view:viewport.name,slot,incomeRate:b.incomePerMinute,actualReceipts:b.earnings.operatingIncome,walkIns:b.earnings.bySource.walkIns,regularBuyers:b.earnings.bySource.regularBuyers});
   }
   assert(state.buildings[0].earnings.bySource.regularBuyers>0,'Actual settled regular payment is present');
   await checkIncome(0);await fit('income-farm');
   use('twoShops');await refresh();
   for(const slot of [1,0]){await selectShop(slot);await checkIncome(slot);await fit('income-selected-'+slot);}

   use('grant');await refresh();
   assert.equal(state.nextStep.action,'expand:'+samples.grantTier);
   assert(state.buildings[0].earnings.oneOffIncome>0,'The delivered project produced a real one-off payment');
   await checkIncome(0);
   await fit('grant-build');
   const cash=state.cash,materials=state.materials;
   const expandTab=page.getByRole('tab',{name:'Expand',exact:true});
   if(await expandTab.isVisible()){await expandTab.click();await settle();}
   await page.locator('#game-expansion-choice').selectOption(String(samples.grantTier));
   const grantButton=page.locator('.game-expansion [data-econ-action="expand:'+samples.grantTier+'"]');
   assert(await grantButton.isEnabled());await grantButton.click();await settle();
   assert.equal(calls.at(-1).endpoint,'expand','The construction panel uses the standard authenticated expansion endpoint');
   assert.equal(calls.at(-1).data.tier,samples.grantTier);
   assert.equal(state.cash,cash);assert.equal(state.materials,materials);
   assert.match(await page.locator('.game-construction').textContent(),/Harbor Fish Stall/);

   use('legacyWorkshop');await go('buildings');await selectShop(2);
   await page.locator('[data-building-activities="quests"]').click();
   assert.equal(await page.locator('#game-activities [data-game-breakfast]').count(),1,'Legacy roastery classes retain their workshop');
   await page.locator('#game-activities [data-game-breakfast]').click();
   assert(await page.locator('#game-breakfast [data-econ-action="breakfast:start"]').isEnabled());
   await page.keyboard.press('Escape');await page.keyboard.press('Escape');

   use('unlocked');await refresh();await selectShop(2);
   await page.locator('[data-building-activities="quests"]').click();
   await page.locator('[data-game-quest="roastery-signature"]').click();
   await page.locator('[data-related-breakfast]').click();
   const start=page.locator('#game-breakfast [data-econ-action="breakfast:start"]');
   assert(await start.isEnabled());
   assert.match(await page.locator('#game-breakfast').textContent(),/25%.*base speed/i);
   assert.match(await page.locator('#game-breakfast').textContent(),/practice coins/i);
   await fit('workshop-unlocked');
   await start.click();await settle();
   assert.equal(calls.at(-1).endpoint,'event/breakfast');
   assert.equal(calls.at(-1).data.action,'start');
   assert.equal(state.breakfastEvent.status,'playing');
   assert.match(await page.locator('#game-breakfast').textContent(),/Workshop supplies only/i);
   assert.match(await page.locator('#game-breakfast').textContent(),/practice coins/i);
   await fit('workshop-playing');
   use('completedWorkshop');await refresh();
   assert.match(await page.locator('#game-breakfast').textContent(),/Espresso.*25%.*base.*speed/i);
   assert.match(await page.locator('#game-breakfast').textContent(),/recipe/i);
   assert.equal(await page.locator('#game-breakfast [data-econ-action="breakfast:start"]').count(),0);
   await fit('workshop-completed');
   allErrors.push(...errors.map(error=>viewport.name+': '+error));
   assert.deepEqual(errors,[]);
   await page.close();currentPage=null;
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({observations,fitProblems,errors:allErrors},null,2)+'\n');
  assert.deepEqual(fitProblems,[],'Viewport/content clipping detected; see .checks/purpose-fixes/results.json');
  console.log('Passed: current business/town income rates with separate actual receipts; selected-business projects and quests; original Market controls/reactions; locked quest, linked and legacy Breakfast Club; grant through normal expand endpoint; desktop, mobile and short landscape fit.');
  if(viewportFilter)console.log('Viewport scope: '+viewportFilter);
  console.log('Screenshots and measured income: .checks/purpose-fixes/');
 }catch(error){
  if(currentPage&&!currentPage.isClosed())await currentPage.screenshot({path:path.join(output,currentLabel+'-failure.png')}).catch(()=>{});
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({observations,fitProblems,errors:allErrors,failure:error.stack||String(error)},null,2)+'\n');
  throw error;
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
