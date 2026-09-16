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
  var section = 'items';
  var session = {};
  try { session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {}; } catch (_) {}

  function el(id) { return document.getElementById(id); }
  function esc(value) { return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function amount(value) { return (Number(value) || 0).toLocaleString('en-US', {maximumFractionDigits:1}); }
  function money(value) { return amount(Math.round(Number(value) || 0)) + ' YM'; }
  function pilotEnabled() { return !!(snapshot && snapshot.crafting && snapshot.crafting.pilot && snapshot.crafting.pilot.enabled); }
  function assetEffects(item) {
    var labels = {speedPercent:'production speed', costReductionPercent:'processing cost', pricePercent:'sale price', storagePercent:'product storage'};
    return Object.keys(item.effects || {}).map(function (key) { return (key === 'costReductionPercent' ? '−' : '+') + item.effects[key] + '% ' + labels[key]; }).join(' · ');
  }
  function catalog() {
    if (!snapshot || !snapshot.crafting) return [];
    if (section === 'tangible' || section === 'intangible') return snapshot.crafting.businessAssets.filter(function (item) { return item.assetType === section; });
    return snapshot.crafting[section] || [];
  }
  function selected() { return catalog().find(function (item) { return item.id === selectedId; }); }
  function status(message, tone) { el('craft-status').textContent = message || ''; el('craft-status').dataset.tone = tone || 'success'; }
  function sprite(node, index, item) {
    var goodsIcon = section === 'supplies' && item && item.id.indexOf('craft_') === 0;
    node.classList.toggle('craft-sprite-good', !!goodsIcon);
    if (goodsIcon) {
      var goodsId = item.id.indexOf('craft_input_') === 0 ? item.id.slice(12) : item.id.slice(6);
      if (goodsId === 'cannery_preserves') goodsId = 'cannery_canned_goods';
      node.style.cssText = 'background-image:url("./assets/game-art/goods/' + encodeURIComponent(goodsId) + '.png")';
      node.textContent = '';
      return;
    }
    var style = spriteStyle(section === 'tangible' || section === 'intangible' ? 'businessAssets' : section, index);
    node.style.cssText = style;
    node.textContent = style ? '' : '◇';
  }
  function spriteStyle(kind, index) {
    var sheets = window.YomamaCraftArt[kind];
    if (!Array.isArray(sheets)) sheets = [sheets];
    var sheet = sheets.find(function (entry) { return index >= (entry.start || 0) && index < (entry.start || 0) + entry.rects.length; });
    if (!sheet) return '';
    var rect = sheet.rects[index - (sheet.start || 0)];
    var size = Math.max(rect[2], rect[3]);
    return '--sprite-image:url("' + sheet.src + '");--sprite-ratio:' + rect[2] / rect[3] + ';--sprite-width:' + rect[2] / size * 100 + '%;--sprite-height:' + rect[3] / size * 100 + '%;' +
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
    el('game-hud').innerHTML = window.YomamaEcon.resourceBar(snapshot);
    el('craft-catalog-count').textContent = catalog().length + ' items';
    var ticker = el('ticker');
    if (ticker && snapshot.tickerLines && snapshot.tickerLines.length) {
      ticker.innerHTML = '<span class="ticker-item">' + esc(snapshot.tickerLines.join(' · ')) + '</span>';
    }
  }
  function renderGrid() {
    var items = catalog();
    var key = items.map(function (item) { return item.id + ':' + item.name + ':' + item.iconIndex + ':' + !!item.pilot; }).join('|');
    // Keep card elements stable so state polls never steal keyboard focus.
    if (gridKey !== key) {
      gridKey = key; grid.replaceChildren();
      items.forEach(function (item, index) {
        var button = document.createElement('button'); button.type = 'button'; button.className = 'craft-item';
        button.id = 'craft-item-' + item.id; button.dataset.craftItem = item.id;
        if (item.assetType) button.dataset.assetType = item.assetType;
        if (item.pilot) button.dataset.pilot = 'true';
        button.title = item.name; button.setAttribute('aria-label', item.name);
        button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-expanded', 'false');
        var icon = document.createElement('span'); icon.className = 'craft-sprite'; icon.setAttribute('aria-hidden', 'true'); sprite(icon, section === 'supplies' ? index : item.iconIndex, item);
        var name = document.createElement('span'); name.className = 'craft-item-name'; name.textContent = item.name;
        button.append(icon, name); grid.appendChild(button);
      });
    }
    items.forEach(function (item) {
      var card = document.getElementById('craft-item-' + item.id);
      if (card) {
        card.classList.toggle('craft-item-pilot', !!(item.pilot && item.unlocked));
        card.classList.toggle('craft-item-crafted', !!item.craftedOnce);
        card.classList.toggle('craft-item-building-locked', !!item.buildingLocked);
        card.classList.toggle('craft-item-unavailable', !!(item.pilot && item.available === false));
        card.title = item.available === false ? item.name + ' · Not available yet' : item.buildingLocked ? item.name + ' · Build required businesses' : item.name;
      }
    });
    grid.dataset.section = section;
    el('craft-intro-text').textContent = section === 'items' ? 'Three special products per building are available. The rest are grayed out.' : section === 'supplies' ? 'Buy materials for special products here or in a product’s recipe.' : 'Buy assets here, then assign three to a building on Build.';
    fit();
  }
  function fit() {
    if (section !== 'items') return;
    var count = catalog().length;
    if (!count || !grid.clientWidth || !grid.clientHeight) return;
    var width = grid.clientWidth, height = grid.clientHeight;
    var gap = width < 700 || height < 350 ? 2 : 4;
    var best = null;
    // Maximize icon size while keeping the complete catalog on one screen.
    // Names remain available on hover, to assistive technology, and in dialogs.
    for (var columns = 2; columns <= Math.min(40, count); columns += 1) {
      var rows = Math.ceil(count / columns);
      var cellWidth = (width - (columns - 1) * gap) / columns;
      var cellHeight = (height - (rows - 1) * gap) / rows;
      var art = Math.floor(Math.min(cellWidth - 8, cellHeight - 8));
      if (!best || art > best.art) best = {columns:columns, rows:rows, art:art};
    }
    if (!best) return;
    grid.dataset.labels = 'false';
    grid.style.setProperty('--craft-gap', gap + 'px');
    grid.style.setProperty('--craft-columns', String(best.columns));
    grid.style.setProperty('--craft-rows', String(best.rows));
    grid.style.setProperty('--craft-art', Math.max(1, best.art) + 'px');
  }
  function ingredientIcon(row) {
    if (row.kind === 'crafted') {
      var product = snapshot.crafting.items.find(function (item) { return item.id === row.id; });
      return '<span class="craft-supply-icon" aria-hidden="true" style="' + esc(spriteStyle('items', product.iconIndex)) + '"></span>';
    }
    if (row.kind === 'supply') {
      var index = snapshot.crafting.supplies.findIndex(function (supply) { return supply.id === row.id; });
      return '<span class="craft-supply-icon" aria-hidden="true" style="' + esc(spriteStyle('supplies', index)) + '"></span>';
    }
    var id = row.id === 'cannery_preserves' ? 'cannery_canned_goods' : row.id;
    return '<img src="./assets/game-art/goods/' + encodeURIComponent(id) + '.png" width="64" height="64" alt="" aria-hidden="true">';
  }
  function renderDetail() {
    var item = selected(); if (!item) return;
    var focusId = dialog.contains(document.activeElement) ? document.activeElement.id : '';
    var scroll = dialog.scrollTop;
    el('craft-dialog-title').textContent = item.name;
    sprite(el('craft-large-icon'), section === 'supplies' ? catalog().findIndex(function (row) { return row.id === item.id; }) : item.iconIndex, item);
    var asset = !!item.assetType;
    var supply = section === 'supplies';
    dialog.dataset.assetType = item.assetType || '';
    dialog.dataset.pilot = String(!!item.pilot);
    dialog.querySelector('.craft-ingredients').hidden = asset || supply;
    el('craft-owned').hidden = asset;
    submit.hidden = asset;
    el('craft-asset-detail').hidden = !asset;
    var pilotDetail = el('craft-pilot-detail');
    if (!pilotDetail) { pilotDetail = document.createElement('div'); pilotDetail.id = 'craft-pilot-detail'; el('craft-makes').after(pilotDetail); }
    pilotDetail.hidden = !item.pilot || asset;
    submit.textContent = 'CRAFT';
    if (supply) {
      pilotDetail.hidden = true;
      el('craft-makes').textContent = 'Basic crafting supply';
      el('craft-owned').textContent = 'Owned: ' + amount(item.quantity);
      el('craft-asset-detail').hidden = true;
      submit.hidden = false;
      submit.textContent = 'BUY 1 · ' + money(item.unitPrice);
      submit.disabled = busy || !connected || !!snapshot.paused || snapshot.cash < item.unitPrice;
      el('craft-reason').textContent = snapshot.paused ? 'Your teacher has paused the class.' : !connected ? 'Reconnect to buy supplies.' : snapshot.cash < item.unitPrice ? 'Need ' + money(item.unitPrice) + '.' : '';
      if (dialog.open && window.YomamaCraftFitDialog) window.YomamaCraftFitDialog.fit();
      return;
    }
    if (asset) {
      el('craft-makes').textContent = item.businessName;
      el('craft-asset-detail').innerHTML = '<p class="asset-kind">' + (item.assetType === 'tangible' ? 'Tangible asset · Equipment' : 'Intangible asset · Software or rights') + '</p><p><strong>' + esc(item.accounting) + '</strong> spreads the recorded cost over the asset’s useful life.</p><p class="asset-pending">Asset preview · Recipe, value and useful life are not set yet. No costs or bonuses are applied.</p>';
      el('craft-reason').textContent = '';
      submit.disabled = true;
      if (item.pilot) {
        var productNames = item.itemIds.map(function (id) { return snapshot.crafting.items.find(function (product) { return product.id === id; }).name; }).join(', ');
        var life = item.owned ? amount(item.remainingSeconds / 86400) + ' game days left' : amount(item.lifeSeconds / 86400) + ' active game days';
        el('craft-asset-detail').innerHTML = '<p class="asset-kind">' + (item.assetType === 'tangible' ? 'Equipment' : 'Software or rights') + ' · ' + esc(item.businessName) + '</p><p><strong>' + esc(assetEffects(item)) + '</strong></p><p class="craft-pilot-muted">For ' + esc(productNames) + '.</p><p>' + money(item.price) + ' · ' + life + '</p><p class="craft-pilot-muted">Wears only while assigned to an operating business. Replace when its life runs out.</p>' + (item.owned ? '<p>Book value: ' + money(item.bookValue) + ' · ' + (item.assignedBuildingId ? 'Assigned' : 'Unassigned') + '</p>' : '') + '<p class="craft-pilot-muted"><a href="./buildings.html">Assign on Build</a> using the arrows beside Last 60 game seconds.</p>';
        submit.hidden = false;
        if (item.usageNote) el('craft-asset-detail').insertAdjacentHTML('beforeend', '<p class="craft-pilot-muted">' + esc(item.usageNote) + '</p>');
        submit.textContent = item.owned && item.remainingSeconds > 0 ? 'OWNED' : (item.owned ? 'REPLACE · ' : 'BUY · ') + money(item.price);
        submit.disabled = busy || !connected || !!snapshot.paused || !item.canBuy;
        el('craft-reason').textContent = snapshot.paused ? 'Your teacher has paused the class.' : !connected ? 'Reconnect to manage this asset.' : !item.canBuy && !(item.owned && item.remainingSeconds > 0) ? 'Need ' + money(item.price) + '.' : '';
      }
      if (dialog.open && window.YomamaCraftFitDialog) window.YomamaCraftFitDialog.fit();
      return;
    }
    el('craft-makes').textContent = 'Makes 1 ' + item.name;
    el('craft-owned').textContent = 'Owned: ' + amount(item.owned);
    if (item.pilot) {
      el('craft-makes').textContent = item.businessName + ' · Automatic production';
      el('craft-owned').textContent = 'Stored: ' + amount(item.owned) + ' / ' + amount(item.storageCap);
      pilotDetail.innerHTML = '<div class="craft-pilot-stats"><span>1 item / ' + amount(item.effectiveBatchSeconds || item.batchSeconds) + ' game sec</span><span>Processing: ' + amount(item.batchCost) + ' YM</span><span>Sells for ' + money(item.sellPrice) + '</span></div>' + (!item.unlocked ? '<ul class="craft-pilot-requirements">' + item.unlockRequirements.map(function (r) { return '<li data-ready="' + r.ready + '">' + (r.ready ? '✓ ' : '○ ') + esc(r.label) + '</li>'; }).join('') + '</ul>' : '<p class="craft-pilot-state">' + esc(item.pilotStatus) + '</p><progress max="1" value="' + item.progress + '" aria-label="Production progress"></progress>') + (item.requiredAssets.length ? '<p class="craft-pilot-assets">Needs: ' + item.requiredAssets.map(function (r) { return '<span data-ready="' + r.ready + '">' + (r.ready ? '✓ ' : '○ ') + esc(r.name) + '</span>'; }).join(' · ') + '</p>' : '') + '<p class="craft-pilot-muted">Products use crafting supplies and sell automatically. Shared supplies take turns.</p>';
    }
    el('craft-ingredient-rows').innerHTML = item.ingredients.map(function (row) {
      var enough = row.available >= row.quantity;
      var source = row.source + (row.kind === 'energy' ? ' · Energy' : row.kind === 'service' ? ' · Service' : '');
      var buy = row.kind === 'supply' && row.missing > 0 ? '<button id="craft-buy-' + esc(row.id) + '" class="craft-buy" type="button" data-craft-buy="' + esc(row.id) + '"' + (busy || !connected || snapshot.paused || !row.canBuy ? ' disabled' : '') + ' aria-label="Buy ' + amount(row.missing) + ' ' + esc(row.name) + ' for ' + money(row.buyCost) + '">Buy ' + amount(row.missing) + ' · ' + money(row.buyCost) + '</button>' + (!row.canBuy ? '<small class="craft-ingredient-source">Need ' + money(row.buyCost) + '</small>' : '') : '';
      return '<tr><td><div class="craft-ingredient">' + ingredientIcon(row) + '<div class="craft-ingredient-info"><span class="craft-ingredient-name">' + esc(row.name) + '</span><span class="craft-ingredient-source">' + esc(source) + '</span>' + (row.reserved ? '<span class="craft-ingredient-reserved">' + amount(row.reserved) + ' saved for deliveries</span>' : '') + buy + '</div></div></td><td>' + amount(row.quantity) + '</td><td class="' + (enough ? 'craft-have-enough' : 'craft-have-missing') + '" aria-label="' + amount(row.available) + ' available">' + amount(row.available) + '</td></tr>';
    }).join('');
    submit.disabled = busy || !connected || !!snapshot.paused || !item.canCraft;
    submit.setAttribute('aria-busy', String(busy));
    el('craft-reason').textContent = !connected ? 'Reconnect to check your ingredients.' : snapshot.paused ? 'Your teacher has paused the class.' : !item.canCraft ? item.why || 'Gather the missing ingredients to craft this item.' : '';
    if (item.pilot) {
      submit.textContent = item.unlocked ? 'AUTOMATIC' : item.activationCraft ? 'CRAFT ONCE' : 'UNLOCK · ' + money(item.unlockCost);
      submit.disabled = busy || !connected || !!snapshot.paused || item.unlocked || !item.canUnlock;
      el('craft-reason').textContent = item.available === false ? 'This product is not available yet.' : !connected ? 'Reconnect to check this product.' : snapshot.paused ? 'Your teacher has paused the class.' : item.unlocked ? '' : item.activationCraft ? 'Craft one item to activate automatic production. Assign three assets to keep it running.' : 'Unlock once. Production starts when its business, assets and ingredients are ready.';
    }
    if (focusId) {
      var target = el(focusId);
      if (target && !target.disabled) target.focus({preventScroll:true});
      else if (dialog.open && !dialog.contains(document.activeElement)) el('craft-close').focus({preventScroll:true});
    }
    dialog.scrollTop = scroll;
    if (dialog.open && window.YomamaCraftFitDialog) window.YomamaCraftFitDialog.fit();
  }
  function apply(data) {
    snapshot = data; connected = true;
    if (data.token && !session.token) {
      session = {token:data.token, name:data.name || 'PLAYER', code:data.code || ''};
      try { localStorage.setItem('yomama_session_v1', JSON.stringify(session)); } catch (_) {}
    }
    content.setAttribute('aria-busy', 'false');
    notice.textContent = !data.crafting || !data.crafting.enabled ? 'Crafting is not available for this class yet.' : data.paused ? 'Your teacher has paused the class.' : '';
    if (pilotEnabled() && !data.paused) {
      var recent = data.crafting.pilot.rewards;
      if (recent.length) { var reward = recent[recent.length - 1]; notice.textContent = reward.reason + ': ' + reward.items.map(function (item) { return item.quantity + ' ' + item.name; }).join(', ') + '.'; }
    }
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
    if (window.YomamaCraftFitDialog) window.YomamaCraftFitDialog.fit();
    dialog.scrollTop = 0;
  }
  function perform(body, label) {
    if (busy || !snapshot || snapshot.paused) return;
    var key = JSON.stringify(body);
    var operation = lastOp && lastOp.key === key ? lastOp : {key:key, body:Object.assign({}, body, {requestId:requestId(), revision:snapshot.crafting.revision})};
    lastOp = operation; busy = true; generation += 1;
    status(body.action === 'buy_supply' ? 'Buying supplies…' : body.action === 'unlock' ? 'Unlocking…' : body.action === 'buy_asset' ? 'Buying asset…' : 'Crafting…', 'pending'); renderDetail();
    request('POST', '/api/game/craft', operation.body).then(function (data) {
      lastOp = null; apply(data); status(label, 'success');
    }).catch(function (error) {
      // A lost response can be retried with the same ID without spending twice.
      if (error.status && error.status < 500) lastOp = null;
      status(error.status ? error.message : 'Could not confirm the request. Try again to check it safely.', 'error');
    }).finally(function () { busy = false; renderDetail(); refresh(); });
  }
  document.querySelectorAll('[data-craft-section]').forEach(function (button) {
    button.addEventListener('click', function () {
      section = button.dataset.craftSection;
      document.querySelectorAll('[data-craft-section]').forEach(function (tab) { tab.setAttribute('aria-pressed', String(tab === button)); });
      grid.setAttribute('aria-label', button.textContent);
      grid.scrollTop = 0;
      if (snapshot) { renderHeader(); renderGrid(); }
    });
  });
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
    if (section === 'supplies') { perform({action:'buy_supply', supplyId:item.id, quantity:1}, 'Bought 1 ' + item.name + '.'); return; }
    if (item.pilot && item.assetType) { perform({action:'buy_asset', assetId:item.id}, 'Bought ' + item.name + '. Assign it on Build.'); return; }
    if (item.pilot) { perform({action:item.activationCraft ? 'craft' : 'unlock', itemId:item.id}, (item.activationCraft ? 'Crafted and activated ' : 'Unlocked ') + item.name + '. Production is automatic.'); return; }
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
