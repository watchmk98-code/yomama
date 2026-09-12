/* New player decisions; every mutation is intercepted and never reaches a save. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3004';
(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const s=await response.json();s.cash=10000;s.rulesRevision=2;s.regularDeliveries=1;
 s.buildings=s.buildings.slice(0,3);s.buildingsOwned=3;s.board=s.board.filter(g=>g.slot<3);
 s.buildings.forEach(b=>{b.artLevel=3;b.focusUnlocked=true;b.lv=3;b.focus='balanced';});
 delete s.contracts.offers[2].project;delete s.contracts.offers[2].completed;s.contracts.offers[2].customer='breakfast';s.contracts.offers[2].name='Breakfast regulars';
 s.contracts.offers.forEach(o=>{o.committed=false;o.replaceRemainingSec=0;});
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});const errors=[],calls=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   const endpoint=url.pathname.split('/').slice(4).join('/');
   if(endpoint==='quiz'&&route.request().method()==='GET')return route.fulfill({json:{questions:[],passMark:4}});
   if(route.request().method()==='POST'&&endpoint!=='login'){
    const data=route.request().postDataJSON();calls.push({endpoint,data});
    if(endpoint==='orders/commit'){
     const o=s.contracts.offers[data.offerIndex];assert.equal(o.id,data.orderId);o.committed=data.committed;
    }
    if(endpoint==='focus')s.buildings[data.slot].focus=data.focus;
   }
   return route.fulfill({json:s});
  });
  async function go(file){await page.goto(base+'/'+file+'.html');await page.locator('.game-resources,.game-wallet').waitFor();}
  await go('marketplace');
  await page.locator('.game-order-commit').first().click();
  await page.waitForFunction(()=>document.querySelector('.game-order-commit').getAttribute('aria-pressed')==='true');
  assert.equal(calls.at(-1).endpoint,'orders/commit');assert.equal(calls.at(-1).data.committed,true);
  await page.reload();await page.locator('.game-order-commit[aria-pressed=true]').waitFor();
  await page.locator('.game-order-commit').first().click();
  await page.waitForFunction(()=>document.querySelector('.game-order-commit').getAttribute('aria-pressed')==='false');
  assert.equal(calls.at(-1).data.committed,false);
  assert(await page.getByText('Saved delivery · original reward preserved; your next card shows town projects').count());
  s.contracts.offers[0].replaceRemainingSec=45;await page.evaluate(()=>window.YomamaEcon.refresh());
  assert(await page.locator('[data-econ-action^="replace:0:"]').isEnabled());
  await go('advanced-hq');await page.locator('#game-business-choice').selectOption('0');
  const focus=page.locator('[data-business-focus="0"]');await focus.selectOption('supply');
  await page.waitForFunction(()=>document.querySelector('[data-business-focus]').value==='supply');
  assert.equal(calls.at(-1).endpoint,'focus');assert.equal(calls.at(-1).data.focus,'supply');
  await go('buildings');await page.locator('[data-select-building="0"]').click();
  assert(await page.locator('.game-upgrade-impact').count());
  for(const [slot,id] of [[0,'farm'],[2,'roastery']]){
   await page.locator('[data-select-building="'+slot+'"]').click();
   for(const level of [2,3,6]){
    s.buildings[slot].artLevel=level;await page.evaluate(()=>window.YomamaEcon.refresh());
    const art=page.locator('.game-site .k-art img');
    await art.evaluate(img=>img.decode());assert(await art.evaluate(img=>img.naturalWidth>0));
    const expected=id==='farm'&&level<6?'/upgrades/animated/farm-level-'+level+'_8f.png':id==='roastery'&&level===2?'/spritesheets/roastery_8f.png':'/upgrades/'+id+'-level-'+level+'.png';
    assert((await art.getAttribute('src')).endsWith(expected));
    await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(250);
    await page.screenshot({animations:'disabled',path:'previews/'+id+'-level-'+level+'-in-game.png'});
   }
  }
  await page.setViewportSize({width:390,height:844});await go('marketplace');
  await page.screenshot({path:'previews/progression-market-mobile.png'});
  s.gateOpen=true;await go('license');assert.equal(await page.locator('#econ-keep-range').count(),0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',decisions:calls.length,buildingArtVariants:6,screenshots:7}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
