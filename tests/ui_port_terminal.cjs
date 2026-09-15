/* Practice trading interactions against an isolated preview.
   node tests/ui_port_terminal.cjs http://127.0.0.1:3012
   All trading state stays in a fresh browser context; no server writes. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');

const base=process.argv[2];
if(!base)throw new Error('Provide an isolated preview URL');
const target=new URL(base);
if(!['localhost','127.0.0.1','[::1]'].includes(target.hostname)||target.port==='3000'){
 throw new Error('Use an isolated local preview, not the regular development or live server');
}
const storageKey='yport.paperState.v1';
const near=(actual,expected,message)=>assert(Math.abs(actual-expected)<0.005,`${message}: ${actual} vs ${expected}`);
const equity=state=>state.account.availableCash+state.account.reservedCash+
 Object.values(state.positions).reduce((total,held)=>total+held.marketValue,0);

(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1366,height:900},reducedMotion:'reduce'});
 try{
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('https://**/*',route=>route.abort());
  async function ready(){
   await page.locator('.port-stock-row[data-symbol="AAPL"]').waitFor();
   await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
   assert(new URL(page.url()).pathname.endsWith('/port_trading.html'),'PORT stays accessible without an analyst licence');
  }
  async function saved(){
   return page.evaluate(key=>JSON.parse(localStorage.getItem(key)),storageKey);
  }
  async function waitForOrders(count){
   await page.waitForFunction(({key,count})=>{
    const data=JSON.parse(localStorage.getItem(key)||'null');
    return data?.paperState?.ledger?.orders.length===count;
   },{key:storageKey,count});
  }
  async function select(symbol){
   await page.locator('#port-symbol-picker').selectOption(symbol);
   assert.equal(await page.locator('#port-selected-symbol').textContent(),symbol,'chart follows stock selection');
   assert.equal(await page.locator('#port-ticket-symbol').textContent(),symbol,'ticket follows stock selection');
  }
  await page.goto(base+'/port_trading.html?demo=1');
  await ready();
  assert.equal(await page.locator('main .port-panel').count(),4,'exactly four essential panels');
  assert.equal(await page.locator('.hero .tabs a[href*="port_trading.html"]').count(),0,'PORT belongs to the business menu');
  assert.equal(await page.locator('.hero .tabs a[href="./buildings.html"]').getAttribute('aria-current'),'page','GAME stays active while using PORT');
  const portNav=page.locator('.game-nav a[href*="port_trading.html"]');
  assert(await portNav.isVisible(),'PORT is visible in every student business menu');
  assert.equal(await portNav.getAttribute('aria-current'),'page');
  assert(await portNav.evaluate(link=>link.previousElementSibling?.getAttribute('href').includes('craft.html')),'PORT follows Craft');
  assert(await portNav.evaluate(link=>{
   const icon=link.querySelector('img,svg,.port-nav-icon');
   if(!icon)return false;
   const rect=icon.getBoundingClientRect();return rect.width>0&&rect.width<=28&&rect.height>0&&rect.height<=28;
  }),'PORT has a small business-navigation icon');
  assert(await page.getByRole('link',{name:'LEAD',exact:true}).isVisible(),'LEAD remains available');
  assert(await page.getByRole('button',{name:'LOG OUT',exact:true}).isVisible(),'account logout remains available');
  assert.equal(await page.locator('#port-symbol-picker option').count(),20,'all existing tradable symbols retained');
  assert.match(await page.locator('#port-quote-meta').textContent(),/practice|sample/i,'sample quotes labelled clearly');

  // PORT shares the game's visual identity while retaining its terminal layout.
  const buildingsPage=await context.newPage();
  try{
   await buildingsPage.route('https://**/*',route=>route.abort());
   await buildingsPage.goto(base+'/buildings.html');
   await buildingsPage.locator('#econ-building .game-panel').first().waitFor();
   await Promise.all([page.evaluate(()=>document.fonts.ready),buildingsPage.evaluate(()=>document.fonts.ready)]);
   async function sharedAppearance(view){
    return view.evaluate(()=>{
     const style=(element,properties)=>{
      const computed=getComputedStyle(element);
      return Object.fromEntries(properties.map(property=>[property,computed[property]]));
     };
     const surface=['backgroundColor','backgroundImage','borderTopColor','borderTopStyle','borderTopWidth','borderRadius'];
     const type=['fontFamily','fontWeight','color'];
     const banner=document.querySelector('.hero-banner');
     // The ticket deliberately uses the selected buy/sell color. Other PORT
     // panels retain the building page's shared surfaces and borders.
     const panel=document.querySelector('main .game-panel:not(.port-order-ticket)');
     return {
      body:style(document.body,['backgroundColor','backgroundImage',...type]),
      panel:style(panel,[...surface,...type]),
      hero:style(document.querySelector('.hero'),surface),
      bannerFrame:style(document.querySelector('.banner-frame'),[...surface,'height']),
      banner:{src:new URL(banner.src).pathname,visible:banner.getClientRects().length>0,loaded:banner.complete&&banner.naturalWidth>0},
      navigation:style(document.querySelector('.hero .tabs'),[...surface,...type,'fontSize','gap']),
      tab:style(document.querySelector('.hero .tabs a[href="./index.html"]'),[...surface,...type,'fontSize']),
      activeTab:style(document.querySelector('.hero .tabs a[aria-current="page"]'),[...surface,...type,'fontSize'])
     };
    });
   }
   const [portAppearance,buildingsAppearance]=await Promise.all([sharedAppearance(page),sharedAppearance(buildingsPage)]);
   assert.deepEqual(portAppearance,buildingsAppearance,'PORT preserves the building page background, fonts, panels, banner and navigation');
   assert(portAppearance.banner.visible&&portAppearance.banner.loaded,'the canonical YOMAMA banner is visible and loaded');
   await buildingsPage.setViewportSize({width:320,height:700});
   for(const gateOpen of [false,true]){
    await buildingsPage.evaluate(value=>window.dispatchEvent(new CustomEvent('yomama:econ',{detail:{gateOpen:value}})),gateOpen);
    const menu=await buildingsPage.locator('.game-nav').evaluate(nav=>({
     links:[...nav.querySelectorAll('a')].filter(link=>!link.hidden&&link.getClientRects().length).map(link=>link.getAttribute('href')),
     columns:getComputedStyle(nav).gridTemplateColumns.split(/\s+/).length,
     documentWidth:document.documentElement.scrollWidth,viewport:innerWidth
    }));
    assert.equal(menu.links.length,6,'business menu keeps PORT discoverable before the licence is earned');
    assert.equal(menu.columns,6,'mobile business columns include PORT for every licence state');
    assert(menu.links.some(href=>href.includes('port_trading.html')),'PORT remains visible after a reset');
    assert.equal(await buildingsPage.locator('.game-nav a[href*="port_trading.html"]').getAttribute('title'),'Open PORT');
    assert(menu.documentWidth<=menu.viewport+1,'business navigation fits320px');
   }
  }finally{
   await buildingsPage.close();
  }

  const initial=await saved();
  assert.equal(initial.paperState.positions.AAPL.quantity,100,'existing example holdings retained');
  assert.equal(initial.paperState.positions.NVDA.quantity,30);
  assert.equal(initial.paperState.positions.MSFT.quantity,65);

  await page.locator('.port-stock-row[data-symbol="MSFT"]').click();
  assert.equal(await page.locator('#port-selected-symbol').textContent(),'MSFT');
  assert.equal(await page.locator('#port-ticket-symbol').textContent(),'MSFT');
  assert.equal(await page.locator('#port-symbol-picker').inputValue(),'MSFT');
  await select('AAPL');
  const beforeBuy=(await saved()).paperState;
  await page.locator('#port-ticket-quantity').fill('2');
  await page.locator('#port-ticket-submit').click();
  await waitForOrders(beforeBuy.ledger.orders.length+1);
  const afterBuy=(await saved()).paperState;
  const buyFill=afterBuy.ledger.fills.at(-1);
  assert.equal(buyFill.side,'buy');
  assert.equal(buyFill.symbol,'AAPL');
  assert.equal(buyFill.quantity,2);
  assert.equal(afterBuy.positions.AAPL.quantity,beforeBuy.positions.AAPL.quantity+2);
  near(afterBuy.positions.AAPL.marketPrice,beforeBuy.positions.AAPL.marketPrice,'buying does not change the sample quote to average cost');
  near(equity(afterBuy),equity(beforeBuy),'a no-fee buy at the market mark preserves portfolio equity');
  near(afterBuy.account.availableCash,beforeBuy.account.availableCash-buyFill.fillPrice*2,'buy subtracts execution cost');
  near(afterBuy.account.reservedCash,beforeBuy.account.reservedCash,'filled market buy releases its reservation');

  await page.locator('.port-side-switch button[data-side="sell"]').click();
  await page.locator('#port-ticket-quantity').fill('1');
  await page.locator('#port-ticket-submit').click();
  await waitForOrders(afterBuy.ledger.orders.length+1);
  const afterSell=(await saved()).paperState;
  const sellFill=afterSell.ledger.fills.at(-1);
  assert.equal(sellFill.side,'sell');
  assert.equal(afterSell.positions.AAPL.quantity,afterBuy.positions.AAPL.quantity-1);
  near(afterSell.account.availableCash,afterBuy.account.availableCash+sellFill.fillPrice,'sell returns proceeds');
  near(equity(afterSell),equity(afterBuy),'a no-fee sell at the market mark preserves portfolio equity');

  await page.locator('.port-side-switch button[data-side="buy"]').click();
  await page.locator('#port-ticket-quantity').fill('0');
  await page.locator('#port-ticket-submit').click();
  assert.deepEqual((await saved()).paperState,afterSell,'invalid quantity leaves account and ledger unchanged');
  assert.match(await page.locator('#port-ticket-feedback').textContent(),/quantity|whole|positive|share|least/i,'invalid quantity gets visible feedback');

  await page.locator('#port-ticket-type').selectOption('limit');
  assert(await page.locator('#port-limit-field').isVisible());
  await page.locator('#port-ticket-quantity').fill('3');
  await page.locator('#port-ticket-limit').fill('1');
  await page.locator('#port-ticket-submit').click();
  await waitForOrders(afterSell.ledger.orders.length+1);
  const limitState=(await saved()).paperState;
  const limit=limitState.ledger.orders.at(-1);
  assert.equal(limit.status,'pending','nonmarketable limit waits');
  assert.equal(limit.type,'limit');
  near(limitState.account.availableCash,afterSell.account.availableCash-3,'limit reserves cash');
  near(limitState.account.reservedCash,afterSell.account.reservedCash+3,'reservation remains visible in account');
  await page.locator('#port-tab-orders').click();
  await page.locator(`[data-order-action="cancel"][data-order-id="${limit.id}"]`).click();
  const afterCancel=(await saved()).paperState;
  assert.equal(afterCancel.ledger.orders.find(order=>order.id===limit.id).status,'canceled');
  near(afterCancel.account.availableCash,afterSell.account.availableCash,'cancel releases cash');
  near(afterCancel.account.reservedCash,afterSell.account.reservedCash,'cancel removes reservation');

  await page.locator('#port-tab-chart').click();
  assert.equal(await page.locator('#port-tab-chart').getAttribute('aria-selected'),'true');
  assert(await page.locator('#port-research-chart').isVisible(),'the selected stock chart remains visible');
  await page.locator('#port-tab-positions').focus();
  await page.keyboard.press('End');
  assert.equal(await page.locator('#port-tab-history').getAttribute('aria-selected'),'true','portfolio tabs support keyboard navigation');
  assert(await page.locator('#port-portfolio-history').isVisible());
  assert.match(await page.locator('#port-portfolio-history').textContent(),/AAPL/);

  await select('ADBE');
  const beforeReload=await saved();
  await page.reload();
  await ready();
  const afterReload=await saved();
  assert.deepEqual(afterReload.paperState,beforeReload.paperState,'refresh preserves positions, cash and ledger');
  assert.equal(await page.locator('#port-selected-symbol').textContent(),'ADBE');
  assert.equal(await page.locator('#port-ticket-symbol').textContent(),'ADBE','refresh restores linked ticket');

  // Reuse an actual generated save to verify the old instantFill preference.
  await page.evaluate(key=>{
   const data=JSON.parse(localStorage.getItem(key));
   data.instantFill=false;
   localStorage.setItem(key,JSON.stringify(data));
  },storageKey);
  await page.reload();
  await ready();
  await select('AAPL');
  await page.locator('#port-ticket-quantity').fill('1');
  const beforePending=(await saved()).paperState;
  await page.locator('#port-ticket-submit').click();
  await waitForOrders(beforePending.ledger.orders.length+1);
  const pendingMarket=(await saved()).paperState;
  assert.equal(pendingMarket.ledger.orders.at(-1).status,'pending','legacy instantFill=false remains respected');
  assert.equal(pendingMarket.ledger.fills.length,beforePending.ledger.fills.length);
  assert.equal(pendingMarket.positions.AAPL.quantity,beforePending.positions.AAPL.quantity);
  const pendingOrder=pendingMarket.ledger.orders.at(-1);
  await page.locator(`[data-order-action="fill"][data-order-id="${pendingOrder.id}"]`).click();
  const confirmed=(await saved()).paperState;
  assert.equal(confirmed.ledger.orders.at(-1).status,'filled','pending practice order can be confirmed from Orders');
  assert.equal(confirmed.positions.AAPL.quantity,beforePending.positions.AAPL.quantity+1);
  near(confirmed.positions.AAPL.marketPrice,beforePending.positions.AAPL.marketPrice,'manual confirmation preserves the sample quote');
  near(equity(confirmed),equity(beforePending),'manual confirmation preserves equity at the sample quote');

  await page.locator('#port-tab-positions').click();
  await page.locator('#port-tab-chart').click();
  const chartStyle=await page.locator('.port-chart-line').evaluate(el=>({stroke:getComputedStyle(el).stroke,fill:getComputedStyle(el).fill}));
  assert.notEqual(chartStyle.stroke,'none','chart line has a visible stroke');
  assert.notEqual(chartStyle.stroke,'rgb(0, 0, 0)','chart line contrasts with the dark background');
  assert.equal(chartStyle.fill,'none','line does not create an unintended opaque chart area');
  const screenshotDir=path.join('.checks','port-terminal');
  await fs.mkdir(screenshotDir,{recursive:true});
  for(const [width,height] of [[1366,900],[1024,768],[768,1024],[390,844],[320,700]]){
   await page.setViewportSize({width,height});
   await page.evaluate(()=>document.fonts.ready);
   const measurements=await page.evaluate(()=>({
    viewport:innerWidth,
    document:document.documentElement.scrollWidth,
    body:document.body.scrollWidth,
    panels:[...document.querySelectorAll('main .port-panel')].map(el=>{
     const rect=el.getBoundingClientRect();
     return {label:el.getAttribute('aria-label')||el.getAttribute('aria-labelledby'),left:rect.left,right:rect.right};
    })
   }));
   assert(measurements.document<=width+1,`${width}px: document overflows: ${JSON.stringify(measurements)}`);
   assert(measurements.body<=width+1,`${width}px: body overflows`);
   assert(measurements.panels.every(panel=>panel.left>=-1&&panel.right<=width+1),`${width}px: panel extends beyond viewport`);
   assert(await page.locator('#port-ticket-submit').isVisible(),`${width}px: trade action available`);
   await page.screenshot({path:path.join(screenshotDir,`terminal-${width}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[],'terminal runs without uncaught page errors');
  console.log(JSON.stringify({result:'passed',checks:['shared building-page visual identity','four panels','linked stock selection','buy and sell accounting','invalid quantity','limit reserve/cancel','keyboard portfolio tabs','reload persistence','legacy pending preference','five responsive viewports'],screenshots:screenshotDir}));
 }finally{
  await context.close();
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exit(1);});
