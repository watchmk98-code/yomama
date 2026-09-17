/* Focus Tree controls render server state; no focus or reward is saved in
   the browser. The saved seat, shared class clock, and API own progression. */
(function () {
  'use strict';
  var root = document.getElementById('food-focus');
  if (!root || !window.FoodEmpireArt) return;
  var NS = 'http://www.w3.org/2000/svg';
  var definitions = [], edges = [];
  var statusNames = {loading:'Loading', available:'Ready', locked:'Locked', completed:'Complete', active:'In progress', excluded:'Path locked'};
  var state = null, selected = null, selectedArt = null, connected = false, busy = false;
  var pending = null, version = 0, receivedAt = 0, frame = 0, expiryRefreshAt = 0;
  var nodes = {}, paths = [], session = {};
  try {session = JSON.parse(localStorage.getItem('yomama_session_v1') || '{}') || {};} catch (_) {}

  function el(id) {return document.getElementById(id);}
  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function icon(status) {
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'focus-state-icon');
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('fill', 'none'); path.setAttribute('stroke', 'currentColor'); path.setAttribute('stroke-width', '3');
    path.setAttribute('d', status === 'completed' ? 'M3 12L9 18L21 5' :
      status === 'active' ? 'M12 3V12L18 15M12 2A10 10 0 1 0 12 22A10 10 0 1 0 12 2' :
      status === 'excluded' ? 'M5 5L19 19M19 5L5 19' : 'M7 10V7A5 5 0 0 1 17 7V10M5 10H19V21H5ZM12 14V18');
    svg.appendChild(path); return svg;
  }
  function notice(text, tone) {
    el('focus-notice').textContent = text || '';
    el('focus-notice').dataset.tone = tone || '';
  }
  function row(id) {return state && state.focusTree && state.focusTree.nodes.find(function (n) {return n.id === id;});}
  function artwork(focus, detail) {
    var art = focus.art || focus.id;
    if (FoodEmpireArt.crops[art]) return FoodEmpireArt.createSvg(detail && art === 'local_brand' ? 'local_brand-detail' : art);
    var img = element('span', 'focus-building-sprite');
    img.style.backgroundImage = 'url("./assets/buildings/spritesheets/'+art+'_8f.png")';
    if (detail) {img.setAttribute('role', 'img'); img.setAttribute('aria-label', focus.title+' pixel artwork');}
    else img.setAttribute('aria-hidden', 'true');
    return img;
  }
  function buildNodes(tree) {
    definitions = tree.nodes;
    definitions.forEach(function (focus) {
      focus.requires.concat(focus.requiresAny).forEach(function (id) {edges.push([id, focus.id, focus.requiresAny.indexOf(id) >= 0]);});
    });
    definitions.forEach(function (d) {
      var button = element('button', 'focus-node');
      button.type = 'button'; button.dataset.focusId = d.id; button.dataset.status = 'loading';
      button.style.gridColumn = d.column; button.style.gridRow = d.row;
      button.setAttribute('aria-pressed', 'false'); button.setAttribute('aria-controls', 'focus-detail');
      var art = element('span', 'focus-node-art'); art.appendChild(artwork(d));
      var copy = element('span', 'focus-node-copy');
      copy.appendChild(element('span', 'focus-node-title', d.title));
      copy.appendChild(element('span', 'focus-node-reward', d.rewardText));
      copy.appendChild(element('span', 'focus-node-status', 'Loading'));
      button.append(art, copy); el('food-focus-nodes').appendChild(button); nodes[d.id] = button;
    });
    edges.forEach(function (edge) {
      var path = document.createElementNS(NS, 'path'); path.setAttribute('class', 'focus-connection');
      path.dataset.from = edge[0]; path.dataset.to = edge[1]; path.dataset.either = String(edge[2]);
      el('food-focus-connections').appendChild(path); paths.push(path);
    });
  }
  function scheduleLines() {
    if (frame) return;
    frame = requestAnimationFrame(function () {frame = 0; drawLines();});
  }
  function drawLines() {
    if (!definitions.length) return;
    var map = el('food-focus-map'), base = map.getBoundingClientRect();
    var boxes = {};
    var gridStyle = getComputedStyle(el('food-focus-nodes'));
    var rowGap = parseFloat(gridStyle.rowGap) || 24, columnGap = parseFloat(gridStyle.columnGap) || 28;
    Object.keys(nodes).forEach(function (id) {
      var r = nodes[id].getBoundingClientRect();
      boxes[id] = {left:r.left-base.left, right:r.right-base.left, top:r.top-base.top, bottom:r.bottom-base.top, x:r.left-base.left+r.width/2, y:r.top-base.top+r.height/2};
    });
    el('food-focus-connections').setAttribute('viewBox', '0 0 '+base.width+' '+base.height);
    paths.forEach(function (path) {
      var from = boxes[path.dataset.from], to = boxes[path.dataset.to], d;
      // Cross-sector links travel through gutters, not through other cards.
      var sourceDef = definitions.find(function (n) {return n.id === path.dataset.from;});
      var targetDef = definitions.find(function (n) {return n.id === path.dataset.to;});
      var targetTop = to.top - rowGap * (.35 + (sourceDef.column % 3) * .12);
      if (sourceDef.column === targetDef.column && targetDef.row === sourceDef.row + 1) {
        d = 'M'+from.x+' '+from.bottom+'V'+to.top;
      } else {
        var right = targetDef.column >= sourceDef.column;
        var gutter = right ? from.right + columnGap * .4 : from.left - columnGap * .4;
        d = 'M'+(right ? from.right : from.left)+' '+from.y+'H'+gutter+'V'+targetTop+'H'+to.x+'V'+to.top;
      }
      path.setAttribute('d', d);
      var source = row(path.dataset.from), target = row(path.dataset.to);
      path.setAttribute('class', 'focus-connection'+(source && source.status === 'completed'?' is-complete':'')+(target && target.status === 'excluded' || source && source.status === 'excluded'?' is-excluded':''));
    });
  }
  function renderNodes() {
    if (!state || !state.focusTree) return;
    state.focusTree.nodes.forEach(function (focus) {
      var button = nodes[focus.id]; if (!button) return;
      button.dataset.status = focus.status;
      button.setAttribute('aria-pressed', String(focus.id === selected));
      button.setAttribute('aria-label', focus.title+'. '+statusNames[focus.status]+'. '+focus.rewardText);
      var status = button.querySelector('.focus-node-status'); status.replaceChildren();
      if (['completed','locked','excluded','active'].indexOf(focus.status) >= 0) status.appendChild(icon(focus.status));
      status.appendChild(document.createTextNode(statusNames[focus.status] || focus.status));
    });
    scheduleLines();
  }
  function duration(seconds) {
    seconds = Math.max(0, Math.ceil(seconds));
    if (seconds >= 3600) return Math.floor(seconds/3600)+'h '+Math.floor(seconds%3600/60)+'m';
    if (seconds >= 60) return Math.floor(seconds/60)+'m '+seconds%60+'s';
    return seconds+'s';
  }
  function renderDetail() {
    var focus = row(selected); if (!focus) return;
    var tree = state.focusTree;
    el('focus-detail').setAttribute('aria-busy', String(busy));
    el('focus-detail-title').textContent = focus.title;
    el('focus-detail-status').textContent = statusNames[focus.status].toUpperCase();
    el('focus-detail-status').dataset.status = focus.status;
    el('focus-detail-branch').textContent = focus.sector;
    if (selectedArt !== focus.id) {
      el('focus-detail-art').replaceChildren(artwork(focus, true));
      selectedArt = focus.id;
    }
    var requirements = el('focus-requirements'); requirements.replaceChildren();
    (focus.requirements || []).forEach(function (requirement) {
      var li = element('li', requirement.met ? 'is-met' : '');
      li.appendChild(icon(requirement.met ? 'completed' : 'locked'));
      li.appendChild(element('span', '', requirement.text)); requirements.appendChild(li);
    });
    el('focus-reward').textContent = focus.rewardText;
    el('focus-duration').textContent = duration(focus.durationSeconds)+' · class time';
    el('focus-choice-warning').textContent = focus.description + (focus.requiresAny.length ? ' Either linked regional route qualifies.' : focus.requires.length > 1 ? ' All linked focuses are required.' : '');
    el('focus-start-reason').textContent = !connected ? 'Reconnecting to your class…' : state.paused ? 'Your teacher has paused the class.' : busy ? '' : focus.why || '';
    var button = el('focus-start');
    button.disabled = busy || !connected || !!state.paused || !focus.canStart;
    button.textContent = busy ? 'STARTING…' : focus.status === 'active' ? (state.paused?'CLASS PAUSED':'FOCUS IN PROGRESS') :
      focus.status === 'completed' ? 'FOCUS COMPLETE' : focus.status === 'excluded' ? 'PATH LOCKED' : !connected ? 'RECONNECTING…' :
      state.paused ? 'CLASS PAUSED' : focus.canStart ? 'START FOCUS' : 'REQUIREMENTS NOT MET';
    el('focus-active-progress').hidden = !(tree.active && tree.active.id === focus.id);
    renderTimer();
  }
  function renderTimer() {
    if (!state || !state.focusTree.active) return;
    var active = state.focusTree.active;
    var elapsed = connected && !state.paused ? Math.max(0,(Date.now()-receivedAt)/1000) : 0;
    var remaining = Math.max(0,active.remainingSeconds-elapsed);
    var focus = row(active.id), total = focus ? focus.durationSeconds : 1;
    var percent = Math.min(100,Math.max(0,100*(1-remaining/Math.max(1,total))));
    el('focus-progress-label').textContent = !connected ? 'RECONNECTING' : state.paused ? 'CLASS PAUSED' : 'IN PROGRESS';
    el('focus-time-left').textContent = remaining > 0 ? duration(remaining)+' left' : 'Syncing completion…';
    el('focus-progress-fill').style.width = percent+'%';
    el('focus-progress-track').setAttribute('aria-valuenow', String(Math.round(percent)));
    // Only a server reply completes the node. Avoid a request each second
    // while a class is paused or the server is still replaying its next tick.
    if (remaining === 0 && connected && !state.paused && Date.now()-expiryRefreshAt > 5000) {expiryRefreshAt=Date.now();refresh();}
  }
  function apply(payload) {
    if (!payload || !payload.focusTree || !payload.focusTree.enabled) {
      connected = false; notice('The focus tree is not available for this class yet.','error'); return;
    }
    var previous = state && state.focusTree;
    state = payload; connected = true; receivedAt = Date.now();
    if (!definitions.length) buildNodes(payload.focusTree);
    if (!selected || !row(selected)) {
      var requested = new URLSearchParams(location.search).get('focus');
      selected = row(requested) ? requested : payload.focusTree.active ? payload.focusTree.active.id :
        row('local_brand').canStart ? 'local_brand' : (payload.focusTree.nodes.find(function (n) {return n.canStart;}) || payload.focusTree.nodes[0]).id;
    }
    if (state.paused) notice('Class paused. Focus timers will continue when your teacher resumes the class.');
    else if (previous && state.focusTree.completedCount > previous.completedCount) notice('Focus complete. Your reward is now active.');
    else notice('');
    renderNodes(); renderDetail();
    el('focus-summary').textContent = state.focusTree.completedCount+' / '+state.focusTree.totalNodes+' COMPLETE · ONE FOCUS AT A TIME';
    window.dispatchEvent(new CustomEvent('yomama:econ', {detail:payload}));
  }
  function request(path, body) {
    var controller = new AbortController();
    var timeout = setTimeout(function () {controller.abort();}, 20000);
    var options = {method:body?'POST':'GET',cache:'no-store',signal:controller.signal};
    if (body) {options.headers={'Content-Type':'application/json'}; options.body=JSON.stringify(Object.assign({},body,{token:session.token || ''}));}
    return fetch(path,options).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || payload.ok === false) {var err = new Error(payload.why || payload.error || 'Unable to reach your class.'); err.status=response.status; throw err;}
        return payload;
      });
    }).finally(function () {clearTimeout(timeout);});
  }
  function failed(error) {
    connected = false;
    notice(error.status === 401 ? 'Your session has expired. Sign in again to continue.' : 'Connection interrupted. Reconnecting to your class…', 'error');
    renderDetail();
  }
  function refresh() {
    if (busy || document.hidden) return Promise.resolve();
    if (pending) return pending;
    var current = version;
    pending = request('/api/game/econ/state?token='+encodeURIComponent(session.token || '')).then(function (payload) {
      if (current === version) apply(payload);
    }).catch(function (error) {if (current === version) failed(error);}).finally(function () {pending=null;});
    return pending;
  }
  function start() {
    var focus = row(selected);
    if (busy || !connected || !focus || !focus.canStart || state.paused) return;
    busy = true; version++; notice(''); renderDetail();
    request('/api/game/focus-tree',{action:'start',focusId:focus.id}).then(function (payload) {
      apply(payload);
      notice(focus.title+' started. Progress follows your class clock.');
    }).catch(function (error) {
      notice(error.name === 'AbortError' ? 'The server has not confirmed yet. Reconnecting to check your focus…' : error.message, 'error');
      if (!error.status) connected=false;
    }).finally(function () {busy=false;renderDetail();refresh();});
  }
  root.addEventListener('click',function (event) {
    var button = event.target.closest('[data-focus-id]');
    if (!button) return;
    selected=button.dataset.focusId;renderNodes();renderDetail();
    if (matchMedia('(max-width:850px)').matches) el('focus-detail').scrollIntoView({block:'start',behavior:'auto'});
  });
  el('focus-start').addEventListener('click',start);
  window.addEventListener('resize',scheduleLines);
  new ResizeObserver(scheduleLines).observe(el('food-focus-map'));
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleLines);
  document.addEventListener('visibilitychange',function () {if (!document.hidden) refresh();});
  window.addEventListener('online',refresh);
  window.addEventListener('pageshow',refresh);
  setInterval(refresh,10000); setInterval(renderTimer,1000);
  scheduleLines();
  // Mirrors entering the other game pages and their offline/login bookkeeping.
  pending=request('/api/game/econ/login',{}).then(apply).catch(failed).finally(function () {pending=null;});
}());
