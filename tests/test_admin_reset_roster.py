"""reset: a new game, same seats. export/import: the roster survives anything."""
import json
import pathlib
import pytest
import game_api as A
import admin
from test_access_integration import db, opened, admin_do   # noqa: F401  (fixture + helpers)


def progress(db, token):
    """Crude 'played for a while' marks: cash, a display blob, a position, net worth."""
    with A.connect() as conn:
        pid = conn.execute("SELECT id FROM players WHERE token=?", (token,)).fetchone()["id"]
        conn.execute("UPDATE players SET cash=999, buildings='{\"hero\":\"x\"}', econ_nw=777 WHERE id=?", (pid,))
        conn.execute("INSERT INTO positions(player_id, symbol, shares, avg_cost) VALUES (?, 'AAPL', 2, 100)", (pid,))
        conn.execute("UPDATE sessions SET clock_accum=5000, econ_tick=333, paused=1, custom_events='[{\"x\":1}]'"
                     " WHERE code=(SELECT code FROM players WHERE id=?)", (pid,))


def test_reset_keeps_every_seat_and_code_but_starts_the_game_over(db):
    c = opened(db, label="9-B")
    alice = A.join(dict(code=c["code"], name="ALICE", pin="1234"))
    A.join(dict(code=c["code"], name="BOB", pin="2222"))
    tt = A.teacher_login({"teacher_code": c["teacher_code"]})["teacher_token"]
    progress(db, alice["token"])
    with A.connect() as conn:
        seed_before = conn.execute("SELECT class_seed FROM sessions WHERE code=?", (c["code"],)).fetchone()[0]

    assert admin.main(["--db", str(db), "reset", c["code"]]) == 1          # no --yes: nothing happens
    with A.connect() as conn:
        assert conn.execute("SELECT cash FROM players WHERE token=?", (alice["token"],)).fetchone()[0] == 999
    assert admin.main(["--db", str(db), "reset", c["code"], "--yes"]) == 0

    # the seats, PINs, tokens and codes are exactly as before
    assert A.join(dict(code=c["code"], name="ALICE", pin="1234"))["token"] == alice["token"]
    with pytest.raises(A.ApiError):
        A.join(dict(code=c["code"], name="ALICE", pin="0000"))
    assert A.teacher({"teacher_token": tt, "action": "roster"})["count"] == 2
    assert A.teacher_login({"teacher_code": c["teacher_code"]})["code"] == c["code"]
    # ...and the game is new
    st = A.econ_state({"token": [alice["token"]]})
    assert st["cash"] == 0 and st["tick"] < 5
    with A.connect() as conn:
        p = conn.execute("SELECT cash, buildings FROM players WHERE token=?", (alice["token"],)).fetchone()
        assert p["cash"] == A.STARTING_CASH and p["buildings"] == "{}"
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (c["code"],)).fetchone()
        assert (s["paused"], s["clock_accum"], s["custom_events"]) == (0, 0, "[]")
        assert json.loads(s["econ_config"]).get("version") == 4
        assert s["class_seed"] != seed_before                              # a running server drops its price book
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger WHERE code=? AND kind LIKE '%migration%'", (c["code"],))]
        assert kinds == []                                                  # a reset is not a legacy migration
    assert A.teacher({"teacher_token": tt, "action": "roster"})["roster"][0]["net_worth"] >= 0


def test_reset_all_covers_every_class(db):
    a, b = opened(db), opened(db)
    ta = A.join(dict(code=a["code"], name="AL", pin="1111"))["token"]
    tb = A.join(dict(code=b["code"], name="BO", pin="2222"))["token"]
    progress(db, ta); progress(db, tb)
    assert admin.main(["--db", str(db), "reset", "--all", "--yes"]) == 0
    with A.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT cash FROM players ORDER BY id")] == [A.STARTING_CASH] * 2
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0


def test_export_then_import_reproduces_codes_names_and_pins_in_a_new_database(db, tmp_path, monkeypatch, capsys):
    c1 = opened(db, label="Class A", size=6)
    c2 = opened(db, label="Class B", size=6)
    for name, pin in (("APPLE", "1357"), ("BANANA", "2468")):
        A.join(dict(code=c1["code"], name=name, pin=pin))
    A.join(dict(code=c2["code"], name="TIGER", pin="9753"))
    assert admin.main(["--db", str(db), "export"]) == 0
    roster = json.loads(capsys.readouterr().out)
    assert {x["code"] for x in roster["classes"]} == {c1["code"], c2["code"]}
    cls_a = next(x for x in roster["classes"] if x["code"] == c1["code"])
    assert cls_a["teacher_code"] == c1["teacher_code"] and cls_a["class_size"] == 6
    assert cls_a["seats"] == [{"name": "APPLE", "pin": "1357"}, {"name": "BANANA", "pin": "2468"}]
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(roster))

    # the disk was lost: a brand-new database
    fresh = tmp_path / "fresh.db"
    monkeypatch.setattr(A, "DB_PATH", fresh)
    A.init_db()
    assert admin.main(["--db", str(fresh), "import", str(path)]) == 0
    out = capsys.readouterr().out
    assert "created" in out and "2 new" in out
    # same codes, same teacher codes, same PINs - and playable at once
    assert A.teacher_login({"teacher_code": c1["teacher_code"]})["code"] == c1["code"]
    j = A.join(dict(code=c1["code"], name="APPLE", pin="1357"))
    assert j["rejoined"] and "cash" in A.econ_state({"token": [j["token"]]})
    with pytest.raises(A.ApiError):
        A.join(dict(code=c1["code"], name="APPLE", pin="0000"))
    with A.connect() as conn:
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM ledger WHERE kind LIKE '%migration%'")]
        assert kinds == []
    # a second import changes nothing; a changed PIN in the file is applied
    assert admin.main(["--db", str(fresh), "import", str(path)]) == 0
    assert "0 new" in capsys.readouterr().out
    cls_a["seats"][0]["pin"] = "1111"
    path.write_text(json.dumps(roster))
    assert admin.main(["--db", str(fresh), "import", str(path)]) == 0
    assert A.join(dict(code=c1["code"], name="APPLE", pin="1111"))["rejoined"]
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 3


def test_import_refuses_bad_codes_and_clashing_teacher_codes(db, tmp_path):
    c = opened(db)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"classes": [{"code": "ab", "teacher_code": "X", "seats": []}]}))
    assert admin.main(["--db", str(db), "import", str(bad)]) == 1
    clash = tmp_path / "clash.json"
    clash.write_text(json.dumps({"classes": [{"code": "NEWCL", "teacher_code": c["teacher_code"], "seats": []}]}))
    assert admin.main(["--db", str(db), "import", str(clash)]) == 1
    badpin = tmp_path / "pin.json"
    badpin.write_text(json.dumps({"classes": [{"code": "NEWCL", "teacher_code": "TCODE1", "seats": [{"name": "X", "pin": "12"}]}]}))
    assert admin.main(["--db", str(db), "import", str(badpin)]) == 1


def test_roster_files_can_never_reach_the_repository():
    ignore = (pathlib.Path(__file__).resolve().parent.parent / ".gitignore").read_text().split()
    assert "roster*.json" in ignore
