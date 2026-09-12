/* Delayed responses exercise actual rapid-click queueing with current order IDs. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3006';
(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);const s=await response.json();
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});let release,rolls=0;const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   if(url.pathname.endsWith('/orders/replace')){
    const body=route.request().postDataJSON();assert.equal(body.orderId,s.contracts.offers[body.offerIndex].id);
    if(rolls===0)await new Promise(resolve=>release=resolve);
    rolls++;const o=s.contracts.offers[body.offerIndex];o.id='rolled-'+rolls;
    o.rarity='jackpot';o.rarityLabel='Jackpot order';o.rewardPercent=313;o.canFulfill=false;
    o.requirements=s.board.slice(0,5).map(g=>({goodId:g.goodId,buildingId:g.buildingId,name:g.name,quantity:12,owned:0}));
    o.reward=Math.round(s.board.slice(0,5).reduce((v,g)=>v+12*g.unitPrice,0)*3.13);
    s.receipt={kind:'order_replace'};
   }
   return route.fulfill({json:s});
  });
  await page.goto(base+'/marketplace.html');const reroll=page.locator('[data-order-slot="0"] [data-econ-action^="replace:"]');
  await reroll.click();assert(release);assert(await reroll.isEnabled());
  await reroll.evaluate(button=>{for(let i=0;i<5;i++)button.click();});
  assert.equal(rolls,0);release();
  await page.waitForFunction(()=>document.querySelector('[data-econ-action="replace:0:rolled-6"]')&&!document.querySelector('[aria-busy="true"]'));
  assert.equal(rolls,6);
  assert.equal(await page.locator('[data-order-slot="0"]').getAttribute('data-rarity'),'jackpot');
  assert(await reroll.isEnabled());
  for(const [width,height] of [[1366,768],[1728,694],[390,844],[844,390]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(150);
   const bad=await page.evaluate(()=>[...document.querySelectorAll('.game-order button,.game-order .econ-good-line')].filter(e=>e.getClientRects().length&&!e.closest('[hidden]')).filter(e=>{
    const r=e.getBoundingClientRect(),p=e.closest('.game-order').getBoundingClientRect();return r.bottom>Math.min(p.bottom,innerHeight)+1||r.right>innerWidth+1;
   }).map(e=>e.textContent));assert.deepEqual(bad,[],width+'x'+height+' order clipped');
   if(width===1366||width===390)await page.screenshot({animations:'disabled',path:'previews/jackpot-order-'+width+'.png'});
  }
  assert.deepEqual(errors,[]);console.log('Passed: 6 rapid clicks, serialized current IDs, jackpot payout label, 5 ingredients, 4 viewport sizes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
