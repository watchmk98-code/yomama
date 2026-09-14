/* Run against an ISOLATED preview only: buys basic supplies and crafts one trap.
   node tests/ui_craft.cjs http://127.0.0.1:4130 */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:4130';
const target = new URL(base);
assert(['127.0.0.1','localhost','[::1]'].includes(target.hostname) && target.port !== '3000',
  'Craft tests require a local isolated preview, not the real development save or live service.');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1366,height:768}});
    const buildPage = await browser.newPage({viewport:{width:1366,height:768}});
    const errors = [], badAssets = [], craftRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (/\/assets\/(craft|game-art\/goods)\//.test(response.url()) && response.status() >= 400) badAssets.push(response.url());
    });
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/game/craft') craftRequests.push(request.postDataJSON());
    });
    await page.route('https://**/*', route => route.abort());
    await buildPage.route('https://**/*', route => route.abort());
    async function headerSnapshot(tab) {
      return tab.evaluate(() => {
        const selectors=['.hero','.hero .topline','.hero .banner-frame','.hero .tabs'];
        const properties=['display','backgroundColor','borderTopWidth','borderTopColor','borderBottomWidth','borderBottomColor','paddingTop','paddingRight','paddingBottom','paddingLeft','fontFamily','fontSize'];
        const boxes=selectors.map(selector=>{
          const node=document.querySelector(selector), rect=node.getBoundingClientRect(), style=getComputedStyle(node);
          return {selector,geometry:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},style:Object.fromEntries(properties.map(property=>[property,style[property]]))};
        });
        const banner=document.querySelector('.hero-banner');
        return {boxes,banner:new URL(banner.src).pathname,tabs:[...document.querySelectorAll('.hero .tabs a')].filter(node=>node.getClientRects().length).map(node=>({href:new URL(node.href).pathname,label:node.textContent.trim()}))};
      });
    }
    async function checkHeader(label) {
      const [actual,expected]=await Promise.all([headerSnapshot(page),headerSnapshot(buildPage)]);
      assert.equal(actual.banner,expected.banner,label+' must reuse BUILD banner');
      assert.deepEqual(actual.tabs,expected.tabs,label+' must preserve BUILD primary navigation');
      for(let index=0;index<expected.boxes.length;index++) {
        const a=actual.boxes[index], e=expected.boxes[index];
        assert.deepEqual(a.style,e.style,label+' '+e.selector+' styles differ from BUILD');
        for(const property of Object.keys(e.geometry)) {
          assert(Math.abs(a.geometry[property]-e.geometry[property])<=1,
            label+' '+e.selector+' '+property+' differs from BUILD: '+a.geometry[property]+' versus '+e.geometry[property]);
        }
      }
    }
    async function ready() {
      await page.waitForFunction(() => window.YomamaCraft && window.YomamaCraft.state() && window.YomamaCraft.state().crafting);
      assert.equal(await page.locator('[data-craft-item]').count(), 30);
      assert.equal(await page.locator('[data-craft-item]:visible').count(), 30, 'all items share one grid');
      assert.equal(await page.locator('.craft-pager').count(), 0, 'crafting has no pagination');
      await page.evaluate(() => document.fonts.ready);
    }
    async function openItem(id) {
      if (await page.locator('#craft-dialog[open]').count()) await page.locator('#craft-close').click();
      const card=page.locator('[data-craft-item="'+id+'"]');
      await card.scrollIntoViewIfNeeded();
      await card.click();
      await page.locator('#craft-dialog[open]').waitFor();
    }
    async function checkViewport(label) {
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1 && document.documentElement.scrollHeight <= innerHeight+1), label+' page overflow');
      const clipped = await page.locator('.game-nav a').evaluateAll(nodes => nodes.filter(n => {
        const r=n.getBoundingClientRect(); return r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1;
      }).map(n=>n.textContent.trim()));
      assert.deepEqual(clipped, [], label+' clipped controls');
      assert.equal(await page.locator('[data-craft-item]:visible').count(),30,label+' hides items');
      assert.equal(await page.locator('.craft-pager').count(),0,label+' adds pagination');
      const grid=await page.locator('#craft-grid').evaluate(node=>{
        const r=node.getBoundingClientRect();
        return {horizontalOverflow:node.scrollWidth>node.clientWidth+1,outsideViewport:r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1};
      });
      assert(!grid.horizontalOverflow,label+' grid scrolls horizontally');
      assert(!grid.outsideViewport,label+' grid exceeds screen');
      const clippedLabels=await page.locator('.craft-item-name').evaluateAll(nodes=>nodes.filter(node=>{
        const card=node.closest('.craft-item'), r=node.getBoundingClientRect(), c=card.getBoundingClientRect();
        return node.scrollWidth>node.clientWidth+1 || node.scrollHeight>node.clientHeight+1 || card.scrollWidth>card.clientWidth+1 || card.scrollHeight>card.clientHeight+1 || r.left<c.left+1 || r.right>c.right-1 || r.top<c.top+1 || r.bottom>c.bottom-1;
      }).map(node=>node.textContent.trim()));
      assert.deepEqual(clippedLabels,[],label+' item names overflow their cards');
      if (await page.evaluate(()=>innerWidth>=1000 && innerHeight>=600)) {
        const offscreen=await page.locator('[data-craft-item]').evaluateAll(nodes=>{
          const grid=document.getElementById('craft-grid').getBoundingClientRect();
          return nodes.filter(node=>{
            const r=node.getBoundingClientRect();
            return r.left<Math.max(0,grid.left)-1 || r.right>Math.min(innerWidth,grid.right)+1 || r.top<Math.max(0,grid.top)-1 || r.bottom>Math.min(innerHeight,grid.bottom)+1;
          }).map(node=>node.textContent.trim());
        });
        assert.deepEqual(offscreen,[],label+' must show all 30 items on screen');
      }
    }
    await Promise.all([page.goto(base+'/craft.html'),buildPage.goto(base+'/buildings.html')]);
    await ready();
    await buildPage.waitForFunction(()=>window.YomamaEcon && window.YomamaEcon.state());
    await buildPage.evaluate(()=>document.fonts.ready);
    if(await buildPage.locator('#econ-overnight[open]').count()) await buildPage.locator('[data-overnight-close]').click();
    const links = await page.locator('.game-nav a').evaluateAll(nodes => nodes.map(n=>new URL(n.href).pathname));
    assert.deepEqual(links, ['/buildings.html','/marketplace.html','/craft.html','/advanced-hq.html','/license.html']);
    await openItem('fish_trap');
    assert.equal(await page.locator('#craft-submit').innerText(), 'CRAFT');
    await page.locator('#craft-close').focus();
    await page.evaluate(() => window.YomamaCraft.refresh());
    assert.equal(await page.evaluate(() => document.activeElement.id), 'craft-close', 'poll preserves dialog focus');
    const before = await page.evaluate(() => window.YomamaCraft.state().crafting.items.find(item=>item.id==='fish_trap').owned);
    for (let tries=0; await page.locator('[data-craft-buy]').count(); tries++) {
      assert(tries<3, 'trap has only two basic ingredients');
      const button=page.locator('[data-craft-buy]').first();
      assert(!await button.isDisabled(), 'preview needs enough cash to purchase missing supplies');
      const response = page.waitForResponse(response=>new URL(response.url()).pathname==='/api/game/craft');
      await button.click(); assert.equal((await response).status(),200);
      await page.waitForFunction(() => document.getElementById('craft-submit').getAttribute('aria-busy')==='false');
    }
    assert(!await page.locator('#craft-submit').isDisabled());
    const requestCount = craftRequests.length;
    const response = page.waitForResponse(response=>new URL(response.url()).pathname==='/api/game/craft');
    await page.locator('#craft-submit').evaluate(button=>{button.click();button.click();});
    assert.equal((await response).status(),200);
    await page.waitForFunction(expected=>window.YomamaCraft.state().crafting.items.find(item=>item.id==='fish_trap').owned===expected, before+1);
    assert.equal(craftRequests.length,requestCount+1,'duplicate click makes only one request');
    assert.match(await page.locator('#craft-status').innerText(), /Crafted Woven Fish Trap/);
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'craft-item-fish_trap','close returns focus to item');
    await page.reload(); await ready();
    assert.equal(await page.evaluate(()=>window.YomamaCraft.state().crafting.items.find(item=>item.id==='fish_trap').owned),before+1,'crafted item survives reload');

    for (const [width,height] of [[1366,768],[1366,650],[1920,1080],[1024,768],[768,768],[390,844],[360,640],[844,390]]) {
      await Promise.all([page.setViewportSize({width,height}),buildPage.setViewportSize({width,height})]);
      await page.waitForFunction(() => [...document.querySelectorAll('.craft-item')].filter(n=>!n.hidden).length===30);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const label=width+'x'+height; await checkViewport(label); await checkHeader(label);
      await openItem('satellite_survey_map');
      assert.equal(await page.locator('#craft-dialog-title').textContent(),'Satellite Survey Map',label+' last item is reachable');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(()=>document.activeElement.id),'craft-item-satellite_survey_map',label+' restores last-item focus');
      // Five ingredients and explicit purchase controls exercise long-dialog scrolling.
      await openItem('smoking_cabinet');
      const bounds=await page.locator('#craft-dialog').boundingBox();
      assert(bounds.x>=0 && bounds.y>=0 && bounds.x+bounds.width<=width+1 && bounds.y+bounds.height<=height+1,label+' dialog outside viewport');
      assert(await page.locator('#craft-dialog').evaluate(node=>node.scrollWidth<=node.clientWidth+1),label+' dialog horizontal overflow');
      await page.locator('#craft-submit').scrollIntoViewIfNeeded();
      const button=await page.locator('#craft-submit').boundingBox();
      assert(button.y>=0 && button.y+button.height<=height,label+' craft button unreachable');
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors,[]); assert.deepEqual(badAssets,[]);
    console.log(JSON.stringify({result:'passed',items:30,viewports:8,headerMatchesBuild:true,crafted:'Woven Fish Trap',requests:craftRequests.length},null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
