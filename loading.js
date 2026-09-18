/* Download the complete public game asset pack before the first page opens.
   The bar counts bytes received from the response bodies, including bytes
   supplied by the browser's HTTP cache on a repeat visit. A failed download
   stays visible with Retry and Enter game options; it never claims 100%. */
(function () {
  'use strict';

  var SESSION_KEY = 'yomama_session_v1';
  var BOOT_KEY = 'yomama_boot_v1';
  var READY_KEY = 'yomama_assets_ready_v1';
  var PARALLEL = 4;
  var FILE_TIMEOUT_MS = 90000;
  var manifest = window.YomamaPreloadManifest || { all: [], version: '' };
  var files = manifest.all || [];
  var version = String(manifest.version || '');

  function storage(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }
  function getFlag(key) {
    var store = storage('sessionStorage');
    try { return store ? store.getItem(key) : null; } catch (e) { return null; }
  }
  function setFlag(key, value) {
    var store = storage('sessionStorage');
    try {
      if (store) {
        if (value === null) store.removeItem(key);
        else store.setItem(key, value);
      }
    } catch (e) {}
  }
  function signedIn() {
    try {
      var raw = window.localStorage.getItem(SESSION_KEY);
      return !!(raw && JSON.parse(raw).token);
    } catch (e) { return false; }
  }

  var showScreen = !/[?&]noboot=1\b/.test(location.search) &&
    !!storage('sessionStorage') && signedIn() &&
    !(version && getFlag(READY_KEY) === version);
  setFlag(BOOT_KEY, null);
  if (!showScreen) {
    window.YomamaLoading = { shown: false };
    return;
  }

  // Install before page styles arrive, so the game never flashes through.
  var root = document.documentElement;
  root.className += (root.className ? ' ' : '') + 'yomama-booting';
  var style = document.createElement('style');
  style.textContent = [
    'html.yomama-booting{background:#000;overflow:hidden}',
    'html.yomama-booting body{background:#000}',
    'html.yomama-booting body>*:not(#yomama-loading){visibility:hidden}',
    '#yomama-loading{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;',
    'align-items:center;justify-content:center;gap:18px;padding:24px;box-sizing:border-box;',
    'background:#000;color:#ffb000;font-family:"VT323 Local","VT323","Lucida Console","Courier New",monospace;',
    'opacity:1;transition:opacity .4s ease;text-align:center}',
    '#yomama-loading[data-done="1"]{opacity:0;pointer-events:none}',
    '#yomama-loading .yl-title{font-size:clamp(40px,9vw,78px);letter-spacing:.16em;line-height:1}',
    '#yomama-loading .yl-track{width:min(520px,74vw);height:20px;padding:3px;background:#000;border:1px solid #7a4d00}',
    '#yomama-loading .yl-fill{height:100%;width:0;background:#ffb000;transition:width .2s linear}',
    '#yomama-loading .yl-mb{font-size:clamp(22px,5vw,31px);letter-spacing:.08em;color:#fff}',
    '#yomama-loading .yl-pct{font-size:20px;color:#a3a3a3}',
    '#yomama-loading .yl-status{font-size:19px;color:#a3a3a3;max-width:540px}',
    '#yomama-loading .yl-actions{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}',
    '#yomama-loading button{font:inherit;font-size:19px;color:#ffcf55;background:#101010;',
    'border:1px solid #5c5039;padding:7px 12px;cursor:pointer}',
    '#yomama-loading button:hover{border-color:#ffcf55}',
    '@media (prefers-reduced-motion:reduce){#yomama-loading,#yomama-loading .yl-fill{transition:none}}'
  ].join('');
  (document.head || root).appendChild(style);

  var screen = document.createElement('div');
  screen.id = 'yomama-loading';
  screen.setAttribute('role', 'status');
  screen.setAttribute('aria-live', 'polite');
  screen.innerHTML =
    '<div class="yl-title">LOADING...</div>' +
    '<div class="yl-track"><div class="yl-fill"></div></div>' +
    '<div class="yl-mb">0.0 / 0.0 MB downloaded</div>' +
    '<div class="yl-pct">0%</div>' +
    '<div class="yl-status">Preparing the full game art pack</div>' +
    '<div class="yl-actions"><button class="yl-retry" type="button" hidden>Retry failed downloads</button>' +
    '<button class="yl-skip" type="button" hidden>Enter game without full download</button></div>';
  var fill = screen.querySelector('.yl-fill');
  var amount = screen.querySelector('.yl-mb');
  var percent = screen.querySelector('.yl-pct');
  var status = screen.querySelector('.yl-status');
  var retry = screen.querySelector('.yl-retry');
  var skip = screen.querySelector('.yl-skip');
  (function mount() {
    if (document.body) document.body.appendChild(screen);
    else requestAnimationFrame(mount);
  }());

  var expected = files.reduce(function (sum, item) { return sum + item[1]; }, 0);
  var received = 0;
  var counted = files.map(function () { return 0; });
  var stopped = false;
  var finished = false;
  var controllers = [];
  var failed = [];

  function mb(bytes) { return (bytes / 1000000).toFixed(1); }
  function paint() {
    var ratio = expected ? Math.min(99, Math.floor(received * 100 / expected)) : 0;
    fill.style.width = ratio + '%';
    amount.textContent = mb(received) + ' / ' + mb(expected) + ' MB downloaded';
    percent.textContent = ratio + '%';
  }
  function count(index, bytes) {
    received += bytes - counted[index];
    counted[index] = bytes;
    paint();
  }
  paint();

  function finish(complete) {
    if (finished) return;
    finished = true;
    stopped = true;
    if (complete) {
      setFlag(READY_KEY, version);
      fill.style.width = '100%';
      percent.textContent = '100%';
      amount.textContent = mb(received) + ' / ' + mb(expected) + ' MB downloaded';
    }
    controllers.forEach(function (controller) { controller.abort(); });
    setTimeout(function () {
      screen.setAttribute('data-done', '1');
      root.className = root.className.replace(/\byomama-booting\b/g, '').trim();
      setTimeout(function () {
        if (screen.parentNode) screen.parentNode.removeChild(screen);
      }, 500);
    }, complete ? 220 : 0);
  }
  skip.addEventListener('click', function () { finish(false); });
  // A weak classroom connection still needs an escape hatch, but the normal
  // path is the complete pack rather than a tempting immediate skip.
  setTimeout(function () { if (!finished) skip.hidden = false; }, 30000);

  function loadOne(index) {
    var url = files[index][0];
    function attempt(tries) {
      if (stopped) return Promise.resolve(false);
      count(index, 0);
      var controller = new AbortController();
      controllers.push(controller);
      var timer = setTimeout(function () { controller.abort(); }, FILE_TIMEOUT_MS);
      return fetch(url, { signal: controller.signal, cache: 'default' }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        if (!response.body || !response.body.getReader) {
          return response.arrayBuffer().then(function (body) { count(index, body.byteLength); });
        }
        var reader = response.body.getReader();
        var bytes = 0;
        function read() {
          return reader.read().then(function (part) {
            if (part.done) return;
            bytes += part.value.byteLength;
            count(index, bytes);
            return read();
          });
        }
        return read();
      }).then(function () {
        clearTimeout(timer);
        controllers.splice(controllers.indexOf(controller), 1);
        return true;
      }, function () {
        clearTimeout(timer);
        controllers.splice(controllers.indexOf(controller), 1);
        if (stopped) return false;
        if (tries < 2) return attempt(tries + 1);
        count(index, 0);
        return false;
      });
    }
    return attempt(0);
  }

  function download(indices) {
    var next = 0;
    var errors = [];
    function worker() {
      if (stopped || next >= indices.length) return Promise.resolve();
      var index = indices[next++];
      return loadOne(index).then(function (ok) {
        if (!ok && !stopped) errors.push(index);
        return worker();
      });
    }
    var lanes = [];
    for (var i = 0; i < Math.min(PARALLEL, indices.length); i++) lanes.push(worker());
    return Promise.all(lanes).then(function () { return errors; });
  }

  function firstRender() {
    return new Promise(function (done) {
      var settled = false;
      function go() {
        if (settled) return;
        settled = true;
        window.removeEventListener('yomama:econ', go);
        requestAnimationFrame(function () { requestAnimationFrame(done); });
      }
      window.addEventListener('yomama:econ', go);
      var slack = document.querySelector('script[src*="econ.js"]') ? 1200 : 0;
      if (document.readyState === 'complete') setTimeout(go, slack);
      else window.addEventListener('load', function () { setTimeout(go, slack); });
      setTimeout(go, 9000);
    });
  }
  var pageReady = firstRender().then(function () {
    return (document.fonts && document.fonts.ready) ? document.fonts.ready : null;
  });

  function run(indices) {
    retry.hidden = true;
    status.textContent = 'Downloading all game assets';
    download(indices).then(function (errors) {
      if (stopped) return;
      failed = errors;
      if (failed.length) {
        status.textContent = failed.length + ' assets could not download. Retry to finish the full pack.';
        retry.hidden = false;
        skip.hidden = false;
        return;
      }
      status.textContent = 'Finishing the page';
      pageReady.then(function () { if (!stopped) finish(true); });
    });
  }
  // Give this page's scripts, snapshot and visible art the first network slots.
  // The screen stays up while the complete pack downloads afterwards.
  if (files.length) {
    retry.addEventListener('click', function () { run(failed); });
    pageReady.then(function () {
      if (!stopped) run(files.map(function (_, index) { return index; }));
    });
  } else {
    status.textContent = 'The asset list is unavailable. Reload or enter the game.';
    retry.hidden = false;
    skip.hidden = false;
    retry.textContent = 'Reload';
    retry.addEventListener('click', function () { location.reload(); });
  }

  window.YomamaLoading = { shown: true, finish: finish };
}());
