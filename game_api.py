#!/usr/bin/env python3
"""Classroom game backend for YoMama.

The server owns the production economy, transactions and saved progress.
production_economy.py implements real goods, recipes, automatic customers,
upgrades and optional deliveries using config/economy.v4.json. The original
v3 rules remain in economy.py for reference and regression tests.

Class time advances in 15-second ticks and stops when a teacher pauses it.
Each player's production is capped at 12 hours after their last own activity;
paid construction follows the class clock. SQLite transactions make actions
atomic. Original saves migrate once with an audit snapshot and retained value.
Part 2 equity trading retains its wallet and server-enforced licence gate.
"""

from __future__ import annotations

import json
import copy
import functools
import math
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import production_economy as economy
import breakfast_event
import access

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "game.db"
QUIZ_PATH = ROOT / "config" / "quiz.json"

_db_lock = threading.RLock()

# ---------------------------------------------------------------- config ---

# Part 2 only. Deterministic function of (session seed, minute) so a class is
# reproducible and needs no internet connection.
EQUITIES = {
    "AAPL": {"name": "Apple",     "base": 185.0, "vol": 0.018, "drift": 0.0006},
    "MSFT": {"name": "Microsoft", "base": 402.0, "vol": 0.015, "drift": 0.0008},
    "NVDA": {"name": "NVIDIA",    "base": 118.0, "vol": 0.038, "drift": 0.0012},
    "SPY":  {"name": "S&P 500",   "base": 512.0, "vol": 0.009, "drift": 0.0005},
    "TSLA": {"name": "Tesla",     "base": 242.0, "vol": 0.034, "drift": 0.0000},
}

# Part 2 starting wallet. Part 1 money is econ.cash and starts at zero.
STARTING_CASH = 2500.0


# --- login -------------------------------------------------------------------
# Off: every request needs a real player token, which only join.html hands out
# against a class code that admin.py opened. No HTTP endpoint can open a class;
# the teacher console opens with a teacher code (see access.py).
#
# AUTO_LOGIN = True is the old solo mode for local previews: a request with no
# valid token is served as one shared "solo" player in a class of its own,
# created on first use. Never run the public server that way.
AUTO_LOGIN = False
SOLO_CODE = "SOLO"
SOLO_NAME = "SOLO PLAYER"
# A brand new player earns 1 YM every 15 seconds, which is nothing to look at.
# The solo class starts this many days old so the first page load has a running
# business on it. Set to 0 for an honest cold start.
SOLO_HEADSTART_DAYS = 0

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    code          TEXT PRIMARY KEY,
    teacher_token TEXT NOT NULL,
    seed          INTEGER NOT NULL,
    created_at    REAL NOT NULL,
    paused        INTEGER NOT NULL DEFAULT 0,
    clock_base    REAL NOT NULL,
    clock_accum   REAL NOT NULL DEFAULT 0,
    class_size    INTEGER NOT NULL DEFAULT 30,
    class_seed    INTEGER NOT NULL DEFAULT 0,
    started_at    REAL NOT NULL DEFAULT 0,
    econ_config   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS players (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    name       TEXT NOT NULL,
    token      TEXT NOT NULL UNIQUE,
    joined_at  REAL NOT NULL,
    cash       REAL NOT NULL,
    pin        TEXT NOT NULL DEFAULT '',
    buildings  TEXT NOT NULL DEFAULT '{}',
    econ       TEXT NOT NULL DEFAULT '',
    econ_nw    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(code, name)
);
CREATE TABLE IF NOT EXISTS positions (
    player_id INTEGER NOT NULL,
    symbol    TEXT NOT NULL,
    shares    REAL NOT NULL DEFAULT 0,
    avg_cost  REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, symbol)
);
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

# Columns added after the first release. SQLite cannot express them in
# CREATE TABLE IF NOT EXISTS, so they are applied to existing databases here.
MIGRATIONS = (
    ("players", "econ_meta", "TEXT NOT NULL DEFAULT '{}'"),
    ("sessions", "pressure", "TEXT NOT NULL DEFAULT '[]'"),
    ("sessions", "income_per_hour", "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "econ_tick", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "custom_events", "TEXT NOT NULL DEFAULT '[]'"),
    ("players", "pin", "TEXT NOT NULL DEFAULT ''"),
    ("players", "econ", "TEXT NOT NULL DEFAULT ''"),
    ("players", "econ_nw", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "class_seed", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "started_at", "REAL NOT NULL DEFAULT 0"),
    ("sessions", "econ_config", "TEXT NOT NULL DEFAULT ''"),
    # Provisioning columns, kept in step with admin.ADMIN_COLUMNS so a database
    # the server created first has them too. access.py reads them.
    ("sessions", "teacher_code", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "joins_open", "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "active", "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "label", "TEXT NOT NULL DEFAULT ''"),
)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("BEGIN IMMEDIATE")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


class ApiError(Exception):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


# ------------------------------------------------------------- class time ---

def econ_clock_seconds(session: sqlite3.Row) -> float:
    """Seconds of unpaused class time so far. Tick 0 is the class start."""
    accum = float(session["clock_accum"])
    if not session["paused"]:
        accum += time.time() - float(session["clock_base"])
    return max(0.0, accum)


def session_minute(session: sqlite3.Row) -> int:
    return int(econ_clock_seconds(session) // 60)


def equity_price(symbol: str, seed: int, minute: int) -> float:
    """Deterministic pseudo-random walk. Same seed+minute always same price."""
    cfg = EQUITIES[symbol]
    price = cfg["base"]
    h = (seed * 2654435761 + sum(ord(c) for c in symbol) * 40503) & 0xFFFFFFFF
    for _i in range(minute + 1):
        h = (h * 1103515245 + 12345) & 0x7FFFFFFF
        u = ((h >> 8) / 8388608.0) - 1.0          # roughly [-1, 1]
        price *= math.exp(cfg["drift"] * 0.1 + cfg["vol"] * u * 0.5)
        price = max(cfg["base"] * 0.25, min(cfg["base"] * 4.0, price))
    return round(price, 2)


# --------------------------------------------------------------- economy ----

_startup_config = economy.load_config()
_book_cache = {}
_class_locks = {}
_META_KEYS = {'tick', 'rngState', 'report', 'reportBaseline', 'lastRank', 'reportTick', 'rumour'}


def econ_config(session):
    cfg = json.loads(session['econ_config']) if session['econ_config'] else copy.deepcopy(_startup_config)
    if 'fun' not in cfg or (_startup_config.get('version') == 4 and cfg.get('version') != 4):
        cfg = copy.deepcopy(_startup_config)
    cfg['global']['seed'] = int(session['class_seed']) or cfg['global']['seed']
    return cfg


def econ_tick_now(cfg, session):
    return int(econ_clock_seconds(session) // cfg['global']['tick'])


def _load_state(player, cfg, session):
    raw = json.loads(player['econ']) if player['econ'] else {}
    if not raw:
        return economy.new_state(cfg, econ_tick_now(cfg,session), seed=cfg['global']['seed']*48611+player['id']*7+5)
    if 'b' not in raw:
        # Preserve the actually owned legacy building and all monetary balances.
        # Previously sold buildings must not be resurrected or refunded again.
        st = economy.new_state(cfg, raw.get('tick',econ_tick_now(cfg,session)))
        ti = raw.get('tier',0)
        st.update({k:raw[k] for k in ('cash','book','taxPaid','lastLogin','catchupUntil','checklist','keepPercent') if k in raw})
        st['b']=[dict(lv=min(raw.get('lv',1),cfg['global']['maxLevel']),auto=raw.get('auto',1),tier=ti)]
        st['tierOf']=[ti]; st['pend']={'0':sum(raw.get('pend',{}).values())}
        if raw.get('build'):
            build=raw['build']; st['build']=dict(t=build['finishTick'],i=build['from']+1)
        st['queue']=[q['from']+1 if isinstance(q,dict) else q+1 for q in raw.get('queue',[])]
        # This is an old single-building save, even though defaults came from
        # the current engine. It still needs the real-goods migration.
        st.pop('modelVersion',None)
        return economy.migrate_state(cfg, st) if cfg.get('version') == 4 else st
    st=economy.State(raw)
    st.update(json.loads(player['econ_meta']))
    defaults=economy.new_state(cfg)
    for k in _META_KEYS:
        if k not in st and k in defaults: st[k]=defaults[k]
    return economy.migrate_state(cfg, st) if cfg.get('version') == 4 else st


def _save_state(conn, player_id, cfg, st):
    core={k:v for k,v in st.items() if k not in _META_KEYS}
    meta={k:v for k,v in st.items() if k in _META_KEYS}
    conn.execute('UPDATE players SET econ=?, econ_meta=?, econ_nw=? WHERE id=?',
                 (json.dumps(core,separators=(',',':')),json.dumps(meta,separators=(',',':')),economy.net_worth(st),player_id))


def _save_world(conn, session, cls):
    conn.execute('UPDATE sessions SET pressure=?, income_per_hour=?, econ_tick=? WHERE code=?',
                 (json.dumps(cls['pressure']),cls['incomePerHour'],cls['nextTick'],session['code']))


def _class_econ(conn, session):
    cfg=econ_config(session)
    # First v3 access migrates old snapshots, recording the original state.
    old=json.loads(session['econ_config']) if session['econ_config'] else {}
    rows=list(conn.execute('SELECT * FROM players WHERE code=? ORDER BY id',(session['code'],)))
    states={p['id']:_load_state(p,cfg,session) for p in rows}
    start=session['econ_tick']
    if not old and not rows:
        # A class admin.py opened stores no config until its first student
        # (join stamps it). Empty and nobody in it yet is a new class, not a
        # legacy one: record the rules and skip the migration below.
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',(json.dumps(cfg),session['code']))
        session=_session_of(conn,session['code'])
    elif cfg.get('version') == 4 and old.get('version') != 4:
        # Preserve the old snapshot in the ledger. New rules start now: past
        # years of class time must not mint new-model goods or money.
        start=econ_tick_now(cfg,session)
        _log(conn,session['code'],None,'v4_migration',dict(config=old,players=[
            dict(id=p['id'],econ=p['econ'],meta=p['econ_meta']) for p in rows]))
        for st in states.values():
            st['tick']=start
            # Paid work keeps its original deadline. Finish overdue buildings
            # without granting retroactive v4 production or automatic spending.
            while st['build'] and st['build']['t']<=start:
                economy.finish_build(cfg,st,st['build']['t'])
            st['lastActiveTick']=start
            st['lastLogin']=start
            st['reportTick']=start
            st['reportBaseline']=dict(st['report'],contractsDone=st['cStats']['done'],contractsFailed=st['cStats']['failed'])
        conn.execute('UPDATE sessions SET econ_config=?, pressure=?, income_per_hour=1 WHERE code=?',
                     (json.dumps(cfg),json.dumps([0]*len(cfg['tiers'])),session['code']))
        session=_session_of(conn,session['code'])
    elif 'fun' not in old:
        start=min((st['tick'] for st in states.values()),default=econ_tick_now(cfg,session))
        _log(conn,session['code'],None,'v3_migration',dict(config=old,players=[dict(id=p['id'],econ=p['econ']) for p in rows]))
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',(json.dumps(cfg),session['code']))
    target=econ_tick_now(cfg,session)
    stop=target if cfg.get('version') == 4 else min(target,start+economy.jsround(cfg['runtime']['maxCatchupDays']*economy.ticks_per_day(cfg)))
    key=(session['code'],json.dumps(cfg,sort_keys=True))
    book=_book_cache.setdefault(key,economy.PriceBook(cfg))
    cls=economy.new_class(cfg,stop+economy.ticks_per_day(cfg),book)
    cls['ev']+=json.loads(session['custom_events'])
    cls['ev'].sort(key=lambda e:e['startTick'])
    cls['pressure']=json.loads(session['pressure']) or [0.0]*len(cfg['tiers'])
    cls['incomePerHour']=session['income_per_hour']
    economy.advance_class(cfg,cls,list(states.values()),start,stop)
    cls['k']=max(0,stop-1);cls['nextTick']=stop
    for player_id,st in states.items():
        if cfg.get('version') == 4:
            breakfast_event.advance(st, stop * cfg['global']['tick'])
        economy.bind_sales(cfg,cls,st)
        # New joiners need today's offers without replaying time before joining.
        if st['offers'] is None and 0<st['tick']<=stop:
            economy.offer_contracts(cfg,st,stop)
        _save_state(conn,player_id,cfg,st)
    _save_world(conn,session,cls)
    return cfg,cls,states,stop<target


def _player_econ(conn, player, session):
    cfg,cls,states,behind=_class_econ(conn,session)
    st=states[player['id']]
    if cfg.get('version') == 4 and not behind:
        # Other students can replay a class, but cannot renew this player's
        # offline allowance. Only their own request records activity.
        st['lastActiveTick']=st['tick']
        _save_state(conn,player['id'],cfg,st)
    return cfg,cls,st,behind


def _event_payload(cfg, cls, k, history=False):
    result=[]
    deck=json.loads((ROOT/'content/headlines.json').read_text())
    for idx,e in enumerate(cls['ev']):
        end=e['startTick']+e['holdTicks']+economy.jsround((cfg['fun']['eventRampMin']+cfg['fun']['eventDecayMin'])*60/cfg['global']['tick'])
        if not e['real'] or e['startTick']>k or (not history and k>end): continue
        direction='up' if e['mag']>1 else 'down'
        choices=[h['text'] for h in deck if h['family']==e['family'] and h['direction']==direction]
        result.append(dict(headline=e.get('headline') or choices[idx%len(choices)] if choices else e.get('headline','Market news'),
                           family=e['family'],direction=direction,started=e['startTick']*cfg['global']['tick'],
                           ends=end*cfg['global']['tick'],multiplier=economy.event_mult(cfg,cls['ev'],e['family'],k)))
    return result


def econ_payload(cfg, st, cls, session, behind=False):
    if cfg.get('version') == 4:
        result = economy.payload(cfg, st, cls, session, behind)
        result['breakfastEvent'] = breakfast_event.payload(st, cls['nextTick'] * cfg['global']['tick'])
        return result
    return _legacy_econ_payload(cfg, st, cls, session, behind)


def _legacy_econ_payload(cfg, st, cls, session, behind=False):
    g=cfg['global'];day=economy.ticks_per_day(cfg);k=cls['k'];rev=economy.revS(cfg,st)
    caps=economy.warehouse_cap(cfg,st);cap=sum(caps);stored=sum(st['pend'].values());buildings=[];board=[]
    for bi,b in enumerate(st['b']):
        ti=st['tierOf'][bi];t=cfg['tiers'][ti];r=economy.bRev(cfg,st,bi)
        lc=economy.level_cost(cfg,st,bi);ac=economy.auto_cost(cfg,st,bi)
        nxt=copy.deepcopy(st);nxt['b'][bi]['lv']+=1;delta=economy.bRev(cfg,nxt,bi)-r
        auto_delta=r*((g['a1Mult'] if b['auto']==1 else g['a2Mult'])-1)
        def payback(cost,d): return round(cost/d*g['tick']/60,1) if cost is not None and d>0 else None
        price=economy.class_price(cfg,cls,ti,k)
        # Trend compares base/event movement with the current shared pressure.
        prev=economy.class_price(cfg,cls,ti,max(0,k-1))
        badges=[]
        if cfg['fun']['setBonus']:
            if sum(cfg['tiers'][i]['family']==t['family'] for i in st['tierOf'])>=cfg['fun']['setSize']:
                badges.append(cfg['families'][t['family']]['name'].upper()+' SET ×'+str(1+cfg['fun']['setFamilyPct']/100))
            if sum(cfg['tiers'][i]['row']==t['row'] for i in st['tierOf'])>=cfg['fun']['setSize']:
                badges.append('TRIPLET ×'+str(1+cfg['fun']['setRowPct']/100))
        pool=st['pend'].get(str(bi),0)
        label='None' if b['auto']==1 else 'Auto Control I' if b['auto']==g['a1Mult'] else 'Auto Control II'
        item=dict(slot=bi,tier=ti,id=t['id'],name=t['name'],family=t['family'],lv=b['lv'],maxed=lc is None,auto=b['auto'],autoLabel=label,
                  revenuePerTick=r,setBadges=badges,levelCost=lc,levelPayback=payback(lc,delta),autoCost=ac,autoPayback=payback(ac,auto_delta),
                  stored=pool,price=price,priceTrend='up' if price>prev else 'down' if price<prev else 'flat',capacity=caps[bi])
        buildings.append(item)
        # A building has ONE goods pool in v3; weighted display conserves every YM.
        weights=sum(x['weight'] for x in t['goods']);allocated=0
        for gi,good in enumerate(t['goods']):
            v=pool-allocated if gi==len(t['goods'])-1 else economy.jsround(pool*good['weight']/weights)
            allocated+=v
            board.append(dict(slot=bi,tier=ti,name=good['name'],tierName=t['name'],family=t['family'],stored=v,poolStored=pool,price=price))
    frontier=[]
    for ti in economy.expand_options(cfg,st):
        t=cfg['tiers'][ti];ok=economy.can_expand(cfg,st,ti)
        frontier.append(dict(tier=ti,name=t['name'],family=t['family'],cost=t['baseCost'],baseRevenue=t['rev'],timerH=t['timerH'],
                             affordable=st['cash']>=t['baseCost'],canExpand=ok['ok'],why=ok.get('why','')))
    def contract(c):
        return dict(c,building=cfg['tiers'][st['tierOf'][c['bi']]]['name'],remainingSec=max(0,(c['deadline']-st['tick'])*g['tick']),
                    progressPercent=round(c.get('delivered',0)/c['target']*100,1))
    rum=economy.rumour_now(cfg,cls['ev'],k)
    build=dict(tier=st['build']['i'],name=cfg['tiers'][st['build']['i']]['name'],remainingSec=max(0,(st['build']['t']-st['tick'])*g['tick'])) if st['build'] else None
    ticker=[e['headline'] for e in _event_payload(cfg,cls,k)]
    if rum: ticker.insert(0,'Rumour: '+cfg['families'][rum['family']]['name']+' demand may move '+('up' if rum['up'] else 'down'))
    for b in buildings:
        depth=cfg['families'][b['family']]['depth']*cls['incomePerHour']
        pressure=min(cfg['fun']['pressureCap'],cls['pressure'][b['tier']]/max(1,depth)) if cfg['fun']['pressure'] else 0
        if pressure>0: ticker.append(b['name']+' market crowded −'+str(economy.jsround(pressure*100))+'%')
    newest=buildings[-1]
    return dict(tick=st['tick'],tickSeconds=g['tick'],behind=behind,cash=st['cash'],netWorth=economy.net_worth(st),book=st['book'],taxPaid=st['taxPaid'],
                taxRate=economy.tax_rate(cfg,rev*day),revenuePerTick=rev,revenuePerDay=rev*day,buildings=buildings,buildingsOwned=len(buildings),
                frontier=frontier,build=build,queue=[dict(tier=i,name=cfg['tiers'][i]['name']) for i in st['queue']],queueDepth=g['queueDepth'],
                warehouseCap=cap,warehouseStored=stored,warehouseFillPercent=round(stored/cap*100,1),overflowing=any(b['stored']>=b['capacity'] for b in buildings),
                overflowDisc=g['overflowDisc'],contracts=dict(offers=[contract(c) for c in st['offers'] or []],active=[contract(c) for c in st['contracts']]),
                rumour=dict(family=rum['family'],direction='up' if rum['up'] else 'down') if rum else None,activeEvents=_event_payload(cfg,cls,k),
                board=board,checklist=st['checklist'],checklistText=cfg['gate']['checklist'],goodSalesNeeded=cfg['gate']['goodSalesNeeded'],
                goodSalePrice=cfg['gate']['goodSalePrice'],gateTier=g['gateTier'],gateOpen=economy.gate_open(cfg,st),keepPercent=st['keepPercent'],
                welcomeBackActive=st['tick']<st['catchupUntil'],currency=cfg['currency'],paused=bool(session['paused']),
                families=cfg['families'],tickerLines=ticker,contractSlots=cfg['fun']['contractSlots'],premiumSalePct=cfg['fun']['premiumSalePct'],maxLevel=g['maxLevel'],gradLevel=g['gradLv'],
                tier=newest['tier'],tierCount=len(cfg['tiers']),buildingName=newest['name'],buildingId=newest['id'],level=newest['lv'],
                auto=newest['auto'],autoLabel=newest['autoLabel'])


# ------------------------------------------------------------- endpoints ---
# Every handler returns a dict. Actions advance the state to now, apply the
# action and persist, all inside one transaction.

def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1
    return "".join(secrets.choice(alphabet) for _ in range(5))


def _player_by_token(conn, token: str):
    return conn.execute("SELECT * FROM players WHERE token=?", (token or "",)).fetchone()


def _log(conn, code, player_id, kind, detail):
    conn.execute(
        "INSERT INTO ledger(code, player_id, at, kind, detail) VALUES (?,?,?,?,?)",
        (code, player_id, time.time(), kind, json.dumps(detail)),
    )


def _session_of(conn, code: str):
    s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
    if s is None:
        raise ApiError("class no longer exists", 404)
    access.check_active(s)          # a revoked class refuses every request
    return s


def _require_open(conn, code: str):
    s = _session_of(conn, code)
    if s["paused"]:
        raise ApiError("the class is paused", 409)
    return s


def _ensure_solo(conn):
    """The seat handed to anyone who arrives without a token. Created on demand."""
    now = time.time()
    cfg = economy.load_config()
    s = conn.execute("SELECT * FROM sessions WHERE code=?", (SOLO_CODE,)).fetchone()
    if s is None:
        conn.execute(
            "INSERT INTO sessions(code, teacher_token, seed, created_at, paused, clock_base,"
            " clock_accum, class_size, class_seed, started_at, econ_config)"
            " VALUES (?,?,?,?,0,?,0,?,?,?,?)",
            (SOLO_CODE, secrets.token_urlsafe(24), secrets.randbelow(1 << 30), now, now, 1,
             int(cfg["global"]["seed"]), now, json.dumps(cfg, separators=(",", ":"))),
        )
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (SOLO_CODE,)).fetchone()

    p = conn.execute("SELECT * FROM players WHERE code=? AND name=?",
                     (SOLO_CODE, SOLO_NAME)).fetchone()
    if p is None:
        # start at tick 0 and age the class, so the first visit replays a
        # couple of days instead of showing an empty farm
        st = economy.new_state(cfg, 0)
        conn.execute(
            "INSERT INTO players(code, name, token, joined_at, cash, pin, econ, econ_nw)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (SOLO_CODE, SOLO_NAME, secrets.token_urlsafe(24), now, STARTING_CASH, "",
             json.dumps(st, separators=(",", ":")), int(economy.net_worth(cfg, st))),
        )
        if SOLO_HEADSTART_DAYS:
            conn.execute("UPDATE sessions SET clock_accum=? WHERE code=?",
                         (SOLO_HEADSTART_DAYS * 86400, SOLO_CODE))
        _log(conn, SOLO_CODE, None, "solo_seat_created", {})
        p = conn.execute("SELECT * FROM players WHERE code=? AND name=?",
                         (SOLO_CODE, SOLO_NAME)).fetchone()
    return p


def _auth(conn, body_or_query, open_only=False):
    token = body_or_query.get("token")
    if isinstance(token, list):
        token = token[0] if token else ""
    p = _player_by_token(conn, str(token or ""))
    if p is None:
        if not AUTO_LOGIN:
            raise ApiError("unknown or expired token", 401)
        p = _ensure_solo(conn)
    s = _require_open(conn, p["code"]) if open_only else _session_of(conn, p["code"])
    return p, s


def create_session(body) -> dict:
    """Open a class. Tick 0 is now.

    Not reachable over HTTP any more: classes are opened with admin.py, which
    also mints the teacher code. Kept for the tests, and as the reference for
    what a session row needs.
    """
    now = time.time()
    cfg = economy.load_config()
    with _db_lock, connect() as conn:
        for _ in range(20):
            code = new_code()
            if conn.execute("SELECT 1 FROM sessions WHERE code=?", (code,)).fetchone() is None:
                break
        else:
            raise ApiError("could not allocate a session code", 500)
        teacher_token = secrets.token_urlsafe(24)
        class_size = max(1, min(200, int(body.get("class_size", 30) or 30)))
        class_seed = secrets.randbelow(1 << 30) or int(cfg["global"]["seed"])
        conn.execute(
            "INSERT INTO sessions(code, teacher_token, seed, created_at, paused, clock_base,"
            " clock_accum, class_size, class_seed, started_at, econ_config)"
            " VALUES (?,?,?,?,0,?,0,?,?,?,?)",
            (code, teacher_token, secrets.randbelow(1 << 30), now, now, class_size,
             class_seed, now, json.dumps(cfg, separators=(",", ":"))),
        )
        _log(conn, code, None, "session_created", {"class_seed": class_seed})
    return {"code": code, "teacher_token": teacher_token, "class_size": class_size,
            "class_seed": class_seed}


def join(body) -> dict:
    """Student joins with the class code, a display name and a 4-digit PIN.

    Names are unique within a class. The PIN is not a password protecting
    anything valuable - it exists so that the second Emma in a class of thirty
    cannot walk into the first Emma's game, and so a student who clears their
    browser can still get their own seat back.
    """
    code = str(body.get("code", "")).strip().upper()
    name = " ".join(str(body.get("name", "")).split())[:24].upper()
    pin = str(body.get("pin", "")).strip()

    if not code or not name:
        raise ApiError("class code and name are required")
    if not (pin.isdigit() and len(pin) == 4):
        raise ApiError("pick a 4-digit PIN you will remember")

    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            raise ApiError("no class with that code", 404)
        access.check_active(s)

        existing = conn.execute(
            "SELECT * FROM players WHERE code=? AND name=?", (code, name)
        ).fetchone()
        if existing is not None:
            seat = f"{code}/{name}"
            if access.PIN_LIMIT.blocked(seat):
                raise ApiError("too many wrong PINs for this name; try again in ten minutes", 429)
            if secrets.compare_digest(str(existing["pin"]), pin):
                return {"token": existing["token"], "name": name, "code": code, "rejoined": True}
            access.PIN_LIMIT.hit(seat)
            raise ApiError(
                f"{name} is already taken in this class. If that is you, check your PIN. "
                "Otherwise add an initial, like " + name.split()[0] + " B.", 409)

        # A closed class still lets its own students back in (same name + PIN,
        # handled above); only a new seat is refused.
        access.check_joins_open(s)
        seats = int(s["class_size"] or 0)
        taken = conn.execute("SELECT COUNT(*) FROM players WHERE code=?", (code,)).fetchone()[0]
        if seats and taken >= seats:
            raise ApiError(f"this class is full ({seats} seats); ask the teacher", 403)
        cfg = econ_config(s)
        if not s["econ_config"]:
            # admin.py opens classes without a config. The first student fixes
            # the rules, so later reads see a version-4 class, not a legacy one.
            conn.execute("UPDATE sessions SET econ_config=? WHERE code=?",
                         (json.dumps(cfg, separators=(",", ":")), code))
        st = economy.new_state(cfg, econ_tick_now(cfg, s))
        token = secrets.token_urlsafe(24)
        cur = conn.execute(
            "INSERT INTO players(code, name, token, joined_at, cash, pin, econ, econ_nw)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (code, name, token, time.time(), STARTING_CASH, pin,
             json.dumps(st, separators=(",", ":")), int(economy.net_worth(cfg, st))),
        )
        _log(conn, code, cur.lastrowid, "join", {"name": name})
    return {"token": token, "name": name, "code": code, "rejoined": False}


def _leaderboard(conn, code: str, me_id: int) -> list:
    """Ranked by net worth from the engine - cash plus warehouse plus book.

    Read from the cached column so one student's poll does not replay the whole
    class; each student's own figure is refreshed as they play.
    """
    board = [{"name": r["name"], "net_worth": int(r["econ_nw"]), "you": r["id"] == me_id}
             for r in conn.execute("SELECT id, name, econ_nw FROM players WHERE code=?", (code,))]
    board.sort(key=lambda x: -x["net_worth"])
    for i, entry in enumerate(board):
        entry["rank"] = i + 1
    return board


def get_state(query) -> dict:
    """Everything the dashboard needs in one round trip."""
    with _db_lock, connect() as conn:
        p, s = _auth(conn, query)
        cfg, book, st, behind = _player_econ(conn, p, s)
        minute, seed = session_minute(s), int(s["seed"])

        positions = []
        for r in conn.execute("SELECT symbol, shares, avg_cost FROM positions"
                              " WHERE player_id=? AND shares>0", (p["id"],)):
            price = equity_price(r["symbol"], seed, minute)
            shares = float(r["shares"])
            positions.append({
                "symbol": r["symbol"], "shares": shares, "avg_cost": round(float(r["avg_cost"]), 2),
                "price": price, "value": round(price * shares, 2),
                "pnl": round((price - float(r["avg_cost"])) * shares, 2),
            })

        return {
            "player": {"name": p["name"], "cash": st["cash"],
                       "net_worth": economy.net_worth(cfg, st),
                       "wallet_cash": round(float(p["cash"]), 2)},
            "session": {"code": p["code"], "minute": minute, "paused": bool(s["paused"]),
                        "tick": st["tick"]},
            "econ": econ_payload(cfg, st, book, s, behind),
            "equities": [{"symbol": sym, "name": c["name"], "price": equity_price(sym, seed, minute)}
                         for sym, c in EQUITIES.items()],
            "positions": positions,
            "leaderboard": _leaderboard(conn, p["code"], p["id"]),
        }


def econ_state(query) -> dict:
    """Advance to now and report. No login side effects."""
    with _db_lock, connect() as conn:
        p, s = _auth(conn, query)
        cfg, book, st, behind = _player_econ(conn, p, s)
        payload = econ_payload(cfg, st, book, s, behind)
        payload["leaderboard"] = _leaderboard(conn, p["code"], p["id"])
        payload["name"] = p["name"]
        return payload


def econ_login(body) -> dict:
    """Advance to now, then apply the returning-player catch-up bonus."""
    with _db_lock, connect() as conn:
        p, s = _auth(conn, body)
        cfg, book, st, behind = _player_econ(conn, p, s)
        previous=st.get('reportTick',st['lastLogin'])
        baseline=st.get('reportBaseline',{})
        report={key:value-baseline.get(key,0) for key,value in st['report'].items()}
        board=_leaderboard(conn,p['code'],p['id'])
        rank=next((r['rank'] for r in board if r['you']),None)
        report.update(contractsDone=st['cStats']['done']-baseline.get('contractsDone',0),
                      contractsFailed=st['cStats']['failed']-baseline.get('contractsFailed',0),
                      events=sum(e['real'] and previous<=e['startTick']<st['tick'] for e in book['ev']),
                      rankChange=st.get('lastRank',rank)-rank if rank else 0)
        show=st['tick']-previous>=cfg['runtime']['overnightAbsenceH']*economy.ticks_per_hour(cfg)
        if not behind:
            economy.on_login(cfg, st)
            st['reportBaseline']=dict(st['report'],contractsDone=st['cStats']['done'],contractsFailed=st['cStats']['failed'])
            st['reportTick']=st['tick'];st['lastRank']=rank
        _save_state(conn, p["id"], cfg, st)
        payload = econ_payload(cfg, st, book, s, behind)
        payload["leaderboard"] = _leaderboard(conn, p["code"], p["id"])
        payload["name"] = p["name"]
        payload["code"] = p["code"]
        payload["overnightReport"] = report if show and not behind else None
        # Handed a seat without being asked to log in? Give the browser the token
        # so every page of this browser is the same player.
        if AUTO_LOGIN and str(body.get("token") or "") != p["token"]:
            payload["token"] = p["token"]
        return payload


def _act(body, apply_fn) -> dict:
    """Advance the class, apply one intention, persist, and report atomically."""
    with _db_lock, connect() as conn:
        p, s = _auth(conn, body, open_only=True)
        cfg, book, st, behind = _player_econ(conn, p, s)
        if behind: raise ApiError("Catching up; retry after replay completes", 409)
        result = apply_fn(cfg, st, book)
        if not result.get("ok"):
            raise ApiError(result.get("why", "not allowed"), details=result)
        _save_state(conn, p["id"], cfg, st)
        _log(conn, p["code"], p["id"], "econ_" + result.get("kind", "action"),
             {k: v for k, v in result.items() if k not in ("ok", "kind")})
        payload = econ_payload(cfg, st, book, s, behind)
        _save_world(conn, s, book)
        payload["receipt"] = result
        return payload


def _index(body, key):
    value=body.get(key)
    if isinstance(value,bool) or not isinstance(value,int): raise ApiError(key+' must be an integer')
    return value


def econ_breakfast(body):
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Event unavailable')
        return breakfast_event.act(st, cls['nextTick'] * cfg['global']['tick'], body)
    return _act(body, apply)


def econ_sell(body):
    slot=_index(body,'slot')
    def apply(cfg,st,cls):
        if not 0<=slot<len(st['b']): return dict(ok=False,why='unknown building slot')
        if cfg.get('version') == 4:
            return dict(economy.sell_one(cfg,st,slot,1,True),kind='sell',name=cfg['tiers'][st['tierOf'][slot]]['name'])
        ti=st['tierOf'][slot];price=economy.class_price(cfg,cls,ti,cls['k'])
        rate=economy.tax_rate(cfg,economy.revS(cfg,st)*economy.ticks_per_day(cfg))
        return dict(economy.sell_one(cfg,st,slot,price,True),kind='sell',name=cfg['tiers'][ti]['name'],price=price,rate=rate,premiumSalePct=cfg['fun']['premiumSalePct'])
    return _act(body,apply)


def econ_level(body):
    slot=_index(body,'slot')
    def apply(cfg,st,cls):
        res=economy.buy_level(cfg,st,slot)
        return dict(res,kind='level',level=st['b'][slot]['lv']) if res['ok'] else res
    return _act(body,apply)


def econ_auto(body):
    slot=_index(body,'slot')
    def apply(cfg,st,cls):
        res=economy.buy_auto(cfg,st,slot)
        return dict(res,kind='auto',auto=st['b'][slot]['auto']) if res['ok'] else res
    return _act(body,apply)


def econ_upgrade(body):
    slot=_index(body,'slot')
    kind=body.get('kind')
    if kind not in ('production','sales','storage'):
        raise ApiError('unknown upgrade')
    return _act(body,lambda cfg,st,cls:dict(economy.buy_upgrade(cfg,st,slot,kind),kind='upgrade',upgrade=kind))


def econ_reserve(body):
    slot=_index(body,'slot')
    reserve=body.get('reserve')
    if not isinstance(reserve,bool):
        raise ApiError('reserve must be true or false')
    return _act(body,lambda cfg,st,cls:dict(economy.set_reserve(cfg,st,slot,reserve),kind='reserve'))


def econ_processing(body):
    slot=_index(body,'slot')
    enabled=body.get('enabled')
    if not isinstance(enabled,bool):
        raise ApiError('enabled must be true or false')
    return _act(body,lambda cfg,st,cls:dict(economy.set_processing(cfg,st,slot,enabled),kind='processing'))


def _order_intention(body, replace=False):
    offer=_index(body,'offerIndex')
    order_id=body.get('orderId')
    if not isinstance(order_id,str) or not order_id or len(order_id)>100:
        raise ApiError('orderId is required')
    def apply(cfg,st,cls):
        fn=economy.replace_order if replace else economy.fulfill_order
        return dict(fn(cfg,st,offer,order_id=order_id),kind='order_replace' if replace else 'order')
    return _act(body,apply)


def econ_fulfill_order(body):
    return _order_intention(body)


def econ_replace_order(body):
    return _order_intention(body,replace=True)


def econ_commit_order(body):
    index=_index(body,'offerIndex')
    order_id=body.get('orderId')
    if not isinstance(order_id,str) or not order_id or len(order_id)>100:
        raise ApiError('orderId is required')
    return _act(body,lambda cfg,st,cls: economy.commit_order(cfg,st,index,order_id,body.get('committed'))
                if cfg.get('version')==4 else dict(ok=False,why='Delivery reservations unavailable'))


def econ_focus(body):
    slot=_index(body,'slot')
    focus=body.get('focus')
    if not isinstance(focus,str): raise ApiError('focus must be a specialty name')
    return _act(body,lambda cfg,st,cls:economy.set_focus(cfg,st,slot,focus)
                if cfg.get('version')==4 else dict(ok=False,why='Specialties unavailable'))


def econ_expand(body):
    tier=_index(body,'tier')
    def apply(cfg,st,cls):
        res=economy.expand(cfg,st,tier,st['tick'])
        return dict(res,kind='expand',frontier=economy.expand_options(cfg,st))
    return _act(body,apply)


def econ_graduate(body):
    raise ApiError('Use /econ/expand with a frontier tier')


def econ_contracts(query):
    return econ_state(query)


def econ_accept_contract(body):
    offer=_index(body,'offerIndex')
    def apply(cfg,st,cls):
        if cfg.get('version') == 4:
            return dict(ok=False,why='Refresh to view your delivery orders')
        return dict(economy.accept_contract(cfg,st,offer,st['tick']),kind='contract')
    return _act(body,apply)


def econ_ticker(query):
    with _db_lock, connect() as conn:
        p,s=_auth(conn,query)
        cfg,cls,st,behind=_player_econ(conn,p,s)
        payload=econ_payload(cfg,st,cls,s,behind)
        lines=[dict(kind='event',**e) for e in _event_payload(cfg,cls,cls['k'],history=True)]
        if payload['rumour']: lines.append(dict(kind='rumour',**payload['rumour']))
        payload['lines']=lines[-cfg['runtime']['tickerLimit']:]
        return payload


def _load_quiz() -> dict:
    with open(QUIZ_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def econ_quiz(body) -> dict:
    """Grade the quiz. Answers are option indexes, in question order."""
    answers = body.get("answers")
    if not isinstance(answers, list):
        raise ApiError("answers must be a list of option indexes")
    quiz = _load_quiz()
    questions = quiz["questions"]
    score = sum(1 for i, q in enumerate(questions)
                if i < len(answers) and answers[i] == q["answer"])
    passed = score >= int(quiz.get("passMark", len(questions)))

    with _db_lock, connect() as conn:
        p, s = _auth(conn, body)
        cfg, book, st, behind = _player_econ(conn, p, s)
        if passed:
            st["checklist"]["quiz"] = True
        _save_state(conn, p["id"], cfg, st)
        _log(conn, p["code"], p["id"], "quiz", {"score": score, "passed": passed})
        payload = econ_payload(cfg, st, book, s, behind)
        payload["quiz"] = {"score": score, "total": len(questions), "passed": passed,
                           "passMark": quiz.get("passMark")}
        return payload


def econ_quiz_questions(query) -> dict:
    """The quiz without the answer key."""
    quiz = _load_quiz()
    return {"passMark": quiz.get("passMark"),
            "questions": [{"id": q["id"], "prompt": q["prompt"], "options": q["options"]}
                          for q in quiz["questions"]]}


def econ_keep(body) -> dict:
    """Keep/sell split for Part 2. Only once the gate is open."""
    percent = _index(body,"percent")
    if not 0 <= percent <= 100:
        raise ApiError("percent must be between 0 and 100")
    with _db_lock, connect() as conn:
        p, s = _auth(conn, body, open_only=True)
        cfg, book, st, behind = _player_econ(conn, p, s)
        if not economy.gate_open(cfg, st):
            raise ApiError("the licence is not open yet")
        if cfg.get('version') == 4:
            raise ApiError('The trading desk uses a separate practice portfolio; town cash is not allocated here')
        st["keepPercent"] = percent
        _save_state(conn, p["id"], cfg, st)
        _log(conn, p["code"], p["id"], "keep", {"percent": percent})
        return econ_payload(cfg, st, book, s, behind)


# ----------------------------------------------------------------- Part 2 ---

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
        cfg, cls, st, behind = _player_econ(conn, p, s)
        if behind or not economy.gate_open(cfg,st): raise ApiError('the licence is not open yet',403)
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


# -------------------------------------------------------- player save blob ---

def save_buildings(body) -> dict:
    """Persist the client's own display state (character choice and the like).

    No money lives in here any more; the economy is server-side.
    """
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
        _session_of(conn, p["code"])         # a revoked class refuses this too
        conn.execute("UPDATE players SET buildings=? WHERE id=?", (encoded, p["id"]))
    return {"saved": True}


def load_buildings(query) -> dict:
    token = (query.get("token") or [""])[0]
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            raise ApiError("unknown or expired token", 401)
        _session_of(conn, p["code"])         # a revoked class refuses this too
        try:
            return {"buildings": json.loads(p["buildings"] or "{}")}
        except json.JSONDecodeError:
            return {"buildings": {}}


def token_may_browse(token) -> bool:
    """server.py asks this before serving a page: the browser's cookie must be
    the token of a seat that still exists, in a class that is still active."""
    if not isinstance(token, str) or not token:
        return False
    with _db_lock, connect() as conn:
        p = _player_by_token(conn, token)
        if p is None:
            return False
        try:
            _session_of(conn, p["code"])
        except ApiError:
            return False
    return True


# ----------------------------------------------------------------- teacher ---

def teacher_login(body) -> dict:
    """class.html: the teacher code off the card becomes the console token."""
    with _db_lock, connect() as conn:
        return access.teacher_login(conn, body.get("teacher_code"))


def teacher(body) -> dict:
    """pause / resume / reset_player / roster - all require the teacher token."""
    token = str(body.get("teacher_token", ""))
    action = str(body.get("action", ""))
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE teacher_token=?", (token,)).fetchone()
        if s is None:
            raise ApiError("not authorised", 403)
        access.check_active(s)
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
            cfg = econ_config(s)
            st = economy.new_state(cfg, econ_tick_now(cfg, s))
            conn.execute("UPDATE players SET cash=?, buildings='{}' WHERE id=?", (STARTING_CASH, row['id']))
            _save_state(conn,row['id'],cfg,st)
            conn.execute("DELETE FROM positions WHERE player_id=?", (row["id"],))
            _log(conn, code, row["id"], "reset_player", {"name": name})
        elif action not in ("pause", "resume", "roster"):
            raise ApiError("unknown teacher action")

        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        roster = []
        for row in conn.execute("SELECT * FROM players WHERE code=? ORDER BY name", (code,)):
            roster.append({"name": row["name"], "net_worth": int(row["econ_nw"]),
                           "joined_at": row["joined_at"]})
        roster.sort(key=lambda r: -r["net_worth"])
        for i, r in enumerate(roster):
            r["rank"] = i + 1
        return {"code": code, "paused": bool(s["paused"]), "minute": session_minute(s),
                "class_size": max(1, int(s["class_size"])), "roster": roster, "count": len(roster)}


def _teacher_auth(conn, data):
    token=data.get('teacher_token','')
    if isinstance(token,list): token=token[0] if token else ''
    s=conn.execute('SELECT * FROM sessions WHERE teacher_token=?',(str(token),)).fetchone()
    if s is None: raise ApiError('not authorised',403)
    access.check_active(s)
    return s


def teacher_econ(query):
    with _db_lock, connect() as conn:
        s=_teacher_auth(conn,query)
        cfg,cls,states,behind=_class_econ(conn,s)
        students=[]
        for row in conn.execute('SELECT * FROM players WHERE code=? ORDER BY id',(s['code'],)):
            st=states[row['id']];payload=econ_payload(cfg,st,cls,s,behind)
            families={}
            for ti in st['tierOf']:
                fam=cfg['tiers'][ti]['family'];families[fam]=families.get(fam,0)+1
            students.append(dict(name=row['name'],buildings=payload['buildings'],families=families,netWorth=payload['netWorth'],
                                  checklist=st['checklist'],gateOpen=payload['gateOpen'],tier=len(st['b']),tierName=payload['buildingName'],
                                  level=payload['level'],auto=payload['auto'],revenuePerDay=payload['revenuePerDay'],taxPaid=st['taxPaid'],behind=behind))
        students.sort(key=lambda p:-p['netWorth'])
        for i,p in enumerate(students): p['rank']=i+1
        return dict(modelVersion=cfg.get('version',3),code=s['code'],paused=bool(s['paused']),tick=cls['nextTick'],day=cls['nextTick']/economy.ticks_per_day(cfg),
                    goodSalesNeeded=cfg['gate']['goodSalesNeeded'],students=students,count=len(students),families=cfg['families'],
                    eventDefaults=dict(up=cfg['fun']['eventMagUp'],down=cfg['fun']['eventMagDown'],holdMin=cfg['fun']['eventHoldMin']))


def teacher_event(body):
    with _db_lock, connect() as conn:
        s=_teacher_auth(conn,body)
        cfg,cls,states,behind=_class_econ(conn,s)
        if cfg.get('version') == 4:
            raise ApiError('This economy uses fixed customer prices',409)
        if behind: raise ApiError('Catching up; retry after replay completes',409)
        family=body.get('family');headline=str(body.get('headline','')).strip()
        try: mag=float(body.get('mag'));hold=float(body.get('holdMin'))
        except (TypeError,ValueError): raise ApiError('mag and holdMin must be numbers')
        if family not in cfg['families']: raise ApiError('unknown family')
        if not math.isfinite(mag) or not cfg['fun']['priceMin']<=mag<=cfg['fun']['priceMax']: raise ApiError('magnitude out of range')
        if not math.isfinite(hold) or hold<=0: raise ApiError('holdMin must be positive')
        if not headline: raise ApiError('headline is required')
        event=dict(rumourTick=cls['k'],startTick=cls['k'],family=family,mag=mag,real=True,
                   holdTicks=economy.jsround(hold*60/cfg['global']['tick']),headline=headline[:240])
        events=json.loads(s['custom_events']);events.append(event)
        conn.execute('UPDATE sessions SET custom_events=? WHERE code=?',(json.dumps(events),s['code']))
        _log(conn,s['code'],None,'teacher_event',event)
        return dict(ok=True,event=event)


def _class_locked(fn):
    @functools.wraps(fn)
    def wrapped(data):
        with connect() as conn:
            token=data.get('token','');teacher_token=data.get('teacher_token','')
            if isinstance(token,list): token=token[0] if token else ''
            if isinstance(teacher_token,list): teacher_token=teacher_token[0] if teacher_token else ''
            # Anything but a string is a bad request, not a crash: bind '' so the
            # handler answers 401/403 instead of sqlite raising here.
            if not isinstance(token,str): token=''
            if not isinstance(teacher_token,str): teacher_token=''
            row=conn.execute('SELECT code FROM players WHERE token=?',(token,)).fetchone()
            if row is None and teacher_token:
                row=conn.execute('SELECT code FROM sessions WHERE teacher_token=?',(teacher_token,)).fetchone()
            code=row['code'] if row else data.get('code',SOLO_CODE)
            if isinstance(code,list): code=code[0] if code else SOLO_CODE
            if not isinstance(code,str): code=SOLO_CODE
        with _db_lock: lock=_class_locks.setdefault(code,threading.RLock())
        with lock: return fn(data)
    return wrapped


for _name in ('get_state','econ_state','econ_login','econ_sell','econ_level','econ_auto','econ_expand',
              'econ_upgrade','econ_reserve','econ_processing','econ_fulfill_order','econ_replace_order','econ_commit_order','econ_focus','econ_breakfast',
              'econ_contracts','econ_accept_contract','econ_ticker','econ_quiz','econ_keep','teacher_econ','teacher_event','trade_equity','join','teacher'):
    globals()[_name]=_class_locked(globals()[_name])
