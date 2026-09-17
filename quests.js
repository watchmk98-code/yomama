/* Quests on Build, in the shape the page already had: a one-line strip per
   kind showing what this business has open, and everything else behind a
   popup. Nothing is listed until you ask for it.
   While econ.js is polling, this reads its snapshot instead of fetching. */
(function () {
  'use strict';
  if (!document.getElementById('econ-building')) return;

  var session = {};
  try { session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {}; } catch (_) {}
  var rendered = '';
  var busy = false;
  var message = '';
  var view = null;     // {kind:'list', scope:'building'|'group'} or {kind:'quest', id:...}

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function el(id) { return document.getElementById(id); }
  function dialog() { return el('game-quests-dialog'); }

  function snapshot() {
    return window.YomamaEcon && window.YomamaEcon.state ? window.YomamaEcon.state() : null;
  }
  function data() {
    var state = snapshot();
    return state && state.quests && state.quests.enabled ? state.quests : null;
  }

  /* econ.js owns the business picker and saves the chosen slot; follow it so
     the strip always describes the business on screen. */
  function building() {
    var state = snapshot();
    if (!state || !state.buildings || !state.buildings.length) return null;
    var slot = null;
    try { slot = Number(sessionStorage.getItem('yomama_business_slot')); } catch (_) {}
    return state.buildings.find(function (b) { return b.slot === slot; }) ||
           state.buildings[state.buildings.length - 1];
  }

  function listFor(scope) {
    var payload = data();
    if (!payload) return [];
    var b = building();
    return payload.quests.filter(function (q) {
      return scope === 'building' ? (b && q.buildingId === b.id) : !q.buildingId;
    });
  }
  function find(id) {
    var payload = data();
    return payload && payload.quests.find(function (q) { return q.id === id; });
  }

  function request(body) {
    return fetch('/api/game/quests', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({}, body, {token: session.token || ''}))
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || payload.ok === false) throw new Error(payload.why || 'That did not work.');
        return payload;
      });
    });
  }

  function claim(questId, choiceId) {
    if (busy) return;
    busy = true; message = '';
    renderDialog();
    var body = {action: 'quest_claim', questId: questId};
    if (choiceId) body.choiceId = choiceId;
    request(body).then(function (payload) {
      var receipt = payload.receipt || payload;
      message = receipt.message || 'Quest complete.';
    }).catch(function (error) {
      message = error.message;
    }).then(function () {
      busy = false; rendered = '';
      if (window.YomamaEcon && window.YomamaEcon.refresh) window.YomamaEcon.refresh();
      renderDialog();
    });
  }

  // ------------------------------------------------------------- the strips
  var RANK = {ready: 0, tracking: 1, available: 2, waiting: 3, done: 4};
  function ordered(rows) {
    return rows.slice().sort(function (a, b) {
      return (RANK[a.status] - RANK[b.status]) || (a.chapter - b.chapter) || (a.id < b.id ? -1 : 1);
    });
  }

  function strip(scope, label, rows) {
    var open = rows.filter(function (q) { return q.status !== 'done'; });
    var ready = rows.filter(function (q) { return q.ready; }).length;
    var summary = open.length
      ? ordered(open).map(function (q) { return q.title; }).join(' · ')
      : (rows.length ? 'All done' : 'Nothing here yet');
    return '<section class="game-building-activity" data-quest-scope="' + scope + '">' +
      '<div class="game-activity-copy"><strong>' + esc(label) +
      (ready ? ' <span class="k-good">' + ready + ' ready</span>' : '') + '</strong>' +
      '<small title="' + esc(summary) + '">' + esc(summary) + '</small></div>' +
      '<button id="game-quests-open-' + scope + '" type="button" class="game-small-button"' +
      ' data-quest-view="' + scope + '">View →</button></section>';
  }

  /* The strips replace econ.js's own inside its `.game-build-bottom`, rather
     than being added next to it. game-fit.js zooms the whole workspace down
     until it fits the viewport, so an extra element of our own shrank the
     entire page and left a dead band beneath it. */
  function render(force) {
    var payload = data();
    document.documentElement.classList.toggle('quests-engine', !!payload);
    var bottom = document.querySelector('#econ-building .game-build-bottom');
    if (!bottom || !payload) { rendered = ''; return; }
    var b = building();
    var mine = listFor('building'), group = listFor('group');
    var key = JSON.stringify([payload, b && b.id]);
    if (!force && key === rendered && bottom.dataset.questsMounted === '1') return;
    rendered = key;
    bottom.dataset.questsMounted = '1';
    bottom.innerHTML = strip('building', b ? b.name + ' quests' : 'Quests', mine) +
                       strip('group', 'Group quests', group);
    renderDialog();
  }

  // -------------------------------------------------------------- the popup
  function hours(seconds) {
    var h = Math.round((Number(seconds) || 0) / 3600);
    return h <= 1 ? 'about an hour' : 'about ' + h + ' hours';
  }
  function actionLabel(quest) {
    if (quest.status === 'done') return 'View reward';
    if (quest.status === 'waiting') return 'Comes back';
    if (quest.ready) return quest.choices && quest.choices.length ? 'Choose reward' : 'Claim reward';
    return quest.status === 'tracking' ? 'View progress' : 'Open quest';
  }

  function questCard(quest) {
    return '<article class="game-panel game-activity-card">' +
      '<h3>' + esc(quest.title) + (quest.status === 'done' ? ' <span class="k-good">✓</span>' : '') +
      (quest.repeatable ? ' <span class="quest-tag">Day ' + quest.day + '</span>' : '') + '</h3>' +
      '<p>' + esc(quest.summary) + '</p>' +
      '<p class="game-quest-reward">' + esc(quest.rewardText) + '</p>' +
      '<button type="button" class="game-small-button" data-quest-open="' + esc(quest.id) + '">' +
      actionLabel(quest) + ' →</button></article>';
  }

  function objective(row) {
    var pct = Math.max(0, Math.min(100, row.quantity ? row.owned / row.quantity * 100 : 0));
    return '<div class="quest-objective' + (row.ready ? ' is-ready' : '') + '">' +
      '<span>' + esc(row.label) + '</span><strong>' + row.owned + ' / ' + row.quantity + '</strong>' +
      '<i class="quest-bar"><b style="width:' + pct.toFixed(1) + '%"></b></i></div>';
  }

  function questDetail(quest) {
    var html = '<p class="game-quest-summary">' + esc(quest.summary) + '</p>';
    if (quest.teaches) html += '<p class="game-hint">' + esc(quest.teaches) + '</p>';
    if (quest.status === 'done') {
      return html + '<div class="game-quest-complete"><strong class="k-good">✓ Quest complete</strong>' +
        '<p>' + esc(quest.rewardText) + '</p></div>';
    }
    html += '<div class="quest-objectives">' + quest.objectives.map(objective).join('') + '</div>';
    if (quest.status === 'waiting') {
      return html + '<p class="game-hint">This one comes back in ' + esc(hours(quest.waitSeconds)) + '.</p>';
    }
    if (quest.choices && quest.choices.length) {
      html += '<h3 class="game-quest-step">Choose your reward</h3><div class="quest-choices">' +
        quest.choices.map(function (c) {
          return '<button type="button" class="game-small-button" data-quest-claim="' + esc(quest.id) +
            '" data-choice="' + esc(c.id) + '"' + (quest.ready && !busy ? '' : ' disabled') + '>' +
            esc(c.label) + '</button>';
        }).join('') + '</div>';
      if (!quest.ready) html += '<p class="game-hint">Finish the goals above to pick one.</p>';
      return html;
    }
    html += '<p class="game-quest-reward">' + esc(quest.rewardText) + '</p>' +
      '<button type="button" class="game-small-button" data-quest-claim="' + esc(quest.id) + '"' +
      (quest.ready && !busy ? '' : ' disabled') + '>' + (quest.ready ? 'Claim reward' : 'In progress') + '</button>';
    if (!quest.ready) html += '<p class="game-hint">Finish the goals above to claim this.</p>';
    return html;
  }

  function renderDialog() {
    var box = dialog();
    if (!box || !view) return;
    var title, eyebrow, body, back = '';
    if (view.kind === 'quest') {
      var quest = find(view.id);
      if (!quest) { view = null; box.close(); return; }
      title = quest.title;
      eyebrow = quest.group || '';
      body = questDetail(quest);
      back = '<button type="button" class="game-text-button" data-quest-back>← All quests</button>';
    } else {
      var b = building();
      var rows = ordered(listFor(view.scope));
      title = view.scope === 'building' ? (b ? b.name : 'Business') + ' quests' : 'Group quests';
      eyebrow = view.scope === 'building' ? 'This business' : 'Across your whole group';
      var payload = data() || {boosts: [], vouchers: []};
      var chips = payload.boosts.map(function (x) {
        return '<span class="quest-chip">×' + x.multiplier + ' order payout · ' + x.charges + ' left</span>';
      }).concat(payload.vouchers.map(function (v) {
        return '<span class="quest-chip">Voucher ' + (Number(v.amount) || 0).toLocaleString('en-US') + ' YM</span>';
      })).join('');
      body = (chips ? '<div class="quest-chips">' + chips + '</div>' : '') + (rows.length
        ? '<div class="game-activity-list">' + rows.map(questCard).join('') + '</div>'
        : '<p class="game-hint">No quests here yet.</p>');
    }
    el('game-quests-dialog-title').textContent = title;
    el('game-quests-eyebrow').textContent = eyebrow;
    el('game-quests-content').innerHTML = back + body;
    var status = box.querySelector('[data-econ-status]');
    if (status) status.textContent = message;
  }

  function open(next) {
    view = next; message = '';
    var box = dialog();
    if (!box) return;
    renderDialog();
    if (!box.open) box.showModal();
  }

  document.addEventListener('click', function (event) {
    if (!(event.target instanceof Element)) return;
    var strip = event.target.closest('[data-quest-view]');
    if (strip) { open({kind: 'list', scope: strip.dataset.questView}); return; }
    var card = event.target.closest('[data-quest-open]');
    if (card) { open({kind: 'quest', id: card.dataset.questOpen}); return; }
    if (event.target.closest('[data-quest-back]')) {
      var quest = find(view && view.id);
      open({kind: 'list', scope: quest && quest.buildingId ? 'building' : 'group'});
      return;
    }
    if (event.target.closest('[data-close-quests]')) {
      var box = dialog(); if (box) box.close(); view = null; return;
    }
    var claimButton = event.target.closest('[data-quest-claim]');
    if (claimButton && !claimButton.disabled) claim(claimButton.dataset.questClaim, claimButton.dataset.choice);
  });

  // econ.js rewrites #econ-building on every poll, taking the strips with it.
  var building_el = document.getElementById('econ-building');
  if (building_el && window.MutationObserver) {
    new MutationObserver(function () { render(true); }).observe(building_el, {childList: true});
  }
  render(true);
  setInterval(render, 1000);   // reads econ.js's snapshot; no network of its own
}());
