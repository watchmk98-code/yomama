"""The standings behind the LEAD page: every seat by net worth, plus each
seat's gain today / this week / this month from the opening figure the
server keeps per day. Net worth itself comes from the engine on every read,
so the tests plant openings, never figures."""
import time
import game_api as A
import admin
from test_access_integration import db, opened, admin_do   # noqa: F401  (fixture + helpers)


def opening(token, days_ago, nw):
    with A.connect() as conn:
        pid = conn.execute("SELECT id FROM players WHERE token=?", (token,)).fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO standings(player_id, day, net_worth) VALUES (?,?,?)",
                     (pid, int(time.time() // 86400) - days_ago, nw))


def row(token, name):
    return next(r for r in A.get_state({"token": [token]})["leaderboard"] if r["name"] == name)


def test_every_seat_by_net_worth_with_real_gains(db):
    c = opened(db)
    a = A.join(dict(code=c["code"], name="ALICE", pin="1111"))["token"]
    b = A.join(dict(code=c["code"], name="BOB", pin="2222"))["token"]
    board = A.get_state({"token": [a]})["leaderboard"]          # the first look fixes today's openings
    assert [(r["rank"], r["name"], r["you"]) for r in board] == [(1, "ALICE", True), (2, "BOB", False)]
    assert all(r["gain"] == {"daily": 0, "weekly": 0, "monthly": 0} for r in board)
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM standings").fetchone()[0] == 2
    nw = row(a, "ALICE")["net_worth"]
    opening(a, 0, nw - 1000)
    opening(a, 6, nw - 4000)
    opening(a, 29, nw - 4500)
    assert row(a, "ALICE")["gain"] == {"daily": 1000, "weekly": 4000, "monthly": 4500}
    assert row(a, "BOB")["gain"] == {"daily": 0, "weekly": 0, "monthly": 0}
    # a seat whose only opening is today's: this week's and month's gain are today's
    opening(b, 0, row(b, "BOB")["net_worth"] - 700)
    assert row(b, "BOB")["gain"] == {"daily": 700, "weekly": 700, "monthly": 700}


def test_a_reset_starts_the_gains_over(db):
    c = opened(db)
    a = A.join(dict(code=c["code"], name="ALICE", pin="1111"))["token"]
    opening(a, 3, row(a, "ALICE")["net_worth"] - 800)
    assert row(a, "ALICE")["gain"]["weekly"] == 800
    assert admin.main(["--db", str(db), "reset", c["code"], "--yes"]) == 0
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM standings").fetchone()[0] == 1   # today's fresh opening only
    assert row(a, "ALICE")["gain"] == {"daily": 0, "weekly": 0, "monthly": 0}
