/* All Market requirements fit at once; API responses are intercepted. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {mkdirSync}=require('node:fs');
const cfg=require('../config/economy.v4.json');
const base=process.argv[2]||'http://127.0.0.1:3013';
const viewports=[[1366,768],[1366,650],[1728,694],[1920,1080],[1024,768],[768,768],[390,844],[844,390]];
(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const state=await response.json(),offers=(state.orders||state.contracts).offers;
 const goods=new Map(cfg.tiers.flatMap(b=>b.goods.map(g=>[g.id,{goodId:g.id,buildingId:b.id,name:g.name,quantity:12,owned:120,reserved:6}])));
 const many=['garage_repairs','solar_coop_battery_storage','solar_array_utility_kwh','solar_array_reserve_capacity','solar_array_renewable_credits'].map(id=>goods.get(id));
 const buyer={...state.customerContracts.customers[0],available:true};
 state.customerContracts.customers=[buyer];state.customerContracts.active=[];
 offers.forEach(o=>{delete o.project;delete o.completed;o.rarity='jackpot';o.rarityLabel='Jackpot order';o.name='Clean Transit Expansion';o.purpose='Repairs, batteries, utility solar, reserves and credits.';});
 const browser=await chromium.launch({headless:true});mkdirSync('.checks/market-goods-fit',{recursive:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
   return url.pathname.startsWith('/api/game/')?route.fulfill({json:state}):route.continue();
  });
  async function panel(name){
   const tab=page.getByRole('tab',{name,exact:true});if(await tab.count())await tab.click();
   await page.evaluate(()=>window.YomamaFit.render());
  }
  async function fit(selector,count,label){
   const result=await page.locator(selector).evaluate((host,count)=>{
    const errors=[],box=host.getBoundingClientRect(),rows=Array.from(host.children),max=parseFloat(getComputedStyle(host).getPropertyValue('--market-product-size'));
    if(box.height<=0||box.width<=0)errors.push('Requirements container has no space');
    if(rows.length!==count)errors.push('Wrong requirement count');
    if(host.scrollHeight>host.clientHeight+1||host.scrollWidth>host.clientWidth+1)errors.push('Requirements overflow their container');
    const inside=(rect,label)=>{if(rect.left<box.left-1||rect.right>box.right+1||rect.top<box.top-1||rect.bottom>box.bottom+1)errors.push(label+' is clipped');};
    rows.forEach(row=>{
     if(row.hidden||!row.getClientRects().length)errors.push('Hidden requirement');
     inside(row.getBoundingClientRect(),row.textContent);
     row.querySelectorAll('.econ-good-name > span,.econ-good-line > span:last-child').forEach(span=>{
      const range=document.createRange();range.selectNodeContents(span);
      Array.from(range.getClientRects()).forEach(rect=>inside(rect,span.textContent));
     });
    });
    const font=parseFloat(getComputedStyle(rows[0].querySelector('.econ-good-name')).fontSize);
    if(font>max+.1)errors.push('Requirements exceed current maximum font');
    if(font<12)errors.push('Requirements font is below 12px: '+font);
    if(document.documentElement.scrollHeight>innerHeight+1||document.documentElement.scrollWidth>innerWidth+1)errors.push('Page overflows viewport');
    return {errors,font,max};
   },count);
   assert.deepEqual(result.errors,[],label);
   assert.equal(await page.locator('.game-order-caption .game-pager,.game-contract-caption .game-pager').count(),0,'No requirement arrows');
   return result;
  }
  let loaded=false;
  for(const [width,height] of viewports){
   await page.setViewportSize({width,height});
   for(const count of [1,5,1]){
    const requirements=count===1?[goods.get('farm_tomatoes')]:many;
    offers.forEach(o=>o.requirements=requirements);buyer.requirements=requirements;
    state.customerContracts.active=[];
    if(!loaded){await page.goto(base+'/marketplace.html');await page.locator('.game-order').first().waitFor({state:'attached'});await page.evaluate(()=>document.fonts.ready);loaded=true;}
    else await page.evaluate(()=>window.YomamaEcon.refresh());
    await panel('Orders');
    const card=page.locator('[data-order-slot="0"]');assert(await card.isVisible());
    const order=await fit('[data-order-slot="0"] .game-order-goods',count,width+'x'+height+' order '+count);
    if(count===1)assert.equal(order.font,order.max,'A short order restores the current maximum font');
    await panel('Contracts');
    const preview=await fit('.game-contract-goods',count,width+'x'+height+' buyer preview '+count);
    if(count===1)assert.equal(preview.font,preview.max,'A short buyer list restores the current maximum font');
    state.customerContracts.active=[{...buyer,id:'fit-active-buyer',customerId:buyer.id,slot:0,status:'supplying',paused:false,deliveries:4,earned:60,nextDeliverySeconds:90,requirements}];
    await page.evaluate(()=>window.YomamaEcon.refresh());await panel('Contracts');
    const active=await fit('.game-contract-goods',count,width+'x'+height+' signed buyer '+count);
    if(count===1)assert.equal(active.font,active.max,'A short signed buyer list restores the current maximum font');
    if(count===5)await page.screenshot({animations:'disabled',path:'.checks/market-goods-fit/buyers-'+width+'x'+height+'.png'});
    await panel('Orders');
    await fit('[data-order-slot="0"] .game-order-goods',count,width+'x'+height+' order after refresh '+count);
    if(count===5)await page.screenshot({animations:'disabled',path:'.checks/market-goods-fit/orders-'+width+'x'+height+'.png'});
   }
  }
  assert.deepEqual(errors,[]);console.log('Passed: all goods visible without item arrows, adaptive/max fonts, long names, buyer previews and signed buyers, refresh and eight viewports.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
