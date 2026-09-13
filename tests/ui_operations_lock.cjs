/* Operations page locked for testing: only the Focus tree opens, whatever the URL or click says.
   node tests/ui_operations_lock.cjs http://127.0.0.1:3301 [screenshot-dir] */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:3301';
const shots = process.argv[3] || '';
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    for (const [name, viewport] of [['desktop', {width: 1366, height: 768}], ['mobile', {width: 390, height: 780}]]) {
      const page = await browser.newPage({viewport}), errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/advanced-hq.html#quests');
      await page.locator('.wf-workspace').waitFor();
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => location.hash), '#focus', 'URL hash forced to the focus tree');
      assert.equal(await page.locator('#game-wf-panel').getAttribute('aria-labelledby'), 'game-wf-tab-focus', 'Focus panel is shown');
      assert.ok(await page.locator('.wf-focus').count(), 'Focus tree rendered');
      assert.equal(await page.locator('.wf-tabs [data-wf-tab]:visible').count(), 1, 'Only the Focus tab is visible');
      assert.ok(await page.locator('.ops-lock-cell:visible').count(), 'Black closed-for-testing cell is shown');
      // Hidden tabs cannot be reached by clicking through the DOM either.
      await page.evaluate(() => document.querySelector('[data-wf-tab="quests"]').click());
      await page.waitForTimeout(100);
      assert.equal(await page.locator('#game-wf-panel').getAttribute('aria-labelledby'), 'game-wf-tab-focus', 'A forced click on Quests still leaves the Focus tree open');
      // Keyboard tab cycling is off.
      await page.locator('#game-wf-tab-focus').focus();
      await page.keyboard.press('ArrowRight');
      await page.waitForTimeout(100);
      assert.equal(await page.locator('#game-wf-panel').getAttribute('aria-labelledby'), 'game-wf-tab-focus', 'Arrow keys do not leave the Focus tree');
      // A hash change from a link elsewhere lands on the focus tree too.
      await page.evaluate(() => { location.hash = '#hq'; });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => location.hash), '#focus', 'Hash change is pulled back to focus');
      assert.equal(await page.locator('#game-wf-panel').getAttribute('aria-labelledby'), 'game-wf-tab-focus', 'Panel is still the Focus tree after a hash change');
      const badge = page.locator('#game-operations-prestige');
      if (await badge.isVisible()) {
        await badge.click(); await page.waitForTimeout(100);
        assert.equal(await page.locator('#game-wf-panel').getAttribute('aria-labelledby'), 'game-wf-tab-focus', 'Prestige badge keeps the Focus tree');
      }
      // Testing rules: no Research / Know-how anywhere, workers pinned, Prestige box inside the develop container.
      assert.equal(await page.locator('#game-growth-open').count(), 0, 'Research button is gone from Operations');
      assert.equal(await page.locator('text=Know-how').count(), 0, 'No Know-how text on Operations');
      assert.equal((await page.locator('[data-worker-total]').first().textContent()).trim(), '104', 'Worker head count is pinned at 104');
      assert.equal(await page.locator('.wf-focus-detail .wf-focus-prestige').count(), 1, 'Prestige box sits inside the develop container');
      assert.equal(await page.locator('.wf-population-summary .wf-prestige').count(), 0, 'Summary strip no longer repeats Prestige on the focus tree');
      assert.deepEqual(errors, [], 'No page errors');
      if (shots) await page.screenshot({path: `${shots}/operations-lock-${name}.png`, fullPage: false});
      await page.close();
    }
    console.log('ui_operations_lock: ok');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
