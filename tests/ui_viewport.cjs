/* Read-only checks against a running game. No purchases or saved game actions.
   node tests/ui_viewport.cjs [http://127.0.0.1:3003] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3003';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const errors=[];let panels=0,pages=0;
  page.on('pageerror',e=>errors.push(e.message));await page.route('https://**/*',r=>r.abort());
  async function visibleBounds(label){
   const bad=await page.evaluate(()=>{
    const selectors='.game-workspace button,.game-workspace select,.game-workspace .econ-good-line,.game-inventory-row,.game-check,.game-next-art';
    return [...document.querySelectorAll(selectors)].filter(e=>e.getClientRects().length&&!e.closest('[hidden]')).map(e=>({text:e.textContent.trim().slice(0,50),rect:e.getBoundingClientRect()})).filter(e=>e.rect.bottom>innerHeight+1||e.rect.right>innerWidth+1||e.rect.top<0).map(e=>e.text);
   });
   assert.deepEqual(bad,[],label+' clipped content');
   assert(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1&&document.documentElement.scrollWidth<=innerWidth+1),label+' page scroll');
  }
  for(const [width,height] of [[1366,768],[1366,650],[1728,694],[1920,1080],[1024,768],[768,768],[390,844],[844,390]]){
   await page.setViewportSize({width,height});
   for(const file of ['buildings','marketplace','advanced-hq','license']){
    await page.goto(base+'/'+file+'.html');
    try{await page.locator('.game-resources,.game-wallet').waitFor({state:'attached'});}
    catch(error){throw new Error(file+' '+width+'x'+height+' did not load at '+page.url()+': '+(await page.locator('body').innerText()).slice(0,600)+'; '+error.message);}
    if(await page.locator('#econ-overnight[open]').count())await page.locator('[data-overnight-close]').click();
    const tabs=await page.locator('.game-view-tabs button').count();
    for(let i=0;i<Math.max(tabs,1);i++){
     if(tabs)await page.locator('.game-view-tabs button').nth(i).click();
     const label=file+' '+width+'x'+height+' panel '+i;await visibleBounds(label);panels++;
     const keys=await page.locator('.game-pager').evaluateAll(es=>es.filter(e=>e.getClientRects().length).map(e=>e.dataset.page));
     for(const key of keys){
      const nav=page.locator('.game-pager[data-page="'+key+'"]');
      for(let guard=0;await nav.locator('button:first-child:not(:disabled)').count();guard++){assert(guard<30);await nav.locator('button:first-child').click();}
      for(let guard=0;await nav.locator('button:last-child:not(:disabled)').count();guard++){assert(guard<30);await nav.locator('button:last-child').click();await visibleBounds(label+' '+key);pages++;}
     }
    }
   }
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'passed',panels,paginationSteps:pages,viewports:8},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
