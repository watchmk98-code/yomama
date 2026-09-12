"""The contract between the game and the access, hosting and account layer.

Each test names the AGENTS.md section it enforces and fails with a message
that says what to do. They exist so that a change to the game - an endpoint,
a page, a payload field, the economy API - cannot silently break sign-in,
the login wall, provisioning or hosting.
"""
import copy
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest

import access
import admin
import game_api as A
import server
from test_access_integration import db, opened, admin_do   # noqa: F401  (fixture + helpers)
from test_page_gate import site, seat                       # noqa: F401  (fixture + helper)

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted(p.name for p in ROOT.glob("*.html"))
GET = server.NewsProxyHandler.GAME_GET_ROUTES
POST = server.NewsProxyHandler.GAME_POST_ROUTES


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def see(section):
    return " See AGENTS.md section %s." % section


# ------------------------------------------------------------ endpoints ---

def test_no_endpoint_answers_without_a_seat(db):
    """AUTO_LOGIN is off: a bogus or missing token is an ApiError, never data."""
    assert A.AUTO_LOGIN is False, "game_api.AUTO_LOGIN must stay False; previews turn it on for themselves." + see("2")
    bogus = {"token": "bogus", "teacher_token": "bogus", "teacher_code": "ZZZZZZ", "code": "ZZZZZ",
             "name": "X", "pin": "1234", "action": "roster", "slot": 0, "tier": 1}
    public = {("GET", "/api/game/econ/quiz")}          # the questions without the answer key
    for method, table in (("GET", GET), ("POST", POST)):
        for path, fn in table.items():
            if (method, path) in public:
                continue
            payloads = [{}, dict(bogus), {k: [v] for k, v in bogus.items()}]
            for payload in payloads:
                try:
                    out = fn(payload)
                except A.ApiError as e:
                    assert e.status in (400, 401, 403, 404), (method, path, payload, e.status, e.message)
                else:
                    pytest.fail("%s %s answered %r without a valid seat: %r. Authenticate with _auth() or "
                                "_teacher_auth() and raise ApiError." % (method, path, payload, out) + see("6"))


def test_endpoints_that_touch_economy_state_are_class_locked():
    """New handlers must be added to the _class_locked name list in game_api.py."""
    # Pinned as found on 2026-09-12. The first four never touch economy state.
    # /econ/graduate is a legacy v3 alias that goes through _act(); it belongs
    # in the list too - move it out of here when it is added there.
    unlocked_on_purpose = {("GET", "/api/game/buildings"), ("GET", "/api/game/econ/quiz"),
                           ("POST", "/api/game/buildings"), ("POST", "/api/game/teacher/login"),
                           ("POST", "/api/game/econ/graduate")}
    found = {(m, p) for m, t in (("GET", GET), ("POST", POST)) for p, fn in t.items()
             if not hasattr(fn, "__wrapped__")}
    new = sorted(found - unlocked_on_purpose)
    assert not new, ("%s are routed but not in the _class_locked list at the bottom of game_api.py. "
                     "Add them there if they read or write economy state; add them to unlocked_on_purpose "
                     "in this test only if they never do." % new) + see("6")


def test_payloads_keep_the_fields_the_header_console_and_gate_read(db):
    """econ-nav.js, yomama-net.js, class.html and teacher-econ.js read these by name."""
    c = opened(db, label="9-B")
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    st = A.econ_state({"token": [alice["token"]]})
    for key in ("cash", "netWorth", "gateOpen", "leaderboard", "name"):
        assert key in st, "econ_state lost %r (read by econ.js / econ-nav.js)." % key + see("3")
    gs = A.get_state({"token": [alice["token"]]})
    assert "cash" in gs["player"] and "code" in gs["session"] and "leaderboard" in gs, \
        "get_state lost a field yomama-net.js or index.html reads." + see("3")
    tt = A.teacher_login({"teacher_code": c["teacher_code"]})["teacher_token"]
    te = A.teacher_econ({"teacher_token": [tt]})
    for key in ("code", "paused", "students", "modelVersion", "goodSalesNeeded", "families", "eventDefaults"):
        assert key in te, "teacher_econ lost %r (read by teacher-econ.js)." % key + see("3")
    student = te["students"][0]
    for key in ("name", "netWorth", "rank", "checklist", "gateOpen", "buildings"):
        assert key in student, "teacher_econ students[] lost %r (read by teacher-econ.js)." % key + see("3")
    for key in ("lv25", "auto", "goodSales", "quiz"):
        assert key in student["checklist"], "checklist lost %r (read by teacher-econ.js)." % key + see("3")
    roster = A.teacher({"teacher_token": tt, "action": "roster"})
    for key in ("code", "paused", "minute", "class_size", "roster", "count"):
        assert key in roster, "teacher roster lost %r (read by class.html)." % key + see("3")
    for key in ("name", "net_worth", "rank", "joined_at"):
        assert key in roster["roster"][0], "roster rows lost %r (read by class.html)." % key + see("3")


# ----------------------------------------------------------------- pages ---

def test_every_page_on_disk_is_behind_the_wall(site, db):
    """No *.html but the two login screens is served without a live seat cookie."""
    c, token = seat(db)
    assert server.TOKEN_RE.fullmatch(token), "a seat token no longer matches server.TOKEN_RE; the wall would reject it." + see("2")
    for name in PAGES:
        path = "/" + name
        if path in server.PUBLIC_PAGES:
            assert site(path)[0] == 200, path
            continue
        assert server.needs_sign_in(path), path + " is not behind the wall." + see("2")
        status, location, _ = site(path)
        assert (status, location) == (302, "/join.html?next=" + quote(path, safe="")), \
            "%s was served without a seat (%s %s)." % (path, status, location) + see("2")
        assert site(path, "yomama_session=" + token)[0] == 200, path + " refused a live seat"
    assert server.PUBLIC_PAGES == frozenset({"/join.html", "/class.html"}), \
        "PUBLIC_PAGES changed: only the two login screens may be served before sign-in." + see("6")


def test_pages_with_the_header_load_the_account_control():
    """LOG OUT, the idle sign-out and the belt redirect live in account.js."""
    for name in PAGES:
        html = read(name)
        if 'class="right-meta"' not in html:
            continue
        assert 'src="./account.js' in html, \
            "%s has the header but does not load account.js: LOG OUT will do nothing there." % name + see("6")
        assert "/" + name not in server.PUBLIC_PAGES, name


# ----------------------------------------------------------------- names ---

def test_client_and_server_agree_on_the_session_names():
    """Renaming any of these signs the live classes out for good."""
    assert server.SESSION_COOKIE == "yomama_session"
    cookie = re.compile(r"yomama_session(?![_\w])")
    for f in ("yomama-net.js", "account.js"):
        assert cookie.search(read(f)), "%s no longer names the cookie %r." % (f, server.SESSION_COOKIE) + see("2")
    keys = {"yomama_session_v1": ("econ.js", "yomama-net.js", "account.js", "econ-nav.js", "class.html"),
            "yomama_teacher_v1": ("class.html", "teacher-econ.js", "account.js"),
            "yomama_teacher_seat_v1": ("class.html", "account.js"),
            "yomama_server_cash_v1": ("yomama-net.js", "account.js")}
    for key, files in keys.items():
        for f in files:
            assert key in read(f), "%s no longer uses the storage key %r; the pages would disagree about who is signed in." % (f, key) + see("2")
    assert set(access.LOGIN_LIMITS) <= set(POST), \
        "access.LOGIN_LIMITS names a route that is not in server.GAME_POST_ROUTES; the limiter would silently stop." + see("6")
    assert set(admin.ADMIN_COLUMNS) <= set(A.MIGRATIONS), \
        "admin.ADMIN_COLUMNS and game_api.MIGRATIONS drifted apart." + see("5")


# --------------------------------------------------------------- secrets ---

def test_secrets_stay_out_of_git_and_off_the_web():
    ignored = read(".gitignore").split()
    for pattern in ("game.db", "*.db", "roster*.json", "backups/"):
        assert pattern in ignored, "%r left .gitignore; the repository is public." % pattern + see("1")
    for path in ("/game.db", "/admin.py", "/access.py", "/run_server.py", "/render.yaml", "/DEPLOY.md",
                 "/AGENTS.md", "/config/quiz.json", "/.git/config", "/tests/test_contract.py", "/backups/"):
        assert not server.is_public_path(path), path + " would be served to anyone." + see("2")
    for path in ("/config/economy.v4.json", "/styles.css", "/account.js", "/assets/fonts/VT323-Regular.ttf"):
        assert server.is_public_path(path), path + " is no longer servable; the pages need it." + see("6")


def test_hosting_entry_point_still_exists():
    """Render starts `python3 run_server.py $PORT`; nothing else is configured."""
    yaml = read("render.yaml")
    assert "startCommand: python3 run_server.py $PORT" in yaml
    assert "autoDeploy: false" in yaml and "key: YOMAMA_DB" in yaml and "key: YOMAMA_BEHIND_PROXY" in yaml
    spec = importlib.util.spec_from_file_location("run_server_check", ROOT / "run_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                   # imports server and game_api; must not fail
    assert callable(module.main)


# --------------------------------------------------------------- economy ---

def test_new_rules_reach_a_running_class_only_through_reset(db, monkeypatch):
    """A class keeps the rules it started with; admin.py reset applies new ones."""
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    A.econ_state({"token": [alice["token"]]})
    marked = copy.deepcopy(A._startup_config)
    marked["contractMarker"] = "new rules"
    monkeypatch.setattr(A, "_startup_config", marked)
    monkeypatch.setattr(A.economy, "load_config", lambda path=None: copy.deepcopy(marked))
    A.econ_state({"token": [alice["token"]]})
    with A.connect() as conn:
        cfg = json.loads(A._session_of(conn, c["code"])["econ_config"])
    assert "contractMarker" not in cfg, "a running class picked up a config change without a reset." + see("5")
    A.reset_class(c["code"])
    with A.connect() as conn:
        cfg = json.loads(A._session_of(conn, c["code"])["econ_config"])
    assert cfg.get("contractMarker") == "new rules", "admin.py reset did not apply the rules on disk." + see("5")
    assert A.join(dict(code=c["code"], name="ALICE", pin="1234"))["token"] == alice["token"], \
        "reset must keep every seat and token." + see("5")
    assert "cash" in A.econ_state({"token": [alice["token"]]})


# --------------------------------------------------------------- previews ---

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url, timeout=5):
    """(status, Location, body) without following redirects."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    req = urllib.request.Request(url)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as r:
            return r.status, r.headers.get("Location"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location"), e.read()


def test_the_preview_launcher_serves_a_signed_in_game():
    """previews/day3_preview.py is what the Playwright checks run against."""
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k != "YOMAMA_DB"}
    real = ROOT / "game.db"
    before = real.stat().st_mtime if real.exists() else None
    proc = subprocess.Popen([sys.executable, "previews/day3_preview.py", str(port), "--fresh", "--no-snapshot"],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 30
        while True:
            if proc.poll() is not None:
                pytest.fail("the preview launcher exited:\n" + proc.stdout.read().decode(errors="replace"))
            try:
                if _get("http://127.0.0.1:%d/join.html" % port, timeout=1)[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, socket.timeout):
                pass
            assert time.time() < deadline, "the preview launcher did not come up in 30 s"
            time.sleep(0.25)
        base = "http://127.0.0.1:%d" % port
        status, location, body = _get(base + "/buildings.html")
        assert status == 200 and b"preview seat" in body and b"yomama_session_v1" in body, \
            "the preview no longer serves buildings.html signed in." + see("4")
        for page in ("/index.html", "/memos.html", "/"):
            status, location, _ = _get(base + page)
            assert status == 200, "%s was sent to sign in (%s %s) on a preview." % (page, status, location) + see("4")
        status, _, body = _get(base + "/api/game/econ/state")
        state = json.loads(body)
        assert status == 200 and "modelVersion" in state and state.get("name") == "NEW GAME PREVIEW", \
            "the preview's SOLO seat does not answer tokenless requests." + see("4")
        assert _get(base + "/game.db")[0] == 404 and _get(base + "/admin.py")[0] == 404
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    after = real.stat().st_mtime if real.exists() else None
    assert before == after, "the preview touched the real game.db." + see("4")


def test_preview_support_refuses_the_real_database(monkeypatch):
    monkeypatch.setattr(A, "AUTO_LOGIN", False)
    monkeypatch.setattr(A, "DB_PATH", A.DB_PATH)
    monkeypatch.setattr(A, "SOLO_NAME", A.SOLO_NAME)
    spec = importlib.util.spec_from_file_location("preview_support_check", ROOT / "previews" / "preview_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit):
        module.solo_seat(ROOT / "game.db", "NOPE")
    assert A.AUTO_LOGIN is False
