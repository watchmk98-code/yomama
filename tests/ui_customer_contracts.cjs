/* Real customer actions against a NEW isolated --fresh preview, never game.db.
   node tests/ui_customer_contracts.cjs http://127.0.0.1:3007
   Includes one real recurring payout; allow about three minutes. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2];
if(!base)throw new Error('Provide a new isolated --fresh preview URL');

(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('https://**/*',route=>route.abort());
  await page.goto(base+'/marketplace.html');
  const panel=page.locator('.game-customer-contracts');
  await panel.waitFor();
  assert.equal(await page.locator('.game-order').count(),3);
  assert.equal(await panel.locator('[data-customer-slot]').count(),2);
  const initial=await (await fetch(base+'/api/game/econ/state')).json();
  assert.equal(initial.customerContracts.active.length,0,'use a fresh isolated preview');
  const candidates=initial.customerContracts.customers.filter(c=>c.available);
  assert(candidates.length>=3);
  const chooser=panel.locator('#game-customer-choice');
  await chooser.selectOption(candidates[1].id);
  await chooser.focus();
  const refreshed=page.waitForResponse(r=>r.url().includes('/api/game/econ/state')&&r.ok());
  await page.evaluate(()=>window.YomamaEcon.refresh());await refreshed;
  assert.equal(await chooser.inputValue(),candidates[1].id,'choice survives polling');
  assert(await chooser.evaluate(el=>el===document.activeElement),'focus survives polling');

  async function act(button){
   const response=page.waitForResponse(r=>r.url().endsWith('/api/game/econ/customers')&&r.request().method()==='POST');
   await button.click();const result=await response;
   assert(result.ok(),await result.text());
   const payload=await result.json();
   await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
   return payload;
  }
  await chooser.selectOption(candidates[0].id);
  const signed=await act(panel.getByRole('button',{name:'Sign customer',exact:true}));
  const first=signed.customerContracts.active[0];
  assert.equal(first.customerId,candidates[0].id);
  assert.equal(signed.customerContracts.earned,0,'signing grants no cash');
  const paused=await act(panel.getByRole('button',{name:'Pause',exact:true}));
  assert(paused.customerContracts.active[0].paused);
  await page.reload();await panel.getByRole('button',{name:'Resume',exact:true}).waitFor();
  await act(panel.getByRole('button',{name:'Resume',exact:true}));
  await panel.locator('[data-customer-slot="1"]').click();
  await chooser.selectOption(candidates[1].id);
  const second=await act(panel.getByRole('button',{name:'Sign customer',exact:true}));
  assert.equal(second.customerContracts.active.length,2);
  const released=await act(panel.getByRole('button',{name:'Release',exact:true}));
  assert.equal(released.customerContracts.active.length,1);
  await panel.locator('[data-customer-slot="0"]').click();
  await panel.getByRole('button',{name:'Switch',exact:true}).click();
  await chooser.selectOption(candidates[2].id);
  const switched=await act(panel.getByRole('button',{name:'Switch customer',exact:true}));
  assert.notEqual(switched.customerContracts.active[0].id,first.id);
  await panel.getByRole('button',{name:'Switch',exact:true}).click();
  await chooser.selectOption(candidates[0].id);
  await act(panel.getByRole('button',{name:'Switch customer',exact:true}));

  for(const [width,height] of [[1366,768],[1024,768],[390,844],[844,390]]){
   await page.setViewportSize({width,height});
   await page.evaluate(()=>window.YomamaFit.render());
   const tab=page.getByRole('tab',{name:'Contracts',exact:true});
   if(await tab.count())await tab.click();
   await panel.waitFor({state:'visible'});
   const clipped=await panel.evaluate(root=>[...root.querySelectorAll('button,select,.econ-good-line')]
    .filter(el=>el.getClientRects().length&&!el.closest('[hidden]')).filter(el=>{
     const r=el.getBoundingClientRect();return r.top<0||r.bottom>innerHeight+1||r.right>innerWidth+1||r.left<0;
    }).map(el=>el.textContent.trim()));
   assert.deepEqual(clipped,[],width+'x'+height+' customer controls clipped');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1));
  }
  await page.setViewportSize({width:1366,height:768});await page.evaluate(()=>window.YomamaFit.render());
  console.log('Customer signup, polling, persistence, pause/resume, release, switch and four viewport checks passed. Waiting for the first real shipment.');
  await page.waitForFunction(()=>{
   const text=document.querySelector('.game-contract-history')?.textContent||'';
   return /[1-9][0-9]* shipments/.test(text);
  },{},{timeout:(candidates[0].intervalSeconds+45)*1000});
  const paid=await (await fetch(base+'/api/game/econ/state')).json();
  assert(paid.customerContracts.earned>=candidates[0].reward);
  assert(paid.customerContracts.deliveries>=1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',earned:paid.customerContracts.earned,shipments:paid.customerContracts.deliveries}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
