/* Exercise a real temporary preview; never point this at a classroom server. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const base=process.argv[2] || 'http://127.0.0.1:3016';

(async()=>{
 const initial=await (await fetch(base+'/api/game/econ/state')).json();
 assert(initial.orderPreview,'This check requires the isolated order preview');
 const expected=initial.contracts.offers[0], third=initial.contracts.offers[2];
 assert(!expected.inTransit && expected.canFulfill,'Start with a stocked, idle delivery card');
 await fs.mkdir('.checks/timed-delivery',{recursive:true});
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1800,height:1050}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/marketplace.html');
  const first=page.locator('[data-order-slot="0"]');
  await first.getByRole('button',{name:/Start delivery/}).waitFor();
  const dispatched=page.waitForResponse(response=>response.url().endsWith('/orders/fulfill') && response.request().method()==='POST');
  await first.getByRole('button',{name:/Start delivery/}).click();
  const outbound=await (await dispatched).json();
  assert.equal(outbound.receipt.kind,'order_dispatch');
  assert.equal(outbound.receipt.durationSeconds,expected.deliverySeconds,'Dispatch must match the displayed quote');
  assert.equal(outbound.cash,initial.cash,'Starting a delivery must not pay the reward');
  assert.equal(outbound.contracts.offers[0].id,expected.id);
  assert.equal(outbound.contracts.offers[0].inTransit,true);
  assert.equal(await page.locator('[data-delivered-order="0"]').count(),0,'No completion emoji at dispatch');
  await page.locator('[data-preview-until]').waitFor();
  assert(await first.locator('[data-econ-action^="replace:"]').isDisabled());
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'.checks/timed-delivery/desktop.png',fullPage:true});

  const sector=page.locator('[data-order-slot="1"]');
  const oldSector=await sector.locator('.game-order-channel').innerText();
  await sector.locator('[data-econ-action^="replace:"]').click();
  await page.waitForFunction(old=>document.querySelector('[data-order-slot="1"] .game-order-channel').textContent!==old,oldSector);
  await page.reload();
  await page.locator('[data-preview-until]').waitFor();
  assert.equal(await page.locator('[data-delivered-order="0"]').count(),0,'Reload cannot invent a completion');
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'.checks/timed-delivery/mobile.png',fullPage:true});
  await page.setViewportSize({width:1800,height:1050});
  console.log('Dispatch, reserved shipment, reload and mobile checks passed; awaiting arrival.');

  const reaction=page.locator('[data-delivered-order="0"]');
  await reaction.waitFor({timeout:expected.deliverySeconds*1000+30000});
  assert.match(await reaction.locator('img').getAttribute('src'),/\/(dollar-sign-pixel|gold-bars-pixel)\.svg$/);
  await page.screenshot({path:'.checks/timed-delivery/arrived.png',fullPage:true});
  const arrived=await (await fetch(base+'/api/game/econ/state')).json();
  assert.equal(arrived.orderPreview.lastDelivery.orderId,expected.id);
  assert.equal(arrived.orderPreview.lastDelivery.reward,expected.reward);
  assert.equal(arrived.cash,initial.cash+expected.reward);
  assert.notEqual(arrived.contracts.offers[0].id,expected.id);
  assert(!arrived.contracts.offers[0].inTransit);
  assert.equal(arrived.contracts.offers[2].id,third.id);
  assert.equal(arrived.contracts.offers[2].reward,third.reward);
  await page.waitForTimeout(600);
  await page.reload();await first.waitFor();
  assert.equal(await page.locator('[data-delivered-order="0"]').count(),0,'Completion must not replay after reload');
  assert.deepEqual(errors,[]);
  console.log('Timed delivery paid on arrival exactly once; original emoji and third card preserved.');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
