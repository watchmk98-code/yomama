/* Building upgrade feedback regression. All snapshots come from real engine
   purchases and ticks in process memory. Playwright intercepts every API write;
   the local preview supplies only page assets and signed-in response metadata.
   Run: node tests/ui_upgrade_feedback.cjs [http://127.0.0.1:3094] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=new URL(process.argv[2]||'http://127.0.0.1:3094').origin;
assert(['127.0.0.1','localhost','[::1]'].includes(new URL(base).hostname),'Use a local preview, never the live class server');
const output=path.join(root,'.checks','upgrade-feedback');
const clone=value=>JSON.parse(JSON.stringify(value));
const units=value=>value.toLocaleString('en-US',{maximumFractionDigits:2});
const incomeRate=value=>units(value)+' YM';

function engineSnapshots(){
 return JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import copy, json
import production_economy as E
import breakfast_event as B
cfg=E.load_config()
def pack(state):
    payload=E.payload(cfg,state,cls,dict(paused=False))
    payload['breakfastEvent']=B.payload(state,state['tick']*cfg['global']['tick'],cfg=cfg)
    payload['classCompetition']=False
    payload['overnightReport']=None
    return payload
result=dict(scenarios=[])
for seed,kind,metric,prerequisite,count in ((39,'production','producedUnits','sales',2),
                                          (40,'sales','soldUnits','production',1)):
    st=E.new_state(cfg,seed=seed)
    cls=E.new_class(cfg)
    def earn_upgrade(upgrade):
        for _ in range(256):
            if st['cash']>=E.upgrade_cost(cfg,st,0,upgrade):
                return
            E.advance_class(cfg,cls,[st],st['tick'],st['tick']+1)
        raise AssertionError('Farm could not earn '+upgrade+' upgrade')
    # Buy the complementary capacity through the real engine so each tested
    # upgrade removes a current limit: customers 3 for production, production 2
    # for customers. The two towns earn their own upgrade costs independently.
    for _ in range(count):
        earn_upgrade(prerequisite)
        assert E.buy_upgrade(cfg,st,0,prerequisite)['ok']
    E.advance_class(cfg,cls,[st],st['tick'],st['tick']+24)
    earn_upgrade(kind)
    before=pack(st)
    control=copy.deepcopy(st)
    receipt=E.buy_upgrade(cfg,st,0,kind)
    assert receipt['ok'], receipt
    purchased=pack(st)
    assert purchased['buildings'][0]['activity']==before['buildings'][0]['activity']
    assert purchased['earnings']==before['earnings']
    assert purchased['buildings'][0]['earnings']==before['buildings'][0]['earnings']
    assert purchased['cash']==before['cash']-receipt['cost']
    assert receipt['incomeBefore']==before['incomePerMinute']
    assert receipt['incomeAfter']==purchased['incomePerMinute']
    assert receipt['incomeDelta']>0, kind+' scenario must improve income immediately'
    assert purchased['incomePerMinute']>before['incomePerMinute']
    assert purchased['buildings'][0]['incomePerMinute']>before['buildings'][0]['incomePerMinute']
    assert receipt['capacityAfter']>receipt['capacityBefore']
    steps=[]
    for _ in range(16):
        E.advance_class(cfg,cls,[st,control],st['tick'],st['tick']+1)
        future=pack(st)
        reference=pack(control)
        steps.append(future)
        actual=future['buildings'][0]['activity'][metric]
        if actual>before['buildings'][0]['activity'][metric] and actual>reference['buildings'][0]['activity'][metric]:
            break
    else:
        raise AssertionError('Upgrade failed to improve real '+metric+' in 16 ticks')
    result['scenarios'].append(dict(kind=kind,metric=metric,before=before,
                                    receipt=receipt,purchased=purchased,steps=steps,
                                    control=reference,elapsedSeconds=len(steps)*cfg['global']['tick']))
result['initial']=result['scenarios'][0]['before']
print(json.dumps(result))
`],{cwd:root,encoding:'utf8'}));
}

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const response=await fetch(base+'/api/game/econ/state');
 assert(response.ok,'Use a signed-in local preview server');
 const metadata=await response.json();
 assert.equal(metadata.modelVersion,4);
 const samples=engineSnapshots();
 const browser=await chromium.launch({headless:true});
 const observations=[],fitProblems=[],allErrors=[];
 let currentPage,currentLabel='startup';
 try{
  for(const viewport of [{name:'desktop',width:1366,height:768},
                         {name:'mobile',width:390,height:844},
                         {name:'landscape',width:844,height:390},
                         {name:'desktop-legacy',width:1366,height:768,legacy:true}]){
   const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height}});
   currentPage=page;
   currentLabel=viewport.name+'-startup';
   page.setDefaultTimeout(10000);
   await page.emulateMedia({reducedMotion:'reduce'});
   const errors=[],calls=[];
   let state,scenarioIndex=0;
   const use=(sample,receipt=null)=>{state=Object.assign(clone(metadata),clone(sample),{receipt,overnightReport:null,classCompetition:false});};
   function wireState(){
    const payload=clone(state);
    if(viewport.legacy){
     // Older running previews report completed receipts as income while the
     // current earning rate is already available in the potential fields.
     delete payload.operations;
     delete payload.progression;
     payload.incomePerMinute=payload.earnings.operatingIncome;
     for(const business of payload.buildings){
      business.incomePerMinute=business.earnings.operatingIncome;
      for(const upgrade of Object.values(business.upgrades || {})){
       delete upgrade.businessIncomeBefore;
       delete upgrade.businessIncomeAfter;
      }
     }
     if(payload.receipt){
      delete payload.receipt.incomeBefore;
      delete payload.receipt.incomeAfter;
      delete payload.receipt.incomeDelta;
     }
     // Older previews only expose each business forecast, so the HUD must
     // add those rates itself for both kinds of upgrade.
     delete payload.potentialIncomePerMinute;
    }
    return payload;
   }
   use(samples.initial);
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==base)return route.abort();
    if(!url.pathname.startsWith('/api/'))return route.continue();
    try{
     if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
     if(request.method()==='POST'){
      if(url.pathname==='/api/game/econ/login')return route.fulfill({json:wireState()});
      assert.equal(url.pathname,'/api/game/econ/upgrade','Unexpected API mutation is intercepted');
      const data=request.postDataJSON(),scenario=samples.scenarios[scenarioIndex];
      assert(scenario,'No further purchase expected');
      assert.equal(data.slot,0);
      assert.equal(data.kind,scenario.kind);
      calls.push({slot:data.slot,kind:data.kind});
      use(scenario.purchased,clone(scenario.receipt));
      scenarioIndex++;
      return route.fulfill({json:wireState()});
     }
     assert.equal(request.method(),'GET','Unexpected API method is intercepted');
     assert(['/api/game/state','/api/game/econ/state'].includes(url.pathname),'Unexpected API read: '+url.pathname);
     return route.fulfill({json:wireState()});
    }catch(error){
     errors.push(error.stack||String(error));
     return route.fulfill({status:500,json:{error:'Isolated upgrade test rejected this request'}});
    }
   });
   async function settle(){
    await page.waitForFunction(()=>window.YomamaEcon&&window.YomamaEcon.state()&&!document.querySelector('[aria-busy="true"]'));
    await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());
    await page.waitForTimeout(100);
   }
   async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await settle();}
   async function showTab(name){
    const tab=page.getByRole('tab',{name,exact:true});
    if(await tab.count()&&await tab.isVisible()){await tab.click();await settle();}
   }
   const metric=name=>page.locator('.game-site [data-business-metric="'+name+'"]');
   async function checkValues(){
    const b=state.buildings[0];
    assert.equal((await metric('income').locator('.game-live-value').textContent()).trim(),incomeRate(b.incomePerMinute),'Selected business shows its current income rate');
    assert.equal((await page.locator('[data-build-metric="income"] dd').textContent()).replace(/\s+/g,''),incomeRate(state.incomePerMinute).replace(/\s+/g,''),'Town HUD shows its current income rate');
    assert.equal((await metric('produced').locator('.game-live-value').textContent()).trim(),units(b.productionCapacityPerMinute));
    assert.equal((await metric('sold').locator('.game-live-value').textContent()).trim(),units(b.customerCapacityPerMinute));
    const production=(await metric('produced').locator('.game-live-rate').textContent()).trim();
    const demand=(await metric('sold').locator('.game-live-rate').textContent()).trim();
    assert.match(production,new RegExp('Actual '+b.activity.producedUnits+' produced.*last 60s','i'));
    assert.match(demand,new RegExp('Actual '+b.activity.soldUnits+' sold.*last 60s','i'));
    assert.match(await page.locator('.game-live-heading').textContent(),/Live rates|Current estimates/i);
   }
   async function fit(label){
    currentLabel=viewport.name+'-'+label;
    await settle();
    const issues=await page.evaluate(()=>{
     const problems=[],margin=2,scope=document.querySelector('.game-workspace');
     const visible=el=>el.getClientRects().length&&!el.closest('[hidden]')&&getComputedStyle(el).visibility!=='hidden';
     const identify=el=>(el.id?'#'+el.id:el.className||el.tagName)+' '+(el.textContent||'').trim().replace(/\s+/g,' ').slice(0,75);
     if(document.documentElement.scrollWidth>innerWidth+1)problems.push('Document horizontal overflow');
     if(document.documentElement.scrollHeight>innerHeight+1)problems.push('Document vertical overflow');
     if(!scope)return ['Workspace missing'];
     for(const el of scope.querySelectorAll('button,select,.game-live-value,.game-live-rate,.game-upgrade-capacity,.game-upgrade-impact,.game-upgrade-reason,[data-econ-status]:not(:empty)')){
      if(!visible(el))continue;
      const r=el.getBoundingClientRect();
      if(r.left < -margin||r.right>innerWidth+margin||r.top < -margin||r.bottom>innerHeight+margin)problems.push('Outside viewport: '+identify(el));
      if(el.scrollWidth>el.clientWidth+margin)problems.push('Text clipped horizontally: '+identify(el));
      if(el.matches('[data-econ-status],.game-live-value,.game-live-rate,.game-upgrade-capacity')&&el.scrollHeight>el.clientHeight+margin)problems.push('Text clipped vertically: '+identify(el));
      const panel=el.closest('.game-panel');
      if(panel){const p=panel.getBoundingClientRect();if(r.left<p.left-margin||r.right>p.right+margin||r.top<p.top-margin||r.bottom>p.bottom+margin)problems.push('Outside own panel: '+identify(el));}
      for(let ancestor=el.parentElement;ancestor&&ancestor!==scope.parentElement;ancestor=ancestor.parentElement){
       const style=getComputedStyle(ancestor),a=ancestor.getBoundingClientRect();
       if(['hidden','clip'].includes(style.overflowX)&&(r.left<a.left-margin||r.right>a.right+margin))problems.push('Horizontally clipped by '+identify(ancestor)+': '+identify(el));
       if(['hidden','clip'].includes(style.overflowY)&&(r.top<a.top-margin||r.bottom>a.bottom+margin))problems.push('Vertically clipped by '+identify(ancestor)+': '+identify(el));
      }
     }
     const status=scope.querySelector('[data-econ-status]:not(:empty)');
     if(status&&visible(status)){
      const toast=status.getBoundingClientRect();
      for(const el of scope.querySelectorAll('button,select,.game-live-value,.game-live-rate,.game-upgrade-capacity')){
       if(!visible(el)||status.contains(el))continue;
       const r=el.getBoundingClientRect();
       if(Math.min(toast.right,r.right)-Math.max(toast.left,r.left)>margin&&Math.min(toast.bottom,r.bottom)-Math.max(toast.top,r.top)>margin)problems.push('Purchase status covers '+identify(el));
      }
     }
     for(const metric of scope.querySelectorAll('[data-business-metric]')){
      if(!visible(metric))continue;
      const children=Array.from(metric.children).filter(visible);
      for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){
       const a=children[i].getBoundingClientRect(),b=children[j].getBoundingClientRect();
       if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>margin&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>margin)problems.push('Overlapping metric content: '+identify(children[i])+' / '+identify(children[j]));
      }
     }
     // Check complete metric cells and each main section too: a grid can place
     // individually unclipped values over another cell or its next shipment.
     for(const container of scope.querySelectorAll('.game-live-metrics,.game-site,.game-business-overview,.game-build-grid')){
      if(!visible(container))continue;
      const children=Array.from(container.children).filter(visible).filter(el=>getComputedStyle(el).position!=='absolute');
      for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){
       const a=children[i].getBoundingClientRect(),b=children[j].getBoundingClientRect();
       if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>margin&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>margin)problems.push('Overlapping business sections: '+identify(children[i])+' / '+identify(children[j]));
      }
     }
     return [...new Set(problems)];
    });
    if(issues.length)fitProblems.push({view:currentLabel,issues});
    await page.screenshot({path:path.join(output,currentLabel+'.png')});
   }
   await page.goto(base+'/buildings.html');
   await page.locator('.game-site').waitFor();
   if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();
   await settle();
   await checkValues();
   await fit('before-upgrades');
   for(const scenario of samples.scenarios){
    use(scenario.before);await refresh();await checkValues();
    await showTab('Upgrades');
    const button=page.locator('[data-econ-action="upgrade:0:'+scenario.kind+'"]');
    const row=button.locator('xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " game-operation ")]');
    const preview=await button.getAttribute('title');
    const effect=units(scenario.receipt.capacityBefore)+' → '+units(scenario.receipt.capacityAfter);
    assert(preview.includes(effect),preview+' must include '+effect);
    assert(preview.includes(scenario.receipt.capacityUnit),preview);
    assert.equal(await row.locator('.game-upgrade-capacity').count(),0,'Capacity details stay in the tooltip');
    const incomeDelta=scenario.kind==='production'?scenario.receipt.optimizedIncomeDelta:Math.round((scenario.receipt.businessIncomeAfter-scenario.receipt.businessIncomeBefore)*100)/100;
    assert.equal(await row.locator('.game-upgrade-impact').textContent(),'+'+units(incomeDelta)+' YM/min');
    await fit(scenario.kind+'-preview');
    const historical=clone(state.buildings[0].activity);
    const earnings=clone(state.earnings),businessEarnings=clone(state.buildings[0].earnings);
    const incomeBefore=state.incomePerMinute,businessIncomeBefore=state.buildings[0].incomePerMinute,cashBefore=state.cash,tickBefore=state.tick;
    const displayedBefore=await metric('income').locator('.game-live-value').textContent();
    const hudBefore=await page.locator('[data-build-metric="income"] dd').textContent();
    assert(await button.isEnabled());
    await button.click();await settle();
    assert.equal(calls.at(-1).kind,scenario.kind);
    assert.deepEqual(state.buildings[0].activity,historical,'Buying an upgrade must not rewrite historical goods totals');
    assert.deepEqual(state.earnings,earnings,'Buying an upgrade must not credit historical town earnings');
    assert.deepEqual(state.buildings[0].earnings,businessEarnings,'Buying an upgrade must not credit historical business earnings');
    assert.equal(state.tick,tickBefore,'Income updates at the purchase tick without waiting for production');
    assert.equal(state.cash,cashBefore-scenario.receipt.cost,'The purchase deducts only the upgrade cost');
    assert.equal(scenario.receipt.incomeBefore,incomeBefore);
    assert.equal(scenario.receipt.incomeAfter,state.incomePerMinute);
    await checkValues();
    assert(scenario.receipt.incomeDelta>0,'Each scenario must exercise an immediate income increase');
    assert(state.incomePerMinute>incomeBefore,'Town income increases in the purchase response');
    assert(state.buildings[0].incomePerMinute>businessIncomeBefore,'Business income increases in the purchase response');
    assert.notEqual(await metric('income').locator('.game-live-value').textContent(),displayedBefore,'Business income updates before any future tick');
    assert.notEqual(await page.locator('[data-build-metric="income"] dd').textContent(),hudBefore,'HUD income updates before any future tick');
    const status=await page.locator('[data-econ-status]').first().textContent();
    const incomeEffect=units(scenario.receipt.incomeBefore)+' → '+units(scenario.receipt.incomeAfter)+' YM/min';
    assert(status.includes(incomeEffect),status+' must confirm '+incomeEffect);
    assert.match(status,/cash.*sales/i,'Feedback explains when the increased rate becomes cash');
    // A later state poll at this same tick must retain the new income rate,
    // including when historical legacy receipts have not changed yet.
    await refresh();await checkValues();
    await fit(scenario.kind+'-purchased-upgrades');
    await showTab('Building');
    await fit(scenario.kind+'-purchased-building');
    for(const step of scenario.steps){use(step);await refresh();await checkValues();}
    const actual=state.buildings[0].activity[scenario.metric];
    const control=scenario.control.buildings[0].activity[scenario.metric];
    assert(actual>historical[scenario.metric]);
    assert(actual>control,'Completed goods must exceed the same town without this upgrade');
    observations.push({view:viewport.name,upgrade:scenario.kind,
      incomeBefore:scenario.receipt.incomeBefore,incomeAfter:scenario.receipt.incomeAfter,
      capacityBefore:scenario.receipt.capacityBefore,capacityAfter:scenario.receipt.capacityAfter,
      capacityUnit:scenario.receipt.capacityUnit,purchaseCount:historical[scenario.metric],
      laterCount:actual,withoutUpgradeCount:control,elapsedSeconds:scenario.elapsedSeconds});
    await fit(scenario.kind+'-completed-ticks');
   }
   assert.deepEqual(calls.map(call=>call.kind),['production','sales']);
   allErrors.push(...errors.map(error=>viewport.name+': '+error));
   assert.deepEqual(errors,[]);
   await page.close();currentPage=null;
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({observations,fitProblems,errors:allErrors},null,2)+'\n');
  assert.deepEqual(fitProblems,[],'Viewport/content clipping detected; see .checks/upgrade-feedback/results.json');
  console.log('Passed: real production/customer upgrades immediately update business/HUD income on current and legacy payloads, and subsequent polls preserve the rate; cash and historical receipts preserved except upgrade cost; increased actual output against unchanged controls; desktop, mobile and landscape fit.');
  console.log('Screenshots and engine observations: .checks/upgrade-feedback/');
 }catch(error){
  if(currentPage&&!currentPage.isClosed())await currentPage.screenshot({path:path.join(output,currentLabel+'-failure.png')}).catch(()=>{});
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({observations,fitProblems,errors:allErrors,failure:error.stack||String(error)},null,2)+'\n');
  throw error;
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
