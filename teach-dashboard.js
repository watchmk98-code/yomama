/* Live teacher dashboard. The teacher console owns sign-in and credentials. */
(function () {
  'use strict';

  var teacherKey = 'yomama_teacher_v1';
  var rows = document.getElementById('rows');
  if (!rows) return;
  var portraits = ['buffett', 'can', 'dennis', 'derdo', 'hara', 'hussein', 'irene', 'marks', 'ozan', 'peaker', 'pelli'];
  var labels = { licensed: 'Licensed', growing: 'Building up', attention: 'Needs attention' };
  var colors = { licensed: 'var(--green)', growing: 'var(--amber)', attention: 'var(--red)' };
  var snapshot = null, students = [], page = 0, loading = false, acting = false;
  var currentToken = '', blockedToken = '', generation = 0;
  var returnFocus = null, returnStudentName = null, activeStudent = null, activeWidget = null;
  var modal = document.getElementById('stu-modal');
  var widgetModal = document.getElementById('widget-modal');

  function el(id) { return document.getElementById(id); }
  function text(id, value) { var node = el(id); if (node) node.textContent = value; }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(value) { var n = Number(value); return Number.isFinite(n) ? n : 0; }
  function count(value) { return Math.round(num(value)).toLocaleString('en-US'); }
  function money(value) { return count(value) + ' YM'; }
  function preciseMoney(value) { return num(value).toLocaleString('en-US', { maximumFractionDigits: 2 }) + ' YM'; }
  function compactMoney(value) {
    var n = num(value);
    return (Math.abs(n) >= 1000000 ? (n / 1000000).toFixed(1) + 'M' : Math.abs(n) >= 10000 ? (n / 1000).toFixed(1) + 'K' : count(n)) + ' YM';
  }
  function teacher() {
    try {
      var stored = JSON.parse(localStorage.getItem(teacherKey) || 'null');
      return stored && typeof stored.teacher_token === 'string' && stored.teacher_token ? stored : null;
    } catch (_) { return null; }
  }
  function portrait(name) {
    var key = (snapshot ? snapshot.code : '') + ':' + name, hash = 2166136261;
    for (var i = 0; i < key.length; i++) hash = Math.imul(hash ^ key.charCodeAt(i), 16777619);
    return './assets/hero-select/player-' + portraits[(hash >>> 0) % portraits.length] + '.png';
  }
  function initials(name) { return String(name).trim().split(/\s+/).map(function (s) { return s.charAt(0); }).slice(0, 2).join(''); }
  function productionModel() { return !snapshot || num(snapshot.modelVersion) === 4; }
  function requirements(student) {
    var c = student.checklist || {}, r = snapshot.licenceRequirements || {};
    var sales = num(student.deliveriesCompleted == null ? c.goodSales : student.deliveriesCompleted);
    var deliveryTarget = num(r.deliveries == null ? snapshot.goodSalesNeeded : r.deliveries);
    var units = num(student.customerUnitsSold), unitTarget = num(r.customerUnits || student.customerUnitsNeeded || 100);
    var businessTarget = num(r.buildings || snapshot.gateTier || 3);
    var productionLevel = num(r.productionLevel || (productionModel() ? 3 : 25));
    var experience = sales >= deliveryTarget || (productionModel() && units >= unitTarget);
    return [
      { label: 'Production level ' + productionLevel, done: !!c.lv25, detail: c.lv25 ? 'Milestone reached' : 'Upgrade a business to level ' + productionLevel },
      { label: productionModel() ? 'Customer upgrade' : 'Automation upgrade', done: !!c.auto, detail: c.auto ? 'Milestone reached' : productionModel() ? 'Upgrade customers to level ' + num(r.customerLevel || 2) : 'Unlock automation' },
      { label: productionModel() ? 'Delivery or customer experience' : 'Qualifying sales', done: experience,
        detail: count(sales) + '/' + count(deliveryTarget) + (productionModel() ? ' deliveries or ' + count(units) + '/' + count(unitTarget) + ' customer units sold' : ' qualifying sales') },
      { label: 'Quiz passed', done: !!c.quiz, detail: c.quiz ? 'Passed' : 'Complete the licence quiz' },
      { label: count(businessTarget) + ' businesses', done: student.buildings.length >= businessTarget,
        detail: student.buildings.length + '/' + count(businessTarget) + ' businesses open' }
    ];
  }
  function blockers(student) {
    var reasons = [];
    student.buildings.forEach(function (building) {
      if (building.reserve || building.processing === false || /^(Business paused|Processing paused|Saving goods)$/.test(building.status || '')) return;
      var full = building.status === 'Storage full' || (!building.status && !building.reserve && building.processing !== false && (building.goods || []).some(function (good) {
        return num(good.capacity) > 0 && num(good.quantity) >= num(good.capacity);
      }));
      if (full) reasons.push(building.name + ': storage full');
      if (building.status === 'More customers needed') reasons.push(building.name + ': more customers needed');
      if (/^Waiting for /.test(building.status || '') || building.status === 'Need cash for production') reasons.push(building.name + ': ' + building.status);
    });
    if (student.customerContracts && num(student.customerContracts.waiting) > 0) reasons.push(count(student.customerContracts.waiting) + ' regular customer contracts waiting for supplies');
    if (!student.checklist.quiz && student.requirements.every(function (r, i) { return i === 3 || r.done; })) reasons.push('Ready for the licence quiz');
    return reasons;
  }
  function prepare(raw, index) {
    var student = Object.assign({}, raw);
    student.index = index;
    student.name = String(raw.name || 'Unnamed seat');
    student.buildings = Array.isArray(raw.buildings) ? raw.buildings : [];
    student.checklist = raw.checklist || {};
    student.deliveries = num(raw.deliveriesCompleted == null ? student.checklist.goodSales : raw.deliveriesCompleted);
    student.requirements = requirements(student);
    student.complete = student.requirements.filter(function (r) { return r.done; }).length;
    student.reasons = blockers(student);
    student.band = student.gateOpen ? 'licensed' : student.reasons.length ? 'attention' : 'growing';
    return student;
  }
  function sum(key) { return students.reduce(function (total, s) { return total + num(s[key]); }, 0); }
  function setControls() {
    var available = !!snapshot && !!currentToken;
    el('teach-pause').disabled = !available || loading || acting;
    el('teach-refresh').disabled = !currentToken || currentToken === blockedToken || loading || acting;
    el('teach-pause').textContent = snapshot && snapshot.paused ? 'RESUME CLASS' : 'PAUSE CLASS';
    el('teach-pause').setAttribute('aria-label', snapshot && snapshot.paused ? 'Resume this class' : 'Pause this class');
    document.querySelectorAll('.widgets [data-widget]').forEach(function (card) {
      card.setAttribute('aria-disabled', available ? 'false' : 'true');
      card.tabIndex = available ? 0 : -1;
    });
  }
  function renderStats() {
    var available = !!snapshot, total = students.length;
    var completed = sum('complete'), possible = total * 5;
    var percent = possible ? Math.round(completed / possible * 100) : 0;
    text('score-num', available ? percent + '%' : '—');
    text('score-foot', available ? count(completed) + ' / ' + count(possible) + ' milestones reached' : 'Connect your class');
    el('score-ring').style.strokeDashoffset = (2 * Math.PI * 33 * (1 - percent / 100)).toFixed(1);
    var ready = sum('readyDeliveries'), offers = sum('deliverySlots');
    var readyPercent = offers ? Math.min(100, ready / offers * 100) : 0;
    text('work-num', available ? count(sum('deliveries')) : '—');
    text('work-foot', available ? productionModel() ? count(ready) + ' ready now · ' + count(offers) + ' offers' : 'Qualifying sales across the class' : 'Completed across the class');
    document.querySelector('[data-widget="deliveries"] .lbl').textContent = productionModel() ? 'Deliveries' : 'Qualifying sales';
    el('tb-sort').querySelector('[value="deliveries"]').textContent = productionModel() ? 'Sort: Deliveries' : 'Sort: Sales';
    el('work-done-arc').setAttribute('stroke-dasharray', readyPercent + ' ' + (100 - readyPercent));
    el('work-open-arc').setAttribute('stroke-dasharray', offers ? (100 - readyPercent) + ' ' + readyPercent : '0 100');
    el('work-open-arc').setAttribute('stroke-dashoffset', -readyPercent);
    Object.keys(labels).forEach(function (band) {
      var card = document.querySelector('[data-widget="' + band + '"]');
      var group = students.filter(function (s) { return s.band === band; });
      card.querySelector('.stat-num').textContent = available ? count(group.length) : '—';
      card.querySelector('.stat-sub').textContent = available ? (total ? Math.round(group.length / total * 100) : 0) + '% of class' : labels[band];
      var mini = card.querySelector('.mini');
      if (mini) mini.innerHTML = group.slice(0, 2).map(function (s) { return '<span class="teach-ava" title="' + esc(s.name) + '">' + esc(initials(s.name)) + '</span>'; }).join('');
    });
    var attention = students.filter(function (s) { return s.band === 'attention'; }).length;
    text('teach-attention-count', available ? count(attention) : '—');
    el('class-avatars').innerHTML = students.slice(0, 3).map(function (s) {
      return '<span class="teach-ava" title="' + esc(s.name) + '">' + esc(initials(s.name)) + '</span>';
    }).join('') + (total > 3 ? '<span class="teach-ava">+' + count(total - 3) + '</span>' : '');
    text('class-label', available ? (snapshot.label || 'CLASS') : 'NO CLASS CONNECTED');
    text('teach-state', available ? (snapshot.paused ? 'PAUSED' : 'LIVE') : 'TEACHER SIGN-IN');
    el('teach-state').classList.toggle('paused', available && !!snapshot.paused);
    text('teach-day', available ? 'DAY ' + (Math.floor(num(snapshot.day)) + 1) : 'DAY —');
    setControls();
  }
  function filteredStudents() {
    var query = el('tb-search').value.trim().toLocaleLowerCase();
    var band = el('tb-band').value, sort = el('tb-sort').value;
    return students.filter(function (s) { return (!query || s.name.toLocaleLowerCase().indexOf(query) >= 0) && (band === 'all' || band === s.band); })
      .sort(function (a, b) {
        if (sort === 'name') return a.name.localeCompare(b.name);
        if (sort === 'deliveries') return b.deliveries - a.deliveries || num(a.rank) - num(b.rank);
        return num(a.rank) - num(b.rank);
      });
  }
  function pageCapacity() {
    var css = getComputedStyle(rows);
    var height = rows.clientHeight - (parseFloat(css.paddingTop) || 0) - (parseFloat(css.paddingBottom) || 0);
    var gap = parseFloat(css.rowGap) || 0;
    var rowHeight = parseFloat(css.getPropertyValue('--teach-row-height')) || 64;
    return Math.max(1, Math.floor((height + gap) / (rowHeight + gap)));
  }
  function rowSubtitle(s) {
    var detail = s.reasons[0] || (s.nextStep && s.nextStep.title) || s.nextGoal || (s.buildings.length + ' businesses');
    return labels[s.band] + ' · ' + detail;
  }
  function renderRoster() {
    var view = filteredStudents(), size = pageCapacity(), pages = Math.max(1, Math.ceil(view.length / size));
    page = Math.max(0, Math.min(page, pages - 1));
    var start = page * size, visible = view.slice(start, start + size);
    text('tb-count', snapshot ? view.length + ' / ' + students.length + ' students' : '');
    text('teach-page-info', view.length ? (start + 1) + '–' + (start + visible.length) + ' of ' + view.length : '0 students');
    el('teach-page-prev').disabled = page === 0;
    el('teach-page-next').disabled = page >= pages - 1;
    rows.style.setProperty('--teach-page-rows', size);
    if (!visible.length) {
      rows.innerHTML = '<div class="teach-empty">' + (snapshot ? (students.length ? 'No students match these filters.' : 'No students have joined this class yet.') : 'Open the teacher console to connect your class.') + '</div>';
      return;
    }
    var focused = rows.contains(document.activeElement) ? document.activeElement.getAttribute('data-name') : null;
    rows.innerHTML = visible.map(function (s) {
      return '<article class="memos-fighter" data-student="' + s.index + '" data-name="' + esc(s.name) + '" role="button" tabindex="0" aria-label="' + esc('Open ' + s.name + ', rank ' + s.rank + ', ' + labels[s.band] + ', ' + s.complete + ' of 5 licence milestones') + '">'
        + '<span class="memos-fighter-bg" aria-hidden="true"></span>'
        + '<span class="memos-rank">#' + count(s.rank) + '</span>'
        + '<span class="memos-fighter-portrait-shell"><img class="memos-fighter-portrait" src="' + portrait(s.name) + '" alt="" loading="lazy" decoding="async"></span>'
        + '<span class="memos-fighter-body"><span class="memos-fighter-name">' + esc(s.name) + '</span>'
        + '<span class="memos-fighter-style" title="' + esc(rowSubtitle(s)) + '">' + esc(rowSubtitle(s)) + '</span></span>'
        + '<span class="memos-fighter-points teach-points"><span class="teach-score-main" title="Net worth: ' + esc(money(s.netWorth)) + '">' + compactMoney(s.netWorth) + '</span>'
        + '<span class="teach-score-strands"><b style="color:' + colors[s.band] + '">LICENCE ' + s.complete + '/5</b><span>' + count(s.deliveries) + (productionModel() ? ' DELIVERIES' : ' SALES') + '</span></span></span></article>';
    }).join('');
    if (focused !== null) {
      var replacement = Array.prototype.find.call(rows.querySelectorAll('[data-name]'), function (node) { return node.getAttribute('data-name') === focused; });
      if (replacement) replacement.focus({ preventScroll: true });
    }
  }
  function kv(label, value) { return '<div class="cell"><div class="k">' + esc(label) + '</div><div class="v">' + esc(value) + '</div></div>'; }
  function section(title, content) { return '<div><div class="teach-sec-title">' + esc(title) + '</div>' + content + '</div>'; }
  function studentContent(s) {
    var contracts = s.customerContracts;
    var profile = '<div><div class="teach-bio-name" id="stu-modal-name">' + esc(s.name) + '</div><div class="teach-bio-sub">'
      + esc((snapshot.label || 'Class') + ' · Rank #' + s.rank + ' · ' + labels[s.band]) + '</div></div>';
    profile += section('Town overview', '<div class="teach-kv">' + kv('Net worth', money(s.netWorth))
      + kv('Cash', s.cash == null ? '—' : money(s.cash)) + kv('Businesses', s.buildings.length)
      + kv('Stock', s.warehouseStored == null ? '—' : count(s.warehouseStored) + ' / ' + count(s.warehouseCap)) + '</div>');
    if (s.operations && s.operations.enabled) {
      var operations = s.operations;
      profile += section('Business finances', '<div class="teach-kv">'
        + kv('Operating profit / min', preciseMoney(operations.profitPerMinute))
        + kv('Operating expenses / min', preciseMoney(operations.operatingCostPerMinute))
        + kv('Total operating costs', money(operations.totalOperatingCosts))
        + kv('Total staff costs', money(operations.totalStaffCosts))
        + '</div><div class="teach-bio-sub">Recorded activity · ' + count(operations.observedSeconds) + ' seconds observed.</div>');
    }
    if (s.progression && s.progression.enabled) {
      var progression = s.progression;
      profile += section('Quests & research', '<div class="teach-kv">'
        + kv('Quests completed', count(progression.questsCompleted))
        + kv('Quests ready', count(progression.questsReady))
        + kv('Research completed', count(progression.researchCompleted))
        + kv('Equipment owned', count(progression.equipmentOwned))
        + kv('Know-how', count(progression.knowHow)) + kv('Prestige', count(progression.prestige)) + '</div>');
    }
    profile += section('Licence · ' + s.complete + '/5 milestones', '<div class="teach-checklist">' + s.requirements.map(function (r) {
      return '<div class="teach-check"><span style="color:' + (r.done ? 'var(--green)' : 'var(--muted)') + '">' + (r.done ? '✓ ' : '□ ') + esc(r.label) + '</span><span class="teach-bio-sub">' + esc(r.detail) + '</span></div>';
    }).join('') + '</div>');
    profile += section(productionModel() ? 'Deliveries & customers' : 'Market experience', '<div class="teach-kv">' + kv(productionModel() ? 'Completed deliveries' : 'Qualifying sales', count(s.deliveries))
      + kv('Ready offers', s.readyDeliveries == null ? '—' : count(s.readyDeliveries) + ' / ' + count(s.deliverySlots))
      + kv('Customer units sold', s.customerUnitsSold == null ? '—' : count(s.customerUnitsSold))
      + kv('Regular contracts', contracts ? count(contracts.active) + ' / ' + count(contracts.slots) + ' signed' : '—')
      + (contracts ? kv('Supplying / waiting / paused', count(contracts.supplying) + ' / ' + count(contracts.waiting) + ' / ' + count(contracts.paused)) + kv('Regular deliveries', count(contracts.deliveries)) : '') + '</div>');
    if (s.townProjects) profile += section('Town projects', '<div class="teach-bio-sub">' + esc(count(s.townProjects.completed) + ' completed' + (s.townProjects.title ? ' · ' + s.townProjects.title : '')) + '</div>');
    if (s.breakfastEvent) {
      var workshop = s.breakfastEvent;
      var workshopStatus = workshop.locked ? 'Locked' : workshop.status === 'done' ? 'Completed' : workshop.status === 'playing' ? 'In progress · Stage ' + (num(workshop.stage) + 1) : 'Available';
      profile += section('Breakfast workshop', '<div class="teach-bio-sub">' + esc(workshopStatus) + '</div>');
    }
    profile += section('Businesses & stock', s.buildings.map(function (b) {
      return '<div class="teach-building"><div class="teach-building-head">' + esc(b.name) + ' · LV ' + count(b.lv) + '</div><div class="teach-building-meta">'
        + esc((b.status || 'Open') + ' · Customers LV ' + num(b.auto) + ' · Stock ' + count(b.stored) + '/' + count(b.capacity)) + '</div>'
        + '<div class="teach-bio-sub">' + (b.goods || []).map(function (g) { return esc(g.name) + ' ' + count(g.quantity) + '/' + count(g.capacity); }).join(' · ') + '</div>'
        + (b.profitPerMinute == null ? '' : '<div class="teach-bio-sub">Operating profit ' + preciseMoney(b.profitPerMinute) + '/min · Expenses ' + preciseMoney(b.operatingCostPerMinute) + '/min</div>')
        + (b.staff ? '<div class="teach-bio-sub">Staff: ' + esc(b.staff.name) + ' · ' + count(Math.ceil(num(b.staff.remainingSeconds) / 60)) + ' min left</div>' : '') + '</div>';
    }).join(''));
    if (s.reasons.length) profile += section('Needs attention', '<div class="teach-bio-sub">' + s.reasons.map(esc).join('<br>') + '</div>');
    if (s.nextStep) profile += section('Next step', '<div>' + esc(s.nextStep.title) + '</div><div class="teach-bio-sub">' + esc(s.nextStep.detail) + '</div>');
    else if (s.nextGoal) profile += section('Next step', '<div>' + esc(s.nextGoal) + '</div>');
    if (s.build) profile += section('Construction', '<div>' + esc(s.build.name) + ' · ' + count(Math.ceil(num(s.build.remainingSec) / 60)) + ' min remaining</div>');
    return profile;
  }
  function showDialog(target) {
    if (modal.hidden && widgetModal.hidden) {
      returnFocus = document.activeElement;
      returnStudentName = returnFocus && returnFocus.getAttribute('data-name');
    }
    modal.hidden = target !== modal;
    widgetModal.hidden = target !== widgetModal;
    target.hidden = false;
    target.querySelector('button').focus({ preventScroll: true });
  }
  function closeDialogs() {
    modal.hidden = true; widgetModal.hidden = true;
    activeStudent = null; activeWidget = null;
    if (returnStudentName) {
      returnFocus = Array.prototype.find.call(rows.querySelectorAll('[data-name]'), function (node) { return node.getAttribute('data-name') === returnStudentName; });
    }
    if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
    else if (snapshot) el('tb-search').focus({ preventScroll: true });
    returnFocus = null; returnStudentName = null;
  }
  function openStudent(index) {
    var s = students[index];
    if (!snapshot || !s) return;
    activeStudent = s.name; activeWidget = null;
    el('stu-modal-portrait').src = portrait(s.name);
    el('stu-modal-portrait').alt = s.name + ' portrait';
    el('stu-modal-content').innerHTML = studentContent(s);
    showDialog(modal);
  }
  function miniList(list, deliveryMode) {
    if (!list.length) return '<div class="teach-empty">No students in this group.</div>';
    return '<div class="teach-mini">' + list.map(function (s) {
      return '<div class="row" role="button" tabindex="0" data-student="' + s.index + '" aria-label="' + esc('Open ' + s.name + ' profile') + '">'
        + '<span class="pic"><img src="' + portrait(s.name) + '" alt="" loading="lazy"></span><span class="nm">' + esc(s.name)
        + '<span class="rk"> #' + count(s.rank) + '</span></span><span class="sc" style="color:' + colors[s.band] + '">'
        + (deliveryMode ? count(s.deliveries) + (productionModel() ? ' deliveries' : ' sales') : s.complete + '/5') + '</span></div>';
    }).join('') + '</div>';
  }
  function widgetContent(kind) {
    if (kind === 'progress') {
      return section('Five licence milestones', '<p>' + (productionModel() ? 'Each student completes production and customer upgrades, delivery or customer experience, the quiz, and the required businesses.' : 'Each student completes production and automation upgrades, qualifying sales, the quiz, and the required businesses.') + '</p>')
        + section('Milestones by student', miniList(students, false));
    }
    if (kind === 'deliveries') {
      if (!productionModel()) return section('Qualifying sales', miniList(students.slice().sort(function (a, b) { return b.deliveries - a.deliveries; }), true));
      return '<div class="teach-kv">' + kv('Completed deliveries', count(sum('deliveries'))) + kv('Offers ready now', count(sum('readyDeliveries')))
        + kv('Regular contract deliveries', count(students.reduce(function (total, s) { return total + num((s.customerContracts || {}).deliveries); }, 0)))
        + kv('Customer units sold', count(sum('customerUnitsSold'))) + '</div>'
        + '<p>Completed deliveries count finished orders. The ring shows ready offers as a share of current offers. Regular customer deliveries are listed separately.</p>'
        + miniList(students.slice().sort(function (a, b) { return b.deliveries - a.deliveries; }), true);
    }
    var explanations = { licensed: 'The licence gate is open for these students.', growing: 'These students are working towards their licence, with no current production or customer blocker detected.', attention: 'These students have a production or customer blocker, a regular contract waiting for supplies, or are ready to take the licence quiz. Open a profile for the specific reason.' };
    return '<p>' + esc(explanations[kind] || '') + '</p>' + miniList(students.filter(function (s) { return s.band === kind; }), false);
  }
  function openWidget(kind) {
    if (!snapshot) return;
    activeWidget = kind; activeStudent = null;
    text('widget-modal-title', kind === 'progress' ? 'LICENCE PROGRESS' : kind === 'deliveries' ? productionModel() ? 'CLASS DELIVERIES' : 'QUALIFYING SALES' : labels[kind].toUpperCase());
    el('widget-modal-content').innerHTML = widgetContent(kind);
    showDialog(widgetModal);
  }
  function render() {
    renderStats(); renderRoster();
    if (activeStudent && !modal.hidden) {
      var student = students.find(function (s) { return s.name === activeStudent; });
      if (student) el('stu-modal-content').innerHTML = studentContent(student);
      else closeDialogs();
    }
    if (activeWidget && !widgetModal.hidden) el('widget-modal-content').innerHTML = widgetContent(activeWidget);
  }
  function clear(message) {
    snapshot = null; students = []; page = 0;
    closeDialogs();
    el('stu-modal-content').textContent = '';
    el('widget-modal-content').textContent = '';
    el('stu-modal-portrait').removeAttribute('src');
    el('stu-modal-portrait').alt = '';
    render(); text('teach-message', message);
  }
  function request(path, options) {
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) { var error = new Error(data.error || 'Could not reach the class.'); error.status = response.status; throw error; }
        return data;
      });
    });
  }
  function handleError(error) {
    if (error.status === 401 || error.status === 403 || error.status === 404) {
      blockedToken = currentToken;
      clear('Teacher access has expired or is unavailable. Open the console and sign in again.');
    } else {
      text('teach-state', snapshot ? 'UPDATE FAILED' : 'OFFLINE');
      text('teach-message', snapshot ? 'Could not refresh. Showing the last update; use Refresh to retry.' : 'Could not load the class. Use Refresh to retry.');
    }
  }
  function refresh() {
    var stored = teacher(), token = stored ? stored.teacher_token : '';
    if (token !== currentToken) {
      currentToken = token; blockedToken = ''; generation++; loading = false;
      clear(token ? 'Loading your class…' : 'Open the teacher console and enter your teacher code to connect this dashboard.');
    }
    if (!token || token === blockedToken || loading || acting) { setControls(); return Promise.resolve(); }
    var run = generation;
    loading = true; setControls();
    return request('/api/game/teacher/econ?teacher_token=' + encodeURIComponent(token), { cache: 'no-store' })
      .then(function (data) {
        if (run !== generation || token !== currentToken) return;
        var storedNow = teacher();
        if (!storedNow || storedNow.teacher_token !== token) return refresh();
        if (!Array.isArray(data.students)) throw new Error('Invalid class response');
        snapshot = data; students = data.students.map(prepare);
        render();
        text('teach-message', 'Updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' · Refreshes every 15 seconds');
      }).catch(function (error) { if (run === generation && token === currentToken) handleError(error); })
      .finally(function () { if (run === generation) { loading = false; setControls(); } });
  }
  function togglePause() {
    if (!snapshot || acting || loading || !currentToken) return;
    var storedNow = teacher();
    if (!storedNow || storedNow.teacher_token !== currentToken) { refresh(); return; }
    var token = currentToken, action = snapshot.paused ? 'resume' : 'pause';
    acting = true; setControls();
    request('/api/game/teacher', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ teacher_token: token, action: action }) })
      .then(function () { if (token === currentToken && snapshot) { snapshot.paused = action === 'pause'; renderStats(); } })
      .catch(function (error) { if (token === currentToken) handleError(error); })
      .finally(function () { acting = false; setControls(); if (snapshot) refresh(); });
  }

  ['tb-search', 'tb-sort', 'tb-band'].forEach(function (id) {
    el(id).addEventListener(id === 'tb-search' ? 'input' : 'change', function () { page = 0; renderRoster(); });
  });
  el('teach-page-prev').addEventListener('click', function () { page--; renderRoster(); });
  el('teach-page-next').addEventListener('click', function () { page++; renderRoster(); });
  el('teach-refresh').addEventListener('click', refresh);
  el('teach-pause').addEventListener('click', togglePause);
  function activateStudent(event) {
    var row = event.target.closest('[data-student]');
    if (!row || (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault(); openStudent(Number(row.getAttribute('data-student')));
  }
  rows.addEventListener('click', activateStudent); rows.addEventListener('keydown', activateStudent);
  widgetModal.addEventListener('click', activateStudent); widgetModal.addEventListener('keydown', activateStudent);
  var widgets = document.querySelector('.widgets');
  function activateWidget(event) {
    var card = event.target.closest('[data-widget]');
    if (!card || (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault(); openWidget(card.getAttribute('data-widget'));
  }
  widgets.addEventListener('click', activateWidget); widgets.addEventListener('keydown', activateWidget);
  [modal, widgetModal].forEach(function (dialog) {
    dialog.addEventListener('click', function (event) { if (event.target === dialog) closeDialogs(); });
  });
  el('stu-modal-close').addEventListener('click', closeDialogs);
  el('widget-modal-close').addEventListener('click', closeDialogs);
  document.addEventListener('keydown', function (event) {
    var visible = !modal.hidden ? modal : !widgetModal.hidden ? widgetModal : null;
    if (!visible) return;
    if (event.key === 'Escape') { event.preventDefault(); closeDialogs(); return; }
    if (event.key !== 'Tab') return;
    var focusable = Array.prototype.filter.call(visible.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]'), function (node) { return node.getClientRects().length; });
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !visible.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || !visible.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
  });
  window.addEventListener('storage', function (event) { if (!event.key || event.key === teacherKey) refresh(); });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
  if (window.ResizeObserver) new ResizeObserver(function () { renderRoster(); }).observe(rows);
  else window.addEventListener('resize', renderRoster);
  clear('Open the teacher console and enter your teacher code to connect this dashboard.');
  refresh();
  setInterval(function () { if (!document.hidden) refresh(); }, 15000);
}());
