/* Run against a signed-in preview: node tests/ui_onboarding.cjs http://127.0.0.1:3099 */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');

const base = new URL(process.argv[2] || 'http://127.0.0.1:3099').origin;
const root = path.resolve(__dirname, '..');
const sample = JSON.parse(execFileSync(path.join(root, '.venv', 'bin', 'python'), ['-c', String.raw`
import json
import production_economy as E
cfg = E.load_config()
st = E.new_state(cfg, seed=41)
payload = E.payload(cfg, st, E.new_class(cfg), dict(paused=False))
payload.update(overnightReport=None, classCompetition=False, receipt=None)
print(json.dumps(payload))
`], {cwd: root, encoding: 'utf8'}));

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 900}});
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const state = JSON.parse(JSON.stringify(sample));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== base) return route.abort();
      if (url.pathname === '/api/game/buildings') return route.fulfill({json: {buildings: {}}});
      if (url.pathname === '/api/game/econ/login' || url.pathname === '/api/game/econ/state' || url.pathname === '/api/game/state') {
        return route.fulfill({json: state});
      }
      if (route.request().method() === 'POST' && url.pathname === '/api/game/econ/orders/fulfill') {
        const body = route.request().postDataJSON();
        assert.equal(body.offerIndex, 0);
        state.checklist.goodSales = 1;
        state.cash += 50;
        state.receipt = {kind: 'order', reward: 50};
        state.contracts.offers[0].id = 'after-first-delivery';
        return route.fulfill({json: state});
      }
      if (route.request().method() === 'POST' && url.pathname === '/api/game/econ/upgrade') {
        const body = route.request().postDataJSON();
        assert.equal(body.slot, 0);
        state.buildings[0].upgrades[body.kind].level++;
        state.cash -= 24;
        state.receipt = {kind: 'upgrade', upgrade: body.kind, cost: 24};
        return route.fulfill({json: state});
      }
      return route.continue();
    });

    await page.goto(base + '/buildings.html');
    if (!await page.evaluate(() => window.YOMAMA_NOTICE_BOARD_ENABLED)) {
      await page.locator('.game-layout').waitFor();
      assert.equal(await page.locator('.game-opening-guide,.game-first-shift-toggle').count(), 0);
      assert.equal(await page.locator('body.first-shift-focus').count(), 0);
      assert.notEqual(await page.locator('.game-actions').evaluate(node => getComputedStyle(node).display), 'none');
      await page.goto(base + '/marketplace.html');
      await page.locator('.game-market-orders').waitFor();
      assert.equal(await page.locator('.game-orders-notice').isVisible(), false);
      assert.equal(await page.locator('.game-first-shift-toggle').count(), 0);
      assert.equal(await page.locator('body.first-shift-focus').count(), 0);
      assert.equal(errors.length, 0, errors.join('\n'));
      console.log('Passed disabled notice board checks on Build and Market.');
      return;
    }
    await page.locator('.game-first-shift-board').waitFor();
    if (process.env.ONBOARDING_SCREENSHOTS) {
      fs.mkdirSync(path.join(root, '.checks', 'onboarding'), {recursive: true});
      await page.screenshot({path: path.join(root, '.checks', 'onboarding', 'build-desktop.png')});
    }
    assert.match(await page.locator('.game-first-shift-board').innerText(), /Your farm/);
    assert.equal(await page.locator('body.first-shift-focus').count(), 1);
    assert.equal(await page.locator('.game-actions').evaluate(node => getComputedStyle(node).display), 'none');
    await page.setViewportSize({width: 390, height: 844});
    await page.waitForFunction(() => !!document.querySelector('[role="tablist"][aria-label="Build panels"]'));
    assert.equal(await page.locator('[role="tablist"][aria-label="Build panels"] [role="tab"]').allTextContents().then(tabs => tabs.join(',')), 'Building,Stock');
    if (process.env.ONBOARDING_SCREENSHOTS) await page.screenshot({path: path.join(root, '.checks', 'onboarding', 'build-mobile-focus.png')});
    await page.setViewportSize({width: 1366, height: 900});
    await page.locator('[data-first-shift-action="stock"]').click();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 1);
    await page.locator('[data-first-shift-close]').click();
    assert.equal(await page.locator('.game-first-shift-board').isVisible(), false);
    assert.equal(await page.locator('body.first-shift-focus').count(), 0);
    assert.notEqual(await page.locator('.game-actions').evaluate(node => getComputedStyle(node).display), 'none');
    await page.locator('[data-first-shift-toggle]').click();
    assert.equal(await page.locator('.game-first-shift-board').isVisible(), true);

    await page.locator('[data-first-shift-action="order"]').click();
    await page.locator('.game-first-shift-board').waitFor();
    assert.match(page.url(), /marketplace\.html/);
    await page.locator('[data-first-shift-action="order"]').click();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 2);
    assert.match(await page.locator('.game-first-shift-board').innerText(), /Save this farm order/);
    assert.equal(await page.locator('.game-order.is-first-shift-order').count(), 1);
    assert.equal(await page.locator('.game-customer-contracts').evaluate(node => getComputedStyle(node).display), 'none');
    assert.equal(await page.locator('.game-order:not(.is-first-shift-order)').first().evaluate(node => getComputedStyle(node).opacity), '0.38');
    await page.locator('[data-first-shift-close]').click();
    assert.notEqual(await page.locator('.game-customer-contracts').evaluate(node => getComputedStyle(node).display), 'none');
    assert.equal(await page.locator('.game-order:not(.is-first-shift-order)').first().evaluate(node => getComputedStyle(node).opacity), '1');
    await page.locator('[data-first-shift-toggle]').click();
    if (process.env.ONBOARDING_SCREENSHOTS) await page.screenshot({path: path.join(root, '.checks', 'onboarding', 'market-desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.locator('[role="tablist"][aria-label="Market panels"]').count(), 0);
    if (process.env.ONBOARDING_SCREENSHOTS) await page.screenshot({path: path.join(root, '.checks', 'onboarding', 'market-mobile-focus.png')});
    await page.setViewportSize({width: 1366, height: 900});
    state.contracts.offers[0].canFulfill = true;
    state.contracts.offers[0].requirements.forEach(need => { need.owned = need.quantity; });
    await page.evaluate(() => window.YomamaEcon.refresh());
    await page.locator('[data-order-slot="0"] [data-econ-action^="fulfill:"]').click();
    await page.locator('[data-first-shift-action="celebrate"]').waitFor();
    assert.match(await page.locator('.game-first-shift-board').innerText(), /First delivery complete/);
    await page.locator('[data-first-shift-action="celebrate"]').click();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 4);

    state.cash = 100;
    state.buildings[0].upgrades.production.canBuy = true;
    state.buildings[0].upgrades.sales.canBuy = true;
    await page.evaluate(() => window.YomamaEcon.refresh());
    await page.locator('[data-first-shift-action="upgrade"]').click();
    await page.setViewportSize({width: 390, height: 844});
    await page.waitForFunction(() => Array.from(document.querySelectorAll('[role="tablist"][aria-label="Build panels"] [role="tab"]')).some(tab => tab.textContent === 'Upgrades'));
    assert.equal(await page.locator('[role="tablist"][aria-label="Build panels"] [role="tab"]').allTextContents().then(tabs => tabs.join(',')), 'Building,Stock,Upgrades');
    await page.setViewportSize({width: 1366, height: 900});
    await page.locator('.game-operations [data-econ-action^="upgrade:"]').first().click();
    await page.locator('[data-first-shift-action="quest"]').waitFor();
    await page.locator('[data-first-shift-action="quest"]').click();
    assert.equal(await page.locator('#game-quest[open]').count(), 1);
    await page.locator('#game-quest-close').click();
    await page.locator('[data-first-shift-action="expand"]').click();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 7);

    const box = await page.locator('.game-first-shift-board').boundingBox();
    assert(box && box.width > 0 && box.height > 0);
    await page.setViewportSize({width: 390, height: 844});
    const mobile = await page.locator('.game-first-shift-board').boundingBox();
    assert(mobile && mobile.x >= -1 && mobile.x + mobile.width <= 391, 'Purple board fits mobile width');
    const overflow = await page.locator('.game-first-shift-board').evaluate(node => node.scrollWidth > node.clientWidth + 1);
    assert.equal(overflow, false, 'Purple board text and controls fit mobile width');
    if (process.env.ONBOARDING_SCREENSHOTS) await page.screenshot({path: path.join(root, '.checks', 'onboarding', 'build-mobile.png')});
    await page.addInitScript(() => {
      if (sessionStorage.getItem('firstShiftFastForward') !== '1') return;
      sessionStorage.removeItem('firstShiftFastForward');
      const key = Object.keys(localStorage).find(name => name.startsWith('yomama_first_shift_v1:'));
      const saved = JSON.parse(localStorage.getItem(key));
      saved.activeMs = 25 * 60 * 1000;
      localStorage.setItem(key, JSON.stringify(saved));
    });
    await page.evaluate(() => sessionStorage.setItem('firstShiftFastForward', '1'));
    await page.reload();
    await page.locator('[data-first-shift-action="finish"]').waitFor();
    await page.locator('[data-first-shift-action="finish"]').click();
    assert.equal(await page.locator('[data-first-shift-toggle]').isVisible(), false);
    await page.goto(base + '/marketplace.html');
    await page.locator('.game-orders-notice').waitFor();
    assert.match(await page.locator('.game-orders-notice').innerText(), /Keep clicking/);
    await page.locator('.game-orders-notice .game-notice-close').click();
    assert.equal(await page.locator('.game-orders-notice').isVisible(), false);
    await page.reload();
    assert.equal(await page.locator('.game-orders-notice').isVisible(), false);

    if (await page.locator('#game-quests-dialog').count()) {
      state.quests = {enabled: true, quests: [{
        id: 'first-crop', title: 'First Crop', summary: 'Sell your first ten tomatoes.',
        teaches: 'Goods become Cash when they sell.', buildingId: 'farm',
        group: 'Opening up', chapter: 10, status: 'tracking', ready: false,
        objectives: [{label: 'Sell 10 Tomatoes', owned: 1, quantity: 10, ready: false}],
        rewardText: '40 YM', choices: []
      }], boosts: [], vouchers: [], features: [], recent: []};
      await page.addInitScript(() => {
        if (sessionStorage.getItem('firstShiftChapter') !== '1') return;
        sessionStorage.removeItem('firstShiftChapter');
        const key = Object.keys(localStorage).find(name => name.startsWith('yomama_first_shift_v1:'));
        const saved = JSON.parse(localStorage.getItem(key));
        Object.assign(saved, {stage: 5, finished: false, closed: false, viewedQuest: false, viewedExpansion: false, activeMs: 0, lastActiveAt: Date.now()});
        localStorage.setItem(key, JSON.stringify(saved));
      });
      await page.evaluate(() => sessionStorage.setItem('firstShiftChapter', '1'));
      await page.goto(base + '/buildings.html');
      await page.locator('[data-first-shift-action="quest"]').click();
      assert.equal(await page.locator('#game-quests-dialog[open]').count(), 1, 'Active chapter quest opens from the guide');
      assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 6);
    }
    state.cash = 250;
    state.checklist.goodSales = 7;
    Object.values(state.buildings[0].upgrades).forEach(upgrade => { upgrade.level = 1; });
    state.tick = 100;
    await page.addInitScript(() => {
      if (sessionStorage.getItem('firstShiftFreshAfterSales') !== '1') return;
      sessionStorage.removeItem('firstShiftFreshAfterSales');
      const key = Object.keys(localStorage).find(name => name.startsWith('yomama_first_shift_v1:'));
      localStorage.removeItem(key);
    });
    await page.evaluate(() => sessionStorage.setItem('firstShiftFreshAfterSales', '1'));
    await page.goto(base + '/buildings.html');
    await page.locator('.game-first-shift-board').waitFor();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 0, 'Passive sales do not skip the first visit');
    await page.addInitScript(() => {
      if (sessionStorage.getItem('firstShiftResetAfterFinish') !== '1') return;
      sessionStorage.removeItem('firstShiftResetAfterFinish');
      const key = Object.keys(localStorage).find(name => name.startsWith('yomama_first_shift_v1:'));
      const saved = JSON.parse(localStorage.getItem(key));
      Object.assign(saved, {stage: 8, finished: true, lastTick: 100});
      localStorage.setItem(key, JSON.stringify(saved));
    });
    await page.evaluate(() => sessionStorage.setItem('firstShiftResetAfterFinish', '1'));
    state.tick = 0;
    await page.reload();
    await page.locator('.game-first-shift-board').waitFor();
    assert.equal(await page.evaluate(() => window.YomamaOnboarding.step()), 0, 'A class reset restarts a finished guide');
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('Passed first shift flow across Build, Market, quest, and mobile.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
