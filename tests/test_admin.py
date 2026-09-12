"""admin.py provisioning and access.py rules, against a real SQLite file."""
import contextlib
import json
import sqlite3
import pytest
import game_api as A
import admin
import access


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "game.db"
    monkeypatch.setattr(A, "DB_PATH", path)
    monkeypatch.setattr(A, "AUTO_LOGIN", False)
    A.init_db()                     # the server creates the tables; admin.py never does
    return path


@contextlib.contextmanager
def conn(db):
    c = admin.connect(db)
    try:
        yield c
    finally:
        c.close()


def opened(db, **kw):
    with conn(db) as c:
        return admin.open_class(c, **kw)


def session(db, code):
    with conn(db) as c:
        return admin.session_of(c, code)


# ------------------------------------------------------------ provisioning ---

def test_admin_opened_class_is_playable_by_the_real_server_code(db):
    c = opened(db, label="9-B", size=12)
    joined = A.join(dict(code=c["code"], name="alice", pin="1234"))
    assert joined["name"] == "ALICE" and not joined["rejoined"]
    state = A.econ_state({"token": [joined["token"]]})
    assert "cash" in state and "buildings" in state
    with conn(db) as k:
        board = admin.roster(k, c["code"])
    assert board == [dict(rank=1, name="ALICE", net_worth=board[0]["net_worth"],
                          joined_at=board[0]["joined_at"])]
    assert isinstance(board[0]["net_worth"], int)


def test_codes_are_distinct_and_typeable(db):
    classes = [opened(db) for _ in range(25)]
    codes = {c["code"] for c in classes}
    teacher_codes = {c["teacher_code"] for c in classes}
    assert len(codes) == len(teacher_codes) == 25
    for c in classes:
        assert len(c["code"]) == 5 and set(c["code"]) <= set(admin.ALPHABET)
        assert len(c["teacher_code"]) == 6 and set(c["teacher_code"]) <= set(admin.ALPHABET)
    assert not (set("IO01") & set("".join(codes | teacher_codes)))


def test_size_and_label_are_clamped(db):
    c = opened(db, label="   a   very   long   label " + "x" * 80, size=999)
    assert c["class_size"] == 200
    assert c["label"].startswith("a very long label") and len(c["label"]) == 40
    assert opened(db, size=0)["class_size"] == 30


def test_close_stops_new_joins_only(db):
    c = opened(db)
    A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    with conn(db) as k:
        admin.close_class(k, c["code"])
    s = session(db, c["code"])
    with pytest.raises(A.ApiError) as e:
        access.check_joins_open(s)
    assert e.value.status == 403
    access.check_active(s)                      # the joined students play on
    with conn(db) as k:
        admin.reopen_class(k, c["code"])
    access.check_joins_open(session(db, c["code"]))


def test_revoke_blocks_everyone_until_restored(db):
    c = opened(db)
    with conn(db) as k:
        admin.revoke_class(k, c["code"])
        s = admin.session_of(k, c["code"])
        with pytest.raises(A.ApiError) as e:
            access.check_active(s)
        assert e.value.status == 403
        with pytest.raises(A.ApiError) as e:
            access.teacher_login(k, c["teacher_code"])
        assert e.value.status == 403
        admin.restore_class(k, c["code"])
        access.check_active(admin.session_of(k, c["code"]))
        assert access.teacher_login(k, c["teacher_code"])["code"] == c["code"]


def test_teacher_login_exchanges_the_short_code_for_the_token(db):
    c = opened(db, label="Ms. Yilmaz", size=25)
    with conn(db) as k:
        s = admin.session_of(k, c["code"])
        got = access.teacher_login(k, " " + c["teacher_code"].lower() + " ")
        assert got == dict(code=c["code"], teacher_token=s["teacher_token"],
                           label="Ms. Yilmaz", class_size=25)
        with pytest.raises(A.ApiError) as e:
            access.teacher_login(k, "NOPE99")
        assert e.value.status == 404
        with pytest.raises(A.ApiError) as e:
            access.teacher_login(k, "")
        assert e.value.status == 400
    # the token the login hands out is the one the console endpoints accept
    assert A.teacher(dict(teacher_token=got["teacher_token"], action="roster"))["code"] == c["code"]


def test_rotate_kills_the_old_code_and_the_old_token(db):
    c = opened(db)
    old = session(db, c["code"])["teacher_token"]
    with conn(db) as k:
        new = admin.rotate(k, c["code"])
        assert new["teacher_code"] != c["teacher_code"]
        with pytest.raises(A.ApiError):
            access.teacher_login(k, c["teacher_code"])
        assert access.teacher_login(k, new["teacher_code"])["teacher_token"] != old
    with pytest.raises(A.ApiError) as e:
        A.teacher(dict(teacher_token=old, action="roster"))
    assert e.value.status == 403


def test_kick_frees_the_seat_and_signs_the_browser_out(db):
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="Alice", pin="1111"))
    with conn(db) as k:
        assert admin.kick(k, c["code"], "  alice ") == dict(code=c["code"], name="ALICE", kicked=True)
        assert admin.roster(k, c["code"]) == []
        with pytest.raises(admin.AdminError):
            admin.kick(k, c["code"], "ALICE")
    with pytest.raises(A.ApiError) as e:
        A.econ_state({"token": [alice["token"]]})
    assert e.value.status == 401
    assert not A.join(dict(code=c["code"], name="ALICE", pin="2222"))["rejoined"]


def test_unknown_class_is_an_error(db):
    with conn(db) as k:
        for fn in (admin.roster, admin.close_class, admin.revoke_class, admin.rotate):
            with pytest.raises(admin.AdminError):
                fn(k, "ZZZZZ")


def test_every_admin_action_leaves_a_ledger_row(db):
    c = opened(db)
    A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    with conn(db) as k:
        admin.close_class(k, c["code"]); admin.reopen_class(k, c["code"])
        admin.revoke_class(k, c["code"]); admin.restore_class(k, c["code"])
        admin.kick(k, c["code"], "ALICE"); admin.rotate(k, c["code"])
        kinds = [r["kind"] for r in k.execute(
            "SELECT kind FROM ledger WHERE code=? AND kind LIKE 'admin_%' ORDER BY id", (c["code"],))]
    assert kinds == ["admin_open_class", "admin_close", "admin_reopen", "admin_revoke",
                     "admin_restore", "admin_kick", "admin_rotate_teacher_code"]


# ------------------------------------------------- databases without admin ---

def test_a_database_from_before_admin_py_is_still_allowed(db):
    # init_db now adds the admin columns itself, so take them away again to get
    # a file from before they existed, with a class already in it.
    teacher = A.create_session({})
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    for _, column, _ in admin.ADMIN_COLUMNS:
        raw.execute(f"ALTER TABLE sessions DROP COLUMN {column}")
    raw.commit()
    s = raw.execute("SELECT * FROM sessions WHERE code=?", (teacher["code"],)).fetchone()
    assert "active" not in s.keys()
    access.check_active(s)
    access.check_joins_open(s)
    with pytest.raises(A.ApiError) as e:
        access.teacher_login(raw, "ABCDEF")
    assert e.value.status == 404
    raw.close()


def test_admin_refuses_a_missing_or_empty_database(tmp_path, capsys):
    assert admin.main(["--db", str(tmp_path / "nope.db"), "list"]) == 1
    assert "start the server once" in capsys.readouterr().err
    (tmp_path / "empty.db").write_bytes(b"")
    assert admin.main(["--db", str(tmp_path / "empty.db"), "list"]) == 1
    assert "start the server once" in capsys.readouterr().err


# ------------------------------------------------------------ rate limiting ---

def test_rate_limiter_counts_failures_within_the_window_only():
    rl = access.RateLimiter(3, 60)
    assert not rl.blocked("1.2.3.4", now=1000)
    for t in (1000, 1030, 1050):
        rl.hit("1.2.3.4", now=t)
    assert rl.blocked("1.2.3.4", now=1059)
    assert not rl.blocked("9.9.9.9", now=1059)      # other addresses unaffected
    assert not rl.blocked("1.2.3.4", now=1061)      # the 1000 failure has aged out
    rl.hit("1.2.3.4", now=1061)
    assert rl.blocked("1.2.3.4", now=1062)          # 1030, 1050, 1061: three again
    assert not rl.blocked("1.2.3.4", now=1122)      # all aged out; nothing sticks


def test_client_ip_trusts_the_proxy_header_only_when_told_to():
    hdrs = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    assert access.client_ip(hdrs, "10.0.0.2", behind_proxy=True) == "203.0.113.7"
    cf = {"CF-Connecting-IP": "198.51.100.4", "X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    assert access.client_ip(cf, "10.0.0.2", behind_proxy=True) == "198.51.100.4"   # the edge wins
    assert access.client_ip({}, "10.0.0.2", behind_proxy=True) == "10.0.0.2"
    assert access.client_ip(hdrs, "10.0.0.2", behind_proxy=False) == "10.0.0.2"   # forgeable on a LAN
    assert "/api/game/join" in access.LOGIN_LIMITS and "/api/game/teacher/login" in access.LOGIN_LIMITS


# --------------------------------------------------------------------- cli ---

def test_cli_open_and_list(db, capsys):
    assert admin.main(["--db", str(db), "--json", "open", "--label", "9-B", "--size", "12"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["label"] == "9-B" and out["class_size"] == 12
    assert session(db, out["code"])["teacher_code"] == out["teacher_code"]

    assert admin.main(["--db", str(db), "open"]) == 0
    text = capsys.readouterr().out
    assert "STUDENTS  join.html" in text and "TEACHER   class.html" in text

    assert admin.main(["--db", str(db), "list"]) == 0
    text = capsys.readouterr().out
    assert out["code"] in text and out["teacher_code"] in text and "9-B" in text

    assert admin.main(["--db", str(db), "roster", out["code"].lower()]) == 0
    assert "nobody has joined" in capsys.readouterr().out
    assert admin.main(["--db", str(db), "kick", out["code"], "NOBODY"]) == 1
    assert "no student" in capsys.readouterr().err
