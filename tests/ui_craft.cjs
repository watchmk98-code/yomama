/* Run against an ISOLATED preview only: buys basic and new advanced supplies,
   and crafts one trap.
   node tests/ui_craft.cjs http://127.0.0.1:4130 */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:4130';
const target = new URL(base);
const itemCount = 300;
const supplyCount = 64;
const addedSupplies = require('../previews/craft_expansion_64_supplies.json');
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
      const metrics=tab=>tab.locator('#game-hud [data-build-metric]').evaluateAll(nodes=>nodes.map(node=>({id:node.dataset.buildMetric,label:node.querySelector('dt').textContent.trim()})));
      const [actualMetrics,expectedMetrics]=await Promise.all([metrics(page),metrics(buildPage)]);
      assert.equal(expectedMetrics.length,5,label+' BUILD resource bar has five metrics');
      assert.deepEqual(actualMetrics,expectedMetrics,label+' must preserve BUILD resource bar metric names');
    }
    async function ready() {
      await page.waitForFunction(() => window.YomamaCraft && window.YomamaCraft.state() && window.YomamaCraft.state().crafting);
      assert.equal(await page.locator('[data-craft-item]').count(), itemCount);
      assert.equal(await page.locator('[data-craft-item]:visible').count(), itemCount, 'all items share one grid');
      assert.equal(await page.locator('.craft-pager').count(), 0, 'crafting has no pagination');
      await page.evaluate(() => document.fonts.ready);
    }
    async function checkArt() {
      const art=await page.evaluate(()=>{
        const crafting=window.YomamaCraft.state().crafting,items=crafting.items;
        const icons=[...document.querySelectorAll('[data-craft-item]')].map(card=>{
          const icon=card.querySelector('.craft-sprite'), style=getComputedStyle(icon,'::before');
          return {id:card.dataset.craftItem,image:style.backgroundImage,width:parseFloat(style.width),height:parseFloat(style.height),rendering:style.imageRendering,signature:[style.backgroundImage,style.backgroundPosition,style.backgroundSize].join('|')};
        });
        const metadata=(kind,indices)=>indices.map(index=>{
          let sheets=window.YomamaCraftArt[kind];if(!Array.isArray(sheets))sheets=[sheets];
          const matches=sheets.filter(sheet=>index>=(sheet.start||0) && index<(sheet.start||0)+sheet.rects.length);
          if(matches.length!==1)return {index,error:'Expected exactly one atlas entry'};
          const sheet=matches[0],rect=sheet.rects[index-(sheet.start||0)];
          const valid=rect.length===4 && rect.every(Number.isFinite) && rect[0]>=0 && rect[1]>=0 && rect[2]>0 && rect[3]>0 && rect[0]+rect[2]<=sheet.width && rect[1]+rect[3]<=sheet.height;
          return {index,error:valid?'':'Sprite bounds exceed the image',src:sheet.src,width:sheet.width,height:sheet.height,address:sheet.src+'|'+rect.join(',')};
        });
        return {ids:items.map(item=>item.id),indices:items.map(item=>item.iconIndex),supplyIds:crafting.supplies.map(supply=>supply.id),supplies:crafting.supplies,icons,itemMetadata:metadata('items',items.map(item=>item.iconIndex)),supplyMetadata:metadata('supplies',crafting.supplies.map((_,index)=>index))};
      });
      assert.equal(new Set(art.ids).size,itemCount,'every craft has a unique id');
      assert.equal(new Set(art.indices).size,itemCount,'every craft addresses a unique icon');
      assert.equal(new Set(art.supplyIds).size,supplyCount,'all 64 purchasable supplies have unique ids');
      assert.deepEqual(art.supplies.slice(36).map(({id,name,unitPrice})=>({id,name,unitPrice})),addedSupplies.map(({id,name,unitPrice})=>({id,name,unitPrice})),'the new 28 supplies follow the original 36 with their declared names and prices');
      assert.equal(new Set(art.icons.map(icon=>icon.signature)).size,itemCount,'300 crafts must not repeat the same sprite address');
      assert.deepEqual(art.icons.filter(icon=>!icon.image || icon.image==='none' || icon.width<=0 || icon.height<=0 || icon.rendering!=='pixelated'),[], 'every craft has visible pixel art');
      assert.deepEqual([...art.itemMetadata,...art.supplyMetadata].filter(entry=>entry.error),[],'every craft and supply resolves to valid art metadata');
      assert.equal(new Set(art.itemMetadata.map(entry=>entry.address)).size,itemCount,'all 300 item sprites have unique atlas addresses');
      assert.equal(new Set(art.supplyMetadata.map(entry=>entry.address)).size,supplyCount,'all 64 supply sprites have unique atlas addresses');
      const atlases=[...new Map([...art.itemMetadata,...art.supplyMetadata].map(entry=>[entry.src,{src:entry.src,width:entry.width,height:entry.height}])).values()];
      const loaded=await page.evaluate(atlases=>Promise.all(atlases.map(atlas=>new Promise(resolve=>{
        const image=new Image();image.onload=()=>resolve({src:atlas.src,width:image.naturalWidth,height:image.naturalHeight});image.onerror=()=>resolve({src:atlas.src,width:0,height:0});image.src=atlas.src;
      }))),atlases);
      assert.deepEqual(loaded,atlases,'every item and supply atlas loads with its declared dimensions');
      return art;
    }
    async function openItem(id) {
      if (await page.locator('#craft-dialog[open]').count()) await page.locator('#craft-close').click();
      const card=page.locator('[data-craft-item="'+id+'"]');
      await card.scrollIntoViewIfNeeded();
      await card.click();
      await page.locator('#craft-dialog[open]').waitFor();
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    }
    async function checkDialogFits(label) {
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const fit=await page.locator('#craft-dialog').evaluate(node=>{
        const r=node.getBoundingClientRect();
        const outside=r.left<0 || r.top<0 || r.right>innerWidth+1 || r.bottom>innerHeight+1;
        const clipped=[...node.querySelectorAll('button,tbody tr,.craft-dialog-head,.craft-makes,.craft-owned,.craft-reason,.craft-status')].filter(child=>child.getClientRects().length).filter(child=>{
          const c=child.getBoundingClientRect();
          return c.left<Math.max(0,r.left)-1 || c.right>Math.min(innerWidth,r.right)+1 || c.top<Math.max(0,r.top)-1 || c.bottom>Math.min(innerHeight,r.bottom)+1;
        }).map(child=>child.textContent.trim());
        const button=document.getElementById('craft-submit').getBoundingClientRect();
        return {outside,horizontalOverflow:node.scrollWidth>node.clientWidth+1,verticalOverflow:node.scrollHeight>node.clientHeight+1,scrollTop:node.scrollTop,scrollLeft:node.scrollLeft,clipped,craftVisible:button.top>=0 && button.bottom<=innerHeight && button.left>=0 && button.right<=innerWidth};
      });
      assert(!fit.outside,label+' dialog outside viewport');
      assert(!fit.horizontalOverflow,label+' dialog scrolls horizontally');
      assert(!fit.verticalOverflow,label+' dialog scrolls vertically');
      assert.equal(fit.scrollTop,0,label+' dialog should not need vertical scrolling');
      assert.equal(fit.scrollLeft,0,label+' dialog should not need horizontal scrolling');
      assert.deepEqual(fit.clipped,[],label+' recipe or controls are clipped');
      assert(fit.craftVisible,label+' CRAFT must be fully visible without scrolling');
    }
    async function checkItemDialog(item,label) {
      await openItem(item.id);
      assert.equal(await page.locator('#craft-dialog-title').textContent(),item.name,label+' opens the matching item');
      assert(item.ingredients.length>0,label+' has a recipe');
      assert.equal(await page.locator('#craft-ingredient-rows tr').count(),item.ingredients.length,label+' shows every ingredient');
      assert.equal(await page.locator('#craft-submit').textContent(),'CRAFT',label+' preserves the action label');
      await checkDialogFits(label);
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(()=>document.activeElement.id),'craft-item-'+item.id,label+' restores item focus');
    }
    async function checkViewport(label) {
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1 && document.documentElement.scrollHeight <= innerHeight+1), label+' page overflow');
      const clipped = await page.locator('.game-nav a').evaluateAll(nodes => nodes.filter(n => {
        const r=n.getBoundingClientRect(); return r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1;
      }).map(n=>n.textContent.trim()));
      assert.deepEqual(clipped, [], label+' clipped controls');
      assert.equal(await page.locator('[data-craft-item]:visible').count(),itemCount,label+' hides items');
      assert.equal(await page.locator('.craft-item-name:visible').count(),0,label+' grid must show icons without item names');
      assert.equal(await page.locator('.craft-pager').count(),0,label+' adds pagination');
      const grid=await page.locator('#craft-grid').evaluate(node=>{
        const r=node.getBoundingClientRect();
        return {horizontalOverflow:node.scrollWidth>node.clientWidth+1,verticalOverflow:node.scrollHeight>node.clientHeight+1,outsideViewport:r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1};
      });
      assert(!grid.horizontalOverflow,label+' grid scrolls horizontally');
      assert(!grid.outsideViewport,label+' grid exceeds screen');
      assert(!grid.verticalOverflow,label+' must show the complete catalog without vertical grid scrolling');
      const clippedLabels=await page.locator('.craft-item-name').evaluateAll(nodes=>nodes.filter(node=>{
        if(!node.getClientRects().length || getComputedStyle(node).visibility==='hidden')return false;
        const card=node.closest('.craft-item'), r=node.getBoundingClientRect(), c=card.getBoundingClientRect();
        return node.scrollWidth>node.clientWidth+1 || node.scrollHeight>node.clientHeight+1 || card.scrollWidth>card.clientWidth+1 || card.scrollHeight>card.clientHeight+1 || r.left<c.left+1 || r.right>c.right-1 || r.top<c.top+1 || r.bottom>c.bottom-1;
      }).map(node=>node.textContent.trim()));
      assert.deepEqual(clippedLabels,[],label+' item names overflow their cards');
      const badCards=await page.locator('[data-craft-item]').evaluateAll(nodes=>{
        const grid=document.getElementById('craft-grid').getBoundingClientRect();
        const items=window.YomamaCraft.state().crafting.items;
        return nodes.map(card=>{
          const r=card.getBoundingClientRect(),icon=card.querySelector('.craft-sprite'),art=icon.getBoundingClientRect(),name=card.querySelector('.craft-item-name');
          const nameVisible=!!name.getClientRects().length && getComputedStyle(name).visibility!=='hidden';
          const labelledBy=(card.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim();
          const accessible=(card.getAttribute('aria-label')||labelledBy||(nameVisible?name.textContent:'')||card.title).trim();
          const item=items.find(item=>item.id===card.dataset.craftItem);
          const boundsBad=r.left<Math.max(0,grid.left)-1 || r.right>Math.min(innerWidth,grid.right)+1 || r.top<Math.max(0,grid.top)-1 || r.bottom>Math.min(innerHeight,grid.bottom)+1;
          const artBad=art.width<=0 || art.height<=0 || getComputedStyle(icon).visibility==='hidden' || art.left<r.left-1 || art.right>r.right+1 || art.top<r.top-1 || art.bottom>r.bottom+1;
          const contentsBad=card.scrollWidth>card.clientWidth+1 || card.scrollHeight>card.clientHeight+1;
          return {id:card.dataset.craftItem,boundsBad,artBad,contentsBad,accessibleNameBad:accessible!==item.name};
        }).filter(card=>card.boundsBad||card.artBad||card.contentsBad||card.accessibleNameBad);
      });
      assert.deepEqual(badCards,[],label+' all 300 icons must fit with accessible item names');
    }
    await Promise.all([page.goto(base+'/craft.html'),buildPage.goto(base+'/buildings.html')]);
    await ready();
    const art=await checkArt();
    await buildPage.waitForFunction(()=>window.YomamaEcon && window.YomamaEcon.state());
    await buildPage.evaluate(()=>document.fonts.ready);
    if(await buildPage.locator('#econ-overnight[open]').count()) await buildPage.locator('[data-overnight-close]').click();
    const links = await page.locator('.game-nav a').evaluateAll(nodes => nodes.map(n=>new URL(n.href).pathname));
    assert.deepEqual(links, ['/buildings.html','/marketplace.html','/craft.html','/port_trading.html','/advanced-hq.html','/license.html']);
    const samples=await page.evaluate(()=>{
      const items=window.YomamaCraft.state().crafting.items;
      const lastId=document.querySelector('#craft-grid > :last-child').dataset.craftItem;
      return {firstNew:items[150],last:items.find(item=>item.id===lastId),cart:items.find(item=>item.id==='wheeled_cart')};
    });
    assert(samples.firstNew && samples.last && samples.cart,'new and existing craft examples exist');
    await openItem('fish_trap');
    await checkDialogFits('supply recipe');
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
      await checkDialogFits('after supply purchase');
    }
    assert(!await page.locator('#craft-submit').isDisabled());
    const requestCount = craftRequests.length;
    const response = page.waitForResponse(response=>new URL(response.url()).pathname==='/api/game/craft');
    await page.locator('#craft-submit').evaluate(button=>{button.click();button.click();});
    assert.equal((await response).status(),200);
    await page.waitForFunction(expected=>window.YomamaCraft.state().crafting.items.find(item=>item.id==='fish_trap').owned===expected, before+1);
    assert.equal(craftRequests.length,requestCount+1,'duplicate click makes only one request');
    assert.match(await page.locator('#craft-status').innerText(), /Crafted Woven Fish Trap/);
    await checkDialogFits('craft success');
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'craft-item-fish_trap','close returns focus to item');
    await page.reload(); await ready();
    assert.equal(await page.evaluate(()=>window.YomamaCraft.state().crafting.items.find(item=>item.id==='fish_trap').owned),before+1,'crafted item survives reload');

    const advanced=await page.evaluate(ids=>{
      const state=window.YomamaCraft.state(),crafting=state.crafting;
      const candidates=crafting.items.slice(150).flatMap(item=>item.ingredients.filter(row=>row.kind==='supply' && ids.includes(row.id) && row.missing>0 && row.canBuy).map(row=>({itemId:item.id,row})));
      const selected=candidates.find(candidate=>candidate.row.unitPrice>=100) || candidates[0];
      if(!selected)return null;
      const supplyIndex=crafting.supplies.findIndex(supply=>supply.id===selected.row.id);
      return {itemId:selected.itemId,row:selected.row,supplyIndex,beforeQuantity:crafting.supplies[supplyIndex].quantity,beforeCash:state.cash};
    },addedSupplies.map(supply=>supply.id));
    assert(advanced,'preview needs an affordable missing new component for a new craft');
    await openItem(advanced.itemId);
    await checkDialogFits('new advanced component recipe');
    const componentButton=page.locator('[data-craft-buy="'+advanced.row.id+'"]');
    const componentArt=await componentButton.evaluate(button=>{
      const icon=button.closest('tr').querySelector('.craft-supply-icon'),style=getComputedStyle(icon,'::before');
      return {image:style.backgroundImage,width:parseFloat(style.width),height:parseFloat(style.height),rendering:style.imageRendering};
    });
    assert(componentArt.image.includes(new URL(art.supplyMetadata[advanced.supplyIndex].src,page.url()).href),'new component uses its own loaded supply atlas');
    assert(componentArt.width>0 && componentArt.height>0 && componentArt.rendering==='pixelated','new component pixel art is visible');
    const advancedResponse=page.waitForResponse(response=>{
      if(new URL(response.url()).pathname!=='/api/game/craft')return false;
      const body=response.request().postDataJSON();return body.action==='buy_supply' && body.supplyId===advanced.row.id;
    });
    await componentButton.click();
    const componentResponse=await advancedResponse; assert.equal(componentResponse.status(),200);
    const purchase=await componentResponse.json();
    assert.equal(purchase.receipt.quantity,advanced.row.missing,'purchase uses the displayed missing quantity');
    assert.equal(purchase.receipt.cost,advanced.row.buyCost,'purchase uses the displayed price');
    assert.equal(purchase.cash,advanced.beforeCash-advanced.row.buyCost,'new component purchase deducts its stated cost');
    const advancedQuantity=advanced.beforeQuantity+advanced.row.missing;
    await page.waitForFunction(({id,quantity})=>window.YomamaCraft.state().crafting.supplies.find(supply=>supply.id===id).quantity===quantity,{id:advanced.row.id,quantity:advancedQuantity});
    await checkDialogFits('new component purchase confirmation');
    await page.reload(); await ready();
    assert.equal(await page.evaluate(id=>window.YomamaCraft.state().crafting.supplies.find(supply=>supply.id===id).quantity,advanced.row.id),advancedQuantity,'new component inventory survives reload');

    for (const [width,height] of [[1366,768],[1366,650],[1920,1080],[1024,768],[768,768],[390,844],[360,640],[844,390]]) {
      await Promise.all([page.setViewportSize({width,height}),buildPage.setViewportSize({width,height})]);
      await page.waitForFunction(count => [...document.querySelectorAll('.craft-item')].filter(n=>!n.hidden).length===count,itemCount);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const label=width+'x'+height; await checkViewport(label); await checkHeader(label);
      await checkItemDialog(samples.firstNew,label+' first new craft');
      await checkItemDialog(samples.last,label+' last craft');
      await checkItemDialog(samples.cart,label+' original cart');
      // Five ingredients and explicit purchase controls must all fit without scrolling.
      await openItem('smoking_cabinet');
      await checkDialogFits(label+' five-ingredient recipe');
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors,[]); assert.deepEqual(badAssets,[]);
    console.log(JSON.stringify({result:'passed',items:itemCount,uniqueSprites:itemCount,supplies:supplyCount,uniqueSupplySprites:supplyCount,viewports:8,headerMatchesBuild:true,crafted:'Woven Fish Trap',purchasedNewComponent:advanced.row.name,requests:craftRequests.length},null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
