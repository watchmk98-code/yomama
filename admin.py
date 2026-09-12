#!/usr/bin/env python3
"""Provisioning for the class server. Developer only.

    python3 admin.py open --label "9-B" --size 30
    python3 admin.py list
    python3 admin.py roster KRT39
    python3 admin.py close KRT39         # stop new students; the joined ones keep playing
    python3 admin.py reopen KRT39
    python3 admin.py revoke KRT39        # kill switch: nobody in the class can play
    python3 admin.py restore KRT39
    python3 admin.py kick KRT39 "ALEX K"
    python3 admin.py rotate KRT39        # new teacher code; the old one stops working
    python3 admin.py resize KRT39 40     # seats, the teacher's own included

Classes are created here and nowhere else: no page and no endpoint can do it.
`open` prints two codes. Students type the class code into join.html with a
name and a 4-digit PIN. The teacher types the teacher code into class.html,
which opens the console for that one class and nothing more.

The database is $YOMAMA_DB, else ./game.db (or --db). On Render, run these
from the service's Shell tab. Start the server once before the first `open`:
it creates the tables. Put --json before the command for machine-readable
output.

This file does not import game_api on purpose. Provisioning has to keep
working while the economy is being reworked, and must not need the economy
config to load. The columns it needs are added here with the same idempotent
pattern game_api.MIGRATIONS uses; access.py reads them.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Same alphabet as game_api.new_code: nothing that reads as something else.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CLASS_CODE_LEN = 5
TEACHER_CODE_LEN = 6

# Added to the schema game_api.py creates. Absent on a database from before
# admin.py existed; access.py treats a missing column as "allowed".
ADMIN_COLUMNS = (
    ("sessions", "teacher_code", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "joins_open",   "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "active",       "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "label",        "TEXT NOT NULL DEFAULT ''"),
)


class AdminError(Exception):
    pass


class tx:
    """Write transaction that takes the lock up front, as game_api.connect does."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def default_db_path() -> Path:
    return Path(os.environ.get("YOMAMA_DB") or ROOT / "game.db").expanduser()


def connect(db_path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if not db_path.exists():
        raise AdminError(f"no database at {db_path} - start the server once, it creates one")
    conn = sqlite3.connect(str(db_path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # same mode as game_api; never fight over it
    ensure_schema(conn)
    return conn


def ensure_schema(conn) -> None:
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"sessions", "players", "ledger"} <= tables:
        raise AdminError("the database has no tables yet - start the server once, it creates them")
    with tx(conn):
        for table, column, decl in ADMIN_COLUMNS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_teacher_code"
            " ON sessions(teacher_code) WHERE teacher_code != ''"
        )


def new_code(conn, column: str, length: int) -> str:
    for _ in range(50):
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if conn.execute(f"SELECT 1 FROM sessions WHERE {column}=?", (code,)).fetchone() is None:
            return code
    raise AdminError("could not allocate a fresh code")


def log(conn, code, kind, detail, player_id=None) -> None:
    conn.execute(
        "INSERT INTO ledger(code, player_id, at, kind, detail) VALUES (?,?,?,?,?)",
        (code, player_id, time.time(), kind, json.dumps(detail)),
    )


def session_of(conn, code: str) -> sqlite3.Row:
    s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
    if s is None:
        raise AdminError(f"no class with code {code}")
    return s


def norm_code(value) -> str:
    return "".join(str(value or "").split()).upper()


def norm_name(value) -> str:
    return " ".join(str(value or "").split())[:24].upper()     # as game_api.join does


# --------------------------------------------------------------- commands ---

def open_class(conn, label: str = "", size: int = 30) -> dict:
    """A new class. econ_config stays empty so the server uses its current config."""
    now = time.time()
    size = max(1, min(200, int(size or 30)))
    label = " ".join(str(label or "").split())[:40]
    with tx(conn):
        code = new_code(conn, "code", CLASS_CODE_LEN)
        teacher_code = new_code(conn, "teacher_code", TEACHER_CODE_LEN)
        conn.execute(
            "INSERT INTO sessions(code, teacher_token, seed, created_at, paused, clock_base,"
            " clock_accum, class_size, class_seed, started_at, teacher_code, label)"
            " VALUES (?,?,?,?,0,?,0,?,?,?,?,?)",
            (code, secrets.token_urlsafe(24), secrets.randbelow(1 << 30), now, now, size,
             1 + secrets.randbelow((1 << 30) - 1), now, teacher_code, label),
        )
        log(conn, code, "admin_open_class", {"label": label, "class_size": size})
    return {"code": code, "teacher_code": teacher_code, "label": label, "class_size": size}


def list_classes(conn) -> list:
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM players p WHERE p.code = s.code) AS players"
        " FROM sessions s ORDER BY s.created_at DESC"
    ).fetchall()
    return [
        {"code": r["code"], "label": r["label"], "teacher_code": r["teacher_code"],
         "class_size": int(r["class_size"]), "players": int(r["players"]),
         "paused": bool(r["paused"]), "joins_open": bool(r["joins_open"]),
         "active": bool(r["active"]), "created_at": float(r["created_at"])}
        for r in rows
    ]


def roster(conn, code: str) -> list:
    session_of(conn, code)
    rows = conn.execute(
        "SELECT name, econ_nw, joined_at FROM players WHERE code=? ORDER BY econ_nw DESC, name",
        (code,),
    ).fetchall()
    return [{"rank": i + 1, "name": r["name"], "net_worth": int(r["econ_nw"]),
             "joined_at": float(r["joined_at"])} for i, r in enumerate(rows)]


def _set_flag(conn, code: str, column: str, value: int, kind: str) -> dict:
    with tx(conn):
        session_of(conn, code)
        conn.execute(f"UPDATE sessions SET {column}=? WHERE code=?", (int(value), code))
        log(conn, code, kind, {column: int(value)})
    return {"code": code, column: bool(value)}


def close_class(conn, code):   return _set_flag(conn, code, "joins_open", 0, "admin_close")
def reopen_class(conn, code):  return _set_flag(conn, code, "joins_open", 1, "admin_reopen")
def revoke_class(conn, code):  return _set_flag(conn, code, "active", 0, "admin_revoke")
def restore_class(conn, code): return _set_flag(conn, code, "active", 1, "admin_restore")


def kick(conn, code: str, name: str) -> dict:
    """Free a seat. The token dies with the row, so their browser is signed out."""
    name = norm_name(name)
    with tx(conn):
        session_of(conn, code)
        p = conn.execute("SELECT id FROM players WHERE code=? AND name=?", (code, name)).fetchone()
        if p is None:
            raise AdminError(f"no student {name!r} in class {code}")
        conn.execute("DELETE FROM positions WHERE player_id=?", (p["id"],))
        conn.execute("DELETE FROM players WHERE id=?", (p["id"],))
        log(conn, code, "admin_kick", {"name": name}, player_id=p["id"])
    return {"code": code, "name": name, "kicked": True}


def resize(conn, code: str, size: int) -> dict:
    """Seats, the teacher's own included. join() refuses the next student."""
    size = max(1, min(200, int(size or 30)))
    with tx(conn):
        session_of(conn, code)
        conn.execute("UPDATE sessions SET class_size=? WHERE code=?", (size, code))
        log(conn, code, "admin_resize", {"class_size": size})
    return {"code": code, "class_size": size}


def rotate(conn, code: str) -> dict:
    with tx(conn):
        session_of(conn, code)
        teacher_code = new_code(conn, "teacher_code", TEACHER_CODE_LEN)
        # A new long token too, so a console still holding the old one is out.
        conn.execute("UPDATE sessions SET teacher_code=?, teacher_token=? WHERE code=?",
                     (teacher_code, secrets.token_urlsafe(24), code))
        log(conn, code, "admin_rotate_teacher_code", {})
    return {"code": code, "teacher_code": teacher_code}


# ---------------------------------------------------------------- output ---

def when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def print_open(d: dict) -> None:
    seats = f"{d['class_size']} seats"
    print(f"Opened class {d['code']}  ({d['label'] + ', ' if d['label'] else ''}{seats})")
    print()
    print(f"  STUDENTS  join.html   class code   {d['code']}    + their name + a 4-digit PIN")
    print(f"  TEACHER   class.html  teacher code {d['teacher_code']}   (console for this class only)")


def print_list(rows: list) -> None:
    if not rows:
        print('no classes yet - python3 admin.py open --label "9-B"')
        return
    print(f"{'CODE':6} {'TEACHER':8} {'PLAYERS':>8}  {'STATE':16} {'OPENED':16} LABEL")
    for r in rows:
        state = ("REVOKED" if not r["active"] else "closed to joins" if not r["joins_open"]
                 else "paused" if r["paused"] else "open")
        print(f"{r['code']:6} {r['teacher_code']:8} {r['players']:>4}/{r['class_size']:<3} "
              f" {state:16} {when(r['created_at']):16} {r['label']}")


def print_roster(code: str, rows: list) -> None:
    if not rows:
        print(f"nobody has joined {code} yet")
        return
    print(f"{'#':>3}  {'NAME':24} {'NET WORTH':>10}  JOINED")
    for r in rows:
        print(f"{r['rank']:>3}  {r['name']:24} {r['net_worth']:>10,}  {when(r['joined_at'])}")


# ------------------------------------------------------------------- cli ---

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="admin.py", description="Provisioning for the class server. Developer only.",
        epilog=__doc__.split("\n\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", help="SQLite file (default: $YOMAMA_DB or ./game.db)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("open", help="open a new class; prints its two codes")
    o.add_argument("--label", default="", help='e.g. "9-B" or "Ms. Yilmaz", for your own list')
    o.add_argument("--size", type=int, default=30,
                   help="seats, the teacher's own included (1-200, default 30); the next student is refused")
    sub.add_parser("list", help="every class with its state")
    for name, help_ in (("roster", "who has joined a class"),
                        ("close", "stop new students joining"),
                        ("reopen", "take new students again"),
                        ("revoke", "kill switch: nobody in the class can play"),
                        ("restore", "undo revoke"),
                        ("rotate", "new teacher code (and token); the old ones stop working")):
        sub.add_parser(name, help=help_).add_argument("code")
    k = sub.add_parser("kick", help="remove a student; frees the seat")
    k.add_argument("code")
    k.add_argument("name")
    r = sub.add_parser("resize", help="change the number of seats (the teacher's own included)")
    r.add_argument("code")
    r.add_argument("size", type=int)
    return p


def run(conn, args) -> object:
    code = norm_code(getattr(args, "code", ""))
    if args.command == "open":
        out = open_class(conn, args.label, args.size)
        if not args.json:
            print_open(out)
    elif args.command == "list":
        out = list_classes(conn)
        if not args.json:
            print_list(out)
    elif args.command == "roster":
        out = roster(conn, code)
        if not args.json:
            print_roster(code, out)
    else:
        fn = {"close": close_class, "reopen": reopen_class, "revoke": revoke_class,
              "restore": restore_class, "rotate": rotate}.get(args.command)
        if args.command == "kick":
            out = kick(conn, code, args.name)
        elif args.command == "resize":
            out = resize(conn, code, args.size)
        else:
            out = fn(conn, code)
        if not args.json:
            print(json.dumps(out))
    return out


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        conn = connect(Path(args.db) if args.db else default_db_path())
        try:
            out = run(conn, args)
        finally:
            conn.close()
    except AdminError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
