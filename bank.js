/* Server-owned bank balances. Retried intentions keep their original receipt ID. */
(function () {
  'use strict';
  var root = document.getElementById('bank-page');
  if (!root) return;
  var session = {}, state = null, busy = false, refreshing = false, pending = null;
  var pendingKey = 'yomama_bank_pending_v1';
  try {
    session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {};
    var saved = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
    if (saved && saved.token === session.token) pending = saved.body;
  } catch (_) {}
  var el = function (id) { return document.getElementById(id); };
  var ym = function (n) { return Math.trunc(n || 0).toLocaleString('en-US') + ' YM'; };
  var usd = function (cents) { return '$' + (cents / 100).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) + ' USD'; };
  function time(seconds) {
    var hours = Math.ceil(seconds / 3600);
    if (seconds <= 0) return 'Due now';
    if (hours >= 24) return Math.floor(hours / 24) + 'd ' + (hours % 24) + 'h';
    return hours + 'h';
  }
  function note(message, tone) {
    el('bank-status').textContent = message; el('bank-status').dataset.tone = tone || '';
    root.querySelectorAll('dialog[open] .bank-dialog-status').forEach(function (node) { node.textContent = message; node.dataset.tone = tone || ''; });
  }
  function shortYM(amount) {
    if (Math.abs(amount) < 100000) return ym(amount);
    return (amount / (Math.abs(amount) >= 1000000 ? 1000000 : 1000)).toLocaleString('en-US', {maximumFractionDigits:1}) + (Math.abs(amount) >= 1000000 ? 'M YM' : 'k YM');
  }
  function remember() {
    try {
      if (pending) sessionStorage.setItem(pendingKey, JSON.stringify({token:session.token, body:pending}));
      else sessionStorage.removeItem(pendingKey);
    } catch (_) {}
  }
  async function request(path, body) {
    var controller = new AbortController(), timeout = setTimeout(function () { controller.abort(); }, 20000);
    try {
      var response = await fetch(path, {method:body ? 'POST' : 'GET', cache:'no-store', signal:controller.signal,
        headers:body ? {'Content-Type':'application/json'} : {},
        body:body ? JSON.stringify(Object.assign({}, body, {token:session.token || ''})) : undefined});
      var data = await response.json();
      if (!response.ok || data.ok === false) {
        var error = new Error(data.error || data.why || 'Transaction could not be completed.');
        error.status = response.status; throw error;
      }
      return data;
    } finally { clearTimeout(timeout); }
  }
  function quote() {
    if (!state) return;
    var rules = state.bank.rules, direction = el('exchange-direction').value;
    var amount = Number(el('exchange-amount').value.replace(/,/g, ''));
    el('exchange-amount').style.width = Math.max(3, el('exchange-amount').value.length) + 'ch';
    var received = direction === 'buy_usd' ? Math.floor(amount * 10000 / rules.ymPerUsdHundredths) : Math.floor(Math.round(amount * 100) * rules.ymPerUsdHundredths / 10000);
    el('exchange-quote').textContent = !Number.isFinite(received) || received < 0 ? '—' : direction === 'buy_usd' ? usd(received) : ym(received);
    el('exchange-quote').style.setProperty('--bank-quote-length', el('exchange-quote').textContent.length);
    var borrow = Number(el('borrow-amount').value), lend = Number(el('lend-amount').value);
    el('borrow-quote').textContent = 'If held 7 days: repay ' + ym(borrow + Math.ceil(borrow * rules.loanBps * rules.termDays / 10000)) + '.';
    el('lend-quote').textContent = 'In 7 days: receive ' + ym(lend + Math.floor(lend * rules.lendingBps * rules.termDays / 10000)) + '.';
  }
  function controls() {
    var locked = busy || !!pending || !state || state.paused || state.behind;
    root.querySelectorAll('form button, form input, form select').forEach(function (node) { node.disabled = !!locked || (node.tagName === 'BUTTON' && node.hidden); });
    el('bank-retry').hidden = !pending;
    el('bank-retry').disabled = busy || !!(state && state.paused);
    if (!state) return;
    var bank = state.bank;
    var unavailable = locked || !!bank.loan;
    el('borrow-form').querySelector('button').disabled = !!unavailable;
    el('lend-form').querySelector('button').disabled = !!locked || bank.notes.length >= bank.rules.maxNotes;
    el('repay-form').querySelectorAll('input,button').forEach(function (node) { node.disabled = !!locked || !bank.loan; });
    el('bank-repay-open').disabled = !bank.loan;
  }
  var names = {deposit:'Deposited', withdraw:'Withdrew', buy_usd:'Exchanged YM to USD', sell_usd:'Exchanged USD to YM', borrow:'Business loan received', repay:'Loan repayment', repay_all:'Loan repaid in full', lend:'Lent to bank', lending_matured:'Bank note returned', savings_interest:'Overnight interest paid', loan_overdue:'Loan overdue'};
  function render() {
    if (!state) { controls(); return; }
    var bank = state.bank;
    el('game-hud').innerHTML = window.YomamaEcon.resourceBar(state);
    el('bank-debt').textContent = shortYM(bank.debt);
    el('bank-score').textContent = bank.creditScore;
    el('bank-gauge-needle').style.transform = 'rotate(' + (-80 + (bank.creditScore - 300) / 550 * 160) + 'deg)';
    el('bank-account-cash').textContent = shortYM(state.cash);
    el('bank-account-cash').title = ym(state.cash) + ' spendable cash';
    el('bank-loan-offer').textContent = shortYM(bank.loan ? bank.debt : bank.borrowLimit);
    el('bank-loan-offer').title = bank.loan ? 'Current loan balance' : 'Available borrowing limit';
    el('bank-borrow-open').textContent = bank.loan ? 'VIEW LOAN' : 'TAKE LOAN';
    el('bank-borrow-open').dataset.bankOpen = bank.loan ? 'repay' : 'borrow';
    el('bank-next-payment').textContent = shortYM(bank.debt);
    el('bank-next-due').textContent = bank.loan ? (bank.loan.overdue ? 'OVERDUE' : 'DUE IN ' + time(bank.loan.secondsRemaining)) : 'NO ACTIVE LOAN';
    el('bank-savings').textContent = shortYM(bank.savings);
    el('bank-savings').title = ym(bank.savings);
    el('bank-usd').textContent = bank.usdCents < 1000000 ? usd(bank.usdCents) : '$' + (bank.usdCents / (bank.usdCents >= 100000000 ? 100000000 : 100000)).toLocaleString('en-US', {maximumFractionDigits:1}) + (bank.usdCents >= 100000000 ? 'M USD' : 'k USD');
    el('bank-usd').title = usd(bank.usdCents);
    el('bank-midnight').textContent = time(bank.nextInterestSeconds) + (state.paused ? ' · paused' : ' · class time');
    el('bank-earned').textContent = ym(bank.interestEarned);
    el('borrow-limit').textContent = bank.loan ? 'Repay your current loan before borrowing again.' : 'Available to borrow: ' + ym(bank.borrowLimit) + '.';
    el('borrow-amount').max = bank.borrowLimit;
    var notes = el('bank-notes'); notes.replaceChildren();
    bank.notes.forEach(function (n) {
      var row = document.createElement('div'); row.className = 'bank-note';
      row.textContent = ym(n.principal) + ' → ' + ym(n.principal + n.interest) + ' in ' + time(n.secondsRemaining); notes.appendChild(row);
    });
    el('loan-balance').textContent = bank.loan ? ym(bank.debt) + ' outstanding' : 'No active loan';
    el('loan-due').textContent = bank.loan ? (bank.loan.overdue ? 'Overdue · repay to stop further interest.' : 'Due in ' + time(bank.loan.secondsRemaining) + ' · automatic payment from spendable cash.') : 'Borrow for a plan. Repay on time.';
    el('repay-amount').max = Math.min(bank.debt, state.cash);
    var history = el('bank-history'); history.replaceChildren();
    bank.history.forEach(function (entry) {
      var row = document.createElement('li'), label = document.createElement('span'), value = document.createElement('span');
      label.textContent = names[entry.kind] || entry.kind;
      value.textContent = entry.kind === 'sell_usd' ? usd(entry.amount) : ym(entry.amount);
      if (entry.received != null) value.textContent += ' → ' + (entry.kind === 'buy_usd' ? usd(entry.received) : ym(entry.received));
      row.append(label, value); history.appendChild(row);
    });
    el('history-count').textContent = '(' + bank.history.length + ')';
    if (state.paused) note('Class paused. Banking resumes when your teacher starts the clock.');
    controls(); quote();
  }
  function apply(data) { state = data; render(); window.dispatchEvent(new CustomEvent('yomama:econ', {detail:data})); }
  async function refresh() {
    if (refreshing || busy) return;
    refreshing = true;
    try { var data = await request('/api/game/econ/state?token=' + encodeURIComponent(session.token || '')); if (!busy) apply(data); }
    catch (error) { if (!busy) note(error.message || 'Connection interrupted. Try again shortly.', 'error'); }
    finally { refreshing = false; }
  }
  async function transact(action, amount) {
    if (busy || !state || state.paused) return;
    if (!pending) {
      if (!Number.isSafeInteger(amount) || amount <= 0) { note('Enter a positive amount.', 'error'); return; }
      pending = {action:action, amount:amount, revision:state.bank.revision, requestId:crypto.randomUUID()};
      remember();
    }
    busy = true; controls(); note('Saving your transaction…');
    try {
      var data = await request('/api/game/bank', pending), receipt = data.receipt;
      pending = null; remember(); apply(data);
      root.querySelectorAll('dialog[open]').forEach(function (dialog) { dialog.close(); });
      note((names[receipt.action] || 'Transaction saved') + ' · ' + (receipt.action === 'sell_usd' ? usd(receipt.amount) : ym(receipt.amount)) + (receipt.replayed ? ' · confirmed from receipt' : ''), 'success');
    } catch (error) {
      // Explicit client errors mean the transaction was rejected. A timeout or
      // server failure is uncertain, so keep the same intention across reloads.
      if (error.status && error.status < 500) { pending = null; remember(); }
      note(pending ? 'Confirmation interrupted. Check the pending transaction to retry safely.' : error.message, 'error');
    } finally { busy = false; controls(); if (!pending) await refresh(); }
  }
  el('savings-form').addEventListener('submit', function (event) { event.preventDefault(); transact(event.submitter ? event.submitter.value : 'deposit', Number(el('savings-amount').value)); });
  el('borrow-form').addEventListener('submit', function (event) { event.preventDefault(); transact('borrow', Number(el('borrow-amount').value)); });
  el('lend-form').addEventListener('submit', function (event) { event.preventDefault(); transact('lend', Number(el('lend-amount').value)); });
  el('repay-form').addEventListener('submit', function (event) { event.preventDefault(); transact('repay', Number(el('repay-amount').value)); });
  el('repay-full').addEventListener('click', function () { if (state) transact('repay_all', state.bank.debt); });
  el('exchange-form').addEventListener('submit', function (event) {
    event.preventDefault(); var action = el('exchange-direction').value, amount = Number(el('exchange-amount').value.replace(/,/g, ''));
    transact(action, action === 'sell_usd' ? Math.round(amount * 100) : amount);
  });
  el('exchange-direction').addEventListener('change', function () {
    var selling = this.value === 'sell_usd';
    el('exchange-label').textContent = 'YOU PAY';
    el('exchange-unit').textContent = selling ? 'USD' : 'YM';
    el('exchange-amount').value = selling ? '1.00' : '1,000';
    root.querySelectorAll('[data-exchange-mode]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.exchangeMode === el('exchange-direction').value));
    });
    quote();
  });
  root.querySelectorAll('[data-exchange-mode]').forEach(function (button) {
    button.addEventListener('click', function () {
      var select = el('exchange-direction');
      if (select.value === button.dataset.exchangeMode) return;
      select.value = button.dataset.exchangeMode;
      select.dispatchEvent(new Event('change'));
    });
  });
  root.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-bank-open]');
    if (opener) {
      var dialog = el('bank-' + opener.dataset.bankOpen + '-dialog');
      if (!dialog) return;
      dialog.querySelectorAll('.bank-dialog-status').forEach(function (node) { node.textContent = ''; });
      if (opener.dataset.bankOpen === 'savings') {
        var withdrawing = opener.dataset.bankMode === 'withdraw';
        el('bank-savings-title').textContent = withdrawing ? 'WITHDRAW YM' : 'DEPOSIT YM';
        el('savings-form').querySelectorAll('button').forEach(function (button) {
          var selected = button.value === (withdrawing ? 'withdraw' : 'deposit');
          button.classList.toggle('bank-primary', selected);
          button.hidden = !selected;
          button.type = selected ? 'submit' : 'button';
          button.disabled = !selected || busy || !!pending || !state || state.paused || state.behind;
        });
      }
      dialog.showModal();
    }
    var closer = event.target.closest('[data-bank-close]');
    if (closer) closer.closest('dialog').close();
  });
  root.addEventListener('input', quote);
  el('bank-retry').addEventListener('click', function () { transact(); });
  controls();
  if (!session.token) { note('Sign in to open your bank account.', 'error'); return; }
  request('/api/game/econ/login', {}).then(function (data) {
    apply(data);
    if (!data.paused) note(pending ? 'A transaction needs confirmation. Check it before continuing.' : 'Welcome to your bank. Every transaction saves to your class seat.');
  }).catch(function (error) { note(error.message || 'Unable to reach your bank.', 'error'); });
  setInterval(function () { if (!document.hidden) refresh(); }, 15000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
}());
