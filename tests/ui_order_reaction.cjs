/* Test the cosmetic reaction with intercepted API responses; no live sales. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3003';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
  const state=await response.json();assert.equal(state.modelVersion,4);
  state.contracts.offers[0].canFulfill=false;
  let reject=false,hold=false,release,serial=0,replacements=0;
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   if(url.pathname.endsWith('/orders/replace')){
    const body=route.request().postDataJSON();assert.equal(body.orderId,state.contracts.offers[body.offerIndex].id);
    if(hold){hold=false;await new Promise(resolve=>release=resolve);}
    if(reject){reject=false;return route.fulfill({status:409,json:{error:'Order changed'}});}
    replacements++;state.contracts.offers[body.offerIndex].id='reaction-order-'+(++serial);
    state.contracts.offers[body.offerIndex].canFulfill=true;
    state.receipt={kind:'order_replace'};
   }
   if(url.pathname.endsWith('/orders/fulfill'))state.receipt={kind:'order',reward:50,materials:1};
   return route.fulfill({json:state});
  });
  await page.goto(base+'/marketplace.html');await page.locator('[data-order-slot="0"]').waitFor();
  if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();
  async function skip(slot=0){await page.locator('[data-order-slot="'+slot+'"] [data-econ-action^="replace:"]').click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));}
  // A newly generated ready order must not be mistaken for a missed one.
  await skip();assert.equal(await page.locator('.game-missed-order').count(),0);
  // Spamming past a newly ready offer must react, even when its click was queued.
  state.contracts.offers[0].canFulfill=false;
  await page.evaluate(()=>window.YomamaEcon.refresh());
  hold=true;
  const spamBefore=replacements;
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').click();
  assert(release);
  await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').evaluate(button=>{
   if(button.disabled)throw new Error('New Order must stay enabled during spam');
   button.click();button.click();
  });
  assert.equal(await page.locator('.game-missed-order').count(),0);
  release();
  await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
  assert.equal(replacements,spamBefore+3);
  assert.equal(await page.locator('[data-missed-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-missed-order').count(),0);
  // An unsuccessful replacement never triggers the reaction.
  reject=true;await skip();assert.equal(await page.locator('.game-missed-order').count(),0);
  // Only acknowledge a skip after the server confirms it.
  hold=true;await page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]').click();
  assert.equal(await page.locator('.game-missed-order').count(),0);assert(release);release();
  await page.locator('[data-missed-order="0"]').waitFor();
  await page.waitForFunction(()=>{const image=document.querySelector('[data-missed-order="0"] img');return image&&image.complete&&image.naturalWidth>0;});
  assert.equal(await page.locator('[data-missed-order="0"] img').evaluate(e=>getComputedStyle(e).imageRendering),'pixelated');
  assert.equal(await page.locator('[data-missed-order="1"]').count(),0);
  assert.equal(await page.locator('[data-missed-order="0"]').evaluate(e=>getComputedStyle(e).pointerEvents),'none');
  await page.waitForTimeout(180);
  await page.screenshot({path:'previews/missed-order-'+Date.now()+'.png'});
  // Rapid clicks remain usable; refreshing the card does not remove its reaction.
  const before=replacements;await skip();assert.equal(replacements,before+1);
  await page.evaluate(()=>window.YomamaEcon.refresh());assert.equal(await page.locator('[data-missed-order="0"]').count(),1);
  await page.waitForTimeout(600);assert.equal(await page.locator('.game-missed-order').count(),0);
  // Delivering a ready order is not a miss.
  await page.locator('[data-order-slot="0"] [data-econ-action^="fulfill:"]').click();await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
  assert.equal(await page.locator('.game-missed-order').count(),0);
  // Reduced motion gets the same brief face without the pop animation.
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(150);await skip();
  assert.equal(await page.locator('.game-missed-order > span').evaluate(e=>getComputedStyle(e).animationName),'none');
  const rect=await page.locator('.game-missed-order').boundingBox();assert(rect.x>=0&&rect.x+rect.width<=390&&rect.y+rect.height<=844);
  await page.reload();await page.locator('[data-order-slot="0"]').waitFor();assert.equal(await page.locator('.game-missed-order').count(),0);
  assert.deepEqual(errors,[]);console.log('Passed: readiness, queued spam, failed/pending requests, rapid clicks, expiry, delivery, mobile, reduced motion, reload.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
