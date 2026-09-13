/* Test the cosmetic reaction with intercepted API responses; no live sales. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const base=process.argv[2]||'http://127.0.0.1:3003';
(async()=>{
 await fs.mkdir('.checks/order-reactions',{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
  const state=await response.json();assert.equal(state.modelVersion,4);
  state.contracts.offers[0].canFulfill=false;
  state.contracts.offers[0].rarity='standard';
  state.contracts.offers[0].committed=false;
  let reject=false,hold=false,release,serial=0,replacements=0,nextRarity='standard',nextCanFulfill=true,completeProject=false;
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  await page.emulateMedia({reducedMotion:'no-preference'});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   if(url.pathname.endsWith('/orders/replace')){
    const body=route.request().postDataJSON();assert.equal(body.orderId,state.contracts.offers[body.offerIndex].id);
    if(hold){hold=false;await new Promise(resolve=>release=resolve);}
    if(reject){reject=false;return route.fulfill({status:409,json:{error:'Order changed'}});}
    replacements++;state.contracts.offers[body.offerIndex].id='reaction-order-'+(++serial);
    Object.assign(state.contracts.offers[body.offerIndex],{canFulfill:nextCanFulfill,rarity:nextRarity,committed:false});
    state.receipt={kind:'order_replace'};
   }
   if(url.pathname.endsWith('/orders/commit')){
    const body=route.request().postDataJSON();assert.equal(body.orderId,state.contracts.offers[body.offerIndex].id);
    if(hold){hold=false;await new Promise(resolve=>release=resolve);}
    if(reject){reject=false;return route.fulfill({status:409,json:{error:'Order changed'}});}
    state.contracts.offers[body.offerIndex].committed=body.committed;
    state.receipt={kind:'order_commit',committed:body.committed};
   }
   if(url.pathname.endsWith('/orders/fulfill')){
    const body=route.request().postDataJSON(),order=state.contracts.offers[body.offerIndex];
    assert.equal(body.orderId,order.id);
    if(hold){hold=false;await new Promise(resolve=>release=resolve);}
    if(reject){reject=false;return route.fulfill({status:409,json:{error:'Order changed'}});}
    Object.assign(order,{id:'delivered-replacement-'+(++serial),committed:false});
    if(!order.project)Object.assign(order,{rarity:'standard',rarityLabel:'Standard order'});
    if(order.project&&completeProject){order.completed=true;state.townProjects.completed=3;}
    state.receipt={kind:'order',reward:50,materials:1};
   }
   return route.fulfill({json:state});
  });
  await page.goto(base+'/marketplace.html');await page.locator('[data-order-slot="0"]').waitFor();
  if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();
  async function showOrder(slot){
   const card=page.locator('[data-order-slot="'+slot+'"]');
   if(await card.isVisible())return;
   const pager=page.locator('.game-pager[data-page="Orders"]');
   while(await pager.locator('button:first-child:not(:disabled)').count())await pager.locator('button:first-child').click();
   for(let i=0;i<3 && !await card.isVisible();i++)await pager.locator('button:last-child:not(:disabled)').click();
   assert(await card.isVisible(),'Requested order is reachable through the pager');
  }
  // The status banner may cover New Order; keyboard activation still exercises its real handler.
  async function skip(slot=0){await showOrder(slot);await page.locator('[data-order-slot="'+slot+'"] [data-econ-action^="replace:"]').press('Enter');await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));}
  async function save(slot=0){await showOrder(slot);await page.locator('[data-order-slot="'+slot+'"] .game-order-commit').click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));}
  async function deliver(slot=0){await showOrder(slot);await page.locator('[data-order-slot="'+slot+'"] [data-econ-action^="fulfill:"]').click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));}
  async function confirmHeld(){
   for(let tries=0;!release&&tries<100;tries++)await page.waitForTimeout(10);
   assert(release,'The held action reached the API before confirmation');
   const confirm=release;release=undefined;confirm();
  }
  async function reaction(kind,asset,slot=0){
   const selector='[data-'+kind+'-order="'+slot+'"]',face=page.locator(selector);
   await face.waitFor({timeout:2000});
   await page.waitForFunction(selector=>{const image=document.querySelector(selector+' img');return image&&image.complete&&image.naturalWidth>0;},selector,{timeout:2000});
   assert.match(await face.locator('img').getAttribute('src'),new RegExp('/'+asset.replace('.', '\\.')+'(?:\\?|$)'));
   assert.equal(await face.locator('img').evaluate(e=>getComputedStyle(e).imageRendering),'pixelated');
   assert.equal(await face.evaluate(e=>getComputedStyle(e).pointerEvents),'none');
   assert.equal(await page.locator('[data-order-reaction="'+slot+'"]').count(),1);
  }
  // A newly generated ready order must not be mistaken for a missed one.
  await skip();assert.equal(await page.locator('.game-missed-order').count(),0);
  // Spamming past a newly ready offer must react, even when its click was queued.
  state.contracts.offers[0].canFulfill=false;
  await page.evaluate(()=>window.YomamaEcon.refresh());
  hold=true;
  const spamBefore=replacements;
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').press('Enter');
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').evaluate(button=>{
   if(button.disabled)throw new Error('New Order must stay enabled during spam');
   button.click();button.click();
  });
  assert.equal(await page.locator('.game-missed-order').count(),0);
  await confirmHeld();
  await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
  assert.equal(replacements,spamBefore+3);
  assert.equal(await page.locator('[data-missed-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-missed-order').count(),0);
  // An unsuccessful replacement never triggers the reaction.
  reject=true;await skip();assert.equal(await page.locator('.game-missed-order').count(),0);
  // Only acknowledge a skip after the server confirms it.
  // Keyboard recovery also works when the existing status banner overlaps a control.
  hold=true;await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').press('Enter');
  assert.equal(await page.locator('.game-missed-order').count(),0);await confirmHeld();
  await page.locator('[data-missed-order="0"]').waitFor();
  await page.waitForFunction(()=>{const image=document.querySelector('[data-missed-order="0"] img');return image&&image.complete&&image.naturalWidth>0;});
  assert.equal(await page.locator('[data-missed-order="0"] img').evaluate(e=>getComputedStyle(e).imageRendering),'pixelated');
  assert.equal(await page.locator('[data-missed-order="1"]').count(),0);
  assert.equal(await page.locator('[data-missed-order="0"]').evaluate(e=>getComputedStyle(e).pointerEvents),'none');
  await page.waitForTimeout(180);
  await page.screenshot({path:'.checks/order-reactions/missed-order.png'});
  // Rapid clicks remain usable; refreshing the card does not remove its reaction.
  const before=replacements;await skip();assert.equal(replacements,before+1);
  await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('[data-missed-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-missed-order').count(),0);
  // Pending and rejected deliveries do not celebrate; accepted delivery shows a dollar.
  reject=true;await deliver();assert.equal(await page.locator('.game-order-reaction').count(),0);
  hold=true;release=undefined;
  await page.locator('[data-order-slot="0"] [data-econ-action^="fulfill:"]').press('Enter');
  assert.equal(await page.locator('.game-order-reaction').count(),0);await confirmHeld();
  await reaction('delivered','dollar-sign-pixel.svg');
  assert.equal(await page.locator('.game-missed-order').count(),0);
  await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('[data-delivered-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  // Finding an unready jackpot is fine; skipping one during queued spam is a miss.
  nextRarity='jackpot';nextCanFulfill=false;
  state.contracts.offers[0].canFulfill=false;
  await page.evaluate(()=>window.YomamaEcon.refresh());
  await skip();assert.equal(await page.locator('.game-order-reaction').count(),0);
  assert.equal(await page.locator('[data-order-slot="0"]').getAttribute('data-rarity'),'jackpot');
  state.contracts.offers[0].rarity='standard';
  await page.evaluate(()=>window.YomamaEcon.refresh());
  hold=true;
  const jackpotBefore=replacements;
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').press('Enter');
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').evaluate(button=>{button.click();button.click();});
  assert.equal(await page.locator('.game-order-reaction').count(),0);
  await confirmHeld();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
  assert.equal(replacements,jackpotBefore+3);
  assert.equal(state.contracts.offers[0].canFulfill,false);
  assert.equal(await page.locator('[data-missed-order="0"]').count(),1);
  await page.waitForTimeout(600);
  // A jackpot save reacts only once the server accepts it, even without enough goods.
  hold=true;await page.locator('[data-order-slot="0"] .game-order-commit').click();
  assert.equal(await page.locator('.game-order-reaction').count(),0);
  await confirmHeld();await page.locator('[data-saved-order="0"]').waitFor();
  assert.equal(await page.locator('[data-order-slot="0"] .game-order-commit').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.game-missed-order').count(),0);
  assert.equal(await page.locator('[data-saved-order="1"]').count(),0);
  await reaction('saved','lucky-seven-pixel.svg');
  assert.equal(await page.locator('.game-saved-order > span').evaluate(e=>getComputedStyle(e).animationName),'game-missed-order');
  assert.equal(await page.locator('.game-saved-order').evaluate(e=>getComputedStyle(e).pointerEvents),'none');
  await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('[data-saved-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  // Releasing goods and rejected saves do not celebrate.
  await save();assert.equal(state.contracts.offers[0].committed,false);
  assert.equal(await page.locator('.game-order-reaction').count(),0);
  reject=true;await save();assert.equal(state.contracts.offers[0].committed,false);
  assert.equal(await page.locator('.game-order-reaction').count(),0);
  // Non-jackpot saves use thumbs-up; fulfilled jackpots show gold even on a standard replacement.
  for(const rarity of ['standard','large','rare','jackpot']){
   Object.assign(state.contracts.offers[0],{rarity,rarityLabel:rarity==='jackpot'?'Jackpot':rarity[0].toUpperCase()+rarity.slice(1)+' order',committed:false,canFulfill:false});
   await page.evaluate(()=>window.YomamaEcon.refresh());
   reject=true;await save();assert.equal(state.contracts.offers[0].committed,false);
   assert.equal(await page.locator('.game-order-reaction').count(),0);
   hold=true;release=undefined;
   await page.locator('[data-order-slot="0"] .game-order-commit').press('Enter');
   assert.equal(await page.locator('.game-order-reaction').count(),0);await confirmHeld();
   await reaction('saved',rarity==='jackpot'?'lucky-seven-pixel.svg':'thumbs-up-pixel.svg');
   assert.equal(state.contracts.offers[0].committed,true);
   if(rarity==='standard'||rarity==='jackpot')await page.screenshot({path:'.checks/order-reactions/saved-'+rarity+'.png'});
   await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
   state.contracts.offers[0].canFulfill=true;
   await page.evaluate(()=>window.YomamaEcon.refresh());await deliver();
   await reaction('delivered',rarity==='jackpot'?'gold-bars-pixel.svg':'dollar-sign-pixel.svg');
   assert.equal(await page.locator('.game-missed-order,.game-saved-order').count(),0);
   if(rarity==='standard'||rarity==='jackpot')await page.screenshot({path:'.checks/order-reactions/delivered-'+rarity+'.png'});
   await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  }
  // Project deliveries react on both the next project and the final completed card.
  const project=state.contracts.offers[2];
  Object.assign(project,{project:true,completed:false,locked:false,canFulfill:true,committed:false,canCommit:true});
  state.townProjects=Object.assign({},state.townProjects,{completed:1});
  await page.evaluate(()=>window.YomamaEcon.refresh());await save(2);
  await reaction('saved','thumbs-up-pixel.svg',2);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  await deliver(2);
  await reaction('delivered','dollar-sign-pixel.svg',2);
  assert.equal(await page.locator('[data-delivered-order="0"]').count(),0);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  completeProject=true;await deliver(2);
  assert.equal(await page.locator('[data-order-slot="2"].is-complete').count(),1);
  await reaction('delivered','dollar-sign-pixel.svg',2);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-order-reaction').count(),0);
  // Reduced motion gets the same brief face without the pop animation.
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:390,height:844});
  state.contracts.offers[0].rarity='jackpot';
  await page.evaluate(()=>window.YomamaEcon.refresh());
  await page.waitForTimeout(150);await skip();
  assert.equal(await page.locator('.game-missed-order > span').evaluate(e=>getComputedStyle(e).animationName),'none');
  const rect=await page.locator('.game-missed-order').boundingBox();assert(rect.x>=0&&rect.x+rect.width<=390&&rect.y+rect.height<=844);
  // Saving immediately replaces the crying face with a single reduced-motion lucky 7.
  await save();assert.equal(await page.locator('.game-missed-order').count(),0);
  await reaction('saved','lucky-seven-pixel.svg');
  assert.equal(await page.locator('[data-order-reaction="0"]').count(),1);
  assert.equal(await page.locator('.game-saved-order > span').evaluate(e=>getComputedStyle(e).animationName),'none');
  const savedRect=await page.locator('.game-saved-order').boundingBox();assert(savedRect.x>=0&&savedRect.x+savedRect.width<=390&&savedRect.y+savedRect.height<=844);
  // Delivery replaces the save reaction and keeps the same reduced-motion treatment.
  state.contracts.offers[0].canFulfill=true;
  await page.evaluate(()=>window.YomamaEcon.refresh());await deliver();
  await reaction('delivered','gold-bars-pixel.svg');
  assert.equal(await page.locator('.game-saved-order').count(),0);
  assert.equal(await page.locator('.game-delivered-order > span').evaluate(e=>getComputedStyle(e).animationName),'none');
  const deliveredRect=await page.locator('.game-delivered-order').boundingBox();assert(deliveredRect.x>=0&&deliveredRect.x+deliveredRect.width<=390&&deliveredRect.y+deliveredRect.height<=844);
  await page.reload();await page.locator('[data-order-slot="0"]').waitFor({state:'attached'});await showOrder(0);assert.equal(await page.locator('.game-order-reaction').count(),0);
  assert.deepEqual(errors,[]);console.log('Passed: readiness, queued jackpot spam, accepted/pending/rejected saves and deliveries, thumbs-up/lucky-7 saves, dollar regular/project deliveries, gold jackpot deliveries, release, rapid clicks, expiry, mobile, reduced motion, reload.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
