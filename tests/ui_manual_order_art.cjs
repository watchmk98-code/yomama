/* Manual-order buyer art follows the requested goods, not the card slot.
   API writes are intercepted; no player save is changed. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const cfg=require('../config/economy.v4.json');
const base=process.argv[2]||'http://127.0.0.1:3013';

(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const state=await response.json(),offers=(state.orders||state.contracts).offers;
 const goods=new Map(cfg.tiers.flatMap(b=>b.goods.map(g=>[g.id,{goodId:g.id,buildingId:b.id,name:g.name,quantity:2,owned:20}])));
 const cases=[
  ['Farm Produce Run','farm_tomatoes','Sunrise Diner','sunrise','order-scenes.png'],
  ['Coffee Refill','roastery_roasted_beans','Copper Cafe','copper','copper-cafe-representative.png'],
  ['Workshop Refit','workshop_welded_frames','Builders Union','builders','order-scenes.png'],
  ['Fresh Seafood Supper','fish_stall_fresh_catch','Harbor Bistro','harbor','harbor-bistro.png'],
  ['Renewable Power Booking','solar_array_utility_kwh','Grid Cooperative','grid','grid-cooperative.png'],
  ['Satellite Data Link','uplink_center_telemetry','Innovation Lab','innovation','innovation-lab.png']
 ];
 const order=offers[0];delete order.project;delete order.completed;
 order.rarity='standard';order.rarityLabel='Standard';order.canFulfill=true;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   return url.pathname.startsWith('/api/game/')?route.fulfill({json:state}):route.continue();
  });
  await page.goto(base+'/marketplace.html');
  const card=page.locator('[data-order-slot="0"]');await card.waitFor();
  for(const [name,goodId,buyer,scene,asset] of cases){
   order.name=name;order.purpose='';order.channelLabel='Quick cash';order.buyerType=scene;order.requirements=[goods.get(goodId)];
   await page.evaluate(()=>window.YomamaEcon.refresh());
   assert.equal(await card.locator('.market-buyer-name').textContent(),buyer);
   const art=card.locator('.market-order-scene');
   assert.equal(await art.getAttribute('data-buyer-scene'),scene);
   assert((await art.locator('span').evaluate(node=>getComputedStyle(node).backgroundImage)).includes(asset),asset+' is loaded');
  }
  delete order.buyerType;order.name='Legacy seafood order';order.requirements=[goods.get('fish_stall_fresh_catch')];
  await page.evaluate(()=>window.YomamaEcon.refresh());
  assert.equal(await card.locator('.market-buyer-name').textContent(),'Harbor Bistro','Saved orders without buyerType retain a compatible fallback');
  assert.deepEqual(errors,[]);
  console.log('Passed: six manual-order buyer scenes follow their requested business goods.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
