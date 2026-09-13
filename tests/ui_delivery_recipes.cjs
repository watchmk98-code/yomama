/* Named delivery recipes stay readable and every ingredient is visible at once.
   All game API writes are intercepted; no player save is changed. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {mkdirSync}=require('node:fs');
const cfg=require('../config/economy.v4.json');
const base=process.argv[2]||'http://127.0.0.1:3007';
(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const s=await response.json(), offers=(s.orders||s.contracts).offers;
 const goods=new Map(cfg.tiers.flatMap(b=>b.goods.map(g=>[g.id,{goodId:g.id,buildingId:b.id,name:g.name}])));
 s.rulesRevision=2;s.regularDeliveries=1;
 const recipes=[
  ['Guesthouse Breakfast Spread','Quick cash','The guesthouse offers smoked fish, pastries, preserves and brewed coffee.',
   ['fish_stall_smoked_fish','roastery_pastries','cannery_preserves','roastery_roasted_beans']],
  ['Clean Transit Expansion','Building supplies','The tram operator pairs repairs and batteries with utility solar, reserves and credits.',
   ['garage_repairs','solar_coop_battery_storage','solar_array_utility_kwh','solar_array_reserve_capacity','solar_array_renewable_credits']],
  ['Breakfast Club Celebration','Saved town delivery','The breakfast club serves smoked fish, tomatoes, pastries, preserves and espresso.',
   ['fish_stall_smoked_fish','farm_tomatoes','roastery_pastries','cannery_preserves','roastery_espresso_shots']]
 ];
 offers.forEach((o,i)=>{
  // Model a preserved pre-project board; new projects have separate coverage.
  delete o.project;delete o.completed;
  [o.name,o.channelLabel,o.purpose]=recipes[i];o.recipeId='ui-recipe-'+i;
  o.customer=i===2?'breakfast':i===1?'builder':'market';o.materials=i===1?12:0;
  o.rarity='jackpot';o.rarityLabel='Jackpot order';o.reward=123456;o.rewardPercent=313;
  o.requirements=recipes[i][3].map(id=>({...goods.get(id),quantity:12,owned:120}));
  o.canFulfill=true;o.committed=false;
 });
 const browser=await chromium.launch({headless:true});mkdirSync('output/delivery-recipes',{recursive:true});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   return url.pathname.startsWith('/api/game/econ/')?route.fulfill({json:s}):route.continue();
  });
  async function checkBounds(label){
   const bad=await page.evaluate(()=>{
    const visible=e=>e.getClientRects().length&&!e.closest('[hidden]');
    const failures=[];
    document.querySelectorAll('.game-order').forEach(card=>{
     if(!visible(card))return;
     const outer=card.getBoundingClientRect();
     const parts=[...card.children].filter(visible);
     [...parts,...card.querySelectorAll('button,.econ-good-line,.game-order-name,.game-order-tier,.game-order-purpose,.game-order-progress')].filter(visible).forEach(e=>{
      const r=e.getBoundingClientRect();
      if(r.bottom>Math.min(outer.bottom,innerHeight)+1||r.top<outer.top-1||r.left<outer.left-1||r.right>Math.min(outer.right,innerWidth)+1)failures.push('clipped: '+e.textContent.trim()+' '+JSON.stringify({left:r.left,right:r.right,bottom:r.bottom,cardBottom:outer.bottom}));
     });
     parts.forEach((a,i)=>parts.slice(i+1).forEach(b=>{
      const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
      if(Math.min(ar.right,br.right)-Math.max(ar.left,br.left)>1&&Math.min(ar.bottom,br.bottom)-Math.max(ar.top,br.top)>1)failures.push('overlap: '+a.className+' / '+b.className);
     }));
    });
    if(document.documentElement.scrollWidth>innerWidth+1||document.documentElement.scrollHeight>innerHeight+1)failures.push('page scroll');
    return failures;
   });
   assert.deepEqual(bad,[],label);
  }
  for(const [width,height] of [[1366,768],[1366,650],[1728,694],[1920,1080],[1024,768],[768,768],[390,844],[844,390]]){
   await page.setViewportSize({width,height});await page.goto(base+'/marketplace.html');
   await page.locator('[data-order-slot="0"]').waitFor();await page.evaluate(()=>document.fonts.ready);
   await page.waitForTimeout(150);const seen=new Set();
   await page.screenshot({animations:'disabled',path:'output/delivery-recipes/orders-'+width+'x'+height+'.png'});
   for(let orderPage=0;orderPage<3;orderPage++){
    await checkBounds(width+'x'+height+' order page '+orderPage);
    const cards=await page.locator('.game-order').evaluateAll(es=>es.filter(e=>!e.hidden&&e.getClientRects().length).map(e=>Number(e.dataset.orderSlot)));
    for(const slot of cards){
     seen.add(slot);const card=page.locator('[data-order-slot="'+slot+'"]');
     assert.equal(await card.locator('.game-order-name').textContent(),recipes[slot][0]);
     assert.equal(await card.locator('.game-order-channel').textContent(),recipes[slot][1]);
     assert.equal(await card.locator('.game-order-purpose').textContent(),recipes[slot][2]);
     const names=await card.locator('.econ-good-line').evaluateAll(es=>es.filter(e=>!e.hidden&&e.getClientRects().length).map(e=>e.querySelector('.econ-good-name').textContent));
     assert.equal(new Set(names).size,recipes[slot][3].length,'All ingredients visible at once at '+width+'x'+height);
     assert.equal(await card.locator('.game-pager').count(),0,'Ingredients need no arrow navigation');
    }
    const next=page.locator('.game-pager[data-page="Orders"] button:last-child:not(:disabled)');
    if(!await next.count())break;await next.click();
   }
   assert.equal(seen.size,3,'All three order channels accessible');
  }
  delete offers[0].purpose;delete offers[0].channelLabel;delete offers[0].recipeId;
  await page.setViewportSize({width:1366,height:768});await page.goto(base+'/marketplace.html');
  await page.locator('[data-order-slot="0"]').waitFor();
  assert.equal(await page.locator('[data-order-slot="0"] .game-order-name').textContent(),recipes[0][0]);
  assert.equal(await page.locator('[data-order-slot="0"] .game-order-channel').textContent(),'Quick cash');
  assert.equal(await page.locator('[data-order-slot="0"] .game-order-purpose').count(),0);
  assert(await page.getByText('Materials reduce future construction costs',{exact:true}).count());
  assert(await page.getByText('Saved delivery · original reward preserved; your next card shows town projects',{exact:true}).count());
  await checkBounds('Legacy offer fallback');assert.deepEqual(errors,[]);
  console.log('Passed: named recipes, purposes, three reward channels, five goods, eight viewports, progress notes and legacy offers.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
