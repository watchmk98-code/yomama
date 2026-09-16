/* loading.js - the LOADING screen between signing in and the first build page.

   The game's art is heavy: a building spritesheet is a megabyte or two, the
   craft sheets are two each, a customer's emote strip is another one and a
   half. Dropped straight onto the build page a student watches the tiles pop
   in one at a time for several seconds. This holds a black screen with one
   bar in front of that, and lets go when the art is actually in the browser.

   What it waits for, in order:
     1. preload-manifest.js `core` - a few kilobytes of shared art that is not
        in the markup: the HUD icons, the order reactions, the stat chips.
     2. the page's own first render - econ.js fetches the player's snapshot
        and draws it, then fires `yomama:econ`. Only then is it known which
        building, goods and customers this player has, so their art is read
        straight off the page and waited for too.
     3. the webfont, so the numbers do not reflow a moment later.
   Then it fades, and the `warm` list - the banner, the badges, the category
   squares, the building and craft sheets - is fetched quietly in the
   background, one file at a time, so the next page and the next tab open with
   the art already in the cache.

   What it deliberately does not do is hold the class behind a fixed download.
   The blocking part is this page's own art, which the browser is fetching
   anyway; the screen hides the pop-in rather than adding to the wait.

   It shows once per tab: join.html sets the boot flag on a successful sign-in,
   and the first game page after that spends it. Moving between pages later
   does not show it again - by then the art is in the HTTP cache anyway.

   Nothing here may trap a class. Every wait has a ceiling (MAX_MS), a file
   that 404s counts as done, and a browser that refuses sessionStorage skips
   the screen entirely.

   Load both first in <head>, before the stylesheets, manifest first - this
   reads window.YomamaPreloadManifest the moment it runs:
     <script src="./preload-manifest.js?v=1"></script>
     <script src="./loading.js?v=1"></script>                       */
(function () {
  'use strict';

  var SESSION_KEY = 'yomama_session_v1';
  var BOOT_KEY = 'yomama_boot_v1';        // join.html sets this on a fresh sign-in
  var SEEN_KEY = 'yomama_loaded_v1';      // one screen per tab, not one per page
  var MAX_MS = 15000;                     // hard ceiling on the whole screen
  var RENDER_WAIT_MS = 9000;              // ceiling on waiting for yomama:econ
  var WARM_DELAY_MS = 1500;               // let the page settle before warming
  var PARALLEL = 6;                       // what a browser opens per host anyway
  var UNKNOWN_BYTES = 120 * 1024;         // weight for a file of unknown size

  // Segments of the bar. The shared set in the manifest is a few kilobytes, so
  // it takes a sliver; the page's own art is what a student is really waiting
  // for and gets the rest.
  var CORE_END = 8, DOM_END = 96;
  var CREEP_CEILING = 0.25;               // how far the bar may run ahead of the snapshot

  function store(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }
  function flag(key) {
    var s = store('sessionStorage');
    try { return s ? s.getItem(key) : null; } catch (e) { return null; }
  }
  function setFlag(key, value) {
    var s = store('sessionStorage');
    try { if (s) { if (value === null) s.removeItem(key); else s.setItem(key, value); } } catch (e) {}
  }
  function signedIn() {
    try {
      var raw = window.localStorage.getItem(SESSION_KEY);
      return !!(raw && JSON.parse(raw).token);
    } catch (e) { return false; }
  }

  function wanted() {
    if (/[?&]noboot=1\b/.test(window.location.search)) return false;
    if (!store('sessionStorage')) return false;   // cannot spend the flag, so never show it
    if (!signedIn()) return false;                // account.js is about to send them to join.html
    if (flag(BOOT_KEY)) return true;              // just signed in
    return !flag(SEEN_KEY);                       // first game page of this tab
  }

  if (!wanted()) { window.YomamaLoading = { shown: false }; return; }
  setFlag(BOOT_KEY, null);

  // ------------------------------------------------------------- the screen --
  // Injected rather than put in a stylesheet: this has to be painting before
  // styles.css has even been fetched, or the page flashes through first.
  var root = document.documentElement;
  root.className += (root.className ? ' ' : '') + 'yomama-booting';
  var style = document.createElement('style');
  style.textContent = [
    'html.yomama-booting{background:#000;overflow:hidden}',
    'html.yomama-booting body{background:#000}',
    'html.yomama-booting body>*:not(#yomama-loading){visibility:hidden}',
    '#yomama-loading{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;',
    'align-items:center;justify-content:center;gap:26px;background:#000;color:#ffb000;',
    'font-family:"VT323 Local","VT323","Lucida Console","Courier New",monospace;',
    'opacity:1;transition:opacity .4s ease}',
    '#yomama-loading[data-done="1"]{opacity:0;pointer-events:none}',
    '#yomama-loading .yl-title{font-size:clamp(40px,9vw,78px);letter-spacing:.16em;line-height:1;',
    'text-shadow:0 0 18px rgba(255,176,0,.35);animation:yl-pulse 1.6s ease-in-out infinite}',
    '#yomama-loading .yl-track{width:min(520px,74vw);height:20px;padding:3px;background:#000;border:1px solid #7a4d00}',
    '#yomama-loading .yl-fill{height:100%;width:0;background:#ffb000;transition:width .3s linear}',
    '#yomama-loading .yl-pct{font-size:21px;letter-spacing:.22em;color:#a3a3a3}',
    '@keyframes yl-pulse{0%,100%{opacity:1}50%{opacity:.62}}',
    '@media (prefers-reduced-motion:reduce){#yomama-loading .yl-title{animation:none}',
    '#yomama-loading,#yomama-loading .yl-fill{transition:none}}'
  ].join('');
  (document.head || root).appendChild(style);

  var screenEl = document.createElement('div');
  screenEl.id = 'yomama-loading';
  screenEl.setAttribute('role', 'status');
  screenEl.setAttribute('aria-live', 'polite');
  screenEl.innerHTML =
    '<div class="yl-title">LOADING...</div>' +
    '<div class="yl-track"><div class="yl-fill"></div></div>' +
    '<div class="yl-pct">0%</div>';
  var fillEl = screenEl.querySelector('.yl-fill');
  var pctEl = screenEl.querySelector('.yl-pct');

  (function mount() {
    if (document.body) document.body.appendChild(screenEl);
    else requestAnimationFrame(mount);
  }());

  var shown = 0;                       // the bar only ever goes forwards
  function show(pct) {
    pct = Math.max(0, Math.min(100, pct));
    if (pct <= shown) return;
    shown = pct;
    fillEl.style.width = pct.toFixed(1) + '%';
    pctEl.textContent = Math.round(pct) + '%';
  }

  var finished = false;
  function finish() {
    if (finished) return;
    finished = true;
    clearTimeout(capTimer);
    show(100);
    setFlag(SEEN_KEY, '1');
    setTimeout(function () {
      screenEl.setAttribute('data-done', '1');
      root.className = root.className.replace(/\byomama-booting\b/g, '').trim();
      setTimeout(function () {
        if (screenEl.parentNode) screenEl.parentNode.removeChild(screenEl);
      }, 500);
      setTimeout(warm, WARM_DELAY_MS);
    }, 160);                          // let the bar be seen full before it goes
  }
  var capTimer = setTimeout(finish, MAX_MS);

  // -------------------------------------------------------------- fetching --
  /* Images go through Image(), not fetch(): an <img> the page creates a moment
     later reads the same cache entry, and a decoded bitmap is kept as well.
     Anything that fails - a 404, a file pulled from the pack - resolves, so one
     missing sprite cannot hold the screen. */
  function grab(url) {
    return new Promise(function (done) {
      var img = new Image();
      img.decoding = 'async';
      img.onload = img.onerror = function () { done(); };
      img.src = url;
      if (img.complete) done();
    });
  }

  /* Runs `list` ([url, bytes] pairs) a few at a time and reports how far along
     it is by bytes arrived, so one 2 MB sheet does not tick like a 4 KB icon. */
  function loadList(list, onProgress) {
    var total = 0, done = 0, next = 0;
    list.forEach(function (item) { total += item[1] || UNKNOWN_BYTES; });
    if (!list.length) { onProgress(1); return Promise.resolve(); }
    function one() {
      if (next >= list.length) return Promise.resolve();
      var item = list[next++];
      return grab(item[0]).then(function () {
        done += item[1] || UNKNOWN_BYTES;
        onProgress(Math.min(1, done / total));
        return one();
      });
    }
    var lanes = [];
    for (var i = 0; i < Math.min(PARALLEL, list.length); i++) lanes.push(one());
    return Promise.all(lanes);
  }

  // ------------------------------------------------- 1. the shared art set --
  var manifest = window.YomamaPreloadManifest || { core: [], warm: [] };
  var corePart = 0, domPart = 0;
  function paint() { show(corePart * CORE_END + domPart * (DOM_END - CORE_END)); }

  var coreDone = loadList(manifest.core || [], function (p) { corePart = p; paint(); });

  // ------------------------------------------------ 2. this player's own art --
  /* econ.js draws the snapshot, then fires yomama:econ. Whatever art the page
     asked for is in the DOM by then - this building's spritesheet, these goods,
     these customers - so read it off the page instead of guessing it here. */
  function pageArt() {
    var urls = [], seen = {};
    function add(value) {
      if (!value) return;
      var url = String(value).trim();
      if (!url || url.slice(0, 5) === 'data:' || url.slice(0, 5) === 'blob:') return;
      try { if (new URL(url, location.href).origin !== location.origin) return; } catch (e) { return; }
      if (seen[url]) return;
      seen[url] = 1;
      urls.push([url, 0]);
    }
    var i, nodes;
    nodes = document.images;
    for (i = 0; i < nodes.length; i++) add(nodes[i].getAttribute('src'));
    // econ.js parks the still and the un-animated fallback on the tag itself;
    // one of them is what a student sees the moment the sheet fails or ends.
    nodes = document.querySelectorAll('[data-art-base],[data-art-fallback],[data-craft-sheet]');
    for (i = 0; i < nodes.length; i++) {
      add(nodes[i].getAttribute('data-art-base'));
      add(nodes[i].getAttribute('data-art-fallback'));
    }
    // Customer frames and craft stock icons come in as inline background urls.
    nodes = document.querySelectorAll('[style*="url("]');
    for (i = 0; i < nodes.length; i++) {
      var found = nodes[i].getAttribute('style').match(/url\(\s*["']?([^"')]+)/g) || [];
      found.forEach(function (chunk) { add(chunk.replace(/^url\(\s*["']?/, '')); });
    }
    return urls;
  }

  function firstRender() {
    return new Promise(function (done) {
      var settled = false;
      function go() {
        if (settled) return;
        settled = true;
        window.removeEventListener('yomama:econ', go);
        // one frame, so the markup econ.js just wrote is in the document
        requestAnimationFrame(function () { requestAnimationFrame(done); });
      }
      window.addEventListener('yomama:econ', go);
      // A page without econ.js, or a snapshot that never arrives, still moves on.
      if (document.readyState === 'complete') setTimeout(go, 1200);
      else window.addEventListener('load', function () { setTimeout(go, 1200); });
      setTimeout(go, RENDER_WAIT_MS);
    });
  }

  // The snapshot is a network round trip. Creep the bar across the part of the
  // page-art segment that is genuinely still pending, so it reads as working
  // rather than stuck - it never runs past what has actually arrived.
  var creep = setInterval(function () {
    if (domPart < CREEP_CEILING) { domPart += 0.012; paint(); }
  }, 260);

  var domDone = firstRender().then(function () {
    clearInterval(creep);
    var art = pageArt();
    var floor = domPart;
    return loadList(art, function (p) { domPart = floor + (1 - floor) * p; paint(); });
  });

  // --------------------------------------------------------- 3. and finish --
  var fonts = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
  Promise.all([coreDone, domDone]).then(function () {
    clearInterval(creep);
    show(DOM_END);
    return Promise.race([fonts, new Promise(function (r) { setTimeout(r, 1500); })]);
  }).then(finish, finish);

  // ------------------------------------------------------------- warm-up --
  /* The heavy sheets the *next* pages need. One at a time and only once the
     screen is gone, so this never competes with anything a student is waiting
     on - by the time they press CRAFT the sheets are already in the cache. */
  function warm() {
    var link = navigator.connection || {};
    // Data saver on, or a phone on a bad signal: what is on screen is enough.
    if (link.saveData || /(^|-)2g$/.test(link.effectiveType || '')) return;
    var list = (manifest.warm || []).slice();
    var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 200); };
    (function next() {
      if (!list.length) return;
      // Nothing to warm for a tab nobody is looking at; pick it up on return.
      if (document.hidden) {
        document.addEventListener('visibilitychange', function again() {
          document.removeEventListener('visibilitychange', again);
          next();
        });
        return;
      }
      idle(function () { grab(list.shift()[0]).then(next); });
    }());
  }

  window.YomamaLoading = { shown: true, finish: finish, warm: warm };
}());
