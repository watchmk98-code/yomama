/* The login wall, LOG OUT, idle sign-out and cross-tab sign-out in a real
   browser, against a running server and an open class. Signs a throwaway
   student in through the real join form; no purchases.
   node tests/ui_account.cjs http://127.0.0.1:4500 CLASSCODE */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3003';
const code=process.argv[3];
if(!code){console.error('usage: node tests/ui_account.cjs BASE CLASSCODE');process.exit(2);}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const ctx=await browser.newContext();
  const page=await ctx.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://**/*',r=>r.abort());          // no CDN, no news feeds
  async function signIn(p){
   await p.goto(base+'/join.html');
   await p.fill('#join-code',code);await p.fill('#join-name','UI TESTER');await p.fill('#join-pin','4321');
   await Promise.all([p.waitForURL(/buildings\.html/,{timeout:15000}),p.click('#join-btn')]);
  }
  // Nobody sees a page before signing in: the server sends the browser to join.html.
  for(const p of ['index.html','buildings.html','teach.html','']){
   await page.goto(base+'/'+p);
   await page.waitForURL(/join\.html\?next=/,{timeout:10000});
   assert.equal(await page.locator('#join-form').count(),1,p+': landed on the sign-in form');
  }
  await signIn(page);
  // Signed in, every page with the header loads and has a live LOG OUT.
  for(const p of ['index.html','buildings.html','marketplace.html','memos.html','port_trading.html','teach.html']){
   await page.goto(base+'/'+p);
   assert.doesNotMatch(page.url(),/join\.html/,p+': served, not sent to sign in');   // pages may add their own ?query
   const btn=page.locator('button[data-account]').first();
   assert.equal((await btn.textContent()).trim(),'LOG OUT',p+': LOG OUT wired');
  }
  // A browser that still holds its seat but lost the cookie is sent to join.html
  // and straight back again, without retyping anything.
  await ctx.clearCookies();
  await page.goto(base+'/marketplace.html');
  await page.waitForURL(/marketplace\.html$/,{timeout:15000});
  assert.equal((await page.locator('button[data-account]').first().textContent()).trim(),'LOG OUT');
  // A second tab of the same browser is signed out too.
  const other=await ctx.newPage();await other.route('https://**/*',r=>r.abort());
  await other.goto(base+'/buildings.html');
  await page.goto(base+'/buildings.html');
  await Promise.all([page.waitForURL(/join\.html\?signedout=1/,{timeout:10000}),page.click('button[data-account]')]);
  assert.equal(await page.evaluate(()=>localStorage.getItem('yomama_session_v1')),null,'session cleared');
  assert.equal(await page.evaluate(()=>localStorage.getItem('yomama_server_cash_v1')),null,'cash mirror cleared');
  assert.equal((await ctx.cookies()).filter(c=>c.name==='yomama_session').length,0,'cookie cleared');
  await other.waitForURL(/join\.html\?signedout=1/,{timeout:10000});
  assert.match(await page.locator('#join-msg').textContent(),/Signed out/);
  // Signed out, no page is served any more.
  await page.goto(base+'/buildings.html');
  await page.waitForURL(/join\.html\?next=/,{timeout:10000});
  // Idle sign-out, with the window shortened to about two seconds.
  await page.addInitScript(()=>{window.YOMAMA_IDLE_MINUTES=0.03;});
  await signIn(page);
  await page.waitForURL(/join\.html\?signedout=idle/,{timeout:15000});
  assert.match(await page.locator('#join-msg').textContent(),/without activity/);
  assert.equal(await page.evaluate(()=>localStorage.getItem('yomama_session_v1')),null,'idle cleared the session');
  assert.deepEqual(errors,[],'no page errors');
  console.log('ui_account: ok');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
