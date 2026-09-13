/* Real temporary class data and browser checks. Pause/resume restores the
   original paused state; all other checks leave saved towns alone. Start with:
   python3 previews/teacher_dashboard_preview.py 3198
   node tests/ui_teacher_dashboard.cjs [http://127.0.0.1:3198]
   Screenshots remain in the gitignored .checks directory. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.argv[2] || 'http://127.0.0.1:3198';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const screenshots = path.resolve('.checks');
  fs.mkdirSync(screenshots, { recursive: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, reducedMotion: 'reduce' });
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://**/*', route => route.abort());
    let teacherReads = 0;
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/game/teacher/econ') teacherReads++;
    });

    await page.goto(base + '/teach.html?teacher=0');
    await page.locator('#teach-state').waitFor();
    assert.equal(await page.locator('#econ-teacher').count(), 0, 'removed standalone black economy panel');
    assert.equal(await page.locator('#rows [data-student]').count(), 0, 'no sample students without a teacher login');
    assert.equal(teacherReads, 0, 'no teacher endpoint request without teacher credentials');
    assert(await page.locator('#teach-pause').isDisabled(), 'pause disabled without teacher login');
    assert(await page.locator('#teach-console').isVisible(), 'class console link is accessible');
    assert.equal((await page.locator('#score-num').innerText()).trim(), '—', 'no invented licence metric');
    assert.equal((await page.locator('#work-num').innerText()).trim(), '—', 'no invented deliveries');

    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/game/teacher/econ' && response.status() === 200);
    await page.goto(base + '/teach.html');
    const data = await (await responsePromise).json();
    const students = data.students;
    assert.equal(data.label, 'TEACHER PREVIEW', 'run mutations only against the generated throwaway class');
    assert(students.length > 8, 'preview has enough actual seats to exercise pagination');
    await page.locator('#rows [data-student]').first().waitFor();
    assert.match(await page.locator('#class-label').innerText(), /TEACHER PREVIEW/);
    assert.equal(Number(await page.locator('[data-widget="licensed"] .stat-num').innerText()), students.filter(student => student.gateOpen).length, 'licensed metric comes from saved towns');
    assert.equal(Number((await page.locator('#work-num').innerText()).replace(/,/g, '')), students.reduce((total, student) => total + student.deliveriesCompleted, 0), 'delivery metric counts completed orders');
    assert.match(await page.locator('#teach-state').innerText(), data.paused ? /PAUSED/ : /LIVE/);

    const cards = page.locator('#rows [data-student]');
    const names = () => cards.locator('.memos-fighter-name').allTextContents();
    async function allNames() {
      const found = [];
      for (let guard = 0; guard < students.length + 1; guard++) {
        found.push(...(await names()).map(name => name.trim()));
        if (await page.locator('#teach-page-next').isDisabled()) return found;
        await page.locator('#teach-page-next').click();
      }
      throw new Error('Pagination did not reach its final page');
    }

    assert.deepEqual(await allNames(), students.map(student => student.name), 'rank pagination covers every real seat exactly once');
    await page.selectOption('#tb-sort', 'name');
    assert.deepEqual(await allNames(), students.map(student => student.name).sort((a, b) => a.localeCompare(b)), 'name sort covers all pages');
    await page.selectOption('#tb-sort', 'deliveries');
    assert.deepEqual(await allNames(), [...students].sort((a, b) => b.deliveriesCompleted - a.deliveriesCompleted || a.rank - b.rank).map(student => student.name), 'delivery sort uses completed order totals');
    await page.selectOption('#tb-sort', 'rank');
    const chosen = students[students.length - 1];
    await page.fill('#tb-search', chosen.name.toLowerCase());
    assert.deepEqual((await names()).map(name => name.trim()), [chosen.name], 'case-insensitive student search');
    await page.fill('#tb-search', 'NO SUCH STUDENT');
    assert.equal(await cards.count(), 0, 'unmatched search shows no stale cards');
    assert.match(await page.locator('#rows').innerText(), /match|found/i);
    await page.fill('#tb-search', '');
    await page.selectOption('#tb-band', 'licensed');
    assert.deepEqual((await allNames()).sort(), students.filter(student => student.gateOpen).map(student => student.name).sort(), 'licensed filter uses the actual licence gate');
    await page.selectOption('#tb-band', 'attention');
    assert.equal((await allNames()).length, Number(await page.locator('[data-widget="attention"] .stat-num').innerText()), 'attention filter and metric agree');
    await page.selectOption('#tb-band', 'growing');
    assert.equal((await allNames()).length, Number(await page.locator('[data-widget="growing"] .stat-num').innerText()), 'building-up filter and metric agree');
    await page.selectOption('#tb-band', 'all');

    // Profiles remain reachable and dismissible from the keyboard.
    await cards.first().focus();
    const profileStudent = (await names())[0].trim();
    await page.keyboard.press('Enter');
    await page.locator('#stu-modal').waitFor({ state: 'visible' });
    assert.match(await page.locator('#stu-modal-content').innerText(), new RegExp(profileStudent));
    const profileData = students.find(student => student.name === profileStudent);
    for (const label of [
      ...(profileData.operations && profileData.operations.enabled ? ['Operating profit / min', 'Total staff costs'] : []),
      ...(profileData.progression && profileData.progression.enabled ? ['Quests completed', 'Research completed', 'Equipment owned'] : []),
    ]) {
      const detail = page.locator('#stu-modal-content').getByText(label, { exact: true });
      await detail.scrollIntoViewIfNeeded();
      assert(await detail.isVisible(), label + ' is accessible in the live student profile');
    }
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press('Tab');
      assert(await page.evaluate(() => document.querySelector('#stu-modal').contains(document.activeElement)), 'Tab stays in student profile');
    }
    await page.keyboard.press('Escape');
    assert(await page.locator('#stu-modal').isHidden());
    assert(await cards.first().evaluate(element => element === document.activeElement), 'closing profile restores its opener');

    await page.locator('[data-widget="progress"]').focus();
    await page.keyboard.press('Space');
    await page.locator('#widget-modal').waitFor({ state: 'visible' });
    await page.keyboard.press('Escape');
    assert(await page.locator('[data-widget="progress"]').evaluate(element => element === document.activeElement), 'closing widget restores keyboard focus');

    // Exercise both server actions, returning the temporary clock to its state.
    try {
      for (const expectedPaused of [!data.paused, data.paused]) {
        const actionResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/game/teacher' && response.request().method() === 'POST');
        await page.locator('#teach-pause').click();
        const action = await actionResponse;
        assert.equal(action.status(), 200, 'teacher action accepted with the saved teacher token');
        assert.equal((await action.json()).paused, expectedPaused, 'server clock paused state changed');
        await page.waitForFunction(paused => document.querySelector('#teach-state').textContent === (paused ? 'PAUSED' : 'LIVE') && !document.querySelector('#teach-pause').disabled, expectedPaused);
      }
    } finally {
      await page.evaluate(async paused => {
        const teacher = JSON.parse(localStorage.getItem('yomama_teacher_v1'));
        const response = await fetch('/api/game/teacher', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ teacher_token: teacher.teacher_token, action: paused ? 'pause' : 'resume' }),
        });
        if (!response.ok) throw new Error('Could not restore the temporary class clock');
      }, data.paused);
    }

    async function assertScreenFit(label) {
      const result = await page.evaluate(() => {
        const selectors = '.teach-page button,.teach-page select,.teach-page input,.teach-page [data-widget],#rows .memos-fighter,.teach-footer';
        const outside = [...document.querySelectorAll(selectors)]
          .filter(element => element.getClientRects().length && !element.closest('[hidden]'))
          .map(element => ({ text: element.getAttribute('aria-label') || element.textContent.trim().slice(0, 60), rect: element.getBoundingClientRect() }))
          .filter(({ rect }) => rect.left < -1 || rect.top < -1 || rect.right > innerWidth + 1 || rect.bottom > innerHeight + 1)
          .map(({ text }) => text);
        return {
          outside,
          scroll: document.documentElement.scrollWidth > innerWidth + 1 || document.documentElement.scrollHeight > innerHeight + 1,
          rosterOverflow: document.querySelector('#rows').scrollHeight > document.querySelector('#rows').clientHeight + 1,
        };
      });
      assert.deepEqual(result.outside, [], label + ': controls and students fit the viewport');
      assert.equal(result.scroll, false, label + ': no page scrolling');
      assert.equal(result.rosterOverflow, false, label + ': pagination fits the roster without hidden rows');
    }
    for (const [width, height] of [[1366, 768], [1366, 650], [1728, 694], [1920, 1080], [1024, 768], [390, 844], [844, 390]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(150);
      await assertScreenFit(width + 'x' + height);
      await page.screenshot({ path: path.join(screenshots, 'teacher-dashboard-' + width + 'x' + height + '.png') });
      if (!await page.locator('#teach-page-next').isDisabled()) {
        await page.locator('#teach-page-next').click();
        await assertScreenFit(width + 'x' + height + ' next page');
      }
    }

    // A temporary transport failure keeps the previous roster visibly stale.
    const teacherEndpoint = '**/api/game/teacher/econ?*';
    const staleNames = await names();
    const staleMetric = await page.locator('#work-num').innerText();
    await page.route(teacherEndpoint, route => route.fulfill({ status: 503, json: { error: 'Temporary preview interruption' } }));
    await page.locator('#teach-refresh').click();
    await page.waitForFunction(() => document.querySelector('#teach-state').textContent === 'UPDATE FAILED');
    assert.deepEqual(await names(), staleNames, 'temporary refresh failure preserves the last roster');
    assert.equal(await page.locator('#work-num').innerText(), staleMetric, 'temporary refresh failure preserves the last metric');
    assert.match(await page.locator('#teach-message').innerText(), /last update.*retry/i, 'stale state has a visible retry explanation');
    await page.unroute(teacherEndpoint);
    await page.locator('#teach-refresh').click();
    await page.waitForFunction(paused => document.querySelector('#teach-state').textContent === (paused ? 'PAUSED' : 'LIVE'), data.paused);
    assert.match(await page.locator('#teach-message').innerText(), /Updated/, 'retry restores fresh-data feedback');

    // The periodic refresh uses the same handler; invoke it during an open
    // profile to verify expired access immediately closes private details.
    await cards.first().click();
    await page.locator('#stu-modal').waitFor({ state: 'visible' });
    await page.route(teacherEndpoint, route => route.fulfill({ status: 403, json: { error: 'Teacher access expired' } }));
    await page.evaluate(() => document.querySelector('#teach-refresh').click());
    await page.waitForFunction(() => document.querySelector('#teach-message').textContent.includes('expired'));
    assert(await page.locator('#stu-modal').isHidden(), 'expired access closes the profile');
    assert(await page.locator('#widget-modal').isHidden(), 'expired access closes widget details');
    assert.equal(await page.locator('#stu-modal-content').textContent(), '', 'expired access clears hidden student details');
    assert.equal(await page.locator('#widget-modal-content').textContent(), '', 'expired access clears hidden widget details');
    assert.equal(await cards.count(), 0, 'expired access clears the visible roster');
    assert.equal((await page.locator('#score-num').innerText()).trim(), '—', 'expired access clears class metrics');
    assert.equal(await page.locator('#class-avatars .teach-ava').count(), 0, 'expired access clears class avatars');
    assert(await page.locator('#teach-pause').isDisabled(), 'expired access disables clock actions');
    assert(await page.locator('[data-widget="progress"]').isDisabled(), 'expired widget data cannot be reopened');
    assert.deepEqual(errors, [], 'no browser script errors');
    console.log(JSON.stringify({ result: 'passed', students: students.length, viewports: 7, screenshots }, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
