/* Display-only population; intercept every API write. Use an isolated preview. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.argv[2] || 'http://127.0.0.1:3023';
(async () => {
  const state = await (await fetch(base + '/api/game/econ/state')).json();
  assert(state.workforce.population?.enabled && state.workforce.population.purposeEnabled === false);
  state.overnightReport = null; state.paused = false;
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1366,height:768}}), errors=[], writes=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>{
      const req=route.request(), url=new URL(req.url());
      if(url.origin!==base)return route.abort();
      if(url.pathname==='/api/game/econ/login')return route.fulfill({json:state});
      if(url.pathname.startsWith('/api/game/') && req.method()==='POST') {writes.push(url.pathname);return route.fulfill({status:409,json:{error:'Display test prevents writes'}});}
      if(url.pathname==='/api/game/state'||url.pathname.startsWith('/api/game/econ/'))return route.fulfill({json:state});
      if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
      return route.continue();
    });
    await page.goto(base+'/advanced-hq.html#workers');
    await page.locator('.wf-population-intro').waitFor();
    assert.equal(await page.locator('[data-worker-total]').textContent(),String(state.workforce.population.total));
    assert.equal(await page.locator('[data-wf-population-total]').textContent(),String(state.workforce.population.total));
    assert.match(await page.locator('.wf-population-intro').textContent(),/no gameplay role yet/);
    assert.equal(await page.locator('[data-wf-step],#game-wf-save-allocation,#game-wf-training-branch').count(),0);
    assert.equal(await page.locator('#game-wf-team-assignments,#game-wf-team-training').count(),0);
    state.workforce.population.total=0;
    await page.evaluate(()=>window.YomamaEcon.refresh());await page.waitForTimeout(150);
    assert.equal(await page.locator('[data-worker-total]').textContent(),'0');
    await page.locator('#game-workers-overview').click();
    assert(await page.locator('.wf-population-intro').isVisible());
    state.workforce.population.total=105;
    await page.evaluate(()=>window.YomamaEcon.refresh());await page.waitForTimeout(150);
    let views=0;fs.mkdirSync('.checks/worker-population',{recursive:true});
    for(const [width,height] of [[1366,768],[768,768],[390,844],[360,740],[844,390]]) {
      await page.setViewportSize({width,height});
      for(const tab of ['focus','team','recipes','quests','projects','hq']) {
        await page.locator('#game-wf-tab-'+tab).click();
        for(const view of (tab==='team'?['recruitment','business']:tab==='hq'?['academy','programs']:[null])) {
          if(view)await page.locator('#game-wf-'+tab+'-'+view).click();
          await page.waitForTimeout(90);
          // Project descriptions use the existing internal panel scroller.
          if(tab==='projects') {
            const claim=page.locator('.game-group-project button:visible').first();
            if(await claim.count())await claim.scrollIntoViewIfNeeded();
          }
          const bad=await page.evaluate(()=>[...document.querySelectorAll('.wf-workspace button,.wf-workspace select')].filter(e=>e.getClientRects().length&&!e.closest('[hidden]')).filter(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth+1||r.top<0||r.bottom>innerHeight+1;}).map(e=>e.textContent.trim().slice(0,60)));
          assert.deepEqual(bad,[],width+'x'+height+' '+tab+'/'+view+' clipped controls');
          assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1 && document.documentElement.scrollHeight<=innerHeight+1),'Page overflow');
          assert(await page.locator('#game-operations-prestige').isVisible());
          if(tab==='team'&&view==='recruitment')await page.screenshot({path:'.checks/worker-population/population-'+width+'.png'});
          views++;
        }
      }
    }
    assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
    console.log('PASS display-only population, zero/count refresh, no assignment controls, '+views+' responsive views');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
