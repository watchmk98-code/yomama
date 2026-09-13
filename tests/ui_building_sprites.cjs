/* Isolated preview only. State and art failures are intercepted, with no purchases. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {tiers}=require('../config/economy.v4.json');
const base=process.argv[2]||'http://127.0.0.1:3007';
// These are the delivered sheets. Higher levels retain the latest available art.
const upgradedLevels={
 farm:[2,3],fish_stall:[2],garage:[2,3],workshop:[2,3],solar_coop:[2,3],
 cannery:[2,3],machine_works:[2,3],turbine_field:[2,3],generator:[2,3],
 data_center:[2],solar_array:[2],uplink_center:[2]
};
function expectedArt(id,level){
 if((id==='farm'||id==='roastery')&&level>=6)return '/upgrades/'+id+'-level-6.png';
 if(id==='roastery'&&level>=3)return '/upgrades/roastery-level-3.png';
 const available=(upgradedLevels[id]||[]).filter(candidate=>candidate<=level);
 if(available.length)return '/upgrades/animated/'+id+'-level-'+available.at(-1)+'_8f.png';
 return '/spritesheets/'+id+'_8f.png';
}
(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const s=await response.json(), original=s.buildings[0];
 s.buildings=tiers.map((t,slot)=>({...structuredClone(original),id:t.id,name:t.name,tier:slot,slot,artLevel:2}));
 s.buildingsOwned=tiers.length;s.paused=false;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'no-preference'});
  // Mocked state advances through explicit refreshes; background polls would
  // replace image nodes during inspection and abort their uncached requests.
  await page.addInitScript(()=>{window.setInterval=()=>0;});
  const errors=[],missingArt=[];page.on('pageerror',e=>errors.push(e.message));
  let failUpgrade=false,failBase=false;
  page.on('response',response=>{
   if(!failUpgrade&&response.status()>=400&&new URL(response.url()).pathname.startsWith('/assets/buildings/'))missingArt.push(response.url());
  });
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   if(failUpgrade&&url.pathname.includes('/upgrades/animated/'))return route.fulfill({status:404,body:''});
   if(failBase&&url.pathname.includes('/buildings/spritesheets/'))return route.fulfill({status:404,body:''});
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   if(url.pathname.endsWith('/quiz'))return route.fulfill({json:{questions:[],passMark:4}});
   if(url.pathname.endsWith('/login'))return route.fulfill({json:s});
   assert.equal(route.request().method(),'GET','sprite checks must not change a save');
   return route.fulfill({json:s});
  });
  await page.goto(base+'/buildings.html');await page.locator('.game-site').waitFor();
  const main=page.locator('.game-site .k-art img');
  async function assertStaticArt(locator,label){
   const motion=await locator.evaluate(img=>({
    animationName:getComputedStyle(img).animationName,
    transform:getComputedStyle(img).transform,
    animations:img.getAnimations().length
   }));
   assert.deepEqual(motion,{animationName:'none',transform:'none',animations:0},label+' stays on its first frame without animations');
   assert.equal(await page.locator('[data-build-art]').count(),0,'building motion cannot be enabled');
  }
  async function waitForBuildingArt(){
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('.k-art > img')).every(img=>img.complete&&img.naturalWidth>0));
  }
  async function selectBuilding(slot){
   await waitForBuildingArt();
   const target=page.locator('[data-select-building="'+slot+'"]');
   for(let attempt=0;attempt<tiers.length&&!await target.isVisible();attempt++){
    const first=Number(await page.locator('.game-roster-list [data-select-building]:visible').first().getAttribute('data-select-building'));
    const direction=slot<first?'Previous':'Next';
    const pager=page.getByRole('button',{name:direction+' buildings page',exact:true});
    assert(await pager.isEnabled(),direction+' building page must reveal slot '+slot);
    await pager.click();
   }
   assert(await target.isVisible(),'building '+slot+' is visible through the roster pager');
   await target.click();
   await waitForBuildingArt();
  }
  for(const level of [1,2,3,6]){
   s.buildings.forEach(b=>b.artLevel=level);await page.evaluate(()=>window.YomamaEcon.refresh());
   for(const [slot,t] of tiers.entries()){
    await selectBuilding(slot);
    await main.evaluate(img=>img.decode());
    const expected=expectedArt(t.id,level);
    assert((await main.getAttribute('src')).endsWith(expected),t.id+' level '+level+' uses '+expected);
    if(expected.includes('/animated/'))assert(await main.evaluate(img=>img.naturalWidth===img.naturalHeight*2),'four columns and two rows of square frames');
    else if(expected.includes('/spritesheets/'))assert(await main.evaluate(img=>img.naturalWidth===img.naturalHeight*8),'eight horizontal square frames');
    const roster=page.locator('[data-select-building="'+slot+'"] .k-art img');
    assert.equal(await roster.getAttribute('src'),await main.getAttribute('src'));
    await assertStaticArt(main,t.id+' level '+level+' main art');
    await assertStaticArt(roster,t.id+' level '+level+' roster art');
   }
  }
  s.buildings.forEach(b=>b.artLevel=3);await page.evaluate(()=>window.YomamaEcon.refresh());
  await selectBuilding(0);
  await main.evaluate(img=>img.decode());
  // Retain the upgraded sheet while displaying exactly its first square cell.
  const firstFrame=await main.evaluate(img=>{
   const frame=img.parentElement.getBoundingClientRect(), sheet=img.getBoundingClientRect();
   return [Math.round(sheet.width/frame.width),Math.round(sheet.height/frame.height),Math.round(sheet.left-frame.left),Math.round(sheet.top-frame.top)];
  });
  assert.deepEqual(firstFrame,[4,2,0,0]);
  await assertStaticArt(main,'upgraded grid art');
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({animations:'disabled',fullPage:true,path:'previews/upgraded-building-sprites-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.body.classList.contains('game-compact'));
  await assertStaticArt(main,'mobile art');
  await page.screenshot({animations:'disabled',fullPage:true,path:'previews/upgraded-building-sprites-mobile.png'});
  await page.setViewportSize({width:1366,height:768});
  await page.waitForFunction(()=>!document.body.classList.contains('game-compact'));
  await page.evaluate(()=>window.YomamaEcon.refresh());
  await waitForBuildingArt();
  await assertStaticArt(main,'refreshed art');
  await page.reload();await main.waitFor();
  await waitForBuildingArt();
  await assertStaticArt(main,'reloaded art');
  s.paused=true;await page.evaluate(()=>window.YomamaEcon.refresh());
  await waitForBuildingArt();
  await assertStaticArt(main,'paused game art');
  s.paused=false;await page.evaluate(()=>window.YomamaEcon.refresh());
  await waitForBuildingArt();
  await assertStaticArt(main,'resumed game art');
  await page.emulateMedia({reducedMotion:'reduce'});
  await assertStaticArt(main,'reduced motion art');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await assertStaticArt(main,'normal motion art');
  await page.goto(base+'/advanced-hq.html');await page.locator('.game-business-picker').waitFor();
  const picker=page.locator('.game-business-picker .k-art img');
  await picker.evaluate(img=>img.decode());
  assert((await picker.getAttribute('src')).endsWith('-level-3_8f.png'));
  await assertStaticArt(picker,'management picker art');
  assert.deepEqual(missingArt,[],'normal progression must never request missing building assets');
  // Missing sheets fall back to the original strip, then the retained static art.
  failUpgrade=true;await page.goto(base+'/buildings.html');
  await selectBuilding(0);
  await page.waitForFunction(()=>{const img=document.querySelector('.game-site .k-art img');return img&&img.src.endsWith('/spritesheets/farm_8f.png')&&img.complete&&img.naturalWidth>0;});
  assert((await main.getAttribute('src')).endsWith('/spritesheets/farm_8f.png'));
  assert.equal(await main.evaluate(img=>img.parentElement.classList.contains('k-art--grid')),false);
  await assertStaticArt(main,'fallback strip art');
  failBase=true;await page.reload();
  await page.waitForFunction(()=>{const img=document.querySelector('.game-site .k-art img');return img&&img.src.endsWith('/upgrades/farm-level-3.png')&&img.complete&&img.naturalWidth>0;});
  assert((await main.getAttribute('src')).endsWith('/upgrades/farm-level-3.png'));
  await assertStaticArt(main,'fallback still art');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',buildingLevelChecks:60,upgradedSheets:20,permanentlyStatic:true,refresh:true,reload:true,pause:true,reducedMotion:true,fallbacks:2,screenshots:2}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
