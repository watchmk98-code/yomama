/* Operations page lock for testing: only the Focus tree is open.
   Flip LOCKED to false (and bump the ?v= on advanced-hq.html) to reopen
   Team, Products, Quests, Group projects and Advanced HQ. Load this before
   workforce.js so the page opens on the Focus tree whatever the URL says. */
(function () {
  'use strict';
  var LOCKED = true;
  var OPEN_TAB = 'focus';
  var MESSAGE = 'CLOSED FOR TESTING';
  var DETAIL = 'Only the Focus tree is open right now. Team, Products, Quests and Advanced HQ come back later.';
  window.YOMAMA_OPERATIONS_LOCKED = LOCKED;
  if (!LOCKED) return;

  function focusHash() {
    if (location.hash !== '#' + OPEN_TAB) {
      try { history.replaceState(null, '', location.pathname + location.search + '#' + OPEN_TAB); } catch (e) { /* file: URLs */ }
    }
  }
  focusHash();
  document.documentElement.classList.add('ops-locked');

  function tabOf(el) {
    var t = el.closest('[data-wf-tab]');
    if (t) return t.dataset.wfTab;
    var o = el.closest('[data-workforce-open]');
    if (o) return o.dataset.workforceOpen;
    return null;
  }
  // Runs before workforce.js's own listener (capture beats bubble on document).
  document.addEventListener('click', function (event) {
    if (!(event.target instanceof Element)) return;
    var wanted = tabOf(event.target);
    if (wanted && wanted !== OPEN_TAB) {
      event.preventDefault();
      event.stopImmediatePropagation();
      var open = document.getElementById('game-wf-tab-' + OPEN_TAB);
      if (open && open.getAttribute('aria-selected') !== 'true') open.click();
    }
  }, true);
  document.addEventListener('keydown', function (event) {
    if (!(event.target instanceof Element) || !event.target.closest('.wf-tabs')) return;
    if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].indexOf(event.key) !== -1) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  window.addEventListener('hashchange', focusHash);

  function enforce() {
    var tabs = document.querySelector('.wf-tabs');
    if (tabs && !tabs.querySelector('.ops-lock-cell')) {
      Array.prototype.forEach.call(tabs.querySelectorAll('[data-wf-tab]'), function (b) {
        if (b.dataset.wfTab !== OPEN_TAB) b.hidden = true;
      });
      var cell = document.createElement('div');
      cell.className = 'ops-lock-cell';
      cell.setAttribute('role', 'note');
      cell.innerHTML = '<strong>' + MESSAGE + '</strong><span>' + DETAIL + '</span>';
      tabs.appendChild(cell);
    }
    var panel = document.getElementById('game-wf-panel');
    if (panel && panel.getAttribute('aria-labelledby') !== 'game-wf-tab-' + OPEN_TAB) {
      var open = document.getElementById('game-wf-tab-' + OPEN_TAB);
      if (open) open.click();
    }
    var badge = document.getElementById('game-operations-prestige');
    if (badge && badge.dataset.workforceOpen !== OPEN_TAB) { badge.dataset.workforceOpen = OPEN_TAB; badge.setAttribute('href', '#' + OPEN_TAB); }
  }
  function watch() {
    var host = document.getElementById('econ-auto');
    if (!host) return;
    new MutationObserver(enforce).observe(host, { childList: true, subtree: true });
    var head = document.querySelector('.game-page-head');
    if (head) new MutationObserver(enforce).observe(head, { attributes: true, subtree: true, attributeFilter: ['data-workforce-open', 'hidden'] });
    enforce();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch); else watch();
})();
