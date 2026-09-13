/* Prestige milestones and contextual construction requirements.
   Engine snapshots and one quest reward are served by interception; no town
   mutation reaches the preview. Run against a signed-in local preview:
   node tests/ui_prestige_progression.cjs http://127.0.0.1:3012 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const base=new URL(process.argv[2]||'http://127.0.0.1:3012').origin;
const output=path.join(root,'.checks','prestige-progression');
const clone=value=>JSON.parse(JSON.stringify(value));

function engineSnapshots(){
 return JSON.parse(execFileSync(path.join(root,'.venv','bin','python'),['-c',String.raw`
import copy,json
import production_economy as E
import business_progression as P
import breakfast_event as B
cfg=E.load_config()
assert cfg['businessDesign']['prestigeExpansion']
st=E.new_state(cfg,seed=29)
cls=E.new_class(cfg)
st.update(tierOf=list(range(8)),b=[E._building(i,lv=3,sales=2) for i in range(8)],cash=10000000,materials=100,offers=None)
st=E.migrate_state(cfg,st)
E.offer_contracts(cfg,st,st['tick'])
def pack(rules=None):
    rules=rules or cfg
    p=E.payload(rules,st,cls,dict(paused=False))
    p['breakfastEvent']=B.payload(st,st['tick']*rules['global']['tick'],cfg=rules)
    p.update(classCompetition=False,overnightReport=None,receipt=None)
    return p
samples={'blocked':pack()}
old=copy.deepcopy(cfg)
old['businessDesign'].pop('prestigeExpansion')
samples['legacy']=pack(old)
assert not samples['legacy']['progression']['prestigeMilestones']
assert next(b for b in samples['legacy']['frontier'] if b['id']=='turbine_field')['canExpand']
def act(action,quest,**kwargs):
    result=P.act(cfg,st,dict(action=action,questId=quest,**kwargs))
    assert result['ok'],result
    return result
def prepare(quest):
    signature=quest.endswith('-signature')
    act('quest_plan',quest,choice='careful' if signature else 'regulars')
    for recipe,count in ([('prepare',3),('finish',2)] if signature else [('first',2),('second',2)]):
        for _ in range(count):
            act('quest_batch',quest,recipe=recipe)
for quest in ['farm-plan','farm-signature','fish_stall-plan','fish_stall-signature','garage-plan']:
    prepare(quest)
    act('quest_finish',quest)
prepare('garage-signature')
samples['rewardReady']=pack()
assert samples['rewardReady']['progression']['prestige']==5
assert next(q for q in samples['rewardReady']['progression']['quests'] if q['id']=='garage-signature')['ready']
receipt=act('quest_finish','garage-signature')
samples['earned']=pack()
samples['earned']['receipt']=receipt
assert samples['earned']['progression']['prestige']==6
assert next(b for b in samples['earned']['frontier'] if b['id']=='turbine_field')['canExpand']
print(json.dumps(samples))
`],{cwd:root,encoding:'utf8'}));
}

(async()=>{
 assert(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Use an isolated local preview');
 const response=await fetch(base+'/api/game/econ/state');
 assert(response.ok,'Use a signed-in local preview server');
 const metadata=await response.json(),samples=engineSnapshots();
 assert.equal(metadata.modelVersion,4);
 const browser=await chromium.launch({headless:true});
 const errors=[],unexpectedMutations=[],checked=[],fitProblems=[];
 fs.mkdirSync(output,{recursive:true});
 let currentPage,label='startup';
 try{
  for(const viewport of [{name:'desktop',width:1440,height:900},{name:'mobile',width:390,height:844},{name:'landscape',width:844,height:390}]){
   const page=await browser.newPage({viewport});currentPage=page;
   page.setDefaultTimeout(10000);
   await page.emulateMedia({reducedMotion:'reduce'});
   let state,sample,claimed=0;
   const use=name=>{sample=name;state=Object.assign(clone(metadata),clone(samples[name]));};
   use('blocked');
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==base)return route.abort();
    if(!url.pathname.startsWith('/api/game/'))return route.continue();
    try{
     if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
     if(request.method()!=='GET'&&!url.pathname.endsWith('/login')){
      const body=request.postDataJSON();
      if(url.pathname==='/api/game/progression'&&body.action==='quest_finish'&&body.questId==='garage-signature'&&sample==='rewardReady'){
       claimed++;use('earned');return route.fulfill({json:state});
      }
      unexpectedMutations.push(url.pathname);
      assert.fail('Unexpected town action: '+url.pathname);
     }
     return route.fulfill({json:state});
    }catch(error){errors.push(error.stack||String(error));return route.fulfill({status:500,json:{error:'Isolated UI check rejected this action'}});}
   });
   async function settle(){
    await page.waitForFunction(()=>window.YomamaEcon&&window.YomamaEcon.state()&&!Array.from(document.querySelectorAll('[aria-busy="true"]')).some(el=>el.getClientRects().length));
    await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());
    await page.evaluate(()=>document.fonts.ready);
    await page.waitForFunction(()=>Array.from(document.images).filter(image=>image.getClientRects().length).every(image=>image.complete));
   }
   async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await settle();}
   async function expand(id){
    const tab=page.getByRole('tab',{name:'Expand',exact:true});
    if(await tab.isVisible()){await tab.focus();await page.keyboard.press('Enter');}
    await settle();
    const business=state.frontier.find(b=>b.id===id);assert(business,id+' is on the frontier');
    await page.selectOption('#game-expansion-choice',String(business.tier));await settle();
    assert.equal(await page.inputValue('#game-expansion-choice'),String(business.tier));
    const button=page.locator('.game-expansion [data-econ-action="expand:'+business.tier+'"]');
    assert(await button.isVisible(),'Build action remains visible, including when requirements are missing');
    assert(await button.evaluate(el=>{
     const r=el.getBoundingClientRect(),panel=el.closest('.game-expansion').getBoundingClientRect();
     return r.top>=panel.top-2&&r.bottom<=panel.bottom+2;
    }),viewport.name+' '+id+': Build action stays within its panel, above the business activity footer');
    return page.locator('.game-expansion');
   }
   async function launch(selector,dialog){
    const button=page.locator(selector);assert(await button.isVisible(),selector+' is visible');
    await button.focus();await page.keyboard.press('Enter');
    assert(await page.locator('#'+dialog).isVisible(),'Keyboard opens '+dialog);
    await settle();
   }
   async function close(id){
    await page.evaluate(id=>{window.__prestigeDialogClosed=false;document.getElementById(id).addEventListener('close',()=>{window.__prestigeDialogClosed=true;},{once:true});},id);
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>window.__prestigeDialogClosed);
    assert.equal(await page.locator('#'+id).isVisible(),false);
   }
   async function reachable(locator){
    await locator.scrollIntoViewIfNeeded();
    assert(await locator.evaluate(el=>{
     const r=el.getBoundingClientRect(),area=el.closest('.game-dialog-content').getBoundingClientRect();
     return r.top>=area.top-2&&r.bottom<=Math.min(area.bottom,innerHeight)+2;
    }),'Lower dialog content can be scrolled fully into view');
   }
   async function fit(name){
    label=viewport.name+'-'+name;await settle();
    const issues=await page.evaluate(()=>{
     const issues=[],margin=2,dialog=Array.from(document.querySelectorAll('dialog[open]')).at(-1);
     const visible=el=>el.getClientRects().length&&!el.closest('[hidden],.game-view-hidden');
     const identify=el=>(el.id?'#'+el.id:el.className||el.tagName)+' '+el.textContent.trim().replace(/\s+/g,' ').slice(0,70);
     if(document.documentElement.scrollWidth>innerWidth+margin)issues.push('Document horizontal overflow');
     if(!dialog&&document.documentElement.scrollHeight>innerHeight+margin)issues.push('Document vertical overflow');
     const scope=dialog||document.querySelector('.game-workspace');
     for(const el of scope.querySelectorAll('[data-requirement-kind],[data-prestige-building],[data-research-id],[data-equipment-id],.game-expansion h3,button,select')){
      if(!visible(el))continue;
      const r=el.getBoundingClientRect();
      if(r.left< -margin||r.right>innerWidth+margin||(!dialog&&(r.top< -margin||r.bottom>innerHeight+margin)))issues.push('Outside viewport: '+identify(el));
      if(el.matches('button,h3')&&(el.scrollWidth>el.clientWidth+margin||el.scrollHeight>el.clientHeight+margin))issues.push('Clipped text: '+identify(el));
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

   await page.goto(base+'/buildings.html');await page.locator('#game-expansion-choice').waitFor({state:'attached'});await settle();
   const turbine=await expand('turbine_field');
   const prestige='[data-requirement-kind="prestige"]';
   assert.match(await turbine.locator(prestige).textContent(),/0\s*\/\s*6/,'Construction shows current and required Prestige');
   assert(await turbine.locator('[data-econ-action="expand:8"]').isDisabled(),'A cash-rich town still needs the permanent qualification');
   const prestigeId=await page.locator(prestige).getAttribute('id');assert(prestigeId,'Requirement launchers have stable focus IDs');
   await page.locator(prestige).focus();await refresh();
   assert.equal(await page.evaluate(()=>document.activeElement.id),prestigeId,'Polling preserves construction requirement focus');
   await fit('prestige-requirement');
   const selectedBusiness=await page.locator('.game-building-activity[data-activity-kind="quests"]').getAttribute('data-activity-building');
   await page.keyboard.press('Enter');
   assert(await page.locator('#game-activities').isVisible());
   assert.match(await page.locator('#game-activities').textContent(),/prestige/i);
   const questBusiness=page.locator('#game-activity-business');
   assert(await questBusiness.isVisible(),'Prestige shortcut can choose among owned business quests');
   assert.equal(await questBusiness.locator('option').count(),state.buildings.length);
   assert.deepEqual(await page.locator('#game-activities [data-game-quest]').evaluateAll(buttons=>buttons.map(b=>b.dataset.gameQuest).sort()),[selectedBusiness+'-plan',selectedBusiness+'-signature'],'Prestige starts with the selected owned business');
   await fit('prestige-quests');await close('game-activities');
   assert.equal(await page.evaluate(()=>document.activeElement.id),prestigeId,'Closing returns focus to the requirement');

   await launch('[data-game-growth]','game-growth');
   await page.locator('[data-growth-tab="prestige"]').click();
   const milestones=page.locator('[data-prestige-building]');
   assert.deepEqual(await milestones.evaluateAll(cards=>cards.map(c=>c.dataset.prestigeBuilding)),['turbine_field','relay_station','solar_array']);
   for(const [id,threshold]of [['turbine_field',6],['relay_station',10],['solar_array',14]])assert.match(await page.locator('[data-prestige-building="'+id+'"]').textContent(),new RegExp('0\\s*\\/\\s*'+threshold));
   assert.match(await page.locator('#game-growth').textContent(),/kept|keep|never spent|not spent|permanent/i,'Prestige explains that construction keeps the qualification');
   await fit('prestige-milestones');
   await reachable(page.locator('[data-prestige-building="solar_array"]'));
   await close('game-growth');

   await expand('generator');
   await fit('generator-requirements');
   await launch('[data-requirement-kind="research"]','game-growth');
   assert.equal(await page.locator('[data-growth-tab="research"]').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('[data-growth-branch="Energy / Tech"]').getAttribute('aria-pressed'),'true');
   const research=page.locator('[data-research-id="energy-basics"]');
   assert(await research.evaluate(el=>el.classList.contains('is-required')),'The required research is highlighted');
   assert(await research.evaluate(el=>el.contains(document.activeElement)),'Research context receives keyboard focus');
   await refresh();
   assert(await research.evaluate(el=>el.contains(document.activeElement)),'Polling preserves focus on the required research');
   await fit('required-research');await close('game-growth');
   await launch('[data-requirement-kind="equipment"]','game-growth');
   assert.equal(await page.locator('[data-growth-tab="equipment"]').getAttribute('aria-pressed'),'true');
   assert.deepEqual(await page.locator('[data-equipment-id]').evaluateAll(cards=>cards.map(c=>c.dataset.equipmentId)),['grid-kit'],'Construction opens its exact kit');
   assert.match(await page.locator('[data-equipment-id="grid-kit"]').textContent(),/Grid control kit/);
   assert(await page.locator('[data-equipment-id="grid-kit"]').evaluate(el=>el.contains(document.activeElement)),'Equipment context receives keyboard focus');
   const researchLink=page.locator('[data-equipment-research="energy-basics"]');
   await researchLink.focus();const researchLinkId=await researchLink.getAttribute('id');await refresh();
   assert.equal(await page.evaluate(()=>document.activeElement.id),researchLinkId,'Polling keeps focus on the kit research shortcut');
   await fit('required-equipment');await page.keyboard.press('Enter');
   assert.equal(await page.locator('[data-growth-tab="research"]').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('[data-growth-branch="Energy / Tech"]').getAttribute('aria-pressed'),'true');
   assert(await research.evaluate(el=>el.classList.contains('is-required')));
   await close('game-growth');await launch('[data-requirement-kind="equipment"]','game-growth');
   await page.locator('[data-growth-all-equipment]').click();
   assert.equal(await page.locator('[data-equipment-id]').count(),6,'All six kits remain accessible');
   await fit('all-equipment');
   await reachable(page.locator('[data-equipment-id="uplink-kit"] [data-econ-action]'));
   await close('game-growth');

   use('rewardReady');await refresh();await expand('turbine_field');
   assert.match(await turbine.locator(prestige).textContent(),/5\s*\/\s*6/);
   await launch(prestige,'game-activities');
   const garageOption=await questBusiness.locator('option').evaluateAll(options=>options.find(o=>/garage/i.test(o.textContent))?.value);
   assert(garageOption!==undefined,'An owned Garage can earn the next point');
   await questBusiness.selectOption(garageOption);await settle();
   assert.deepEqual(await page.locator('#game-activities [data-game-quest]').evaluateAll(buttons=>buttons.map(b=>b.dataset.gameQuest).sort()),['garage-plan','garage-signature']);
   await questBusiness.focus();await refresh();
   assert.equal(await page.evaluate(()=>document.activeElement.id),'game-activity-business','Polling preserves the owned business selector');
   assert.equal(await questBusiness.inputValue(),garageOption,'Polling preserves the chosen quest business');
   await page.locator('#game-activities [data-game-quest="garage-signature"]').click();
   assert(await page.locator('#game-quest').isVisible());
   await page.locator('[data-econ-action="progression:quest_finish:garage-signature"]').click();
   await page.waitForFunction(()=>window.YomamaEcon.state().progression.prestige===6);await settle();
   assert.equal(claimed,1,'Exactly one isolated quest reward is claimed');
   assert(await page.locator('#game-quest .game-quest-complete').isVisible());
   await close('game-quest');if(await page.locator('#game-activities').isVisible())await close('game-activities');
   await expand('turbine_field');
   assert.match(await turbine.locator(prestige).textContent(),/6\s*\/\s*6/);
   assert.equal(await turbine.locator('[data-econ-action="expand:8"]').isDisabled(),false,'Earning the sixth point opens construction');
   await fit('earned-prestige');
   await launch('[data-game-growth]','game-growth');await page.locator('[data-growth-tab="prestige"]').click();
   assert.match(await page.locator('[data-prestige-building="turbine_field"]').textContent(),/6\s*\/\s*6/);
   assert.match(await page.locator('[data-prestige-building="turbine_field"]').textContent(),/ready|qualified|unlocked/i);
   await refresh();
   assert.equal(state.progression.prestige,6,'Refreshing retains the earned reward');
   await fit('earned-milestone');await close('game-growth');

   use('legacy');await refresh();await expand('turbine_field');
   assert.equal(await page.locator(prestige).count(),0,'An existing snapshot without the new flag gains no Prestige gate');
   assert.equal(await turbine.locator('[data-econ-action="expand:8"]').isDisabled(),false);
   await launch('[data-game-growth]','game-growth');
   assert.equal(await page.locator('[data-growth-tab="prestige"]').count(),0,'Legacy classes do not advertise inactive milestones');
   assert.equal(await page.locator('[data-prestige-building]').count(),0);
   await fit('legacy-research');await close('game-growth');
   await page.close();
  }
  assert.deepEqual(unexpectedMutations,[]);assert.deepEqual(errors,[]);
  assert.deepEqual(fitProblems,[],'Requirements and growth content remain legible');
  console.log(JSON.stringify({result:'passed',viewports:3,layouts:checked.length,checks:['Prestige gate and permanent milestones','contextual research and equipment','owned business quest navigation','keyboard activation and polling focus','isolated real quest reward reaches threshold','legacy snapshot compatibility']},null,2));
 }catch(error){
  if(currentPage&&!currentPage.isClosed())await currentPage.screenshot({path:path.join(output,'failure-'+label+'.png'),animations:'disabled'});
  throw error;
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
