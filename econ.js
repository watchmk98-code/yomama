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
  var refreshPending = null;
  var actionVersion = 0;
  var businessMetricChanges = {};
  var businessClocks = {};
  var businessConnected = true;
  var businessClockNeedsSync = false;
  var busy = false;
  var staffChoices = {};
  var selectedQuest = null;
  var selectedProject = null;
  var activitiesKind = 'quests';
  var salvageBuildingId = null;
  var growthTab = 'research';
  var growthBranch = 'Food';
  var growthContext = null;
  var growthEquipment = null;
  var activitiesPurpose = null;
  var pendingRerolls = [];
  var customerSlot = Math.max(0,Number(new URLSearchParams(window.location.search).get('customer')) || 0);
  var customerChoices = {};
  var customerSwitchId = null;
  var customerThanks = {};
  var customerArtEnabled = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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
    return fetch(path.indexOf('/api/')===0 ? path : BASE + path, opts).then(function (res) {
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
  function independentProduction(s) { return s.productionMode === 'independent'; }
  function operatingStatement(s) { return s.operatingStatement && s.operatingStatement.enabled?s.operatingStatement:null; }

  function units(value) {
    return (Number(value) || 0).toLocaleString('en-US', { maximumFractionDigits: 1 });
  }

  function materialAmount(value) { return units(value) + ' material' + (Number(value) === 1 ? '' : 's'); }

  function orderOffers(s) { return ((s.orders || s.contracts || {}).offers || []); }
  function goalOrder() { return null; }
  function orderAt(s,index) { var goal=goalOrder(s);return goal && index===(goal.offerIndex==null?3:goal.offerIndex)?goal:orderOffers(s)[index]; }

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

  // Building art permanently shows the first frame of each strip or grid sheet.
  // Highest generated sheet per building. Keep that upgrade at later levels.
  var BUILDING_SHEET_LEVELS = {
    farm:3, fish_stall:2, garage:3, workshop:3, solar_coop:3,
    cannery:3, machine_works:3, turbine_field:3, generator:3,
    data_center:2, solar_array:2, uplink_center:2
  };

  function buildingArtStage(id, level) {
    if ((id==='farm' || id==='roastery') && level>=6) return 6;
    if (BUILDING_SHEET_LEVELS[id] && level>=2) return Math.min(BUILDING_SHEET_LEVELS[id], level>=3 ? 3 : 2);
    if (id==='roastery' && level>=3) return 3;
    return 1;
  }

  function art(s) {
    var id = String(s.buildingId || '');
    var legacy = id==='farm' || id==='roastery';
    var stage = buildingArtStage(id, s.artLevel);
    var grid = !!BUILDING_SHEET_LEVELS[id] && (stage===2 || stage===3);
    var staticUpgrade = stage>1 && !grid;
    var initial = (s.buildingName || '?').charAt(0).toUpperCase();
    var gamePage = document.body.classList.contains('game-page');
    var animated = !staticUpgrade && (grid || gamePage);
    var base = ART_DIR+'spritesheets/'+encodeURIComponent(id)+'_8f.png';
    var still = ART_DIR+encodeURIComponent(id)+'.png';
    var source = staticUpgrade ? ART_DIR+'upgrades/'+id+'-level-'+stage+'.png' : grid ? ART_DIR+'upgrades/animated/'+encodeURIComponent(id)+'-level-'+stage+'_8f.png' : animated ? base : still;
    var fallback = grid && legacy && stage===3 ? ART_DIR+'upgrades/'+id+'-level-3.png' : still;
    return '<div class="k-art' + (stage>1 ? ' k-art--upgraded' : '') + (animated ? ' k-art--animated' : '') + (grid ? ' k-art--grid' : '') + '" data-art-level="'+stage+'" data-initial="' + esc(initial) + '">' +
      '<img src="'+source+'" alt="'+esc(s.buildingName)+(stage>1?' · level '+stage+' improvements':'')+'" ' +
      (grid || staticUpgrade ? 'data-art-base="'+base+'" ' : '') +
      (animated || staticUpgrade ? 'data-art-fallback="'+fallback+'" ' : '') +
      'onerror="if(this.dataset.artBase){this.parentNode.classList.remove(\'k-art--grid\');this.parentNode.classList.add(\'k-art--animated\');this.src=this.dataset.artBase;delete this.dataset.artBase;}else if(this.dataset.artFallback){this.parentNode.classList.remove(\'k-art--animated\',\'k-art--grid\');this.src=this.dataset.artFallback;delete this.dataset.artFallback;}else{this.parentNode.classList.add(\'k-art--missing\');this.remove();}"></div>';
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
    return '<div class="k-status' + tone + (statusMessage && statusMessage.tone === 'success' ? ' game-visually-hidden' : '') + '" data-econ-status role="status" aria-live="polite">' +
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

  function workerOverview(s) {
    var population=(s.workforce || {}).population;
    if(population && population.enabled)return {workers:Math.max(0,Math.floor(Number(population.total) || 0)),population:true};
    return ((s.workforce || {}).teams || []).reduce(function(total,team){
      var count=Math.max(0,Math.floor(Number(team.workers) || 0));
      var assigned=['production','sales','efficiency'].reduce(function(sum,branch){return sum+Math.max(0,Math.floor(Number((team.allocation || {})[branch]) || 0));},0);
      total.workers+=count;total.unassigned+=Math.max(0,count-assigned);return total;
    },{workers:0,unassigned:0});
  }

  function renderOperationsPrestige(s) {
    var badge=document.getElementById('game-operations-prestige');
    if(!badge)return;
    badge.hidden=!progressionEnabled(s);
    if(badge.hidden)return;
    var balance=units(s.progression.prestige), spendable=connectedProgression(s);
    badge.querySelector('[data-prestige-balance]').textContent=balance;
    badge.title=spendable?'Available Prestige for focus advancements. Earn 1 per quest; basic focus costs 1 and advanced focus costs 2.':'Prestige earned through business quests.';
    badge.setAttribute('aria-label',balance+' Prestige'+(spendable?' available. Open focus tree.':'. View business quests.'));
    badge.href=spendable?'#focus':'#quests';
    badge.dataset.workforceOpen=spendable?'focus':'quests';
  }

  function resourceBar(s) {
    if(productionModel(s) && document.getElementById('game-hud')){
      var costs=s.operations || {}, statement=operatingStatement(s);
      var costRate=statement?statement.costs:costs.operatingCostPerMinute || 0, actualSales=statement?statement.sales:s.earnings && s.earnings.operatingIncome;
      var metrics=[
        ['cash','Cash',s.cash,'Available to spend'],
        ['net-worth','Net worth',s.netWorth,'Cash + recoverable stock value + business value'],
        ['income',actualSales!=null?'Sales · last 60s':'Potential sales/min',actualSales==null?s.incomePerMinute:actualSales,statement?'What walk-ins and regular buyers paid before selling fees in the last 60 game seconds. Order rewards are separate.':'Cash from walk-ins and regular buyers in the last 60 game seconds. Order payouts are separate.'],
        ['cost','Costs · last 60s',costRate,statement?'Production costs plus supplies and selling fees paid from customer sales in the last 60 game seconds. Upfront purchases are separate.':'Production costs paid in the last 60 game seconds across all businesses. Upfront purchases are separate.'],
        ['materials','Materials',s.materials,'Used to open new businesses']
      ];
      var crew=s.workforce && s.workforce.enabled?workerOverview(s):null;
      if(crew)metrics[4]=['workers','Workers',crew.workers,crew.population?units(crew.workers)+' workers in your conglomerate. Population only; no gameplay effects yet.':units(crew.workers)+' trained workers across your owned businesses; '+units(crew.unassigned)+' unassigned.'];
      return '<dl class="game-resources game-build-metrics" aria-label="'+(connectedProgression(s)?'Conglomerate finances':'Town finances')+'">'+metrics.map(function(metric){
        if(metric[0]==='workers')return '<div data-build-metric="workers" title="'+metric[3]+'"><dt>Workers</dt><dd><a id="game-workers-overview" class="game-worker-link" href="./advanced-hq.html'+(crew.population?'#workers':crew.workers?'#workers':'#team')+'" data-workforce-open="team" data-workforce-view="'+(crew.population?'recruitment':crew.workers?'assignments':'recruitment')+'" aria-label="'+units(crew.workers)+(crew.population?' workers. View population.':' workers, '+units(crew.unassigned)+' unassigned. Manage workers.')+'"><img src="./assets/game-art/ui/workers.svg" alt="" width="24" height="24" aria-hidden="true"><span data-worker-total>'+units(crew.workers)+'</span></a></dd></div>';
        var money=metric[0]!=='materials', rate=metric[0]==='income' || metric[0]==='cost';
        var value=rate && Math.abs(metric[2])<1000 ? incomeRate(metric[2]) : ym(metric[2]);
        var sign=metric[0]==='cost'?'−':'';
        return '<div data-build-metric="'+metric[0]+'" title="'+metric[3]+'"><dt>'+metric[1]+'</dt><dd title="'+sign+(rate?incomeRate(metric[2]):units(metric[2])+(money?' YM':''))+'">'+(money?sign+value.replace(/ YM$/,'')+'<small>YM</small>':units(metric[2]))+'</dd></div>';
      }).join('')+'</dl>';
    }
    if(productionModel(s))return '<div class="game-wallet"><span>Cash <strong>'+ym(s.cash)+'</strong></span></div>';
    var values = [['Cash', ym(s.cash)], [productionModel(s) ? 'Sales / min' : 'Production / ' + s.tickSeconds + ' sec', productionModel(s) ? incomeRate(s.incomePerMinute) : ym(s.revenuePerTick)], ['Storage', percent(s.warehouseFillPercent / 100)], ['Business value', ym(s.netWorth)]];
    return '<div class="game-resources">' + values.map(function (v) { return '<div><span>' + v[0] + '</span><strong>' + v[1] + '</strong></div>'; }).join('') + '</div>';
  }

  function roster(s) {
    return '<aside class="game-panel game-roster" aria-label="Your buildings">' + panelHead('Your buildings', s.buildingsOwned + ' / ' + s.tierCount) +
      '<div class="game-roster-list" data-keep-scroll="roster">' + s.buildings.map(function (b) {
        return '<button type="button" class="game-building-choice" data-select-building="' + b.slot + '" aria-pressed="' + (b.slot === selectedSlot) + '">' +
          art({buildingId:b.id, buildingName:b.name, paused:true, artLevel:b.artLevel}) + '<span><strong>' + esc(b.name) + '</strong><small>' + (productionModel(s) ? esc(b.status || 'Working') : 'Lv ' + b.lv + ' · ' + ym(b.revenuePerTick) + ' / tick') + '</small></span></button>';
      }).join('') + '</div><div class="game-roster-foot">Open businesses keep producing.</div></aside>';
  }

  function site(b, s) {
    if (productionModel(s)) return productionSite(b, s);
    return '<section class="game-panel game-site">' + panelHead(b.name, '<span class="' + (s.paused ? 'k-money' : 'k-good') + '">' + (s.paused ? 'Ⅱ Paused' : '● Producing') + '</span>') +
      '<div class="game-site-stage">' + art({buildingId:b.id, buildingName:b.name, paused:s.paused}) +
      '<div><span class="game-eyebrow">' + esc(s.families[b.family].name) + '</span><div class="game-level">LEVEL ' + b.lv + '</div><strong class="game-output">' + ym(b.revenuePerTick) + '<small> / ' + s.tickSeconds + ' sec</small></strong>' +
      '<span class="game-site-auto">Output ×' + b.auto + '</span></div></div>' +
      '<div class="game-site-footer"><span>' + (b.setBadges.length ? esc(b.setBadges.join(' · ')) : 'Building ' + (b.tier + 1) + ' / ' + s.tierCount) + '</span></div></section>';
  }

  function stockPanel(b, s) {
    if (productionModel(s)) return buildingStockPanel(b, s);
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
    return '<section class="game-panel game-expansion">' + panelHead('New business', progressionEnabled(s)?'<button id="game-growth-open" type="button" class="game-text-button game-growth-heading" data-game-growth>'+ (equipmentEnabled(s)?'Research & kits':researchEnabled(s)?'Research':'Prestige') +' →</button>':detail) +
      '<div class="game-expansion-body">' + (b ? '<div class="game-next-art" data-preview-business="'+esc(b.id)+'">'+art({buildingId:b.id,buildingName:b.name,paused:true})+'</div><label class="game-visually-hidden" for="game-expansion-choice">Next building</label><select id="game-expansion-choice">' + frontier.map(function(item) {return '<option value="' + item.tier + '"' + (item.tier === b.tier ? ' selected' : '') + '>' + esc(item.name) + '</option>';}).join('') + '</select>' +
      '<div class="game-small-stats"><span>' + (productionModel(s) ? duration(b.buildSeconds == null ? b.timerH * 3600 : b.buildSeconds).replace(/ 00s$/,'').replace(/ 00m$/,'') : b.timerH + 'h') + ' build</span><span>' + (productionModel(s) ? (b.constructionGrant ? 'Cash + materials covered' : b.materialsMissing ? 'Buy ' + materialAmount(b.materialsMissing) : materialAmount(b.materialsCost)) : ym(b.baseRevenue) + ' / tick') + '</span></div>' +
      expansionRequirements(b,s)+bar(b.cost > 0 ? s.cash / b.cost * 100 : 100,'k-bar-fill--gold') + bigButton('expand:' + b.tier, b.constructionGrant?'Build · grant funded':'Build · ' + ym(b.cost),'',!b.canExpand,' k-btn--alt') +
      (!b.canExpand && (!b.requirementWhy || b.why!==b.requirementWhy) ? why(/^Need \d+ YM more$/.test(b.why)?'Need '+ym(Math.max(0,b.cost-s.cash))+' more':b.why) : '') : '<p class="k-good">All businesses open</p>') +
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
    el.innerHTML=notice(s)+(productionModel(s)?openingGuide(s):'')+'<div class="game-layout">'+roster(s)+'<div class="game-center">'+site(b,s)+(productionModel(s)?'':stockPanel(b,s))+'</div><div class="game-actions">'+(productionModel(s)?operationsPanel(b,s):upgradePanel(b,s,false)+upgradePanel(b,s,true))+expansionPanel(s)+'</div></div><div class="game-build-bottom">'+(productionModel(s)?buildingActivityStrips(b,s):gameFooter(s)+breakfastStrip(s))+'</div>'+statusLine();
  }

  var breakfastGoods = {
    beans: ['Beans', 'roastery_roasted_beans'], eggs: ['Eggs', 'farm_eggs'],
    honey: ['Honey', 'farm_honey'], coffee: ['Coffee', 'roastery_espresso_shots'],
    pastry: ['Pastries', 'roastery_pastries']
  };
  function breakfastIcon(key) { return assetIcon('goods/'+breakfastGoods[key][1]+'.png','econ-good-icon'); }
  function breakfastStrip(s) {
    var e=s.breakfastEvent;if(!e)return '';
    return '<section class="game-event-strip'+(e.locked?' is-locked':'')+'" aria-label="Breakfast Club event">'+breakfastIcon('coffee')+'<div><strong>Breakfast Club</strong><small>'+(e.locked?esc(e.unlockText || 'Open the roastery to unlock the recipe workshop'):e.status==='done'?'Recipe workshop complete':'Recipe workshop · improve one recipe')+'</small></div><button type="button" class="game-small-button" data-game-breakfast>'+(e.locked?'Preview':e.status==='new'?'Play':e.status==='done'?'View':'Resume')+' ↗</button></section>';
  }
  function breakfastMarkup(s) {
    var e=s.breakfastEvent;if(!e)return '<p>Event unavailable.</p>';
    if(e.locked)return '<div class="breakfast-welcome"><h3>Learn to run a café kitchen</h3><p>'+esc(e.unlockText || 'Open the roastery first.')+'</p><p class="game-hint">Plan batches and choose a recipe to improve. This workshop uses its own practice supplies.</p></div>';
    if(e.status==='new')return '<div class="breakfast-welcome"><div class="breakfast-welcome-art">'+breakfastIcon('coffee')+breakfastIcon('pastry')+'</div><h3>Master the morning rush</h3><div class="breakfast-prize">4 practice orders → +25% base speed for one roastery recipe + 5 materials</div><p class="game-hint">Plan batches with separate workshop supplies and practice coins. No deadline. Close and resume anytime.</p>'+bigButton('breakfast:start','Open the kitchen','',false)+'</div>';
    if(e.status==='done')return '<div class="breakfast-welcome"><div class="breakfast-welcome-art">'+breakfastIcon('coffee')+breakfastIcon('pastry')+'</div><h3>Breakfast is served!</h3><div class="breakfast-prize">+5 materials added to your town</div><p>4 practice orders served · '+esc(e.townPerk || ((e.upgrade==='coffee'?'Espresso':'Pastries')+' +25% of base production speed at your roastery'))+'</p></div>';
    var completed=e.stage>=4?3:e.stage;
    var html='<div class="breakfast-progress"><span>'+completed+' / 4 served</span><span>'+e.coins+' practice coins</span></div>'+bar(completed/4*100,'k-bar-fill--gold');
    html+='<div class="breakfast-stock">'+Object.keys(breakfastGoods).map(function(k){return '<div>'+breakfastIcon(k)+'<strong>'+e.stock[k]+'</strong><small>'+breakfastGoods[k][0]+'</small>'+(e.supply[k]?'<small>+1 / '+({beans:15,eggs:30,honey:60}[k])+'s</small>':'')+'</div>';}).join('')+'</div>';
    html+='<div class="breakfast-layout"><section class="game-panel">'+panelHead('Kitchen','1 cooking · 1 queued')+'<div class="game-panel-body">';
    html+='<div class="breakfast-job" role="status">'+(e.active?'<strong>Making '+breakfastGoods[e.active.recipe][0].toLowerCase()+'</strong><b data-econ-countdown="'+e.active.remaining+'">'+duration(e.active.remaining)+'</b>':'<strong>Kitchen ready</strong>')+'</div>';
    html+='<div class="breakfast-queue">'+(e.queued?'<span>'+breakfastGoods[e.queued.recipe][0]+' · '+(e.active?'queued':'waiting for ingredients')+'</span><button type="button" class="game-text-button" data-econ-action="breakfast:cancel:'+e.queued.id+'" aria-label="Cancel queued batch">Cancel</button>':'<span>Queue a batch to keep cooking</span>')+'</div>';
    html+=Object.keys(e.recipes).map(function(k){var r=e.recipes[k];return '<div class="breakfast-recipe"><div><strong>'+breakfastGoods[k][0]+' ×'+r.output+'</strong><small>'+Object.keys(r.inputs).map(function(i){return r.inputs[i]+' '+breakfastGoods[i][0].toLowerCase();}).join(' + ')+' · '+r.seconds+'s</small></div>'+bigButton('breakfast:make:'+k,e.active||!r.ready?'Queue':'Make','',!!e.queued||e.stock[k]>=12)+'</div>';}).join('');
    html+='</div></section><section class="game-panel">'+panelHead(e.stage===3?'Choose your upgrade':e.stage===1?'Pick one order':'Serve an order',e.stage===4?'+5 materials':'')+'<div class="game-panel-body breakfast-orders">';
    if(e.stage===3){
      html+='<p class="game-hint">Twice the batch here. Finish to keep +25% base speed for this roastery recipe.</p>'+['coffee','pastry'].map(function(k){return '<div class="breakfast-order"><h3>'+breakfastGoods[k][0]+' kitchen</h3><p>'+breakfastRecipeText(k)+'</p>'+bigButton('breakfast:upgrade:'+k,'Upgrade · 100 practice coins','',false)+'</div>';}).join('');
    }else{
      html+=e.orders.map(function(o){return '<div class="breakfast-order"><h3>'+esc(o.name)+'</h3><div class="breakfast-needs">'+Object.keys(o.needs).map(function(k){return '<span class="'+(e.stock[k]>=o.needs[k]?'is-ready':'')+'">'+breakfastIcon(k)+Math.min(e.stock[k],o.needs[k])+'/'+o.needs[k]+' '+breakfastGoods[k][0]+'</span>';}).join('')+'</div>'+bigButton('breakfast:deliver:'+o.id,o.coins?'Serve · +'+o.coins+' practice coins':'Serve · unlock town upgrade','',!o.ready)+'</div>';}).join('');
    }
    return html+'</div></section></div><p class="game-hint breakfast-note">Workshop supplies only · Ingredients refill up to 12 · Town inventory stays separate · Progress saves when you close</p>';
  }
  function breakfastRecipeText(k){return k==='coffee'?'4 beans → 4 coffees · 30s':'2 eggs + 2 honey → 2 pastries · 45s';}

  function contractsMarkup(s) {
    if (productionModel(s)) return ordersMarkup(s);
    var c=s.contracts;
    function info(o) {return '<h3>'+esc(o.building)+'</h3>'+line('Goods needed',ym(o.target))+line('Reward',ym(o.reward))+line('If missed',ym(o.penalty))+'<p class="game-hint">Due in <span data-econ-countdown="'+o.remainingSec+'">'+duration(o.remainingSec)+'</span></p>';}
    return '<h3>Active deliveries</h3><div class="game-card-grid">'+(c.active.length ? c.active.map(function(o) {return '<section class="k-card">'+info(o)+line('Delivered',ym(o.delivered)+' / '+ym(o.target))+bar(o.progressPercent)+'<p class="game-hint">Production fills this order first.</p></section>';}).join('') : '<p class="game-hint">No delivery in progress.</p>')+'</div><h3>Available jobs</h3><div class="game-card-grid">'+c.offers.map(function(o,i){return '<section class="k-card">'+info(o)+bigButton('contract:'+i,'Accept job','',c.active.length>=s.contractSlots || o.remainingSec<=0)+(c.active.length>=s.contractSlots?why('Finish an active job first.'):o.remainingSec<=0?why('Offer expired. New jobs arrive later.'):'')+'</section>';}).join('')+'</div>'+statusLine();
  }

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
    if (productionModel(s) && s.workforce && s.workforce.enabled && window.YomamaWorkforce) {
      el.innerHTML=notice(s)+businessPicker(s,b)+window.YomamaWorkforce.render(s,b,{
        recipePanel:recipePanel,questsPanel:questsPanel,focusMarkup:focusMarkup,
        esc:esc,ym:ym,duration:duration,act:act,render:render
      })+statusLine();
      return;
    }
    if (productionModel(s)) {
      el.innerHTML=notice(s)+businessPicker(s,b)+'<div class="game-purpose-layout'+(s.operations && s.operations.enabled?' game-management-layout':' game-recipes-only')+'"><div class="game-purpose-main">'+recipePanel(b,s)+focusMarkup(b)+'</div>'+teamPanel(b,s)+questsPanel(b,s)+'</div>'+statusLine();
      return;
    }
    el.innerHTML=notice(s)+'<div class="game-layout">'+roster(s)+'<div class="game-center">'+site(b,s)+'<section class="game-panel">'+panelHead('Your production team','')+'<div class="game-panel-body">'+goodsStrip(b,s)+line('Current output',ym(b.revenuePerTick)+' / '+s.tickSeconds+' sec')+line('Auto Control',esc(b.autoLabel))+'<p class="game-hint">Boost this building while your other buildings keep working.</p></div></section></div><div class="game-actions">'+upgradePanel(b,s,true)+upgradePanel(b,s,false)+'</div></div>'+gameFooter(s)+statusLine();
  }

  function productionSite(b, s) {
    var status=s.paused ? 'Paused' : b.status || 'Working';
    var working=status==='Working', group=(s.families || {})[b.family];
    return '<section class="game-panel game-site game-business-live">' + panelHead(b.name,'<span class="'+(working?'k-good':'k-money')+'">'+esc(status)+'</span>') +
      '<div class="game-business-overview"><div class="game-site-stage" title="'+esc(group ? group.name : 'Your business')+'">'+art({buildingId:b.id,buildingName:b.name,paused:s.paused || b.paused,artLevel:b.artLevel})+'</div>'+businessMetrics(b,s)+'</div>'+buildingStockPanel(b,s)+'</section>';
  }

  function businessMetrics(b,s) {
    var activity=b.activity || {}, changes=b.slot===lastRenderedSlot?(businessMetricChanges[b.slot] || {}):{};
    var rhythm=s.sectorRhythms && s.sectorRhythms.enabled && b.productionRhythm;
    var productionTip=independentProduction(s)?'Current production capacity. Goods need shelf space, their quest unlock, and cash for production costs. No ingredients are taken from stock.':'Current production capacity. Completed goods still need ingredients and shelf space.';
    if(rhythm){
      var batches=(b.goods || []).filter(function(g){return !g.locked && g.productionBatch && g.productionBatch.quantity>0 && g.productionBatch.averageSeconds>0;}).map(function(g){return g.name+': '+units(g.productionBatch.quantity)+' every '+units(g.productionBatch.averageSeconds)+'s on average';});
      productionTip='Average output per minute. '+rhythm.description+(batches.length?' '+batches.join('; ')+'.':'')+' Stock updates every '+units(s.tickSeconds || 15)+' game seconds. '+productionTip;
    }
    var metrics=[
      ['income','Sales · last 60s',incomeRate(b.earnings && b.earnings.operatingIncome!=null?b.earnings.operatingIncome:b.incomePerMinute),'Cash actually received from walk-ins and regular buyers in the last 60 game seconds.'],
      ['produced','Production / min',activity.producedUnits==null?'—':units(activity.producedUnits),productionTip],
      ['sold','Customer demand / min',activity.soldUnits==null?'—':units(activity.soldUnits),'Current walk-in demand. Sales still need available stock; regular shipments are additional.'],
      ['stock','Stock / capacity',units(b.stored)+' / '+units(b.capacity),'Goods currently stored in this business']
    ];
    var withCosts=s.operations && s.operations.enabled;
    if(withCosts)metrics=metrics.filter(function(m){return m[0]==='produced' || m[0]==='sold';});
    var note=activity.observedSeconds!=null && activity.observedSeconds<60?units(activity.observedSeconds)+'s recorded':'stock now';
    return '<div class="game-business-numbers"><div class="game-live-heading"><span class="game-live-title">'+(withCosts?'AUTO-SALES':'Live rates')+(withCosts?'':' <small>· '+note+'</small>')+'</span><span data-business-feed>'+(!businessConnected?'Reconnecting':s.paused || b.paused?'Paused':'Live')+'</span></div><dl class="game-live-metrics'+(withCosts?' has-costs':'')+'" aria-label="Business activity">'+(withCosts?financeMetrics(b,changes):'')+metrics.map(function(m){
      var capacity=m[0]==='produced'?b.productionCapacityPerMinute:m[0]==='sold'?b.customerCapacityPerMinute:null;
      var value=capacity==null?m[2]:rateUnits(capacity);
      return '<div data-business-metric="'+m[0]+'" title="'+esc(m[3])+'"><dt>'+m[1]+'</dt><dd class="game-live-value'+(m[0]==='income'?' game-output':'')+(changes[m[0]]?' is-updated':'')+'">'+value+'</dd></div>';
    }).join('')+'</dl>'+(withCosts && b.savingForOrders?'<p class="game-cashflow-note">Saving goods: production costs continue. Cash arrives after delivery.</p>':'')+'</div>';
  }

  function financeValues(b) {
    var statement=operatingStatement(b);
    if(statement)return {sales:statement.sales,cost:statement.costs,profit:statement.profit,margin:statement.margin,statement:statement};
    var sales=b.earnings && b.earnings.operatingIncome!=null?b.earnings.operatingIncome:b.incomePerMinute;
    var cost=b.operatingCostPerMinute, profit=sales!=null && cost!=null?sales-cost:b.profitPerMinute;
    return {sales:sales,cost:cost,profit:profit,margin:sales>0 && Number.isFinite(profit)?profit/sales*100:null};
  }

  function financeMetrics(b,changes) {
    var values=financeValues(b), statement=values.statement;
    var marginTip='Operating cash margin over the last 60 game seconds: customer sales minus production and selling costs, divided by sales. Making stock can lower it. Order rewards and upfront purchases are separate.';
    if(statement && Number.isFinite(statement.targetMarginPercent))marginTip+=' Base-level target (all output sold): '+rateUnits(statement.targetMarginPercent)+'%. Actual results can be higher, lower or negative.';
    return '<div class="game-margin-row" aria-label="Actual customer cashflow in the last 60 game seconds">'+[
      ['income','Sales · last 60s',values.sales,statement?'What walk-ins and regular buyers paid before selling fees. Order rewards are separate.':'Cash actually received from walk-ins and regular buyers. Order payouts are separate.',statement?statement.potentialSales:b.potentialIncomePerMinute],
      ['cost','Costs · last 60s',values.cost,statement?'Production costs paid, including unsold stock, plus supplies and selling fees taken from customer sales. Hiring and upgrades are separate.':'Production costs actually paid, including goods kept in stock. Hiring and upgrades are paid separately.',statement?statement.potentialCosts:b.potentialOperatingCostPerMinute],
      ['profit','Profit · last 60s',values.profit,statement?'Customer sales minus production and selling costs paid. Saving stock can make this negative. Order rewards add to Cash separately.':'Customer cash received minus production costs paid. Saving stock can make this negative. Order rewards add to Cash separately.',statement?statement.potentialProfit:b.potentialProfitPerMinute],
      ['margin','Profit margin',values.margin,statement?marginTip:'Profit divided by actual customer sales, as a percentage. Order payouts and upfront purchases are separate.',null]
    ].map(function(m){
      var value=m[0]==='margin'?(m[2]==null?'—':Number(m[2].toFixed(1)).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})+'%'):(m[0]==='cost'?'−':'')+incomeRate(m[2]);
      var potential=m[4]==null?'':'<dd class="game-finance-potential" title="Potential with current production and customers; saved goods and shipment timing can reduce actual cash received.">Potential '+rateUnits(m[4])+' / min</dd>';
      return '<div data-business-metric="'+m[0]+'" title="'+esc(m[3])+'"><dt>'+m[1]+'</dt><dd class="game-live-value'+(m[0]==='income'?' game-output':'')+(changes[m[0]]?' is-updated':'')+((m[0]==='profit' || m[0]==='margin') && Number(m[2])<0?' is-loss':'')+(m[0]==='margin' && m[2]==null?' is-unavailable':'')+'">'+value+'</dd>'+potential+'</div>';
    }).join('')+'</div>';
  }

  function progressionEnabled(s) { return !!(s.progression && s.progression.enabled); }
  function connectedProgression(s) { return !!(s.progression && s.progression.mode==='connected'); }
  function equipmentEnabled(s) { return !!(s.progression && s.progression.equipmentEnabled!==false && !connectedProgression(s)); }
  function researchEnabled(s) { return !!(s.progression && s.progression.enabled && s.progression.researchEnabled!==false); }
  function unlockQuestId(b,s) { return b.id+(connectedProgression(s)?'-plan':'-signature'); }
  function growthButton(s) {
    if(!researchEnabled(s))return '';
    return progressionEnabled(s)?'<button id="game-growth-open" type="button" class="game-small-button game-growth-open" data-game-growth><span class="game-growth-label">'+(equipmentEnabled(s)?'Research & equipment':'Research')+'</span> <small>'+units(s.progression.knowHow)+' Know-how</small></button>':'';
  }

  function expansionRequirements(b,s) {
    if(!progressionEnabled(s))return '';
    var r=b.requirements || b.progressionRequirements || {};
    var items=Array.isArray(r)?r:(r.requirements || r.items || []);
    var html=items.map(function(i){
      var count=i.kind==='equipment' || i.kind==='prestige'?' · '+units(i.owned)+' / '+units(i.quantity):'';
      return '<button id="game-growth-requirement-'+esc(b.id)+'-'+esc(i.id)+'" type="button" class="game-requirement-link'+(i.ready?' k-good':'')+'" data-requirement-kind="'+esc(i.kind)+'" data-requirement-id="'+esc(i.id)+'" title="'+esc(i.description || 'View '+i.name+' for '+b.name)+'">'+(i.ready?'✓ ':'')+esc(i.name || i.label)+count+' →</button>';
    }).join('');
    return html?'<div class="game-expansion-requirements">'+html+'</div>':'';
  }

  function businessAction(action,b,staff) { return 'business:'+action+':'+encodeURIComponent(b.buildingId)+(staff?':'+encodeURIComponent(staff):''); }

  function teamPanel(b,s) {
    if(!(s.operations && s.operations.enabled))return '';
    var options=b.staffOptions || [], chosen=options.find(function(o){return o.id===staffChoices[b.buildingId];}) || options[0];
    if(chosen)staffChoices[b.buildingId]=chosen.id;
    var staff=b.staff, salvage=b.salvage || {};
    return '<section class="game-panel game-business-team">'+panelHead('Temporary staff','1 shift at a time')+'<div class="game-team-body" data-keep-scroll="team"><div class="game-staff-hire">'+
      (staff?'<div class="game-active-shift"><strong>'+esc(staff.name)+'</strong><span class="k-good" data-econ-countdown="'+staff.remainingSeconds+'" data-countdown-paused="'+!!b.paused+'">'+duration(staff.remainingSeconds)+'</span><p>'+esc(staff.effect)+'</p></div>':chosen?'<label for="game-staff-choice">Hire for this business</label><select id="game-staff-choice">'+options.map(function(o){return '<option value="'+esc(o.id)+'"'+(o.id===chosen.id?' selected':'')+'>'+esc(o.name)+'</option>';}).join('')+'</select><p class="game-staff-effect">'+esc(chosen.effect)+'</p><div class="game-shift-price"><span>'+duration(chosen.durationSeconds)+' shift</span><strong>'+ym(chosen.cost)+' upfront</strong></div>'+bigButton(businessAction('hire',b,chosen.id),'Hire '+chosen.name,'',!chosen.canHire || s.paused)+(!chosen.canHire?why(chosen.why):''):'<p class="game-hint">Staff is unavailable.</p>')+
      '<p class="game-hint">'+(independentProduction(s)?'Cash and shelf space':'Ingredients and shelf space')+' still limit output. Extra goods need customers. Shifts pause with this business and the class.</p></div><div class="game-business-control"><div><h3>'+(b.paused?'Business paused':'Business open')+'</h3><p class="game-hint">Pause production and its costs for free.</p></div><button id="game-business-toggle" type="button" class="game-small-button" data-econ-action="'+businessAction(b.paused?'resume':'pause',b)+'"'+(s.paused?' disabled':'')+'>'+(b.paused?'Resume':'Pause')+'</button></div><div class="game-salvage-entry"><div><h3>Close this business</h3><p class="game-hint">Salvage '+ym(salvage.value)+' · '+duration(salvage.cooldownSeconds)+' before rebuilding</p></div><button id="game-salvage-open" type="button" class="game-text-button" data-business-close="'+esc(b.buildingId)+'">Review →</button></div></div></section>';
  }

  function questsPanel(b,s) {
    if(!progressionEnabled(s))return '';
    var quests=s.progression.quests.filter(function(q){return q.buildingId===b.id;});
    return '<section class="game-panel game-business-quests">'+panelHead('Business quests',quests.filter(function(q){return q.status==='done';}).length+' / '+quests.length)+'<div class="game-quest-list" data-keep-scroll="quests">'+quests.map(function(q){return '<article class="game-quest-card"><h3>'+esc(q.title)+(q.status==='done'?' <span class="k-good">✓</span>':'')+'</h3><p>'+esc(q.summary)+'</p><p class="game-quest-reward">'+esc(q.rewardText)+'</p><button id="game-quest-open-'+esc(q.id)+'" type="button" class="game-small-button" data-game-quest="'+esc(q.id)+'">'+(q.status==='done'?'View reward':q.status==='locked'?'Preview':q.ready?'Claim reward':q.status==='tracking'?'View progress':q.status==='workshop'?'Resume quest':'Start quest')+' →</button></article>';}).join('')+'<p class="game-hint">'+(connectedProgression(s)?'Produce and sell real goods to develop this business. Each quest rewards you once.':'Practice supplies are separate from your town. Complete each quest once to keep its reward.')+'</p></div></section>';
  }

  function buildingQuests(b,s) {
    var quests=((s.progression || {}).quests || []).filter(function(q){return q.buildingId===b.id;});
    if(!quests.length && b.id==='roastery' && s.breakfastEvent){
      var event=s.breakfastEvent;
      quests.push({id:'roastery-breakfast',title:'Breakfast Club',summary:'Plan batches and improve one roastery recipe.',rewardText:'+25% base speed for one recipe · 5 materials',status:event.locked?'locked':event.status,unlockText:event.unlockText,legacyEvent:true});
    }
    return quests;
  }

  function buildingProjects(b,s) {
    if(connectedProgression(s))return [];
    return ((s.townProjects || {}).projects || []).filter(function(p){return p.buildingId===b.id;});
  }

  function buildingActivityStrips(b,s) {
    return ['quests'].map(function(kind){
      var items=kind==='quests'?buildingQuests(b,s):buildingProjects(b,s);
      var summary=items.map(function(item){return item.title || item.name;}).join(' · ') || 'No '+kind+' for this business yet';
      return '<section class="game-building-activity" data-activity-kind="'+kind+'" data-activity-building="'+esc(b.id)+'" aria-label="'+esc(b.name+' '+kind)+'"><div class="game-activity-copy"><strong>Quests</strong><small title="'+esc(summary)+'">'+esc(summary)+'</small></div><button id="game-activity-open-'+kind+'" type="button" class="game-small-button" data-building-activities="'+kind+'" aria-label="View '+esc(b.name+' '+kind)+'">View →</button></section>';
    }).join('');
  }

  function activitiesMarkup(s) {
    var b=selectedBuilding(s), isQuest=activitiesKind==='quests';
    var items=isQuest?buildingQuests(b,s):buildingProjects(b,s);
    document.getElementById('game-activities-title').textContent=b.name+' · '+(isQuest?'Quests':'Projects');
    var purpose='';
    if(isQuest && activitiesPurpose){
      if(!researchEnabled(s))activitiesPurpose='prestige';
      var currency=activitiesPurpose==='prestige'?'Prestige':'Know-how';
      purpose='<div class="game-activity-purpose"><p>Each completed quest earns 1 '+currency+'. '+(activitiesPurpose==='prestige'?(connectedProgression(s)?'Spend available Prestige on your team’s focus tree. Earned Prestige still qualifies business expansion.':'Prestige qualifies you for new businesses and is never spent.'):'Spend Know-how on research.')+'</p><label for="game-activity-business">Business quests</label><select id="game-activity-business">'+s.buildings.map(function(owned){var remaining=buildingQuests(owned,s).filter(function(q){return q.status!=='done';}).length;return '<option value="'+owned.slot+'"'+(owned.slot===b.slot?' selected':'')+'>'+esc(owned.name)+' · '+remaining+' left</option>';}).join('')+'</select></div>';
    }
    return purpose+'<div class="game-activity-list">'+(items.length?items.map(function(item){
      var done=item.status==='done' || item.status==='completed';
      var label=done?'Completed':item.status==='locked'?'Preview':isQuest?'Open quest':'Open project';
      return '<article class="game-panel game-activity-card"><h3>'+esc(item.title)+(done?' <span class="k-good">✓</span>':'')+'</h3><p>'+esc(item.summary || item.description)+'</p><p class="game-quest-reward">'+esc(item.rewardText)+'</p>'+(item.status==='locked'?'<p class="game-hint">'+esc(item.unlockText)+'</p>':'')+'<button id="game-activity-'+(isQuest?'quest':'project')+'-'+esc(item.id)+'" type="button" class="game-small-button" '+(item.legacyEvent?'data-game-breakfast':'data-game-'+(isQuest?'quest':'project')+'="'+esc(item.id)+'"')+'>'+label+' →</button></article>';
    }).join(''):'<p class="game-hint">No '+(isQuest?'quests':'projects')+' for this business yet.</p>')+'</div>';
  }

  function connectedQuestMarkup(q,s) {
    var prefix='progression:', id=encodeURIComponent(q.id), html='';
    if(q.status==='plan')html+='<h3 class="game-quest-step">Choose your business perk</h3><div class="game-plan-choices">'+(q.choices || []).map(function(c){return '<article class="game-panel game-plan-choice"><h4>'+esc(c.name)+'</h4><p>'+esc(c.description)+'</p><small>'+esc(c.perk)+'</small>'+bigButton(prefix+'quest_plan:'+id+':'+encodeURIComponent(c.id),'Choose this perk','',s.paused)+'</article>';}).join('')+'</div>';
    var selected=(q.choices || []).find(function(c){return c.id===q.selectedChoice;});
    if(selected)html+='<p class="game-hint">Selected perk: '+esc(selected.name)+' · '+esc(selected.perk)+'</p>';
    html+='<section class="game-connected-quest" data-connected-quest="'+esc(q.id)+'"><h3 class="game-quest-step">Business progress</h3><div class="game-connected-objectives">'+(q.objectives || []).map(function(g){return '<div class="game-workshop-goal" data-quest-objective="'+esc(g.id)+'"><span>'+(g.kind==='sell'?'Sell ':'Produce ')+esc(g.name)+'</span><strong class="'+(g.ready?'k-good':'')+'">'+units(Math.min(g.owned,g.quantity))+' / '+units(g.quantity)+'</strong></div>';}).join('')+'</div><p class="game-hint">Your business’s production and sales count here. Keep making goods and serving buyers.</p>';
    if(q.status!=='plan')html+=bigButton(prefix+'quest_finish:'+id,'Claim quest reward','',!q.ready || s.paused)+(q.ready?'':why('Complete these business goals to claim your reward.'));
    return html+'</section>';
  }

  function projectMarkup(s) {
    var b=selectedBuilding(s), project=buildingProjects(b,s).find(function(p){return p.id===selectedProject;});
    if(!project)return '<p class="game-hint">Choose a project for this business.</p>';
    var html='<div class="game-quest-intro"><span class="game-eyebrow">'+esc(b.name)+'</span><h3>'+esc(project.title)+'</h3><p>'+esc(project.description)+'</p><p class="game-quest-reward">'+esc(project.rewardText)+'</p></div>';
    if(project.status==='completed')return html+'<p class="k-good">✓ Project complete</p>';
    html+='<div class="game-workshop-goals">'+(project.requirements || []).map(function(g){return '<div class="game-workshop-goal"><span>'+esc(g.name)+'</span><strong class="'+(g.owned>=g.quantity?'k-good':'')+'">'+units(g.owned)+' / '+units(g.quantity)+'</strong></div>';}).join('')+'</div>';
    if(project.status==='locked')return html+'<p class="game-hint">'+esc(project.unlockText)+'</p>';
    var offers=(s.contracts || {}).offers || [], index=offers.findIndex(function(o){return o.id===project.orderId;}), offer=offers[index];
    if(!offer)return html+'<p class="game-hint">This project is not available yet.</p>';
    return html+'<div class="game-confirm-actions">'+bigButton('fulfill:'+index+':'+offer.id,'Deliver project',offer.canFulfill?'Ready':offer.why || 'Waiting for goods',!offer.canFulfill || s.paused)+'<button id="game-project-save" type="button" class="game-small-button" data-econ-action="commit:'+index+':'+esc(offer.id)+'" aria-pressed="'+!!offer.committed+'"'+(s.paused || (!offer.committed && offer.canCommit===false)?' disabled':'')+' title="'+esc(offer.commitWhy || 'Save this project’s goods after regular buyers are supplied')+'">'+(offer.committed?'Release goods':'Save for this project')+'</button></div><p class="game-hint">'+esc(offer.canCommit===false?offer.commitWhy:'Regular buyers get goods first. Save the rest for this project. No deadline.')+'</p>';
  }

  function questMarkup(s) {
    var q=((s.progression || {}).quests || []).find(function(item){return item.id===selectedQuest;});
    if(!q)return '<p class="game-hint">Choose a business quest in Operations.</p>';
    var prefix='progression:', id=encodeURIComponent(q.id);
    var html='<div class="game-quest-intro"><span class="game-eyebrow">'+esc(q.buildingName)+'</span><h3>'+esc(q.title)+'</h3><p>'+esc(q.summary)+'</p><p class="game-quest-reward">'+esc(q.rewardText)+'</p></div>';
    if(q.mode!=='connected' && q.linkedEvent==='breakfast')html+='<p class="game-hint">'+esc(q.relatedText || '')+' <button id="game-quest-breakfast" type="button" class="game-text-button" data-related-breakfast>Open Breakfast Club →</button></p>';
    if(q.status==='locked')return html+'<p class="game-hint">'+esc(q.unlockText || 'Open this business to begin.')+'</p>';
    if(q.status==='done')return html+'<div class="game-quest-complete"><strong class="k-good">✓ Quest complete</strong><p>Your reward stays with your '+(connectedProgression(s)?'group':'town')+', including after closing this business.</p></div>';
    if(q.mode==='connected')return html+connectedQuestMarkup(q,s);
    if(q.ready)return html+bigButton(prefix+'quest_finish:'+id,'Claim quest reward','',s.paused);
    if(q.status==='plan')return html+'<h3 class="game-quest-step">1 · Choose a plan</h3><div class="game-plan-choices">'+(q.choices || []).map(function(c){return '<article class="game-panel game-plan-choice"><h4>'+esc(c.name)+'</h4><p>'+esc(c.description)+'</p><small>'+esc(c.perk)+'</small>'+bigButton(prefix+'quest_plan:'+id+':'+encodeURIComponent(c.id),'Use this plan','',s.paused)+'</article>';}).join('')+'</div><p class="game-hint">Try the workshop, then finish to keep the reward. You can restart the practice before finishing.</p>';
    html+='<div class="game-workshop-top"><h3 class="game-quest-step">2 · Make your practice goods</h3><span>'+units(q.workRemaining)+' / '+units(q.workTotal)+' '+esc(q.workLabel || 'work')+' available</span></div><div class="game-practice-stock">'+(q.stocks || []).map(function(stock){return '<span><strong>'+units(stock.quantity)+'</strong> '+esc(stock.name)+'</span>';}).join('')+'</div>';
    html+='<div class="game-workshop-layout"><section class="game-panel">'+panelHead('Workshop','Practice supplies')+'<div class="game-workshop-recipes">'+(q.recipes || []).map(function(r){return '<article class="game-workshop-recipe"><h4>'+esc(r.name)+'</h4><p>'+(r.inputs || []).map(function(i){return units(i.quantity)+' '+esc(i.name);}).join(' + ')+' → '+units(r.output.quantity)+' '+esc(r.output.name)+'</p>'+bigButton(prefix+'quest_batch:'+id+':'+encodeURIComponent(r.id),'Make batch · '+units(r.work)+' work','',!r.ready || s.paused)+(!r.ready?why(r.why):'')+'</article>';}).join('')+'</div></section><section class="game-panel">'+panelHead('Finish the quest','')+'<div class="game-workshop-goals">'+(q.goals || []).map(function(g){return '<div class="game-workshop-goal"><span>'+esc(g.name)+'</span><strong class="'+(g.ready?'k-good':'')+'">'+units(g.owned)+' / '+units(g.quantity)+'</strong></div>';}).join('')+bigButton(prefix+'quest_finish:'+id,'Finish & keep reward','',!q.ready || s.paused)+(!q.ready?why('Make the required goods to finish.'):'')+'</div></section></div>';
    return html+(q.canReset?'<button class="game-text-button" type="button" data-econ-action="'+prefix+'quest_reset:'+id+'"'+(s.paused?' disabled':'')+'>Restart practice · choose another plan</button>':'');
  }

  function growthMarkup(s) {
    var p=s.progression;
    if(!p || !p.enabled)return '<p class="game-hint">Research is unavailable in this class.</p>';
    var milestones=p.prestigeMilestones || [], tabs=researchEnabled(s)?[['research','Research']]:[];
    var growthTitle=document.getElementById('game-growth-title');
    if(growthTitle)growthTitle.textContent=researchEnabled(s)?(equipmentEnabled(s)?'Research & equipment':'Research'):'Prestige';
    if(!researchEnabled(s) && !milestones.length)return '<p class="game-hint">Research is closed for testing.</p>';
    if(!researchEnabled(s) && growthTab==='research')growthTab='prestige';
    if(equipmentEnabled(s))tabs.push(['equipment','Equipment']);
    else if(growthTab==='equipment')growthTab='research';
    if(milestones.length)tabs.push(['prestige','Prestige']);
    else if(growthTab==='prestige')growthTab='research';
    var nav='<div class="game-growth-balance">'+(researchEnabled(s)?'<strong>'+units(p.knowHow)+' Know-how</strong>':'<strong>Research closed for testing</strong>')+'<span>'+units(p.prestige)+(connectedProgression(s)?' Prestige available · '+units(p.prestigeEarned)+' earned':' Prestige · earned through quests')+'</span></div><div class="game-growth-tabs" role="group" aria-label="Growth tools">'+tabs.map(function(tab){return '<button id="game-growth-tab-'+tab[0]+'" type="button" class="game-small-button" data-growth-tab="'+tab[0]+'" aria-pressed="'+(growthTab===tab[0])+'">'+tab[1]+'</button>';}).join('')+'</div>';
    if(growthContext)nav+='<p class="game-growth-context">To open '+esc(growthContext.buildingName)+'</p>';
    if(growthTab==='prestige')return nav+'<p class="game-hint">'+(connectedProgression(s)?'Each quest earns 1 Prestige once. Spend your available points in the focus tree. Expansion counts all Prestige earned, including spent points.':'Complete business quests to earn Prestige. You keep it when opening a business.')+'</p><div class="game-prestige-milestones">'+milestones.map(function(m){return '<article class="game-panel game-prestige-milestone" data-prestige-building="'+esc(m.buildingId)+'"><div><h3>'+esc(m.name)+'</h3><p>'+(m.owned?'Already open':units(m.current)+' / '+units(m.prestigeRequired)+(connectedProgression(s)?' Prestige earned':' Prestige'))+'</p></div><strong class="'+(m.ready || m.owned?'k-good':'')+'">'+(m.owned?'Opened':m.ready?'Qualified':units(Math.max(0,m.prestigeRequired-m.current))+' to earn')+'</strong></article>';}).join('')+'</div><button id="game-growth-earn-prestige" type="button" class="game-small-button game-growth-earn" data-growth-earn="prestige">Earn Prestige · business quests →</button>';
    if(growthTab==='equipment'){
      var equipment=(p.equipment || []).filter(function(e){return !growthEquipment || e.id===growthEquipment;});
      return nav+'<p class="game-hint">Craft one kit at a time. Opening a business consumes its kit; research is permanent.</p>'+(growthEquipment?'<button id="game-growth-all-equipment" type="button" class="game-text-button" data-growth-all-equipment>View all equipment →</button>':'')+'<div class="game-equipment-grid'+(growthEquipment?' is-focused':'')+'">'+equipment.map(function(e){
        var research=(p.research || []).find(function(r){return r.id===e.researchId;});
        return '<article id="game-growth-equipment-'+esc(e.id)+'" tabindex="-1" class="game-panel game-equipment-card" data-equipment-id="'+esc(e.id)+'"><h3>'+esc(e.name)+' <small>Owned '+units(e.quantity)+'</small></h3><p>'+esc(e.description)+'</p><ul class="game-equipment-inputs">'+(e.inputs || []).map(function(i){return '<li class="'+(i.ready?'k-good':'')+'">'+esc(i.name)+' <span>'+units(i.owned)+' / '+units(i.quantity)+'</span></li>';}).join('')+'</ul><small class="game-hint">For '+esc((e.usedFor || []).join(', '))+'</small>'+(!e.unlocked && research?'<button id="game-growth-kit-research-'+esc(e.id)+'" type="button" class="game-text-button game-equipment-research" data-equipment-research="'+esc(research.id)+'">Research '+esc(research.name)+' →</button>':'')+bigButton('progression:craft:'+encodeURIComponent(e.id),'Craft · '+ym(e.cost),'',!e.ready || s.paused)+(!e.ready?why(e.why):'')+'</article>';
      }).join('')+'</div>';
    }
    var branches=[['Food','Food'],['Industry','Industry'],['Energy / Tech','Energy / Tech']];
    var research=p.research || [], branchKeys=research.map(function(r){return r.branch;});
    if(branchKeys.length && branchKeys.indexOf(growthBranch)<0)growthBranch=branchKeys[0];
    return nav+'<p class="game-hint">Earn Know-how from quests. Learn a branch in order.</p><div class="game-growth-branches" role="group" aria-label="Research branch">'+branches.map(function(branch){var key=branch[0];return '<button id="game-growth-branch-'+encodeURIComponent(key)+'" type="button" class="game-small-button" data-growth-branch="'+key+'" aria-pressed="'+(growthBranch===key)+'">'+branch[1]+'</button>';}).join('')+'</div><div class="game-research-path">'+research.filter(function(r){return r.branch===growthBranch;}).map(function(r,index){return '<article id="game-growth-research-'+esc(r.id)+'" tabindex="-1" class="game-panel game-research-card'+(growthContext && growthContext.researchId===r.id?' is-required':'')+'" data-research-id="'+esc(r.id)+'"><span class="game-research-step">'+(index+1)+'</span><div><h3>'+esc(r.name)+(r.owned?' <span class="k-good">✓ Learned</span>':'')+'</h3><p>'+esc(r.description)+'</p>'+((r.requires || []).length?'<small>Requires '+r.requires.map(function(pr){return esc(pr.name)+(pr.owned?' ✓':'');}).join(', ')+'</small>':'<small>Start here</small>')+'</div><div class="game-research-action">'+bigButton('progression:research:'+encodeURIComponent(r.id),r.owned?'Learned':units(r.knowHowCost)+' Know-how'+(r.cost?' + '+ym(r.cost):''),'',r.owned || !r.ready || s.paused)+(!r.owned && !r.ready?why(r.why):'')+'</div></article>';}).join('')+'</div><button id="game-growth-earn-knowhow" type="button" class="game-small-button game-growth-earn" data-growth-earn="knowhow">Earn Know-how · business quests →</button>';
  }

  function salvageMarkup(s) {
    var b=(s.buildings || []).find(function(item){return item.buildingId===salvageBuildingId;});
    if(!b)return '<p class="game-hint">This business is no longer open.</p>';
    var q=b.salvage || {};
    return '<div class="game-salvage-review"><h3>Close '+esc(b.name)+'?</h3><div class="game-refund"><span>Cash returned</span><strong>'+units(q.value)+' YM</strong></div><p>'+units(q.percent)+'% of eligible cash spent on construction and permanent upgrades. Free grants and consumed supplies have no cash refund.</p><ul><li>Production stops and this business slot is freed.</li><li>Empty the shelves and finish any active shift before closing.</li><li>Wait '+duration(q.cooldownSeconds)+' before rebuilding this business type.</li><li>Completed quests, product unlocks and research stay learned.</li></ul>'+((q.affectedBusinesses || []).length?'<p class="game-salvage-impact">Supply affected: '+esc(q.affectedBusinesses.join(', '))+'.</p>':'')+(!q.canSalvage?why(q.why):'')+'<div class="game-confirm-actions"><button type="button" class="game-small-button" data-close-business-dialog>Keep business</button>'+bigButton(businessAction('salvage',b),'Close · receive '+units(q.value)+' YM','',!q.canSalvage || s.paused,' game-danger-button')+'</div></div>';
  }

  function ensureBusinessDialogs() {
    if(!document.querySelector('#econ-building, #econ-auto'))return;
    if(!document.getElementById('game-breakfast')){var breakfastDialog=document.createElement('dialog');breakfastDialog.id='game-breakfast';breakfastDialog.setAttribute('aria-labelledby','game-breakfast-title');breakfastDialog.innerHTML='<div class="game-dialog-head"><h2 id="game-breakfast-title">Breakfast Club</h2><button type="button" class="game-small-button" data-close-breakfast>Close ×</button></div><div id="game-breakfast-content" class="econ-kid"></div>'+statusLine();document.body.appendChild(breakfastDialog);}
    [['game-growth',!snapshot || researchEnabled(snapshot)?(equipmentEnabled(snapshot || {})?'Research & equipment':'Research'):'Prestige'],['game-activities','Business activities'],['game-project','Business project'],['game-quest','Business quest'],['game-business-dialog','Close business']].forEach(function(info){
      if(document.getElementById(info[0]))return;
      var dialog=document.createElement('dialog');dialog.id=info[0];dialog.className='game-management-dialog';dialog.setAttribute('aria-labelledby',info[0]+'-title');
      dialog.innerHTML='<div class="game-dialog-head"><h2 id="'+info[0]+'-title">'+info[1]+'</h2><button id="'+info[0]+'-close" type="button" class="game-small-button" data-close-business-dialog>Close ×</button></div><div class="econ-kid game-dialog-content" data-keep-scroll="'+info[0]+'"><div id="'+info[0]+'-content"></div>'+statusLine()+'</div>';
      document.body.appendChild(dialog);
    });
  }

  function renderBusinessDialogs(s) {
    ensureBusinessDialogs();
    [['game-growth',growthMarkup],['game-activities',activitiesMarkup],['game-project',projectMarkup],['game-quest',questMarkup],['game-business-dialog',salvageMarkup]].forEach(function(info){var dialog=document.getElementById(info[0]);if(dialog && dialog.open)document.getElementById(info[0]+'-content').innerHTML=info[1](s);});
  }

  function openBusinessDialog(id,trigger) {
    ensureBusinessDialogs();
    var dialog=document.getElementById(id);if(!dialog)return;
    dialog._returnFocusId=trigger && trigger.id;
    dialog.showModal();renderBusinessDialogs(snapshot);
    document.getElementById(id+'-close').focus({preventScroll:true});
  }

  function focusGrowthTarget(kind,id) {
    var target=document.getElementById('game-growth-'+kind+'-'+id);
    if(target)target.focus({preventScroll:false});
  }

  function openExpansionRequirement(trigger) {
    var business=(snapshot.frontier || []).find(function(b){return b.tier===selectedFrontier;});
    if(!business)return;
    var source=business.requirements || business.progressionRequirements || [];
    var items=Array.isArray(source)?source:(source.requirements || source.items || []);
    var need=items.find(function(item){return item.id===trigger.dataset.requirementId && item.kind===trigger.dataset.requirementKind;});
    if(!need)return;
    if(need.kind==='prestige'){
      activitiesKind='quests';activitiesPurpose='prestige';openBusinessDialog('game-activities',trigger);return;
    }
    var research=(snapshot.progression.research || []).find(function(r){return r.id===(need.researchId || need.id);});
    growthContext={buildingName:business.name,researchId:research && research.id};
    if(research)growthBranch=research.branch;
    growthTab=need.kind==='equipment'?'equipment':'research';
    growthEquipment=need.kind==='equipment'?need.id:null;
    openBusinessDialog('game-growth',trigger);
    focusGrowthTarget(growthTab,need.id);
  }

  function openingGuide(s) {
    var n=s.nextStep;
    if(s.build)n={title:s.build.name+' is being built',detail:s.build.remainingSec+'s remaining. Your other businesses keep working.'};
    if(!n || (!s.build && !(n.action && n.action.indexOf('expand:')===0)))n=Number(s.buildingsOwned || (s.buildings || []).length)>=15?
      {title:'Business network complete',detail:'All 15 businesses are open. Keep improving them through upgrades and quests.'}:
      {title:'Choose your next business',detail:'Build when you have enough cash and Prestige. Your open businesses keep working.'};
    var control=n.action?bigButton(n.action,n.actionLabel || 'Continue','',!!n.disabled || s.paused,' k-btn--alt'):'';
    return '<section class="game-opening-guide" aria-label="Business status"><div><strong>'+esc(n.title)+'</strong><small>'+esc(n.detail)+'</small></div>'+control+'</section>';
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

  function buildingStockPanel(b, s) {
    var goods=b.goods || s.board.filter(function(g){return g.slot===b.slot;});
    var canSell=b.clearableQuantity==null ? goods.some(function(g){return g.quantity>(g.reserved || 0);}) : b.clearableQuantity>0;
    var independent=independentProduction(s), protectedNote=independent?'Regular buyer and order goods stay saved.':'Recipe and delivery supplies stay saved.';
    var saleNote=(s.clearStockPercent || 60)+(operatingStatement(s)?'% of shop payout · ':'% of retail · ')+protectedNote;
    return '<section id="stock" class="game-building-stock game-inventory-table" aria-label="'+esc(b.name)+' stock">'+
      '<div class="game-stock-heading"><h3>Stock</h3><span>'+esc(b.name)+'</span><small>'+(b.reserve?'Shop sales paused':'Automatic shop sales')+'</small></div>'+
      '<div class="game-inventory-head"><span>Item</span><span>Stock / cap.</span><span>Saved</span></div><div class="game-inventory-rows" data-keep-scroll="inventory">'+goods.map(function(g){
        var questId=unlockQuestId(b,s), quest=buildingQuests(b,s).find(function(q){return q.id===questId;});
        var unlockText=quest?'Complete '+quest.title+' to unlock '+g.name:g.unlockText || 'Complete this business’s unlock quest';
        return '<div class="game-inventory-row'+(g.locked?' is-locked':'')+'" data-stock-good="'+esc(g.goodId)+'" data-stock-locked="'+!!g.locked+'"><span class="game-inventory-good">'+goodIcon(b,g,false)+'<span><strong>'+esc(g.name)+'</strong>'+(g.locked?'<button id="game-stock-unlock-'+esc(g.goodId)+'" type="button" class="game-stock-unlock" title="'+esc(unlockText)+'" aria-label="'+esc(unlockText)+'" data-game-quest="'+esc(unlockQuestId(b,s))+'">Locked · Unlock →</button>':'')+bar(g.capacity?g.quantity/g.capacity*100:0)+'</span></span><span data-stock-count>'+units(g.quantity)+'<small> / '+units(g.capacity || 0)+'</small></span><span data-stock-saved title="'+(independent?'Held for regular buyers, saved orders, or paused shop sales':'Held for recipes, deliveries, or paused shop sales')+'">'+units(g.reserved || 0)+'</span></div>';
      }).join('')+'</div><div class="game-stock-controls"><button type="button" class="game-small-button game-reserve'+(b.reserve?' is-active':'')+'" data-econ-action="reserve:'+b.slot+':'+(!b.reserve)+'" aria-pressed="'+!!b.reserve+'" title="Pause walk-in sales for this business. '+(independent?'Deliveries can still use their goods.':'Recipes and deliveries keep using their supplies.')+'">'+(b.reserve?'Resume shop sales':'Hold goods')+'</button><button type="button" class="game-small-button game-stock-sell" data-econ-action="sell:'+b.slot+'"'+(!canSell?' disabled':'')+' title="'+(canSell?saleNote:'No surplus yet. '+protectedNote)+'">Sell surplus · '+ym(b.clearStockValue || 0)+'</button></div></section>';
  }

  function operationsPanel(b, s) {
    return '<section class="game-panel game-operations">'+panelHead('Upgrades','')+upgradeRows(b,['production','sales','storage'])+'</section>';
  }

  function rateUnits(value) {
    return Number(value).toLocaleString('en-US',{maximumFractionDigits:2});
  }

  function incomeRate(value) { return rateUnits(value)+' YM'; }

  function upgradeCapacity(u) {
    return u && u.capacityBefore!=null && u.capacityAfter!=null ? rateUnits(u.capacityBefore)+' → '+rateUnits(u.capacityAfter)+' '+u.capacityUnit : '';
  }

  function forecastIncome(s) {
    if(!s)return null;
    if(s.potentialIncomePerMinute!=null)return s.potentialIncomePerMinute;
    var buildings=s.buildings || [];
    if(buildings.length && buildings.every(function(b){return b.potentialIncomePerMinute!=null;}))return Math.round(buildings.reduce(function(total,b){return total+b.potentialIncomePerMinute;},0)*100)/100;
    return null;
  }

  function upgradeMessage(receipt) {
    var capacity=upgradeCapacity(receipt);
    var statement=receipt && receipt.operatingStatement;
    if(statement && statement.before && statement.after)return 'Potential profit '+rateUnits(statement.before.profit)+' → '+rateUnits(statement.after.profit)+' YM/min'+(capacity?' · '+capacity:'')+' · Cash arrives with sales.';
    var costs=receipt && receipt.operatingCostDelta>0?' · Running costs +'+rateUnits(receipt.operatingCostDelta)+' YM/min':'';
    if(receipt && (receipt.upgrade==='production' || receipt.upgrade==='sales') && receipt.incomeBefore!=null && receipt.incomeAfter!=null){
      return 'Take-home sales '+rateUnits(receipt.incomeBefore)+' → '+rateUnits(receipt.incomeAfter)+' YM/min'+(capacity?' · '+capacity:'')+costs+' · Cash arrives with sales.';
    }
    if(!capacity)return (receipt && receipt.consequence || 'Upgrade complete')+costs;
    var label={production:'Production capacity',sales:'Walk-in demand',storage:'Storage'}[receipt.upgrade] || 'Capacity';
    return label+' '+capacity+costs+(receipt.upgrade==='storage'?'':' · Applies to upcoming goods; totals show the last 60s.');
  }

  function upgradeRows(b,kinds) {
    var names={production:'Production',sales:'Customers',storage:'Storage'};
    return '<div class="game-operation-list">'+kinds.map(function(kind){
      var u=(b.upgrades || {})[kind];
      if(!u) return '';
      var done=u.cost===null;
      var reasonId='game-upgrade-reason-'+b.slot+'-'+kind;
      var capacity=upgradeCapacity(u);
      var incomeDelta=u.businessIncomeBefore!=null && u.businessIncomeAfter!=null?Math.round((u.businessIncomeAfter-u.businessIncomeBefore)*100)/100:u.incomeDelta;
      var statement=u.operatingStatement, statementReady=statement && statement.before && statement.after;
      var costDelta=u.operatingCostDelta;
      if(statementReady){incomeDelta=Math.round((statement.after.sales-statement.before.sales)*100)/100;costDelta=Math.round((statement.after.costs-statement.before.costs)*100)/100;}
      var incomeValue=incomeDelta==null?'':(incomeDelta>=0?'+':'−')+rateUnits(Math.abs(incomeDelta))+' YM/min';
      var costValue=costDelta==null?'':(costDelta>0?'+':costDelta<0?'−':'')+rateUnits(Math.abs(costDelta))+' YM/min';
      var incomeTitle=statementReady?'Estimated customer sales change before selling fees, with current customers and available goods. Net profit changes by '+rateUnits(statement.after.profit-statement.before.profit)+' YM/min.':'Estimated take-home sales change for this business after the next upgrade, with current customers and available goods. Production costs are separate.';
      var income=!done && incomeValue?'<small class="game-upgrade-impact'+(incomeDelta>0?' k-good':incomeDelta<0?' k-bad':' game-no-gain')+'" aria-label="Estimated income change: '+incomeValue+'" title="'+incomeTitle+'">Sales <span class="game-upgrade-value">'+incomeValue+'</span></small>':'';
      var extra=kind==='production' && incomeDelta<=0 && !done?'<small class="game-upgrade-explanation">'+esc(u.consequence || 'More goods, no extra sales yet. Attract customers or save for orders.')+'</small>':'';
      var costs=!done && costValue?'<small class="game-upgrade-running-cost" aria-label="Estimated cost change: '+costValue+'" title="'+(statementReady?'Estimated production and selling cost change. Goods cost money to make; selling fees come out of customer payments.':'Estimated running cost change for this business after the next upgrade. Costs are charged as goods are produced.')+'">Costs <span class="game-upgrade-cost">'+costValue+'</span></small>':'';
      return '<div class="game-operation"><div><strong>'+(kinds.length===1?'Level '+u.level:names[kind]+' <small>Lv '+u.level+'</small>')+'</strong>'+(done?'<span class="game-upgrade-capacity">Complete</span>':income+costs+extra)+'</div><div class="game-upgrade-buy"><button class="game-small-button" type="button" data-econ-action="upgrade:'+b.slot+':'+kind+'"'+(!u.canBuy?' disabled':'')+' aria-label="'+esc('Upgrade '+names[kind]+(done?'':', '+ym(u.cost)))+'"'+(!u.canBuy&&!done?' aria-describedby="'+reasonId+'"':'')+' title="'+esc(u.why || (capacity?capacity+(u.unlocksSpecialty?' · Specialty':''):u.consequence || u.effect))+'">'+(done?'MAX':ym(u.cost)+' ↑')+'</button>'+(!u.canBuy&&!done?'<small id="'+reasonId+'" class="game-upgrade-reason">'+esc(u.why || 'Keep earning to upgrade')+'</small>':'')+'</div></div>';
    }).join('')+'</div>';
  }

  function recipePanel(b, s) {
    var recipes=independentProduction(s)?[]:b.recipes || (b.recipe ? [b.recipe] : []);
    if(!recipes.length) return '<section class="game-panel">'+panelHead('Produces','No ingredients needed')+'<div class="game-direct-products">'+(b.goods || []).map(function(g){return '<div>'+goodIcon(b,g,false)+'<span>'+esc(g.name)+'</span>'+(g.locked?'<button type="button" class="game-text-button" data-game-quest="'+esc(unlockQuestId(b,s))+'">Quest required →</button>':'')+'</div>';}).join('')+'</div></section>';
    var direct=(b.goods || []).filter(function(g){return !g.inputs || !g.inputs.length;});
    return '<section class="game-panel">'+panelHead('Production chains',processingControl(b))+'<div class="game-panel-body game-recipe">'+direct.map(function(g){return '<div class="game-recipe-chain"><div class="econ-good-line"><span class="econ-good-name">'+goodIcon(b,g,false)+esc(g.name)+'</span><span>'+units(g.productionPerMinute)+' / min</span></div><span class="game-hint">No ingredients needed</span></div>';}).join('')+recipes.map(function(recipe){
      return '<div class="game-recipe-chain">'+recipe.inputs.map(function(i){
        var producer=s.buildings.find(function(p){return p.id===i.buildingId;}) || {id:i.buildingId};
        return '<div class="econ-good-line"><span class="econ-good-name">'+goodIcon(producer,i,false)+esc(i.name)+'</span><span class="'+(i.owned>=i.quantity?'k-good':'k-money')+'" title="'+units(i.owned)+' in stock">'+units(i.quantity)+(i.owned<i.quantity?' · Need '+units(i.quantity-i.owned):'')+'</span></div>';
      }).join('')+'<div class="econ-good-line game-recipe-output"><span class="econ-good-name">'+goodIcon(b,recipe.output,false)+'→ '+esc(recipe.output.name)+'</span><span>'+units(recipe.output.quantity)+'</span>'+(recipe.locked?'<button type="button" class="game-text-button game-recipe-unlock" title="'+esc(recipe.unlockText)+'" data-game-quest="'+esc(unlockQuestId(b,s))+'">Quest →</button>':'')+'</div></div>';
    }).join('')+'</div></section>';
  }

  // Brief local feedback for skipped opportunities, saved orders and deliveries.
  // Keep one reaction per slot across re-renders while rapid replacements finish.
  var orderReactions = {};
  var orderClocks = {};
  function reactToOrder(index,kind,label,art) {
    if(orderReactions[index])window.clearTimeout(orderReactions[index].timer);
    var reaction={kind:kind,label:label,art:art || {missed:'crying-face-pixel.png',saved:'thumbs-up-pixel.svg',delivered:'dollar-sign-pixel.svg'}[kind],until:performance.now()+500};
    orderReactions[index]=reaction;
    reaction.timer=window.setTimeout(function(){
      if(orderReactions[index]!==reaction)return;
      delete orderReactions[index];
      document.querySelectorAll('[data-order-reaction="'+index+'"]').forEach(function(node){node.remove();});
    },500);
  }
  function orderReactionMarkup(index){
    var reaction=orderReactions[index];
    if(!reaction || reaction.until<=performance.now())return '';
    var kind=reaction.kind,art=reaction.art;
    return '<span class="game-order-reaction game-'+kind+'-order" data-order-reaction="'+index+'" data-'+kind+'-order="'+index+'" role="img" aria-label="'+esc(reaction.label)+'"><span aria-hidden="true"><img src="./assets/game-art/reactions/'+art+'" alt="" width="80" height="80"></span></span>';
  }

  function trackOrderClocks(s) {
    var next={}, offers=orderOffers(s).slice();
    var goal=goalOrder(s);
    if(goal && !offers.some(function(o){return o.id===goal.id;}))offers.push(goal);
    offers.forEach(function(o){
      if(s.paused || !o.committed || o.etaSeconds==null) return;
      var seconds=Number(o.etaSeconds);
      if(!Number.isFinite(seconds))return;
      // Production forecasts can move in either direction after any action.
      // Every server snapshot replaces the previous local estimate.
      next[o.id]={ready:!!o.canFulfill,deadline:Date.now()+Math.max(0,seconds)*1000};
    });
    orderClocks=next;
  }

  function orderClockLabel(clock) {
    if(clock.ready)return 'Ready now';
    var left=Math.max(0,Math.ceil((clock.deadline-Date.now())/1000));
    // An elapsed estimate cannot prove that the required goods are available.
    return left>0?'About '+duration(left):'Checking supplies…';
  }

  function syncOrderClocks() {
    if(!businessConnected || (snapshot && snapshot.paused))return;
    document.querySelectorAll('[data-order-countdown]').forEach(function(node){
      var clock=orderClocks[node.dataset.orderCountdown];
      if(!clock)return;
      node.textContent=orderClockLabel(clock);
    });
  }

  function projectCard(o,i,s) {
    var project=s.townProjects || {}, done=!!o.completed;
    if(done)return '<section id="town-project" class="k-card game-order game-town-project is-complete" data-order-slot="'+i+'">'+orderReactionMarkup(i)+'<h3>Town projects complete <small>3 / 3</small></h3><p>Your town has earned the café reputation reward.</p><div class="game-project-reward">Café reputation: +20% walk-in customers</div><p class="game-hint">Next: upgrade your businesses, choose regular buyers, or try the Breakfast Club recipe workshop on Build.</p></section>';
    return '<section id="town-project" class="k-card game-order game-town-project" data-order-slot="'+i+'">'+orderReactionMarkup(i)+'<h3><span class="game-order-name">'+esc(o.name)+'</span><small class="game-order-tier">Project '+((project.completed || 0)+1)+' / 3</small></h3><div class="game-order-context"><span class="game-order-channel">Town projects</span><p class="game-order-purpose">'+esc(o.purpose)+'</p><p class="game-project-reward">'+esc(o.rewardText || project.rewardText || '')+'</p></div><div class="game-order-items" data-order-items="'+i+'" data-order-id="'+esc(o.id)+'"><div class="game-order-caption">Have / need</div><div class="game-order-goods">'+o.requirements.map(function(g){var b=s.buildings.find(function(x){return x.id===g.buildingId;}) || {id:g.buildingId};return '<div class="econ-good-line"><span class="econ-good-name">'+goodIcon(b,g,false)+'<span>'+esc(g.name)+'</span></span><span class="'+(g.owned>=g.quantity?'k-good':'k-money')+'">'+units(g.owned)+' / '+units(g.quantity)+'</span></div>';}).join('')+'</div></div><div class="game-order-reward"><span>'+ym(o.reward)+'</span><small>+ project reward above</small></div><div class="game-order-controls">'+bigButton('fulfill:'+i+':'+o.id,'Deliver project',o.canFulfill?'Ready':o.why || 'Waiting for goods',!o.canFulfill)+(o.locked?linkButton('./buildings.html',s.nextStep && s.nextStep.action?'Build with your grant →':'Open Build →',' k-btn--alt'):'<button class="game-small-button game-order-commit" type="button" aria-pressed="'+!!o.committed+'" data-econ-action="commit:'+i+':'+esc(o.id)+'"'+(!o.committed && o.canCommit===false?' disabled':'')+' title="'+esc(o.commitWhy || 'Save only this project’s goods')+'">'+(o.committed?'Release goods':'Save for this project')+'</button>')+'</div><p class="game-hint">'+esc(o.locked?o.why:o.canCommit===false?o.commitWhy:o.supplyConflicts && o.supplyConflicts.length?'Also saved for '+o.supplyConflicts[0]+'. Release that delivery to supply this project sooner.':'Regular buyers get goods first. Save the rest for this project. No deadline.')+'</p></section>';
  }

  function orderEta(o) {
    if(o.etaLabel==null && o.etaSeconds==null && o.etaIfSavedSeconds==null && !o.etaReason)return '';
    var clock=o.committed && orderClocks[o.id];
    var label=o.canFulfill?'Ready now':clock?orderClockLabel(clock):o.etaLabel || (o.etaSeconds!=null?'About '+duration(o.etaSeconds):o.etaIfSavedSeconds!=null?'If saved: about '+duration(o.etaIfSavedSeconds):'Waiting for supplies');
    return '<p class="game-order-eta" data-order-eta><span'+(clock?' data-order-countdown="'+esc(o.id)+'"':'')+'>'+esc(label)+'</span>'+(o.etaReason?'<small>'+esc(o.etaReason)+'</small>':'')+'</p>';
  }

  function ordersMarkup(s) {
    var indexed=orderOffers(s).map(function(o,i){return {order:o,index:i};});
    if(goal && !indexed.some(function(entry){return entry.order.id===goal.id;}))indexed.push({order:goal,index:goal.offerIndex==null?3:goal.offerIndex});
    var rolls=(s.contracts || {}).rolls;
    var rollTip='Free reroll · '+(Array.isArray(rolls)?rolls.map(function(r){return r.label+' '+r.chance+'%';}).join(', '):'Standard 65%, Large 25%, Rare 8%, Jackpot 2%')+' · Rewards require delivery';
    indexed.sort(function(a,b){return Number(b.order===goal)*2+Number(!!b.order.project && (!b.order.completed || !!orderReactions[b.index]))-Number(a.order===goal)*2-Number(!!a.order.project && (!a.order.completed || !!orderReactions[a.index]));});
    return '<div class="game-card-grid game-order-grid" data-keep-scroll="orders">'+indexed.map(function(entry){
      var o=entry.order,i=entry.index;if(o.project)return projectCard(o,i,s);
      var isGoal=false, relationship=o.customer==='breakfast';
      var channel=relationship?'Saved town delivery':(o.channelLabel || (o.materials?'Building supplies':'Quick cash'));
      var rarity=['standard','small','bulk','large','rare','jackpot'].includes(o.rarity)?o.rarity:'standard';
      var label=isGoal?'Goal order':o.rarityLabel || 'Standard';
      var typeHint=rarity==='small'?'A few units of one product. A small, easy-to-fill shopping list.':rarity==='bulk'?'Many units of one product. Sell spare stock at a lower price per item than a standard order.':'';
      return '<section '+(isGoal?'id="goal-order" ':'')+'class="k-card game-order'+(isGoal?' game-goal-order':'')+'" data-rarity="'+rarity+'" data-order-slot="'+i+'">'+orderReactionMarkup(i)+'<h3><span class="game-order-name">'+esc(o.name || channel)+'</span><small class="game-order-tier"'+(typeHint?' title="'+esc(typeHint)+'"':'')+'>'+esc(label)+'</small></h3><div class="game-order-context"><span class="game-order-channel">'+esc(channel)+'</span></div><div class="game-order-items" data-order-items="'+i+'" data-order-id="'+esc(o.id)+'"><div class="game-order-caption">Have / need</div><div class="game-order-goods">'+o.requirements.map(function(g){
        var building=s.buildings.find(function(b){return b.id===g.buildingId;}) || {id:g.buildingId};
        return '<div class="econ-good-line"><span class="econ-good-name">'+goodIcon(building,g,false)+'<span>'+esc(g.name)+'</span></span><span class="'+(g.owned>=g.quantity?'k-good':'k-money')+'">'+units(g.owned)+' / '+units(g.quantity)+'</span></div>';
      }).join('')+'</div></div><div class="game-order-reward"><span title="Paid after you deliver all requested goods">'+ym(o.reward)+'</span>'+(o.rewardPercent?'<small>'+mult(o.rewardPercent/100)+(operatingStatement(s)?'× shop payout':'× retail')+'</small>':'')+(o.materials?'<span>+'+materialAmount(o.materials)+'</span>':'')+'</div><div class="game-order-controls">'+bigButton('fulfill:'+i+':'+o.id,isGoal?'Deliver goal order':'Deliver',o.canFulfill?'Ready':o.why || 'Waiting for goods',!o.canFulfill || s.paused)+(s.rulesRevision>=2?'<button class="game-small-button game-order-commit" type="button" aria-pressed="'+!!o.committed+'" data-econ-action="commit:'+i+':'+esc(o.id)+'"'+(!o.committed && o.canCommit===false || s.paused?' disabled':'')+' title="'+(independentProduction(s)?'Regular buyers get goods first. Save the rest for this order; walk-ins and other orders cannot use it.':'Regular buyers and their recipes get goods first. Save the rest for this order; other recipes and walk-ins cannot use it.')+'">'+(o.committed?'Release goods':'Save for this order')+'</button>':'')+'</div>'+(isGoal?'<p class="game-order-goal-note">Sized for your remaining goal. No deadline.</p>':'<button class="game-text-button" type="button" data-econ-action="replace:'+i+':'+esc(o.id)+'" title="'+esc(rollTip)+'">CLICK!!!!</button>')+'</section>';
    }).join('')+'</div>';
  }

  function customerAction(action, slot, customerId, contractId) {
    return 'customer:'+action+':'+slot+':'+encodeURIComponent(customerId || '')+':'+encodeURIComponent(contractId || '');
  }

  // Each generated sheet is four emotes (rows), with four actual pose frames.
  // Per-emote crop: zoom, left %, top %. Each crop includes every pose in its row.
  var CUSTOMER_ART = {
    builders_union:[[1.3689,-19.6405,-27.5045],[1.225,-10.9546,-6.0669],[1.2675,-11.0514,-3.7757],[1.2844,-14.6286,-1.2135]],
    city_couriers:[[1.3498,-19.426,-27.0724],[1.2354,-10.2869,-8.1249],[1.3498,-19.534,-10.7131],[1.3374,-16.333,-0.1242]],
    clean_power_group:[[1.262,-10.1805,-19.04],[1.1433,-8.5394,-5.0751],[1.1002,-5.0981,-1.4179],[1.2622,-16.4303,-9.993]],
    cloud_studio:[[1.4725,-21.3918,-31.2498],[1.4577,-22.3009,-23.2338],[1.4504,-23.5572,-18.2415],[1.4725,-23.7403,-15.524]],
    copper_cafe:[[1.0565,-1.0533,-4.2543],[1.0525,-5.2253,-3.0466],[1.0641,-3.624,-2.6078],[1.0565,-3.3247,-1.0532]],
    corner_grocer:[[1.1433,-7.3504,-13.2729],[1.0798,-5.1057,-4.5873],[1.1524,-8.9058,-7.1598],[1.1663,-6.7342,-4.8739]],
    district_heating:[[1.2433,-15.3362,-13.3592],[1.1213,-6.1543,-2.7568],[1.2595,-13.5785,-15.1906],[1.3252,-15.2047,-21.2275]],
    harbor_bistro:[[1.068,-4.8462,-6.037],[1.0054,-0.5405,-0.1898],[1.0641,-4.1347,-5.6617],[1.068,-5.1026,-5.8661]],
    honey_collective:[[1.0878,-1.2702,-6.9106],[1.0758,-4.7296,-5.5902],[1.1044,-5.2191,-4.2527],[1.0921,-4.6905,-1.5562]],
    inventors_lab:[[1.2568,-14.6413,-16.9474],[1.1258,-7.6339,-3.8625],[1.246,-14.7785,-12.3987],[1.2789,-12.4156,-13.4323]],
    mobile_network:[[1.3312,-20.7018,-25.3744],[1.3134,-17.862,-17.6584],[1.3312,-18.472,-13.4865],[1.3132,-15.7644,-7.1761]],
    neighborhood_grid:[[1.2458,-10.4032,-17.1555],[1.1998,-9.1344,-9.7103],[1.246,-14.7847,-10.0188],[1.2622,-12.4038,-9.1851]],
    orbital_research:[[1.3624,-24.9681,-28.2311],[1.2958,-15.0948,-17.79],[1.2354,-11.967,-8.7179],[1.2844,-17.7046,-7.3527]],
    pantry_network:[[1.225,-13.8884,-17.5939],[1.225,-11.7386,-15.8422],[1.2677,-14.0959,-13.893],[1.2354,-13.9375,-9.3109]],
    rally_crew:[[1.0941,-8.021,-7.8459],[1.0,-0.0,-0.0],[1.0859,-7.5874,-2.2228],[1.1479,-6.6586,-5.109]],
    regional_utility:[[1.3883,-21.9608,-29.263],[1.2568,-12.5362,-14.7481],[1.3753,-25.2376,-17.9964],[1.3561,-18.1294,-14.0205]],
    sunrise_diner:[[1.1044,-4.4295,-10.4382],[1.0839,-5.6645,-7.0465],[1.0878,-3.7831,-6.5625],[1.0839,-4.3692,-3.9356]]
  };
  var CUSTOMER_EMOTES = {
    working:{row:0,label:'On the job'}, waiting:{row:1,label:'Waiting patiently'},
    thanks:{row:2,label:'Thank you!'}, paused:{row:3,label:'Taking a break'}
  };

  function customerEmote(current, s) {
    if(s.paused || current.paused)return 'paused';
    if((customerThanks[current.id] || 0)>Date.now())return 'thanks';
    return current.status==='waiting'?'waiting':'working';
  }

  function customerFrameStyle(id,row) {
    var frame=(CUSTOMER_ART[id] || [])[row] || [1,0,0];
    return '--customer-row:'+row+';--customer-sheet-size:'+(400*frame[0])+'%;--customer-stride:'+(-100*frame[0])+'%;--customer-left:'+frame[1]+'%;--customer-offset:'+frame[2]+'%';
  }

  function customerArt(current,s,choosing) {
    var id=current.customerId || current.id, emote=customerEmote(current,s);
    var label=choosing && emote==='working'?'Ready to meet you':CUSTOMER_EMOTES[emote].label;
    var available=!!CUSTOMER_ART[id];
    return '<div class="game-customer-character"><div class="game-customer-avatar'+(!available?' is-missing':'')+'" role="img" aria-label="'+esc(current.name+' · '+label)+'" data-customer-art="'+esc(id)+'" data-contract-id="'+esc(choosing?'':current.id)+'" data-emote="'+emote+'" data-motion="'+customerArtEnabled+'" data-initial="'+esc((current.name || '?').charAt(0))+'" style="'+customerFrameStyle(id,CUSTOMER_EMOTES[emote].row)+'">'+(available?'<img src="./assets/customers/emotes/'+id+'_16f.png" alt="" decoding="async" onerror="this.parentNode.classList.add(\'is-missing\');this.remove();">':'')+'</div><span class="game-customer-emote-label">'+label+'</span></div>';
  }

  function syncCustomerEmotes() {
    if(!snapshot)return;
    var active=(snapshot.customerContracts || {}).active || [];
    document.querySelectorAll('.game-customer-avatar').forEach(function(node){
      node.dataset.motion=String(customerArtEnabled);
      var current=active.find(function(item){return item.id===node.dataset.contractId;});
      if(!current)return;
      var emote=customerEmote(current,snapshot), detail=CUSTOMER_EMOTES[emote];
      if(node.dataset.emote!==emote){
        node.style.cssText=customerFrameStyle(node.dataset.customerArt,detail.row);
        node.dataset.emote=emote;
      }
      node.setAttribute('aria-label',current.name+' · '+detail.label);
      node.parentNode.querySelector('.game-customer-emote-label').textContent=detail.label;
    });
  }

  function trackCustomerDeliveries(previous,next) {
    var prior=((previous || {}).customerContracts || {}).active || [];
    var active=(next.customerContracts || {}).active || [], now=Date.now();
    var pending={};
    active.forEach(function(current){
      var before=prior.find(function(item){return item.id===current.id;});
      // First load, signing and switching do not invent a successful shipment.
      if(before && current.deliveries>before.deliveries && !next.paused && !current.paused)pending[current.id]=now+4800;
      else if(!next.paused && !current.paused && customerThanks[current.id]>now)pending[current.id]=customerThanks[current.id];
    });
    customerThanks=pending;
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
    var taken=active.map(function(item){return item.customerId;});
    var eligible=customers.filter(function(item){return item.available && taken.indexOf(item.id)<0;});
    var choice=choosing?(eligible.find(function(item){return item.id===customerChoices[customerSlot];}) || eligible[0]):null;
    if(choice)customerChoices[customerSlot]=choice.id;
    // Open slots preview distinct candidates; only the Sign button creates a contract.
    var previews={};
    if(choice)previews[customerSlot]=choice;
    var proposed=choice?[choice.id]:[];
    for(var index=0;index<slots;index++){
      if(previews[index] || active.some(function(item){return item.slot===index;}))continue;
      var candidates=eligible.filter(function(item){return proposed.indexOf(item.id)<0;});
      var preview=candidates.find(function(item){return item.id===customerChoices[index];}) || candidates[0];
      if(preview){previews[index]=preview;proposed.push(preview.id);customerChoices[index]=preview.id;}
    }
    var slotMarkup=Array.from({length:slots},function(_,index){
      var contract=active.find(function(item){return item.slot===index;});
      var person=previews[index] || contract, previewing=!!previews[index];
      var status=previewing?'Preview':contract?(contract.paused?'Paused':contract.status==='waiting'?'Waiting':'Active'):'Open';
      return '<button id="game-customer-slot-'+index+'" type="button" data-customer-slot="'+index+'" aria-pressed="'+(index===customerSlot)+'" aria-label="Slot '+(index+1)+': '+esc(person?person.name+', '+status:'open')+'">'+(person?customerArt(person,s,previewing):'<span class="game-customer-empty" aria-hidden="true">+</span>')+'<span class="game-customer-slot-label"><strong>'+esc(person?person.name:'Open slot')+'</strong><small>'+(index+1)+' · '+status+'</small></span></button>';
    }).join('');
    var content='';
    if(choosing){
      var options=customers.map(function(item){
        var unavailable=!item.available || taken.indexOf(item.id)>=0;
        return '<option value="'+esc(item.id)+'"'+(unavailable?' disabled':'')+(choice && item.id===choice.id?' selected':'')+'>'+esc(item.name)+(taken.indexOf(item.id)>=0?' · Already signed':!item.available?' · '+esc(item.unlockText || (connectedProgression(s)?'Grow your group to unlock':'Grow your town to unlock')):'')+'</option>';
      }).join('');
      content='<div class="game-contract-summary"><label for="game-customer-choice">'+(switching?'Replace '+esc(current.name):'Choose a regular customer')+'</label><select id="game-customer-choice"'+(!choice?' disabled':'')+'>'+(!choice?'<option>No customers available</option>':'')+options+'</select>'+(choice?'<p class="game-contract-description">'+esc(choice.description)+'</p><div class="game-contract-pay"><strong>'+ym(choice.reward)+'</strong><span>per shipment · every '+duration(choice.intervalSeconds)+'</span></div>':'<p class="game-contract-description">New businesses bring new customers.</p>')+'</div><div class="game-contract-supply">'+(choice?'<div class="game-contract-caption" aria-label="Goods per shipment">Per shipment</div>'+customerRequirements(s,choice.requirements || [],false):'')+'<div class="game-contract-controls">'+bigButton(customerAction(switching?'switch':'accept',customerSlot,choice && choice.id,current && current.id),switching?'Switch customer':'Sign customer','',!choice)+(switching?'<button id="game-customer-cancel" class="game-text-button" type="button" data-customer-cancel>Keep current customer</button>':'')+'</div><p class="game-contract-help">'+(switching?'Switching frees held goods and starts a new shipment timer.':'First shipment after the full interval. Goods are saved for this buyer first.')+'</p></div>';
    }else{
      var status=current.paused?'Paused · goods released':current.status==='waiting'?'Waiting for goods · no penalty':'Next shipment in <span data-econ-countdown="'+Math.max(0,current.nextDeliverySeconds || 0)+'">'+duration(current.nextDeliverySeconds)+'</span>';
      content='<div class="game-contract-summary"><h3>'+esc(current.name)+'</h3><div class="game-contract-pay"><strong>'+ym(current.reward)+'</strong><span>per shipment · every '+duration(current.intervalSeconds)+'</span></div><p class="game-contract-status'+(current.paused?' is-paused':'')+'">'+status+'</p><span class="game-contract-history">'+units(current.deliveries)+' shipments · '+ym(current.earned)+' earned</span></div><div class="game-contract-supply"><div class="game-contract-caption" aria-label="Saved / needed for next shipment">Saved / need</div>'+customerRequirements(s,current.requirements || [],true)+'<div class="game-contract-controls"><button id="game-customer-toggle" class="game-small-button" type="button" data-econ-action="'+customerAction(current.paused?'resume':'pause',customerSlot,'',current.id)+'">'+(current.paused?'Resume':'Pause')+'</button><button id="game-customer-switch" class="game-small-button" type="button" data-customer-switch="'+esc(current.id)+'">Switch</button><button id="game-customer-release" class="game-text-button" type="button" data-econ-action="'+customerAction('release',customerSlot,'',current.id)+'">Release</button></div>'+(customerOrderChoice(current) || '<p class="game-contract-help">'+(current.paused?'Resume starts a new shipment timer.':'Ships automatically when ready. Pause to free the saved goods.')+'</p>')+'</div>';
    }
    var next=contracts.nextUnlock;
    return '<section class="game-panel game-customer-contracts" aria-label="Customer contracts">'+panelHead('Regular buyers',active.length+' / '+slots+' signed')+'<div class="game-contract-panel"><p class="game-contract-intro">Automatic shipments at 90% of '+(operatingStatement(s)?'shop payout':'retail')+'. Regular buyers get goods first.</p><div class="game-contract-slots" role="group" aria-label="Customer slots">'+slotMarkup+'</div><div class="game-contract-body">'+content+'</div><div class="game-contract-footer"><span>'+ym(contracts.earned)+' earned</span><button class="game-customer-motion" type="button" data-customer-motion aria-pressed="'+customerArtEnabled+'" aria-label="Animate customer emotes">Motion '+(customerArtEnabled?'on':'off')+'</button><span>'+(next?'Slot '+next.slots+' at '+next.buildings+' businesses':'All '+slots+' slots unlocked')+'</span></div></div></section>';
  }

  function renderProductionInventory(el,s,b,market) {
    if(market){
      el.innerHTML=notice(s)+'<div class="game-market-surface'+(s.customerContracts?' has-contracts':'')+'"><div class="game-market-income'+(s.customerContracts?' has-contracts':'')+'"><section class="game-market-orders" aria-label="Delivery orders">'+panelHead(connectedProgression(s)?'Orders':'Projects & deliveries',connectedProgression(s)?'Deliver goods · earn cash & materials':'Build your town · earn cash & materials')+ordersMarkup(s)+'</section>'+customerContractsMarkup(s)+'</div></div>'+statusLine();
      return;
    }
  }

  function businessPicker(s,b){
    return '<div class="game-business-picker">'+art({buildingId:b.id,buildingName:b.name,paused:true,artLevel:b.artLevel})+'<label for="game-business-choice">Business</label><select id="game-business-choice">'+s.buildings.map(function(item){return '<option value="'+item.slot+'"'+(item.slot===b.slot?' selected':'')+'>'+esc(item.name)+'</option>';}).join('')+'</select>'+growthButton(s)+'</div>';
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
      if(desk)desk.innerHTML=panelHead('Practice investing','')+'<div class="game-panel-body"><p class="game-hint">Your trading desk uses a separate practice portfolio. Your '+(connectedProgression(s)?'group':'town')+' keeps its cash.</p>'+linkButton('./port_trading.html','Open trading desk ↗',' k-btn--alt')+'</div>';
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
        [operatingStatement(s)?'Take-home sales / min':productionModel(s)?'Income / min':'Sales / min', incomeRate(s.incomePerMinute == null ? s.revenuePerDay/1440 : s.incomePerMinute)],
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
    var prestige=document.getElementById('game-operations-prestige');if(prestige)prestige.hidden=true;
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
    renderOperationsPrestige(snapshot);
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
    renderBusinessDialogs(snapshot);
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
    if(focusId && /^(game-wf-|game-staff-|game-growth-|game-quest-|game-activity-|game-activities-|game-project-|game-next-goal-|game-stock-unlock-)/.test(focusId)){var managementControl=document.getElementById(focusId);if(managementControl && !managementControl.disabled)managementControl.focus({preventScroll:true});}
    if(focusId==='game-business-choice' || focusId==='game-business-focus'){var businessChoice=document.getElementById(focusId);if(businessChoice)businessChoice.focus({preventScroll:true});}
    var openBreakfast=document.querySelector('#game-breakfast[open]');
    if(openBreakfast && !openBreakfast.contains(document.activeElement))openBreakfast.querySelector('[data-close-breakfast]').focus({preventScroll:true});
    if(window.YomamaFit)window.YomamaFit.render();
    if(focusId && /^(game-customer-|game-tab-)/.test(focusId)){var customerControl=document.getElementById(focusId);if(customerControl && !customerControl.disabled)customerControl.focus({preventScroll:true});}
    renderCashChip(snapshot);
    var stats=document.getElementById('buildings-side-stats');
    if(stats) stats.innerHTML=line('Buildings owned',snapshot.buildingsOwned)+line('Net worth',ym(snapshot.netWorth))+line(operatingStatement(snapshot)?'Est. take-home sales / day':productionModel(snapshot)?'Est. revenue / day':'Revenue / day',ym(snapshot.revenuePerDay));
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
    syncBusinessClocks();
    businessMetricChanges={};
  }

  var statusTimer = null;
  function setStatus(text, tone) {
    if(statusTimer) window.clearTimeout(statusTimer);
    statusMessage = text ? { text: text, tone: tone } : null;
    var messages=document.getElementById('buildings-lab-log');if(messages && text)messages.textContent=text;
    document.querySelectorAll('[data-econ-status]').forEach(function (el) {
    {
      el.textContent = text || '';
      el.className = 'k-status' + (tone === 'error' ? ' k-status--bad' : (tone === 'success' ? ' k-status--good game-visually-hidden' : ''));
    }
    });
    if(text && tone==='success') statusTimer=window.setTimeout(function(){setStatus('', '');},8000);
  }

  function trackBusinessMetrics(previous,next) {
    businessMetricChanges={};
    if(!previous || !document.getElementById('econ-building') || previous.tick>next.tick)return;
    (next.buildings || []).forEach(function(b){
      var before=(previous.buildings || []).find(function(item){return item.slot===b.slot && item.id===b.id;});
      if(!before)return;
      var changes={}, oldActivity=before.activity || {}, activity=b.activity || {};
      var oldFinances=financeValues(before), finances=financeValues(b);
      if(oldFinances.sales!==finances.sales)changes.income=true;
      if(oldFinances.cost!==finances.cost || oldFinances.estimatedCost!==finances.estimatedCost)changes.cost=true;
      if(oldFinances.profit!==finances.profit || oldFinances.estimatedProfit!==finances.estimatedProfit)changes.profit=true;
      if(oldFinances.margin!==finances.margin)changes.margin=true;
      if(oldActivity.producedUnits!=null && activity.producedUnits!=null && oldActivity.producedUnits!==activity.producedUnits)changes.producedActual=true;
      if(oldActivity.soldUnits!=null && activity.soldUnits!=null && oldActivity.soldUnits!==activity.soldUnits)changes.soldActual=true;
      if(before.productionCapacityPerMinute!==b.productionCapacityPerMinute)changes.produced=true;
      if(before.customerCapacityPerMinute!==b.customerCapacityPerMinute)changes.sold=true;
      if(before.stored!==b.stored || before.capacity!==b.capacity)changes.stock=true;
      businessMetricChanges[b.slot]=changes;
    });
  }

  function trackBusinessClocks(s) {
    var now=Date.now(), nextClocks={};
    ((s.customerContracts || {}).active || []).forEach(function(c){
      var before=businessClocks[c.id], left=Math.max(0,Number(c.nextDeliverySeconds) || 0)*1000;
      var due=Number(s.tick || 0)*Number(s.tickSeconds || 15)+left/1000;
      var paused=!!(s.paused || c.paused);
      if(before && before.due===due && before.deliveries===c.deliveries && before.paused===paused){
        var priorLeft=before.paused?before.remaining:Math.max(0,before.deadline-now);
        left=Math.min(left,priorLeft);
      }
      nextClocks[c.id]={due:due,deliveries:c.deliveries,paused:paused,remaining:left,deadline:now+left};
    });
    businessClocks=nextClocks;
  }

  function syncBusinessClocks() {
    if(!snapshot)return;
    document.querySelectorAll('[data-business-feed]').forEach(function(node){
      node.textContent=!businessConnected?'Reconnecting':snapshot.paused?'Paused':'Live';
      node.dataset.state=!businessConnected?'offline':snapshot.paused?'paused':'live';
    });
    if(!businessConnected)return;
    var contracts=(snapshot.customerContracts || {}).active || [];
    document.querySelectorAll('[data-business-countdown]').forEach(function(node){
      var c=contracts.find(function(item){return item.id===node.dataset.businessCountdown;}), clock=businessClocks[node.dataset.businessCountdown];
      if(!c || !clock)return;
      var left=Math.max(0,Math.ceil((clock.paused?clock.remaining:clock.deadline-Date.now())/1000));
      node.dataset.remainingSeconds=String(left);
      node.dataset.state=clock.paused?'paused':left>0?'counting':c.status==='waiting'?'waiting':'due';
      node.textContent=clock.paused?(snapshot.paused?'Class paused':'Buyer paused'):left>0?duration(left):c.status==='waiting'?'Waiting':'Due now';
    });
  }

  function apply(payload) {
    if (!payload) return;
    // Login is disabled for now: the server hands out a seat on first contact.
    // Keep it, so every page in this browser is the same player.
    if (payload.token && (!session || session.token !== payload.token)) {
      session = { token: payload.token, name: payload.name || 'PLAYER', code: payload.code || '' };
      try { window.localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch (_) {}
    }
    if(!businessConnected && statusMessage && statusMessage.text==='Connection lost. We will try again shortly.')setStatus('', '');
    if(!businessConnected || businessClockNeedsSync)businessClocks={};
    businessClockNeedsSync=false;
    businessConnected=true;
    trackOrderClocks(payload);
    trackBusinessMetrics(snapshot,payload);
    trackBusinessClocks(payload);
    trackCustomerDeliveries(snapshot,payload);
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
    if(refreshPending)return refreshPending;
    var version=actionVersion;
    refreshPending=fetchState().then(function(payload){if(version===actionVersion && !busy)apply(payload);}).catch(function (err) {
      if(version!==actionVersion || busy)return;
      businessConnected=false;
      syncBusinessClocks();
      if (err && err.status === 401) renderOffline('This class session has expired. Join again to keep playing.');
      else {
        clearCompetition();
        setStatus('Connection lost. We will try again shortly.', 'error');
      }
    }).then(function(){refreshPending=null;});
    return refreshPending;
  }

  // --------------------------------------------------------------- actions --
  function act(name) {
    if (busy) {
      if(name.indexOf('replace:')===0)pendingRerolls.push(Number(name.split(':')[1]));
      return;
    }
    var path = '/' + name;
    var body = {};
    var skippedOpportunity = false;
    var savedOrder = false;
    var savedJackpot = false;
    var deliveredOrder = false;
    var deliveredJackpot = false;
    var skippedJackpot = false;
    if (name.indexOf('workforce:')===0) {
      var workforceBits=name.split(':');path='/api/game/workforce';
      try { body=JSON.parse(decodeURIComponent(workforceBits.slice(2).join(':'))); }
      catch (_) { setStatus('Refresh Operations and try again','error');return; }
      body.action=workforceBits[1];
    } else if (name.indexOf('business:')===0) {
      var businessBits=name.split(':');path='/api/game/business';body={action:businessBits[1],buildingId:decodeURIComponent(businessBits[2])};
      if(businessBits[3])body.staffId=decodeURIComponent(businessBits[3]);
    } else if(name.indexOf('progression:')===0) {
      var progressBits=name.split(':');path='/api/game/progression';body={action:progressBits[1]};
      if(body.action==='research')body.researchId=decodeURIComponent(progressBits[2]);
      else if(body.action==='craft')body.equipmentId=decodeURIComponent(progressBits[2]);
      else {body.questId=decodeURIComponent(progressBits[2]);if(progressBits[3])body[body.action==='quest_plan'?'choice':'recipe']=decodeURIComponent(progressBits[3]);}
    } else if (name.indexOf('customer:') === 0) {
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
      var oldOrder=snapshot && orderAt(snapshot,body.offerIndex);
      if(order[0]==='commit')body.committed=!(oldOrder && oldOrder.committed);
      var matchingOrder=!!oldOrder && oldOrder.id===body.orderId;
      skippedJackpot=order[0]==='replace' && matchingOrder && oldOrder.rarity==='jackpot';
      skippedOpportunity=order[0]==='replace' && matchingOrder && (oldOrder.canFulfill===true || skippedJackpot);
      savedOrder=order[0]==='commit' && body.committed===true && matchingOrder;
      savedJackpot=savedOrder && oldOrder.rarity==='jackpot';
      deliveredOrder=order[0]==='fulfill' && matchingOrder;
      deliveredJackpot=deliveredOrder && oldOrder.rarity==='jackpot';
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

    if(body.slot!=null && !/^customer:/.test(name)){
      var expectedBusiness=(snapshot.buildings || []).find(function(item){return item.slot===body.slot;});
      if(expectedBusiness && expectedBusiness.buildingId)body.buildingId=expectedBusiness.buildingId;
    }
    busy = true;
    actionVersion++;
    document.querySelectorAll('[data-econ-action]').forEach(function(button){button.disabled=button.dataset.econAction.indexOf('replace:')!==0;button.setAttribute('aria-busy','true');});
    request('POST', path, body).then(function (payload) {
      busy = false;
      var receipt = payload.receipt;
      var upgradeBuilding=name.indexOf('upgrade:')===0 && snapshot && (snapshot.buildings || []).find(function(b){return b.slot===body.slot;});
      var upgradePreview=upgradeBuilding && (upgradeBuilding.upgrades || {})[body.kind];
      var incomeBefore=upgradePreview && upgradePreview.incomeBefore!=null?upgradePreview.incomeBefore:upgradePreview && upgradePreview.businessIncomeBefore!=null?upgradePreview.businessIncomeBefore:forecastIncome(snapshot);
      var incomeAfter=upgradePreview && upgradePreview.incomeAfter!=null?upgradePreview.incomeAfter:upgradePreview && upgradePreview.businessIncomeAfter!=null?upgradePreview.businessIncomeAfter:forecastIncome(payload);
      if(skippedOpportunity)reactToOrder(body.offerIndex,'missed',skippedJackpot?'Skipped a jackpot order':'Skipped a ready order');
      if(savedOrder)reactToOrder(body.offerIndex,'saved',savedJackpot?'Saved a jackpot order':'Saved an order',savedJackpot?'lucky-seven-pixel.svg':null);
      if(deliveredOrder)reactToOrder(body.offerIndex,'delivered',deliveredJackpot?'Delivered a jackpot order':'Delivered an order',deliveredJackpot?'gold-bars-pixel.svg':null);
      if(name.indexOf('customer:')===0)customerSwitchId=null;
      if(name.indexOf('business:salvage:')===0){salvageBuildingId=null;var closedDialog=document.getElementById('game-business-dialog');if(closedDialog)closedDialog.close();}
      apply(payload);
      if(name.indexOf('upgrade:')===0 && receipt){
        if(receipt.incomeBefore==null)receipt.incomeBefore=incomeBefore;
        if(receipt.incomeAfter==null)receipt.incomeAfter=incomeAfter;
      }
      if(name.indexOf('customer:')===0){var nextCustomerControl=document.getElementById(body.action==='release'?'game-customer-choice':body.action==='upgrade' || body.action==='downgrade'?'game-customer-size':'game-customer-toggle');if(nextCustomerControl)nextCustomerControl.focus({preventScroll:true});}
      if (productionModel(payload)) {
        if(name.indexOf('workforce:')===0) setStatus(receipt && receipt.message || 'Workforce updated','success');
        else if(name.indexOf('business:')===0 || name.indexOf('progression:')===0) setStatus(receipt && receipt.message || ({pause:'Production paused · no new production costs',resume:'Business resumed',hire:'Shift started',salvage:'Business closed · salvage paid',research:'Research learned',craft:'Equipment crafted',quest_plan:'Plan selected',quest_batch:'Practice batch complete',quest_finish:'Quest complete · reward unlocked',quest_reset:'Practice supplies restored'}[body.action]) || 'Saved','success');
        else if (name.indexOf('customer:')===0) setStatus(receipt && receipt.message || ({accept:'Customer signed · automatic shipments start after the first interval',switch:'Customer switched · a new shipment timer has started',pause:'Customer paused · held goods released',resume:'Customer resumed · a new shipment timer has started',release:'Customer released · slot and goods available',upgrade:'Larger order accepted · a new shipment timer has started',downgrade:'Smaller order restored · a new shipment timer has started'}[body.action]),'success');
        else if (receipt && receipt.kind === 'breakfast') setStatus(receipt.message,'success');
        else if (receipt && receipt.kind === 'sell') setStatus('Stock sold · '+ym(receipt.net == null ? receipt.gross : receipt.net),'success');
        else if (name.indexOf('upgrade:')===0) setStatus(upgradeMessage(receipt),'success');
        else if (name.indexOf('commit:')===0) setStatus(body.committed?'Saving this order’s goods · surplus keeps selling':independentProduction(payload)?'Goods released to customers and orders':'Goods released to customers and recipes','success');
        else if (name.indexOf('focus:')===0) setStatus('Specialty changed · check your new output','success');
        else if (name.indexOf('reserve:')===0) setStatus(body.reserve?'Saving goods for orders':'Customer sales resumed','success');
        else if (name.indexOf('processing:')===0) setStatus(body.enabled?'Processing resumed':'Recipes paused','success');
        else if (name.indexOf('fulfill:')===0) setStatus('Delivered · '+ym(receipt && receipt.reward)+(receipt && receipt.materials?' · +'+materialAmount(receipt.materials):'')+(receipt && receipt.projectReward?' · '+receipt.projectReward:''),'success');
        else if (name.indexOf('replace:')===0) setStatus(skippedOpportunity?'':'New order ready','success');
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
    if(event.target.classList && event.target.classList.contains('game-management-dialog')){var returnControl=event.target._returnFocusId && document.getElementById(event.target._returnFocusId);if(returnControl)returnControl.focus({preventScroll:true});}
    if(event.target.id==='game-breakfast'){
      var trigger=document.getElementById(event.target._returnFocusId) || document.querySelector('[data-game-breakfast]');
      if(trigger)trigger.focus({preventScroll:true});
    }
  },true);

  document.addEventListener('click', function (event) {
    if(event.target.closest('[data-related-breakfast]')){var relatedBreakfast=document.getElementById('game-breakfast');if(relatedBreakfast){relatedBreakfast._returnFocusId='game-quest-breakfast';document.getElementById('game-breakfast-content').innerHTML=breakfastMarkup(snapshot);relatedBreakfast.showModal();}return;}
    var closeBusiness=event.target.closest('[data-close-business-dialog]');
    if(closeBusiness){closeBusiness.closest('dialog').close();return;}
    var growthOpen=event.target.closest('[data-game-growth]');
    if(growthOpen){growthContext=null;growthEquipment=null;openBusinessDialog('game-growth',growthOpen);return;}
    var requirementOpen=event.target.closest('[data-requirement-kind]');
    if(requirementOpen){openExpansionRequirement(requirementOpen);return;}
    var earnOpen=event.target.closest('[data-growth-earn]');
    if(earnOpen){activitiesKind='quests';activitiesPurpose=earnOpen.dataset.growthEarn;openBusinessDialog('game-activities',earnOpen);return;}
    var kitResearch=event.target.closest('[data-equipment-research]');
    if(kitResearch){
      var kit=(snapshot.progression.equipment || []).find(function(e){return e.id===kitResearch.closest('[data-equipment-id]').dataset.equipmentId;});
      var requiredResearch=(snapshot.progression.research || []).find(function(r){return r.id===kitResearch.dataset.equipmentResearch;});
      if(requiredResearch){growthTab='research';growthBranch=requiredResearch.branch;growthContext={buildingName:kit && (kit.usedFor || [])[0] || 'this business',researchId:requiredResearch.id};render();focusGrowthTarget('research',requiredResearch.id);}return;
    }
    if(event.target.closest('[data-growth-all-equipment]')){growthEquipment=null;growthContext=null;render();document.getElementById('game-growth-tab-equipment').focus({preventScroll:true});return;}
    var activitiesOpen=event.target.closest('[data-building-activities]');
    if(activitiesOpen){activitiesKind=activitiesOpen.dataset.buildingActivities;activitiesPurpose=null;openBusinessDialog('game-activities',activitiesOpen);return;}
    var projectOpen=event.target.closest('[data-game-project]');
    if(projectOpen){selectedProject=projectOpen.dataset.gameProject;openBusinessDialog('game-project',projectOpen);return;}
    var questOpen=event.target.closest('[data-game-quest]');
    if(questOpen){selectedQuest=questOpen.dataset.gameQuest;openBusinessDialog('game-quest',questOpen);return;}
    var closeOpen=event.target.closest('[data-business-close]');
    if(closeOpen){salvageBuildingId=closeOpen.dataset.businessClose;openBusinessDialog('game-business-dialog',closeOpen);return;}
    var growthTabButton=event.target.closest('[data-growth-tab]');
    if(growthTabButton){growthTab=growthTabButton.dataset.growthTab;if(growthTab==='prestige')growthContext=null;render();return;}
    var branchButton=event.target.closest('[data-growth-branch]');
    if(branchButton){growthBranch=branchButton.dataset.growthBranch;growthContext=null;render();return;}
    if(event.target.closest('[data-customer-motion]')){
      customerArtEnabled=!customerArtEnabled;
      document.querySelectorAll('[data-customer-motion]').forEach(function(button){button.setAttribute('aria-pressed',String(customerArtEnabled));button.textContent='Motion '+(customerArtEnabled?'on':'off');});
      syncCustomerEmotes();return;
    }
    var customerSlotButton=event.target.closest('[data-customer-slot]');
    if(customerSlotButton){customerSlot=Number(customerSlotButton.dataset.customerSlot);customerSwitchId=null;render();return;}
    var customerSwitch=event.target.closest('[data-customer-switch]');
    if(customerSwitch){customerSwitchId=customerSwitch.dataset.customerSwitch;render();var chooser=document.getElementById('game-customer-choice');if(chooser)chooser.focus({preventScroll:true});return;}
    if(event.target.closest('[data-customer-cancel]')){customerSwitchId=null;render();var switchControl=document.getElementById('game-customer-switch');if(switchControl)switchControl.focus({preventScroll:true});return;}
    var breakfastDialog=document.getElementById('game-breakfast');
    if(breakfastDialog && event.target.closest('[data-game-breakfast]')){breakfastDialog._returnFocusId=event.target.closest('[data-game-breakfast]').id;document.getElementById('game-breakfast-content').innerHTML=breakfastMarkup(snapshot);breakfastDialog.showModal();return;}
    if(breakfastDialog && event.target.closest('[data-close-breakfast]')){breakfastDialog.close();return;}
    var chosen=event.target.closest('[data-select-building]');
    if(chosen){selectedSlot=Number(chosen.dataset.selectBuilding);render();return;}
    var step=event.target.closest('[data-quiz-step]');
    if(step){quizStep+=Number(step.dataset.quizStep);render();var question=document.querySelector('.game-quiz-question:not([hidden]) input');if(question)question.focus();return;}
    var deliveryDialog=document.getElementById('game-deliveries');
    if(deliveryDialog && event.target.closest('[data-game-deliveries]')){deliveryDialog.showModal();return;}
    if(deliveryDialog && event.target.closest('[data-close-deliveries]')){deliveryDialog.close();return;}

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
    if(event.target.id==='game-activity-business'){selectedSlot=Number(event.target.value);render();return;}
    if(event.target.id==='game-staff-choice'){staffChoices[selectedBuilding(snapshot).buildingId]=event.target.value;render();return;}
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
    pollTimer = window.setInterval(refresh, document.getElementById('econ-building')?3000:(Number(snapshot && snapshot.tickSeconds)*1000 || POLL_MS));
    tickTimer = window.setInterval(function () {
      syncCustomerEmotes();
      syncBusinessClocks();
      syncOrderClocks();
      if(snapshot && snapshot.paused)return;
      document.querySelectorAll('[data-econ-countdown]').forEach(function (node) {
        if(node.dataset.countdownPaused==='true')return;
        var left = Math.max(0, Number(node.getAttribute('data-econ-countdown')) - 1);
        node.setAttribute('data-econ-countdown', left);
        node.textContent = left > 0 ? duration(left) : 'any moment now';
      });
    }, 1000);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {businessClockNeedsSync=true;refresh();}
  });

  function showOvernight(r) {
    var dialog=document.getElementById('econ-overnight');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='econ-overnight';dialog.className='econ-kid';document.body.appendChild(dialog);}
    if (snapshot && productionModel(snapshot)) {
      dialog.innerHTML='<h2>Welcome back</h2>'+line(operatingStatement(snapshot)?'Shop cash after selling fees':'Retail sales',ym(r.retailEarned),'k-good')+(r.customerEarned || r.customerDeliveries?line(operatingStatement(snapshot)?'Buyer cash after selling fees':'Customer contracts',ym(r.customerEarned),'k-good')+line('Customer shipments',units(r.customerDeliveries)):'')+line('Goods made',units(r.unitsProduced))+(r.builds?line('Businesses opened',r.builds):'')+(r.offlineTicksSkipped>0?'<p class="game-hint">'+units(snapshot.offlineHours || 12)+'h offline limit reached.</p>':'')+'<button class="k-btn" data-overnight-close>Continue</button>';
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

  window.YomamaEcon = { refresh: refresh, state: function () { return snapshot; }, format: ym, resourceBar: resourceBar };
}());
