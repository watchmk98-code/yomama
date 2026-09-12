"""advance: the class jumps ahead in game time and every town is simulated,
nothing is wiped, nobody is signed out."""
import json
import time
import pytest
import game_api as A
import admin
import production_economy as economy
from test_access_integration import db, opened, admin_do   # noqa: F401  (fixture + helpers)

DAY = 86400


def seats(code, *names):
    return {n: A.join(dict(code=code, name=n, pin="1234"))["token"] for n in names}


def state(token):
    return A.econ_state({"token": [token]})


def session(code):
    with A.connect() as conn:
        return conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()


def report(token):
    with A.connect() as conn:
        row = conn.execute("SELECT econ_meta FROM players WHERE token=?", (token,)).fetchone()
    return json.loads(row["econ_meta"])["report"]


def test_advance_moves_the_class_a_day_ahead_and_simulates_every_town(db):
    cfg = economy.load_config()
    per_day = economy.ticks_per_day(cfg)
    c = opened(db, label="9-B")
    t = seats(c["code"], "ALICE", "BOB")
    tt = A.teacher_login({"teacher_code": c["teacher_code"]})["teacher_token"]
    A.econ_login({"token": t["ALICE"]})          # ALICE has been here; BOB never came back
    tick0 = state(t["ALICE"])["tick"]
    clock0 = session(c["code"])["clock_accum"]

    # without --yes nothing happens
    assert admin.main(["--db", str(db), "advance", c["code"], "--days", "1"]) == 1
    assert state(t["ALICE"])["tick"] - tick0 < 10
    assert admin.main(["--db", str(db), "advance"]) == 1                    # no class named

    started = time.time()
    assert admin.main(["--db", str(db), "advance", c["code"], "--days", "1", "--yes"]) == 0
    assert time.time() - started < 30

    s = session(c["code"])
    assert DAY <= s["clock_accum"] - clock0 < DAY + 60
    assert s["econ_tick"] >= tick0 + per_day
    for name, token in t.items():
        st = state(token)
        assert per_day <= st["tick"] - tick0 < per_day + 10, name
        r = report(token)
        # a whole day longer than the 12 h offline allowance, and nothing skipped
        assert r["offlineTicksSkipped"] == 0, name
        assert r["produced"] > 0 and r["unitsProduced"] > 0, name
        assert st["netWorth"] > 0

    # seats, PINs, tokens and the teacher console are untouched
    assert A.join(dict(code=c["code"], name="ALICE", pin="1234"))["token"] == t["ALICE"]
    with pytest.raises(A.ApiError):
        A.join(dict(code=c["code"], name="ALICE", pin="0000"))
    roster = A.teacher({"teacher_token": tt, "action": "roster"})
    assert roster["count"] == 2 and roster["minute"] >= DAY // 60
    # ...and the next visit shows the whole stretch as time away
    login = A.econ_login({"token": t["ALICE"]})
    assert login["overnightReport"] is not None
    assert login["overnightReport"]["produced"] > 0
    with A.connect() as conn:
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger WHERE code=?", (c["code"],))]
    assert "admin_advance_clock" in kinds


def test_advance_keeps_a_paused_class_paused_and_still_moves_it(db):
    c = opened(db)
    t = seats(c["code"], "ALICE")
    tt = A.teacher_login({"teacher_code": c["teacher_code"]})["teacher_token"]
    A.teacher({"teacher_token": tt, "action": "pause"})
    tick0 = state(t["ALICE"])["tick"]
    assert admin.main(["--db", str(db), "advance", c["code"], "--hours", "3", "--yes"]) == 0
    s = session(c["code"])
    assert s["paused"] == 1
    per_hour = economy.ticks_per_hour(economy.load_config())
    assert 3 * per_hour <= state(t["ALICE"])["tick"] - tick0 < 3 * per_hour + 2
    assert report(t["ALICE"])["offlineTicksSkipped"] == 0


def test_random_hours_are_drawn_per_class_within_bounds(db, capsys):
    a, b = opened(db, label="A"), opened(db, label="B")
    seats(a["code"], "ALICE"); seats(b["code"], "BOB")
    assert admin.main(["--db", str(db), "--json", "advance", a["code"], b["code"],
                       "--hours", "1", "--random-hours", "2", "--yes"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["code"] for r in out] == [a["code"], b["code"]]
    for r in out:
        assert 3600 <= r["seconds"] <= 3 * 3600
        assert r["tick_after"] > r["tick_before"]
        assert r["players"] and all(p["after"] >= 0 for p in r["players"])
    # a jump of zero is refused, so is a negative one
    assert admin.main(["--db", str(db), "advance", a["code"], "--yes"]) == 1
    assert admin.main(["--db", str(db), "advance", a["code"], "--days", "-1", "--yes"]) == 1


def test_all_means_every_active_class(db):
    live, dead = opened(db, label="live"), opened(db, label="dead")
    seats(live["code"], "ALICE"); seats(dead["code"], "BOB")
    admin_do(db, admin.revoke_class, dead["code"])
    assert admin.main(["--db", str(db), "advance", "--all", "--hours", "1", "--yes"]) == 0
    assert session(live["code"])["clock_accum"] >= 3600
    assert session(dead["code"])["clock_accum"] < 60


def test_advance_class_clock_refuses_nonsense(db):
    with pytest.raises(A.ApiError):
        A.advance_class_clock("NOPE", 3600)
    c = opened(db)
    for bad in (0, -5, float("nan"), float("inf")):
        with pytest.raises(A.ApiError):
            A.advance_class_clock(c["code"], bad)


def town(token):
    with A.connect() as conn:
        row = conn.execute("SELECT econ FROM players WHERE token=?", (token,)).fetchone()
    return json.loads(row["econ"])


def test_without_play_nobody_buys_anything(db):
    c = opened(db)
    t = seats(c["code"], "ALICE", "BOB")
    assert admin.main(["--db", str(db), "advance", c["code"], "--days", "2", "--yes"]) == 0
    for token in t.values():
        st = town(token)
        assert len(st["b"]) == 1 and st["b"][0]["lv"] == 1 and not st["queue"] and st["build"] is None
        assert st["customerContracts"]["active"] == []


def test_play_makes_every_town_grow_and_differ(db, capsys):
    c = opened(db, label="9-B")
    t = seats(c["code"], "ALICE", "BOB", "CARA", "DAN", "EVE")
    assert admin.main(["--db", str(db), "--json", "advance", c["code"], "--days", "3", "--play", "--yes"]) == 0
    out = json.loads(capsys.readouterr().out)[0]
    assert out["play"] is True
    shapes = set()
    for name, token in t.items():
        st = town(token)
        levels = sum(b["lv"] + b["sales"] + b["storage"] for b in st["b"])
        assert len(st["b"]) >= 2, name                                  # bought businesses
        assert levels > 3 * len(st["b"]), name                          # and upgrades
        assert st["report"]["offlineTicksSkipped"] == 0 if "report" in st else True
        assert not st["checklist"].get("quiz"), name                    # the quiz is never taken for anyone
        assert st["cash"] >= 0 and st["book"] > 0
        shapes.add((len(st["b"]), levels, len(st["customerContracts"]["active"])))
        row = next(p for p in out["players"] if p["name"] == name)
        assert row["played"]["visits"] > 0 and row["played"]["builds"] + row["played"]["upgrades"] > 0
        assert row["buildings"] >= 2
    assert len(shapes) > 1                                              # personalities differ
    assert all(report(tok)["offlineTicksSkipped"] == 0 for tok in t.values())
    # the seats are untouched and the next visit still shows the time away
    assert A.join(dict(code=c["code"], name="ALICE", pin="1234"))["token"] == t["ALICE"]
    assert A.econ_login({"token": t["ALICE"]})["overnightReport"] is not None


def test_the_stand_in_is_deterministic_per_seat():
    cfg = economy.load_config()
    a = economy.new_state(cfg, 0, seed=5); a["cash"] = 20000
    b = economy.new_state(cfg, 0, seed=5); b["cash"] = 20000
    import autopilot
    for when in (0, 960, 1920):
        ra = autopilot.visit(cfg, a, 42, when)
        rb = autopilot.visit(cfg, b, 42, when)
        assert ra == rb
    assert a == b
    assert len(a["b"]) + len(a["queue"]) + bool(a["build"]) > 1 or sum(x["lv"] for x in a["b"]) > 1
