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

    /** Sell produced goods into (or buy back from) the shared market. */
    tradeProduct: function (productId, side, qty) {
      return request('POST', '/product', withToken({ product_id: productId, side: side, qty: qty }))
        .then(function (r) { setCachedCash(r.cash); return r; });
    },

    tradeEquity: function (symbol, side, shares) {
      return request('POST', '/equity', withToken({ symbol: symbol, side: side, shares: shares }))
        .then(function (r) { setCachedCash(r.cash); return r; });
    },

    /** Pay the cash half of a build/upgrade. Server is the authority. */
    spend: function (amount, reason) {
      return request('POST', '/spend', withToken({ amount: amount, reason: reason || 'build' }))
        .then(function (r) { setCachedCash(r.cash); return r; });
    },

    /** Register goods just produced so they reach the shared marketplace. */
    deposit: function (productId, qty) {
      return request('POST', '/produce', withToken({ product_id: productId, qty: qty }));
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

  window.YomamaNet = Net;

  // Probe on load so pages can check isLive() shortly after boot.
  if (session) { Net.connect().catch(function () {}); }
}());
