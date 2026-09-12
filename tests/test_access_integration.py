"""The access rules as wired into game_api.py and server.py - over real HTTP too."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import pytest
import game_api as A
import admin
import access
import server


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "game.db"
    monkeypatch.setattr(A, "DB_PATH", path)
    A.init_db()
    return path


def opened(db, **kw):
    return admin_do(db, admin.open_class, **kw)


def admin_do(db, fn, *args, **kw):
    c = admin.connect(db)
    try:
        return fn(c, *args, **kw)
    finally:
        c.close()


# ------------------------------------------------------------- in-process ---

def test_login_is_off_and_the_server_schema_carries_the_admin_columns(db):
    assert A.AUTO_LOGIN is False
    assert set(admin.ADMIN_COLUMNS) <= set(A.MIGRATIONS)
    with A.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    assert {"teacher_code", "joins_open", "active", "label"} <= cols
    with pytest.raises(A.ApiError) as e:
        A.econ_state({"token": [""]})
    assert e.value.status == 401


def test_teacher_code_opens_the_console(db):
    c = opened(db, label="9-B")
    got = A.teacher_login({"teacher_code": c["teacher_code"].lower()})
    assert got["code"] == c["code"] and got["label"] == "9-B"
    assert A.teacher({"teacher_token": got["teacher_token"], "action": "roster"})["code"] == c["code"]
    assert A.teacher_econ({"teacher_token": [got["teacher_token"]]})["code"] == c["code"]


def test_closed_class_lets_its_own_students_back_in_but_seats_nobody_new(db):
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    admin_do(db, admin.close_class, c["code"])
    assert A.join(dict(code=c["code"], name="ALICE", pin="1234"))["rejoined"]
    assert "cash" in A.econ_state({"token": [alice["token"]]})
    with pytest.raises(A.ApiError) as e:
        A.join(dict(code=c["code"], name="BOB", pin="1234"))
    assert e.value.status == 403
    admin_do(db, admin.reopen_class, c["code"])
    assert not A.join(dict(code=c["code"], name="BOB", pin="1234"))["rejoined"]


def test_revoked_class_refuses_students_and_teacher_alike(db):
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    token = A.teacher_login({"teacher_code": c["teacher_code"]})["teacher_token"]
    admin_do(db, admin.revoke_class, c["code"])
    calls = (lambda: A.econ_state({"token": [alice["token"]]}),
             lambda: A.econ_sell(dict(token=alice["token"], slot=0)),
             lambda: A.join(dict(code=c["code"], name="ALICE", pin="1234")),
             lambda: A.join(dict(code=c["code"], name="BOB", pin="1234")),
             lambda: A.teacher({"teacher_token": token, "action": "roster"}),
             lambda: A.teacher_econ({"teacher_token": [token]}),
             lambda: A.teacher_login({"teacher_code": c["teacher_code"]}))
    for call in calls:
        with pytest.raises(A.ApiError) as e:
            call()
        assert e.value.status == 403
    admin_do(db, admin.restore_class, c["code"])
    assert "cash" in A.econ_state({"token": [alice["token"]]})


# ------------------------------------------------------------------- http ---

class Quiet(server.NewsProxyHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def http(db, monkeypatch):
    fresh = {p: access.RateLimiter(l.limit, l.window) for p, l in access.LOGIN_LIMITS.items()}
    monkeypatch.setattr(access, "LOGIN_LIMITS", fresh)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]

    def call(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw
    yield call
    srv.shutdown()
    srv.server_close()


def test_http_nobody_can_open_a_class_and_secrets_are_not_served(http):
    assert http("POST", "/api/game/session", {"class_size": 30})[0] == 404
    assert http("GET", "/game.db")[0] == 404
    assert http("GET", "/.git/config")[0] == 404
    assert http("GET", "/admin.py")[0] == 404
    assert http("GET", "/join.html")[0] == 200
    assert http("GET", "/class.html")[0] == 200


def test_http_teacher_login_then_console_then_student_join(http, db):
    c = opened(db)
    status, t = http("POST", "/api/game/teacher/login", {"teacher_code": c["teacher_code"]})
    assert status == 200 and t["code"] == c["code"]
    status, board = http("POST", "/api/game/teacher", {"teacher_token": t["teacher_token"], "action": "roster"})
    assert status == 200 and board["count"] == 0
    status, j = http("POST", "/api/game/join", {"code": c["code"], "name": "Alice", "pin": "1234"})
    assert status == 200 and j["name"] == "ALICE"
    status, st = http("GET", "/api/game/econ/state?token=" + j["token"])
    assert status == 200 and "cash" in st
    status, board = http("POST", "/api/game/teacher", {"teacher_token": t["teacher_token"], "action": "roster"})
    assert board["count"] == 1 and board["roster"][0]["name"] == "ALICE"


def test_http_wrong_codes_are_budgeted_per_address_and_right_ones_are_free(http, db, monkeypatch):
    monkeypatch.setattr(access, "BEHIND_PROXY", True)
    c = opened(db)
    limit = access.LOGIN_LIMITS["/api/game/teacher/login"].limit
    for _ in range(limit):
        assert http("POST", "/api/game/teacher/login", {"teacher_code": "ZZZZZZ"})[0] == 404
    status, body = http("POST", "/api/game/teacher/login", {"teacher_code": c["teacher_code"]})
    assert status == 429 and "ten minutes" in body["error"]     # even the right code, from that address
    status, body = http("POST", "/api/game/teacher/login", {"teacher_code": c["teacher_code"]},
                        {"X-Forwarded-For": "203.0.113.9"})
    assert status == 200                                          # another address is unaffected
    # A whole class joins from one router: right answers never count.
    for i in range(access.LOGIN_LIMITS["/api/game/join"].limit + 5):
        assert http("POST", "/api/game/join", {"code": c["code"], "name": "S%d" % i, "pin": "1234"})[0] == 200
    # A malformed request is a 400 and does not count either; a wrong PIN does.
    assert http("POST", "/api/game/join", {"code": c["code"], "name": "S1", "pin": "12"})[0] == 400
    assert http("POST", "/api/game/join", {"code": c["code"], "name": "S1", "pin": "9999"})[0] == 409
    assert http("POST", "/api/game/join", {"code": c["code"], "name": "S1", "pin": "1234"})[0] == 200
