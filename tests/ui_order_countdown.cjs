/* Exercise the real order-clock functions in a browser DOM with a controlled
   clock. No server, credentials, saved town, or network mutations are involved. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>route.abort());
    await page.setContent('<main id="order-clock-fixture"></main>');
    await page.evaluate(()=>{window.fixtureNow=0;Date.now=()=>window.fixtureNow;});
    const source=fs.readFileSync(path.join(__dirname,'../econ.js'),'utf8').replace(
      '  // ------------------------------------------------------------------ boot --',
      '  window.OrderClockFixture={apply:function(s){snapshot=s;trackOrderClocks(s);},markup:orderEta,tick:syncOrderClocks};\n  // ------------------------------------------------------------------ boot --');
    await page.addScriptTag({content:source});
    const order={id:'forecast-test',committed:true,canFulfill:false,etaSeconds:90,
      etaLabel:'About 2 min',etaReason:'Approximate supply time. Existing regular buyers receive their goods first.'};
    async function apply(changes={},paused=false,asGoal=false){
      Object.assign(order,changes);
      await page.evaluate(({order,paused,asGoal})=>{
        const state={paused,contracts:{offers:asGoal?[]:[order]},goalOrder:asGoal?order:null};
        window.OrderClockFixture.apply(state);
        document.getElementById('order-clock-fixture').innerHTML=window.OrderClockFixture.markup(order);
      },{order,paused,asGoal});
    }
    async function tick(now){await page.evaluate(now=>{window.fixtureNow=now;window.OrderClockFixture.tick();},now);}
    const label=()=>page.locator('.game-order-eta > span').textContent();
    await apply();assert.equal(await label(),'About 1m 30s');
    await page.evaluate(()=>window.originalReason=document.querySelector('.game-order-eta small'));
    await tick(10000);assert.equal(await label(),'About 1m 20s');
    assert.equal(await page.locator('.game-order-eta small').textContent(),order.etaReason,'clock ticks must preserve the explanation');
    assert(await page.evaluate(()=>window.originalReason===document.querySelector('.game-order-eta small')),'clock ticks must not replace the explanation element');

    await tick(30000);await apply({etaSeconds:300});
    assert.equal(await label(),'About 5m 00s','a longer server forecast replaces the old deadline');
    await tick(31000);assert.equal(await label(),'About 4m 59s');
    await apply({etaSeconds:15});assert.equal(await label(),'About 15s','a shorter server forecast replaces the old deadline');
    await tick(50000);assert.equal(await label(),'Checking supplies…','an estimate reaching zero must not claim the order is ready');
    await apply({etaSeconds:0,canFulfill:true,etaLabel:'An older forecast'});
    assert.equal(await label(),'Ready now','server readiness overrides the old clock and label');
    await tick(51000);assert.equal(await label(),'Ready now');

    await apply({etaSeconds:null,canFulfill:false,etaLabel:'Production paused',etaReason:'The class clock is paused.'},true);
    assert.equal(await page.locator('[data-order-countdown]').count(),0,'a paused snapshot clears the active countdown');
    await tick(600000);assert.equal(await label(),'Production paused');
    await apply({etaSeconds:45,etaLabel:'About 45s',etaReason:'Approximate supply time.'});
    assert.equal(await label(),'About 45s','resume uses the current server forecast');
    await tick(601000);assert.equal(await label(),'About 44s');
    await apply({committed:false,etaSeconds:null,etaIfSavedSeconds:90,etaLabel:'If saved: about 2 min'});
    assert.equal(await page.locator('[data-order-countdown]').count(),0,'releasing an order clears its countdown');
    await tick(700000);assert.equal(await label(),'If saved: about 2 min');

    await apply({id:'goal-only',committed:true,etaSeconds:60,etaIfSavedSeconds:null,etaLabel:'About 1 min'},false,true);
    await tick(701000);assert.equal(await label(),'About 59s','dedicated goal orders receive a live clock');
    assert.deepEqual(errors,[]);
    console.log('Passed authoritative ETA changes, early readiness, elapsed estimates, pause/resume, release, goal clocks and persistent explanation text.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
