/**
 * YOMAMA INVESTMENTS - client link to the classroom server.
 *
 * Everything shared or scored (market prices, cash, inventory, positions,
 * leaderboard) lives on the server. This module is the only thing that talks
 * to it.
 *
 * Degrades gracefully: if the student has not joined a class, or the server is
 * unreachable, `isLive()` returns false and every page falls back to the
 * original localStorage behaviour. Opening index.html straight off disk still
 * works.
 */
(function () {
  'use strict';

  var SESSION_KEY = 'yomama_session_v1';
  var CASH_MIRROR_KEY = 'yomama_server_cash_v1';
  var BASE = '/api/game';

  var PLAYER_SAVE_KEY = 'yomama_player_save_v1';
  var PLAYER_SAVE_BACKUP_KEY = 'yomama_player_save_v1_backup';
  var SAVED_AT_KEY = 'yomama_save_at_v1';
  var PUSH_DEBOUNCE_MS = 3000;

  var pushTimer = null;
  var pendingEconomy = null;
  var pendingStamp = 0;      // when the state CHANGED, not when we send it
  var lastSyncedJson = null; // what the server already has, to skip no-op pushes
  // Nothing may be written to the server until we know whether this browser or
  // the server holds the newer base. Without this a freshly-opened second
  // device pushes its blank starting state over the real save.
  var hydrateDone = false;
  var readyPromise = null;

  var session = null;      // { token, name, code }
  var live = false;        // server reachable AND joined
  var lastState = null;
  var cashListeners = [];
  var probe = null;

  // ---------------------------------------------------------------- storage
  function readJson(key) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }
  function writeJson(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  }
  function clearKey(key) {
    try { window.localStorage.removeItem(key); } catch (_) {}
  }

  function localEconomy() {
    var save = readJson(PLAYER_SAVE_KEY);
    return (save && save.economyV01 && typeof save.economyV01 === 'object') ? save.economyV01 : null;
  }

  // Send immediately, bypassing the debounce. Used when the page is going away.
  function flushNow() {
    var blob = pendingEconomy;
    if (!blob || !session) return;
    pendingEconomy = null;
    if (pushTimer) { clearTimeout(pushTimer); pushTimer = null; }
    var stamp = pendingStamp || Date.now();
    // Record it locally up front: a beacon gives no callback, and a browser
    // that stayed behind would otherwise re-adopt its own push next load.
    writeJson(SAVED_AT_KEY, { at: stamp });
    lastSyncedJson = JSON.stringify(blob);
    var payload = JSON.stringify({
      token: session.token, buildings: { economy: blob, savedAt: stamp },
    });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(BASE + '/buildings', new Blob([payload], { type: 'application/json' }));
        return;
      }
    } catch (_) {}
    try {
      fetch(BASE + '/buildings', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: payload, keepalive: true,
      });
    } catch (_) {}
  }

  function loadSession() {
    var s = readJson(SESSION_KEY);
    if (s && typeof s === 'object' && s.token && s.code) return s;
    return null;
  }
  session = loadSession();

  // ------------------------------------------------------------- transport
  function request(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(BASE + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.error) || ('HTTP ' + res.status));
          err.status = res.status;
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  function withToken(body) {
    var out = body || {};
    out.token = session ? session.token : '';
    return out;
  }

  // ------------------------------------------------------------------ cash
  // A synchronous mirror of server cash, so code paths that cannot await
  // (the buildings spend path) can still gate on it.
  function cachedCash() {
    var v = readJson(CASH_MIRROR_KEY);
    return (v && typeof v.cash === 'number' && isFinite(v.cash)) ? v.cash : null;
  }
  function setCachedCash(cash) {
    if (typeof cash !== 'number' || !isFinite(cash)) return;
    writeJson(CASH_MIRROR_KEY, { cash: cash, at: Date.now() });
    cashListeners.forEach(function (fn) {
      try { fn(cash); } catch (_) {}
    });
  }

  // ------------------------------------------------------------------- api
  var Net = {
    isJoined: function () { return !!session; },

    /**
     * Resolves once this browser's base is settled against the server - either
     * the server copy was adopted or ours was found to be newer. Read the
     * economy only after this resolves.
     */
    ready: function () { return readyPromise || Promise.resolve(0); },
    isLive: function () { return live; },
    session: function () { return session ? { name: session.name, code: session.code } : null; },
    onCash: function (fn) { if (typeof fn === 'function') cashListeners.push(fn); },
    cachedCash: cachedCash,
    lastState: function () { return lastState; },

    /** Verify the stored token still works. Sets isLive(). */
    connect: function () {
      if (probe) return probe;
      if (!session) { live = false; return Promise.resolve(false); }
      probe = Net.refresh().then(function (s) {
        live = !!s;
        return live;
      }).catch(function () {
        live = false;
        return false;
      }).then(function (v) { probe = null; return v; });
      return probe;
    },

    join: function (code, name, pin) {
      return request('POST', '/join', { code: code, name: name, pin: pin }).then(function (data) {
        session = { token: data.token, name: data.name, code: data.code };
        writeJson(SESSION_KEY, session);
        live = true;
        return data;
      });
    },

    leave: function () {
      session = null; live = false; lastState = null;
      clearKey(SESSION_KEY); clearKey(CASH_MIRROR_KEY);
    },

    /** One round trip for everything a page needs. */
    refresh: function () {
      if (!session) return Promise.resolve(null);
      return request('GET', '/state?token=' + encodeURIComponent(session.token)).then(function (s) {
        lastState = s;
        live = true;
        if (s && s.player) setCachedCash(s.player.cash);
        return s;
      }).catch(function (err) {
        if (err && err.status === 401) Net.leave();   // token no longer valid
        live = false;
        throw err;
      });
    },

    // The Part 1 economy is not here: econ.js talks to /api/game/econ/* and the
    // server owns every YM. What is left below is the class session, the Part 2
    // equity desk and the small display-state blob.

    tradeEquity: function (symbol, side, shares) {
      return request('POST', '/equity', withToken({ symbol: symbol, side: side, shares: shares }))
        .then(function (r) { setCachedCash(r.cash); return r; });
    },

    /**
     * Push the whole buildings/economy blob to the server, debounced.
     *
     * Wrapped as { economy, savedAt } rather than stamping a field inside the
     * economy itself, because app.js sanitises that object and would drop an
     * unknown key - taking the timestamp the newer-wins check depends on.
     */
    pushBuildings: function (economy) {
      if (!session || !live || !hydrateDone || !economy) return;
      // Re-sending an unchanged base would give it a fresh timestamp and make
      // this browser look newer than another device's real progress.
      var json;
      try { json = JSON.stringify(economy); } catch (_) { return; }
      if (json === lastSyncedJson) return;
      pendingEconomy = economy;
      pendingStamp = Date.now();
      if (pushTimer) return;
      pushTimer = setTimeout(function () {
        pushTimer = null;
        var blob = pendingEconomy;
        pendingEconomy = null;
        if (!blob) return;
        var stamp = pendingStamp || Date.now();
        writeJson(SAVED_AT_KEY, { at: stamp });
        lastSyncedJson = JSON.stringify(blob);
        request('POST', '/buildings', withToken({ buildings: { economy: blob, savedAt: stamp } }))
          .catch(function () {});     // a failed push just means the next one carries it
      }, PUSH_DEBOUNCE_MS);
    },

    /**
     * Adopt the server's copy when it is newer than this browser's.
     * Returns the savedAt it adopted, or 0 when local already wins.
     */
    hydrateBuildings: function () {
      if (!session) { hydrateDone = true; return Promise.resolve(0); }
      return request('GET', '/buildings?token=' + encodeURIComponent(session.token))
        .then(function (res) {
          hydrateDone = true;
          var remote = res && res.buildings;
          if (!remote || !remote.economy || !remote.savedAt) {
            Net.pushBuildings(localEconomy());   // server has nothing yet
            return 0;
          }
          var localAt = (readJson(SAVED_AT_KEY) || {}).at || 0;
          if (remote.savedAt <= localAt) { Net.pushBuildings(localEconomy()); return 0; }

          var save = readJson(PLAYER_SAVE_KEY);
          save = (save && typeof save === 'object') ? save : {};
          save.economyV01 = remote.economy;
          if (remote.economy.activeCharacter) save.selectedCharacter = remote.economy.activeCharacter;
          writeJson(PLAYER_SAVE_KEY, save);
          writeJson(PLAYER_SAVE_BACKUP_KEY, save);
          writeJson(SAVED_AT_KEY, { at: remote.savedAt });
          lastSyncedJson = JSON.stringify(remote.economy);
          return remote.savedAt;
        })
        .catch(function () {
          // Could not read the server copy. Allow saving anyway: losing future
          // progress is worse than the small risk of an out-of-date push.
          hydrateDone = true;
          return 0;
        });
    },

    saveBuildings: function (blob) {
      if (!session) return Promise.resolve(null);
      return request('POST', '/buildings', withToken({ buildings: blob }));
    },

    loadBuildings: function () {
      if (!session) return Promise.resolve(null);
      return request('GET', '/buildings?token=' + encodeURIComponent(session.token))
        .then(function (r) { return r.buildings; });
    },
  };

  // A navigation kills the debounce timer, so make sure anything pending goes
  // out before the page disappears.
  window.addEventListener('pagehide', flushNow);
  window.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushNow();
  });

  window.YomamaNet = Net;

  // Connect and settle the base before any page reads it. Pages call ready()
  // and wait; racing this with a reload does not work, because app.js finishes
  // its own async init and writes its in-memory defaults back over whatever
  // was just adopted.
  readyPromise = session
    ? Net.connect().then(function () { return Net.hydrateBuildings(); }).catch(function () { return 0; })
    : Promise.resolve(0);
}());
