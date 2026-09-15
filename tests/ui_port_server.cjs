/* PORT's server adapter against a controlled HTTP contract. Run on an isolated
   preview. The mock owns all balances; no game account is changed.
   node tests/ui_port_server.cjs http://127.0.0.1:3012 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2];
if(!base)throw new Error('Provide an isolated preview URL');
const target=new URL(base);
if(!['localhost','127.0.0.1','[::1]'].includes(target.hostname)||target.port==='3000')throw new Error('Use an isolated local preview');
const oldKey='yport.paperState.v1';
const sample=JSON.stringify({paperState:{account:{availableCash:9999999},positions:{NVDA:{quantity:300}}}});
let portfolio={accountId:'ui-test-account',account:{startingCash:100000,availableCash:100000,reservedCash:0,realizedPnl:0},positions:{},ledger:{orders:[],fills:[],cashEvents:[]},meta:{updatedAt:new Date().toISOString(),revision:0}};
let firstRead=true,releaseRead;
const readGate=new Promise(resolve=>{releaseRead=resolve;});
let readBlocked=false,dropNextPost=false,stale=false,unconfigured=false,quotePrice=100,marketClosed=false,closePassed=false;
const posts=[],errors=[];
const chartRequests=[];
let failChartSymbol='',holdNextChart=false,releaseHeldChart=null,finishHeldChart=null;
let heldChartFinished=Promise.resolve();
let holdNextRead=false,releaseHeldRead=null,notifyHeldRead=null;
function holdRead(){holdNextRead=true;return new Promise(resolve=>{notifyHeldRead=resolve;});}
function payload(){
 const now=Date.now()/1000;
 return {portfolio,serverTime:now,executionRules:{clock:'real_time',timezone:'America/New_York',session:'regular',buyPrice:'ask',sellPrice:'bid',maxQuoteAgeSeconds:10,marketOrderTimeoutSeconds:30,limitTimeInForce:'gtc',matching:'server_poll',pollIntervalSeconds:2},
  quotes:unconfigured?{}:{AAPL:{price:quotePrice,bid:99,ask:101,timestamp:now-(stale?60:0)}},
  market:{source:'alpaca_sip',status:unconfigured?'unconfigured':marketClosed?'closed':'open',message:unconfigured?'Market prices are not configured.':marketClosed?'The regular session is closed.':'',maxQuoteAgeSeconds:10,
   asOf:now-120,nextOpen:new Date((now+86400)*1000).toISOString(),nextClose:new Date((now+(closePassed?-1:3600))*1000).toISOString()},
  canTrade:!unconfigured&&!marketClosed,blockedReason:unconfigured?'Market prices are not configured.':'',player:{name:'UI TEST'},session:{paused:false}};
}
async function routePort(route){
 const request=route.request();
 if(new URL(request.url()).pathname==='/api/game/port/chart')return routeChart(route);
 if(request.method()==='GET'){
  if(firstRead){firstRead=false;await readGate;}
  if(readBlocked)return route.abort('failed');
  if(holdNextRead){
   holdNextRead=false;
   const oldPayload=JSON.stringify(payload());
   await new Promise(resolve=>{releaseHeldRead=resolve;notifyHeldRead();});
   return route.fulfill({status:200,contentType:'application/json',body:oldPayload});
  }
 }else{
  const body=request.postDataJSON();
  assert(body.token,'existing seat authenticates every write');
  assert.equal(body.accountId,portfolio.accountId);
  assert(!('referencePrice' in body)&&!('price' in body),'client does not choose the fill price');
  posts.push({path:new URL(request.url()).pathname,body});
  if(request.url().endsWith('/order')){
   if(!portfolio.ledger.orders.some(order=>order.id===body.clientOrderId)){
    const order={...body,id:body.clientOrderId,status:'pending',createdAt:new Date().toISOString()};
    delete order.token;
    portfolio.ledger.orders.push(order);
    if(body.side==='buy'){
     const reserve=body.quantity*(body.type==='limit'?body.limitPrice:101);
     portfolio.account.availableCash-=reserve;portfolio.account.reservedCash+=reserve;
    }
   }
  }else{
   const order=portfolio.ledger.orders.find(order=>order.id===body.orderId);
   order.cancellationRequestedAt=new Date().toISOString();
  }
  portfolio.meta.revision++;
  if(dropNextPost){dropNextPost=false;readBlocked=true;return route.abort('failed');}
 }
 return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload())});
}
async function routeChart(route){
 const request=route.request(),params=new URL(request.url()).searchParams;
 const symbol=params.get('symbol'),range=params.get('range');
 assert.equal(request.method(),'GET');
 assert(params.get('token'),'chart requests use the existing student seat');
 assert(['1D','1W','1M','3M','1Y','5Y'].includes(range),'the chart endpoint receives the requested range');
 chartRequests.push({symbol,range,token:params.get('token')});
 let held=false;
 if(holdNextChart&&symbol==='NVDA'){
  holdNextChart=false;held=true;
  heldChartFinished=new Promise(resolve=>{finishHeldChart=resolve;});
  await new Promise(resolve=>{releaseHeldChart=resolve;});
 }
 const end=Math.floor(Date.now()/1000)-60;
 const step={ '1D':60,'1W':1800,'1M':3600,'3M':14400,'1Y':86400,'5Y':604800 }[range];
 const bars=Array.from({length:12},(_,index)=>{
  const open=(symbol==='NVDA'?200:symbol==='MSFT'?300:90)+index;
  return {time:end-(11-index)*step,value:open+0.5,open,high:open+2,low:open-1,close:open+0.5};
 });
 try{
  return await route.fulfill({status:symbol===failChartSymbol?503:200,contentType:'application/json',body:JSON.stringify(symbol===failChartSymbol
   ?{error:'Chart history is temporarily unavailable.'}
   :{symbol,range,source:'alpaca_sip',bars,status:'ok',message:''})});
 }catch(error){if(!held)throw error;}finally{if(held)finishHeldChart();}
}
async function waitCash(page,cash){try{await page.waitForFunction(value=>document.querySelector('#port-cash').textContent===value,cash,{timeout:10000});}catch(error){console.error(await page.locator('#port-trade-ticket-form').innerText(), 'cash:', await page.locator('#port-cash').textContent(), 'writes:',posts.length,'page errors:',errors);throw error;}}
async function refresh(page){await page.evaluate(()=>window.dispatchEvent(new Event('focus')));}
async function chartReady(page,symbol,range){
 await page.waitForFunction(({symbol,range})=>{
  const host=document.querySelector('#port-market-chart-host');
  return host?.dataset.symbol===symbol&&host.dataset.range===range&&host.dataset.status==='ready';
 },{symbol,range});
}
async function sameCanvas(page,canvas,message){
 assert(await page.evaluate(previous=>previous===document.querySelector('#port-market-chart-host canvas'),canvas),message);
}
(async()=>{
 const browser=await chromium.launch({headless:true});
 const contexts=[];
 async function device(){
  const context=await browser.newContext({viewport:{width:1366,height:900},reducedMotion:'reduce'});
  contexts.push(context);
  await context.addInitScript(({key,value})=>localStorage.setItem(key,value),{key:oldKey,value:sample});
  await context.route('https://**/*',route=>route.abort());
  await context.route(/\/api\/game\/port(?:[/?]|$)/,routePort);
  const page=await context.newPage();
  await page.clock.install();
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/port_trading.html');
  await page.locator('.port-stock-row[data-symbol="AAPL"]').waitFor();
  await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
  return page;
 }
 try{
  const first=await device();
  assert.equal(await first.locator('#port-cash').textContent(),'—','no sample cash flashes before the server loads');
  assert(await first.locator('#port-ticket-submit').isDisabled());
  releaseRead();
  await waitCash(first,'$100,000.00');
  assert.equal(await first.locator('.hero .tabs a[href*="port_trading.html"]').count(),0,'server PORT lives under GAME');
  assert.equal(await first.locator('.hero .tabs a[href="./buildings.html"]').getAttribute('aria-current'),'page');
  const portNav=first.locator('.game-nav a[href*="port_trading.html"]');
  assert(await portNav.isVisible(),'every signed-in seat sees the business PORT link');
  assert.equal(await portNav.getAttribute('aria-current'),'page');
  assert(await portNav.evaluate(link=>link.previousElementSibling?.getAttribute('href').includes('craft.html')),'PORT follows Craft');
  assert.match(await first.locator('#port-portfolio-positions').textContent(),/first filled buy/);
  assert.equal(await first.locator('.port-stock-row[data-symbol="NVDA"] .port-stock-price').textContent(),'—','missing live quote never uses sample NVDA price');
  assert.equal(await first.locator('.port-chart-line').count(),0,'server mode does not invent historical prices');
  assert.equal(await first.evaluate(key=>localStorage.getItem(key),oldKey),sample,'sample save remains separate and untouched');
  assert.match(await first.locator('#port-ticket-note').textContent(),/Regular U\.S\. session.*closes.* ET.*fresh ask.*30s/,'market ticket explains the real regular session and next ask execution');
  assert.match(await first.locator('#port-quote-meta').textContent(),/ ET/,'quote timestamps use New York market time');

  // Real historical bars come through the authenticated server endpoint. Chart
  // gestures and portfolio polling must not reset the chart or submit orders.
  await chartReady(first,'AAPL','1W');
  const initialCanvas=await first.locator('#port-market-chart-host canvas').first().elementHandle();
  assert(initialCanvas,'historical bars render into the local chart');
  assert.equal(chartRequests.at(-1).symbol,'AAPL');assert.equal(chartRequests.at(-1).range,'1W');
  assert.equal(await first.locator('#port-market-chart-host').getAttribute('data-chart-type'),'area');
  const initialChartReads=chartRequests.length;
  const watchButton=await first.locator('.port-stock-row[data-symbol="AAPL"]').elementHandle();
  const pickerOption=await first.locator('#port-symbol-picker option[value="NVDA"]').elementHandle();
  await watchButton.focus();
  quotePrice=100.5;
  await first.waitForFunction(()=>document.querySelector('#port-selected-price').textContent==='$100.50');
  assert(await first.evaluate(button=>button===document.activeElement,watchButton),'a price poll retains watchlist keyboard focus');
  assert(await first.evaluate(option=>option===document.querySelector('#port-symbol-picker option[value="NVDA"]'),pickerOption),'price polling preserves native stock-picker options');
  await first.locator('#port-symbol-picker').focus();
  quotePrice=100.6;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-selected-price').textContent==='$100.60');
  assert(await first.locator('#port-symbol-picker').evaluate(picker=>picker===document.activeElement),'a poll does not disturb the focused native picker');
  await first.locator('#port-ticket-quantity').fill('23');
  quotePrice=100.7;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-selected-price').textContent==='$100.70');
  assert(await first.locator('#port-ticket-quantity').evaluate(input=>input===document.activeElement&&input.value==='23'),'quote updates preserve an unfinished quantity edit');
  await sameCanvas(first,initialCanvas,'an actual price poll preserves the chart canvas and zoom');
  await first.locator('.port-chart-menu summary').click();
  await first.locator('.port-chart-menu button[data-chart-type="line"]').focus();
  await first.keyboard.press('Escape');
  assert.equal(await first.locator('.port-chart-menu').getAttribute('open'),null,'Escape dismisses the chart menu');
  assert(await first.locator('.port-chart-menu summary').evaluate(summary=>summary===document.activeElement),'Escape returns focus to the menu button');
  await first.locator('#port-tab-orders').click();
  assert(await first.locator('#port-market-chart-host').isVisible());
  await first.locator('#port-tab-positions').click();
  await sameCanvas(first,initialCanvas,'portfolio tab changes preserve the chart');
  await first.setViewportSize({width:320,height:900});
  await sameCanvas(first,initialCanvas,'resizing preserves the chart');
  const chartBounds=await first.locator('#port-market-chart-host').boundingBox();
  assert(chartBounds&&chartBounds.width>0&&chartBounds.height>0,'the chart remains visible on mobile');
  assert(chartBounds.x>=-1&&chartBounds.x+chartBounds.width<=321,'the chart fits the mobile viewport');
  await first.setViewportSize({width:1366,height:900});
  await sameCanvas(first,initialCanvas,'restoring desktop size preserves the chart');
  assert.equal(chartRequests.length,initialChartReads,'polling, tab changes and resizing do not refetch history');

  await first.locator('button[data-chart-type="candles"]').click();
  await first.waitForFunction(()=>document.querySelector('#port-market-chart-host').dataset.chartType==='candles');
  await sameCanvas(first,initialCanvas,'switching to candles preserves the chart canvas');
  assert.equal(chartRequests.length,initialChartReads,'candles reuse the same server OHLC bars');
  await first.locator('button[data-chart-type="bars"]').click();
  await first.waitForFunction(()=>document.querySelector('#port-market-chart-host').dataset.chartType==='bars');
  await sameCanvas(first,initialCanvas,'switching to bars preserves the chart canvas');
  assert.equal(chartRequests.length,initialChartReads,'bars reuse the same server OHLC history');
  await first.locator('button[data-chart-type="candles"]').click();
  await first.waitForFunction(()=>document.querySelector('#port-market-chart-host').dataset.chartType==='candles');
  await first.reload();await waitCash(first,'$100,000.00');await chartReady(first,'AAPL','1W');
  assert.equal(await first.locator('#port-market-chart-host').getAttribute('data-chart-type'),'candles','the chart type preference survives refresh');
  const readsAfterReload=chartRequests.length;
  await first.locator('button[data-chart-type="area"]').click();
  await first.waitForFunction(()=>document.querySelector('#port-market-chart-host').dataset.chartType==='area');
  assert.equal(chartRequests.length,readsAfterReload,'returning to area view reuses history');
  await initialCanvas.dispose();

  // Release an older stock's response only after the newly selected stock has
  // rendered, proving an out-of-order response cannot relabel its chart.
  holdNextChart=true;
  const nvdaRequested=first.waitForRequest(request=>new URL(request.url()).pathname==='/api/game/port/chart'&&new URL(request.url()).searchParams.get('symbol')==='NVDA');
  await first.locator('#port-symbol-picker').selectOption('NVDA');await nvdaRequested;
  await first.locator('#port-symbol-picker').selectOption('MSFT');await chartReady(first,'MSFT','1W');
  assert(releaseHeldChart,'the old symbol request is still waiting');
  releaseHeldChart();await heldChartFinished;
  await first.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await first.locator('#port-market-chart-host').getAttribute('data-symbol'),'MSFT','late old-symbol response does not overwrite the selected chart');
  failChartSymbol='AMD';
  await first.locator('#port-symbol-picker').selectOption('AMD');
  await first.waitForFunction(()=>document.querySelector('#port-market-chart-host').dataset.status==='unavailable');
  assert(await first.locator('#port-chart-message').isVisible(),'a failed history fetch has a visible unavailable state');
  assert.match(await first.locator('#port-chart-message').textContent(),/unavailable|could not|unable|connection/i);
  assert.equal(await first.locator('.port-chart-line').count(),0,'failure never creates an illustrative replacement line');
  failChartSymbol='';
  await first.locator('#port-symbol-picker').selectOption('AAPL');await chartReady(first,'AAPL','1W');
  assert.deepEqual(await first.locator('.port-timeframes button').allTextContents(),['1m','30m','1h','4h','D','W']);
  for(const range of ['1D','1M','3M','1Y','5Y','1W']){
   const before=chartRequests.length;
   await first.locator('.port-workspace button[data-range="'+range+'"]').click();await chartReady(first,'AAPL',range);
   assert.equal(chartRequests.length,before+1,'changing range fetches its historical bars once');
   assert.equal(chartRequests.at(-1).symbol,'AAPL');assert.equal(chartRequests.at(-1).range,range);
   assert.equal(await first.locator('.port-workspace button[data-range="'+range+'"]').getAttribute('aria-pressed'),'true');
  }
  for(const [range,label] of [['3M','4h'],['5Y','1W']]){
   await first.locator('button[data-range="'+range+'"]').click();await chartReady(first,'AAPL',range);
   await first.reload();await chartReady(first,'AAPL',range);
   assert.equal(await first.locator('button[data-range="'+range+'"]').getAttribute('aria-pressed'),'true','new intervals survive reload');
   assert.match(await first.locator('#port-chart-source').textContent(),new RegExp(label+' bars'),'source labels the actual bar interval');
  }
  await first.locator('button[data-range="1W"]').click();await chartReady(first,'AAPL','1W');
  assert.equal(posts.length,0,'chart actions never submit portfolio orders');
  quotePrice=100;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-selected-price').textContent==='$100.00');

  assert(await first.locator('#port-ticket-submit').isEnabled());
  await first.locator('#port-ticket-quantity').fill('2');
  const slowOrderRead=holdRead();await refresh(first);await slowOrderRead;
  await first.locator('#port-ticket-submit').click();
  await first.waitForFunction(()=>document.querySelector('#port-cash').textContent==='$99,798.00',null,{timeout:2000});
  const staleOrderResponse=first.waitForResponse(response=>new URL(response.url()).pathname==='/api/game/port');
  releaseHeldRead();releaseHeldRead=null;await staleOrderResponse;
  await first.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await first.locator('#port-cash').textContent(),'$99,798.00','an older poll cannot roll back an accepted order');
  assert.equal(posts.length,1);
  assert(chartRequests.every(request=>request.token===posts[0].body.token),'chart history and orders authenticate as the same seat');
  assert.equal(portfolio.ledger.orders.length,1);
  assert.equal(await first.locator('[data-order-action="fill"]').count(),0,'server orders have no client fill action');
  assert.match(await first.locator('#port-portfolio-orders').textContent(),/Waiting for fresh quote/);

  // An authoritative fill appears on both devices; the browser never performs it.
  const buy=portfolio.ledger.orders[0];buy.status='filled';
  portfolio.account.reservedCash=0;
  portfolio.positions.AAPL={symbol:'AAPL',quantity:2,avgCost:101,totalCost:202,marketPrice:100,marketValue:200,unrealizedPnl:-2};
  portfolio.ledger.fills.push({orderId:buy.id,symbol:'AAPL',side:'buy',quantity:2,fillPrice:101,createdAt:new Date().toISOString()});
  await first.locator('#port-tab-positions').click();await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-ticket-feedback').textContent.includes('Bought 2 AAPL at $101.00'));
  assert.equal(await first.locator('#port-tab-positions').getAttribute('aria-selected'),'true','a background fill respects the selected portfolio tab');
  await first.setViewportSize({width:320,height:900});
  const holdingButton=await first.locator('#port-portfolio-positions .port-position-button').elementHandle();
  await holdingButton.focus();
  const scrollBefore=await first.locator('#port-portfolio-positions .port-table-wrap').evaluate(wrap=>{wrap.scrollLeft=100;return wrap.scrollLeft;});
  assert(scrollBefore>0,'the mobile positions table has a horizontal reading position');
  portfolio.positions.AAPL.marketValue=203;portfolio.positions.AAPL.unrealizedPnl=1;
  await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-portfolio-positions').textContent.includes('$203.00'));
  assert(await first.evaluate(button=>button===document.activeElement,holdingButton),'changing position values retain keyboard focus');
  assert.equal(await first.locator('#port-portfolio-positions .port-table-wrap').evaluate(wrap=>wrap.scrollLeft),scrollBefore,'changing position values retain mobile table scroll');
  await first.setViewportSize({width:1366,height:900});
  const second=await device();
  await waitCash(second,'$99,798.00');
  await second.locator('#port-tab-positions').click();
  assert.match(await second.locator('#port-portfolio-positions').textContent(),/AAPL/);
  await second.locator('.port-side-switch button[data-side="sell"]').click();
  await second.locator('#port-ticket-submit').click();
  await second.waitForFunction(()=>document.querySelector('#port-order-count').textContent==='(1)');
  const sell=portfolio.ledger.orders[1];assert.equal(sell.side,'sell');sell.status='filled';
  portfolio.account.availableCash+=99;portfolio.account.realizedPnl=-2;
  portfolio.positions.AAPL={...portfolio.positions.AAPL,quantity:1,totalCost:101,marketValue:100,unrealizedPnl:-1};
  portfolio.ledger.fills.push({orderId:sell.id,symbol:'AAPL',side:'sell',quantity:1,fillPrice:99,createdAt:new Date().toISOString()});
  await first.reload();await waitCash(first,'$99,897.00');
  await first.locator('#port-tab-history').click();
  assert.match(await first.locator('#port-portfolio-history').textContent(),/SELL/,'sell from the other browser appears in history');
  assert.match(await first.locator('#port-portfolio-history').textContent(),/ ET/,'trade history uses explicit New York market time');

  // A committed request whose response is lost is retried with its original ID.
  await first.locator('#port-ticket-type').selectOption('limit');
  assert.match(await first.locator('#port-ticket-note').textContent(),/fresh ask.*GTC.*until filled or cancelled/,'the limit ticket explains its price and lifetime');
  await first.locator('#port-ticket-limit').fill('1');
  dropNextPost=true;
  await first.locator('#port-ticket-submit').click();
  await first.waitForFunction(()=>document.querySelector('#port-ticket-submit').textContent.startsWith('RETRY'));
  const uncertainId=posts.at(-1).body.clientOrderId;
  const orderCount=portfolio.ledger.orders.length;
  assert(await first.locator('#port-ticket-quantity').isDisabled(),'unconfirmed request cannot be silently edited');
  readBlocked=false;
  await first.locator('#port-ticket-submit').click();
  await first.waitForFunction(()=>document.querySelector('#port-ticket-submit').textContent==='PLACE BUY ORDER');
  assert.equal(posts.at(-1).body.clientOrderId,uncertainId,'retry keeps the original idempotency key');
  assert.equal(portfolio.ledger.orders.length,orderCount,'retry does not create another order');
  await first.locator('#port-tab-orders').click();
  const slowCancelRead=holdRead();await refresh(first);await slowCancelRead;
  await first.locator('[data-order-action="cancel"]').click();
  await first.waitForFunction(()=>document.querySelector('#port-portfolio-orders').textContent.includes('Cancellation pending'),null,{timeout:2000});
  const staleCancelResponse=first.waitForResponse(response=>new URL(response.url()).pathname==='/api/game/port');
  releaseHeldRead();releaseHeldRead=null;await staleCancelResponse;
  await first.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.match(await first.locator('#port-portfolio-orders').textContent(),/Cancellation pending/,'an older poll cannot undo a cancellation acknowledgment');
  assert(posts.at(-1).body.clientOrderId,'cancellation also has its own idempotency key');
  assert(await first.locator('[data-order-action="cancel"]').isDisabled());
  const cancelled=portfolio.ledger.orders.find(order=>order.id===uncertainId);cancelled.status='canceled';
  portfolio.account.availableCash+=cancelled.quantity*cancelled.limitPrice;portfolio.account.reservedCash-=cancelled.quantity*cancelled.limitPrice;
  await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-ticket-feedback').textContent.includes('AAPL buy order cancelled'));
  assert.equal(await first.locator('#port-tab-orders').getAttribute('aria-selected'),'true','confirmed cancellation does not switch tabs');

  // A reset invalidates an unresolved request rather than replaying it into
  // the replacement account, including after the original browser reloads.
  dropNextPost=true;
  await first.locator('#port-ticket-submit').click();
  await first.waitForFunction(()=>document.querySelector('#port-ticket-submit').textContent.startsWith('RETRY'));
  const writesBeforeReset=posts.length;
  portfolio={accountId:'replacement-ui-account',account:{startingCash:100000,availableCash:100000,reservedCash:0,realizedPnl:0},positions:{},ledger:{orders:[],fills:[],cashEvents:[]},meta:{updatedAt:new Date().toISOString(),revision:0}};
  readBlocked=false;
  await first.reload();await waitCash(first,'$100,000.00');
  assert.match(await first.locator('#port-ticket-feedback').textContent(),/account was reset/);
  assert.equal(posts.length,writesBeforeReset,'refresh never submits the old request to a replacement account');
  assert.equal(await first.evaluate(()=>sessionStorage.getItem('yport.pendingRequest.v1')),null);

  // Device-clock jumps happen between responses; they cannot disable a fresh
  // quote, change countdowns, or revive a quote that the server considers old.
  const jumps=await first.evaluate(()=>{
   const original=Date.now,input=document.querySelector('#port-ticket-quantity'),button=document.querySelector('#port-ticket-submit');
   const results=[];
   try{for(const offset of [365*86400000,-365*86400000]){
    Date.now=()=>original()+offset;input.dispatchEvent(new Event('input',{bubbles:true}));
    results.push({disabled:button.disabled,note:document.querySelector('#port-ticket-note').textContent});
   }}finally{Date.now=original;input.dispatchEvent(new Event('input',{bubbles:true}));}
   return {results};
  });
  assert(jumps.results.every(result=>!result.disabled),'browser clock jumps do not disable fresh server quotes');
  assert(jumps.results.every(result=>/\(in (?:1h 0m|60m)\)/.test(result.note)),'session countdown uses elapsed time, not the browser date');

  stale=true;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-ticket-note').textContent.includes('Waiting for a fresh'));
  assert(await first.locator('#port-ticket-submit').isDisabled(),'stale quote blocks new orders');
  assert(await first.evaluate(()=>{
   const original=Date.now,input=document.querySelector('#port-ticket-quantity');
   try{Date.now=()=>original()-60000;input.dispatchEvent(new Event('input',{bubbles:true}));return document.querySelector('#port-ticket-submit').disabled;}
   finally{Date.now=original;input.dispatchEvent(new Event('input',{bubbles:true}));}
  }),'rolling back a device clock cannot make a stale quote tradable');
  stale=false;closePassed=true;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-ticket-note').textContent.includes('Regular session closed'));
  assert(await first.locator('#port-ticket-submit').isDisabled(),'the known regular-session close blocks an order before another market status arrives');
  closePassed=false;marketClosed=true;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-data-label').textContent==='Market closed');
  assert.match(await first.locator('#port-ticket-note').textContent(),/opens.* ET/,'closed market shows the next opening in New York time');
  marketClosed=false;unconfigured=true;await refresh(first);
  await first.waitForFunction(()=>document.querySelector('#port-selected-price').textContent==='—');
  assert(await first.locator('#port-ticket-submit').isDisabled(),'unconfigured provider cannot trade');
  assert.equal(await first.evaluate(key=>localStorage.getItem(key),oldKey),sample);
  const beforeClockRollback=chartRequests.length;
  await first.clock.setSystemTime(new Date(Date.now()-365*86400000));
  await first.clock.fastForward(31000);
  await first.waitForRequest(request=>new URL(request.url()).pathname==='/api/game/port/chart',{timeout:10000}).catch(error=>{if(chartRequests.length===beforeClockRollback)throw error;});
  assert(chartRequests.length>beforeClockRollback,'history refresh follows elapsed time despite a backward device-clock jump');
  for(const width of [1366,320]){
   await first.setViewportSize({width,height:900});
   const bounds=await first.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,
    panels:[...document.querySelectorAll('main .port-panel')].map(panel=>{const rect=panel.getBoundingClientRect();return {left:rect.left,right:rect.right};})}));
   assert(bounds.document<=bounds.width+1,'server status messages fit '+width+'px');
   assert(bounds.panels.every(panel=>panel.left>=-1&&panel.right<=bounds.width+1),'server panels fit '+width+'px');
  }
  assert.deepEqual(errors,[],'no uncaught frontend errors');
  console.log(JSON.stringify({result:'passed',checks:['empty before server load','sample isolation','authenticated historical chart ranges','chart survives polling, tab changes and resize','persisted area/candle preference','late chart response ignored','chart unavailable state','mobile chart fit','authoritative holdings and history across browsers','pending orders','exact retry after lost response','pending cancellation','reset after lost response and reload','monotonic server clock','ET session and execution rules','known close blocks orders','stale quote block','provider unavailable']}));
 }finally{releaseRead();if(releaseHeldRead)releaseHeldRead();if(releaseHeldChart)releaseHeldChart();for(const context of contexts)await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
