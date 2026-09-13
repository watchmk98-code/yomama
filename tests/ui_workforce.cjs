/* Operations interactions and fit, with every mutation intercepted in-browser.
   node tests/ui_workforce.cjs http://127.0.0.1:3097 */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:3097';
(async () => {
  const response = await fetch(base + '/api/game/econ/state');
  assert(response.ok, 'Use a signed-in isolated preview.');
  const state = await response.json();
  // Exercise the retained crew UI used by class snapshots predating population.
  state.workforce.population = {enabled: false};
  state.workforce.teams.forEach(team => { team.populationEnabled = false; });
  assert(state.workforce && state.workforce.enabled, 'Preview must enable permanent workforce.');
  state.overnightReport = null;
  state.paused = false;
  const team = state.workforce.teams[0], building = state.buildings.find(b => b.buildingId === team.buildingId);
  Object.assign(team, {hires: 1, trainers: 1, trainerCap: 3, workers: 3, workerCap: 10, paused: false, trainingBranch: 'production', allocation: {production: 3, sales: 0, efficiency: 0}, workerProgress: .4, nextWorkerSeconds: 180});
  Object.assign(team.hire, {canHire: true, why: '', remainingSeconds: 0});
  team.nodes.forEach(node => {
    node.owned = ['orientation', 'sales'].includes(node.id);
    node.unlocked = node.owned || ['production', 'efficiency'].includes(node.id);
    node.canBuy = node.unlocked && !node.owned;
    node.why = node.canBuy || node.owned ? '' : 'Complete the preceding focus first';
  });
  Object.assign(state.workforce.hq, {level: 1, programSlots: 1, targets: []});
  Object.assign(state.workforce.hq.upgrade, {canBuy: true, why: '', cost: 900});
  building.paused = false;
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 768}}), errors = [], calls = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== base) return route.abort();
      if (url.pathname === '/api/game/workforce') {
        const body = request.postDataJSON(); calls.push(body);
        if (body.action === 'allocate') { team.allocation = body.allocation; team.trainingBranch = body.trainingBranch; team.effects = {production: body.allocation.production * 2.5, customer: body.allocation.sales * 2.5, efficiency: body.allocation.efficiency}; }
        if (body.action === 'focus') team.nodes.find(n => n.id === body.nodeId).owned = true;
        if (body.action === 'hire') { team.hires++; team.trainers++; team.hire.canHire = false; team.hire.remainingSeconds = 1800; team.hire.why = 'Recruitment cooling down'; }
        if (body.action === 'hq_assign') { state.workforce.hq.targets = body.enabled ? [team.typeId] : []; team.hqSupported = body.enabled; }
        state.receipt = {kind: 'workforce', message: 'Team updated'};
        return route.fulfill({json: state});
      }
      if (url.pathname === '/api/game/state' || url.pathname.startsWith('/api/game/econ/')) return route.fulfill({json: state});
      if (url.pathname === '/api/game/buildings') return route.fulfill({json: {buildings: {}}});
      return route.continue();
    });
    await page.goto(base + '/advanced-hq.html');
    await page.locator('.wf-workspace').waitFor();
    await page.selectOption('#game-business-choice', String(building.slot));
    const refresh = async () => {
      const reply = page.waitForResponse(r => r.url().includes('/api/game/econ/state'));
      await page.evaluate(() => window.YomamaEcon.refresh()); await reply;
      await page.waitForTimeout(70);
    };
    const clickAction = async selector => {
      const reply = page.waitForResponse(r => r.url().endsWith('/api/game/workforce'));
      await page.locator(selector).click(); assert((await reply).ok()); await page.waitForTimeout(70);
    };
    assert.equal(await page.locator('.wf-map-node').count(), 7, 'Root plus three two-node focus branches.');
    assert.equal(await page.getByText('Temporary staff', {exact: true}).count(), 0);
    await page.locator('#game-wf-map-production').click();
    await clickAction('#game-wf-node-production');
    assert.equal(calls.at(-1).nodeId, 'production');
    assert.equal(calls.at(-1).buildingId, team.buildingId);
    await page.locator('#game-wf-tab-team').click();
    await page.locator('#game-wf-team-assignments').click();
    await page.locator('#game-wf-minus-production').click();
    await page.locator('#game-wf-plus-sales').click();
    await page.selectOption('#game-wf-training-branch', 'sales');
    const beforeSave = calls.length;
    await refresh();
    assert.equal(calls.length, beforeSave, 'Editing assignments has no background spending or mutation.');
    assert.equal(await page.locator('[aria-label="Production workers"]').textContent(), '2');
    assert.equal(await page.locator('[aria-label="Customers workers"]').textContent(), '1');
    assert.equal(await page.inputValue('#game-wf-training-branch'), 'sales');
    assert.equal(await page.locator('#game-wf-team-assignments').getAttribute('aria-pressed'), 'true');
    await clickAction('#game-wf-save-allocation');
    assert.deepEqual(calls.at(-1).allocation, {production: 2, sales: 1, efficiency: 0});
    assert.equal(calls.at(-1).trainingBranch, 'sales');
    assert.match(await page.locator('[data-wf-job="production"]').textContent(), /\+5% base speed/);
    assert.match(await page.locator('[data-wf-job="sales"]').textContent(), /\+2.5% walk-in demand/);
    assert(await page.locator('#game-wf-save-allocation').isDisabled());
    await page.locator('#game-wf-team-recruitment').click();
    await clickAction('#game-wf-hire');
    assert(await page.locator('#game-wf-hire').isDisabled());
    assert.equal(await page.locator('.wf-team-training [data-econ-countdown]:visible').getAttribute('data-countdown-paused'), 'false');
    team.paused = building.paused = true;
    await refresh();
    assert.equal(await page.locator('.wf-team-training [data-econ-countdown]:visible').getAttribute('data-countdown-paused'), 'false', 'Recruitment follows class time even when business training pauses.');
    await page.locator('#game-wf-team-assignments').click();
    assert(await page.locator('#game-wf-minus-production').isEnabled(), 'A paused business can reorganize its workers.');
    state.paused = true; await refresh();
    assert(await page.locator('#game-wf-minus-production').isDisabled(), 'Teacher class pause freezes management actions.');
    state.paused = false; team.paused = building.paused = false; await refresh();
    await page.locator('#game-wf-tab-hq').click();
    await page.locator('#game-wf-hq-programs').click();
    await clickAction('#game-wf-hq-program-' + team.buildingId);
    assert.equal(calls.at(-1).enabled, true);
    assert(state.workforce.hq.targets.includes(team.typeId));
    const tabs = ['focus', 'team', 'recipes', 'quests', 'hq'];
    let views = 0;
    async function bounds(label) {
      await page.waitForTimeout(40);
      const bad = await page.evaluate(() => [...document.querySelectorAll('.wf-workspace button,.wf-workspace select')].filter(e => e.getClientRects().length && !e.closest('[hidden]')).filter(e => {const r = e.getBoundingClientRect(); return r.left < 0 || r.right > innerWidth + 1 || r.top < 0 || r.bottom > innerHeight + 1;}).map(e => e.textContent.trim().slice(0,50)));
      assert.deepEqual(bad, [], label + ' clipped controls');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1 && document.documentElement.scrollHeight <= innerHeight + 1), label + ' page overflow');
      views++;
    }
    for (const [width, height] of [[1366,768], [1728,694], [1920,1080], [768,768], [390,844], [360,740], [844,390]]) {
      await page.setViewportSize({width, height});
      for (const name of tabs) {
        await page.locator('#game-wf-tab-' + name).click();
        const subviews = name === 'team' ? ['recruitment','training','assignments','business'] : name === 'hq' ? ['academy','programs'] : [null];
        for (const subview of subviews) {
          if (subview) await page.locator('#game-wf-' + name + '-' + subview).click();
          await bounds(width + 'x' + height + ' ' + name + '/' + subview);
          for (let guard = 0; guard < 20; guard++) {
            const next = page.locator('.wf-pager button[data-wf-direction="1"]:visible:not(:disabled)');
            if (!await next.count()) break;
            await next.click(); await bounds(name + ' page ' + guard);
          }
        }
      }
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({result: 'passed', mutations: calls.map(c => c.action), views}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
