/* Connected business progression and preserved legacy controls.
   All writes are intercepted; run against an isolated signed-in preview:
   node tests/ui_connected_progression.cjs http://127.0.0.1:3097 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=new URL(process.argv[2]||'http://127.0.0.1:3097').origin;
const output=path.join(root,'.checks','connected-progression');
const clone=value=>JSON.parse(JSON.stringify(value));
const samples=JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import json
import production_economy as E
import business_progression as P
def sample(connected,workshop=False):
    cfg=E.load_config()
    cfg['businessDesign']['connectedProgression']=connected
    st=E.new_state(cfg,seed=41)
    st['cash']=5000
    st['b'][0]['lv']=3
    if connected:
        st['b'].append(E._building(3,lv=3))
        st['tierOf'].append(3)
    if workshop:
        q=P.payload(cfg,st)['quests'][0]
        assert P.act(cfg,st,dict(action='quest_plan',questId=q['id'],choice=q['choices'][0]['id']))['ok']
    data=E.payload(cfg,st,E.new_class(cfg),dict(paused=False))
    data.update(overnightReport=None,classCompetition=False,receipt=None)
    return data
print(json.dumps(dict(connected=sample(True),legacy=sample(False),workshop=sample(False,True))))
`],{cwd:root,encoding:'utf8'}));

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 assert.equal(samples.connected.progression.mode,'connected');
 assert.equal(samples.connected.groupProjects.enabled,true);
 assert.equal(samples.connected.contracts.offers.length,3,'All three containers must be active orders.');
 let state=clone(samples.connected), calls=[];
 state.progression.prestige=1;state.progression.prestigeEarned=5;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.setDefaultTimeout(10000);
  page.on('pageerror',e=>{errors.push(e.message);if(process.env.CONNECTED_UI_DEBUG)console.error(e.message);});
  if(process.env.CONNECTED_UI_DEBUG)page.on('request',r=>{if(r.method()==='POST')console.log('POST',r.url());});
  function updateFocus(){
   const team=state.workforce.teams[0];
   team.nodes.forEach(n=>{
    if(n.owned){n.canBuy=false;return;}
    const preceding=(n.requires||[]).every(id=>team.nodes.some(x=>x.id===id&&x.owned));
    n.canBuy=preceding&&!n.id.endsWith('-advanced')&&state.progression.prestige>=(n.prestigeCost||0);
    n.why=n.canBuy?'':!preceding?'Complete the preceding focus first':n.id.endsWith('-advanced')?'Complete this business’s signature quest':'Need more Prestige';
   });
  }
  updateFocus();
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==base)return route.abort();
   if(request.method()==='POST'&&url.pathname.startsWith('/api/game/')){
    const body=request.postDataJSON();calls.push({path:url.pathname,body});
    if(url.pathname==='/api/game/progression'){
     const q=state.progression.quests.find(q=>q.id===body.questId);
     if(body.action==='quest_plan'){q.selectedChoice=body.choice;q.status='tracking';}
     if(body.action==='quest_finish'){q.status='done';q.ready=false;state.progression.prestige++;state.progression.prestigeEarned++;}
     if(body.action==='group_project_claim'){assert.equal(body.projectId,state.groupProjects.current.projectId);state.groupProjects.completed=state.groupProjects.total;state.groupProjects.current=null;}
     if(body.action==='legacy_project_deliver')delete state.groupProjects.legacyDelivery;
    }
    if(url.pathname==='/api/game/workforce'&&body.action==='focus'){
     const node=state.workforce.teams[0].nodes.find(n=>n.id===body.nodeId);
     state.cash-=node.cost;state.progression.prestige-=node.prestigeCost||0;node.owned=true;updateFocus();
    }
    if(url.pathname.endsWith('/orders/replace')){
     const offers=state.contracts.offers;offers[body.offerIndex].id+='-next';
    }
    state.receipt={message:'Saved'};
    return route.fulfill({json:state});
   }
   if(url.pathname==='/api/game/state'||url.pathname.startsWith('/api/game/econ/'))return route.fulfill({json:state});
   if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
   return route.continue();
  });
  async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await page.waitForTimeout(90);}
  async function act(selector){if(process.env.CONNECTED_UI_DEBUG)console.log('Click',selector);const [reply]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/api/game/')),page.locator(selector).first().click()]);assert(reply.ok());await page.waitForTimeout(90);}
  await page.goto(base+'/marketplace.html');await page.locator('.game-order-grid').waitFor();
  assert.equal(await page.locator('[data-order-slot]').count(),3);
  assert.equal(await page.locator('#town-project').count(),0);
  assert.equal(await page.locator('.game-order [data-econ-action^="replace:"]').count(),3);
  await page.screenshot({path:path.join(output,'market-before-actions.png')});
  for(let i=0;i<3;i++){
   const selector='[data-order-slot="'+i+'"] [data-econ-action^="replace:"]';
   if(!await page.locator(selector).isVisible())await page.locator('.game-pager[data-page="Orders"] button').last().click();
   await act(selector);
  }
  assert.deepEqual(calls.filter(c=>c.path.endsWith('/orders/replace')).map(c=>c.body.offerIndex),[0,1,2]);
  await page.screenshot({path:path.join(output,'market-three-orders.png')});

  await page.goto(base+'/buildings.html');await page.locator('#game-activity-open-projects').waitFor();
  assert.match(await page.locator('[data-activity-kind="projects"]').textContent(),/Group projects/);
  await page.goto(base+'/buildings.html#group-projects');
  await page.locator('#game-activities[open]').waitFor();
  assert.equal(await page.locator('#game-activities .game-group-project').count(),1);
  assert.match(await page.locator('#game-activities .game-quest-reward').textContent(),/15 YM/);
  assert.equal(await page.locator('#game-activities [data-econ-action^="group_project_claim:"]').isDisabled(),true);
  await page.locator('#game-activities-close').click();
  if(await page.locator('.game-fit-picker').isVisible())await page.locator('.game-fit-picker').selectOption('1');
  else await page.locator('[data-select-building="1"]').click();
  const stockTab=page.getByRole('tab',{name:'Stock',exact:true});
  if(await stockTab.isVisible())await stockTab.click();
  const locked=page.locator('[data-stock-locked="true"] [data-game-quest]').first();
  assert.equal(await locked.getAttribute('data-game-quest'),'garage-plan');
  for(let i=0;!await locked.isVisible()&&i<3;i++)await page.getByRole('button',{name:'Next inventory page',exact:true}).click();
  await locked.click();
  assert.equal(await page.locator('#game-quest [data-connected-quest="garage-plan"]').count(),1);
  await page.locator('#game-quest-close').click();
  await page.goto(base+'/advanced-hq.html#quests');
  await page.locator('#game-business-choice').selectOption('0');
  await page.locator('[data-game-quest="farm-plan"]').click();
  assert.equal(await page.locator('#game-quest .game-connected-quest').count(),1);
  assert.equal(await page.locator('#game-quest [data-econ-action*="quest_batch"]').count(),0);
  assert.equal(await page.locator('#game-quest [data-econ-action*="quest_reset"]').count(),0);
  const q=state.progression.quests.find(q=>q.id==='farm-plan');
  await act('#game-quest [data-econ-action^="progression:quest_plan:"]');
  assert.equal(await page.locator('#game-quest [data-econ-action^="progression:quest_finish:"]').isDisabled(),true);
  q.objectives.forEach(o=>{o.owned=o.quantity;o.ready=true;});q.ready=true;
  await refresh();
  assert.equal(await page.locator('#game-quest .game-connected-objectives .k-good').count(),q.objectives.length);
  await act('#game-quest [data-econ-action^="progression:quest_finish:"]');
  assert.equal(await page.locator('#game-quest .game-quest-complete').count(),1);
  await page.locator('#game-quest-close').click();
  await page.locator('[data-game-growth]').click();
  assert.equal(await page.locator('#game-growth [data-growth-tab="equipment"]').count(),0);
  assert.equal(await page.locator('#game-growth [data-econ-action^="progression:craft:"]').count(),0);
  assert.match(await page.locator('.game-growth-balance').textContent(),/Prestige available.*earned/);
  await page.locator('#game-growth-close').click();

  state.progression.prestige=1;updateFocus();
  await page.goto(base+'/advanced-hq.html');await page.locator('.wf-workspace').waitFor();
  assert.equal(await page.locator('#game-wf-tab-projects').count(),1);
  assert.match(await page.locator('[data-wf-prestige]').textContent(),/1 Prestige available/);
  assert.match(await page.locator('#game-wf-node-orientation').textContent(),/Free/);
  await act('#game-wf-node-orientation');
  await page.locator('#game-wf-map-production').click();
  assert.match(await page.locator('#game-wf-node-production').textContent(),/1 Prestige.*24 YM/);
  await act('#game-wf-node-production');
  assert.match(await page.locator('[data-wf-prestige]').textContent(),/0 Prestige available/);
  await page.locator('#game-wf-map-sales').click();
  assert.equal(await page.locator('#game-wf-node-sales').isDisabled(),true);
  assert.match(await page.locator('.wf-node-why').textContent(),/Prestige/);
  await page.locator('#game-wf-map-production-advanced').click();
  assert.match(await page.locator('#game-wf-node-production-advanced').textContent(),/2 Prestige.*48 YM/);
  for(const size of [{width:1366,height:768},{width:390,height:844}]){
   await page.setViewportSize(size);await page.locator('#game-wf-tab-focus').click();
   await page.evaluate(()=>window.YomamaWorkforce.fit());
   assert(await page.locator('.wf-focus-layout').evaluate(el=>{
    const map=el.querySelector('.wf-focus-map').getBoundingClientRect(),detail=el.querySelector('.wf-focus-detail').getBoundingClientRect();
    return innerWidth>540||map.bottom<=detail.top+1;
   }),'Mobile focus map and selected node must not overlap.');
   await page.screenshot({path:path.join(output,'focus-'+size.width+'.png')});
   await page.locator('#game-wf-tab-projects').click();
   assert.equal(await page.locator('#game-wf-panel .game-group-project').count(),1);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(output,'group-projects-'+size.width+'.png')});
   await page.locator('#game-wf-panel .game-confirm-actions').scrollIntoViewIfNeeded();
   assert(await page.locator('#game-wf-panel .game-confirm-actions').evaluate(el=>{
    const r=el.getBoundingClientRect(),panel=el.closest('.wf-scroll').getBoundingClientRect();
    return r.top>=panel.top-1&&r.bottom<=panel.bottom+1&&r.bottom<=innerHeight;
   }),'Group claim and order controls must be reachable inside the project panel.');
   await page.screenshot({path:path.join(output,'group-controls-'+size.width+'.png')});
  }
  const project=state.groupProjects.current;
  project.ready=project.canClaim=true;project.status='ready';project.why='';project.requirements.forEach(g=>g.delivered=g.quantity);
  await refresh();await act('#game-wf-panel [data-econ-action^="group_project_claim:"]');
  assert.match(await page.locator('#game-wf-panel').textContent(),/Group projects complete/);
  state=clone(samples.connected);
  state.groupProjects.legacyDelivery={id:'saved-project',name:'Saved delivery',reward:77,canFulfill:true,requirements:[{name:'Tomatoes',quantity:6,owned:6}]};
  await refresh();
  assert.equal(await page.locator('[data-legacy-project]').count(),1);
  assert.equal(await page.locator('[data-econ-action^="group_project_claim:"]').count(),0);
  await act('[data-econ-action^="legacy_project_deliver:"]');
  assert.equal(calls.at(-1).body.id,'saved-project');

  // An already-started practice quest remains finishable after adoption.
  state.progression.quests[0]=clone(samples.workshop.progression.quests[0]);
  await refresh();await page.locator('#game-wf-tab-quests').click();
  await page.locator('[data-game-quest="farm-plan"]').click();
  assert(await page.locator('#game-quest [data-econ-action*="quest_batch"]').count()>0);
  assert.equal(await page.locator('#game-quest [data-econ-action*="quest_reset"]').count(),1);
  await page.locator('#game-quest-close').click();
  state=clone(samples.legacy);
  await page.goto(base+'/advanced-hq.html');await page.locator('.wf-workspace').waitFor();
  assert.equal(await page.locator('#game-wf-tab-projects').count(),0);
  assert.equal(await page.locator('[data-wf-prestige]').count(),0);
  await page.locator('[data-game-growth]').click();
  assert.equal(await page.locator('#game-growth [data-growth-tab="equipment"]').count(),1);
  await page.locator('#game-growth-close').click();
  await page.goto(base+'/marketplace.html');await page.locator('.game-order-grid').waitFor();
  assert.equal(await page.locator('#town-project').count(),1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',actions:calls.length,coverage:'three active orders, real quest counters and rewards, group claims outside board, Prestige prices/spending, disabled equipment, adopted practice quest, legacy snapshots',screenshots:output}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
