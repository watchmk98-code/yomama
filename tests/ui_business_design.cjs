/* Mutating UI smoke for previews/business_design_preview.py --all-buildings only.
   node tests/ui_business_design.cjs http://127.0.0.1:3012 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3012';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route('https://**/*',r=>r.abort());
  await page.goto(base+'/advanced-hq.html');await page.locator('#game-business-choice').waitFor();
  const state=()=>page.evaluate(()=>window.YomamaEcon.state());
  const initial=await state();assert(initial.operations.enabled&&initial.progression.enabled);assert.equal(initial.buildings.length,15,'Use the isolated all-buildings preview.');
  assert.equal(initial.progression.quests.length,30);
  async function act(selector,predicate){const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/api/game/'));await page.locator(selector).click();const res=await response;assert(res.ok(),await res.text());if(predicate)await page.waitForFunction(predicate);}
  await page.selectOption('#game-business-choice','0');
  await page.locator('#game-wf-tab-focus').click();
  if(!(await state()).workforce.teams[0].nodes.find(n=>n.id==='orientation').owned)
   await act('[data-econ-action^="workforce:focus:"]');
  await page.locator('#game-wf-tab-team').click();
  if(!(await state()).workforce.teams[0].hires)
   await act('[data-econ-action^="workforce:hire:"]',()=>window.YomamaEcon.state().workforce.teams[0].hires===1);
  await page.locator('#game-wf-team-business').click();
  await act('#game-wf-business-toggle',()=>window.YomamaEcon.state().buildings[0].paused===true);
  assert((await state()).workforce.teams[0].paused);
  await act('#game-wf-business-toggle',()=>window.YomamaEcon.state().buildings[0].paused===false);
  await page.locator('#game-wf-salvage-open').click();
  assert(await page.locator('#game-business-dialog').isVisible());
  assert.equal(await page.locator('#game-business-dialog [data-econ-action]').isDisabled(),true,'Recovery farm cannot be closed.');
  await page.locator('#game-business-dialog-close').click();
  await page.locator('#game-wf-tab-quests').click();
  async function completeQuest(id,choice,recipeSequence){
   await page.locator('[data-game-quest="'+id+'"]').first().click();
   const q=(await state()).progression.quests.find(q=>q.id===id);
   if(q.status!=='done'){
    if(q.status==='workshop')await act('[data-econ-action="progression:quest_reset:'+id+'"]');
    await act('[data-econ-action="progression:quest_plan:'+id+':'+choice+'"]',()=>document.querySelectorAll('.game-workshop-recipe').length>0);
    for(const recipe of recipeSequence)await act('[data-econ-action="progression:quest_batch:'+id+':'+recipe+'"]');
    await act('[data-econ-action="progression:quest_finish:'+id+'"]',()=>!!document.querySelector('.game-quest-complete'));
   }
   await page.locator('#game-quest-close').click();
  }
  await completeQuest('farm-plan','regulars',['first','first','second','second']);
  await completeQuest('farm-signature','careful',['prepare','prepare','prepare','finish','finish']);
  await page.locator('[data-game-growth]').click();
  const current=await state();
  if(!current.progression.research.find(r=>r.id==='food-basics').owned)await act('[data-econ-action="progression:research:food-basics"]',()=>window.YomamaEcon.state().progression.research.find(r=>r.id==='food-basics').owned);
  await page.locator('[data-growth-tab="equipment"]').click();
  const equipment=(await state()).progression.equipment.find(e=>e.ready);
  if(equipment)await act('[data-econ-action="progression:craft:'+equipment.id+'"]');
  await page.locator('#game-growth-close').click();
  await page.setViewportSize({width:390,height:844});
  await page.locator('#game-wf-tab-quests').click();
  await page.locator('[data-game-quest="farm-plan"]').click();
  assert(await page.locator('#game-quest').isVisible());
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#game-quest').isVisible(),false);
  await page.locator('[data-game-growth]').click();
  await page.locator('[data-growth-tab="research"]').click();
  await page.locator('[data-growth-branch="Energy / Tech"]').click();
  assert.equal(await page.locator('.game-research-card').count(),2);
  await page.locator('#game-growth-close').click();
  await page.goto(base+'/buildings.html');await page.locator('.game-margin-row').waitFor();
  assert.equal(await page.locator('.game-margin-row [data-business-metric]').count(),3);
  assert.equal(await page.locator('[data-business-metric="cost"] dd').evaluate(el=>getComputedStyle(el).color),'rgb(255, 133, 133)');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',quests:30,actions:'hire, pause, resume, salvage review, two quests, research, equipment, mobile dialogs',equipmentCrafted:!!equipment}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
