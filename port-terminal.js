/* Port reads each student's portfolio from the game server. The paper engine
 * supplies read-only presentation helpers. The old browser sample is available
 * only with ?demo=1 and is never imported into a student's game account. */
(function () {
  'use strict';

  var engine = window.YomamaPaperEngine;
  var root = document.querySelector('.port-workspace');
  if (!root) return;
  if (!engine) {
    root.innerHTML = '<p class="port-fatal" role="alert">The trading desk could not load. Please reload the page.</p>';
    return;
  }

  var STORAGE_KEY = 'yport.paperState.v1';
  var PREFERENCES_KEY = 'yport.view.v1';
  var PENDING_KEY = 'yport.pendingRequest.v1';
  var demoMode = new URLSearchParams(window.location.search).get('demo') === '1';
  var DEFAULT_WATCHLIST = ['AAPL', 'NVDA', 'MSFT', 'AMZN', 'GOOGL', 'AMD'];
  // Fixed example quotes, not a market feed. The first four preserve the old
  // demo's marks and order reference prices. Saved marks take precedence.
  var catalog = {
    AAPL: { name: 'Apple Inc.', sector: 'Technology', price: 191.25, change: 1.40, description: 'Devices, software and services.', aliases: ['Apple'] },
    NVDA: { name: 'NVIDIA Corp.', sector: 'Semiconductors', price: 887, change: -1.66, description: 'Computing chips and software for graphics and data centres.', aliases: ['Nvidia', 'NVIDIA'] },
    MSFT: { name: 'Microsoft Corp.', sector: 'Technology', price: 436.40, change: 1.12, description: 'Business software, cloud services and computing products.', aliases: ['Microsoft'] },
    AMZN: { name: 'Amazon.com Inc.', sector: 'Retail & cloud', price: 184.06, change: -0.60, description: 'Online retail, cloud computing and subscription services.', aliases: ['Amazon'] },
    GOOGL: { name: 'Alphabet Inc.', sector: 'Technology', price: 176.33, change: 0.85, description: 'Search, advertising, video and cloud services.', aliases: ['Alphabet', 'Google'] },
    AMD: { name: 'Advanced Micro Devices', sector: 'Semiconductors', price: 164.20, change: 2.10, description: 'Processors and graphics chips for computers and data centres.', aliases: ['AMD', 'Advanced Micro Devices'] },
    META: { name: 'Meta Platforms', price: 493.50 }, TSLA: { name: 'Tesla Inc.', price: 177.29 },
    AVGO: { name: 'Broadcom Inc.', price: 171.50 }, ADBE: { name: 'Adobe Inc.', price: 519.28 },
    NFLX: { name: 'Netflix Inc.', price: 650.61 }, INTC: { name: 'Intel Corp.', price: 30.74 },
    CSCO: { name: 'Cisco Systems', price: 46.65 }, QCOM: { name: 'Qualcomm Inc.', price: 203.81 },
    AMAT: { name: 'Applied Materials', price: 235.41 }, MU: { name: 'Micron Technology', price: 132.23 },
    TXN: { name: 'Texas Instruments', price: 195.01 }, BKNG: { name: 'Booking Holdings', price: 3885.43 },
    PDD: { name: 'PDD Holdings', price: 147.35 }, INTU: { name: 'Intuit Inc.', price: 576.44 }
  };
  var byId = function (id) { return document.getElementById(id); };
  var contestConfig;
  var paperState;
  var selectedSymbol = 'AAPL';
  var activeTab = 'positions';
  var researchTab = 'chart';
  var chartRange = '1W';
  var chartType = 'area';
  var side = 'buy';
  var instantFill = true;
  var savedQuotes = {};
  var liveQuotes = {};
  var serverLoaded = false;
  var serverConnected = false;
  var serverCanTrade = false;
  var serverMarket = { status: 'loading', message: 'Connecting to your portfolio…' };
  var executionRules = { maxQuoteAgeSeconds: 10, marketOrderTimeoutSeconds: 30 };
  var serverClockSeconds = null;
  var serverBlockedReason = '';
  var serverPlayerName = '';
  var requestBusy = false;
  var refreshPromise = null;
  var refreshGeneration = 0;
  var pendingRequest = null;
  var connectionMessage = '';
  var lastToken = '';
  var lastRefreshedAt = 0;
  var storageBlocked = false;
  var chartGeometry = null;
  var feedback = '';
  var feedbackError = false;
  var renderedMarkup = new WeakMap();
  var pickerSymbol = '';
  var quantityInput = byId('port-ticket-quantity');
  var typeInput = byId('port-ticket-type');
  var limitInput = byId('port-ticket-limit');

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  // Patch changed text and attributes while keeping focused buttons and scroll
  // containers in place. Row keys also preserve them when another row appears.
  function patchChildren(target, source) {
    Array.from(source.childNodes).forEach(function (next, index) {
      var current = target.childNodes[index];
      var key = next.nodeType === 1 && next.getAttribute('data-render-key');
      if (key && (!current || current.nodeType !== 1 || current.getAttribute('data-render-key') !== key)) {
        current = Array.from(target.children).find(function (child) { return child.getAttribute('data-render-key') === key; });
        if (current) target.insertBefore(current, target.childNodes[index] || null);
        else { target.insertBefore(next.cloneNode(true), target.childNodes[index] || null); return; }
      }
      if (!current) { target.appendChild(next.cloneNode(true)); return; }
      if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) {
        target.replaceChild(next.cloneNode(true), current); return;
      }
      if (next.nodeType !== 1) { if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue; return; }
      Array.from(current.attributes).forEach(function (attribute) {
        if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
      });
      Array.from(next.attributes).forEach(function (attribute) {
        if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
      });
      patchChildren(current, next);
    });
    while (target.childNodes.length > source.childNodes.length) target.lastChild.remove();
  }

  function renderContent(id, markup) {
    var target = byId(id);
    if (renderedMarkup.get(target) === markup) return;
    var template = document.createElement('template');
    template.innerHTML = markup;
    patchChildren(target, template.content);
    renderedMarkup.set(target, markup);
  }

  function symbolOf(value) {
    var symbol = String(value || '').trim().toUpperCase();
    return /^[A-Z][A-Z0-9.-]{0,11}$/.test(symbol) ? symbol : '';
  }

  function finite(value) { return typeof value === 'number' && Number.isFinite(value); }
  function positive(value) { return finite(value) && value > 0; }
  function money(value) {
    return finite(value) ? '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
  }
  function signedMoney(value) { return finite(value) ? (value >= 0 ? '+' : '−') + money(Math.abs(value)) : '—'; }
  function percent(value) { return finite(value) ? (value >= 0 ? '+' : '−') + Math.abs(value).toFixed(2) + '%' : '—'; }
  function tone(value) { return value > 0 ? 'is-up' : value < 0 ? 'is-down' : ''; }
  function dateText(value, includeTime, includeSeconds) {
    var date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return '—';
    var options = includeTime
      ? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }
      : { day: '2-digit', month: 'short', year: 'numeric' };
    options.timeZone = 'America/New_York';
    if (includeTime && includeSeconds) options.second = '2-digit';
    return date.toLocaleString('en-GB', options) + ' ET';
  }
  function epochSeconds(value) { return finite(value) ? value : Date.parse(value) / 1000; }
  function responseAgeSeconds() { return Math.max(0, performance.now() - lastRefreshedAt) / 1000; }
  function marketNow() { return finite(serverClockSeconds) ? serverClockSeconds + responseAgeSeconds() : null; }
  function countdown(seconds) {
    var remaining = Math.max(0, Math.ceil(seconds));
    if (remaining >= 86400) return Math.floor(remaining / 86400) + 'd ' + Math.floor(remaining % 86400 / 3600) + 'h';
    if (remaining >= 3600) return Math.floor(remaining / 3600) + 'h ' + Math.floor(remaining % 3600 / 60) + 'm';
    return remaining >= 60 ? Math.ceil(remaining / 60) + 'm' : remaining + 's';
  }
  function marketSessionText() {
    var open = serverMarket.status === 'open';
    var boundary = epochSeconds(open ? serverMarket.nextClose : serverMarket.nextOpen);
    var now = marketNow();
    var text = 'Regular U.S. session';
    if (!finite(boundary)) return text + ' · ET.';
    if (finite(now) && boundary <= now) return text + ' · awaiting market update.';
    return text + ' · ' + (open ? 'closes ' : 'opens ') + dateText(boundary * 1000, true) +
      (finite(now) ? ' (in ' + countdown(boundary - now) + ')' : '') + '.';
  }
  function executionText(isLimit) {
    var price = side === 'buy' ? 'ask' : 'bid';
    return isLimit ? 'Next eligible fresh ' + price + ' at your limit or better. GTC: open until filled or cancelled.'
      : 'Next eligible fresh ' + price + '; unfilled orders expire after ' + executionRules.marketOrderTimeoutSeconds + 's.';
  }
  function company(symbol) { return catalog[symbol] || { name: symbol }; }
  function position(symbol) { return paperState.positions && paperState.positions[symbol]; }
  function allSymbols() {
    return Array.from(new Set(Object.keys(catalog).concat(Object.keys(paperState.positions || {}),
      engine.getOpenOrders(paperState).map(function (order) { return order.symbol; }), [selectedSymbol]))).filter(symbolOf);
  }

  function quote(symbol) {
    if (!demoMode) {
      var live = liveQuotes[symbol] || {};
      return { price: positive(live.price) ? live.price : null,
        bid: positive(live.bid) ? live.bid : null, ask: positive(live.ask) ? live.ask : null,
        change: finite(live.change) ? live.change : null, timestamp: live.timestamp };
    }
    var stock = company(symbol);
    var held = position(symbol);
    var price = held && positive(held.marketPrice) ? held.marketPrice : savedQuotes[symbol];
    if (!positive(price)) price = stock.price;
    if (!positive(price) && held && positive(held.avgCost)) price = held.avgCost;
    if (!positive(price)) {
      var fills = paperState.ledger && paperState.ledger.fills || [];
      for (var i = fills.length - 1; i >= 0; i -= 1) {
        if (fills[i].symbol === symbol && positive(fills[i].fillPrice)) { price = fills[i].fillPrice; break; }
      }
    }
    var previous = positive(stock.price) && finite(stock.change) ? stock.price / (1 + stock.change / 100) : null;
    return { price: positive(price) ? price : null, change: previous && positive(price) ? (price / previous - 1) * 100 : null };
  }

  function saveState() {
    if (!demoMode) {
      try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ selectedSymbol: selectedSymbol,
        activeTab: activeTab, researchTab: researchTab, chartRange: chartRange, chartType: chartType })); } catch (_) {}
      return;
    }
    if (storageBlocked) return;
    allSymbols().forEach(function (symbol) { var value = quote(symbol).price; if (positive(value)) savedQuotes[symbol] = value; });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        contestConfig: contestConfig, paperState: paperState, selectedSymbol: selectedSymbol,
        activeTab: activeTab, instantFill: instantFill, researchTab: researchTab,
        chartRange: chartRange, quotes: savedQuotes
      }));
      byId('port-save-status').textContent = 'Saved on this browser';
    } catch (_) {
      byId('port-save-status').textContent = 'Browser storage unavailable';
      feedback = 'This browser could not save your practice portfolio. Keep this tab open to retain your changes.';
      feedbackError = true;
    }
  }

  function loadState() {
    if (!demoMode) return false;
    var raw;
    try { raw = localStorage.getItem(STORAGE_KEY); } catch (_) { return false; }
    if (!raw) return false;
    try {
      var saved = JSON.parse(raw);
      if (!saved || !saved.paperState || !saved.contestConfig || !saved.paperState.account ||
          !saved.paperState.positions || !saved.paperState.ledger || !Array.isArray(saved.paperState.ledger.orders) ||
          !Array.isArray(saved.paperState.ledger.fills) || !finite(saved.paperState.account.availableCash)) throw Error('Invalid portfolio');
      contestConfig = saved.contestConfig;
      paperState = saved.paperState;
      selectedSymbol = symbolOf(saved.selectedSymbol) || 'AAPL';
      activeTab = ['positions', 'orders', 'history'].indexOf(saved.activeTab) >= 0 ? saved.activeTab : 'positions';
      chartRange = ['1D', '1W', '1M', '3M', '1Y', '5Y'].indexOf(saved.chartRange) >= 0 ? saved.chartRange : '1W';
      instantFill = typeof saved.instantFill === 'boolean' ? saved.instantFill : true;
      if (saved.quotes && typeof saved.quotes === 'object') Object.keys(saved.quotes).forEach(function (symbol) {
        if (symbolOf(symbol) && positive(saved.quotes[symbol])) savedQuotes[symbol] = saved.quotes[symbol];
      });
      return true;
    } catch (_) {
      // Leave the original save untouched; never replace a damaged portfolio
      // with sample holdings just because the new view cannot read it.
      storageBlocked = true;
      feedback = 'Your saved portfolio could not be read. Trading is paused to protect the existing save.';
      feedbackError = true;
      return false;
    }
  }

  function emptyServerState() {
    return { accountId: '', account: { startingCash: 0, availableCash: 0, reservedCash: 0, realizedPnl: 0 },
      positions: {}, ledger: { orders: [], fills: [], cashEvents: [] }, meta: {} };
  }

  function seatToken() {
    try { var seat = JSON.parse(localStorage.getItem('yomama_session_v1') || 'null'); return seat && seat.token || ''; }
    catch (_) { return ''; }
  }

  function newRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return Array.from(bytes).map(function (value) { return value.toString(16).padStart(2, '0'); }).join('');
  }

  function savePendingRequest() {
    try {
      if (pendingRequest) sessionStorage.setItem(PENDING_KEY, JSON.stringify(pendingRequest));
      else sessionStorage.removeItem(PENDING_KEY);
    } catch (_) {}
  }

  function loadServerPreferences() {
    try {
      var prefs = JSON.parse(localStorage.getItem(PREFERENCES_KEY) || 'null');
      if (prefs) {
        selectedSymbol = symbolOf(prefs.selectedSymbol) || 'AAPL';
        if (['positions', 'orders', 'history'].indexOf(prefs.activeTab) >= 0) activeTab = prefs.activeTab;
        if (['1D', '1W', '1M', '3M', '1Y', '5Y'].indexOf(prefs.chartRange) >= 0) chartRange = prefs.chartRange;
        if (['area', 'candles', 'bars', 'line'].indexOf(prefs.chartType) >= 0) chartType = prefs.chartType;
      }
    } catch (_) {}
    lastToken = seatToken();
    try {
      var pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
      if (pending && pending.token === lastToken && ['/order', '/cancel'].indexOf(pending.path) >= 0 &&
          pending.body && pending.body.accountId && pending.body.clientOrderId) pendingRequest = pending;
    } catch (_) {}
  }

  function serverRequest(method, path, body) {
    var token = seatToken();
    if (!token) { var absent = new Error('Sign in to load your Port account.'); absent.status = 401; return Promise.reject(absent); }
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timeout = controller ? setTimeout(function () { controller.abort(); }, 12000) : null;
    var options = { method: method, cache: 'no-store', credentials: 'same-origin', headers: {} };
    if (controller) options.signal = controller.signal;
    var url = '/api/game/port' + path;
    if (method === 'GET') url += '?' + new URLSearchParams(Object.assign({}, body || {}, { token: token })).toString();
    else { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(Object.assign({}, body, { token: token })); }
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { throw new Error('The portfolio server returned an unreadable response.'); }).then(function (payload) {
        if (!response.ok) { var error = new Error(payload.error || 'The portfolio request failed.'); error.status = response.status; throw error; }
        if (token !== seatToken()) { var changed = new Error('The signed-in seat changed. Reload to open its account.'); changed.status = 401; throw changed; }
        return payload;
      });
    }).finally(function () { if (timeout) clearTimeout(timeout); });
  }

  function applyServerResponse(payload) {
    var state = payload && payload.portfolio;
    if (!state || !state.accountId || !state.account || !finite(state.account.availableCash) ||
        !state.positions || !state.ledger || !Array.isArray(state.ledger.orders) || !Array.isArray(state.ledger.fills)) {
      throw new Error('The portfolio response could not be read. Trading is paused.');
    }
    var previous = paperState;
    paperState = state;
    liveQuotes = payload.quotes && typeof payload.quotes === 'object' ? payload.quotes : {};
    serverMarket = payload.market || { status: 'unavailable', message: 'Market prices are unavailable.' };
    var rules = payload.executionRules || {};
    executionRules.maxQuoteAgeSeconds = positive(rules.maxQuoteAgeSeconds) ? rules.maxQuoteAgeSeconds
      : positive(serverMarket.maxQuoteAgeSeconds) ? serverMarket.maxQuoteAgeSeconds : 10;
    executionRules.marketOrderTimeoutSeconds = positive(rules.marketOrderTimeoutSeconds) ? rules.marketOrderTimeoutSeconds : 30;
    serverClockSeconds = positive(payload.serverTime) ? payload.serverTime : positive(serverMarket.asOf) ? serverMarket.asOf : null;
    serverCanTrade = payload.canTrade === true;
    serverBlockedReason = payload.blockedReason || '';
    serverPlayerName = payload.player && payload.player.name || '';
    serverLoaded = true;
    serverConnected = true;
    lastRefreshedAt = performance.now();
    connectionMessage = '';
    if (pendingRequest) {
      if (pendingRequest.body.accountId !== state.accountId) {
        pendingRequest = null;
        feedback = 'Your Port account was reset. Review the new balance before placing an order.';
        feedbackError = true;
      } else {
        var order = state.ledger.orders.find(function (item) {
          return item.id === (pendingRequest.path === '/order' ? pendingRequest.body.clientOrderId : pendingRequest.body.orderId);
        });
        if (order && (pendingRequest.path === '/order' || order.cancellationRequestedAt || order.status !== 'pending')) {
          pendingRequest = null;
          describeOrder(order);
        }
      }
      savePendingRequest();
    }
    if (!requestBusy && !pendingRequest && previous.accountId === state.accountId) {
      var completed = state.ledger.orders.filter(function (order) {
        return order.status !== 'pending' && previous.ledger.orders.some(function (old) { return old.id === order.id && old.status === 'pending'; });
      });
      if (completed.length) describeOrder(completed[completed.length - 1]);
    }
  }

  function describeOrder(order) {
    var label = order.symbol + ' ' + order.side + ' order';
    feedbackError = ['rejected', 'expired'].indexOf(order.status) >= 0;
    if (order.status === 'filled') {
      var fill = paperState.ledger.fills.find(function (item) { return item.orderId === order.id; });
      feedback = (order.side === 'buy' ? 'Bought ' : 'Sold ') + order.quantity + ' ' + order.symbol +
        (fill ? ' at ' + money(fill.fillPrice) : '') + '. View History for details.';
    } else if (order.status !== 'pending') {
      feedback = label + ' ' + (order.status === 'canceled' ? 'cancelled' : order.status) + '. ' + (order.reason || 'View History for details.');
    } else if (order.cancellationRequestedAt) {
      feedback = 'Cancellation requested for ' + label + '. Waiting for confirmation.';
    } else {
      feedback = label + ' saved. ' + (order.type === 'limit' ? 'Waiting for your limit. View or cancel it in Orders.' : 'Waiting for the next eligible market quote.');
    }
  }

  function refreshPortfolio() {
    if (demoMode || requestBusy || refreshPromise) return refreshPromise || Promise.resolve();
    var token = seatToken();
    if (token !== lastToken) {
      lastToken = token;
      paperState = emptyServerState(); liveQuotes = {}; serverLoaded = false;
      serverClockSeconds = null;
      pendingRequest = null; savePendingRequest();
    }
    var generation = refreshGeneration;
    refreshPromise = serverRequest('GET', '').then(function (payload) {
      if (generation === refreshGeneration) applyServerResponse(payload);
    }).catch(function (error) {
      if (generation !== refreshGeneration) return;
      serverConnected = false; serverCanTrade = false;
      connectionMessage = error.status === 401 ? error.message : 'Portfolio connection interrupted. Reconnecting…';
      if (!serverLoaded) connectionMessage = error.status === 401 ? error.message : 'Your portfolio could not load. Retrying…';
    }).finally(function () { refreshPromise = null; render(); });
    return refreshPromise;
  }

  function quoteIsFresh(current) {
    var seconds = epochSeconds(current.timestamp);
    var now = marketNow();
    // The response's server time advances only by monotonic elapsed time.
    // Changing a student's device date cannot revive an old quote.
    if (!finite(now)) return false;
    var age = now - seconds;
    return positive(current.price) && finite(seconds) && age >= -5 && age <= executionRules.maxQuoteAgeSeconds;
  }

  function tradingBlock() {
    if (!serverLoaded) return connectionMessage || 'Loading your portfolio…';
    if (!serverConnected) return connectionMessage || 'Reconnecting to your portfolio…';
    if (responseAgeSeconds() > 15) return 'Refreshing your account before trading…';
    if (!finite(marketNow())) return 'Waiting for the market clock…';
    if (!serverCanTrade) return serverBlockedReason || serverMarket.message || 'Trading is temporarily unavailable.';
    var nextClose = epochSeconds(serverMarket.nextClose);
    if (serverMarket.status === 'open' && finite(nextClose) && marketNow() >= nextClose) return 'Regular session closed. Refreshing market status…';
    if (!quoteIsFresh(quote(selectedSymbol))) return 'Waiting for a fresh ' + selectedSymbol + ' quote.';
    return '';
  }

  function sendPendingRequest() {
    if (requestBusy || !pendingRequest || pendingRequest.token !== seatToken()) return;
    var request = pendingRequest;
    var submittedFromTab = activeTab;
    requestBusy = true;
    refreshGeneration += 1;
    feedback = 'Sending ' + (request.path === '/cancel' ? 'cancellation' : 'order') + '…'; feedbackError = false;
    render();
    // Admit orders and cancellations immediately. A poll started before this
    // intent can finish later, but its older account response is discarded.
    Promise.resolve().then(function () {
      if (request.body.accountId !== paperState.accountId || pendingRequest !== request) return null;
      return serverRequest('POST', request.path, request.body);
    }).then(function (payload) {
      if (!payload) return;
      applyServerResponse(payload);
      pendingRequest = null; savePendingRequest();
      var order = paperState.ledger.orders.find(function (item) { return item.id === (request.path === '/cancel' ? request.body.orderId : request.body.clientOrderId); });
      if (order) describeOrder(order);
      if (activeTab === submittedFromTab) activeTab = order && order.status !== 'pending' ? 'history' : 'orders';
    }).catch(function (error) {
      feedbackError = true;
      serverConnected = false; serverCanTrade = false;
      if (error.status >= 400 && error.status < 500) {
        pendingRequest = null; savePendingRequest();
        feedback = error.message;
      } else {
        feedback = 'Confirmation was interrupted. Retry this same request to check its result safely.';
      }
    }).finally(function () {
      requestBusy = false; saveState(); render(); refreshPortfolio();
    });
  }

  function commit(result) {
    if (result && result.ok && result.nextState) paperState = result.nextState;
    return result;
  }

  function fillAtPracticePrice(order, price) {
    var result = commit(engine.fillPendingOrder(order.id, price, paperState));
    if (result.ok) {
      // The engine rebuilds a bought position at average cost. Restore its
      // displayed market mark so trading itself cannot change the quote or P&L.
      var marks = {};
      marks[order.symbol] = price;
      savedQuotes[order.symbol] = price;
      commit(engine.markPortfolioToMarket(marks, paperState));
    }
    return result;
  }

  function seedPractice() {
    contestConfig = engine.createContestConfig();
    paperState = engine.createPaperState({ contestId: 'contest_yport_preview', participantId: 'student_yport_07',
      alias: 'YPORT Student 07', benchmarkSymbol: contestConfig.benchmarkSymbol });
    // Preserve the original Port demonstration portfolio and engine actions.
    [
      { symbol: 'AAPL', side: 'buy', type: 'market', quantity: 120, referencePrice: 184.5, fill: 184.5 },
      { symbol: 'NVDA', side: 'buy', type: 'market', quantity: 30, referencePrice: 902, fill: 902 },
      { symbol: 'MSFT', side: 'buy', type: 'market', quantity: 65, referencePrice: 421, fill: 421 },
      { symbol: 'AAPL', side: 'sell', type: 'limit', quantity: 20, referencePrice: 192.4, limitPrice: 192, fill: 193.1 },
      { symbol: 'AMD', side: 'buy', type: 'limit', quantity: 80, referencePrice: 164.2, limitPrice: 162.5 }
    ].forEach(function (draft) {
      var submitted = commit(engine.submitDraftOrder(engine.createOrderDraft(draft), contestConfig, paperState));
      if (submitted.ok && draft.fill) commit(engine.fillPendingOrder(submitted.order.id, draft.fill, paperState));
    });
    commit(engine.markPortfolioToMarket({ AAPL: 191.25, NVDA: 887, MSFT: 436.4 }, paperState));
    commit(engine.setBenchmarkBaseline(500, paperState, { source: 'yport_demo' }));
    commit(engine.markBenchmarkPrice(518.5, paperState, { source: 'yport_demo' }));
  }

  function selectSymbol(symbol) {
    var clean = symbolOf(symbol);
    if (!clean) return;
    selectedSymbol = clean;
    if (typeInput.value === 'limit') limitInput.value = positive(quote(clean).price) ? quote(clean).price.toFixed(2) : '';
    feedback = '';
    feedbackError = false;
    saveState();
    render();
  }

  function renderWatchlist() {
    var symbols = DEFAULT_WATCHLIST.slice();
    if (symbols.indexOf(selectedSymbol) < 0) symbols[symbols.length - 1] = selectedSymbol;
    renderContent('port-stocks-list', symbols.map(function (symbol) {
      var stock = company(symbol), current = quote(symbol);
      return '<button type="button" class="port-stock-row' + (symbol === selectedSymbol ? ' is-selected' : '') +
        '" data-render-key="' + esc(symbol) + '" data-symbol="' + esc(symbol) + '" aria-pressed="' + (symbol === selectedSymbol) + '">' +
        '<span class="port-stock-identity"><strong>' + esc(symbol) + '</strong><small>' + esc(stock.name) + '</small></span>' +
        '<span class="port-stock-price">' + esc(current.price === null ? '—' : current.price.toFixed(2)) + '</span>' +
        '<span class="port-stock-change ' + tone(current.change) + '">' + percent(current.change) + '</span></button>';
    }).join(''));
    renderContent('port-symbol-picker', allSymbols().map(function (symbol) {
      return '<option data-render-key="' + esc(symbol) + '" value="' + esc(symbol) + '">' + esc(symbol + ' · ' + company(symbol).name) + '</option>';
    }).join(''));
    if (pickerSymbol !== selectedSymbol) { byId('port-symbol-picker').value = selectedSymbol; pickerSymbol = selectedSymbol; }
  }

  function renderSummary() {
    var summary = engine.getPortfolioSummary(paperState);
    byId('port-equity').textContent = money(summary.equity);
    byId('port-cash').textContent = money(summary.availableCash);
    byId('port-pnl').textContent = signedMoney(summary.totalPnl);
    byId('port-pnl').className = 'port-summary-value ' + tone(summary.totalPnl);
    byId('port-portfolio-count').textContent = summary.positionsCount + (summary.positionsCount === 1 ? ' holding' : ' holdings');
    byId('port-order-count').textContent = summary.openOrdersCount ? '(' + summary.openOrdersCount + ')' : '';
    byId('port-portfolio-updated').textContent = 'Portfolio updated ' + dateText(paperState.meta && paperState.meta.updatedAt, true);
    byId('port-reserved-cash').textContent = summary.reservedCash ? money(summary.reservedCash) + ' reserved for open orders' : 'No cash reserved';
    if (!demoMode) {
      byId('port-account-label').textContent = serverPlayerName ? serverPlayerName + ' · VIRTUAL ACCOUNT' : 'VIRTUAL ACCOUNT';
      byId('port-data-label').textContent = serverMarket.source === 'local_test_fixture' ? 'TEST QUOTES' : serverMarket.status === 'open' ? 'Alpaca SIP' : serverMarket.status === 'closed' ? 'Market closed' : 'Market feed offline';
      byId('port-data-label').title = marketSessionText();
      byId('port-save-status').textContent = !serverLoaded ? connectionMessage || 'Loading your account…'
        : !serverConnected ? 'Connection interrupted · last saved account' : 'Saved to your student seat';
      if (!serverLoaded) {
        ['port-equity', 'port-cash', 'port-pnl'].forEach(function (id) { byId(id).textContent = '—'; });
        byId('port-portfolio-updated').textContent = 'Waiting for your saved portfolio';
        byId('port-portfolio-count').textContent = '';
        byId('port-reserved-cash').textContent = '';
      }
    }
    if (storageBlocked) {
      ['port-equity', 'port-cash', 'port-pnl'].forEach(function (id) { byId(id).textContent = '—'; });
      byId('port-save-status').textContent = 'Saved portfolio needs attention';
    }
  }

  function availableShares(symbol) {
    var held = position(symbol);
    var pending = engine.getOpenOrders(paperState).reduce(function (total, order) {
      return total + (order.side === 'sell' && order.symbol === symbol ? order.quantity : 0);
    }, 0);
    return Math.max(0, (held ? held.quantity : 0) - pending);
  }

  function updateTicket() {
    root.querySelector('.port-order-ticket').dataset.ticketSide = side;
    var current = quote(selectedSymbol);
    var isLimit = typeInput.value === 'limit';
    var quantity = Number(quantityInput.value);
    var price = isLimit ? Number(limitInput.value) : !demoMode ? (side === 'buy' ? current.ask : current.bid) || current.price : current.price;
    byId('port-limit-field').hidden = !isLimit;
    limitInput.disabled = !isLimit;
    byId('port-ticket-estimate').textContent = positive(price) && Number.isInteger(quantity) && quantity > 0 ? money(price * quantity) : '—';
    byId('port-ticket-resource-label').textContent = side === 'buy' ? 'Available cash' : 'Shares available';
    byId('port-ticket-resource').textContent = !demoMode && !serverLoaded ? '—' : side === 'buy' ? money(paperState.account.availableCash) : String(availableShares(selectedSymbol));
    byId('port-ticket-submit').textContent = 'PLACE ' + side.toUpperCase() + ' ORDER';
    byId('port-ticket-submit').disabled = storageBlocked || !positive(current.price);
    byId('port-ticket-note').textContent = isLimit
      ? 'Practice limit orders wait until their limit can be met at the sample price.'
      : instantFill ? 'Practice orders fill at the displayed sample price.' : 'Practice orders queue for confirmation in Orders.';
    if (!demoMode) {
      var blocked = tradingBlock();
      var locked = requestBusy || !!pendingRequest;
      quantityInput.disabled = locked;
      typeInput.disabled = locked;
      limitInput.disabled = !isLimit || locked;
      root.querySelectorAll('button[data-side]').forEach(function (button) { button.disabled = locked; });
      byId('port-ticket-submit').textContent = requestBusy ? 'SENDING…' : pendingRequest ?
        (pendingRequest.path === '/cancel' ? 'RETRY CANCELLATION' : 'RETRY ' + pendingRequest.body.symbol + ' ' + pendingRequest.body.side.toUpperCase()) : 'PLACE ' + side.toUpperCase() + ' ORDER';
      byId('port-ticket-submit').disabled = requestBusy || (!pendingRequest && !!blocked) || !serverLoaded;
      var rulesText = executionText(isLimit);
      byId('port-ticket-note').textContent = marketSessionText() + ' ' + (pendingRequest
        ? 'The previous request needs confirmation. Retry checks that same request.' : blocked || rulesText);
      byId('port-ticket-note').title = rulesText;
    }
    root.querySelectorAll('button[data-side]').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.side === side)); });
    if (byId('port-ticket-feedback').textContent !== feedback) byId('port-ticket-feedback').textContent = feedback;
    byId('port-ticket-feedback').className = 'port-ticket-feedback' + (feedbackError ? ' is-error' : '');
  }

  function table(headers, rows, label) {
    return '<div class="port-table-wrap"><table class="port-table" aria-label="' + esc(label) + '"><thead><tr>' +
      headers.map(function (header, index) { return '<th scope="col"' + (index ? ' class="port-numeric"' : '') + '>' + header + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  function stockButton(symbol) {
    return '<button class="port-position-button" type="button" data-symbol="' + esc(symbol) + '"><strong>' + esc(symbol) + '</strong><small>' + esc(company(symbol).name) + '</small></button>';
  }

  function renderPositions() {
    var positions = Object.keys(paperState.positions || {}).map(function (symbol) { return paperState.positions[symbol]; });
    if (!positions.length) { renderContent('port-portfolio-positions', '<p class="port-empty">' + (!demoMode && !serverLoaded ? esc(connectionMessage || 'Loading your saved holdings…') : 'Your first filled buy will appear here.') + '</p>'); return; }
    renderContent('port-portfolio-positions', table(['STOCK', 'SHARES', 'AVG COST', 'VALUE', 'P&amp;L'], positions.map(function (held) {
      var value = finite(held.marketValue) ? held.marketValue : held.totalCost;
      var pnl = finite(held.unrealizedPnl) ? held.unrealizedPnl : value - held.totalCost;
      return '<tr data-render-key="' + esc(held.symbol) + '"' + (held.symbol === selectedSymbol ? ' class="is-selected"' : '') + '><td>' + stockButton(held.symbol) + '</td><td class="port-numeric">' +
        esc(held.quantity) + '</td><td class="port-numeric">' + money(held.avgCost) + '</td><td class="port-numeric">' + money(value) +
        '</td><td class="port-numeric ' + tone(pnl) + '">' + signedMoney(pnl) + '</td></tr>';
    }), 'Portfolio positions'));
  }

  function fillable(order) {
    var price = quote(order.symbol).price;
    return positive(price) && (order.type === 'market' || (order.side === 'buy' ? price <= order.limitPrice : price >= order.limitPrice));
  }

  function renderOrders() {
    var orders = engine.getOpenOrders(paperState);
    if (!orders.length) { renderContent('port-portfolio-orders', '<p class="port-empty">No open orders. Completed orders are in History.</p>'); return; }
    renderContent('port-portfolio-orders', table(['STOCK', 'SIDE / TYPE', 'SHARES', 'LIMIT', 'STATUS', 'ACTIONS'], orders.map(function (order) {
      var canFill = demoMode && fillable(order);
      var status = demoMode ? (canFill ? 'Ready to fill' : 'Waiting for limit') : order.cancellationRequestedAt ? 'Cancellation pending' : order.type === 'limit' ? 'Waiting for limit' : 'Waiting for fresh quote';
      return '<tr data-render-key="' + esc(order.id) + '" data-order-id="' + esc(order.id) + '"><td>' + stockButton(order.symbol) + '</td><td class="port-numeric">' + esc(order.side.toUpperCase() + ' / ' + order.type) +
        '</td><td class="port-numeric">' + esc(order.quantity) + '</td><td class="port-numeric">' + money(order.limitPrice) +
        '</td><td class="port-numeric"><span class="port-order-status">' + status + '</span></td>' +
        '<td class="port-numeric"><div class="port-order-actions">' + (canFill ? '<button type="button" data-order-action="fill" data-order-id="' + esc(order.id) + '">Fill practice order</button>' : '') +
        '<button type="button" data-order-action="cancel" data-order-id="' + esc(order.id) + '"' + (!demoMode && (requestBusy || pendingRequest || !serverConnected || order.cancellationRequestedAt) ? ' disabled' : '') + '>' + (order.cancellationRequestedAt ? 'Requested' : 'Cancel') + '</button></div></td></tr>';
    }), 'Open orders'));
  }

  function renderHistory() {
    var orders = paperState.ledger.orders.filter(function (order) { return order.status !== 'pending'; }).slice().reverse();
    var fills = paperState.ledger.fills || [];
    if (!orders.length) { renderContent('port-portfolio-history', '<p class="port-empty">Filled and cancelled orders will appear here.</p>'); return; }
    renderContent('port-portfolio-history', table(['STOCK', 'SIDE', 'SHARES', 'FILL PRICE', 'STATUS', 'TIME'], orders.map(function (order) {
      var fill = fills.find(function (item) { return item.orderId === order.id; });
      return '<tr data-render-key="' + esc(order.id) + '"><td>' + stockButton(order.symbol) + '</td><td class="port-numeric">' + esc(order.side.toUpperCase()) +
        '</td><td class="port-numeric">' + esc(order.quantity) + '</td><td class="port-numeric">' + money(fill && fill.fillPrice) +
        '</td><td class="port-numeric">' + (order.status === 'canceled' ? 'Cancelled' : esc(order.status)) +
        (order.reason ? '<br><small>' + esc(order.reason) + '</small>' : '') +
        '</td><td class="port-numeric">' + esc(dateText(fill && fill.createdAt || order.canceledAt || order.updatedAt || order.createdAt, true)) + '</td></tr>';
    }), 'Trade history'));
  }

  function syncTabs() {
    [['research', researchTab], ['portfolio', activeTab]].forEach(function (group) {
      root.querySelectorAll('[data-' + group[0] + '-tab]').forEach(function (button) {
        var selected = button.getAttribute('data-' + group[0] + '-tab') === group[1];
        button.setAttribute('aria-selected', String(selected));
        button.tabIndex = selected ? 0 : -1;
        byId(button.getAttribute('aria-controls')).hidden = !selected;
      });
    });
    root.querySelectorAll('[data-range]').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.range === chartRange)); });
    root.querySelectorAll('button[data-chart-type]').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.chartType === chartType)); });
  }

  function drawChart() {
    if (researchTab !== 'chart') return;
    var svg = byId('port-chart-svg'), host = byId('port-price-chart');
    var width = host.clientWidth, height = host.clientHeight || 300, current = quote(selectedSymbol).price;
    if (!width) return;
    if (!demoMode) {
      svg.setAttribute('hidden', '');
      var marketChart = byId('port-market-chart-host');
      marketChart.hidden = false;
      if (window.YomamaPortChart) {
        window.YomamaPortChart.render(marketChart, { symbol: selectedSymbol, range: chartRange, type: chartType,
          token: seatToken(), quote: serverConnected && quoteIsFresh(quote(selectedSymbol)) ? quote(selectedSymbol) : null,
          request: function (symbol, range) { return serverRequest('GET', '/chart', { symbol: symbol, range: range }); } });
      } else {
        marketChart.textContent = 'Chart unavailable. Reload the page to try again.';
      }
      chartGeometry = null;
      return;
    }
    byId('port-chart-tooltip').hidden = true;
    if (!positive(current)) { svg.innerHTML = '<text x="20" y="40" fill="currentColor">No practice price available</text>'; chartGeometry = null; return; }
    var left = width < 340 ? 47 : 56, right = 18, top = 18, bottom = 32;
    var range = { '1D': { span: .025, labels: ['09:30', '11:00', '12:30', '14:00', '16:00'] },
      '1W': { span: .07, labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] },
      '1M': { span: .14, labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'] },
      '3M': { span: .20, labels: ['Month 1', 'Month 2', 'Month 3'] },
      '1Y': { span: .30, labels: ['Jan', 'Apr', 'Jul', 'Oct', 'Dec'] },
      '5Y': { span: .55, labels: ['Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5'] } }[chartRange];
    var seed = selectedSymbol.split('').reduce(function (sum, character) { return sum + character.charCodeAt(0); }, 0);
    // A deliberately illustrative preview chart, not invented historical quotes.
    // The last point always agrees with the saved practice price used by orders.
    var samples = [], count = 91;
    for (var i = 0; i < count; i += 1) {
      var progress = i / (count - 1), fade = Math.sin(Math.PI * progress);
      var wave = (Math.sin(i * .39 + seed) * .10 + Math.sin(i * 1.73 + seed) * .035) * fade;
      samples.push(current * (1 - range.span + range.span * progress + range.span * wave));
    }
    var low = Math.min.apply(null, samples), high = Math.max.apply(null, samples), padding = (high - low) * .13;
    low -= padding; high += padding;
    var x = function (index) { return left + index / (count - 1) * (width - left - right); };
    var y = function (value) { return top + (high - value) / (high - low) * (height - top - bottom); };
    var path = samples.map(function (value, index) { return (index ? 'L' : 'M') + x(index).toFixed(2) + ',' + y(value).toFixed(2); }).join(' ');
    var pieces = ['<title>' + esc(selectedSymbol + ' illustrative ' + chartRange + ' price history, ending at ' + money(current)) + '</title>',
      '<defs><linearGradient id="port-chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ffb000" stop-opacity=".19"/><stop offset="100%" stop-color="#ffb000" stop-opacity=".01"/></linearGradient></defs>'];
    for (var tick = 0; tick < 5; tick += 1) {
      var value = low + (high - low) * tick / 4, yy = y(value);
      pieces.push('<line class="port-chart-gridline" x1="' + left + '" x2="' + (width - right) + '" y1="' + yy + '" y2="' + yy + '"/><text class="port-chart-axis" x="' + (left - 9) + '" y="' + (yy + 4) + '" text-anchor="end">' + (high - low < 3 ? value.toFixed(1) : Math.round(value).toLocaleString('en-US')) + '</text>');
    }
    var labels = width < 380 ? [range.labels[0], range.labels[Math.floor(range.labels.length / 2)], range.labels[range.labels.length - 1]] : range.labels;
    labels.forEach(function (label, index) {
      var xx = left + index / (labels.length - 1) * (width - left - right);
      pieces.push('<line class="port-chart-gridline" x1="' + xx + '" x2="' + xx + '" y1="' + top + '" y2="' + (height - bottom) + '"/><text class="port-chart-axis" x="' + xx + '" y="' + (height - 9) + '" text-anchor="' + (index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle') + '">' + label + '</text>');
    });
    pieces.push('<path d="' + path + ' L' + x(count - 1) + ',' + (height - bottom) + ' L' + left + ',' + (height - bottom) + ' Z" fill="url(#port-chart-fill)"/>',
      '<path class="port-chart-line" d="' + path + '"/><circle class="port-chart-end" cx="' + x(count - 1) + '" cy="' + y(current) + '" r="3"/>',
      '<line id="port-chart-guide" class="port-chart-guide" y1="' + top + '" y2="' + (height - bottom) + '" visibility="hidden"/>');
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.setAttribute('aria-label', selectedSymbol + ' illustrative price chart, ' + chartRange + '. Ends at ' + money(current) + '.');
    svg.innerHTML = pieces.join('');
    chartGeometry = { samples: samples, left: left, right: width - right, width: width };
  }

  function render() {
    var stock = company(selectedSymbol), current = quote(selectedSymbol);
    byId('port-selected-symbol').textContent = selectedSymbol;
    byId('port-company-name').textContent = stock.name;
    byId('port-selected-price').textContent = money(current.price);
    byId('port-selected-change').textContent = percent(current.change);
    byId('port-selected-change').className = tone(current.change);
    byId('port-ticket-symbol').textContent = selectedSymbol;
    byId('port-ticket-company').textContent = stock.name;
    if (!demoMode) {
      var timestamp = finite(current.timestamp) ? current.timestamp * 1000 : current.timestamp;
      var feedLabel = serverMarket.source === 'local_test_fixture' ? 'Test fixture · simulated' : 'Alpaca SIP';
      byId('port-quote-meta').textContent = current.price ? feedLabel + ' · ' + (quoteIsFresh(current) ? 'Quote ' : 'Last quote ') + dateText(timestamp, true, true)
        : serverMarket.message || 'Waiting for market prices…';
    }
    renderSummary(); renderWatchlist(); renderPositions(); renderOrders(); renderHistory();
    updateTicket(); syncTabs(); drawChart();
  }

  function submitOrder(event) {
    event.preventDefault();
    if (storageBlocked) return;
    if (!demoMode && pendingRequest) { sendPendingRequest(); return; }
    if (!demoMode && (requestBusy || tradingBlock())) return;
    var quantity = Number(quantityInput.value), current = quote(selectedSymbol).price;
    feedbackError = true;
    if (!Number.isInteger(quantity) || quantity <= 0) { feedback = 'Enter a whole number of shares greater than zero.'; updateTicket(); return; }
    if (!positive(current)) { feedback = 'A practice price is not available for this stock.'; updateTicket(); return; }
    if (side === 'sell' && quantity > availableShares(selectedSymbol)) { feedback = 'Only ' + availableShares(selectedSymbol) + ' shares are available to sell. Check your open sell orders.'; updateTicket(); return; }
    if (!demoMode) {
      if (typeInput.value === 'limit' && !positive(Number(limitInput.value))) {
        feedback = 'Enter a limit price greater than zero.'; updateTicket(); return;
      }
      pendingRequest = { token: seatToken(), path: '/order', body: {
        accountId: paperState.accountId, clientOrderId: newRequestId(), symbol: selectedSymbol,
        side: side, type: typeInput.value, quantity: quantity
      } };
      if (typeInput.value === 'limit') pendingRequest.body.limitPrice = Number(limitInput.value);
      savePendingRequest(); sendPendingRequest(); return;
    }
    var draft = engine.createOrderDraft({ symbol: selectedSymbol, side: side, type: typeInput.value,
      quantity: quantity, referencePrice: current, limitPrice: typeInput.value === 'limit' ? Number(limitInput.value) : undefined, session: 'regular' });
    var result = engine.submitDraftOrder(draft, contestConfig, paperState);
    if (!result.ok) { feedback = (result.errors || ['Order could not be placed.']).join(' '); updateTicket(); return; }
    commit(result);
    var order = result.order;
    if (fillable(order) && (order.type === 'limit' || instantFill)) {
      var filled = fillAtPracticePrice(order, current);
      if (filled.ok) {
        feedbackError = false;
        feedback = (side === 'buy' ? 'Bought ' : 'Sold ') + quantity + ' ' + selectedSymbol + ' at ' + money(current) + ' · practice fill.';
        activeTab = 'positions';
      } else {
        // The successful submission owns reserved cash even if filling fails.
        // Keep it visible and cancellable instead of losing that intermediate state.
        feedback = 'Order queued. ' + (filled.errors || []).join(' '); activeTab = 'orders';
      }
    } else {
      feedbackError = false; feedback = 'Order placed. View or cancel it in Orders.'; activeTab = 'orders';
    }
    saveState(); render();
  }

  root.addEventListener('click', function (event) {
    var stock = event.target.closest('[data-symbol]');
    if (stock) { selectSymbol(stock.dataset.symbol); return; }
    var sideButton = event.target.closest('button[data-side]');
    if (sideButton) { side = sideButton.dataset.side; feedback = ''; feedbackError = false; updateTicket(); return; }
    var tab = event.target.closest('[role="tab"]');
    if (tab) {
      if (tab.dataset.researchTab) researchTab = tab.dataset.researchTab;
      else activeTab = tab.dataset.portfolioTab;
      syncTabs(); drawChart(); saveState(); return;
    }
    var range = event.target.closest('[data-range]');
    if (range) { chartRange = range.dataset.range; syncTabs(); drawChart(); saveState(); return; }
    var chartStyle = event.target.closest('button[data-chart-type]');
    if (chartStyle) { chartType = chartStyle.dataset.chartType; syncTabs(); drawChart(); saveState();
      var menu = chartStyle.closest('details'); if (menu) menu.open = false; return; }
    if (event.target.closest('[data-chart-fit]')) { if (window.YomamaPortChart) window.YomamaPortChart.fit(byId('port-market-chart-host'));
      var fitMenu = event.target.closest('details'); if (fitMenu) fitMenu.open = false; return; }
    var action = event.target.closest('[data-order-action]');
    if (!action || storageBlocked) return;
    var order = engine.getOpenOrders(paperState).find(function (item) { return item.id === action.dataset.orderId; });
    if (!order) return;
    if (!demoMode) {
      if (action.dataset.orderAction !== 'cancel' || requestBusy || pendingRequest || !serverConnected || order.cancellationRequestedAt) return;
      pendingRequest = { token: seatToken(), path: '/cancel', body: {
        accountId: paperState.accountId, clientOrderId: newRequestId(), orderId: order.id
      } };
      savePendingRequest(); sendPendingRequest(); return;
    }
    var price = quote(order.symbol).price;
    var result = action.dataset.orderAction === 'cancel' ? commit(engine.cancelPendingOrder(order.id, paperState)) : fillAtPracticePrice(order, price);
    feedbackError = !result.ok;
    feedback = result.ok ? (action.dataset.orderAction === 'cancel' ? 'Order cancelled.' : 'Practice order filled at ' + money(price) + '.') : (result.errors || []).join(' ');
    saveState(); render();
  });
  root.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      var menu = root.querySelector('.port-chart-menu[open]');
      if (menu) { event.preventDefault(); menu.open = false; menu.querySelector('summary').focus(); return; }
    }
    if (!event.target.matches('[role="tab"]') || ['ArrowLeft', 'ArrowRight', 'Home', 'End'].indexOf(event.key) < 0) return;
    var tabs = Array.from(event.target.parentElement.querySelectorAll('[role="tab"]'));
    var index = tabs.indexOf(event.target);
    var next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault(); tabs[next].click(); tabs[next].focus();
  });
  byId('port-symbol-picker').addEventListener('change', function () { selectSymbol(this.value); });
  typeInput.addEventListener('change', function () {
    if (this.value === 'limit' && !limitInput.value) limitInput.value = positive(quote(selectedSymbol).price) ? quote(selectedSymbol).price.toFixed(2) : '';
    feedback = ''; feedbackError = false; updateTicket();
  });
  [quantityInput, limitInput].forEach(function (input) { input.addEventListener('input', function () { feedback = ''; feedbackError = false; updateTicket(); }); });
  byId('port-trade-ticket-form').addEventListener('submit', submitOrder);
  byId('port-price-chart').addEventListener('pointermove', function (event) {
    if (!chartGeometry) return;
    var rect = this.getBoundingClientRect(), x = Math.max(chartGeometry.left, Math.min(chartGeometry.right, event.clientX - rect.left));
    var index = Math.round((x - chartGeometry.left) / (chartGeometry.right - chartGeometry.left) * (chartGeometry.samples.length - 1));
    var tooltip = byId('port-chart-tooltip'), guide = byId('port-chart-guide');
    tooltip.textContent = money(chartGeometry.samples[index]) + ' · illustrative'; tooltip.hidden = false;
    tooltip.style.left = Math.max(4, Math.min(x + 10, chartGeometry.width - tooltip.offsetWidth - 6)) + 'px'; tooltip.style.top = '8px';
    guide.setAttribute('x1', x); guide.setAttribute('x2', x); guide.setAttribute('visibility', 'visible');
  });
  byId('port-price-chart').addEventListener('pointerleave', function () {
    byId('port-chart-tooltip').hidden = true; var guide = byId('port-chart-guide'); if (guide) guide.setAttribute('visibility', 'hidden');
  });

  if (demoMode) {
    byId('port-chart-controls').hidden = true;
    root.querySelectorAll('[data-range]').forEach(function (button) { button.textContent = button.dataset.range;
      button.setAttribute('aria-label', button.dataset.range); button.title = 'Illustrative ' + button.dataset.range + ' history'; });
    byId('port-account-label').textContent = 'SAMPLE · THIS BROWSER';
    byId('port-data-label').textContent = 'Practice prices';
    byId('port-quote-meta').textContent = 'Practice price · not a live quote';
    byId('port-chart-source').textContent = 'Illustrative history · USD';
    if (!loadState()) { seedPractice(); if (!storageBlocked) saveState(); }
  } else {
    paperState = emptyServerState();
    loadServerPreferences();
    byId('port-chart-source').textContent = 'Alpaca SIP · USD · ET';
  }
  render();
  if (window.ResizeObserver) new ResizeObserver(drawChart).observe(byId('port-price-chart'));
  else window.addEventListener('resize', drawChart);
  window.addEventListener('storage', function (event) {
    if (demoMode && event.key === STORAGE_KEY && event.newValue && loadState()) { feedback = 'Portfolio updated from another tab.'; feedbackError = false; render(); }
    if (!demoMode && event.key === 'yomama_session_v1') refreshPortfolio();
  });
  if (!demoMode) {
    refreshPortfolio();
    setInterval(function () { if (!document.hidden) refreshPortfolio(); }, 2000);
    // Disable a stale ticket even between polls or after a sleeping tab resumes.
    setInterval(function () { if (!document.hidden) updateTicket(); }, 1000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { updateTicket(); refreshPortfolio(); } });
    window.addEventListener('focus', refreshPortfolio);
  }
})();
