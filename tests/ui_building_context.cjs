/* Selected-business quests, projects, unlockable stock and town operating costs.
   Engine snapshots are served by Playwright interception. No API mutation can
   reach the local preview or a user's town. Run against any signed-in preview:
   node tests/ui_building_context.cjs http://127.0.0.1:3012 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=new URL(process.argv[2]||'http://127.0.0.1:3012').origin;
const output=path.join(root,'.checks','building-context');
const clone=value=>JSON.parse(JSON.stringify(value));
const rate=value=>Number(value).toLocaleString('en-US',{maximumFractionDigits:2});

function engineSnapshots(){
 return JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import json
import production_economy as E
import business_progression as P
import breakfast_event as B
cfg=E.load_config()
# This regression intentionally covers preserved workshop-style class saves.
cfg['businessDesign']['connectedProgression']=False
st=E.new_state(cfg,seed=37)
cls=E.new_class(cfg)
def pack():
    p=E.payload(cfg,st,cls,dict(paused=False))
    p['breakfastEvent']=B.payload(st,st['tick']*cfg['global']['tick'],cfg=cfg)
    p.update(classCompetition=False,overnightReport=None,receipt=None)
    return p
samples={'opening':pack()}
st['tierOf']=list(range(len(cfg['tiers'])))
st['b']=[E._building(i,lv=3,sales=2) for i in st['tierOf']]
st.update(cash=25000,materials=20,offers=None)
st=E.migrate_state(cfg,st)
E.offer_contracts(cfg,st,st['tick'])
samples['locked']=pack()
assert next(b for b in samples['locked']['buildings'] if b['id']=='garage')['goods'][-1]['locked']
def act(action,quest,**kwargs):
    r=P.act(cfg,st,dict(action=action,questId=quest,**kwargs))
    assert r['ok'],r
for quest,choice,batches in [
    ('garage-plan','regulars',[('first',2),('second',2)]),
    ('garage-signature','careful',[('prepare',3),('finish',2)])]:
    act('quest_plan',quest,choice=choice)
    for recipe,count in batches:
        for _ in range(count):
            act('quest_batch',quest,recipe=recipe)
    act('quest_finish',quest)
samples['unlocked']=pack()
assert not next(b for b in samples['unlocked']['buildings'] if b['id']=='garage')['goods'][-1]['locked']
# A farm beside a cafe still advertises only its own current-demand sales gain.
# Independent production means other businesses do not consume farm goods.
st=E.new_state(cfg,seed=37)
st.update(cash=1000000,tierOf=[0,2],b=[E._building(0,sales=8),E._building(2,lv=8,sales=8)],offers=[])
st=E.migrate_state(cfg,st)
samples['supplyChain']=pack()
preview=samples['supplyChain']['buildings'][0]['upgrades']['production']
assert preview['businessIncomeAfter']>preview['businessIncomeBefore']
assert preview['incomeDelta']==preview['businessIncomeAfter']-preview['businessIncomeBefore']
assert E.buy_upgrade(cfg,st,0,'production')['ok']
samples['supplyChainUpgraded']=pack()
print(json.dumps(samples))
`],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024}));
}

(async()=>{
 assert(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Use an isolated local preview');
 const response=await fetch(base+'/api/game/econ/state');
 assert(response.ok,'Use a signed-in local preview server');
 const metadata=await response.json();
 assert.equal(metadata.modelVersion,4);
 const samples=engineSnapshots();
 const browser=await chromium.launch({headless:true});
 const errors=[],mutations=[],fitProblems=[],checked=[];
 fs.mkdirSync(output,{recursive:true});
 let currentPage,label='startup';
 try{
  for(const viewport of [{name:'desktop',width:1366,height:768},{name:'mobile',width:390,height:844},{name:'landscape',width:844,height:390}]){
   const page=await browser.newPage({viewport});
   currentPage=page;
   page.setDefaultTimeout(10000);
   await page.emulateMedia({reducedMotion:'reduce'});
   let state;
   const use=name=>{state=Object.assign(clone(metadata),clone(samples[name]));};
   use('locked');
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==base)return route.abort();
    if(!url.pathname.startsWith('/api/game/'))return route.continue();
    try{
     if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
     if(request.method()!=='GET'&&!url.pathname.endsWith('/login')){
      mutations.push(url.pathname);
      assert.fail('Display controls must not mutate a town: '+url.pathname);
     }
     return route.fulfill({json:state});
    }catch(error){errors.push(error.stack||String(error));return route.fulfill({status:500,json:{error:'Isolated UI check rejected a mutation'}});}
   });
   async function settle(){
    await page.waitForFunction(()=>window.YomamaEcon&&window.YomamaEcon.state()&&!document.querySelector('[aria-busy="true"]'));
    await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());
    await page.evaluate(()=>document.fonts.ready);
    await page.waitForFunction(()=>Array.from(document.images).filter(image=>image.getClientRects().length).every(image=>image.complete));
   }
   async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await settle();}
   async function select(id){
    const business=state.buildings.find(b=>b.id===id);
    assert(business,'Unknown business '+id);
    const picker=page.locator('.game-fit-picker');
    if(await picker.isVisible())await picker.selectOption(String(business.slot));
    else if(state.buildings.length>1){
     const button=page.locator('[data-select-building="'+business.slot+'"]');
     for(let attempt=0;!await button.isVisible()&&attempt<20;attempt++){
      const first=Number(await page.locator('.game-roster-list [data-select-building]:visible').first().getAttribute('data-select-building'));
      await page.getByRole('button',{name:(business.slot<first?'Previous':'Next')+' buildings page',exact:true}).click();
     }
     await button.click();
    }
    await settle();
    for(const kind of ['quests','projects'])assert.equal(await page.locator('.game-building-activity[data-activity-kind="'+kind+'"]').getAttribute('data-activity-building'),id,'The '+kind+' panel follows the selected business');
    return business;
   }
   async function openActivities(kind){
    const button=page.locator('[data-building-activities="'+kind+'"]');
    if(!await button.isVisible()){
     const buildingTab=page.getByRole('tab',{name:'Building',exact:true});
     if(await buildingTab.isVisible()){await buildingTab.click();await settle();}
    }
    assert(await button.isVisible(),kind+' launcher is visible on the selected Build panel');
    await button.focus();await page.keyboard.press('Enter');
    assert(await page.locator('#game-activities').isVisible(),'Keyboard opens '+kind);
   }
   async function close(id){
    // The close event follows the `open` attribute change; wait for focus
    // restoration before sending the next keyboard activation.
    await page.evaluate(id=>{window.__buildingContextClosed=false;document.getElementById(id).addEventListener('close',()=>{window.__buildingContextClosed=true;},{once:true});},id);
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>window.__buildingContextClosed);
    assert.equal(await page.locator('#'+id).isVisible(),false);
   }
   async function fit(name){
    label=viewport.name+'-'+name;await settle();
    const issues=await page.evaluate(()=>{
     const issues=[],margin=2,dialog=document.querySelector('dialog[open]');
     const visible=el=>el.getClientRects().length&&!el.closest('[hidden],.game-view-hidden');
     const identify=el=>(el.id?'#'+el.id:el.className||el.tagName)+' '+el.textContent.trim().replace(/\s+/g,' ').slice(0,55);
     if(document.documentElement.scrollWidth>innerWidth+margin)issues.push('Document horizontal overflow');
     if(!dialog&&document.documentElement.scrollHeight>innerHeight+margin)issues.push('Document vertical overflow');
     const scope=dialog||document.querySelector('.game-workspace');
     if(!dialog)for(const el of document.querySelectorAll('#game-hud [data-build-metric]')){
      const r=el.getBoundingClientRect();
      if(r.left< -margin||r.right>innerWidth+margin||r.top< -margin||r.bottom>innerHeight+margin)issues.push('HUD tile outside viewport: '+identify(el));
      for(const text of el.querySelectorAll('dt,dd'))if(text.scrollWidth>text.clientWidth+margin||text.scrollHeight>text.clientHeight+margin)issues.push('HUD text clipped: '+identify(text));
     }
     for(const el of scope.querySelectorAll('[data-build-metric],.game-building-activity,.game-building-activity button,.game-inventory-row,.game-stock-unlock,.game-inventory-good strong,.game-upgrade-running-cost,.game-upgrade-cost,[data-game-quest],[data-game-project],button')){
      if(!visible(el))continue;
      const r=el.getBoundingClientRect();
      if(r.left< -margin||r.right>innerWidth+margin||(!dialog&&(r.top< -margin||r.bottom>innerHeight+margin)))issues.push('Outside viewport: '+identify(el));
      if(el.matches('button,strong,.game-upgrade-running-cost')&&(el.scrollWidth>el.clientWidth+margin||el.scrollHeight>el.clientHeight+margin))issues.push('Clipped text: '+identify(el));
      if(!dialog)for(let a=el.parentElement;a&&a!==scope.parentElement;a=a.parentElement){
       const style=getComputedStyle(a),box=a.getBoundingClientRect();
       if(['hidden','clip'].includes(style.overflowX)&&(r.left<box.left-margin||r.right>box.right+margin))issues.push('Horizontal clipping: '+identify(el));
       if(['hidden','clip'].includes(style.overflowY)&&(r.top<box.top-margin||r.bottom>box.bottom+margin))issues.push('Vertical clipping: '+identify(el));
      }
     }
     return [...new Set(issues)];
    });
    if(issues.length)fitProblems.push({label,issues});
    await page.screenshot({path:path.join(output,label+'.png'),animations:'disabled'});
    checked.push(label);
   }

   await page.goto(base+'/buildings.html');
   await page.locator('.game-building-activity').first().waitFor();await settle();
   const cost=page.locator('[data-build-metric="cost"]');
   assert.equal(await cost.count(),1,'Town expenses have one dedicated HUD tile');
   assert.equal(await cost.evaluate(el=>el.previousElementSibling?.dataset.buildMetric),'income','Cost is immediately beside Sales / min');
   assert.match(await cost.locator('dt').textContent(),/cost.*last 60s/i);
   assert.equal(await cost.locator('dd').getAttribute('title'),'−'+rate(state.operations.operatingCostPerMinute)+' YM','Exact town expenses remain available when large values are abbreviated');
   assert.match((await cost.locator('dd').textContent()).replace(/\s/g,''),/^−[\d,.]+[kM]?YM$/);
   assert(await cost.locator('dd').evaluate(el=>{const [r,g,b]=getComputedStyle(el).color.match(/\d+/g).map(Number);return r>g+40&&r>b+40;}),'Cost rate is red');
   assert.equal(await page.locator('[data-build-metric="income"] .game-town-cost').count(),0,'Cost is not a footnote inside Sales');
   const fullTownCost=state.operations.operatingCostPerMinute;
   state.operations.operatingCostPerMinute=98.76;await refresh();
   assert.equal((await cost.locator('dd').textContent()).replace(/\s/g,''),'−98.76YM','Cost tile updates immediately from the current potential rate');
   state.operations.operatingCostPerMinute=fullTownCost;await refresh();

   await select('farm');
   assert.doesNotMatch(await page.locator('#econ-building').textContent(),/Breakfast Club/,'Farm does not show the roastery workshop');
   await openActivities('quests');
   const quests=page.locator('#game-activities [data-game-quest]');
   assert.deepEqual(await quests.evaluateAll(buttons=>buttons.map(b=>b.dataset.gameQuest).sort()),['farm-plan','farm-signature']);
   const plan=page.locator('#game-activities [data-game-quest="farm-plan"]');
   await plan.focus();await refresh();
   assert.equal(await page.evaluate(()=>document.activeElement?.dataset.gameQuest),'farm-plan','Polling preserves keyboard focus in business quests');
   await fit('farm-quests');
   await page.keyboard.press('Enter');
   assert(await page.locator('#game-quest').isVisible());
   assert.match(await page.locator('#game-quest').textContent(),/Greenfield Farm/);
   await close('game-quest');
   if(await page.locator('#game-activities').isVisible())await close('game-activities');
   await openActivities('projects');
   assert.deepEqual(await page.locator('#game-activities [data-game-project]').evaluateAll(buttons=>buttons.map(b=>b.dataset.gameProject)),['farm_neighbors']);
   await page.locator('#game-activities [data-game-project="farm_neighbors"]').click();
   assert(await page.locator('#game-project').isVisible());
   assert.match(await page.locator('#game-project').textContent(),/Feed the neighborhood/);
   assert.match(await page.locator('#game-project').textContent(),/complete/i);
   assert.equal(await page.locator('#game-project [data-econ-action]').count(),0,'Completed project does not repeat its delivery');
   await fit('farm-completed-project');await close('game-project');
   if(await page.locator('#game-activities').isVisible())await close('game-activities');

   const garage=await select('garage');
   const upgradesTab=page.getByRole('tab',{name:'Upgrades',exact:true});
   if(await upgradesTab.isVisible()){await upgradesTab.focus();await page.keyboard.press('Enter');await settle();}
   for(const kind of ['production','sales','storage']){
    const upgrade=garage.upgrades[kind];
    assert(upgrade.operatingCostDelta>0,kind+' carries a running cost increase');
    const row=page.locator('.game-operation').filter({has:page.locator('[data-econ-action="upgrade:'+garage.slot+':'+kind+'"]')});
    const preview=row.locator('.game-upgrade-running-cost');
    assert(await preview.isVisible(),kind+' running-cost preview is visible before buying');
    assert.equal((await preview.locator('.game-upgrade-cost').textContent()).trim(),'+'+rate(upgrade.operatingCostDelta)+' YM/min');
    const incomeDelta=Math.round((upgrade.businessIncomeAfter-upgrade.businessIncomeBefore)*100)/100;
    const income=row.locator('.game-upgrade-impact');
    assert.equal((await income.locator('.game-upgrade-value').textContent()).trim(),(incomeDelta>=0?'+':'−')+rate(Math.abs(incomeDelta))+' YM/min');
    if(kind==='production'){
     assert.match(await income.getAttribute('title'),/current customers/);
     if(incomeDelta===0)assert(await row.locator('.game-upgrade-explanation').isVisible(),'A zero sales gain explains why');
    }
    if(incomeDelta>0)assert(await income.evaluate(el=>{const [r,g,b]=getComputedStyle(el).color.match(/\d+/g).map(Number);return g>r+40&&g>b+40;}),kind+' positive income change stays green');
    assert.match(await income.getAttribute('aria-label'),/^Estimated income change:/);
    assert.match(await preview.getAttribute('aria-label'),/^Estimated cost change:/);
    assert(!/Est\. income|Est\. cost/.test(await row.textContent()),kind+' shows values without labels');
    assert(!(await row.textContent()).includes('Profit'),kind+' keeps the preview to income and cost');
    assert(await preview.locator('.game-upgrade-cost').evaluate(el=>{const [r,g,b]=getComputedStyle(el).color.match(/\d+/g).map(Number);return r>g+40&&r>b+40;}),kind+' cost increase is red');
   }
   await fit('garage-upgrade-costs');
   await openActivities('projects');
   assert.equal(await page.locator('#game-activities [data-game-project]').count(),0,'No unrelated town project is attached to the garage');
   assert.match(await page.locator('#game-activities').textContent(),/no .*projects|no projects|projects .*yet/i);
   await close('game-activities');await openActivities('quests');
   assert.deepEqual(await quests.evaluateAll(buttons=>buttons.map(b=>b.dataset.gameQuest).sort()),['garage-plan','garage-signature']);
   await close('game-activities');
   const stockTab=page.getByRole('tab',{name:'Stock',exact:true});
   if(await stockTab.isVisible())await stockTab.click();
   const locked=page.locator('[data-stock-good="garage_custom_mods"]');
   for(let pageIndex=0;!await locked.isVisible()&&pageIndex<3;pageIndex++)await page.getByRole('button',{name:'Next inventory page',exact:true}).click();
   assert(await locked.isVisible(),'Locked signature item remains visible in dedicated stock');
   assert.equal(await locked.getAttribute('data-stock-locked'),'true');
   assert(await locked.evaluate(el=>el.classList.contains('is-locked')));
   assert(await locked.evaluate(el=>[el,...el.querySelectorAll('*')].some(node=>/grayscale\(1\)|grayscale\(100%\)/.test(getComputedStyle(node).filter))),'Locked stock has a grayscale presentation');
   const unlock=locked.locator('.game-stock-unlock[data-game-quest="garage-signature"]');
   assert(await unlock.isVisible(),'Locked product explains how to unlock it');
   await fit('garage-locked-stock');
   await unlock.focus();await page.keyboard.press('Enter');
   assert(await page.locator('#game-quest').isVisible());
   assert.match(await page.locator('#game-quest').textContent(),/Custom Ride/);
   await close('game-quest');
   use('unlocked');await refresh();
   assert.equal(await locked.locator('.game-stock-unlock').count(),0,'Unlocked product drops its quest gate');
   assert.equal(await locked.evaluate(el=>el.classList.contains('is-locked')),false,'Unlocked stock restores the normal style');
   assert.equal(await locked.evaluate(el=>[el,...el.querySelectorAll('*')].some(node=>/grayscale\(1\)|grayscale\(100%\)/.test(getComputedStyle(node).filter))),false,'Unlocked product regains its color');
   await fit('garage-unlocked-stock');

   await select('roastery');
   await openActivities('quests');
   assert.match(await page.locator('#game-activities').textContent(),/Breakfast Club/,'Roastery keeps its dedicated original workshop');
   assert.deepEqual(await quests.evaluateAll(buttons=>buttons.map(b=>b.dataset.gameQuest).sort()),['roastery-plan','roastery-signature']);
   await close('game-activities');await openActivities('projects');
   assert.deepEqual(await page.locator('#game-activities [data-game-project]').evaluateAll(buttons=>buttons.map(b=>b.dataset.gameProject)),['cafe_opening']);
   await page.locator('#game-activities [data-game-project="cafe_opening"]').click();
   assert.match(await page.locator('#game-project').textContent(),/Open the neighborhood cafe/);
   assert(await page.locator('#game-project [data-econ-action^="fulfill:"]').isVisible(),'Available project exposes its delivery');
   assert(await page.locator('#game-project [data-econ-action^="commit:"]').isVisible(),'Available project can reserve its goods');
   await fit('roastery-current-project');await close('game-project');
   if(await page.locator('#game-activities').isVisible())await close('game-activities');
   const project=state.townProjects.projects.find(p=>p.id==='cafe_opening');
   Object.assign(project,{status:'locked',orderId:null,unlockText:'Complete Serve the harbor lunch first'});
   await refresh();await openActivities('projects');
   await page.locator('#game-activities [data-game-project="cafe_opening"]').click();
   assert.match(await page.locator('#game-project').textContent(),/Complete Serve the harbor lunch first/);
   assert.equal(await page.locator('#game-project [data-econ-action]').count(),0,'Locked project does not offer a current delivery');
   await fit('roastery-locked-project');await close('game-project');
   if(await page.locator('#game-activities').isVisible())await close('game-activities');

   use('supplyChain');await refresh();
   const farm=await select('farm');
   if(await upgradesTab.isVisible())await upgradesTab.click();
   const productionRow=page.locator('.game-operation').filter({has:page.locator('[data-econ-action="upgrade:0:production"]')});
   assert.equal(await productionRow.locator('.game-upgrade-impact .game-upgrade-value').textContent(),'+'+rate(farm.upgrades.production.businessIncomeAfter-farm.upgrades.production.businessIncomeBefore)+' YM/min','Farm preview shows extra income under current customer and supply limits');
   await fit('farm-next-upgrade-income');
   use('supplyChainUpgraded');await refresh();
   assert.equal(state.buildings[0].incomePerMinute-farm.incomePerMinute,farm.upgrades.production.businessIncomeAfter-farm.upgrades.production.businessIncomeBefore,'Advertised business sales gain matches the purchase response');
   const buildingTab=page.getByRole('tab',{name:'Building',exact:true});
   if(await buildingTab.isVisible())await buildingTab.click();
   assert.equal((await page.locator('.game-site [data-business-metric="income"] .game-live-value').textContent()).trim(),rate(state.buildings[0].earnings.operatingIncome)+' YM');

   use('opening');await refresh();await select('farm');
   await fit('starter-town');
   if(await upgradesTab.isVisible())await upgradesTab.click();
   assert.equal(state.buildings[0].upgrades.production.incomeDelta,0,'Starter demand already has enough production');
   assert.equal(await productionRow.locator('.game-upgrade-impact .game-upgrade-value').textContent(),'+0 YM/min','Starter production shows no extra sales when demand is already met');
   assert(state.buildings[0].upgrades.production.optimizedIncomeDelta>0);
   await fit('starter-production-potential');
   await openActivities('projects');
   await page.locator('#game-activities [data-game-project="farm_neighbors"]').click();
   assert(await page.locator('#game-project [data-econ-action^="fulfill:"]').isVisible(),'Starter farm retains a reachable first project');
   await close('game-project');
   await page.close();
  }
  assert.deepEqual(mutations,[]);assert.deepEqual(errors,[]);
  assert.deepEqual(fitProblems,[],'All business content fits and remains legible');
  console.log(JSON.stringify({result:'passed',viewports:3,layouts:checked.length,checks:['business quest filtering','business project filtering and states','keyboard activation and poll focus','greyed stock and signature unlock','dedicated red town cost rate','customer and storage upgrade running costs','starter progression']},null,2));
 }catch(error){
  if(currentPage&&!currentPage.isClosed())await currentPage.screenshot({path:path.join(output,'failure-'+label+'.png'),animations:'disabled'});
  throw error;
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
