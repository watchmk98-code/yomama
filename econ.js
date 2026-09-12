/**
 * YOMAMA INVESTMENTS - Part 1 economy client.
 *
 * The browser owns no money or inventory. It sends intentions and renders
 * server-authoritative production, customer sales, goods, orders, and costs.
 * Version 4 uses real item quantities; older saved-model payloads retain their
 * original display while their server completes migration.
 *
 * One file drives every economy screen. Each screen is just an empty div with a
 * known id; whichever ids exist on the page get rendered:
 *
 *   #econ-building    buildings.html    collection, levels, upgrades, expansion
 *   #econ-warehouse   warehouse.html    per-good storage and the capacity bar
 *   #econ-auto        advanced-hq.html  production and customer operations
 *   #econ-market      marketplace.html  the board: prices and selling
 *   #econ-license     license.html      the four-box checklist, quiz, keep/sell
 *   #econ-dashboard   index.html        net worth, revenue, tier, leaderboard
 *
 * The five game screens render in "kid mode": big art, one big number, one
 * action per card, plain words, and a printed reason under every disabled
 * button. They are styled by econ-kids.css, scoped under .econ-kid. The
 * dashboard deliberately keeps the amber terminal look of the rest of the app.
 *
 * Building art is optional: assets/buildings/<tier id>.png. A missing file
 * shows a placeholder, never a broken image. See that folder's README.
 */
(function () {
  'use strict';

  var SESSION_KEY = 'yomama_session_v1';
  var BASE = '/api/game/econ';
  var POLL_MS = 15000;            // one tick
  var ART_DIR = './assets/buildings/';

  var session = null;
  var snapshot = null;            // last payload from the server
  var quiz = null;                // questions, fetched once on the licence page
  var statusMessage = null;       // { text, tone }
  var pollTimer = null;
  var tickTimer = null;
  var busy = false;
  var pendingRerolls = [];
  var customerSlot = 0;
  var customerChoices = {};
  var customerSwitchId = null;

  // ------------------------------------------------------------- session --
  try {
    var raw = window.localStorage.getItem(SESSION_KEY);
    var parsed = raw ? JSON.parse(raw) : null;
    if (parsed && parsed.token && parsed.code) session = parsed;
  } catch (_) { session = null; }

  // ------------------------------------------------------------ transport --
  function request(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      body.token = session ? session.token : '';
      opts.body = JSON.stringify(body);
    }
    return fetch(BASE + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error((data && (data.why || data.error)) || ('HTTP ' + res.status));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function fetchState() {
    return request('GET', '/state?token=' + encodeURIComponent(session ? session.token : ''));
  }

  // ----------------------------------------------------------- formatting --
  // Whole YM only. Thousands become k, millions become M, above 10,000.
  function ym(value) {
    var n = Math.round(Number(value) || 0);
    var sign = n < 0 ? '-' : '';
    var abs = Math.abs(n);
    if (abs >= 1000000) return sign + (abs / 1000000).toFixed(1) + 'M YM';
    if (abs >= 10000) return sign + (abs / 1000).toFixed(1) + 'k YM';
    return sign + abs.toLocaleString('en-US') + ' YM';
  }

  function productionModel(s) { return Number(s.modelVersion) >= 4; }

  function units(value) {
    return (Number(value) || 0).toLocaleString('en-US', { maximumFractionDigits: 1 });
  }

  function materialAmount(value) { return units(value) + ' material' + (Number(value) === 1 ? '' : 's'); }

  function orderOffers(s) { return ((s.orders || s.contracts || {}).offers || []); }

  function mult(value) { return (Number(value) || 0).toFixed(2); }

  function percent(value) { return Math.round((Number(value) || 0) * 100) + '%'; }

  function minutes(value) {
    if (value === null || value === undefined) return 'never';
    var m = Number(value);
    if (m < 90) return Math.round(m) + ' minutes';
    if (m < 1440) return (m / 60).toFixed(1) + ' hours';
    return (m / 1440).toFixed(1) + ' days';
  }

  function duration(totalSeconds) {
    var s = Math.max(0, Math.round(Number(totalSeconds) || 0));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    if (h > 0) return h + 'h ' + String(m).padStart(2, '0') + 'm ' + String(sec).padStart(2, '0') + 's';
    if (m > 0) return m + 'm ' + String(sec).padStart(2, '0') + 's';
    return sec + 's';
  }

  function esc(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[<>&"]/g, function (c) {
        return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c];
      });
  }

  // ------------------------------------------------------ kid-mode pieces --

  // Eight-frame strips supplied at 120ms per frame. Other screens retain PNG art.
  var buildArtEnabled = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function art(s) {
    var id = String(s.buildingId || '');
    if ((id==='farm' || id==='roastery') && s.artLevel>=3) {
      var stage=s.artLevel>=6?6:3;
      return '<div class="k-art k-art--upgraded" data-art-level="'+stage+'"><img src="'+ART_DIR+'upgrades/'+id+'-level-'+stage+'.png" alt="'+esc(s.buildingName)+' · level '+stage+' improvements" onerror="this.src=\''+ART_DIR+'spritesheets/'+id+'_8f.png\';this.parentNode.classList.add(\'k-art--animated\',\'k-art--paused\');this.onerror=null;"></div>';
    }
    var initial = (s.buildingName || '?').charAt(0).toUpperCase();
    var animated = document.body.classList.contains('game-page');
    var paused = !buildArtEnabled || s.paused;
    return '<div class="k-art' + (animated ? ' k-art--animated' : '') + (paused ? ' k-art--paused' : '') + '" data-initial="' + esc(initial) + '">' +
      '<img src="' + ART_DIR + (animated ? 'spritesheets/' : '') + encodeURIComponent(id) + (animated ? '_8f.png' : '.png') + '" alt="' + esc(s.buildingName) + '" ' +
      (animated ? 'data-art-fallback="' + ART_DIR + encodeURIComponent(id) + '.png" ' : '') +
      'onerror="if(this.dataset.artFallback){this.parentNode.classList.remove(\'k-art--animated\');this.src=this.dataset.artFallback;delete this.dataset.artFallback;}else{this.parentNode.classList.add(\'k-art--missing\');this.remove();}"></div>';
  }

  // The supplied pack omits Preserves. Only request files that actually exist.
  var GOOD_ART = {
  "farm_tomatoes": true,
  "farm_eggs": true,
  "farm_honey": true,
  "fish_stall_fresh_catch": true,
  "fish_stall_oysters": true,
  "fish_stall_smoked_fish": true,
  "roastery_roasted_beans": true,
  "roastery_espresso_shots": true,
  "roastery_pastries": true,
  "garage_repairs": true,
  "garage_spare_parts": true,
  "garage_custom_mods": true,
  "workshop_steel_brackets": true,
  "workshop_welded_frames": true,
  "workshop_machined_bolts": true,
  "solar_coop_daytime_kwh": true,
  "solar_coop_battery_storage": true,
  "solar_coop_carbon_credits": true,
  "cannery_canned_goods": true,
  "cannery_sauces": true,
  "machine_works_cnc_parts": true,
  "machine_works_tooling": true,
  "machine_works_prototypes": true,
  "turbine_field_wind_kwh": true,
  "turbine_field_capacity_contracts": true,
  "turbine_field_green_certificates": true,
  "generator_baseload_power": true,
  "generator_peak_power": true,
  "generator_steam_heat": true,
  "relay_station_bandwidth": true,
  "relay_station_sms_traffic": true,
  "relay_station_tower_leases": true,
  "freight_terminal_container_slots": true,
  "freight_terminal_cold_storage": true,
  "freight_terminal_last_mile_delivery": true,
  "data_center_compute_hours": true,
  "data_center_cloud_storage": true,
  "data_center_api_calls": true,
  "solar_array_utility_kwh": true,
  "solar_array_reserve_capacity": true,
  "solar_array_renewable_credits": true,
  "uplink_center_satellite_bandwidth": true,
  "uplink_center_ground_time": true,
  "uplink_center_telemetry": true
};

  function assetIcon(path, style, label) {
    return '<img class="econ-art-icon ' + (style || '') + '" src="./assets/game-art/' + path +
      '" alt="' + esc(label || '') + '" width="40" height="40" loading="eager" decoding="async" onerror="this.hidden=true" />';
  }

  function goodIcon(building, good, labeled) {
    var key = building.id + '_' + String(good.name).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (GOOD_ART[key]) return assetIcon('goods/' + key + '.png', 'econ-good-icon', labeled ? good.name : '');
    return '<span class="econ-art-fallback"' + (labeled ? ' role="img" aria-label="' + esc(good.name) + '"' : ' aria-hidden="true"') + '>' + esc(good.name.slice(0, 2)) + '</span>';
  }

  function goodsStrip(building, s) {
    return '<div class="econ-product-strip" aria-label="Produced goods">' + s.board.filter(function (good) { return good.slot === building.slot; }).map(function (good) {
      return '<span title="' + esc(good.name) + '">' + goodIcon(building, good, true) + '</span>';
    }).join('') + '</div>';
  }

  function goodsRow(building, good, value) {
    return '<div class="econ-good-line"><span class="econ-good-name">' + goodIcon(building, good, false) + '<span>' + esc(good.name) + '</span></span><span>' + value + '</span></div>';
  }

  function line(label, value, tone) {
    return '<div class="k-line"><span>' + esc(label) + '</span><span' +
      (tone ? ' class="' + tone + '"' : '') + '>' + value + '</span></div>';
  }

  function bigButton(action, label, sub, disabled, style) {
    var icon = { level: 'action_level_up', auto: 'action_auto_control', expand: 'action_expand' }[action.split(':')[0]];
    return '<button class="k-btn' + (style || '') + (icon ? ' k-btn--illustrated' : '') + '" type="button" data-econ-action="' + esc(action) + '"' +
      (disabled ? ' disabled' : '') + '><span class="econ-action-label">' +
      (icon ? assetIcon('actions/' + icon + '.png', 'econ-action-icon') : '') + esc(label) + '</span>' +
      (sub ? '<small>' + esc(sub) + '</small>' : '') + '</button>';
  }

  function linkButton(href, label, style) {
    return '<a class="k-btn' + (style || '') + '" href="' + href + '">' + esc(label) + '</a>';
  }

  function why(text) {
    return text ? '<div class="k-why">' + esc(text) + '</div>' : '';
  }

  function bar(fillPercent, tone) {
    var width = Math.max(0, Math.min(100, Number(fillPercent) || 0));
    return '<div class="k-bar"><div class="k-bar-fill' + (tone ? ' ' + tone : '') +
      '" style="width:' + width + '%"></div></div>';
  }

  function statusLine() {
    var tone = '';
    if (statusMessage) {
      tone = statusMessage.tone === 'error' ? ' k-status--bad'
        : (statusMessage.tone === 'success' ? ' k-status--good' : '');
    }
    return '<div class="k-status' + tone + '" data-econ-status role="status" aria-live="polite">' +
      (statusMessage ? esc(statusMessage.text) : '') + '</div>';
  }

  function notice(s) {
    if (!s) return '';
    if (s.paused) return '<div class="k-banner">Your teacher paused the class. Nothing is being made right now.</div>';
    if (s.welcomeBackActive) return '<div class="k-banner">Welcome back — your production boost is active.</div>';
    if (s.behind) return '<div class="k-banner k-banner--calm">Catching up on the time you were away. Refresh in a moment for the rest.</div>';
    return '';
  }

  function hero(s, bigValue, bigLabel, badges) {
    return '<div class="k-hero">' + art(s) +
      '<div class="k-hero-info">' +
      '<h2 class="k-title">' + esc(s.buildingName) + '</h2>' +
      '<div class="k-sub">Building ' + (s.tier + 1) + ' of ' + s.tierCount + ' &middot; Level ' + s.level + '</div>' +
      '<div class="k-big">' + bigValue + '</div>' +
      '<div class="k-big-label">' + esc(bigLabel) + '</div>' +
      (badges && badges.length ? '<div class="k-badges">' + badges.join('') + '</div>' : '') +
      '</div></div>';
  }

  function badge(text, style) {
    return '<span class="k-badge' + (style || '') + '">' + esc(text) + '</span>';
  }

  // ------------------------------------------------------------- screens ---

  function family(b, s) {
    return '<span class="k-badge family-' + esc(b.family) + '">' + esc(s.families[b.family].name) + '</span>';
  }

  // One selected business keeps management compact as the collection grows.
  var selectedSlot = null;
  try { var savedSlot=sessionStorage.getItem('yomama_business_slot');if(savedSlot!==null)selectedSlot=Number(savedSlot); } catch (_) {}
  var lastRenderedSlot = null;
  var selectedFrontier = null;
  var quizStep = 0;

  function selectedBuilding(s) {
    var b = s.buildings.find(function (item) { return item.slot === selectedSlot; }) || s.buildings[s.buildings.length - 1];
    selectedSlot = b.slot;
    try {sessionStorage.setItem('yomama_business_slot',String(selectedSlot));} catch (_) {}
    return b;
  }

  function panelHead(title, detail) {
    return '<div class="game-panel-head"><h2>' + esc(title) + '</h2>' + (detail ? '<span>' + detail + '</span>' : '') + '</div>';
  }

  function resourceBar(s) {
    if(productionModel(s))return '<div class="game-wallet"><span>Cash <strong>'+ym(s.cash)+'</strong></span>'+(document.getElementById('econ-building')?'<span title="Used to open new businesses">Materials <strong>'+units(s.materials)+'</strong></span>':'')+'</div>';
    var values = [['Cash', ym(s.cash)], [productionModel(s) ? 'Sales / min' : 'Production / ' + s.tickSeconds + ' sec', ym(productionModel(s) ? s.incomePerMinute : s.revenuePerTick)], ['Storage', percent(s.warehouseFillPercent / 100)], ['Business value', ym(s.netWorth)]];
    return '<div class="game-resources">' + values.map(function (v) { return '<div><span>' + v[0] + '</span><strong>' + v[1] + '</strong></div>'; }).join('') + '</div>';
  }

  function roster(s) {
    return '<aside class="game-panel game-roster" aria-label="Your buildings">' + panelHead('Your buildings', s.buildingsOwned + ' / ' + s.tierCount) +
      '<div class="game-roster-list" data-keep-scroll="roster">' + s.buildings.map(function (b) {
        return '<button type="button" class="game-building-choice" data-select-building="' + b.slot + '" aria-pressed="' + (b.slot === selectedSlot) + '">' +
          art({buildingId:b.id, buildingName:b.name, paused:true, artLevel:b.artLevel}) + '<span><strong>' + esc(b.name) + '</strong><small>' + (productionModel(s) ? esc(b.status || 'Working') : 'Lv ' + b.lv + ' · ' + ym(b.revenuePerTick) + ' / tick') + '</small></span></button>';
      }).join('') + '</div><div class="game-roster-foot">All buildings keep producing.</div></aside>';
  }

  function site(b, s) {
    if (productionModel(s)) return productionSite(b, s);
    return '<section class="game-panel game-site">' + panelHead(b.name, '<span class="' + (s.paused ? 'k-money' : 'k-good') + '">' + (s.paused ? 'Ⅱ Paused' : '● Producing') + '</span>') +
      '<div class="game-site-stage">' + art({buildingId:b.id, buildingName:b.name, paused:s.paused}) +
      '<div><span class="game-eyebrow">' + esc(s.families[b.family].name) + '</span><div class="game-level">LEVEL ' + b.lv + '</div><strong class="game-output">' + ym(b.revenuePerTick) + '<small> / ' + s.tickSeconds + ' sec</small></strong>' +
      '<span class="game-site-auto">Output ×' + b.auto + '</span></div></div>' +
      '<div class="game-site-footer"><span>' + (b.setBadges.length ? esc(b.setBadges.join(' · ')) : 'Building ' + (b.tier + 1) + ' / ' + s.tierCount) + '</span><button class="game-text-button" type="button" data-build-art aria-pressed="' + buildArtEnabled + '">Animation ' + (buildArtEnabled ? 'on' : 'off') + '</button></div></section>';
  }

  function stockPanel(b, s) {
    if (productionModel(s)) return inventoryPanel(b, s);
    var fill = b.capacity > 0 ? b.stored / b.capacity * 100 : 0;
    return '<section class="game-panel game-stock">' + panelHead('Goods ready to sell', '<span class="' + (b.price >= 1 ? 'k-good' : 'k-bad') + '">Price ×' + mult(b.price) + '</span>') +
      '<div class="game-stock-progress"><span>' + ym(b.stored) + ' / ' + ym(b.capacity) + '</span>' + bar(fill, fill >= 100 ? 'k-bar-fill--full' : '') + '</div>' +
      '<div class="game-goods">' + s.board.filter(function(g) { return g.slot === b.slot; }).map(function(g) {return goodsRow(b,g,ym(g.stored));}).join('') + '</div>' +
      '<div class="game-sell-row"><span title="Manual sales include a fresh-goods bonus. The server applies market price and tax.">+' + s.premiumSalePct + '% fresh bonus</span>' + bigButton('sell:' + b.slot,'Sell goods','',b.stored <= 0,' k-btn--alt') + '</div>' +
      (b.stored <= 0 ? '<p class="game-hint">Goods appear as your building produces.</p>' : '') + '</section>';
  }

  function upgradePanel(b, s, auto) {
    var cost = auto ? b.autoCost : b.levelCost;
    var done = auto ? cost === null : b.maxed;
    var blocked = done || s.cash < cost;
    var payback = auto ? b.autoPayback : b.levelPayback;
    return '<section class="game-panel game-upgrade">' + panelHead(auto ? 'Auto Control' : 'Level up', auto ? 'Output ×' + b.auto : 'Lv ' + b.lv + ' → ' + (done ? 'MAX' : b.lv + 1)) +
      '<div class="game-upgrade-body">' + bigButton((auto ? 'auto:' : 'level:') + b.slot, done ? 'Fully upgraded' : (auto ? 'Boost' : 'Upgrade') + ' · ' + ym(cost),'',blocked,auto ? ' k-btn--alt' : '') +
      '<span class="game-hint">' + (done ? 'Complete' : s.cash < cost ? 'Need ' + ym(cost - s.cash) + ' more' : payback == null ? 'Increase production' : 'Pays back in ' + minutes(payback)) + '</span></div></section>';
  }

  function expansionPanel(s) {
    var frontier = s.frontier || [], queue = s.queue || [];
    var b = frontier.find(function(item) { return item.tier === selectedFrontier; }) || frontier[0];
    if (b) selectedFrontier = b.tier;
    var detail = productionModel(s) ? '' : (queue.length + (s.build ? 1 : 0)) + '/' + s.queueDepth + ' slots';
    return '<section class="game-panel game-expansion">' + panelHead('New business', detail) +
      '<div class="game-expansion-body">' + (b ? '<div class="game-next-art" data-preview-business="'+esc(b.id)+'">'+art({buildingId:b.id,buildingName:b.name,paused:true})+'</div><label class="game-visually-hidden" for="game-expansion-choice">Next building</label><select id="game-expansion-choice">' + frontier.map(function(item) {return '<option value="' + item.tier + '"' + (item.tier === b.tier ? ' selected' : '') + '>' + esc(item.name) + '</option>';}).join('') + '</select>' +
      '<div class="game-small-stats"><span>' + (productionModel(s) ? duration(b.buildSeconds == null ? b.timerH * 3600 : b.buildSeconds) : b.timerH + 'h') + ' build</span><span>' + (productionModel(s) ? (b.materialsMissing ? 'Buy ' + materialAmount(b.materialsMissing) : materialAmount(b.materialsCost)) : ym(b.baseRevenue) + ' / tick') + '</span></div>' +
      bar(b.cost > 0 ? s.cash / b.cost * 100 : 100,'k-bar-fill--gold') + bigButton('expand:' + b.tier, 'Build · ' + ym(b.cost),'',!b.canExpand,' k-btn--alt') +
      (!b.canExpand ? why(/^Need \d+ YM more$/.test(b.why)?'Need '+ym(Math.max(0,b.cost-s.cash))+' more':b.why) : '') : '<p class="k-good">All businesses open</p>') +
      (s.build ? '<div class="game-construction"><span>' + esc(s.build.name) + '</span><b data-econ-countdown="' + s.build.remainingSec + '">' + duration(s.build.remainingSec) + '</b></div>' : '') +
      (queue.length ? '<details class="game-queue"><summary>' + queue.length + ' queued</summary>' + queue.map(function(q) {return '<p>' + esc(q.name) + '</p>';}).join('') + '</details>' : '') + '</div></section>';
  }

  function gameFooter(s) {
    if (productionModel(s)) {
      var goal=s.build?s.build.name+' opening soon':s.frontier && s.frontier.length?'Next · '+s.frontier[0].name:'All businesses open';
      return '<div class="game-footer"><span class="game-next-goal">' + esc(goal || 'Next: open another business') + '</span><span class="game-materials">' + materialAmount(s.materials) + '</span></div>';
    }
    var c=s.checklist || {};
    var count=[c.lv25,c.auto,(c.goodSales || 0)>=s.goodSalesNeeded,c.quiz,s.buildingsOwned>=s.gateTier].filter(Boolean).length;
    return '<div class="game-footer">' + assetIcon('badges/licence_' + (s.gateOpen ? 'unlocked' : 'locked') + '.png','econ-licence-icon') +
      '<span>Licence <b>' + count + '/5</b></span><div class="game-goal-track" aria-label="' + count + ' of 5 goals complete">' + [0,1,2,3,4].map(function(i) {return '<i class="' + (i<count ? 'is-done' : '') + '"></i>';}).join('') + '</div>' +
      '<a href="./license.html" class="game-text-button">View goals ↗</a><button class="game-text-button" type="button" data-game-deliveries>Delivery jobs' + (s.contracts.active.length ? ' · ' + s.contracts.active.length + ' active' : '') + ' ↗</button></div>';
  }

  function renderBuilding(el, s) {
    var b=selectedBuilding(s);
    el.innerHTML=notice(s)+'<div class="game-layout">'+roster(s)+'<div class="game-center">'+site(b,s)+(productionModel(s)?'':stockPanel(b,s))+'</div><div class="game-actions">'+(productionModel(s)?operationsPanel(b,s):upgradePanel(b,s,false)+upgradePanel(b,s,true))+expansionPanel(s)+'</div></div><div class="game-build-bottom">'+(productionModel(s)?'':gameFooter(s))+breakfastStrip(s)+'</div>'+statusLine();
  }

  var breakfastGoods = {
    beans: ['Beans', 'roastery_roasted_beans'], eggs: ['Eggs', 'farm_eggs'],
    honey: ['Honey', 'farm_honey'], coffee: ['Coffee', 'roastery_espresso_shots'],
    pastry: ['Pastries', 'roastery_pastries']
  };
  function breakfastIcon(key) { return assetIcon('goods/'+breakfastGoods[key][1]+'.png','econ-good-icon'); }
  function breakfastStrip(s) {
    var e=s.breakfastEvent;if(!e)return '';
    return '<section class="game-event-strip" aria-label="Breakfast Club event">'+breakfastIcon('coffee')+'<div><strong>Breakfast Club</strong><small>'+(e.status==='done'?'Complete · recipe improved':'Kitchen challenge · lasting upgrade')+'</small></div><button type="button" class="game-small-button" data-game-breakfast>'+(e.status==='new'?'Play':e.status==='done'?'View':'Resume')+' ↗</button></section>';
  }
  function breakfastMarkup(s) {
    var e=s.breakfastEvent;if(!e)return '<p>Event unavailable.</p>';
    if(e.status==='new')return '<div class="breakfast-welcome"><div class="breakfast-welcome-art">'+breakfastIcon('coffee')+breakfastIcon('pastry')+'</div><h3>Run the morning rush</h3><div class="breakfast-prize">4 orders → +5 materials + a permanent recipe upgrade</div><p class="game-hint">Your own event supplies. No deadline. Close and resume anytime.</p>'+bigButton('breakfast:start','Open the kitchen','',false)+'</div>';
    if(e.status==='done')return '<div class="breakfast-welcome"><div class="breakfast-welcome-art">'+breakfastIcon('coffee')+breakfastIcon('pastry')+'</div><h3>Breakfast is served!</h3><div class="breakfast-prize">+5 materials added to your town</div><p>4 orders served · '+(e.upgrade==='coffee'?'Coffee':'Pastry')+' kitchen upgraded</p></div>';
    var completed=e.stage>=4?3:e.stage;
    var html='<div class="breakfast-progress"><span>'+completed+' / 4 served</span><span>'+e.coins+' event coins</span></div>'+bar(completed/4*100,'k-bar-fill--gold');
    html+='<div class="breakfast-stock">'+Object.keys(breakfastGoods).map(function(k){return '<div>'+breakfastIcon(k)+'<strong>'+e.stock[k]+'</strong><small>'+breakfastGoods[k][0]+'</small>'+(e.supply[k]?'<small>+1 / '+({beans:15,eggs:30,honey:60}[k])+'s</small>':'')+'</div>';}).join('')+'</div>';
    html+='<div class="breakfast-layout"><section class="game-panel">'+panelHead('Kitchen','1 cooking · 1 queued')+'<div class="game-panel-body">';
    html+='<div class="breakfast-job" role="status">'+(e.active?'<strong>Making '+breakfastGoods[e.active.recipe][0].toLowerCase()+'</strong><b data-econ-countdown="'+e.active.remaining+'">'+duration(e.active.remaining)+'</b>':'<strong>Kitchen ready</strong>')+'</div>';
    html+='<div class="breakfast-queue">'+(e.queued?'<span>'+breakfastGoods[e.queued.recipe][0]+' · '+(e.active?'queued':'waiting for ingredients')+'</span><button type="button" class="game-text-button" data-econ-action="breakfast:cancel:'+e.queued.id+'" aria-label="Cancel queued batch">Cancel</button>':'<span>Queue a batch to keep cooking</span>')+'</div>';
    html+=Object.keys(e.recipes).map(function(k){var r=e.recipes[k];return '<div class="breakfast-recipe"><div><strong>'+breakfastGoods[k][0]+' ×'+r.output+'</strong><small>'+Object.keys(r.inputs).map(function(i){return r.inputs[i]+' '+breakfastGoods[i][0].toLowerCase();}).join(' + ')+' · '+r.seconds+'s</small></div>'+bigButton('breakfast:make:'+k,e.active||!r.ready?'Queue':'Make','',!!e.queued||e.stock[k]>=12)+'</div>';}).join('');
    html+='</div></section><section class="game-panel">'+panelHead(e.stage===3?'Choose your upgrade':e.stage===1?'Pick one order':'Serve an order',e.stage===4?'+5 materials':'')+'<div class="game-panel-body breakfast-orders">';
    if(e.stage===3){
      html+='<p class="game-hint">Twice the batch here. Finish to keep +25% base speed for this roastery recipe.</p>'+['coffee','pastry'].map(function(k){return '<div class="breakfast-order"><h3>'+breakfastGoods[k][0]+' kitchen</h3><p>'+breakfastRecipeText(k)+'</p>'+bigButton('breakfast:upgrade:'+k,'Upgrade · 100 coins','',false)+'</div>';}).join('');
    }else{
      html+=e.orders.map(function(o){return '<div class="breakfast-order"><h3>'+esc(o.name)+'</h3><div class="breakfast-needs">'+Object.keys(o.needs).map(function(k){return '<span class="'+(e.stock[k]>=o.needs[k]?'is-ready':'')+'">'+breakfastIcon(k)+Math.min(e.stock[k],o.needs[k])+'/'+o.needs[k]+' '+breakfastGoods[k][0]+'</span>';}).join('')+'</div>'+bigButton('breakfast:deliver:'+o.id,o.coins?'Serve · +'+o.coins+' coins':'Serve · unlock town upgrade','',!o.ready)+'</div>';}).join('');
    }
    return html+'</div></section></div><p class="game-hint breakfast-note">Event supplies only · Ingredients refill up to 12 · Progress saves when you close</p>';
  }
  function breakfastRecipeText(k){return k==='coffee'?'4 beans → 4 coffees · 30s':'2 eggs + 2 honey → 2 pastries · 45s';}

  function contractsMarkup(s) {
    if (productionModel(s)) return ordersMarkup(s);
    var c=s.contracts;
    function info(o) {return '<h3>'+esc(o.building)+'</h3>'+line('Goods needed',ym(o.target))+line('Reward',ym(o.reward))+line('If missed',ym(o.penalty))+'<p class="game-hint">Due in <span data-econ-countdown="'+o.remainingSec+'">'+duration(o.remainingSec)+'</span></p>';}
    return '<h3>Active deliveries</h3><div class="game-card-grid">'+(c.active.length ? c.active.map(function(o) {return '<section class="k-card">'+info(o)+line('Delivered',ym(o.delivered)+' / '+ym(o.target))+bar(o.progressPercent)+'<p class="game-hint">Production fills this order first.</p></section>';}).join('') : '<p class="game-hint">No delivery in progress.</p>')+'</div><h3>Available jobs</h3><div class="game-card-grid">'+c.offers.map(function(o,i){return '<section class="k-card">'+info(o)+bigButton('contract:'+i,'Accept job','',c.active.length>=s.contractSlots || o.remainingSec<=0)+(c.active.length>=s.contractSlots?why('Finish an active job first.'):o.remainingSec<=0?why('Offer expired. New jobs arrive later.'):'')+'</section>';}).join('')+'</div>'+statusLine();
  }

  function renderWarehouse(el,s) { renderInventory(el,s,false); }
  function renderMarket(el,s) { renderInventory(el,s,true); }

  function renderInventory(el,s,market) {
    var b=selectedBuilding(s);
    if (productionModel(s)) { renderProductionInventory(el,s,b,market); return; }
    var side='<section class="game-panel">'+panelHead(market?'Market today':'Storage overview','')+'<div class="game-panel-body">'+
      (market ? line('Sale price','×'+mult(b.price),b.price>=1?'k-good':'k-bad')+line('Price movement',esc(b.priceTrend))+line('Fresh bonus','+'+s.premiumSalePct+'%')+line('Sales tax',percent(s.taxRate))+'<p class="game-hint">Above ×1 means a better price for your goods.</p>' : line('All goods stored',ym(s.warehouseStored))+line('Total capacity',ym(s.warehouseCap))+bar(s.warehouseFillPercent,s.overflowing?'k-bar-fill--full':'')+'<p class="game-hint">When storage fills, extra goods sell at a '+percent(s.overflowDisc)+' discount.</p>')+'</div></section>';
    if(market && s.tickerLines.length) side+='<section class="game-panel">'+panelHead('Market news','')+'<div class="game-panel-body game-news" data-keep-scroll="news">'+s.tickerLines.map(function(t){return '<p>'+esc(t)+'</p>';}).join('')+'</div></section>';
    el.innerHTML=notice(s)+'<div class="game-layout">'+roster(s)+'<div class="game-center">'+site(b,s)+stockPanel(b,s)+'</div><div class="game-actions">'+side+'</div></div>'+gameFooter(s)+statusLine();
  }

  function renderAuto(el,s) {
    var b=selectedBuilding(s);
    if (productionModel(s)) {
      el.innerHTML=notice(s)+businessPicker(s,b)+'<div class="game-purpose-layout game-recipes-only"><div class="game-purpose-main">'+recipePanel(b,s)+focusMarkup(b)+'</div></div>'+statusLine();
      return;
    }
    el.innerHTML=notice(s)+'<div class="game-layout">'+roster(s)+'<div class="game-center">'+site(b,s)+'<section class="game-panel">'+panelHead('Your production team','')+'<div class="game-panel-body">'+goodsStrip(b,s)+line('Current output',ym(b.revenuePerTick)+' / '+s.tickSeconds+' sec')+line('Auto Control',esc(b.autoLabel))+'<p class="game-hint">Boost this building while your other buildings keep working.</p></div></section></div><div class="game-actions">'+upgradePanel(b,s,true)+upgradePanel(b,s,false)+'</div></div>'+gameFooter(s)+statusLine();
  }

  function productionSite(b, s) {
    var status=s.paused ? 'Paused' : b.status || 'Working';
    var working=status==='Working', group=(s.families || {})[b.family];
    return '<section class="game-panel game-site">' + panelHead(b.name,'<span class="'+(working?'k-good':'k-money')+'">'+esc(status)+'</span>') +
      '<div class="game-site-stage">'+art({buildingId:b.id,buildingName:b.name,paused:s.paused,artLevel:b.artLevel})+'<div><span class="game-eyebrow">'+esc(group ? group.name : 'Your business')+(b.artLevel>=3?' · Improved '+b.artLevel:'')+'</span>'+
      '<strong class="game-output">'+ym(b.incomePerMinute)+'<small> / min</small></strong><span class="game-eyebrow">Shop income · last minute</span></div></div>'+
      productionLoop(b,s)+nextAction(b,s)+'<div class="game-site-footer"><span>'+ (b.regularBonus?'Breakfast regulars · +20% customers':'Works offline · up to ' + units(s.offlineHours || 12) + 'h') +'</span>'+(!(b.artLevel>=3 && (b.id==='farm'||b.id==='roastery'))?'<button class="game-text-button" type="button" data-build-art aria-pressed="'+buildArtEnabled+'">Animation '+(buildArtEnabled?'on':'off')+'</button>':'')+'</div></section>';
  }

  function productionLoop(b,s) {
    var good=(b.goods || s.board.filter(function(g){return g.slot===b.slot;}))[0];
    return '<div class="game-production-loop" aria-label="How this business earns money"><div>'+(good?goodIcon(b,good,false):'')+'<strong>Make goods</strong><small>'+units(b.productionPerMinute)+' / min</small></div><span class="game-flow-arrow" aria-hidden="true">→</span><div><span class="game-flow-shop" aria-hidden="true">'+assetIcon('ui/customers.svg','')+'</span><strong>Serve customers</strong><small>Up to '+units(b.customerCapacityPerMinute == null ? b.salesPerMinute : b.customerCapacityPerMinute)+' / min</small></div><span class="game-flow-arrow" aria-hidden="true">→</span><div><span class="game-flow-coin" aria-hidden="true">'+assetIcon('ui/coin.svg','')+'</span><strong>Earn cash</strong><small>'+(s.paused?'Class paused':b.reserve?'Shop sales paused':'Sales are automatic')+'</small></div></div>';
  }

  function nextAction(b,s) {
    var text='Upgrade this business or open the next one.', href='', label='';
    if(s.paused)text='Your business continues when your teacher resumes the class.';
    else if(b.reserve){text='Shop sales are paused while you hold goods.';href='./warehouse.html';label='Manage stock';}
    else if(b.status==='Processing paused' || /^Waiting for /.test(b.status || '')){text=b.status==='Processing paused'?'Recipes are paused. Other goods still produce.':b.status+'. Check the recipe ingredients.';href='./advanced-hq.html';label='View recipes';}
    else if(b.status==='Storage full'){if(b.clearableQuantity>0){text='Storage is full. Sell surplus to free up space.';href='./warehouse.html';label='Manage stock';}else text='Storage is full with saved goods. Upgrade Storage for more room.';}
    else if(b.status==='Goods ready'){text='Put your extra goods toward delivery rewards.';href='./marketplace.html';label='View orders';}
    else if(b.status==='More customers needed')text='Goods are piling up. Upgrade Customers to sell faster.';
    else if(!s.paused && b.upgrades && b.upgrades.production && b.upgrades.production.canBuy)text='Ready to grow? Upgrade Production to make more goods.';
    return '<div class="game-next-action"><span>'+esc(text)+'</span>'+(href?'<a class="game-text-button" href="'+href+'">'+label+' →</a>':'')+'</div>';
  }

  function focusMarkup(b) {
    if(!(b.focusOptions||[]).length)return '';
    if(!b.focusUnlocked)return '<div class="game-specialty game-hint">Production level 3 unlocks a specialty</div>';
    var choice=b.focusOptions.find(function(o){return o.id===b.focus;}) || b.focusOptions[0];
    return '<div class="game-specialty"><label>Specialty <select id="game-business-focus" data-business-focus="'+b.slot+'" aria-label="Business specialty">'+b.focusOptions.map(function(o){return '<option value="'+o.id+'"'+(choice.id===o.id?' selected':'')+'>'+esc(o.name)+'</option>';}).join('')+'</select></label><small>'+esc(choice.effect)+' · Switch freely</small></div>';
  }

  function processingControl(b) {
    return '<button type="button" class="game-text-button game-processing" data-econ-action="processing:'+b.slot+':'+(b.processing===false)+'" aria-pressed="'+(b.processing!==false)+'" title="Other goods keep producing.">'+(b.processing===false?'Resume recipes':'Pause recipes')+'</button>';
  }

  function inventoryPanel(b, s) {
    var goods=b.goods || s.board.filter(function(g){return g.slot===b.slot;});
    var fill=b.capacity>0 ? b.stored/b.capacity*100 : 0;
    var canSell=b.clearableQuantity===undefined ? goods.some(function(g){return g.quantity>(g.reserved || 0);}) : b.clearableQuantity>0;
    return '<section class="game-panel game-stock">'+panelHead('Goods',units(b.stored)+' / '+units(b.capacity))+
      '<div class="game-stock-progress">'+bar(fill,fill>=100?'k-bar-fill--full':'')+'</div><div class="game-goods">'+goods.map(function(g){
        return goodsRow(b,g,'<span class="game-item-count '+(g.capacity && g.quantity>=g.capacity?'k-money':'')+'">'+units(g.quantity)+(g.capacity?'<small> / '+units(g.capacity)+'</small>':'')+(g.reserved?'<small title="Kept for production or orders">'+units(g.reserved)+' saved</small>':'')+'</span><span class="game-unit-price">'+ym(g.unitPrice)+' each</span>');
      }).join('')+'</div><div class="game-inventory-actions">'+(document.getElementById('econ-building')?'':'<button type="button" class="game-small-button game-reserve'+(b.reserve?' is-active':'')+'" data-econ-action="reserve:'+b.slot+':'+(!b.reserve)+'" aria-pressed="'+!!b.reserve+'" title="Hold goods for orders. Production can still use ingredients.">'+(b.reserve?'✓ Saving goods':'Save for orders')+'</button>')+bigButton('sell:'+b.slot,'Clear stock',(b.clearStockValue==null?'':ym(b.clearStockValue)+' · ')+(s.clearStockPercent || 60)+'% price',!canSell,' k-btn--alt')+'</div></section>';
  }

  function operationsPanel(b, s) {
    return '<section class="game-panel game-operations">'+panelHead('Upgrades','')+upgradeRows(b,['production','sales','storage'])+'</section>';
  }

  function upgradeRows(b,kinds) {
    var names={production:'Production',sales:'Customers',storage:'Storage'};
    return '<div class="game-operation-list">'+kinds.map(function(kind){
      var u=(b.upgrades || {})[kind];
      if(!u) return '';
      var done=u.cost===null;
      var reasonId='game-upgrade-reason-'+b.slot+'-'+kind;
      return '<div class="game-operation"><div><strong>'+(kinds.length===1?'Level '+u.level:names[kind]+' <small>Lv '+u.level+'</small>')+'</strong><span>'+esc(done?'Complete':u.effect.replace(' base ', ' ')+(u.unlocksSpecialty?' · Specialty':''))+'</span>'+(u.consequence&&!done?'<small class="game-upgrade-impact '+(u.incomeDelta>0?'k-good':'')+'" title="Sustainable capacity estimate; current stock and committed deliveries can delay the change.">'+esc(u.consequence)+'</small>':'')+'</div><div class="game-upgrade-buy"><button class="game-small-button" type="button" data-econ-action="upgrade:'+b.slot+':'+kind+'"'+(!u.canBuy?' disabled':'')+' aria-label="'+esc('Upgrade '+names[kind]+(done?'':', '+ym(u.cost)))+'"'+(!u.canBuy&&!done?' aria-describedby="'+reasonId+'"':'')+' title="'+esc(u.why || u.consequence || u.effect)+'">'+(done?'MAX':ym(u.cost)+' ↑')+'</button>'+(!u.canBuy&&!done?'<small id="'+reasonId+'" class="game-upgrade-reason">'+esc(u.why || 'Keep earning to upgrade')+'</small>':'')+'</div></div>';
    }).join('')+'</div>';
  }

  function recipePanel(b, s) {
    var recipes=b.recipes || (b.recipe ? [b.recipe] : []);
    if(!recipes.length) return '<section class="game-panel">'+panelHead('Produces','No ingredients needed')+'<div class="game-direct-products">'+(b.goods || []).map(function(g){return '<div>'+goodIcon(b,g,false)+'<span>'+esc(g.name)+'</span></div>';}).join('')+'</div></section>';
    var direct=(b.goods || []).filter(function(g){return !g.inputs || !g.inputs.length;});
    return '<section class="game-panel">'+panelHead('Production chains',processingControl(b))+'<div class="game-panel-body game-recipe">'+direct.map(function(g){return '<div class="game-recipe-chain"><div class="econ-good-line"><span class="econ-good-name">'+goodIcon(b,g,false)+esc(g.name)+'</span><span>'+units(g.productionPerMinute)+' / min</span></div><span class="game-hint">No ingredients needed</span></div>';}).join('')+recipes.map(function(recipe){
      return '<div class="game-recipe-chain">'+recipe.inputs.map(function(i){
        var producer=s.buildings.find(function(p){return p.id===i.buildingId;}) || {id:i.buildingId};
        return '<div class="econ-good-line"><span class="econ-good-name">'+goodIcon(producer,i,false)+esc(i.name)+'</span><span class="'+(i.owned>=i.quantity?'k-good':'k-money')+'" title="'+units(i.owned)+' in stock">'+units(i.quantity)+(i.owned<i.quantity?' · Need '+units(i.quantity-i.owned):'')+'</span></div>';
      }).join('')+'<div class="econ-good-line game-recipe-output"><span class="econ-good-name">'+goodIcon(b,recipe.output,false)+'→ '+esc(recipe.output.name)+'</span><span>'+units(recipe.output.quantity)+'</span></div></div>';
    }).join('')+'</div></section>';
  }

  // A brief local reaction to skipping an order that was ready on screen.
  // Keep it across card re-renders while rapid replacements finish.
  var missedOrders = {};
  function reactToMissedOrder(index) {
    if(missedOrders[index])window.clearTimeout(missedOrders[index].timer);
    var reaction={until:performance.now()+500};
    missedOrders[index]=reaction;
    reaction.timer=window.setTimeout(function(){
      if(missedOrders[index]!==reaction)return;
      delete missedOrders[index];
      document.querySelectorAll('[data-missed-order="'+index+'"]').forEach(function(node){node.remove();});
    },500);
  }
  function missedOrderMarkup(index){
    var reaction=missedOrders[index];
    return reaction && reaction.until>performance.now()?'<span class="game-missed-order" data-missed-order="'+index+'" role="img" aria-label="Skipped a ready order"><span aria-hidden="true"><img src="./assets/game-art/reactions/crying-face-pixel.png" alt="" width="80" height="80"></span></span>':'';
  }

  function ordersMarkup(s) {
    return '<div class="game-card-grid game-order-grid" data-keep-scroll="orders">'+orderOffers(s).map(function(o,i){
      var relationship=o.customer==='breakfast';
      var note=relationship ? ((s.regularDeliveries||0)>=3?'Regulars earned · +20% roastery customers':(s.regularDeliveries||0)+'/3 visits → +20% roastery customers') : o.materials?'Materials reduce new-business costs':'';
      var rarity=['standard','large','rare','jackpot'].includes(o.rarity)?o.rarity:'standard';
      var label=o.rarityLabel || 'Standard';
      return '<section class="k-card game-order" data-rarity="'+rarity+'" data-order-slot="'+i+'">'+missedOrderMarkup(i)+'<h3>'+esc(o.name)+'<small class="game-order-tier">'+esc(label)+'</small></h3>'+(note?'<p class="game-order-purpose">'+esc(note)+'</p>':'')+'<div class="game-order-caption">Have / need</div><div class="game-order-items" data-order-items="'+i+'" data-order-id="'+esc(o.id)+'"><div class="game-order-goods">'+o.requirements.map(function(g){
        var building=s.buildings.find(function(b){return b.id===g.buildingId;}) || {id:g.buildingId};
        return '<div class="econ-good-line"><span class="econ-good-name">'+goodIcon(building,g,false)+esc(g.name)+'</span><span class="'+(g.owned>=g.quantity?'k-good':'k-money')+'">'+units(g.owned)+' / '+units(g.quantity)+'</span></div>';
      }).join('')+'</div></div><div class="game-order-reward"><span title="Paid after you deliver all requested goods">'+ym(o.reward)+'</span>'+(o.rewardPercent?'<small>'+mult(o.rewardPercent/100)+'× retail</small>':'')+(o.materials?'<span>+'+materialAmount(o.materials)+'</span>':'')+'</div><div class="game-order-controls">'+bigButton('fulfill:'+i+':'+o.id,'Deliver',o.canFulfill?'Ready':o.why || 'Waiting for goods',!o.canFulfill)+(s.rulesRevision>=2?'<button class="game-small-button game-order-commit" type="button" aria-pressed="'+!!o.committed+'" data-econ-action="commit:'+i+':'+esc(o.id)+'" title="Save only this order’s quantities. Other goods keep selling. Recipes cannot consume committed stock.">'+(o.committed?'Release goods':'Save for this order')+'</button>':'')+'</div><button class="game-text-button" type="button" data-econ-action="replace:'+i+':'+esc(o.id)+'" title="Free reroll · Standard 65%, Large 25%, Rare 8%, Jackpot 2% · Rewards require delivery">New order ↻ <small>Free</small></button></section>';
    }).join('')+'</div>';
  }

  function customerAction(action, slot, customerId, contractId) {
    return 'customer:'+action+':'+slot+':'+encodeURIComponent(customerId || '')+':'+encodeURIComponent(contractId || '');
  }

  function customerRequirements(s, requirements, active) {
    return '<div class="game-contract-goods">'+requirements.map(function(g){
      var building=s.buildings.find(function(item){return item.id===g.buildingId;}) || {id:g.buildingId};
      var held=Number(g.reserved || 0), ready=active && held>=g.quantity;
      return '<div class="econ-good-line game-customer-requirement"><span class="econ-good-name">'+goodIcon(building,g,false)+'<span>'+esc(g.name)+'</span></span><span class="'+(ready?'k-good':'')+'" title="'+(active?'Saved for this customer’s next shipment':'Required for every shipment')+'">'+(active?units(held)+' / ':'')+units(g.quantity)+'</span></div>';
    }).join('')+'</div>';
  }

  function customerOrderChoice(current) {
    if(!current.largerOrder && !current.largerOffer)return '';
    var offer=current.largerOffer;
    var terms=offer?(offer.requirements || []).map(function(g){return units(g.quantity)+' '+esc(g.name);}).join(' + ')+' → <strong>'+ym(offer.reward)+'</strong> · same interval':'Return to the original goods and pay.';
    return '<div class="game-contract-order-choice"><span>'+terms+'</span><button id="game-customer-size" class="game-small-button" type="button" data-econ-action="'+customerAction(current.largerOrder?'downgrade':'upgrade',current.slot,'',current.id)+'" title="Changing order size restarts the next shipment timer.">'+(current.largerOrder?'Use smaller order':'Take larger order')+'</button></div>';
  }

  function customerContractsMarkup(s) {
    var contracts=s.customerContracts;
    if(!contracts)return '';
    var active=contracts.active || [], customers=contracts.customers || [], slots=Number(contracts.slots || 2);
    customerSlot=Math.max(0,Math.min(customerSlot,slots-1));
    var current=active.find(function(item){return item.slot===customerSlot;});
    var switching=!!current && current.id===customerSwitchId;
    var choosing=!current || switching;
    var slotMarkup=Array.from({length:slots},function(_,index){
      var contract=active.find(function(item){return item.slot===index;});
      return '<button id="game-customer-slot-'+index+'" type="button" data-customer-slot="'+index+'" aria-pressed="'+(index===customerSlot)+'" aria-label="Slot '+(index+1)+': '+esc(contract?contract.name+', '+(contract.paused?'paused':'active'):'open')+'">'+(index+1)+' · '+(contract?(contract.paused?'Paused':'Active'):'Open')+'</button>';
    }).join('');
    var content='';
    if(choosing){
      var taken=active.map(function(item){return item.customerId;});
      var eligible=customers.filter(function(item){return item.available && taken.indexOf(item.id)<0;});
      var choice=eligible.find(function(item){return item.id===customerChoices[customerSlot];}) || eligible[0];
      if(choice)customerChoices[customerSlot]=choice.id;
      var options=customers.map(function(item){
        var unavailable=!item.available || taken.indexOf(item.id)>=0;
        return '<option value="'+esc(item.id)+'"'+(unavailable?' disabled':'')+(choice && item.id===choice.id?' selected':'')+'>'+esc(item.name)+(taken.indexOf(item.id)>=0?' · Already signed':!item.available?' · '+esc(item.unlockText || 'Grow your town to unlock'):'')+'</option>';
      }).join('');
      content='<div class="game-contract-summary"><label for="game-customer-choice">'+(switching?'Replace '+esc(current.name):'Choose a regular customer')+'</label><select id="game-customer-choice"'+(!choice?' disabled':'')+'>'+(!choice?'<option>No customers available</option>':'')+options+'</select>'+(choice?'<p class="game-contract-description">'+esc(choice.description)+'</p><div class="game-contract-pay"><strong>'+ym(choice.reward)+'</strong><span>per shipment · every '+duration(choice.intervalSeconds)+'</span></div>':'<p class="game-contract-description">New businesses bring new customers.</p>')+'</div><div class="game-contract-supply">'+(choice?'<div class="game-contract-caption">Goods per shipment</div>'+customerRequirements(s,choice.requirements || [],false):'')+'<div class="game-contract-controls">'+bigButton(customerAction(switching?'switch':'accept',customerSlot,choice && choice.id,current && current.id),switching?'Switch customer':'Sign customer','',!choice)+(switching?'<button id="game-customer-cancel" class="game-text-button" type="button" data-customer-cancel>Keep current customer</button>':'')+'</div><p class="game-contract-help">'+(switching?'Switching frees held goods and starts a new shipment timer.':'First shipment after the full interval. Recipes and saved orders get goods first.')+'</p></div>';
    }else{
      var status=current.paused?'Paused · goods released':current.status==='waiting'?'Waiting for goods · no penalty':'Next shipment in <span data-econ-countdown="'+Math.max(0,current.nextDeliverySeconds || 0)+'">'+duration(current.nextDeliverySeconds)+'</span>';
      content='<div class="game-contract-summary"><h3>'+esc(current.name)+'</h3><div class="game-contract-pay"><strong>'+ym(current.reward)+'</strong><span>per shipment · every '+duration(current.intervalSeconds)+'</span></div><p class="game-contract-status'+(current.paused?' is-paused':'')+'">'+status+'</p><span class="game-contract-history">'+units(current.deliveries)+' shipments · '+ym(current.earned)+' earned</span></div><div class="game-contract-supply"><div class="game-contract-caption">Saved / needed for next shipment</div>'+customerRequirements(s,current.requirements || [],true)+'<div class="game-contract-controls"><button id="game-customer-toggle" class="game-small-button" type="button" data-econ-action="'+customerAction(current.paused?'resume':'pause',customerSlot,'',current.id)+'">'+(current.paused?'Resume':'Pause')+'</button><button id="game-customer-switch" class="game-small-button" type="button" data-customer-switch="'+esc(current.id)+'">Switch</button><button id="game-customer-release" class="game-text-button" type="button" data-econ-action="'+customerAction('release',customerSlot,'',current.id)+'">Release</button></div>'+(customerOrderChoice(current) || '<p class="game-contract-help">'+(current.paused?'Resume starts a new shipment timer.':'Ships automatically when ready, including while you’re away.')+'</p>')+'</div>';
    }
    var next=contracts.nextUnlock;
    return '<section class="game-panel game-customer-contracts" aria-label="Customer contracts">'+panelHead('Regular customers',active.length+' / '+slots+' signed')+'<p class="game-contract-intro">Repeat deliveries, sent automatically. Short of goods? Customers wait.</p><div class="game-contract-slots" role="group" aria-label="Customer slots">'+slotMarkup+'</div><div class="game-contract-body">'+content+'</div><div class="game-contract-footer"><span>'+ym(contracts.earned)+' earned</span><span>'+(next?'Slot '+next.slots+' at '+next.buildings+' businesses':'All '+slots+' slots unlocked')+'</span></div></section>';
  }

  function renderProductionInventory(el,s,b,market) {
    if(market){
      el.innerHTML=notice(s)+'<div class="game-market-surface'+(s.customerContracts?' has-contracts':'')+'"><div class="game-market-income'+(s.customerContracts?' has-contracts':'')+'"><section class="game-market-orders" aria-label="Delivery orders">'+panelHead('Delivery orders','One-time rewards')+ordersMarkup(s)+'</section>'+customerContractsMarkup(s)+'</div></div>'+statusLine();
      return;
    }
    var goods=b.goods || s.board.filter(function(g){return g.slot===b.slot;});
    var canSell=b.clearableQuantity===undefined?goods.some(function(g){return g.quantity>(g.reserved || 0);}):b.clearableQuantity>0;
    var fill=b.capacity>0?b.stored/b.capacity*100:0;
    var surplus='<section class="game-panel">'+panelHead('Sell surplus',units(b.clearableQuantity || 0)+' goods')+'<div class="game-surplus-sale"><span>'+(s.clearStockPercent || 60)+'% of retail price · '+(b.reserve?'Includes manually held goods':'Keeps recipe and order supplies')+'</span>'+bigButton('sell:'+b.slot,'Sell surplus · '+ym(b.clearStockValue || 0),'',!canSell,' k-btn--alt')+(!canSell?why('No surplus yet. Goods needed for recipes and orders stay saved.'):'')+'</div></section>';
    el.innerHTML=notice(s)+businessPicker(s,b)+'<div class="game-purpose-layout"><section class="game-panel game-inventory-table">'+panelHead('Stock',units(b.stored)+' / '+units(b.capacity)+' capacity')+'<div class="game-stock-progress">'+bar(fill,fill>=100?'k-bar-fill--full':'')+'</div><div class="game-inventory-head"><span>Item</span><span>In stock</span><span>Saved</span></div><div class="game-inventory-rows" data-keep-scroll="inventory">'+goods.map(function(g){return '<div class="game-inventory-row"><span class="game-inventory-good">'+goodIcon(b,g,false)+'<span><strong>'+esc(g.name)+'</strong>'+bar(g.capacity?g.quantity/g.capacity*100:0)+'</span></span><span>'+units(g.quantity)+(g.capacity?'<small> / '+units(g.capacity)+'</small>':'')+'</span><span>'+units(g.reserved || 0)+'</span></div>';}).join('')+'</div><p class="game-hint game-inventory-explainer">Saved goods are held for recipes, deliveries, or paused shop sales.</p></section><div class="game-purpose-side"><section class="game-panel">'+panelHead('Shop sales',b.reserve?'Paused':'Automatic')+'<div class="game-panel-body"><button type="button" class="game-small-button game-reserve'+(b.reserve?' is-active':'')+'" data-econ-action="reserve:'+b.slot+':'+(!b.reserve)+'" aria-pressed="'+!!b.reserve+'">'+(b.reserve?'Resume shop sales':'Hold goods')+'</button><p class="game-hint">'+(b.reserve?'Goods stay here instead of selling to walk-in customers. Recipes can still use them.':'Hold goods to stop walk-in sales for this business. Use Market to save for a specific order.')+'</p></div></section>'+surplus+'</div></div>'+statusLine();
  }

  function businessPicker(s,b){
    return '<div class="game-business-picker">'+art({buildingId:b.id,buildingName:b.name,paused:true})+'<label for="game-business-choice">Business</label><select id="game-business-choice">'+s.buildings.map(function(item){return '<option value="'+item.slot+'"'+(item.slot===b.slot?' selected':'')+'>'+esc(item.name)+'</option>';}).join('')+'</select></div>';
  }

  function renderLicense(el,s) {
    var c=s.checklist || {}, keep=s.keepPercent==null?50:s.keepPercent;
    var previousGoals=document.getElementById('game-goals');
    var goalsOpen=previousGoals?previousGoals.open:window.matchMedia('(min-width:851px)').matches;
    var items=[
      [!!c.lv25,'Reach a level milestone',(s.checklistText || [])[0] || 'Reach level 25 on a building'],
      [!!c.auto,'Install Auto Control','Boost one of your buildings'],
      [(c.goodSales||0)>=s.goodSalesNeeded,'Make good sales',Math.min(c.goodSales||0,s.goodSalesNeeded)+' / '+s.goodSalesNeeded+' sales at ×'+mult(s.goodSalePrice)+' or more'],
      [!!c.quiz,'Pass the quiz',''],
      [s.buildingsOwned>=s.gateTier,'Grow your collection',Math.min(s.buildingsOwned,s.gateTier)+' / '+s.gateTier+' buildings']
    ];
    if (productionModel(s)) {
      items[0]=[!!c.lv25,(s.checklistText || [])[0] || 'Production level 3',''];
      items[1]=[!!c.auto,(s.checklistText || [])[1] || 'Upgrade customers',''];
      items[2]=[(c.goodSales||0)>=s.goodSalesNeeded || (s.customerUnitsSold||0)>=(s.customerUnitsNeeded||100),'Serve your customers',Math.min(c.goodSales||0,s.goodSalesNeeded)+'/'+s.goodSalesNeeded+' deliveries OR '+Math.min(s.customerUnitsSold||0,s.customerUnitsNeeded||100)+'/'+(s.customerUnitsNeeded||100)+' goods sold'];
    }
    var done=items.filter(function(i){return i[0];}).length;
    var questions=quiz && quiz.questions || [];
    quizStep=Math.min(quizStep,Math.max(0,questions.length-1));
    var quizHtml=c.quiz?'<div class="game-quiz-complete"><span class="k-good">✓ Quiz passed</span></div>':questions.length?'<div class="game-quiz-top"><span>Question '+(quizStep+1)+' / '+questions.length+'</span><span>'+quiz.passMark+' correct to pass</span></div><form id="econ-quiz-form">'+questions.map(function(q,qi){return '<fieldset class="game-quiz-question"'+(qi===quizStep?'':' hidden')+'><legend>'+esc(q.prompt.replace(/^TODO\s*[-—:]\s*/i,''))+'</legend>'+q.options.map(function(opt,oi){return '<label class="k-opt"><input type="radio" name="q'+qi+'" value="'+oi+'"><span>'+esc(opt)+'</span></label>';}).join('')+'</fieldset>';}).join('')+'</form><div class="game-quiz-navigation"><button type="button" class="game-text-button" data-quiz-step="-1"'+(quizStep===0?' disabled':'')+'>← Back</button>'+(quizStep<questions.length-1?'<button type="button" class="game-small-button" data-quiz-step="1">Next →</button>':bigButton('quiz','Check answers','',false))+'</div>':'<p class="game-hint">Loading quiz…</p>';
    el.innerHTML=notice(s)+'<div class="game-license-layout'+(s.gateOpen?'':' game-license-locked')+(c.quiz?' game-license-quiz-done':'')+'"><section class="game-panel">'+panelHead('Your licence',done+'/5 goals')+'<div class="game-licence-summary">'+assetIcon('badges/licence_'+(s.gateOpen?'unlocked':'locked')+'.png','game-large-badge')+'<div><strong>'+(s.gateOpen?'Trading unlocked!':'Unlock trading')+'</strong>'+bar(done/5*100,'k-bar-fill--gold')+'</div></div><details id="game-goals"'+(goalsOpen?' open':'')+'><summary>Milestones</summary><div class="game-checklist">'+items.map(function(item){return '<div class="game-check"><span class="game-check-box '+(item[0]?'is-done':'')+'">'+(item[0]?'✓':'')+'</span><div><strong>'+item[1]+'</strong><span>'+esc(item[2])+'</span></div></div>';}).join('')+'</div></details></section>'+(!c.quiz?'<section class="game-panel">'+panelHead('Business quiz','')+'<div class="game-panel-body">'+quizHtml+'</div></section>':'')+(s.gateOpen?'<section class="game-panel game-invest">'+panelHead('Keep or invest','')+'<div class="game-panel-body">'+(s.gateOpen?'<p class="game-hint">Choose how much stays in your business.</p><input class="k-range" type="range" min="0" max="100" step="5" id="econ-keep-range" value="'+keep+'"><div class="k-bar-label" id="econ-keep-label"><span>Keep '+keep+'%</span><span>Invest '+(100-keep)+'%</span></div>'+bigButton('keep','Save split','',false)+linkButton('./port_trading.html','Open trading desk ↗',' k-btn--alt'):'<p class="game-hint">Complete all five goals to unlock investing.</p>')+'</div></section>':'')+'</div>'+statusLine();
    if(productionModel(s) && s.gateOpen){
      var desk=el.querySelector('.game-invest');
      if(desk)desk.innerHTML=panelHead('Practice investing','')+'<div class="game-panel-body"><p class="game-hint">Your trading desk uses a separate practice portfolio. Your town keeps its cash.</p>'+linkButton('./port_trading.html','Open trading desk ↗',' k-btn--alt')+'</div>';
    }
  }

  // The dashboard stays in the terminal style of the rest of index.html.
  function renderDashboard(el, s) {
    var board = Array.isArray(s.leaderboard) ? s.leaderboard : [];
    function rows(pairs) {
      return '<div class="data-table-wrap"><table class="data-table"><tbody>' +
        pairs.map(function (p) {
          return '<tr><td class="muted">' + esc(p[0]) + '</td><td class="' +
            (p[2] || 'amber') + '">' + p[1] + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    el.innerHTML = '<div class="panelhead"><div class="hdr">YOUR BUSINESS</div></div>' +
      rows([
        ['Net worth', ym(s.netWorth)],
        ['Cash', ym(s.cash)],
        ['Sales / min', ym(s.incomePerMinute == null ? s.revenuePerDay/1440 : s.incomePerMinute)],
        ['Buildings owned', s.buildingsOwned + ' of ' + s.tierCount],
        ['Licence', s.gateOpen ? 'open' : 'locked', s.gateOpen ? 'up' : 'muted'],
      ]) +
      (s.classCompetition === true ? '<div class="hdr">CLASS LEADERBOARD</div>' +
      '<div class="data-table-wrap"><table class="data-table"><thead><tr>' +
      '<th>#</th><th>STUDENT</th><th>NET WORTH</th></tr></thead><tbody>' +
      board.map(function (row) {
        return '<tr' + (row.you ? ' class="amber"' : '') + '><td>' + row.rank + '</td><td>' +
          esc(row.name) + (row.you ? ' (you)' : '') + '</td><td>' + ym(row.net_worth) + '</td></tr>';
      }).join('') +
      '</tbody></table></div>' : '') +
      '<div class="bld-action-row"><a class="bld-btn" href="./buildings.html">OPEN TOWN ↗</a></div>';
  }

  // id, renderer, kid mode
  var SCREENS = [
    ['econ-building', renderBuilding, true],
    ['econ-warehouse', renderWarehouse, true],
    ['econ-auto', renderAuto, true],
    ['econ-market', renderMarket, true],
    ['econ-license', renderLicense, true],
    ['econ-dashboard', renderDashboard, false],
  ];

  function mounted() {
    return SCREENS.filter(function (screen) { return document.getElementById(screen[0]); });
  }

  function renderOffline(message) {
    snapshot = null;
    clearCompetition();
    mounted().forEach(function (screen) {
      document.getElementById(screen[0]).innerHTML =
        '<div class="k-card"><h3 class="k-card-title">Not in a class</h3>' +
        '<div class="k-note">' + esc(message) + '</div>' +
        linkButton('./join.html', 'JOIN A CLASS') + '</div>';
    });
  }

  function renderCashChip(s) {
    var rightMeta = document.querySelector('.right-meta');
    if (!rightMeta) return;
    var chip = document.getElementById('game-cash-chip');
    if (!chip) {
      chip = document.createElement('span');
      chip.id = 'game-cash-chip';
      chip.className = 'chip amber';
      rightMeta.insertBefore(chip, rightMeta.firstChild);
    }
    chip.textContent = ((session && session.name) || s.name || 'PLAYER') + (document.getElementById('game-hud')?'':' | ' + ym(s.cash));
  }

  function render() {
    if (!snapshot) return;
    var hud=document.getElementById('game-hud');
    if(hud) hud.innerHTML=resourceBar(snapshot);
    var scrollPositions=Array.from(document.querySelectorAll('[data-keep-scroll]')).map(function(node){return {key:node.dataset.keepScroll,top:node.scrollTop,left:node.scrollLeft};});
    var focused = document.activeElement;
    var selectedControl=focused && focused.getAttribute('data-select-building');
    var action = focused && focused.getAttribute('data-econ-action');
    var focusId=focused && focused.id;
    var focusedInput = focused && focused.matches('#econ-license input')
      ? { name: focused.name, value: focused.value, id: focused.id } : null;
    var logistics=document.getElementById('mercury-logistics');
    var logisticsOpen=logistics && logistics.open;
    var edits = Array.from(document.querySelectorAll('#econ-license input')).map(function (input) {
      return { name: input.name, value: input.value, checked: input.checked, id: input.id };
    });
    mounted().forEach(function (screen) {
      var el = document.getElementById(screen[0]);
      if (screen[2]) el.classList.add('econ-kid');
      screen[1](el, snapshot);
    });
    var deliveries=document.getElementById('game-deliveries-content');
    if(deliveries) deliveries.innerHTML=contractsMarkup(snapshot);
    var breakfast=document.getElementById('game-breakfast-content');
    if(breakfast) breakfast.innerHTML=breakfastMarkup(snapshot);
    scrollPositions.forEach(function(position){document.querySelectorAll('[data-keep-scroll]').forEach(function(node){if(node.dataset.keepScroll===position.key){node.scrollTop=position.top;node.scrollLeft=position.left;}});});
    if(selectedSlot!==lastRenderedSlot || !scrollPositions.length){
      var selectedButton=document.querySelector('[data-select-building="'+selectedSlot+'"]');
        var rosterList=document.querySelector('.game-roster-list') || document.querySelector('.game-town-grid');
      if(selectedButton && rosterList){
        var itemRect=selectedButton.getBoundingClientRect(), listRect=rosterList.getBoundingClientRect();
        if(itemRect.left<listRect.left) rosterList.scrollLeft+=itemRect.left-listRect.left;
        else if(itemRect.right>listRect.right) rosterList.scrollLeft+=itemRect.right-listRect.right;
        if(itemRect.top<listRect.top) rosterList.scrollTop+=itemRect.top-listRect.top;
        else if(itemRect.bottom>listRect.bottom) rosterList.scrollTop+=itemRect.bottom-listRect.bottom;
      }
    }
    lastRenderedSlot=selectedSlot;
    if(selectedControl!==null && selectedControl!==undefined){var selector=document.querySelector('[data-select-building="'+selectedControl+'"]');if(selector)selector.focus({preventScroll:true});}
    if(logisticsOpen && document.getElementById('mercury-logistics')) document.getElementById('mercury-logistics').open=true;
    edits.forEach(function (edit) {
      document.querySelectorAll('#econ-license input').forEach(function (input) {
        if (edit.id && input.id === edit.id) input.value = edit.value;
        else if (input.name === edit.name && input.value === edit.value) input.checked = edit.checked;
      });
    });
    if (focusedInput) {
      Array.from(document.querySelectorAll('#econ-license input')).some(function (input) {
        if (focusedInput.id ? input.id !== focusedInput.id : input.name !== focusedInput.name || input.value !== focusedInput.value) return false;
        input.focus({ preventScroll: true }); return true;
      });
    }
    var keepRange = document.getElementById('econ-keep-range');
    if (keepRange) keepRange.dispatchEvent(new Event('input', { bubbles: true }));
    if (action) {
      var buttons = document.querySelectorAll('[data-econ-action]');
      Array.from(buttons).some(function (button) {
        var currentAction=button.getAttribute('data-econ-action');
        var togglePrefix=/^(reserve|processing|replace):/.test(action) ? action.split(':').slice(0,2).join(':')+':' : null;
        if ((currentAction !== action && (!togglePrefix || currentAction.indexOf(togglePrefix)!==0)) || button.disabled) return false;
        button.focus({ preventScroll: true }); return true;
      });
    }
    if(focusId==='game-expansion-choice'){var expansionChoice=document.getElementById(focusId);if(expansionChoice)expansionChoice.focus({preventScroll:true});}
    if(focusId==='game-business-choice' || focusId==='game-business-focus'){var businessChoice=document.getElementById(focusId);if(businessChoice)businessChoice.focus({preventScroll:true});}
    var openBreakfast=document.querySelector('#game-breakfast[open]');
    if(openBreakfast && !openBreakfast.contains(document.activeElement))openBreakfast.querySelector('[data-close-breakfast]').focus({preventScroll:true});
    if(window.YomamaFit)window.YomamaFit.render();
    if(focusId && /^(game-customer-|game-tab-)/.test(focusId)){var customerControl=document.getElementById(focusId);if(customerControl && !customerControl.disabled)customerControl.focus({preventScroll:true});}
    renderCashChip(snapshot);
    var stats=document.getElementById('buildings-side-stats');
    if(stats) stats.innerHTML=line('Buildings owned',snapshot.buildingsOwned)+line('Net worth',ym(snapshot.netWorth))+line('Revenue / day',ym(snapshot.revenuePerDay));
    var messages=document.getElementById('buildings-lab-log');
    if(messages) messages.textContent=statusMessage ? statusMessage.text : (snapshot.tickerLines.join(' · ') || 'Your class market is open.');
    var ticker=document.getElementById('ticker');
    if(ticker && snapshot.tickerLines.length) {
      var headline=snapshot.tickerLines.join(' · ');
      ticker.innerHTML='<span class="ticker-item">'+esc(headline)+'</span><span class="ticker-item" aria-hidden="true">'+esc(headline)+'</span>';
    }
    // hide the link to Part 2 until the licence is open
    document.querySelectorAll('[data-econ-gate]').forEach(function (node) {
      node.hidden = !snapshot.gateOpen;
    });
  }

  var statusTimer = null;
  function setStatus(text, tone) {
    if(statusTimer) window.clearTimeout(statusTimer);
    statusMessage = text ? { text: text, tone: tone } : null;
    var messages=document.getElementById('buildings-lab-log');if(messages && text)messages.textContent=text;
    document.querySelectorAll('[data-econ-status]').forEach(function (el) {
    {
      el.textContent = text || '';
      el.className = 'k-status' + (tone === 'error' ? ' k-status--bad' : (tone === 'success' ? ' k-status--good' : ''));
    }
    });
    if(text && tone==='success') statusTimer=window.setTimeout(function(){setStatus('', '');},8000);
  }

  function apply(payload) {
    if (!payload) return;
    // Login is disabled for now: the server hands out a seat on first contact.
    // Keep it, so every page in this browser is the same player.
    if (payload.token && (!session || session.token !== payload.token)) {
      session = { token: payload.token, name: payload.name || 'PLAYER', code: payload.code || '' };
      try { window.localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch (_) {}
    }
    snapshot = payload;
    render();
    window.dispatchEvent(new CustomEvent('yomama:econ',{detail:payload}));
    if(payload.overnightReport) showOvernight(payload.overnightReport);

  }

  function clearCompetition() {
    if (snapshot) {
      snapshot.classCompetition = false;
      snapshot.leaderboard = [];
      var dashboard = document.getElementById('econ-dashboard');
      if (dashboard) renderDashboard(dashboard, snapshot);
    }
    window.dispatchEvent(new CustomEvent('yomama:econ', {
      detail: snapshot || { classCompetition: false, gateOpen: false }
    }));
  }

  function refresh() {
    if (busy || document.visibilityState === 'hidden') return Promise.resolve();
    return fetchState().then(apply).catch(function (err) {
      if (err && err.status === 401) renderOffline('This class session has expired. Join again to keep playing.');
      else {
        clearCompetition();
        setStatus('Connection lost. We will try again shortly.', 'error');
      }
    });
  }

  // --------------------------------------------------------------- actions --
  function act(name) {
    if (busy) {
      if(name.indexOf('replace:')===0)pendingRerolls.push(Number(name.split(':')[1]));
      return;
    }
    var path = '/' + name;
    var body = {};
    var skippedReady = false;
    if (name.indexOf('customer:') === 0) {
      var customerBits=name.split(':');path='/customers';body={action:customerBits[1],slot:Number(customerBits[2])};
      if(customerBits[3])body.customerId=decodeURIComponent(customerBits[3]);
      if(customerBits[4])body.contractId=decodeURIComponent(customerBits[4]);
    } else if (name.indexOf('breakfast:') === 0) {
      var eventBits=name.split(':');path='/event/breakfast';body={action:eventBits[1]};
      if(body.action==='deliver')body.orderId=eventBits[2];
      else if(body.action==='cancel')body.jobId=Number(eventBits[2]);
      else if(eventBits[2])body.recipe=eventBits[2];
    } else if (name.indexOf('sell:') === 0) {
      path = '/sell';
      body = { slot: Number(name.split(':')[1]) };
    } else if (name.indexOf('upgrade:') === 0) {
      var upgrade=name.split(':');path='/upgrade';body={slot:Number(upgrade[1]),kind:upgrade[2]};
    } else if (name.indexOf('reserve:') === 0) {
      var reserve=name.split(':');path='/reserve';body={slot:Number(reserve[1]),reserve:reserve[2]==='true'};
    } else if (name.indexOf('processing:')===0) {
      var processing=name.split(':');path='/processing';body={slot:Number(processing[1]),enabled:processing[2]==='true'};
    } else if (name.indexOf('focus:')===0) {
      var focus=name.split(':');path='/focus';body={slot:Number(focus[1]),focus:focus[2]};
    } else if (/^(fulfill|replace|commit):/.test(name)) {
      var order=name.split(':');path='/orders/'+order[0];body={offerIndex:Number(order[1]),orderId:order.slice(2).join(':')};
      var oldOrder=snapshot && orderOffers(snapshot)[body.offerIndex];
      if(order[0]==='commit')body.committed=!(oldOrder && oldOrder.committed);
      skippedReady=order[0]==='replace' && !!oldOrder && oldOrder.id===body.orderId && oldOrder.canFulfill===true;
    } else if (/^(level|auto|expand|contract):/.test(name)) {
      var bits=name.split(':');path=bits[0]==='contract' ? '/contracts/accept' : '/'+bits[0];
      body[bits[0]==='expand' ? 'tier' : bits[0]==='contract' ? 'offerIndex' : 'slot']=Number(bits[1]);
    } else if (name === 'quiz') {
      path = '/quiz';
      body = { answers: readQuizAnswers() };
    } else if (name === 'keep') {
      path = '/keep';
      var range = document.getElementById('econ-keep-range');
      body = { percent: range ? Number(range.value) : 0 };
    }

    busy = true;
    document.querySelectorAll('[data-econ-action]').forEach(function(button){button.disabled=button.dataset.econAction.indexOf('replace:')!==0;button.setAttribute('aria-busy','true');});
    request('POST', path, body).then(function (payload) {
      busy = false;
      var receipt = payload.receipt;
      if(skippedReady)reactToMissedOrder(body.offerIndex);
      if(name.indexOf('customer:')===0)customerSwitchId=null;
      apply(payload);
      if(name.indexOf('customer:')===0){var nextCustomerControl=document.getElementById(body.action==='release'?'game-customer-choice':body.action==='upgrade' || body.action==='downgrade'?'game-customer-size':'game-customer-toggle');if(nextCustomerControl)nextCustomerControl.focus({preventScroll:true});}
      if (productionModel(payload)) {
        if (name.indexOf('customer:')===0) setStatus(receipt && receipt.message || ({accept:'Customer signed · automatic shipments start after the first interval',switch:'Customer switched · a new shipment timer has started',pause:'Customer paused · held goods released',resume:'Customer resumed · a new shipment timer has started',release:'Customer released · slot and goods available',upgrade:'Larger order accepted · a new shipment timer has started',downgrade:'Smaller order restored · a new shipment timer has started'}[body.action]),'success');
        else if (receipt && receipt.kind === 'breakfast') setStatus(receipt.message,'success');
        else if (receipt && receipt.kind === 'sell') setStatus('Stock sold · '+ym(receipt.net == null ? receipt.gross : receipt.net),'success');
        else if (name.indexOf('upgrade:')===0) setStatus(receipt && receipt.consequence || 'Upgrade complete','success');
        else if (name.indexOf('commit:')===0) setStatus(body.committed?'Saving this order’s goods · surplus keeps selling':'Goods released to customers and recipes','success');
        else if (name.indexOf('focus:')===0) setStatus('Specialty changed · check your new output','success');
        else if (name.indexOf('reserve:')===0) setStatus(body.reserve?'Saving goods for orders':'Customer sales resumed','success');
        else if (name.indexOf('processing:')===0) setStatus(body.enabled?'Processing resumed':'Recipes paused','success');
        else if (name.indexOf('fulfill:')===0) setStatus('Delivered · '+ym(receipt && receipt.reward)+(receipt && receipt.materials?' · +'+materialAmount(receipt.materials):''),'success');
        else if (name.indexOf('replace:')===0) setStatus(skippedReady?'':'New order ready','success');
        else if (name.indexOf('expand:')===0) setStatus('Construction started','success');
        else if (payload.quiz) setStatus(payload.quiz.passed?'Quiz passed':'Score '+payload.quiz.score+' / '+payload.quiz.total,payload.quiz.passed?'success':'error');
        else if (name==='keep') setStatus('Split saved','success');
      } else if (receipt && receipt.kind === 'sell') {
        setStatus('Sold your ' + receipt.name + ' for ' + ym(receipt.net) + ' (gross '+ym(receipt.gross)+', +'+receipt.premiumSalePct+'% fresh goods). Tax took ' +
          percent(receipt.rate) + ' (' + ym(receipt.tax) + ').', 'success');
      } else if (receipt && receipt.kind === 'level') {
        setStatus('Your building is now level ' + receipt.level + '. It cost ' + ym(receipt.cost) + '.', 'success');
      } else if (receipt && receipt.kind === 'auto') {
        setStatus('Auto Control installed for ' + ym(receipt.cost) + '. Your output is now ' +
          receipt.auto + ' times bigger.', 'success');
      } else if (receipt && receipt.kind === 'expand') {
        setStatus('Building started for ' + ym(receipt.cost) + '. Come back when the timer runs out.', 'success');
      } else if (receipt && receipt.kind === 'contract') {
        setStatus('Delivery accepted. New goods go to the contract first.','success');
      } else if (payload.quiz) {
        setStatus(payload.quiz.passed
          ? 'You passed: ' + payload.quiz.score + ' out of ' + payload.quiz.total + '.'
          : 'Not yet: ' + payload.quiz.score + ' out of ' + payload.quiz.total +
            '. You need ' + payload.quiz.passMark + '. Have another go.',
          payload.quiz.passed ? 'success' : 'error');
      } else if (name === 'keep') {
        setStatus('Saved. You keep ' + payload.keepPercent + '% in the business.', 'success');
      }
      if(pendingRerolls.length){
        var nextSlot=pendingRerolls.shift(),nextOrder=orderOffers(snapshot)[nextSlot];
        if(nextOrder)act('replace:'+nextSlot+':'+nextOrder.id);
      }
    }).catch(function (err) {
      busy = false;
      pendingRerolls=[];
      if (err && err.status === 401) {
        renderOffline('This class session has expired. Join again to keep playing.');
        return;
      }
      setStatus((err && err.message) || 'The server said no.', 'error');
      refresh();
    });
  }

  function readQuizAnswers() {
    if (!quiz) return [];
    return quiz.questions.map(function (_q, qi) {
      var checked = document.querySelector('input[name="q' + qi + '"]:checked');
      return checked ? Number(checked.value) : -1;
    });
  }

  document.addEventListener('close', function(event){
    if(event.target.id==='game-breakfast'){
      var trigger=document.querySelector('[data-game-breakfast]');
      if(trigger)trigger.focus({preventScroll:true});
    }
  },true);

  document.addEventListener('click', function (event) {
    var customerSlotButton=event.target.closest('[data-customer-slot]');
    if(customerSlotButton){customerSlot=Number(customerSlotButton.dataset.customerSlot);customerSwitchId=null;render();return;}
    var customerSwitch=event.target.closest('[data-customer-switch]');
    if(customerSwitch){customerSwitchId=customerSwitch.dataset.customerSwitch;render();var chooser=document.getElementById('game-customer-choice');if(chooser)chooser.focus({preventScroll:true});return;}
    if(event.target.closest('[data-customer-cancel]')){customerSwitchId=null;render();var switchControl=document.getElementById('game-customer-switch');if(switchControl)switchControl.focus({preventScroll:true});return;}
    var breakfastDialog=document.getElementById('game-breakfast');
    if(breakfastDialog && event.target.closest('[data-game-breakfast]')){breakfastDialog.showModal();return;}
    if(breakfastDialog && event.target.closest('[data-close-breakfast]')){breakfastDialog.close();return;}
    var chosen=event.target.closest('[data-select-building]');
    if(chosen){selectedSlot=Number(chosen.dataset.selectBuilding);render();return;}
    var step=event.target.closest('[data-quiz-step]');
    if(step){quizStep+=Number(step.dataset.quizStep);render();var question=document.querySelector('.game-quiz-question:not([hidden]) input');if(question)question.focus();return;}
    var deliveryDialog=document.getElementById('game-deliveries');
    if(deliveryDialog && event.target.closest('[data-game-deliveries]')){deliveryDialog.showModal();return;}
    if(deliveryDialog && event.target.closest('[data-close-deliveries]')){deliveryDialog.close();return;}

    var artToggle = event.target.closest('[data-build-art]');
    if (artToggle) {
      buildArtEnabled = !buildArtEnabled;
      document.querySelectorAll('[data-build-art]').forEach(function(button){button.setAttribute('aria-pressed',String(buildArtEnabled));button.textContent='Animation '+(buildArtEnabled?'on':'off');});
      document.querySelectorAll('.k-art--animated').forEach(function (node) {
        node.classList.toggle('k-art--paused', !buildArtEnabled || !!(snapshot && snapshot.paused));
      });
      return;
    }
    if(event.target.closest('[data-overnight-close]')) { document.getElementById('econ-overnight').close(); return; }
    var dialog = document.getElementById('build-license-dialog');
    if (dialog && event.target.closest('[data-build-license]')) { dialog.showModal(); return; }
    if (dialog && event.target.closest('[data-build-close]')) { dialog.close(); return; }
    var target = event.target instanceof Element ? event.target.closest('[data-econ-action]') : null;
    if (!target || target.disabled) return;
    event.preventDefault();
    act(String(target.getAttribute('data-econ-action')));
  });

  document.addEventListener('change', function(event){
    if(event.target.id==='game-customer-choice'){customerChoices[customerSlot]=event.target.value;render();return;}
    if(event.target.matches('[data-business-focus]'))act('focus:'+event.target.dataset.businessFocus+':'+event.target.value);
    if(event.target.id==='game-business-choice'){selectedSlot=Number(event.target.value);render();document.getElementById('game-business-choice').focus({preventScroll:true});}
    if(event.target.id==='game-expansion-choice'){selectedFrontier=Number(event.target.value);render();document.getElementById('game-expansion-choice').focus();}
  });

  document.addEventListener('input', function (event) {
    var range = event.target instanceof Element ? event.target.closest('#econ-keep-range') : null;
    if (!range) return;
    var label = document.getElementById('econ-keep-label');
    if (label) {
      label.innerHTML = '<span>Keep ' + range.value + '% in the business</span>' +
        '<span>Invest ' + (100 - Number(range.value)) + '%</span>';
    }
  });

  // ---------------------------------------------------------------- clocks --
  // The build timer counts down locally between polls so it does not sit still
  // for fifteen seconds at a time.
  function startTimers() {
    if (pollTimer) return;
    pollTimer = window.setInterval(refresh, snapshot ? snapshot.tickSeconds*1000 : POLL_MS);
    tickTimer = window.setInterval(function () {
      if(snapshot && snapshot.paused)return;
      document.querySelectorAll('[data-econ-countdown]').forEach(function (node) {
        var left = Math.max(0, Number(node.getAttribute('data-econ-countdown')) - 1);
        node.setAttribute('data-econ-countdown', left);
        node.textContent = left > 0 ? duration(left) : 'any moment now';
      });
    }, 1000);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') refresh();
  });

  function showOvernight(r) {
    var dialog=document.getElementById('econ-overnight');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='econ-overnight';dialog.className='econ-kid';document.body.appendChild(dialog);}
    if (snapshot && productionModel(snapshot)) {
      dialog.innerHTML='<h2>Welcome back</h2>'+line('Retail sales',ym(r.retailEarned),'k-good')+(r.customerEarned || r.customerDeliveries?line('Customer contracts',ym(r.customerEarned),'k-good')+line('Customer shipments',units(r.customerDeliveries)):'')+line('Goods made',units(r.unitsProduced))+(r.builds?line('Businesses opened',r.builds):'')+(r.offlineTicksSkipped>0?'<p class="game-hint">'+units(snapshot.offlineHours || 12)+'h offline limit reached.</p>':'')+'<button class="k-btn" data-overnight-close>Continue</button>';
    } else {
      dialog.innerHTML='<h2>OVERNIGHT REPORT</h2>'+line('Goods produced',ym(r.produced))+line('Overflow goods sold',ym(r.overflowSold))+
        line('Overflow discount cost',ym(r.overflowCost))+line('Buildings completed',r.builds)+line('Market events',r.events)+
        line('Contracts completed / missed',r.contractsDone+' / '+r.contractsFailed)+line('Rank change',r.rankChange)+
        '<button class="k-btn" data-overnight-close>Collect</button>';
    }
    if(!dialog.open)dialog.showModal();
  }

  // ------------------------------------------------------------------ boot --
  function boot() {
    if (!mounted().length) return;
    if (document.getElementById('econ-license')) {
      request('GET', '/quiz').then(function (data) { quiz = data; render(); }).catch(function () {});
    }
    // Opening the game is a login: it is what earns the catch-up bonus after a
    // day away. Polling afterwards uses /state, which has no side effects.
    request('POST', '/login', {}).then(apply).catch(function (err) {
      if (err && err.status === 401) {
        renderOffline('This class session has expired. Join again to keep playing.');
        return;
      }
      return fetchState().then(apply).catch(function (error) {
        clearCompetition();
        var localPreview = window.location.protocol === 'file:' ||
          (['localhost', '127.0.0.1', '[::1]'].indexOf(window.location.hostname) >= 0 && window.location.port !== '3000');
        var missingApi = localPreview && (window.location.protocol === 'file:' || [404, 405, 501].indexOf(error && error.status) >= 0);
        mounted().forEach(function (screen) {
          document.getElementById(screen[0]).innerHTML = '<div class="k-card"><h3 class="k-card-title">' +
            (missingApi ? 'Open the game server' : 'Your business is offline') + '</h3><p class="k-note">' +
            (missingApi ? 'This preview cannot run the simulator. Open the game to continue.' : 'Cannot reach the game server. We will reconnect automatically.') +
            '</p>' + (localPreview ? linkButton('http://127.0.0.1:3000/buildings.html', 'Open game') : '') + '</div>' + statusLine();
        });
        if (!missingApi) setStatus('Cannot reach the class server.', 'error');
      });
    }).then(startTimers);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.YomamaEcon = { refresh: refresh, state: function () { return snapshot; }, format: ym };
}());
