/* The first shift follows real economy state. Only the guide's reading progress
   lives in the browser; cash, goods, orders, and quest rewards stay on server. */
(function () {
  'use strict';

  var buildPage = !!document.getElementById('econ-building');
  var marketPage = !!document.getElementById('econ-market');
  if (!buildPage && !marketPage) return;

  var session = null;
  try { session = JSON.parse(localStorage.getItem('yomama_session_v1') || 'null'); } catch (_) {}
  if (!session || !session.token) return;

  function seatKey(token) {
    var a = 2166136261, b = 2246822519;
    for (var i = 0; i < token.length; i++) {
      a = Math.imul(a ^ token.charCodeAt(i), 16777619);
      b = Math.imul(b ^ token.charCodeAt(i), 3266489917);
    }
    return (a >>> 0).toString(36) + '-' + (b >>> 0).toString(36);
  }
  var key = 'yomama_first_shift_v1:' + seatKey(session.token);
  var record = null;
  var state = null;
  var originalMarket = null;
  var DURATION = 25 * 60 * 1000;

  function read() {
    if (record) return record;
    try { record = JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) {}
    return record;
  }
  function save() {
    try { localStorage.setItem(key, JSON.stringify(record)); } catch (_) {}
  }
  function fresh(s) {
    var farm = (s.buildings || []).find(function (b) { return b.id === 'farm'; });
    var upgrades = farm && farm.upgrades || {};
    return s.modelVersion >= 4 && s.buildingsOwned === 1 && !!farm &&
      Number((s.checklist || {}).goodSales || 0) === 0 &&
      Number((s.progression || {}).prestigeEarned || 0) === 0 &&
      Number(s.cash || 0) <= 200 &&
      ['production', 'sales', 'storage'].every(function (kind) {
        return !upgrades[kind] || Number(upgrades[kind].level) === 1;
      });
  }
  function setup(s) {
    if (read()) return record;
    var eligible = fresh(s);
    record = {
      version: 1, stage: eligible ? 0 : 9, closed: false, finished: !eligible,
      activeMs: 0, lastActiveAt: Date.now(), lastTick: Number(s.tick || 0),
      firstSales: Number((s.checklist || {}).goodSales || 0),
      upgradeLevels: levels(s), seenStock: false, seenOrder: false,
      viewedQuest: false, viewedExpansion: false, celebrationSeen: false,
      deliveryReward: null, deliveryCash: null, lastUpgrade: null
    };
    save();
    return record;
  }
  function levels(s) {
    var farm = (s.buildings || []).find(function (b) { return b.id === 'farm'; });
    var upgrades = farm && farm.upgrades || {};
    return ['production', 'sales', 'storage'].map(function (kind) {
      return Number(upgrades[kind] && upgrades[kind].level || 1);
    });
  }
  function active(s) {
    return !setup(s).finished;
  }
  function sales(s) {
    return Number((s.checklist || {}).goodSales || 0) > record.firstSales;
  }
  function upgraded(s) {
    return levels(s).some(function (level, i) { return level > record.upgradeLevels[i]; });
  }
  function quest(s) {
    if (s.quests && s.quests.enabled) {
      var chapter = s.quests.quests || [];
      return chapter.find(function (q) { return q.id === 'first-crop' && q.status !== 'done'; }) ||
        chapter.find(function (q) { return q.buildingId === 'farm' && q.status !== 'done'; }) ||
        chapter.find(function (q) { return q.id === 'first-crop'; });
    }
    var legacy = (s.progression || {}).quests || [];
    return legacy.find(function (q) { return q.id === 'farm-plan' && q.status !== 'done'; }) ||
      legacy.find(function (q) { return q.buildingId === 'farm' && q.status !== 'done'; }) ||
      legacy.find(function (q) { return q.id === 'farm-plan'; });
  }
  function targetOrder(s) {
    var offers = ((s.orders || s.contracts || {}).offers || []);
    var choices = offers.map(function (order, index) { return {order: order, index: index}; })
      .filter(function (item) {
        var needs = item.order.requirements || [];
        return !item.order.project && !item.order.locked && needs.length &&
          needs.every(function (need) { return need.buildingId === 'farm'; });
      });
    choices.sort(function (a, b) {
      var tomatoA = a.order.requirements.every(function (need) { return need.goodId === 'farm_tomatoes'; });
      var tomatoB = b.order.requirements.every(function (need) { return need.goodId === 'farm_tomatoes'; });
      return Number(tomatoB) - Number(tomatoA) ||
        Number(b.order.canFulfill) - Number(a.order.canFulfill) ||
        Number(a.order.target || 0) - Number(b.order.target || 0);
    });
    return choices[0] || null;
  }
  function orderSelector(s, actionControl) {
    var found = targetOrder(s);
    if (!found) return '.game-market-orders';
    var card = '[data-order-slot="' + found.index + '"]';
    if (actionControl && found.order.canFulfill) return card + ' [data-econ-action^="fulfill:"]';
    if (actionControl && !found.order.committed) return card + ' [data-econ-action^="commit:"]';
    return card;
  }
  function advance(s) {
    if (record.stage <= 1 && record.seenStock) record.stage = 1;
    if (record.stage === 1 && record.seenOrder) record.stage = 2;
    if (record.stage <= 2 && sales(s)) record.stage = 3;
    if (record.stage === 3 && record.celebrationSeen) record.stage = 4;
    if (record.stage === 4 && upgraded(s)) record.stage = 5;
    if (record.stage === 5 && !quest(s)) record.stage = 6;
    if (record.stage === 5 && record.viewedQuest) record.stage = 6;
    if (record.stage === 6 && (record.viewedExpansion || s.buildingsOwned > 1)) record.stage = 7;
    if (record.stage === 7 && record.activeMs >= DURATION) record.stage = 8;
  }
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function minutesLeft() {
    return Math.max(0, Math.ceil((DURATION - record.activeMs) / 60000));
  }
  function message(s) {
    var farm = (s.buildings || []).find(function (b) { return b.id === 'farm'; });
    var order = targetOrder(s), next = (s.frontier || [])[0], q = quest(s);
    if (s.paused) return {title: 'Class paused', detail: 'Your teacher will resume the business clock. Your progress is saved.', button: 'Review guide', action: 'review'};
    switch (record.stage) {
      case 0: return {title: 'First shift · Your farm', detail: 'Your farm makes goods automatically. Start by looking at its stock.', button: buildPage ? 'Show stock' : 'Open farm', action: 'stock'};
      case 1: return {title: 'First shift · Find an order', detail: 'Market orders turn goods into cash. Find a farm order and read Have / need.', button: marketPage ? 'Show farm order' : 'Open Market', action: 'order'};
      case 2:
        if (!order) return {title: 'Find a farm order', detail: 'The current cards need other goods. Use CLICK!!!! on an order card for a free new offer.', button: marketPage ? 'Show orders' : 'Open Market', action: 'order'};
        if (order.order.canFulfill) return {title: 'First shift · Ready to deliver', detail: 'This order has every item it needs. Press Deliver on its card to earn cash.', button: marketPage ? 'Show Deliver' : 'Open Market', action: 'order'};
        if (order.order.committed) return {title: 'Goods are on their way', detail: 'This order is saved. Your farm is making the missing goods; Have / need updates as they arrive.', button: marketPage ? 'Show order' : 'Open Market', action: 'order'};
        return {title: 'Save this farm order', detail: 'Walk-in customers buy automatically. Save this order so its available goods stay for delivery.', button: marketPage ? 'Show Save' : 'Open Market', action: 'order'};
      case 3: return {title: 'First delivery complete!', detail: record.deliveryReward != null && record.deliveryCash != null ?
        'The order paid ' + record.deliveryReward + ' YM. Cash is now ' + record.deliveryCash + ' YM. You can spend it on upgrades.' :
        'The goods left your stock and the reward went into Cash. You can spend Cash on upgrades.', button: 'Continue', action: 'celebrate'};
      case 4:
        var upgrades = farm && farm.upgrades || {};
        var preferred = farm && Number(farm.stored || 0) > Number(farm.capacity || 0) * 0.3 ? 'sales' : 'production';
        if (upgrades[preferred] && !upgrades[preferred].canBuy && upgrades[preferred === 'sales' ? 'production' : 'sales'] &&
            upgrades[preferred === 'sales' ? 'production' : 'sales'].canBuy) preferred = preferred === 'sales' ? 'production' : 'sales';
        var row = upgrades[preferred] || upgrades.sales || upgrades.production;
        var affordable = row && row.canBuy;
        return affordable ?
          {title: 'First shift · Choose an upgrade', detail: preferred === 'sales' ? 'Stock is building up. Customers can buy more of what your farm makes.' : 'Production makes goods faster. Check the Sales and Costs change before buying.', button: buildPage ? 'Show upgrades' : 'Open Build', action: 'upgrade'} :
          {title: 'Save for your first upgrade', detail: 'Upgrades spend Cash now. Fill another order or let shop sales earn enough first.', button: marketPage ? 'Show orders' : 'Open Market', action: 'order'};
      case 5: return {title: record.lastUpgrade ? 'Your ' + record.lastUpgrade + ' upgrade is live' : 'First shift · Farm quest', detail: q ? 'Next, ' + q.title + ': ' + q.summary : 'Quests reward real business progress. Open the farm quest to see its goal.', button: buildPage ? 'View quest' : 'Open Build', action: 'quest'};
      case 6: return {title: 'First shift · Your next business', detail: next ? next.name + ' needs ' + (next.why || 'Cash and any listed requirements') + '. Your farm keeps working when another business opens.' : 'Your other businesses keep working as you expand.', button: buildPage ? 'Show expansion' : 'Open Build', action: 'expand'};
      case 7:
        if (s.build) return {title: s.build.name + ' is being built', detail: 'Your farm keeps earning while construction finishes. The next business will join it.', button: buildPage ? 'Show construction' : 'Open Build', action: 'expand'};
        if (s.buildingsOwned > 1) return {title: s.buildingsOwned + ' businesses are working', detail: 'They make goods at the same time. Check Market for orders using your new products.', button: marketPage ? 'Show orders' : 'Open Market', action: 'order'};
        if (q && q.ready) return {title: q.title + ' is ready', detail: 'Claim the quest reward you earned from your business activity.', button: buildPage ? 'View quest' : 'Open Build', action: 'quest'};
        if (next && next.canExpand) return {title: 'Ready for ' + next.name, detail: 'You can open it now. Your farm will continue producing alongside it.', button: buildPage ? 'Show expansion' : 'Open Build', action: 'expand'};
        return {title: 'Your next move', detail: 'Deliver orders for Cash. ' + (s.quests && s.quests.enabled ? 'Follow opening quests for rewards.' : 'Work on the farm quest for Prestige.') + ' ' + minutesLeft() + ' min left in your first shift.', button: marketPage ? 'Show orders' : 'Open Market', action: 'order'};
      default: return {title: 'First shift complete', detail: 'You know the loop: make goods, deliver orders, improve businesses, and follow quests to expand.', button: 'Finish', action: 'finish'};
    }
  }
  function board() {
    return buildPage ? document.querySelector('#econ-building > .game-opening-guide') : document.querySelector('.game-orders-notice');
  }
  function guideButton() {
    var head = document.querySelector('.game-page-head');
    if (!head) return;
    var button = head.querySelector('[data-first-shift-toggle]');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'game-first-shift-toggle';
      button.dataset.firstShiftToggle = '';
      button.textContent = '?';
      button.title = 'Open first shift guide';
      button.setAttribute('aria-label', 'Open first shift guide');
      var heading = head.querySelector('.game-build-guide') || head.querySelector('h1');
      if (heading) heading.after(button);
      else head.appendChild(button);
    }
    button.hidden = record.finished;
    button.setAttribute('aria-pressed', String(!record.closed));
  }
  function highlight(selector) {
    document.querySelectorAll('.is-first-shift-target').forEach(function (node) { node.classList.remove('is-first-shift-target'); });
    var target = selector && document.querySelector(selector);
    if (target && !target.closest('[hidden],.game-view-hidden')) target.classList.add('is-first-shift-target');
  }
  function render(s) {
    var focused = !record.finished && !record.closed && record.stage <= 6;
    document.body.classList.toggle('first-shift-focus', focused);
    if (focused) document.body.dataset.firstShiftStage = String(record.stage);
    else delete document.body.dataset.firstShiftStage;
    document.querySelectorAll('.first-shift-targeted-orders,.is-first-shift-order').forEach(function (node) {
      node.classList.remove('first-shift-targeted-orders', 'is-first-shift-order');
    });
    if (focused && marketPage && record.stage <= 2) {
      var chosen = document.querySelector(orderSelector(s, false));
      var grid = chosen && chosen.closest('.game-order-grid');
      if (grid) {
        grid.classList.add('first-shift-targeted-orders');
        chosen.classList.add('is-first-shift-order');
      }
    }
    guideButton();
    var node = board();
    if (!node) return;
    if (marketPage && originalMarket === null) originalMarket = node.innerHTML;
    if (record.finished) {
      node.classList.remove('game-first-shift-board');
      if (marketPage) node.innerHTML = originalMarket;
      if (marketPage) {
        try { node.hidden = sessionStorage.getItem('yomama_market_notice_dismissed') === '1'; }
        catch (_) { node.hidden = false; }
      } else node.hidden = true;
      highlight(null);
      if (window.YomamaFit && window.YomamaFit.render) window.YomamaFit.render();
      return;
    }
    node.hidden = !!record.closed;
    if (record.closed) {
      highlight(null);
      if (window.YomamaFit && window.YomamaFit.render) window.YomamaFit.render();
      return;
    }
    var step = message(s);
    var focusedAction = node.contains(document.activeElement) && document.activeElement.dataset.firstShiftAction;
    var focusedClose = node.contains(document.activeElement) && document.activeElement.hasAttribute('data-first-shift-close');
    node.classList.add('game-first-shift-board');
    var progress = record.stage < 7 ? 'STEP ' + (record.stage + 1) + '/7' : record.stage === 7 ? 'PRACTICE' : 'COMPLETE';
    node.innerHTML = '<span class="game-first-shift-progress">FIRST SHIFT · ' +
      escapeHtml(progress) + '</span><div><strong' + (marketPage ? ' id="orders-notice-title"' : '') + '>' + escapeHtml(step.title) +
      '</strong><small>' + escapeHtml(step.detail) + '</small></div>' +
      '<button type="button" class="game-small-button" data-first-shift-action="' + step.action + '">' + escapeHtml(step.button) + '</button>' +
      '<button type="button" class="game-notice-close" data-first-shift-close aria-label="Hide guide" title="Hide guide">×</button>';
    var focusTarget = focusedClose ? node.querySelector('[data-first-shift-close]') :
      focusedAction === step.action ? node.querySelector('[data-first-shift-action]') : null;
    if (focusTarget) focusTarget.focus({preventScroll: true});
    var highlighted = null;
    if (buildPage) {
      if (record.stage === 0) highlighted = '#stock';
      else if (record.stage === 4) highlighted = '.game-operations';
      else if (record.stage === 7 && quest(s) && quest(s).ready)
        highlighted = s.quests && s.quests.enabled ? '[data-quest-view="building"]' : '[data-building-activities="quests"]';
      else if (record.stage >= 6) highlighted = '.game-expansion';
    } else if (record.stage <= 2) highlighted = orderSelector(s, record.stage === 2);
    highlight(highlighted);
    if (window.YomamaFit && window.YomamaFit.render) window.YomamaFit.render();
  }
  function update(s) {
    state = s;
    setup(s);
    if (!record.finished) {
      var now = Date.now();
      if (document.visibilityState !== 'hidden' && !s.paused) record.activeMs += Math.max(0, Math.min(30000, now - record.lastActiveAt));
      record.lastActiveAt = now;
      if (Number(s.tick || 0) < record.lastTick) {
        record = null;
        try { localStorage.removeItem(key); } catch (_) {}
        setup(s);
      }
      record.lastTick = Number(s.tick || 0);
      advance(s);
      save();
    }
    render(s);
  }
  function show(selector) {
    var target = document.querySelector(selector);
    if (!target) return false;
    var panel = target.closest('.game-view-hidden');
    if (panel) {
      var tab = document.querySelector('[aria-controls="' + panel.id + '"]');
      if (tab) tab.click();
      target = document.querySelector(selector);
    }
    if (!target) return false;
    var pages = 0;
    while (target.closest('[hidden],.game-view-hidden') && pages++ < 6) {
      var pager = document.querySelector('.game-pager[data-page="Orders"] button:last-child');
      if (!pager) break;
      pager.click();
      target = document.querySelector(selector);
    }
    if (!target || target.closest('[hidden],.game-view-hidden')) return false;
    highlight(selector);
    target.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'smooth'});
    return true;
  }
  function move(action) {
    if (!state || !record) return;
    record.closed = false;
    if (action === 'finish') { record.finished = true; save(); render(state); if (buildPage && window.YomamaEcon) window.YomamaEcon.refresh(); return; }
    if (action === 'celebrate') { record.celebrationSeen = true; advance(state); save(); render(state); return; }
    if (action === 'review') { render(state); return; }
    if (action === 'stock') {
      if (!buildPage) { location.href = './buildings.html#stock'; return; }
      if (show('#stock')) { record.seenStock = true; advance(state); save(); render(state); }
      return;
    }
    if (action === 'order') {
      if (!marketPage) { location.href = './marketplace.html'; return; }
      if (show(orderSelector(state, record.stage === 2))) {
        record.seenOrder = true; advance(state); save(); render(state);
      }
      return;
    }
    if (!buildPage) { location.href = './buildings.html'; return; }
    if (action === 'upgrade') { show('.game-operations'); return; }
    if (action === 'expand') {
      if (show('.game-expansion') && record.stage === 6) { record.viewedExpansion = true; advance(state); save(); render(state); }
      return;
    }
    if (action === 'quest') {
      var trigger = state.quests && state.quests.enabled ? document.querySelector('[data-quest-view="building"]') :
        document.querySelector('[data-building-activities="quests"]');
      if (!trigger) return;
      trigger.click();
      var selected = quest(state);
      var item = selected && document.querySelector(state.quests && state.quests.enabled ?
        '[data-quest-open="' + selected.id + '"]' : '[data-game-quest="' + selected.id + '"]');
      if (item) item.click();
      var activities = document.getElementById('game-activities');
      if (activities && activities.open && item) activities.close();
      record.viewedQuest = true;
      advance(state);
      save();
      render(state);
    }
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-first-shift-toggle]')) { record.closed = !record.closed; save(); render(state); return; }
    if (event.target.closest('[data-first-shift-close]')) { record.closed = true; save(); render(state); return; }
    var action = event.target.closest('[data-first-shift-action]');
    if (action) move(action.dataset.firstShiftAction);
    if (marketPage && event.target.closest('.game-orders-notice .game-notice-close:not([data-first-shift-close])')) {
      var notice = board();
      if (notice) notice.hidden = true;
      try { sessionStorage.setItem('yomama_market_notice_dismissed', '1'); } catch (_) {}
    }
  });
  window.addEventListener('yomama:econ', function (event) {
    if (event.detail && event.detail.buildings) update(event.detail);
  });
  document.addEventListener('visibilitychange', function () {
    if (record) { record.lastActiveAt = Date.now(); save(); }
  });
  window.addEventListener('yomama:econ-action', function (event) {
    if (!record || record.finished) return;
    var name = event.detail && event.detail.name || '';
    if (name.indexOf('fulfill:') === 0) {
      record.stage = Math.max(record.stage, 3);
      record.deliveryReward = event.detail.receipt && event.detail.receipt.reward != null ? Number(event.detail.receipt.reward) : null;
      record.deliveryCash = event.detail.cashAfter != null ? Number(event.detail.cashAfter) : null;
    }
    if (name.indexOf('upgrade:') === 0) record.lastUpgrade = {production:'Production',sales:'Customers',storage:'Storage'}[name.split(':')[2]] || 'business';
    save();
    if (state) { advance(state); render(state); }
  });
  window.setInterval(function () { if (state && record && !record.finished) update(state); }, 10000);
  window.YomamaOnboarding = {active: active, step: function () { return record && record.stage; }};
}());
