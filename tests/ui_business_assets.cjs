/* Read-only UI checks against an isolated local preview. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:4137';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname) && new URL(base).port !== '3000');
(async () => {
 const browser = await chromium.launch({headless:true});
 try {
  const page = await browser.newPage(); const errors=[];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('https://**/*', r => r.abort());
  for (const viewport of [{width:1366,height:768},{width:390,height:844}]) {
   await page.setViewportSize(viewport);
   await page.goto(base+'/craft.html');
   await page.locator('.craft-item').first().waitFor();
   await page.getByRole('button',{name:'Business assets · 45',exact:true}).click();
   assert.equal(await page.locator('.craft-item').count(),45);
   assert.equal(await page.locator('[data-asset-type="tangible"].craft-item').count(),30);
   assert.equal(await page.locator('[data-asset-type="intangible"].craft-item').count(),15);
   await page.getByRole('button',{name:'Irrigation system',exact:true}).click();
   assert.match(await page.locator('#craft-asset-detail').innerText(),/Depreciation/);
   assert.equal(await page.locator('#craft-submit').isVisible(),false);
   await page.locator('#craft-close').click();
   await page.getByRole('button',{name:'Fixed-term satellite bandwidth rights',exact:true}).click();
   assert.match(await page.locator('#craft-asset-detail').innerText(),/Amortization/);
   assert.match(await page.locator('#craft-makes').innerText(),/Orbital Uplink/);
   await page.locator('#craft-close').click();
   await page.locator('#craft-grid').evaluate(e=>e.scrollTop=0);
   await page.screenshot({path:'.checks/business-assets-'+viewport.width+'.png'});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.getByRole('button',{name:'Craft items',exact:true}).click();
   assert.equal(await page.locator('.craft-item').count(),300);
   await page.locator('.craft-item').first().click();
   assert.equal(await page.locator('.craft-ingredients').isVisible(),true);
   assert.equal(await page.locator('#craft-submit').isVisible(),true);
  }
  assert.deepEqual(errors,[]); console.log('45 assets: desktop/mobile, both accounting types, scroll, dialog and recipe switching passed');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
