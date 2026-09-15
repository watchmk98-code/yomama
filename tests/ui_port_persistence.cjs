/* Real SQLite/API portfolio across separate browser contexts; no API mocking.
   Run against previews/port_preview.py --fixture-quotes only. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2];
const url=new URL(base);
if(!['127.0.0.1','localhost'].includes(url.hostname)||url.port==='3000')throw Error('Use an isolated PORT test preview');

(async()=>{
 const browser=await chromium.launch({headless:true});
 const errors=[];
 try{
  async function device(){
   const context=await browser.newContext({viewport:{width:1366,height:900}});
   const page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('https://**/*',r=>r.abort());
   await page.goto(base+'/port_trading.html');
   await page.getByText('Saved to your student seat',{exact:true}).waitFor();
   return {context,page};
  }
  const first=await device();
  async function portfolio(page){
   return page.evaluate(async()=>{
    const {token}=JSON.parse(localStorage.getItem('yomama_session_v1'));
    return (await fetch('/api/game/port?token='+encodeURIComponent(token))).json();
   });
  }
  const initial=await portfolio(first.page);
  assert.equal(initial.market.source,'local_test_fixture','requires explicit temporary fixture feed');
  assert.equal(initial.portfolio.account.availableCash,100000);
  assert.deepEqual(initial.portfolio.positions,{});
  assert.equal(initial.portfolio.ledger.orders.length,0);
  await first.page.locator('#port-ticket-quantity').fill('2');
  await first.page.locator('#port-ticket-submit').click();
  await first.page.waitForFunction(()=>document.querySelector('#port-portfolio-positions tbody')?.textContent.includes('AAPL'));
  const bought=(await portfolio(first.page)).portfolio;
  assert.equal(bought.positions.AAPL.quantity,2);
  assert.equal(bought.account.availableCash,99799.98);
  const second=await device();
  const elsewhere=(await portfolio(second.page)).portfolio;
  assert.equal(elsewhere.accountId,bought.accountId);
  assert.equal(elsewhere.positions.AAPL.quantity,2);
  assert.equal(elsewhere.account.availableCash,bought.account.availableCash);
  assert.deepEqual(elsewhere.ledger,bought.ledger);
  await second.page.locator('[data-side="sell"]').click();
  await second.page.locator('#port-ticket-quantity').fill('1');
  await second.page.locator('#port-ticket-submit').click();
  await second.page.waitForFunction(()=>document.querySelector('#port-cash')?.textContent==='$99,899.97');
  await first.page.reload();
  await first.page.getByText('Saved to your student seat',{exact:true}).waitFor();
  const sold=(await portfolio(first.page)).portfolio;
  assert.equal(sold.positions.AAPL.quantity,1);
  assert.equal(sold.account.availableCash,99899.97);
  assert.equal(sold.ledger.fills.length,2);
  assert.equal(sold.account.realizedPnl,-.02);
  assert.equal(await first.page.evaluate(()=>localStorage.getItem('yport.paperState.v1')),null);
  assert.equal(await second.page.evaluate(()=>localStorage.getItem('yport.paperState.v1')),null);
  const offlineOrder=await second.page.evaluate(async()=>{
   const {token}=JSON.parse(localStorage.getItem('yomama_session_v1'));
   const state=await (await fetch('/api/game/port?token='+encodeURIComponent(token))).json();
   const clientOrderId=crypto.randomUUID();
   const response=await fetch('/api/game/port/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    token,accountId:state.portfolio.accountId,clientOrderId,symbol:'AAPL',side:'buy',type:'market',quantity:1
   })});
   const result=await response.json();
   if(!response.ok)throw Error(JSON.stringify(result));
   return {id:clientOrderId,status:result.portfolio.ledger.orders.find(order=>order.id===clientOrderId)?.status};
  });
  assert.equal(offlineOrder.status,'pending','order submission cannot fill itself');
  await first.context.close();
  await second.context.close();
  await new Promise(resolve=>setTimeout(resolve,4500));
  const reopenedAt=Date.now();
  const third=await device();
  const unattended=(await portfolio(third.page)).portfolio;
  const filled=unattended.ledger.orders.find(order=>order.id===offlineOrder.id);
  assert.equal(filled.status,'filled');
  assert.ok(Date.parse(filled.filledAt)<reopenedAt,'server filled before any browser reopened');
  assert.equal(unattended.positions.AAPL.quantity,2);
  assert.equal(unattended.account.availableCash,99799.96);
  assert.deepEqual(errors,[]);
  console.log('PASS: real server buy/sell, cross-device persistence, history, sample isolation, background fill with all browsers closed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
