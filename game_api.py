#!/usr/bin/env python3
"""Classroom game backend for YOMAMA INVESTMENTS.

Owns everything that is shared or scored: market prices, market stock,
player cash, product inventory, stock positions, and the leaderboard.
Buildings and production timers stay client-side.

Design notes:
  * Market stock decays toward a neutral level continuously ("outside demand"),
    computed lazily from elapsed time. No background thread, no cron.
  * Product price is a function of that stock, so 30 students selling into the
    same book genuinely move the price for each other.
  * Equity prices are a deterministic function of (session seed, minute), so a
    class is reproducible and needs no internet connection.
"""

from __future__ import annotations

import json
import math
import secrets
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "game.db"

_db_lock = threading.Lock()

# ---------------------------------------------------------------- config ---

# base = midpoint of the original fixed buy/sell pair in marketplace.js.
# neutral = the old marketStartStock; capacity = the old marketCap.
PRODUCTS = {
    "hydro_lettuce_crate": {"name": "Hydro Lettuce Crate", "base": 22.3, "neutral": 140, "capacity": 220},
    "canned_bean_pack":    {"name": "Canned Bean Pack",    "base": 8.0,  "neutral": 120, "capacity": 200},
    "bio_fuel_cell":       {"name": "Bio Fuel Cell",       "base": 58.0, "neutral": 55,  "capacity": 90},
    "copper_tool_set":     {"name": "Copper Tool Set",     "base": 35.0, "neutral": 80,  "capacity": 130},
    "sensor_chip_batch":   {"name": "Sensor Chip Batch",   "base": 79.5, "neutral": 42,  "capacity": 70},
}

ELASTICITY = 0.60     # how hard price reacts to stock imbalance
PRICE_FLOOR = 0.45    # clamp as a multiple of base
PRICE_CEIL = 1.90
SPREAD = 0.10         # bid/ask spread around mid
DEMAND_HALF_LIFE_S = 120.0   # stock returns halfway to neutral in this long

STARTING_CASH = 2500.0
DEPOSIT_BASE = 400          # starting production allowance, in units
DEPOSIT_PER_HOUR = 120      # generous vs real output; blocks bulk cheating

EQUITIES = {
    "AAPL": {"name": "Apple",     "base": 185.0, "vol": 0.018, "drift": 0.0006},
    "MSFT": {"name": "Microsoft", "base": 402.0, "vol": 0.015, "drift": 0.0008},
    "NVDA": {"name": "NVIDIA",    "base": 118.0, "vol": 0.038, "drift": 0.0012},
    "SPY":  {"name": "S&P 500",   "base": 512.0, "vol": 0.009, "drift": 0.0005},
    "TSLA": {"name": "Tesla",     "base": 242.0, "vol": 0.034, "drift": 0.0000},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    code          TEXT PRIMARY KEY,
    teacher_token TEXT NOT NULL,
    seed          INTEGER NOT NULL,
    created_at    REAL NOT NULL,
    paused        INTEGER NOT NULL DEFAULT 0,
    clock_base    REAL NOT NULL,
    clock_accum   REAL NOT NULL DEFAULT 0,
    class_size    INTEGER NOT NULL DEFAULT 30
);
CREATE TABLE IF NOT EXISTS players (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    name       TEXT NOT NULL,
    token      TEXT NOT NULL UNIQUE,
    joined_at  REAL NOT NULL,
    cash       REAL NOT NULL,
    buildings  TEXT NOT NULL DEFAULT '{}',
    UNIQUE(code, name)
);
CREATE TABLE IF NOT EXISTS inventory (
    player_id  INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    qty        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, product_id)
);
CREATE TABLE IF NOT EXISTS positions (
    player_id INTEGER NOT NULL,
    symbol    TEXT NOT NULL,
    shares    REAL NOT NULL DEFAULT 0,
    avg_cost  REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, symbol)
);
CREATE TABLE IF NOT EXISTS market (
    code       TEXT NOT NULL,
    product_id TEXT NOT NULL,
    stock      REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (code, product_id)
);
CREATE TABLE IF NOT EXISTS deposits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    qty        INTEGER NOT NULL,
    at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deposits_player ON deposits(player_id);
CREATE TABLE IF NOT EXISTS ledger (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code      TEXT NOT NULL,
    player_id INTEGER,
    at        REAL NOT NULL,
    kind      TEXT NOT NULL,
    detail    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_code ON ledger(code, at);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# ------------------------------------------------------------- economics ---

def decay_stock(stock: float, neutral: float, elapsed_s: float) -> float:
    """Outside demand pulls stock back toward neutral exponentially."""
    if elapsed_s <= 0:
        return stock
    k = math.pow(0.5, elapsed_s / DEMAND_HALF_LIFE_S)
    return neutral + (stock - neutral) * k


def depth(product_id: str, class_size: int) -> tuple:
    """Market depth scales with the class: 30 students need ~30x the book of one.

    Keeps a single student's sale a small nudge (~1%) while the whole class
    selling at once moves the price 25-40% - which is the lesson.
    """
    cfg = PRODUCTS[product_id]
    scale = max(1, int(class_size))
    return float(cfg["neutral"]) * scale, float(cfg["capacity"]) * scale


def price_for(product_id: str, stock: float, class_size: int = 1) -> dict:
    cfg = PRODUCTS[product_id]
    neutral, _cap = depth(product_id, class_size)
    imbalance = (neutral - stock) / neutral
    mult = 1.0 + ELASTICITY * imbalance
    mult = max(PRICE_FLOOR, min(PRICE_CEIL, mult))
    mid = cfg["base"] * mult
    return {
        "mid": round(mid, 2),
        "buy": round(mid * (1 + SPREAD / 2), 2),
        "sell": round(mid * (1 - SPREAD / 2), 2),
        "change_pct": round((mult - 1.0) * 100, 1),
    }


def equity_price(symbol: str, seed: int, minute: int) -> float:
    """Deterministic pseudo-random walk. Same seed+minute always same price."""
    cfg = EQUITIES[symbol]
    price = cfg["base"]
    h = (seed * 2654435761 + sum(ord(c) for c in symbol) * 40503) & 0xFFFFFFFF
    for i in range(minute + 1):
        h = (h * 1103515245 + 12345) & 0x7FFFFFFF
        u = ((h >> 8) / 8388608.0) - 1.0          # roughly [-1, 1]
        price *= math.exp(cfg["drift"] * 0.1 + cfg["vol"] * u * 0.5)
        price = max(cfg["base"] * 0.25, min(cfg["base"] * 4.0, price))
    return round(price, 2)


def session_minute(row: sqlite3.Row) -> int:
    """Elapsed game minutes, excluding paused time."""
    accum = float(row["clock_accum"])
    if not row["paused"]:
        accum += time.time() - float(row["clock_base"])
    return int(accum // 60)


# -------------------------------------------------------------- helpers ----

def class_size_of(conn, code: str) -> int:
    row = conn.execute("SELECT class_size FROM sessions WHERE code=?", (code,)).fetchone()
    return max(1, int(row["class_size"])) if row else 1


def _market_row(conn, code: str, product_id: str, class_size: int = None) -> float:
    now = time.time()
    if class_size is None:
        class_size = class_size_of(conn, code)
    row = conn.execute(
        "SELECT stock, updated_at FROM market WHERE code=? AND product_id=?",
        (code, product_id),
    ).fetchone()
    neutral, _cap = depth(product_id, class_size)
    if row is None:
        conn.execute(
            "INSERT INTO market(code, product_id, stock, updated_at) VALUES (?,?,?,?)",
            (code, product_id, neutral, now),
        )
        return neutral
    fresh = decay_stock(float(row["stock"]), neutral, now - float(row["updated_at"]))
    conn.execute(
        "UPDATE market SET stock=?, updated_at=? WHERE code=? AND product_id=?",
        (fresh, now, code, product_id),
    )
    return fresh


def _log(conn, code, player_id, kind, detail):
    conn.execute(
        "INSERT INTO ledger(code, player_id, at, kind, detail) VALUES (?,?,?,?,?)",
        (code, player_id, time.time(), kind, json.dumps(detail)),
    )


def _player_by_token(conn, token: str):
    return conn.execute("SELECT * FROM players WHERE token=?", (token or "",)).fetchone()


def _net_worth(conn, player, minute: int, seed: int, class_size: int = 1) -> float:
    total = float(player["cash"])
    for r in conn.execute("SELECT product_id, qty FROM inventory WHERE player_id=?", (player["id"],)):
        pid = r["product_id"]
        if pid in PRODUCTS and r["qty"]:
            stock = _market_row(conn, player["code"], pid, class_size)
            total += price_for(pid, stock, class_size)["sell"] * int(r["qty"])
    for r in conn.execute("SELECT symbol, shares FROM positions WHERE player_id=?", (player["id"],)):
        if r["symbol"] in EQUITIES and r["shares"]:
            total += equity_price(r["symbol"], seed, minute) * float(r["shares"])
    return round(total, 2)


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1
    return "".join(secrets.choice(alphabet) for _ in range(5))


# ------------------------------------------------------------- endpoints ---
# Every handler returns (status_code, dict). Raises nothing to the caller.

class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def create_session(body) -> dict:
    """Teacher starts a class. Returns the code to project on the board."""
    now = time.time()
    with _db_lock, connect() as conn:
        for _ in range(20):
            code = new_code()
            if conn.execute("SELECT 1 FROM sessions WHERE code=?", (code,)).fetchone() is None:
                break
        else:
            raise ApiError("could not allocate a session code", 500)
        teacher_token = secrets.token_urlsafe(24)
        class_size = max(1, min(200, int(body.get("class_size", 30) or 30)))
        conn.execute(
            "INSERT INTO sessions(code, teacher_token, seed, created_at, paused, clock_base, clock_accum, class_size)"
            " VALUES (?,?,?,?,0,?,0,?)",
            (code, teacher_token, secrets.randbelow(1 << 30), now, now, class_size),
        )
        for pid in PRODUCTS:
            _market_row(conn, code, pid, class_size)
        _log(conn, code, None, "session_created", {})
    return {"code": code, "teacher_token": teacher_token, "class_size": class_size}


def join(body) -> dict:
    """Student joins with the class code and a display name. No password."""
    code = str(body.get("code", "")).strip().upper()
    name = " ".join(str(body.get("name", "")).split())[:24].upper()
    if not code or not name:
        raise ApiError("class code and name are required")
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            raise ApiError("no class with that code", 404)
        existing = conn.execute("SELECT * FROM players WHERE code=? AND name=?", (code, name)).fetchone()
        if existing is not None:
            # Rejoin: same name in the same class returns the same seat.
            return {"token": existing["token"], "name": name, "code": code, "rejoined": True}
        token = secrets.token_urlsafe(24)
        cur = conn.execute(
            "INSERT INTO players(code, name, token, joined_at, cash) VALUES (?,?,?,?,?)",
            (code, name, token, time.time(), STARTING_CASH),
        )
        _log(conn, code, cur.lastrowid, "join", {"name": name})
    return {"token": token, "name": name, "code": code, "rejoined": False}


def get_state(query) -> dict:
    """Everything a student's page needs in one round trip."""
    token = (query.get("token") or [""])[0]
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (p["code"],)).fetchone()
        if s is None:
            raise ApiError("class no longer exists", 404)
        minute = session_minute(s)
        seed = int(s["seed"])

        class_size = max(1, int(s["class_size"]))
        market = []
        for pid, cfg in PRODUCTS.items():
            stock = _market_row(conn, p["code"], pid, class_size)
            pr = price_for(pid, stock, class_size)
            neutral, cap = depth(pid, class_size)
            market.append({
                "id": pid, "name": cfg["name"],
                "stock": round(stock, 1), "capacity": int(cap), "neutral": int(neutral),
                "space": max(0, int(cap - stock)),
                **pr,
            })

        inv = {r["product_id"]: int(r["qty"]) for r in
               conn.execute("SELECT product_id, qty FROM inventory WHERE player_id=?", (p["id"],))}

        equities = [{"symbol": sym, "name": cfg["name"], "price": equity_price(sym, seed, minute)}
                    for sym, cfg in EQUITIES.items()]

        pos = []
        for r in conn.execute("SELECT symbol, shares, avg_cost FROM positions WHERE player_id=? AND shares>0",
                              (p["id"],)):
            price = equity_price(r["symbol"], seed, minute)
            shares = float(r["shares"])
            pos.append({
                "symbol": r["symbol"], "shares": shares, "avg_cost": round(float(r["avg_cost"]), 2),
                "price": price, "value": round(price * shares, 2),
                "pnl": round((price - float(r["avg_cost"])) * shares, 2),
            })

        board = []
        for row in conn.execute("SELECT * FROM players WHERE code=?", (p["code"],)):
            board.append({"name": row["name"], "net_worth": _net_worth(conn, row, minute, seed, class_size),
                          "you": row["id"] == p["id"]})
        board.sort(key=lambda x: -x["net_worth"])
        for i, entry in enumerate(board):
            entry["rank"] = i + 1

        return {
            "player": {"name": p["name"], "cash": round(float(p["cash"]), 2),
                       "net_worth": _net_worth(conn, p, minute, seed, class_size)},
            "session": {"code": p["code"], "minute": minute, "paused": bool(s["paused"])},
            "inventory": inv, "market": market,
            "equities": equities, "positions": pos,
            "leaderboard": board,
        }


def _require_open(conn, code):
    s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
    if s is None:
        raise ApiError("class no longer exists", 404)
    if s["paused"]:
        raise ApiError("the class is paused", 409)
    return s


def trade_product(body) -> dict:
    """Sell produced goods into, or buy them back from, the shared market."""
    token = str(body.get("token", ""))
    pid = str(body.get("product_id", ""))
    side = str(body.get("side", "")).lower()
    qty = int(body.get("qty", 0))
    if pid not in PRODUCTS:
        raise ApiError("unknown product")
    if side not in ("buy", "sell"):
        raise ApiError("side must be buy or sell")
    if qty <= 0 or qty > 10000:
        raise ApiError("quantity out of range")

    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        sess = _require_open(conn, p["code"])
        class_size = max(1, int(sess["class_size"]))
        stock = _market_row(conn, p["code"], pid, class_size)
        _neutral, cap = depth(pid, class_size)
        cash = float(p["cash"])
        held = conn.execute("SELECT qty FROM inventory WHERE player_id=? AND product_id=?",
                            (p["id"], pid)).fetchone()
        held = int(held["qty"]) if held else 0

        # Fill unit by unit so a large order walks the price — the supply/demand lesson.
        filled = 0
        proceeds = 0.0
        for _ in range(qty):
            pr = price_for(pid, stock, class_size)
            if side == "sell":
                if held - filled <= 0 or stock >= cap:
                    break
                proceeds += pr["sell"]
                stock += 1
            else:
                if stock <= 0 or cash + proceeds < pr["buy"]:
                    break
                proceeds -= pr["buy"]
                stock -= 1
            filled += 1

        if filled == 0:
            raise ApiError("nothing could be filled at current market conditions")

        new_qty = held - filled if side == "sell" else held + filled
        conn.execute(
            "INSERT INTO inventory(player_id, product_id, qty) VALUES (?,?,?)"
            " ON CONFLICT(player_id, product_id) DO UPDATE SET qty=excluded.qty",
            (p["id"], pid, new_qty),
        )
        conn.execute("UPDATE market SET stock=?, updated_at=? WHERE code=? AND product_id=?",
                     (stock, time.time(), p["code"], pid))
        new_cash = round(cash + proceeds, 2)
        conn.execute("UPDATE players SET cash=? WHERE id=?", (new_cash, p["id"]))
        _log(conn, p["code"], p["id"], f"product_{side}",
             {"product": pid, "qty": filled, "proceeds": round(proceeds, 2)})
        avg = abs(proceeds) / filled if filled else 0
        return {"filled": filled, "requested": qty, "avg_price": round(avg, 2),
                "proceeds": round(proceeds, 2), "cash": new_cash,
                "price": price_for(pid, stock, class_size), "stock": round(stock, 1)}


def trade_equity(body) -> dict:
    """Put cash to work in the market, or take it back out."""
    token = str(body.get("token", ""))
    symbol = str(body.get("symbol", "")).upper()
    side = str(body.get("side", "")).lower()
    shares = float(body.get("shares", 0))
    if symbol not in EQUITIES:
        raise ApiError("unknown symbol")
    if side not in ("buy", "sell"):
        raise ApiError("side must be buy or sell")
    if shares <= 0 or shares > 1e6:
        raise ApiError("share count out of range")

    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        s = _require_open(conn, p["code"])
        price = equity_price(symbol, int(s["seed"]), session_minute(s))
        cash = float(p["cash"])
        row = conn.execute("SELECT shares, avg_cost FROM positions WHERE player_id=? AND symbol=?",
                           (p["id"], symbol)).fetchone()
        have = float(row["shares"]) if row else 0.0
        avg = float(row["avg_cost"]) if row else 0.0

        if side == "buy":
            cost = price * shares
            if cost > cash + 1e-9:
                raise ApiError(f"not enough cash: need ${cost:,.2f}, have ${cash:,.2f}")
            avg = ((avg * have) + cost) / (have + shares)
            have += shares
            cash -= cost
        else:
            if shares > have + 1e-9:
                raise ApiError(f"you only hold {have:g} shares of {symbol}")
            have -= shares
            cash += price * shares
            if have <= 1e-9:
                have, avg = 0.0, 0.0

        conn.execute(
            "INSERT INTO positions(player_id, symbol, shares, avg_cost) VALUES (?,?,?,?)"
            " ON CONFLICT(player_id, symbol) DO UPDATE SET shares=excluded.shares, avg_cost=excluded.avg_cost",
            (p["id"], symbol, have, avg),
        )
        cash = round(cash, 2)
        conn.execute("UPDATE players SET cash=? WHERE id=?", (cash, p["id"]))
        _log(conn, p["code"], p["id"], f"equity_{side}", {"symbol": symbol, "shares": shares, "price": price})
        return {"symbol": symbol, "side": side, "shares": shares, "price": price,
                "cash": cash, "position": {"shares": have, "avg_cost": round(avg, 2)}}


def spend_cash(body) -> dict:
    """Client-side buildings call this to pay the cash half of a build/upgrade."""
    token = str(body.get("token", ""))
    amount = float(body.get("amount", 0))
    reason = str(body.get("reason", "build"))[:64]
    if amount <= 0 or amount > 1e7:
        raise ApiError("amount out of range")
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        _require_open(conn, p["code"])
        cash = float(p["cash"])
        if amount > cash + 1e-9:
            raise ApiError(f"not enough cash: need ${amount:,.2f}, have ${cash:,.2f}")
        cash = round(cash - amount, 2)
        conn.execute("UPDATE players SET cash=? WHERE id=?", (cash, p["id"]))
        _log(conn, p["code"], p["id"], "spend", {"amount": amount, "reason": reason})
        return {"cash": cash, "spent": amount}


def deposit_products(body) -> dict:
    """Register goods the client just produced.

    Production itself is still simulated client-side, so this endpoint trusts
    the quantity but meters it: a player accrues an allowance over time and
    cannot bank more than that. It blocks the trivial "deposit a million" exploit
    without needing the whole factory simulated server-side.
    """
    token = str(body.get("token", ""))
    pid = str(body.get("product_id", ""))
    qty = int(body.get("qty", 0))
    if pid not in PRODUCTS:
        raise ApiError("unknown product")
    if qty <= 0 or qty > 5000:
        raise ApiError("quantity out of range")

    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        _require_open(conn, p["code"])

        # allowance: DEPOSIT_PER_HOUR units/hour since joining, plus a starting float
        elapsed_h = max(0.0, (time.time() - float(p["joined_at"])) / 3600.0)
        allowance = DEPOSIT_BASE + DEPOSIT_PER_HOUR * elapsed_h
        row = conn.execute(
            "SELECT COALESCE(SUM(qty),0) AS n FROM deposits WHERE player_id=?", (p["id"],)
        ).fetchone()
        banked = float(row["n"]) if row else 0.0
        if banked + qty > allowance:
            raise ApiError(
                f"production allowance reached ({int(banked)}/{int(allowance)} units). "
                "Your base needs more time.", 429)

        conn.execute("INSERT INTO deposits(player_id, product_id, qty, at) VALUES (?,?,?,?)",
                     (p["id"], pid, qty, time.time()))
        held = conn.execute("SELECT qty FROM inventory WHERE player_id=? AND product_id=?",
                            (p["id"], pid)).fetchone()
        held = int(held["qty"]) if held else 0
        conn.execute(
            "INSERT INTO inventory(player_id, product_id, qty) VALUES (?,?,?)"
            " ON CONFLICT(player_id, product_id) DO UPDATE SET qty=excluded.qty",
            (p["id"], pid, held + qty))
        _log(conn, p["code"], p["id"], "produce", {"product": pid, "qty": qty})
        return {"product_id": pid, "qty": held + qty,
                "allowance_left": int(max(0, allowance - banked - qty))}


def save_buildings(body) -> dict:
    """Persist the client-owned buildings blob so a refresh or a new machine is safe."""
    token = str(body.get("token", ""))
    blob = body.get("buildings")
    if not isinstance(blob, dict):
        raise ApiError("buildings must be an object")
    encoded = json.dumps(blob)
    if len(encoded) > 200_000:
        raise ApiError("buildings payload too large")
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        conn.execute("UPDATE players SET buildings=? WHERE id=?", (encoded, p["id"]))
    return {"saved": True}


def load_buildings(query) -> dict:
    token = (query.get("token") or [""])[0]
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        try:
            return {"buildings": json.loads(p["buildings"] or "{}")}
        except json.JSONDecodeError:
            return {"buildings": {}}


def teacher(body) -> dict:
    """pause / resume / reset_player / roster — all require the teacher token."""
    token = str(body.get("teacher_token", ""))
    action = str(body.get("action", ""))
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE teacher_token=?", (token,)).fetchone()
        if s is None:
            raise ApiError("not authorised", 403)
        code, now = s["code"], time.time()

        if action == "pause" and not s["paused"]:
            conn.execute("UPDATE sessions SET paused=1, clock_accum=? WHERE code=?",
                         (float(s["clock_accum"]) + now - float(s["clock_base"]), code))
        elif action == "resume" and s["paused"]:
            conn.execute("UPDATE sessions SET paused=0, clock_base=? WHERE code=?", (now, code))
        elif action == "reset_player":
            name = str(body.get("name", "")).upper()
            row = conn.execute("SELECT id FROM players WHERE code=? AND name=?", (code, name)).fetchone()
            if row is None:
                raise ApiError("no such student", 404)
            conn.execute("UPDATE players SET cash=?, buildings='{}' WHERE id=?", (STARTING_CASH, row["id"]))
            conn.execute("DELETE FROM inventory WHERE player_id=?", (row["id"],))
            conn.execute("DELETE FROM positions WHERE player_id=?", (row["id"],))
        elif action == "shock":
            # Nudge every product's stock to move prices; magnitude is a fraction of neutral.
            mag = max(-0.9, min(0.9, float(body.get("magnitude", 0.3))))
            csz = class_size_of(conn, code)
            for pid in PRODUCTS:
                stock = _market_row(conn, code, pid, csz)
                neutral, cap = depth(pid, csz)
                target = max(0.0, min(cap, stock + mag * neutral))
                conn.execute("UPDATE market SET stock=?, updated_at=? WHERE code=? AND product_id=?",
                             (target, now, code, pid))
            _log(conn, code, None, "shock", {"magnitude": mag})
        elif action not in ("pause", "resume", "roster"):
            raise ApiError("unknown teacher action")

        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        minute, seed = session_minute(s), int(s["seed"])
        csz = max(1, int(s["class_size"]))
        roster = []
        for row in conn.execute("SELECT * FROM players WHERE code=? ORDER BY name", (code,)):
            roster.append({
                "name": row["name"], "cash": round(float(row["cash"]), 2),
                "net_worth": _net_worth(conn, row, minute, seed, csz),
                "joined_at": row["joined_at"],
            })
        roster.sort(key=lambda r: -r["net_worth"])
        for i, r in enumerate(roster):
            r["rank"] = i + 1
        return {"code": code, "paused": bool(s["paused"]), "minute": minute, "class_size": csz,
                "roster": roster, "count": len(roster)}
