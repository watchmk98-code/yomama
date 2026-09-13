/* Shared worker population, business focus trees and the specialist HQ academy. */
(function () {
  'use strict';
  var tabs = [['focus', 'Focus tree'], ['team', 'Team'], ['recipes', 'Recipes'], ['quests', 'Quests'], ['hq', 'Advanced HQ']];
  var tab = { '#team': 'team', '#workers': 'team', '#quests': 'quests', '#projects': 'projects', '#hq': 'hq', '#recipes': 'recipes' }[location.hash] || 'focus';
  var drafts = {}, current = null, helpers = null, selectedNode = 'orientation', teamView = location.hash==='#workers'?'assignments':'recruitment', hqView = 'academy', listPages = {};
  var branches = [['production', 'Production', 'Make goods'], ['sales', 'Customers', 'Find buyers'], ['efficiency', 'Efficiency', 'Lower costs']];

  function esc(value) { return helpers.esc(value == null ? '' : String(value)); }
  function number(value) { return Math.max(0, Math.floor(Number(value) || 0)); }
  function action(name, body) { return 'workforce:' + name + ':' + encodeURIComponent(JSON.stringify(body || {})); }
  function button(id, label, encoded, disabled, extra) {
    return '<button id="game-wf-' + esc(id) + '" type="button" class="wf-button' + (extra ? ' ' + extra : '') + '"' + (encoded ? ' data-econ-action="' + esc(encoded) + '"' : '') + (disabled ? ' disabled' : '') + '>' + esc(label) + '</button>';
  }
  function note(value, extra) { return value ? '<p class="wf-note' + (extra ? ' ' + extra : '') + '">' + esc(value) + '</p>' : ''; }
  function timer(seconds, paused) {
    return '<span data-econ-countdown="' + Math.max(0, Number(seconds) || 0) + '" data-countdown-paused="' + !!paused + '">' + esc(helpers.duration(seconds)) + '</span>';
  }
  function meter(progress, label) {
    var amount = Math.max(0, Math.min(100, (Number(progress) || 0) * 100));
    return '<div class="wf-meter" role="progressbar" aria-label="' + esc(label) + '" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + Math.round(amount) + '"><span style="width:' + amount.toFixed(2) + '%"></span></div>';
  }
  function owned(team, id) { return (team.nodes || []).some(function (node) { return node.id === id && node.owned; }); }
  function enabledBranch(team, branch) { return owned(team, branch === 'production' ? 'orientation' : branch); }
  function sameAllocation(a, b) { return branches.every(function (branch) { return number(a[branch[0]]) === number(b[branch[0]]); }); }
  function allocation(team) {
    var saved = team.allocation || {}, draft = drafts[team.buildingId];
    if (draft && sameAllocation(draft.allocation, saved) && draft.trainingBranch === team.trainingBranch) { delete drafts[team.buildingId]; draft = null; }
    return draft || { allocation: { production: number(saved.production), sales: number(saved.sales), efficiency: number(saved.efficiency) }, trainingBranch: team.trainingBranch || 'production' };
  }
  function assigned(values) { return branches.reduce(function (sum, branch) { return sum + number(values[branch[0]]); }, 0); }
  function connected(snapshot) { return !!(snapshot.progression && snapshot.progression.mode === 'connected'); }
  function population(snapshot) { var pool = (snapshot.workforce || {}).population; return pool && pool.enabled ? pool : null; }
  function panelTabs(snapshot) {
    var available = connected(snapshot) ? tabs.slice(0, 4).concat([['projects', 'Group projects']], tabs.slice(4)) : tabs;
    return population(snapshot) ? available.map(function (item) { return item[0] === 'team' ? ['team', 'Workers'] : item; }) : available;
  }
  function changeDraft(team) {
    if (!drafts[team.buildingId]) {
      var initial = allocation(team);
      drafts[team.buildingId] = { allocation: Object.assign({}, initial.allocation), trainingBranch: initial.trainingBranch };
    }
    return drafts[team.buildingId];
  }
  function redraw(focusId) {
    helpers.render();
    var control = focusId && document.getElementById(focusId);
    if (control && !control.disabled) control.focus({ preventScroll: true });
  }
  function subnav(group, items, selected) {
    return '<div class="wf-subnav" role="group" aria-label="' + (group === 'team' ? 'Team management' : 'HQ management') + '">' + items.map(function (item) { return '<button id="game-wf-' + group + '-' + item[0] + '" type="button" data-wf-view="' + item[0] + '" data-wf-group="' + group + '" aria-pressed="' + (selected === item[0]) + '">' + esc(item[1]) + '</button>'; }).join('') + '</div>';
  }
  function summary(team, snapshot) {
    var pool = population(snapshot);
    if (pool) return '<div class="wf-overview wf-population-summary" aria-label="Conglomerate worker population"><span><img src="./assets/game-art/ui/workers.svg" alt="" width="20" height="20"><b data-wf-population-total>' + number(pool.total) + '</b> workers</span>' + (connected(snapshot) && tab !== 'focus' ? '<span class="wf-prestige" data-wf-prestige><b>' + number(snapshot.progression.prestige) + '</b> Prestige available</span>' : '') + '</div>';
    var state = snapshot.paused ? 'Class paused' : team.paused ? 'Training paused' : team.trainers ? 'Training team' : 'Ready to develop';
    return '<div class="wf-overview"><span class="wf-state' + (team.paused || snapshot.paused ? ' is-paused' : '') + '"><i aria-hidden="true"></i>' + state + '</span><span><b>' + number(team.trainers) + '</b> / ' + number(team.trainerCap) + ' trainers</span><span><b>' + number(team.workers) + '</b> / ' + number(team.workerCap) + ' crew</span>' + (connected(snapshot) ? '<span class="wf-prestige" data-wf-prestige><b>' + number(snapshot.progression.prestige) + '</b> Prestige available</span>' : '') + (team.hqSupported ? '<span class="wf-hq-badge">HQ supported</span>' : '') + '</div>';
  }
  function treeNode(node, team, snapshot, root) {
    if (!node) return '';
    var ready = node.unlocked !== undefined ? node.unlocked : (node.requires || []).every(function (requirement) { return owned(team, typeof requirement === 'string' ? requirement : requirement.id); });
    var status = node.owned ? 'Completed' : ready ? 'Available' : 'Locked';
    var price = number(node.prestigeCost) ? number(node.prestigeCost) + ' Prestige + ' + helpers.ym(node.cost) : connected(snapshot) && !node.cost ? 'Free' : helpers.ym(node.cost);
    return '<article class="wf-node' + (root ? ' wf-root' : '') + (node.owned ? ' is-owned' : ready ? ' is-available' : ' is-locked') + '" data-wf-node="' + esc(node.id) + '"><div class="wf-node-top"><span class="wf-node-state">' + (node.owned ? '✓ ' : '') + status + '</span>' + (root ? '<span class="wf-node-step">START HERE</span>' : '') + '</div><h3>' + esc(node.name) + '</h3><p>' + esc(node.effect) + '</p>' + button('node-' + node.id, node.owned ? 'Completed' : 'Develop · ' + price, action('focus', { buildingId: team.buildingId, nodeId: node.id }), node.owned || !node.canBuy || snapshot.paused, 'wf-node-buy') + (!node.owned && !node.canBuy ? note(node.why, 'wf-node-why') : '') + '</article>';
  }
  function prestigeBox(snapshot) {
    if (!connected(snapshot)) return '';
    return '<div class="wf-focus-prestige" data-wf-prestige aria-label="Prestige available"><img src="./assets/game-art/ui/prestige.svg" alt="" width="34" height="34" aria-hidden="true"><strong>' + number(snapshot.progression.prestige) + '</strong><span>Prestige available</span></div>';
  }
  function focusTree(team, snapshot) {
    var nodes = team.nodes || [], selected = nodes.find(function (node) { return node.id === selectedNode; }) || nodes[0];
    function mapNode(node, root) {
      if (!node) return '';
      var ready = node.unlocked !== undefined ? node.unlocked : (node.requires || []).every(function (requirement) { return owned(team, typeof requirement === 'string' ? requirement : requirement.id); });
      return '<button id="game-wf-map-' + esc(node.id) + '" type="button" class="wf-map-node' + (root ? ' wf-map-root' : '') + (node.owned ? ' is-owned' : ready ? ' is-available' : ' is-locked') + '" data-wf-focus="' + esc(node.id) + '" aria-pressed="' + (selected.id === node.id) + '"><strong>' + esc(node.name) + '</strong><span>' + (node.owned ? '✓ Completed' : ready ? 'Available' : 'Locked') + '</span></button>';
    }
    return '<section class="wf-focus"><div class="wf-section-heading"><div><h2>Choose your business focus</h2><p>Develop your team through three connected paths.</p></div></div><div class="wf-focus-layout"><div class="wf-focus-map" aria-label="' + esc(team.name) + ' focus tree">' + mapNode(nodes.find(function (node) { return node.id === 'orientation'; }), true) + '<div class="wf-map-branches">' + branches.map(function (branch) {
      return '<section class="wf-map-branch" aria-label="' + branch[1] + ' focus"><h3>' + branch[1] + '</h3>' + nodes.filter(function (node) { return node.id !== 'orientation' && node.branch === branch[0]; }).map(function (node) { return mapNode(node, false); }).join('') + '</section>';
    }).join('') + '</div></div><div class="wf-focus-detail">' + treeNode(selected, team, snapshot, false) + prestigeBox(snapshot) + '</div></div></section>';
  }
  function populationPanel(team, building, snapshot) {
    var pool = population(snapshot), growth = pool.growth || {}, salvage = building.salvage || {};
    if (teamView !== 'business') teamView = 'recruitment';
    return '<section class="wf-team is-population">' + subnav('team', [['recruitment','Population'],['business','Business']], teamView) +
      '<section class="wf-population-intro" data-wf-population-view="recruitment"><div class="wf-section-heading"><div><h2>Worker population</h2><p>Your conglomerate has ' + number(pool.total) + ' workers.</p></div></div>' +
      '<div class="wf-population-growth"><div><strong>+' + number(growth.workersPerBusiness) + '</strong><span>First opening of each business type</span></div><div><strong>+' + number(growth.workersPerProductionLevel) + '</strong><span>Each new highest production level</span></div></div>' +
      note('Workers have no gameplay role yet. There are no assignments, staffing requirements or worker bonuses.') +
      note('Business growth adds up to ' + number(growth.capacityPerBusiness) + ' workers per business type. Rebuilding does not repeat arrivals. HQ specialists are separate.') + '</section>' +
      '<div class="wf-business-controls" data-wf-population-view="business"><div class="game-business-control"><div><h3>' + (building.paused ? 'Business paused' : 'Business open') + '</h3>' + note('Pause production and operating costs.') + '</div>' + button('business-toggle', building.paused ? 'Resume' : 'Pause', 'business:' + (building.paused ? 'resume' : 'pause') + ':' + encodeURIComponent(building.buildingId), snapshot.paused, 'wf-button-light') + '</div><div class="game-salvage-entry"><div><h3>Close this business</h3>' + note('Salvage ' + helpers.ym(salvage.value) + ' · ' + helpers.duration(salvage.cooldownSeconds) + ' before rebuilding') + '</div><button id="game-wf-salvage-open" type="button" class="game-text-button" data-business-close="' + esc(building.buildingId) + '">Review →</button></div></div></section>';
  }
  function teamPanel(team, building, snapshot) {
    if (population(snapshot)) return populationPanel(team, building, snapshot);
    var draft = allocation(team), count = assigned(draft.allocation), unassigned = number(team.workers) - count;
    var dirty = !!drafts[team.buildingId], paused = snapshot.paused || team.paused, hire = team.hire || {}, salvage = building.salvage || {};
    var workerStatus = team.workers >= team.workerCap ? 'Crew roster full — hire another trainer to add positions.' : !team.trainers ? 'Hire your first trainer to begin.' : paused ? 'Training resumes when this business and class are running.' : 'Next worker in ';
    var workerClock = !paused && team.nextWorkerSeconds != null && team.workers < team.workerCap ? timer(team.nextWorkerSeconds, paused) : '';
    var hireLabel = !owned(team, 'orientation') ? 'Develop orientation first' : team.hires >= 3 ? 'All permanent hires recruited' : hire.remainingSeconds > 0 ? 'Recruitment cooling down' : 'Hire permanent trainer · ' + helpers.ym(hire.cost);
    var html = '<section class="wf-team">' + subnav('team', [['recruitment','Recruitment'],['training','Training'],['assignments','Assignments'],['business','Business']], teamView) + '<div class="wf-team-columns"><section class="wf-team-training"><div class="wf-training-count"><strong>' + number(team.trainers) + '<small> / ' + number(team.trainerCap) + '</small></strong><div><h3>Trainers</h3><span>' + number(team.hires) + ' personally hired' + (team.hqSupported ? ' · HQ develops more' : '') + '</span></div></div>' + button('hire', hireLabel, action('hire', { buildingId: team.buildingId }), !hire.canHire || snapshot.paused) + (hire.remainingSeconds > 0 ? '<p class="wf-note">Next recruitment in ' + timer(hire.remainingSeconds, snapshot.paused) + '</p>' : !hire.canHire ? note(hire.why) : '') + note('Pay once to hire. Recruitment reopens after ' + helpers.duration(snapshot.workforce.recruitmentCooldownSeconds || 1800) + ' of class time.') + '<div class="wf-worker-training"><div class="wf-training-count"><strong>' + number(team.workers) + '<small> / ' + number(team.workerCap) + '</small></strong><div><h3>Trained crew</h3><span>' + (team.trainers ? 'Each trainer develops one worker per ' + helpers.duration(snapshot.workforce.workerTrainingSeconds || 300) : 'Your trainer starts the first worker') + '</span></div></div>' + meter(team.workerProgress, 'Next worker training progress') + '<p class="wf-note">' + esc(workerStatus) + workerClock + '</p></div>' + (team.hqSupported ? '<div class="wf-academy-progress"><h3>HQ trainer development</h3>' + meter(team.trainerProgress, 'Next trainer development progress') + '<p class="wf-note">' + (paused ? 'Training paused' : team.nextTrainerSeconds != null ? 'Next trainer in ' + timer(team.nextTrainerSeconds, paused) : 'Trainer positions filled') + '</p></div>' : '') + '</section><section class="wf-allocation" aria-label="Worker assignments"><div class="wf-allocation-heading"><h3>Assign your crew</h3><strong class="' + (unassigned < 0 ? 'k-bad' : '') + '">' + unassigned + ' unassigned</strong></div>' + branches.map(function (branch) {
      var key = branch[0], unlocked = enabledBranch(team, key), value = number(draft.allocation[key]);
      var effect = (team.effects || {})[key === 'sales' ? 'customer' : key] || 0;
      var effectText = key === 'production' ? '+' + effect + '% base speed' : key === 'sales' ? '+' + effect + '% walk-in demand' : '−' + effect + '% batch costs';
      return '<div class="wf-job' + (unlocked ? '' : ' is-locked') + '" data-wf-job="' + key + '"><div><h4>' + branch[1] + '</h4><span>' + (unlocked ? esc(effectText) : 'Develop ' + branch[1].toLowerCase() + ' focus') + '</span></div><div class="wf-stepper"><button id="game-wf-minus-' + key + '" type="button" data-wf-step="-1" data-wf-branch="' + key + '" aria-label="Remove one ' + branch[1].toLowerCase() + ' worker"' + (!value || snapshot.paused ? ' disabled' : '') + '>−</button><output aria-label="' + branch[1] + ' workers">' + value + '</output><button id="game-wf-plus-' + key + '" type="button" data-wf-step="1" data-wf-branch="' + key + '" aria-label="Assign one ' + branch[1].toLowerCase() + ' worker"' + (!unlocked || unassigned <= 0 || snapshot.paused ? ' disabled' : '') + '>+</button></div></div>';
    }).join('') + '<label class="wf-training-choice" for="game-wf-training-branch"><span>New workers join</span><select id="game-wf-training-branch"' + (snapshot.paused ? ' disabled' : '') + '>' + branches.map(function (branch) { return '<option value="' + branch[0] + '"' + (draft.trainingBranch === branch[0] ? ' selected' : '') + (!enabledBranch(team, branch[0]) ? ' disabled' : '') + '>' + branch[1] + '</option>'; }).join('') + '</select></label>' + button('save-allocation', dirty ? 'Save team assignments' : 'Assignments saved', action('allocate', { buildingId: team.buildingId, allocation: draft.allocation, trainingBranch: draft.trainingBranch }), !dirty || unassigned < 0 || snapshot.paused) + (dirty ? note('Unsaved changes · current assignments keep working until you save.', 'wf-unsaved') : note('New workers automatically take the job you selected. No extra hiring charges.')) + '</section></div><div class="wf-business-controls"><div class="game-business-control"><div><h3>' + (building.paused ? 'Business paused' : 'Business open') + '</h3>' + note('Pause production, training and operating costs.') + '</div>' + button('business-toggle', building.paused ? 'Resume' : 'Pause', 'business:' + (building.paused ? 'resume' : 'pause') + ':' + encodeURIComponent(building.buildingId), snapshot.paused, 'wf-button-light') + '</div><div class="game-salvage-entry"><div><h3>Close this business</h3>' + note('Salvage ' + helpers.ym(salvage.value) + ' · ' + helpers.duration(salvage.cooldownSeconds) + ' before rebuilding') + '</div><button id="game-wf-salvage-open" type="button" class="game-text-button" data-business-close="' + esc(building.buildingId) + '">Review →</button></div></div></section>';
    return html;
  }
  function headquarters(snapshot) {
    var workforce = snapshot.workforce, hq = workforce.hq || {}, targets = hq.targets || [], upgrade = hq.upgrade || {}, full = targets.length >= number(hq.programSlots), shared = !!population(snapshot);
    return '<section class="wf-headquarters">' + subnav('hq', [['academy','Academy · Lv ' + number(hq.level)],['programs','Training programs']], hqView) + '<div class="wf-hq-layout"><section class="wf-academy"><div class="wf-generator-chain" aria-label="' + (shared ? 'HQ develops its separate specialist team' : 'HQ develops trainers, trainers develop workers, workers improve businesses') + '"><span>HQ academy</span><i aria-hidden="true">↓</i><span>Business trainers</span><i aria-hidden="true">↓</i><span>' + (shared ? 'HQ specialists' : 'Trained crew') + '</span><i aria-hidden="true">↓</i><span>' + (shared ? 'Separate from workers' : 'Business capacity') + '</span></div><p class="wf-note">Each supported business develops one additional trainer every ' + esc(helpers.duration(hq.trainerSeconds || 600)) + ', up to its trainer limit. ' + (shared ? 'These specialists are separate from the worker population.' : 'More trainers develop your crew faster.') + '</p>' + button('hq-upgrade', number(hq.level) >= 3 ? 'HQ fully developed' : (hq.level ? 'Upgrade HQ' : 'Establish academy') + ' · ' + helpers.ym(upgrade.cost), action('hq_upgrade'), !upgrade.canBuy || snapshot.paused) + (!upgrade.canBuy ? note(upgrade.why) : '') + note(shared ? 'Each HQ level opens another simultaneous program. Ordinary workers arrive through business growth and have no gameplay role yet.' : 'Each HQ level opens another simultaneous program. Permanent hires add worker and trainer positions.') + '</section><section class="wf-programs" aria-label="HQ training programs"><div class="wf-allocation-heading"><h3>Training programs</h3><strong>' + targets.length + ' / ' + number(hq.programSlots) + ' active</strong></div>' + workforce.teams.map(function (team) {
      var active = targets.indexOf(team.typeId) !== -1, ready = active || !!hq.level && !full && number(team.hires) > 0;
      var status = active ? team.paused || snapshot.paused ? 'Training paused' : team.nextTrainerSeconds != null ? 'Next trainer in ' + timer(team.nextTrainerSeconds, false) : 'Trainer positions filled' : !hq.level ? 'Establish the HQ academy' : !team.hires ? 'Hire a trainer at this business first' : full ? 'All HQ programs assigned' : number(team.trainers) + ' / ' + number(team.trainerCap) + ' trainers';
      return '<article class="wf-program' + (active ? ' is-active' : '') + '"><div><h4>' + esc(team.name) + '</h4><p>' + status + '</p>' + (active ? meter(team.trainerProgress, team.name + ' trainer development') : '') + '</div><div class="wf-program-actions">' + (shared ? button('hq-hire-' + team.buildingId, 'Hire specialist · ' + helpers.ym(team.hire.cost), action('hire', { buildingId: team.buildingId }), !team.hire.canHire || snapshot.paused, 'wf-button-light') : '') + button('hq-program-' + team.buildingId, active ? 'Release' : 'Assign HQ', action('hq_assign', { buildingId: team.buildingId, enabled: !active }), !ready || snapshot.paused, 'wf-button-light') + '</div>' + '</article>';
    }).join('') + '</section></div></section>';
  }
  function render(snapshot, building, suppliedHelpers) {
    helpers = suppliedHelpers;
    var workforce = snapshot.workforce || {}, team = (workforce.teams || []).find(function (item) { return item.buildingId === building.buildingId; });
    current = team ? { team: team, snapshot: snapshot, building: building } : null;
    if (!team) return '<section class="game-panel"><div class="game-panel-body">' + note(population(snapshot) ? 'Open a business to welcome workers.' : 'Open a business to develop its permanent team.') + '</div></section>';
    var availableTabs = panelTabs(snapshot);
    if (!availableTabs.some(function (item) { return item[0] === tab; })) tab = 'focus';
    var nav = '<div class="wf-tabs" role="tablist" aria-label="Operations panels">' + availableTabs.map(function (item) { return '<button id="game-wf-tab-' + item[0] + '" type="button" role="tab" aria-selected="' + (tab === item[0]) + '" aria-controls="game-wf-panel" tabindex="' + (tab === item[0] ? '0' : '-1') + '" data-wf-tab="' + item[0] + '">' + item[1] + '</button>'; }).join('') + '</div>';
    var body = tab === 'focus' ? focusTree(team, snapshot) : tab === 'team' ? teamPanel(team, building, snapshot) : tab === 'hq' ? headquarters(snapshot) : tab === 'projects' ? helpers.projectsPanel(building, snapshot) : tab === 'recipes' ? '<div class="wf-recipes">' + helpers.recipePanel(building, snapshot) + helpers.focusMarkup(building) + '</div>' : helpers.questsPanel(building, snapshot) || note('Business quests become available as your businesses develop.');
    requestAnimationFrame(fit);
    return '<div class="wf-workspace'+(connected(snapshot)?' is-connected':'')+'">' + nav + (tab !== 'hq' ? summary(team, snapshot) : '') + '<div id="game-wf-panel" class="wf-scroll" role="tabpanel" aria-labelledby="game-wf-tab-' + tab + '" tabindex="0" data-keep-scroll="workforce-' + building.buildingId + '-' + tab + '">' + body + '</div></div>';
  }
  document.addEventListener('click', function (event) {
    if (!current || !helpers) return;
    var overview=event.target.closest('[data-workforce-open]');
    if(overview){
      var target=overview.dataset.workforceOpen;
      if(panelTabs(current.snapshot).some(function(item){return item[0]===target;})){
        event.preventDefault();tab=target;
        if(target==='team')teamView=overview.dataset.workforceView==='assignments'?'assignments':'recruitment';
        redraw('game-wf-tab-'+tab);
      }
      return;
    }
    var chosen = event.target.closest('[data-wf-tab]');
    if (chosen) { tab = chosen.dataset.wfTab; redraw('game-wf-tab-' + tab); return; }
    var view = event.target.closest('[data-wf-view]');
    if (view) { if (view.dataset.wfGroup === 'team') teamView = view.dataset.wfView; else hqView = view.dataset.wfView; redraw(view.id); return; }
    var paging = event.target.closest('[data-wf-page]');
    if (paging && !paging.disabled) { listPages[paging.dataset.wfPage] = (listPages[paging.dataset.wfPage] || 0) + Number(paging.dataset.wfDirection); var pageFocus = paging.id; fit(); var pageControl = document.getElementById(pageFocus); if (pageControl && !pageControl.disabled) pageControl.focus({preventScroll:true}); else { var previousPage = document.querySelector('.wf-pager button:not(:disabled)'); if (previousPage) previousPage.focus({preventScroll:true}); } return; }
    var focus = event.target.closest('[data-wf-focus]');
    if (focus) { selectedNode = focus.dataset.wfFocus; redraw(focus.id); return; }
    var discard = event.target.closest('[data-wf-discard]');
    if (discard) { delete drafts[current.team.buildingId]; redraw('game-wf-save-allocation'); return; }
    var step = event.target.closest('[data-wf-step]');
    if (!step || step.disabled || current.snapshot.paused) return;
    var team = current.team, draft = changeDraft(team), branch = step.dataset.wfBranch, amount = Number(step.dataset.wfStep);
    if (!branches.some(function (item) { return item[0] === branch; }) || !enabledBranch(team, branch)) return;
    if (amount > 0 && assigned(draft.allocation) >= team.workers) return;
    draft.allocation[branch] = Math.max(0, number(draft.allocation[branch]) + amount);
    redraw(step.id);
  });
  document.addEventListener('change', function (event) {
    if (!current || !helpers || event.target.id !== 'game-wf-training-branch' || current.snapshot.paused) return;
    if (!enabledBranch(current.team, event.target.value)) return;
    changeDraft(current.team).trainingBranch = event.target.value;
    redraw(event.target.id);
  });
  document.addEventListener('keydown', function (event) {
    var control = event.target.closest('.wf-tabs [role="tab"]');
    if (!control || !helpers) return;
    var availableTabs = panelTabs(current.snapshot), index = availableTabs.findIndex(function (item) { return item[0] === tab; }), next;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') next = (index + (event.key === 'ArrowRight' ? 1 : -1) + availableTabs.length) % availableTabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = availableTabs.length - 1;
    else return;
    event.preventDefault(); tab = availableTabs[next][0]; redraw('game-wf-tab-' + tab);
  });
  window.addEventListener('hashchange', function () {
    var selected = { '#team': 'team', '#workers': 'team', '#quests': 'quests', '#projects': 'projects', '#hq': 'hq', '#recipes': 'recipes', '#focus': 'focus' }[location.hash];
    if (selected && current && helpers) { tab = selected;if(location.hash==='#workers')teamView='assignments';redraw('game-wf-tab-' + tab); }
  });
  function fit() {
    var host = document.querySelector('.wf-workspace'), panel = host && host.querySelector('.wf-scroll');
    if (!panel) return;
    host.classList.toggle('wf-short', panel.clientHeight < (host.classList.contains('is-connected') ? 300 : 260));
    host.classList.toggle('wf-medium', panel.clientHeight < 400);
    var team = host.querySelector('.wf-team');
    if (team) {
      team.dataset.view = teamView;
      if (team.classList.contains('is-population')) {
        Array.from(team.querySelectorAll('[data-wf-population-view]')).forEach(function (node) { node.hidden = node.dataset.wfPopulationView !== teamView; });
      } else {
        team.querySelector('.wf-team-training').hidden = !['recruitment','training'].includes(teamView);
        Array.from(team.querySelector('.wf-team-training').children).forEach(function (node) {
          var training = node.classList.contains('wf-worker-training') || node.classList.contains('wf-academy-progress');
          node.hidden = training ? teamView !== 'training' : teamView !== 'recruitment';
        });
        team.querySelector('.wf-allocation').hidden = teamView !== 'assignments';
        team.querySelector('.wf-business-controls').hidden = teamView !== 'business';
      }
    }
    var headquarters = host.querySelector('.wf-headquarters');
    if (headquarters) {
      headquarters.querySelector('.wf-academy').hidden = hqView !== 'academy';
      headquarters.querySelector('.wf-programs').hidden = hqView !== 'programs';
      if (hqView === 'programs') paginate(headquarters.querySelector('.wf-programs'), '.wf-program', 'Programs', Math.max(1,Math.floor((panel.clientHeight - 100) / (population(current.snapshot) ? 120 : 86))));
    }
    var quests = host.querySelector('.game-quest-list');
    if (quests) paginate(quests, '.game-quest-card', 'Quests', panel.clientHeight < 260 || innerWidth < 650 ? 1 : 2);
    var recipes = host.querySelector('.game-recipe');
    if (recipes) paginate(recipes, '.game-recipe-chain', 'Recipes', panel.clientHeight < 260 ? 1 : innerWidth < 650 ? 2 : 4);
  }
  function paginate(parent, selector, key, per) {
    var items = Array.from(parent.querySelectorAll(':scope > ' + selector));
    var existing = parent.querySelector(':scope > .wf-pager');
    if (existing) existing.remove();
    var count = Math.ceil(items.length / per), page = Math.max(0, Math.min(listPages[key] || 0, count - 1));
    listPages[key] = page;
    items.forEach(function (item,index) { item.hidden = index < page * per || index >= (page + 1) * per; });
    if (count <= 1) return;
    var nav = document.createElement('div'); nav.className = 'wf-pager'; nav.setAttribute('aria-label', key + ' pages');
    nav.innerHTML = '<button id="game-wf-page-' + key.toLowerCase() + '-prev" type="button" data-wf-page="' + key + '" data-wf-direction="-1" aria-label="Previous ' + key.toLowerCase() + ' page"' + (page === 0 ? ' disabled' : '') + '>←</button><span>' + (page + 1) + ' / ' + count + '</span><button id="game-wf-page-' + key.toLowerCase() + '-next" type="button" data-wf-page="' + key + '" data-wf-direction="1" aria-label="Next ' + key.toLowerCase() + ' page"' + (page === count - 1 ? ' disabled' : '') + '>→</button>';
    parent.appendChild(nav);
  }
  window.addEventListener('resize', function () { requestAnimationFrame(fit); });
  window.addEventListener('yomama:econ', fit);
  window.YomamaWorkforce = { render: render, fit: fit };
})();
