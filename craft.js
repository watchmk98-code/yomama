/* Crafting is server-authoritative. This page owns selection and the catalog layout. */
(function () {
  'use strict';
  var grid = document.getElementById('craft-grid');
  if (!grid) return;
  var dialog = document.getElementById('craft-dialog');
  var content = document.getElementById('econ-craft');
  var notice = document.getElementById('craft-notice');
  var submit = document.getElementById('craft-submit');
  var snapshot = null;
  var selectedId = null;
  var busy = false;
  var connected = true;
  var generation = 0;
  var refreshing = null;
  var lastOp = null;
  var gridKey = '';
  var session = {};
  var SUPPLY_ART = ['wooden_boards','fiber_bundles','metal_sheets','copper_stock','battery_cells','solar_cells','glass_panels','rubber_sheets','plastic_casings','circuit_boards','insulation','packaging'];
  try { session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {}; } catch (_) {}

  function el(id) { return document.getElementById(id); }
  function esc(value) { return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function amount(value) { return (Number(value) || 0).toLocaleString('en-US', {maximumFractionDigits:1}); }
  function money(value) { return amount(Math.round(Number(value) || 0)) + ' YM'; }
  function catalog() { return snapshot && snapshot.crafting && snapshot.crafting.items || []; }
  function selected() { return catalog().find(function (item) { return item.id === selectedId; }); }
  function status(message, tone) { el('craft-status').textContent = message || ''; el('craft-status').dataset.tone = tone || 'success'; }
  function sprite(node, index) {
    node.style.cssText = spriteStyle('items', index);
  }
  function spriteStyle(kind, index) {
    var sheet = window.YomamaCraftArt[kind];
    var rect = sheet.rects[Math.max(0, Math.min(sheet.rects.length - 1, Number(index) || 0))];
    var size = Math.max(rect[2], rect[3]);
    return '--sprite-ratio:' + rect[2] / rect[3] + ';--sprite-width:' + rect[2] / size * 100 + '%;--sprite-height:' + rect[3] / size * 100 + '%;' +
      '--sprite-sheet-width:' + sheet.width / rect[2] * 100 + '%;--sprite-sheet-height:' + sheet.height / rect[3] * 100 + '%;' +
      '--sprite-x:' + rect[0] / (sheet.width - rect[2]) * 100 + '%;--sprite-y:' + rect[1] / (sheet.height - rect[3]) * 100 + '%;';
  }
  function requestId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    var bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes);
    return Array.from(bytes, function (n) { return n.toString(16).padStart(2, '0'); }).join('');
  }
  function request(method, path, body) {
    var options = {method:method, headers:{}};
    if (body) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(Object.assign({}, body, {token:session.token || ''})); }
    return fetch(path, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var error = new Error(data.why || data.error || 'The request could not be completed.');
          error.status = response.status; throw error;
        }
        return data;
      });
    });
  }
  function renderHeader() {
    var host = document.querySelector('.right-meta');
    var chip = el('game-cash-chip');
    if (!chip) { chip = document.createElement('span'); chip.id = 'game-cash-chip'; chip.className = 'chip amber'; host.prepend(chip); }
    chip.textContent = session.name || snapshot.name || 'PLAYER';
    el('craft-wallet').textContent = money(snapshot.cash);
    var ticker = el('ticker');
    if (ticker && snapshot.tickerLines && snapshot.tickerLines.length) {
      ticker.innerHTML = '<span class="ticker-item">' + esc(snapshot.tickerLines.join(' · ')) + '</span>';
    }
  }
  function renderGrid() {
    var items = catalog();
    var key = items.map(function (item) { return item.id + ':' + item.name + ':' + item.iconIndex; }).join('|');
    // Keep card elements stable so state polls never steal keyboard focus.
    if (gridKey !== key) {
      gridKey = key; grid.replaceChildren();
      items.forEach(function (item) {
        var button = document.createElement('button'); button.type = 'button'; button.className = 'craft-item';
        button.id = 'craft-item-' + item.id; button.dataset.craftItem = item.id;
        button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-expanded', 'false');
        var icon = document.createElement('span'); icon.className = 'craft-sprite'; icon.setAttribute('aria-hidden', 'true'); sprite(icon, item.iconIndex);
        var name = document.createElement('span'); name.className = 'craft-item-name'; name.textContent = item.name;
        button.append(icon, name); grid.appendChild(button);
      });
    }
    fit();
  }
  function fit() {
    var count = catalog().length;
    if (!count || !grid.clientWidth || !grid.clientHeight) return;
    var scroll = innerWidth < 1000 || innerHeight < 600;
    grid.dataset.scroll = String(scroll);
    var width = grid.clientWidth, height = grid.clientHeight;
    var gap = parseFloat(getComputedStyle(grid).columnGap) || 8;
    var best = null;
    // Choose the arrangement that gives all 30 items the largest complete icons.
    // Small screens keep the same catalog in one vertically scrolling grid.
    for (var columns = 3; columns <= 10; columns += 1) {
      var rows = Math.ceil(count / columns);
      var cellWidth = (width - (columns - 1) * gap) / columns;
      if (cellWidth < (scroll ? 98 : 116)) continue;
      var label = cellWidth < 140 ? 18 : cellWidth < 180 ? 20 : 22;
      var cellHeight = scroll ? Math.min(180, cellWidth - 16) + label * 2.1 + 20 : (height - (rows - 1) * gap) / rows;
      var art = Math.floor(Math.min(260, cellWidth - 16, cellHeight - label * 2.1 - 20));
      if (!best || art > best.art) best = {columns:columns, rows:rows, label:label, height:cellHeight, art:art};
    }
    if (!best) return;
    grid.style.setProperty('--craft-columns', String(best.columns));
    grid.style.setProperty('--craft-rows', String(best.rows));
    grid.style.setProperty('--craft-label', best.label + 'px');
    // Measure full names, including longer three-line labels, before sizing art.
    var labelHeight = Math.max.apply(null, Array.from(grid.querySelectorAll('.craft-item-name')).map(function (name) { return name.getBoundingClientRect().height; }));
    if (scroll) best.height = best.art + labelHeight + 20;
    else best.art = Math.min(best.art, Math.floor(best.height - labelHeight - 20));
    grid.style.setProperty('--craft-cell-height', Math.ceil(best.height) + 'px');
    grid.style.setProperty('--craft-art', Math.max(24, best.art) + 'px');
  }
  function ingredientIcon(row) {
    if (row.kind === 'supply') {
      var index = SUPPLY_ART.indexOf(row.id);
      return '<span class="craft-supply-icon" aria-hidden="true" style="' + spriteStyle('supplies', index) + '"></span>';
    }
    var id = row.id === 'cannery_preserves' ? 'cannery_canned_goods' : row.id;
    return '<img src="./assets/game-art/goods/' + encodeURIComponent(id) + '.png" width="64" height="64" alt="" aria-hidden="true">';
  }
  function renderDetail() {
    var item = selected(); if (!item) return;
    var focusId = dialog.contains(document.activeElement) ? document.activeElement.id : '';
    var scroll = dialog.scrollTop;
    el('craft-dialog-title').textContent = item.name;
    sprite(el('craft-large-icon'), item.iconIndex);
    el('craft-makes').textContent = 'Makes 1 ' + item.name;
    el('craft-owned').textContent = 'Owned: ' + amount(item.owned);
    el('craft-ingredient-rows').innerHTML = item.ingredients.map(function (row) {
      var enough = row.available >= row.quantity;
      var source = row.source + (row.kind === 'energy' ? ' · Energy' : row.kind === 'service' ? ' · Service' : '');
      var buy = row.kind === 'supply' && row.missing > 0 ? '<button id="craft-buy-' + esc(row.id) + '" class="craft-buy" type="button" data-craft-buy="' + esc(row.id) + '"' + (busy || !connected || snapshot.paused || !row.canBuy ? ' disabled' : '') + ' aria-label="Buy ' + amount(row.missing) + ' ' + esc(row.name) + ' for ' + money(row.buyCost) + '">Buy ' + amount(row.missing) + ' · ' + money(row.buyCost) + '</button>' + (!row.canBuy ? '<small class="craft-ingredient-source">Need ' + money(row.buyCost) + '</small>' : '') : '';
      return '<tr><td><div class="craft-ingredient">' + ingredientIcon(row) + '<div class="craft-ingredient-info"><span class="craft-ingredient-name">' + esc(row.name) + '</span><span class="craft-ingredient-source">' + esc(source) + '</span>' + (row.reserved ? '<span class="craft-ingredient-reserved">' + amount(row.reserved) + ' saved for deliveries</span>' : '') + buy + '</div></div></td><td>' + amount(row.quantity) + '</td><td class="' + (enough ? 'craft-have-enough' : 'craft-have-missing') + '" aria-label="' + amount(row.available) + ' available">' + amount(row.available) + '</td></tr>';
    }).join('');
    submit.disabled = busy || !connected || !!snapshot.paused || !item.canCraft;
    submit.setAttribute('aria-busy', String(busy));
    el('craft-reason').textContent = !connected ? 'Reconnect to check your ingredients.' : snapshot.paused ? 'Your teacher has paused the class.' : !item.canCraft ? item.why || 'Gather the missing ingredients to craft this item.' : '';
    if (focusId) {
      var target = el(focusId);
      if (target && !target.disabled) target.focus({preventScroll:true});
      else if (dialog.open && !dialog.contains(document.activeElement)) el('craft-close').focus({preventScroll:true});
    }
    dialog.scrollTop = scroll;
  }
  function apply(data) {
    snapshot = data; connected = true;
    if (data.token && !session.token) {
      session = {token:data.token, name:data.name || 'PLAYER', code:data.code || ''};
      try { localStorage.setItem('yomama_session_v1', JSON.stringify(session)); } catch (_) {}
    }
    content.setAttribute('aria-busy', 'false');
    notice.textContent = !data.crafting || !data.crafting.enabled ? 'Crafting is not available for this class yet.' : data.paused ? 'Your teacher has paused the class.' : '';
    renderHeader(); renderGrid(); if (dialog.open) renderDetail();
    window.dispatchEvent(new CustomEvent('yomama:econ', {detail:data}));
  }
  function refresh() {
    if (busy || refreshing) return refreshing || Promise.resolve();
    var version = generation;
    refreshing = request('GET', '/api/game/econ/state?token=' + encodeURIComponent(session.token || '')).then(function (data) {
      if (version === generation && !busy) apply(data);
    }).catch(function (error) {
      if (version !== generation) return;
      connected = false; content.setAttribute('aria-busy', 'false');
      notice.textContent = error.status === 401 || error.status === 403 ? error.message : 'Cannot reach your class. Reconnecting…';
      if (dialog.open) renderDetail();
    }).finally(function () { refreshing = null; });
    return refreshing;
  }
  function openItem(id) {
    selectedId = id; status(''); renderDetail();
    Array.from(grid.children).forEach(function (card) { card.setAttribute('aria-expanded', String(card.dataset.craftItem === id)); });
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
  }
  function perform(body, label) {
    if (busy || !snapshot || snapshot.paused) return;
    var key = body.action === 'buy_supply' ? 'buy:' + body.supplyId : 'craft:' + body.itemId;
    var operation = lastOp && lastOp.key === key ? lastOp : {key:key, body:Object.assign({}, body, {requestId:requestId(), revision:snapshot.crafting.revision})};
    lastOp = operation; busy = true; generation += 1;
    status(body.action === 'buy_supply' ? 'Buying supplies…' : 'Crafting…', 'pending'); renderDetail();
    request('POST', '/api/game/craft', operation.body).then(function (data) {
      lastOp = null; apply(data); status(label, 'success');
    }).catch(function (error) {
      // A lost response can be retried with the same ID without spending twice.
      if (error.status && error.status < 500) lastOp = null;
      status(error.status ? error.message : 'Could not confirm the request. Try again to check it safely.', 'error');
    }).finally(function () { busy = false; renderDetail(); refresh(); });
  }
  grid.addEventListener('click', function (event) {
    var card = event.target.closest('[data-craft-item]'); if (card) openItem(card.dataset.craftItem);
  });
  el('craft-close').addEventListener('click', function () { dialog.close(); });
  dialog.addEventListener('close', function () {
    Array.from(grid.children).forEach(function (card) { card.setAttribute('aria-expanded', 'false'); });
    var opener = el('craft-item-' + selectedId); if (opener && !opener.hidden) opener.focus({preventScroll:true});
  });
  dialog.addEventListener('click', function (event) {
    var button = event.target.closest('[data-craft-buy]'); if (!button || button.disabled || busy) return;
    var item = selected(); if (!item) return;
    var row = item.ingredients.find(function (ingredient) { return ingredient.id === button.dataset.craftBuy; });
    if (!row || !row.canBuy || row.missing <= 0) return;
    perform({action:'buy_supply', supplyId:row.id, quantity:row.missing}, 'Bought ' + amount(row.missing) + ' ' + row.name + '.');
  });
  submit.addEventListener('click', function () {
    var item = selected(); if (!item || submit.disabled) return;
    perform({itemId:item.id}, 'Crafted ' + item.name + '.');
  });
  var resizeFrame;
  function onResize() { cancelAnimationFrame(resizeFrame); resizeFrame = requestAnimationFrame(fit); }
  if (window.ResizeObserver) new ResizeObserver(onResize).observe(grid);
  window.addEventListener('resize', onResize);
  if (document.fonts) document.fonts.ready.then(onResize);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
  request('POST', '/api/game/econ/login', {}).then(apply).catch(function () { return refresh(); }).finally(function () {
    setInterval(function () { if (!document.hidden) refresh(); }, 15000);
  });
  window.YomamaCraft = {refresh:refresh, state:function () { return snapshot; }};
}());
