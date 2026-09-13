"""Fixes from the adversarial review: kill-switch coverage, limiter semantics,
the seat cap, fresh-class config, malformed tokens, the quiz file."""
import json
import pytest
import game_api as A
import admin
import access
import server
from test_access_integration import db, http, opened, admin_do   # noqa: F401  (fixtures + helpers)


@pytest.fixture(autouse=True)
def fresh_pin_limit(monkeypatch):
    monkeypatch.setattr(access, "PIN_LIMIT", access.RateLimiter(access.PIN_LIMIT.limit, access.PIN_LIMIT.window))


def test_revoked_class_refuses_the_buildings_endpoints_too(db):
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    assert A.save_buildings({"token": alice["token"], "buildings": {"hero": "x"}}) == {"saved": True}
    admin_do(db, admin.revoke_class, c["code"])
    for call in (lambda: A.load_buildings({"token": [alice["token"]]}),
                 lambda: A.save_buildings({"token": alice["token"], "buildings": {"hero": "y"}})):
        with pytest.raises(A.ApiError) as e:
            call()
        assert e.value.status == 403
    admin_do(db, admin.restore_class, c["code"])
    assert A.load_buildings({"token": [alice["token"]]}) == {"buildings": {"hero": "x"}}


def test_an_admin_opened_class_is_new_not_legacy(db):
    c = opened(db)
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    with A.connect() as conn:
        assert json.loads(A._session_of(conn, c["code"])["econ_config"]).get("version") == 4
    A.econ_state({"token": [alice["token"]]})
    # and a class the teacher looks at before anyone has joined
    c2 = opened(db)
    tt = A.teacher_login({"teacher_code": c2["teacher_code"]})["teacher_token"]
    A.teacher_econ({"teacher_token": [tt]})
    with A.connect() as conn:
        assert json.loads(A._session_of(conn, c2["code"])["econ_config"]).get("version") == 4
        kinds = [r["kind"] for r in conn.execute(
            "SELECT kind FROM ledger WHERE code IN (?,?) AND kind LIKE '%migration%'", (c["code"], c2["code"]))]
    assert kinds == []


def test_class_size_is_a_seat_cap_the_admin_can_raise(db):
    c = opened(db, size=2)
    A.join(dict(code=c["code"], name="ALICE", pin="1111"))
    A.join(dict(code=c["code"], name="BOB", pin="2222"))
    with pytest.raises(A.ApiError) as e:
        A.join(dict(code=c["code"], name="CARA", pin="3333"))
    assert e.value.status == 403 and "full" in e.value.message
    assert A.join(dict(code=c["code"], name="ALICE", pin="1111"))["rejoined"]      # a rejoin is not a seat
    assert admin_do(db, admin.resize, c["code"], 3) == {"code": c["code"], "class_size": 3}
    assert not A.join(dict(code=c["code"], name="CARA", pin="3333"))["rejoined"]


def test_wrong_pins_are_budgeted_per_seat_not_per_class(db):
    c = opened(db)
    A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    A.join(dict(code=c["code"], name="BOB", pin="1234"))
    for _ in range(access.PIN_LIMIT.limit):
        with pytest.raises(A.ApiError) as e:
            A.join(dict(code=c["code"], name="ALICE", pin="0000"))
        assert e.value.status == 409
    with pytest.raises(A.ApiError) as e:
        A.join(dict(code=c["code"], name="ALICE", pin="1234"))          # even the right PIN now
    assert e.value.status == 429
    assert A.join(dict(code=c["code"], name="BOB", pin="1234"))["rejoined"]   # Bob is untouched


def test_malformed_tokens_are_bad_requests_not_crashes(db):
    for call, status in ((lambda: A.econ_state({"token": {"a": 1}}), 401),
                         (lambda: A.econ_state({"token": [{"a": 1}]}), 401),
                         (lambda: A.econ_state({"token": "", "code": {"x": 1}}), 401),
                         (lambda: A.teacher({"teacher_token": {"a": 1}, "action": "roster"}), 403)):
        with pytest.raises(A.ApiError) as e:
            call()
        assert e.value.status == status


def test_http_refusals_of_a_right_code_never_count_against_the_classroom(http, db):
    c = opened(db, size=3)
    limit = access.LOGIN_LIMITS["/api/game/join"].limit
    join = lambda name, code=c["code"]: http("POST", "/api/game/join", {"code": code, "name": name, "pin": "1234"})[0]
    assert join("ALICE") == 200
    admin_do(db, admin.close_class, c["code"])
    assert all(join("LATE%d" % i) == 403 for i in range(limit + 1))       # closed: right code, refused
    admin_do(db, admin.reopen_class, c["code"])
    assert join("S1") == 200 and join("S2") == 200                         # now full
    assert all(join("MORE%d" % i) == 403 for i in range(limit + 1))       # full: right code, refused
    assert join("ALICE") == 200                                            # rejoin still fine
    assert all(join("X", "ZZZZZ") == 404 for _ in range(limit))           # unknown codes do count
    assert join("ALICE") == 429


def test_quiz_answer_key_is_not_served_but_the_economy_config_is(http):
    assert not server.is_public_path("/config/quiz.json")
    assert not server.is_public_path("/config/quiz.v3.json")
    assert server.is_public_path("/config/economy.v4.json")
    assert http("GET", "/config/quiz.json")[0] == 404
    assert http("GET", "/config/economy.v4.json")[0] == 200


def test_a_wrong_pin_says_so_and_never_invites_a_second_seat(db):
    """A friend with a card mistypes the PIN: the answer must point at the PIN,
    not suggest 'add an initial' - that is how a stray 'BANANA B' seat was born."""
    c = opened(db)
    A.join(dict(code=c["code"], name="BANANA", pin="2468"))
    with pytest.raises(A.ApiError) as e:
        A.join(dict(code=c["code"], name="banana", pin="2817"))
    assert e.value.status == 409
    assert "PIN" in e.value.message and "BANANA" in e.value.message
    assert "initial" not in e.value.message and "BANANA B" not in e.value.message
    assert A.join(dict(code=c["code"], name="BANANA", pin="2468"))["rejoined"]
    # and a closed class cannot grow a second seat even from a new name
    admin_do(db, admin.close_class, c["code"])
    with pytest.raises(A.ApiError) as e:
        A.join(dict(code=c["code"], name="BANANA B", pin="1111"))
    assert e.value.status == 403
