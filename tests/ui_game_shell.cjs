/* Shared game-shell regression. The local preview supplies page assets and one
   representative snapshot. Every browser API request is intercepted, so this
   test cannot change the preview town or any class save.
   Run: node tests/ui_game_shell.cjs [http://127.0.0.1:3094] */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

const base=new URL(process.argv[2]||'http://127.0.0.1:3094').origin;
assert(['127.0.0.1','localhost','[::1]'].includes(new URL(base).hostname),'Use a local preview, never the live class server');

const routes=[
 {file:'buildings',title:'BUILD',current:'buildings.html'},
 {file:'marketplace',title:'MARKET',current:'marketplace.html'},
 {file:'advanced-hq',title:'OPERATIONS',current:'advanced-hq.html'},
 {file:'license',title:'LICENCE',current:'license.html'}
];
const navLabels=['Build','Market','Operations','Licence'];
const navTargets=['buildings.html','marketplace.html','advanced-hq.html','license.html'];
const metricKeys=['cash','net-worth','income','materials'];
const metricLabels=['Cash','Net worth','Income / min','Materials'];
const viewports=[
 {name:'desktop',width:1366,height:768},
 {name:'mobile',width:390,height:844},
 {name:'landscape',width:844,height:390}
];
const clone=value=>JSON.parse(JSON.stringify(value));
const near=(actual,expected,label,tolerance=1)=>assert(Math.abs(actual-expected)<=tolerance,label+': '+actual+' != '+expected);

function compareRect(actual,expected,label){
 for(const key of ['x','y','width','height'])near(actual[key],expected[key],label+' '+key);
}

(async()=>{
 const response=await fetch(base+'/api/game/econ/state');
 assert(response.ok,'Use a running signed-in local preview');
 const state=await response.json();
 assert.equal(state.modelVersion,4,'The shell check requires the production economy');
 Object.assign(state,{cash:39,netWorth:773,incomePerMinute:55,materials:0,overnightReport:null,receipt:null,classCompetition:false});

 const browser=await chromium.launch({headless:true});
 const errors=[],mutations=[],observations=[];
 try{
  const page=await browser.newPage({viewport:{width:viewports[0].width,height:viewports[0].height}});
  page.setDefaultTimeout(10000);
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==base)return route.abort();
   if(!url.pathname.startsWith('/api/'))return route.continue();
   try{
    if(url.pathname==='/api/game/econ/login')return route.fulfill({json:clone(state)});
    if(request.method()!=='GET'){
     mutations.push(request.method()+' '+url.pathname);
     return route.fulfill({status:405,json:{error:'Read-only shell check'}});
    }
    if(url.pathname==='/api/game/buildings')return route.fulfill({json:{buildings:{}}});
    if(url.pathname==='/api/game/state')return route.fulfill({json:clone(state)});
    if(url.pathname==='/api/game/econ/quiz')return route.fulfill({json:{questions:[],passMark:4}});
    if(url.pathname==='/api/game/econ/state')return route.fulfill({json:clone(state)});
    throw new Error('Unexpected API request: '+request.method()+' '+url.pathname);
   }catch(error){
    errors.push(error.stack||String(error));
    return route.fulfill({status:500,json:{error:'Shell check rejected this request'}});
   }
  });

  for(const viewport of viewports){
   await page.setViewportSize({width:viewport.width,height:viewport.height});
   let reference=null;
   for(const route of routes){
    await page.goto(base+'/'+route.file+'.html');
    await page.locator('#game-hud .game-build-metrics [data-build-metric]').first().waitFor();
    await page.waitForFunction(()=>document.querySelectorAll('#game-hud .game-build-metrics > [data-build-metric]').length===4);
    await page.evaluate(()=>window.YomamaFit&&window.YomamaFit.render());
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));

    const workspace=page.locator('.game-workspace');
    const head=workspace.locator(':scope > .game-page-head');
    const hud=workspace.locator(':scope > #game-hud');
    const heading=head.locator(':scope > h1');
    const nav=head.locator(':scope > .game-nav');
    const bar=hud.locator(':scope > .game-build-metrics');
    assert.equal(await head.count(),1,route.file+' has one direct page head');
    assert.equal(await hud.count(),1,route.file+' has one direct finance row');
    assert.equal(await heading.count(),1,route.file+' has one H1 in the page head');
    assert.equal(await nav.count(),1,route.file+' has one game navigation in the page head');
    assert.equal(await bar.count(),1,route.file+' has one finance bar in the HUD');
    assert.equal(await heading.evaluate(element=>[...element.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE).map(node=>node.textContent).join('').trim()),route.title,route.file+' H1 title');
    assert.equal(await page.locator('#game-hud').count(),1,route.file+' has exactly one HUD');
    assert(await page.evaluate(()=>{
     const head=document.querySelector('.game-workspace > .game-page-head');
     return !!head && head.nextElementSibling===document.querySelector('.game-workspace > #game-hud');
    }),route.file+' finance bar is the separate row immediately after the page head');
    assert.deepEqual(await head.evaluate(element=>[...element.children].map(child=>child.tagName)),['H1','NAV'],route.file+' page head contains only the title and navigation');

    const links=nav.locator(':scope > a');
    assert.equal(await links.count(),4,route.file+' has the four business links');
    assert.deepEqual((await links.allTextContents()).map(text=>text.trim()),navLabels,route.file+' business link labels');
    assert.deepEqual(await links.evaluateAll(elements=>elements.map(link=>new URL(link.href).pathname.split('/').pop())),navTargets,route.file+' business link destinations');
    const active=nav.locator(':scope > a[aria-current="page"]');
    assert.equal(await active.count(),1,route.file+' has exactly one active business link');
    assert.equal(await active.evaluate(link=>new URL(link.href).pathname.split('/').pop()),route.current,route.file+' marks its own link active');

    assert.equal(await bar.getAttribute('aria-label'),'Town finances');
    const metrics=bar.locator(':scope > [data-build-metric]');
    assert.equal(await metrics.count(),4,route.file+' shows exactly four town figures');
    assert.deepEqual(await metrics.evaluateAll(elements=>elements.map(element=>element.dataset.buildMetric)),metricKeys,route.file+' finance metric identities');
    assert.deepEqual((await metrics.locator(':scope > dt').allTextContents()).map(text=>text.trim()),metricLabels,route.file+' finance metric labels');
    assert.deepEqual(await metrics.evaluateAll(elements=>elements.map(element=>element.querySelector('dd').textContent.replace(/\s+/g,'').trim())),['39YM','773YM','55YM','0'],route.file+' finance values use the shared snapshot');

    const shell=await page.evaluate(()=>{
     const rect=element=>{const r=element.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
     const workspace=document.querySelector('.game-workspace');
     const head=workspace.querySelector(':scope > .game-page-head');
     const heading=head.querySelector(':scope > h1');
     const nav=head.querySelector(':scope > .game-nav');
     const hud=workspace.querySelector(':scope > #game-hud');
     const bar=hud.querySelector(':scope > .game-build-metrics');
     return {
      viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,
      workspace:rect(workspace),head:rect(head),heading:rect(heading),nav:rect(nav),hud:rect(hud),bar:rect(bar),
      links:[...nav.children].map(rect),metrics:[...bar.children].map(rect),
      navOverflow:nav.scrollWidth-nav.clientWidth,barOverflow:bar.scrollWidth-bar.clientWidth,
      clipped:[...nav.children,...bar.children].filter(element=>element.scrollWidth>element.clientWidth+1).map(element=>element.textContent.trim())
     };
    });
    assert(shell.documentWidth<=viewport.width+1,route.file+' has no horizontal page overflow at '+viewport.name);
    assert(shell.navOverflow<=1,route.file+' business navigation does not overflow at '+viewport.name);
    assert(shell.barOverflow<=1,route.file+' finance bar does not overflow at '+viewport.name);
    assert.deepEqual(shell.clipped,[],route.file+' shell text is not horizontally clipped at '+viewport.name);
    for(const [name,rect] of [['head',shell.head],['navigation',shell.nav],['HUD',shell.hud],['finance bar',shell.bar],...shell.links.map((rect,index)=>['link '+navLabels[index],rect]),...shell.metrics.map((rect,index)=>['metric '+metricKeys[index],rect])]){
     assert(rect.x>=-1,route.file+' '+name+' starts inside '+viewport.name);
     assert(rect.right<=viewport.width+1,route.file+' '+name+' ends inside '+viewport.name);
    }
    near(shell.hud.x,shell.head.x,route.file+' HUD aligns with page head left');
    near(shell.hud.right,shell.head.right,route.file+' HUD aligns with page head right');
    near(shell.bar.x,shell.hud.x,route.file+' finance bar aligns with HUD left');
    near(shell.bar.right,shell.hud.right,route.file+' finance bar aligns with HUD right');
    assert(shell.hud.y>=shell.head.bottom-1,route.file+' finance row sits below the page head');
    near(shell.metrics[0].x,shell.bar.x,route.file+' first metric starts at bar left');
    near(shell.metrics.at(-1).right,shell.bar.right,route.file+' final metric ends at bar right');
    for(const metric of shell.metrics){
     near(metric.y,shell.metrics[0].y,route.file+' metrics remain in one row at '+viewport.name);
     near(metric.height,shell.metrics[0].height,route.file+' metric heights match at '+viewport.name);
    }
    if(viewport.name==='desktop'){
     near(shell.heading.x,shell.head.x,route.file+' H1 sits at the left of the page head');
     assert(shell.nav.x>shell.heading.right,route.file+' navigation sits to the right of its H1 on desktop');
     near(shell.nav.right,shell.head.right,route.file+' navigation sits at the right edge on desktop');
    }else{
     if(shell.heading.width)near(shell.heading.x,shell.head.x,route.file+' responsive H1 starts at the left');
     near(shell.links[0].x,shell.nav.x,route.file+' first responsive link starts at navigation left');
     near(shell.links.at(-1).right,shell.nav.right,route.file+' four responsive links fill the navigation row');
    }

    const comparable={head:shell.head,heading:{x:shell.heading.x,y:shell.heading.y,height:shell.heading.height},nav:shell.nav,hud:shell.hud,bar:shell.bar,links:shell.links,metrics:shell.metrics};
    if(!reference)reference={file:route.file,geometry:comparable,values:await metrics.evaluateAll(elements=>elements.map(element=>element.textContent.replace(/\s+/g,' ').trim()))};
    else{
     for(const key of ['head','nav','hud','bar'])compareRect(comparable[key],reference.geometry[key],viewport.name+' '+route.file+' '+key+' matches '+reference.file);
     for(const key of ['x','y','height'])near(comparable.heading[key],reference.geometry.heading[key],viewport.name+' '+route.file+' heading '+key+' matches '+reference.file);
     for(const key of ['links','metrics'])for(const [index,rect] of comparable[key].entries())compareRect(rect,reference.geometry[key][index],viewport.name+' '+route.file+' '+key+' '+index+' matches '+reference.file);
     assert.deepEqual(await metrics.evaluateAll(elements=>elements.map(element=>element.textContent.replace(/\s+/g,' ').trim())),reference.values,route.file+' finance text matches '+reference.file+' at '+viewport.name);
    }
    observations.push({viewport:viewport.name,page:route.file,head:shell.head,nav:shell.nav,hud:shell.hud});
   }
  }

  assert.deepEqual(mutations,[],'The shell check must not send API writes');
  assert.deepEqual(errors,[],'Pages and intercepted requests complete without errors');
  console.log(JSON.stringify({result:'passed',pages:routes.length,viewports:viewports.length,observations},null,2));
 }finally{
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exit(1)});
