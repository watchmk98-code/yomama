/* Operations page lock.

   Two rules, and only one applies to a class:
   - Quest engine ON  -> the page opens when the player has earned the
     'operations' feature (the Head Office quest). Until then only the Focus
     tree is open, and the notice says how to open the rest.
   - Quest engine OFF -> the testing lock below decides, exactly as before.
     Flip TESTING_LOCK to false (and bump the ?v= on advanced-hq.html) to
     reopen Team, Products, Quests, Group projects and Advanced HQ.

   Loaded before workforce.js so the page opens on the Focus tree whatever the
   URL says. The lock is presentational: the API enforces its own rules. */
(function () {
  'use strict';
  var TESTING_LOCK = true;
  var OPEN_TAB = 'focus';
  var TESTING_MESSAGE = 'CLOSED FOR TESTING';
  var TESTING_DETAIL = 'Only the Focus tree is open right now. Team, Products, Quests and Advanced HQ come back later.';
  var QUEST_MESSAGE = 'LOCKED';
  var QUEST_DETAIL = 'Own six businesses and claim the Head Office quest to open Team, Products and Advanced HQ.';

  var questMode = false;   // true once a snapshot says the quest engine is on
  var locked = TESTING_LOCK;
  window.YOMAMA_OPERATIONS_LOCKED = locked;

  function snapshot() {
    return window.YomamaEcon && window.YomamaEcon.state ? window.YomamaEcon.state() : null;
  }
  function evaluate() {
    var state = snapshot();
    var quests = state && state.quests;
    if (quests && quests.enabled) {
      questMode = true;
      return (quests.features || []).indexOf('operations') === -1;
    }
    if (state) questMode = false;      // a real snapshot without the engine
    return TESTING_LOCK;
  }
  function message() { return questMode ? QUEST_MESSAGE : TESTING_MESSAGE; }
  function detail() { return questMode ? QUEST_DETAIL : TESTING_DETAIL; }

  function focusHash() {
    if (locked && location.hash !== '#' + OPEN_TAB) {
      try { history.replaceState(null, '', location.pathname + location.search + '#' + OPEN_TAB); } catch (e) { /* file: URLs */ }
    }
  }
  function tabOf(el) {
    var t = el.closest('[data-wf-tab]');
    if (t) return t.dataset.wfTab;
    var o = el.closest('[data-workforce-open]');
    if (o) return o.dataset.workforceOpen;
    return null;
  }

  // Runs before workforce.js's own listener (capture beats bubble on document).
  document.addEventListener('click', function (event) {
    if (!locked || !(event.target instanceof Element)) return;
    var wanted = tabOf(event.target);
    if (wanted && wanted !== OPEN_TAB) {
      event.preventDefault();
      event.stopImmediatePropagation();
      var open = document.getElementById('game-wf-tab-' + OPEN_TAB);
      if (open && open.getAttribute('aria-selected') !== 'true') open.click();
    }
  }, true);
  document.addEventListener('keydown', function (event) {
    if (!locked || !(event.target instanceof Element) || !event.target.closest('.wf-tabs')) return;
    if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].indexOf(event.key) !== -1) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  window.addEventListener('hashchange', focusHash);

  function enforce() {
    var tabs = document.querySelector('.wf-tabs');
    if (!locked) {
      document.documentElement.classList.remove('ops-locked');
      if (tabs) {
        Array.prototype.forEach.call(tabs.querySelectorAll('[data-wf-tab]'), function (b) { b.hidden = false; });
        var stale = tabs.querySelector('.ops-lock-cell');
        if (stale) stale.remove();
      }
      return;
    }
    document.documentElement.classList.add('ops-locked');
    if (tabs) {
      Array.prototype.forEach.call(tabs.querySelectorAll('[data-wf-tab]'), function (b) {
        if (b.dataset.wfTab !== OPEN_TAB) b.hidden = true;
      });
      var cell = tabs.querySelector('.ops-lock-cell');
      if (!cell) {
        cell = document.createElement('div');
        cell.className = 'ops-lock-cell';
        cell.setAttribute('role', 'note');
        tabs.appendChild(cell);
      }
      cell.innerHTML = '<strong>' + message() + '</strong><span>' + detail() + '</span>';
    }
    var panel = document.getElementById('game-wf-panel');
    if (panel && panel.getAttribute('aria-labelledby') !== 'game-wf-tab-' + OPEN_TAB) {
      var open = document.getElementById('game-wf-tab-' + OPEN_TAB);
      if (open) open.click();
    }
    var badge = document.getElementById('game-operations-prestige');
    if (badge && badge.dataset.workforceOpen !== OPEN_TAB) { badge.dataset.workforceOpen = OPEN_TAB; badge.setAttribute('href', '#' + OPEN_TAB); }
  }

  function refresh() {
    var next = evaluate();
    var changed = next !== locked;
    locked = next;
    window.YOMAMA_OPERATIONS_LOCKED = locked;
    if (changed) focusHash();
    enforce();
  }

  function watch() {
    var host = document.getElementById('econ-auto');
    if (host) new MutationObserver(enforce).observe(host, { childList: true, subtree: true });
    var head = document.querySelector('.game-page-head');
    if (head) new MutationObserver(enforce).observe(head, { attributes: true, subtree: true, attributeFilter: ['data-workforce-open', 'hidden'] });
    refresh();
    setInterval(refresh, 1000);   // reads econ.js's snapshot; no network of its own
  }
  focusHash();
  if (locked) document.documentElement.classList.add('ops-locked');
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch); else watch();
})();
