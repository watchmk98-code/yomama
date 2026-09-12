/* The account control in the header: LOG OUT on every page, and nobody
   inherits the previous person's seat on a shared computer.

   - Wires the LOG OUT pill that index.html and the game pages carry in
     .right-meta. Signed out, it reads SIGN IN and goes to join.html.
   - Log out clears every credential this browser holds - the student
     session, the cash mirror, the teacher console login and the teacher's
     seat PIN - and goes to join.html.
   - After IDLE_MINUTES without a click, key, touch or scroll the same
     happens on its own, so a student who walks away is signed out before
     the next one sits down. Set window.YOMAMA_IDLE_MINUTES before this
     script loads to change it; 0 disables it.
   - Logging out in one tab signs out every other tab of this browser.
   - The server only serves pages to a browser with a live seat cookie
     (server.py PUBLIC_PAGES). This script is the belt to that: a page that
     is open without a seat - a cached copy, a back-button restore - goes to
     join.html as well. */
(function () {
  'use strict';
  var SESSION_KEY = 'yomama_session_v1';
  var KEYS = [SESSION_KEY, 'yomama_server_cash_v1', 'yomama_teacher_v1', 'yomama_teacher_seat_v1'];
  var IDLE_MINUTES = (typeof window.YOMAMA_IDLE_MINUTES === 'number' && isFinite(window.YOMAMA_IDLE_MINUTES))
    ? window.YOMAMA_IDLE_MINUTES : 20;
  var JOIN = './join.html';

  function session() { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch (e) { return null; } }
  function signedIn() { var s = session(); return !!(s && s.token); }

  function clearAll() {
    try { if (window.YomamaNet && window.YomamaNet.leave) window.YomamaNet.leave(); } catch (e) {}
    KEYS.forEach(function (k) { try { localStorage.removeItem(k); } catch (e) {} });
    try {   // the cookie the server reads; yomama-net.js clears it too when it is loaded
      document.cookie = 'yomama_session=; Path=/; Max-Age=0; SameSite=Lax' +
        (window.location.protocol === 'https:' ? '; Secure' : '');
    } catch (e) {}
  }
  function toSignIn() {
    var here = window.location.pathname + window.location.search;
    window.location.replace(JOIN + '?next=' + encodeURIComponent(here));
  }
  function logout(reason) {
    clearAll();
    window.location.replace(JOIN + '?signedout=' + (reason || '1'));
  }

  // The pill has no id in the markup; find it by where it sits and what it says.
  function isAccountButton(b) {
    if (!b || b.tagName !== 'BUTTON') return false;
    if (b.hasAttribute('data-account')) return true;
    var t = (b.textContent || '').trim().toUpperCase();
    return !!b.closest('.right-meta') && (t === 'LOG OUT' || t === 'SIGN IN');
  }
  function label() {
    var pills = document.querySelectorAll('.right-meta button, button[data-account]');
    for (var i = 0; i < pills.length; i++) {
      var b = pills[i];
      if (!isAccountButton(b)) continue;
      b.setAttribute('data-account', '1');
      var s = session();
      if (s && s.token) {
        b.textContent = 'LOG OUT';
        b.title = 'Sign out ' + (s.name || '') + ' so the next person can sign in';
      } else {
        b.textContent = 'SIGN IN';
        b.title = 'Sign in with your class code, name and PIN';
      }
    }
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest('button') : null;
    if (!isAccountButton(b)) return;
    ev.preventDefault();
    if (signedIn()) logout('1'); else window.location.href = JOIN;
  });

  // Idle sign-out. Only real activity resets it; the pages' own polling does not.
  var idleTimer = null;
  function armIdle() {
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
    if (!IDLE_MINUTES || !signedIn()) return;
    idleTimer = setTimeout(function () { if (signedIn()) logout('idle'); }, IDLE_MINUTES * 60000);
  }
  ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll'].forEach(function (evt) {
    document.addEventListener(evt, armIdle, { passive: true, capture: true });
  });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) armIdle(); });

  // Another tab of this browser logged out (or in).
  window.addEventListener('storage', function (ev) {
    if (ev.key !== SESSION_KEY) return;
    if (!ev.newValue) { window.location.replace(JOIN + '?signedout=1'); return; }
    label(); armIdle();
  });

  if (!signedIn()) { toSignIn(); return; }
  window.addEventListener('pageshow', function (ev) { if (ev.persisted && !signedIn()) toSignIn(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', label); else label();
  window.addEventListener('yomama:econ', label);     // econ.js redraws the header on updates
  armIdle();
  window.YomamaAccount = { logout: logout, idleMinutes: IDLE_MINUTES };
}());
