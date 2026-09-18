/* The LOADING screen downloads the complete public art pack with byte
   progress, then keeps it ready for the remaining pages in this tab.
   node tests/ui_loading.cjs http://127.0.0.1:4500 CLASSCODE */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3003';
const code=process.argv[3];
if(!code){console.error('usage: node tests/ui_loading.cjs BASE CLASSCODE');process.exit(2);}
const gone=p=>p.waitForFunction(()=>!document.getElementById('yomama-loading'),null,{timeout:30000});
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const ctx=await browser.newContext();
  const page=await ctx.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://**/*',r=>r.abort());          // no CDN, no news feeds

  // Signing in lands on the build page behind a LOADING screen.
  await page.goto(base+'/join.html');
  await page.fill('#join-code',code);await page.fill('#join-name','LOAD TESTER');await page.fill('#join-pin','4321');
  await Promise.all([page.waitForURL(/buildings\.html/,{timeout:15000}),page.click('#join-btn')]);
  const screen=page.locator('#yomama-loading');
  await screen.waitFor({state:'visible',timeout:5000});
  assert.equal((await screen.locator('.yl-title').textContent()).trim(),'LOADING...','the big word');
  assert.equal(await page.locator('.shell').isVisible(),false,'the page stays hidden behind it');

  // The counter names the real pack size and reports received megabytes.
  const total=await page.locator('.yl-mb').innerText();
  assert.match(total,/\d+\.\d+ \/ \d+\.\d+ MB downloaded/);
  assert.ok(Number(total.split(' / ')[1].split(' ')[0])>=160,total);

  // The bar fills, and it only ever goes forwards.
  const seen=[];
  for(let i=0;i<24 && await page.locator('#yomama-loading').count();i++){
   seen.push(await page.evaluate(()=>{
    const el=document.querySelector('#yomama-loading .yl-fill');
    return el?parseFloat(el.style.width)||0:100;
   }));
   await page.waitForTimeout(250);
  }
  assert.ok(seen.some(v=>v>0)||!(await page.locator('#yomama-loading').count()),
    'the bar moved or finished, saw '+seen.join(','));
  for(let i=1;i<seen.length;i++) assert.ok(seen[i]>=seen[i-1],'the bar never goes backwards: '+seen.join(','));

  // It lets go after the complete pack is ready. Visible images have loaded.
  await gone(page);
  assert.equal(await page.evaluate(()=>sessionStorage.getItem('yomama_assets_ready_v1')),
    await page.evaluate(()=>window.YomamaPreloadManifest.version),'complete pack marked ready');
  assert.equal(await page.locator('.shell').isVisible(),true,'the page is visible once it is gone');
  const pending=await page.evaluate(()=>[...document.images]
   .filter(i=>i.getAttribute('src') && !i.complete).map(i=>i.getAttribute('src')));
  assert.deepEqual(pending,[],'no sprite still loading when the screen goes');
  assert.equal(await page.evaluate(()=>sessionStorage.getItem('yomama_boot_v1')),null,'the sign-in flag was spent');

  // Once per tab: the next pages open straight away, no second screen.
  for(const p of ['marketplace.html','craft.html','buildings.html']){
   await page.goto(base+'/'+p);
   await page.waitForTimeout(400);
   assert.equal(await page.locator('#yomama-loading').count(),0,p+': no second LOADING screen');
   assert.equal(await page.locator('.shell').isVisible(),true,p+': shown straight away');
  }

  // A new tab of the same browser has its own session storage, so it gets one.
  const tab=await ctx.newPage();await tab.route('https://**/*',r=>r.abort());
  await tab.goto(base+'/buildings.html');
  assert.equal(await tab.locator('#yomama-loading').count(),1,'a fresh tab loads its art too');
  await gone(tab);
  await tab.close();

  // Signing in again in the same tab keeps the completed pack.
  await page.goto(base+'/buildings.html');
  await page.click('button[data-account]');                // LOG OUT
  await page.waitForURL(/join\.html/,{timeout:10000});
  await page.fill('#join-code',code);await page.fill('#join-name','LOAD TESTER');await page.fill('#join-pin','4321');
  await Promise.all([page.waitForURL(/buildings\.html/,{timeout:15000}),page.click('#join-btn')]);
  assert.equal(await page.locator('#yomama-loading').count(),0,'completed pack is reused');

  // A failed download stays visible for retry; the student can enter anyway.
  const slow=await ctx.newPage();await slow.route('https://**/*',r=>r.abort());
  await slow.route('**/*.png',r=>r.abort());
  await slow.route('**/*.svg',r=>r.abort());
  await slow.goto(base+'/buildings.html');
  await slow.locator('.yl-retry').waitFor({state:'visible',timeout:30000});
  assert.match(await slow.locator('.yl-status').innerText(),/could not download/);
  await slow.locator('.yl-skip').click();
  await gone(slow);
  assert.equal(await slow.locator('.shell').isVisible(),true,'handed over even with no art at all');
  await slow.close();

  // Signed out, the screen never shows: account.js is sending them to join.html.
  await page.evaluate(()=>{localStorage.clear();sessionStorage.clear();});
  await ctx.clearCookies();
  await page.goto(base+'/buildings.html');
  await page.waitForURL(/join\.html/,{timeout:10000});
  assert.equal(await page.locator('#yomama-loading').count(),0,'no screen for a signed-out browser');

  assert.deepEqual(errors,[],'no page errors');
  console.log('ui_loading: ok');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
