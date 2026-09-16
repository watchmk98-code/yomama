/* Quests render at the bottom of Build. The server owns every claim.
   This module never fetches on its own while econ.js is polling: it reads the
   snapshot econ.js already holds, so a class of thirty adds no extra load. */
(function () {
  'use strict';
  var host = document.getElementById('econ-quests');
  if (!host) return;

  var session = {};
  try { session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {}; } catch (_) {}
  var rendered = '';
  var busy = false;
  var message = '';

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function ym(value) { return (Number(value) || 0).toLocaleString('en-US') + ' YM'; }

  function snapshot() {
    return window.YomamaEcon && window.YomamaEcon.state ? window.YomamaEcon.state() : null;
  }
  function data() {
    var state = snapshot();
    return state && state.quests && state.quests.enabled ? state.quests : null;
  }

  function request(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({}, body, {token: session.token || ''}))
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.why || payload.error || 'That did not work.');
        }
        return payload;
      });
    });
  }

  function claim(questId) {
    if (busy) return;
    busy = true;
    message = '';
    render(true);
    request('/api/game/quests', {action: 'quest_claim', questId: questId}).then(function (payload) {
      message = payload.message || 'Quest complete.';
    }).catch(function (error) {
      message = error.message;
    }).then(function () {
      busy = false;
      rendered = '';
      if (window.YomamaEcon && window.YomamaEcon.refresh) window.YomamaEcon.refresh();
      else render(true);
    });
  }

  function objective(row) {
    var pct = Math.max(0, Math.min(100, row.quantity ? row.owned / row.quantity * 100 : 0));
    return '<div class="quest-objective' + (row.ready ? ' is-ready' : '') + '">' +
      '<span class="quest-objective-label">' + esc(row.label) + '</span>' +
      '<span class="quest-objective-bar"><i style="width:' + pct.toFixed(1) + '%"></i></span>' +
      '<strong>' + row.owned + ' / ' + row.quantity + '</strong></div>';
  }

  function card(quest) {
    var done = quest.status === 'done';
    var button = done
      ? '<span class="quest-done">✓ Complete</span>'
      : '<button type="button" class="game-small-button quest-claim" data-quest="' + esc(quest.id) + '"' +
        (quest.ready && !busy ? '' : ' disabled') + '>' + (quest.ready ? 'Claim reward' : 'In progress') + '</button>';
    return '<article class="game-panel quest-card" data-status="' + esc(quest.status) + '">' +
      '<h4>' + esc(quest.title) + (done ? ' <span class="k-good">✓</span>' : '') + '</h4>' +
      '<p class="quest-summary">' + esc(quest.summary) + '</p>' +
      (quest.teaches ? '<p class="quest-teaches">' + esc(quest.teaches) + '</p>' : '') +
      (done ? '' : '<div class="quest-objectives">' + quest.objectives.map(objective).join('') + '</div>') +
      '<p class="quest-reward">' + esc(quest.rewardText) + '</p>' + button + '</article>';
  }

  function strip(payload) {
    var bits = payload.boosts.map(function (boost) {
      return '<span class="quest-chip">×' + boost.multiplier + ' ' +
        esc(String(boost.metric).replace(/_/g, ' ')) + ' · ' + boost.charges + ' left</span>';
    }).concat(payload.vouchers.map(function (voucher) {
      return '<span class="quest-chip">Voucher ' + esc(ym(voucher.amount)) + '</span>';
    }));
    return bits.length ? '<div class="quest-strip">' + bits.join('') + '</div>' : '';
  }

  function chapters(payload) {
    var groups = {};
    payload.quests.forEach(function (quest) {
      (groups[quest.chapter] = groups[quest.chapter] || []).push(quest);
    });
    return Object.keys(groups).sort(function (a, b) { return a - b; }).map(function (key) {
      var label = key === '0' ? 'Business development' : 'Chapter ' + key;
      return '<section class="quest-chapter"><h3>' + esc(label) + '</h3>' +
        '<div class="quest-grid">' + groups[key].map(card).join('') + '</div></section>';
    }).join('');
  }

  function render(force) {
    var payload = data();
    // One quest system per class: hide econ.js's legacy panels while this one runs.
    document.documentElement.classList.toggle('quests-engine', !!payload);
    if (!payload) { host.innerHTML = ''; host.hidden = true; rendered = ''; return; }
    host.hidden = false;
    var key = JSON.stringify(payload) + '|' + busy + '|' + message;
    if (!force && key === rendered) return;
    rendered = key;
    host.innerHTML =
      '<div class="quest-head"><h2>QUESTS</h2>' +
      '<span class="quest-count">' + payload.completed + ' / ' + payload.total + ' complete</span></div>' +
      strip(payload) +
      (payload.quests.length ? chapters(payload)
        : '<p class="game-hint">No quests available yet. Keep building.</p>') +
      (message ? '<p class="quest-status" role="status">' + esc(message) + '</p>' : '');
  }

  host.addEventListener('click', function (event) {
    var button = event.target.closest('.quest-claim');
    if (button && button.dataset.quest) claim(button.dataset.quest);
  });

  render(true);
  setInterval(render, 1000);   // reads econ.js's snapshot; no network of its own
}());
