/* The LEAD page in a real browser: the class's real seats as fighter cards
   with stable portraits, PTS = net worth, the timeframe switch, and the LEAD
   tab visible in the navigation. Signs two throwaway students in.
   node tests/ui_lead.cjs http://127.0.0.1:4600 CLASSCODE */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3003';
const code=process.argv[3];
if(!code){console.error('usage: node tests/ui_lead.cjs BASE CLASSCODE');process.exit(2);}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  async function signIn(ctx,name,pin){
   const p=await ctx.newPage();await p.route('https://**/*',r=>r.abort());
   await p.goto(base+'/join.html');
   await p.fill('#join-code',code);await p.fill('#join-name',name);await p.fill('#join-pin',pin);
   await Promise.all([p.waitForURL(/buildings\.html/,{timeout:15000}),p.click('#join-btn')]);
   return p;
  }
  const other=await browser.newContext();await signIn(other,'UI TWO','2222');
  const ctx=await browser.newContext();const page=await signIn(ctx,'UI ONE','1111');
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/memos.html');
  await page.waitForFunction(()=>document.querySelectorAll('.memos-roster article.memos-fighter').length===2,null,{timeout:15000});
  const names=await page.$$eval('.memos-fighter .memos-fighter-name',els=>els.map(e=>e.textContent.trim()));
  assert.deepEqual([...names].sort(),['UI ONE','UI TWO'],'both real seats, nobody else');
  assert.doesNotMatch(await page.content(),/OGAN BEYAZCA|PELLI TURIN|WARREN BUFFETT/,'no sample fighters');
  assert.equal(await page.$eval('.memos-fighter.is-you .memos-fighter-name',e=>e.textContent.trim()),'UI ONE');
  const srcs=await page.$$eval('.memos-fighter-portrait',imgs=>imgs.map(i=>[i.getAttribute('src'),i.naturalWidth]));
  for(const [src,w] of srcs){assert.match(src,/^\.\/assets\/hero-select\/player-[a-z]+\.png$/,src);assert.ok(w>0,'portrait loaded: '+src);}
  const pts=await page.$$eval('.memos-points-value',els=>els.map(e=>e.textContent.trim()));
  pts.forEach(v=>assert.match(v,/^[\d,]+$/,'PTS is a number: '+v));
  assert.match(await page.$eval('.memos-fighter .memos-points-delta',e=>e.textContent),/Δ/);
  assert.deepEqual(await page.$$eval('.memos-rank',els=>els.map(e=>e.textContent.trim())),['#1','#2']);
  assert.equal(await page.$eval('.memos-timeframe-btn.is-active',e=>e.dataset.timeframe),'daily');
  await page.click('.memos-timeframe-btn[data-timeframe="weekly"]');
  assert.equal(await page.$eval('.memos-timeframe-btn.is-active',e=>e.dataset.timeframe),'weekly');
  assert.match(page.url(),/tf=weekly/);
  assert.ok(await page.$eval('.memos-fighter-bg-canvas',c=>c.width>0),'glow canvas sized');
  // the same student keeps the same face
  const before=await page.$eval('.memos-fighter.is-you .memos-fighter-portrait',i=>i.getAttribute('src'));
  await page.reload();
  await page.waitForFunction(()=>document.querySelectorAll('.memos-roster article.memos-fighter').length===2,null,{timeout:15000});
  assert.equal(await page.$eval('.memos-fighter.is-you .memos-fighter-portrait',i=>i.getAttribute('src')),before);
  // the LEAD tab is visible in the navigation again
  await page.goto(base+'/index.html');
  assert.ok(await page.isVisible('a.tab[href*="memos.html"]'),'LEAD tab visible on index.html');
  assert.deepEqual(errors,[],'no page errors');
  console.log('ui_lead: ok');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
