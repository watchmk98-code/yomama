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
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import production_economy as economy
import crafting_pilot
import breakfast_event
import access
import autopilot
import alpaca_market
import port_portfolio
import quest_engine

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
CREATE TABLE IF NOT EXISTS standings (
    player_id INTEGER NOT NULL,
    day       INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    PRIMARY KEY (player_id, day)
);
"""

# Columns added after the first release. SQLite cannot express them in
# CREATE TABLE IF NOT EXISTS, so they are applied to existing databases here.
MIGRATIONS = (
    ("players", "port_state", "TEXT NOT NULL DEFAULT ''"),
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
    _settled.clear()
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

def _stage_config():
    """Stage the rules every new or reset class is stamped with.

    The quest engine replaces the 30 business quests, which were the only
    source of Prestige, so an engine class runs with the Prestige expansion
    qualification off; the three businesses it gated would otherwise be
    unreachable. Existing v4 classes keep their stored snapshot and never see
    either change until they are reset.
    """
    cfg = quest_engine.configure(crafting_pilot.configure(economy.load_config()))
    if quest_engine.enabled(cfg):
        cfg.setdefault('businessDesign', {})['prestigeExpansion'] = False
    return cfg


_startup_config = _stage_config()
_book_cache = {}
_class_locks = {}
_META_KEYS = {'tick', 'rngState', 'report', 'reportBaseline', 'lastRank', 'reportTick', 'rumour'}

# Zero-tick polls. Build pages poll every 3 s while a tick lasts 15 s, so most
# requests find the class clock exactly where the last pass left it. The full
# pass is then a no-op for every town - advance_class replays an empty tick
# range, only re-syncs pools, and re-saves byte-identical rows - so a
# read-only request may load and save the requesting town alone. The
# invariant behind the shortcut: every players row of the class is what a full
# pass THIS process committed at this tick under the stamped rules left there
# (_settled), every seat already has today's standings opening (the first
# save of a day writes it for everyone), and no migration branch of
# _class_econ applies. Whatever breaks it - a tick, an action, a login, a new
# or reset seat, re-stamped rules, a rolled-back pass, rows another process
# wrote - clears or misses the marker, and the next request takes the full pass.
FAST_POLL = True
_settled = {}   # class code -> (econ_tick, config key) of the last full pass committed here


def econ_config(session):
    cfg = json.loads(session['econ_config']) if session['econ_config'] else copy.deepcopy(_startup_config)
    if 'fun' not in cfg or (_startup_config.get('version') == 4 and cfg.get('version') != 4):
        cfg = copy.deepcopy(_startup_config)
    elif (cfg.get('version') == 4 and 'craftingPilot' in _startup_config
          and cfg.get('craftingPilot', {}).get('version', 0) < _startup_config['craftingPilot']['version']):
        # Existing v4 classes receive newer crafting rules without losing progress.
        cfg['craftingPilot'] = copy.deepcopy(_startup_config['craftingPilot'])
    cfg['global']['seed'] = int(session['class_seed']) or cfg['global']['seed']
    # The offline replay cap is a server setting, not a class rule: it bounds how
    # much of an absence the first request of the day replays for the whole
    # class in one go, so the value on disk wins over the one stamped at reset.
    hours = (_startup_config.get('runtime') or {}).get('offlineHours')
    if hours is not None:
        cfg.setdefault('runtime', {})['offlineHours'] = hours
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
    nw=economy.net_worth(st)
    conn.execute('UPDATE players SET econ=?, econ_meta=?, econ_nw=? WHERE id=?',
                 (json.dumps(core,separators=(',',':')),json.dumps(meta,separators=(',',':')),nw,player_id))
    # The first save of each day fixes that day's opening figure; the LEAD page
    # shows each seat's gain since today's, this week's and this month's.
    conn.execute('INSERT OR IGNORE INTO standings(player_id, day, net_worth) VALUES (?,?,?)',
                 (player_id,int(time.time()//86400),int(nw)))


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
    elif (cfg.get('version') == 4 and 'craftingPilot' in cfg
          and old.get('craftingPilot', {}).get('version', 0) < cfg['craftingPilot']['version']):
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',(json.dumps(cfg),session['code']))
    target=econ_tick_now(cfg,session)
    stop=target if cfg.get('version') == 4 else min(target,start+economy.jsround(cfg['runtime']['maxCatchupDays']*economy.ticks_per_day(cfg)))
    key=(session['code'],json.dumps(cfg,sort_keys=True))
    cls=_class_world(cfg,session,stop,key)
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
    _settled[session['code']]=(stop,key)
    return cfg,cls,states,stop<target


def _class_world(cfg, session, stop, key):
    """The shared context a pass runs in: price book, teacher events, pressure."""
    cls=economy.new_class(cfg,stop+economy.ticks_per_day(cfg),_book_cache.setdefault(key,economy.PriceBook(cfg)))
    cls['ev']+=json.loads(session['custom_events'])
    cls['ev'].sort(key=lambda e:e['startTick'])
    cls['pressure']=json.loads(session['pressure']) or [0.0]*len(cfg['tiers'])
    cls['incomePerHour']=session['income_per_hour']
    return cls


def _fast_poll(conn, player, session):
    """One town at zero ticks, or None when the class needs the full pass."""
    cfg=econ_config(session)
    old=json.loads(session['econ_config']) if session['econ_config'] else {}
    stop=session['econ_tick']
    if (not FAST_POLL or cfg.get('version')!=4 or old.get('version')!=4 or 'fun' not in old
            or econ_tick_now(cfg,session)!=stop): return None
    key=(session['code'],json.dumps(cfg,sort_keys=True))
    if _settled.get(session['code'])!=(stop,key): return None
    if conn.execute('SELECT COUNT(*) FROM players p WHERE p.code=? AND NOT EXISTS'
                    ' (SELECT 1 FROM standings s WHERE s.player_id=p.id AND s.day=?)',
                    (session['code'],int(time.time()//86400))).fetchone()[0]: return None
    st=_load_state(player,cfg,session)
    if st['tick']!=stop or st['offers'] is None: return None
    cls=_class_world(cfg,session,stop,key)
    cls['k']=max(0,stop-1);cls['nextTick']=stop
    # Exactly what the full pass does to this town at zero ticks.
    economy._sync_pools(cfg,st)
    breakfast_event.advance(st,stop*cfg['global']['tick'])
    economy.bind_sales(cfg,cls,st)
    st['lastActiveTick']=st['tick']
    if not session['paused']:
        import crafting_pilot
        crafting_pilot.visit(cfg,st)
    _save_state(conn,player['id'],cfg,st)
    return cfg,cls,st,False


def _player_econ(conn, player, session, fast=False):
    """This player's town at now. Only read-only polls may pass fast=True."""
    if fast:
        found=_fast_poll(conn,player,session)
        if found is not None: return found
    cfg,cls,states,behind=_class_econ(conn,session)
    st=states[player['id']]
    if cfg.get('version') == 4 and not behind:
        # Other students can replay a class, but cannot renew this player's
        # offline allowance. Only their own request records activity.
        st['lastActiveTick']=st['tick']
        if not session['paused']:
            import crafting_pilot
            crafting_pilot.visit(cfg,st)
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
        result['breakfastEvent'] = breakfast_event.payload(st, cls['nextTick'] * cfg['global']['tick'], cfg)
    else:
        result = _legacy_econ_payload(cfg, st, cls, session, behind)
    result['classCompetition'] = session['code'] != SOLO_CODE
    return result


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
            # A seat is shared by whoever holds its name and PIN, on any number of
            # devices. Say only that the PIN is wrong: suggesting another name once
            # turned a typo into a stray second seat.
            raise ApiError(
                f"Wrong PIN for {name}. Check the four digits you were given and try again.", 409)

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
        _settled.pop(code, None)
    return {"token": token, "name": name, "code": code, "rejoined": False}


def _leaderboard(conn, code: str, me_id: int) -> list:
    """Ranked by net worth from the engine - cash plus warehouse plus book.

    Read from the cached column so one student's poll does not replay the whole
    class; each student's own figure is refreshed as they play.
    """
    if code == SOLO_CODE:
        return []
    today = int(time.time() // 86400)
    openings = {}
    for r in conn.execute("SELECT s.player_id, s.day, s.net_worth FROM standings s"
                          " JOIN players p ON p.id = s.player_id WHERE p.code=?", (code,)):
        openings.setdefault(r["player_id"], {})[int(r["day"])] = int(r["net_worth"])

    def baseline(pid, days, now_nw):
        """The figure a period started from: the latest opening at or before the
        period's first day, else the earliest one inside it, else now (no gain)."""
        snaps = openings.get(pid, {})
        start = today - days + 1
        before = [d for d in snaps if d <= start]
        if before:
            return snaps[max(before)]
        within = [d for d in snaps if d > start]
        return snaps[min(within)] if within else now_nw

    board = []
    for r in conn.execute("SELECT id, name, econ_nw FROM players WHERE code=?", (code,)):
        nw = int(r["econ_nw"])
        board.append({"name": r["name"], "net_worth": nw, "you": r["id"] == me_id,
                      "gain": {key: nw - baseline(r["id"], days, nw)
                               for key, days in (("daily", 1), ("weekly", 7), ("monthly", 30))}})
    board.sort(key=lambda x: (-x["net_worth"], x["name"]))
    for i, entry in enumerate(board):
        entry["rank"] = i + 1
    return board


def get_state(query) -> dict:
    """Everything the dashboard needs in one round trip."""
    with _db_lock, connect() as conn:
        p, s = _auth(conn, query)
        cfg, book, st, behind = _player_econ(conn, p, s, fast=True)
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
                        "tick": st["tick"], "classCompetition": p["code"] != SOLO_CODE},
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
        cfg, book, st, behind = _player_econ(conn, p, s, fast=True)
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
        _settled.pop(p["code"], None)
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
        # A second tab can still display a slot that moved after a closure.
        # New clients identify the instance as well as its displayed slot.
        if 'slot' in body and 'buildingId' in body:
            slot = _index(body, 'slot')
            building_id = body.get('buildingId')
            if (not isinstance(building_id, str) or not building_id
                    or not 0 <= slot < len(st['b'])
                    or st['b'][slot].get('buildingId') != building_id):
                raise ApiError('This business changed; refresh and try again', 409)
        result = apply_fn(cfg, st, book)
        if not result.get("ok"):
            raise ApiError(result.get("why", "not allowed"), details=result)
        import crafting_pilot
        crafting_pilot.observe_rewards(cfg,st)
        _save_state(conn, p["id"], cfg, st)
        _settled.pop(p["code"], None)
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
        return breakfast_event.act(st, cls['nextTick'] * cfg['global']['tick'], body, cfg)
    return _act(body, apply)


def econ_business(body):
    """Apply one business intention inside the seat's class transaction."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Business operations unavailable')
        return economy.manage_business(cfg, st, body)
    return _act(body, apply)


def econ_craft(body):
    """Craft or purchase basic supplies inside the authenticated class save."""
    import crafting
    return _act(body, lambda cfg, st, cls: crafting.act(cfg, st, body))


def econ_progression(body):
    """Business quests and group milestones share the seat's atomic save."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Business progression unavailable')
        if body.get('action') == 'group_project_claim':
            return economy.claim_group_project(cfg, st, body.get('projectId'))
        if body.get('action') == 'legacy_project_deliver':
            return economy.fulfill_legacy_project(cfg, st, body.get('id'))
        import business_progression
        return business_progression.act(cfg, st, body)
    return _act(body, apply)


def econ_quests(body):
    """Claim a quest reward inside the seat's atomic save."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Quests unavailable')
        import quest_engine
        return quest_engine.act(cfg, st, body)
    return _act(body, apply)


def econ_focus_tree(body):
    """Start a town development focus in the authenticated class save."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Town focus tree unavailable')
        import focus_tree
        return focus_tree.act(cfg, st, body)
    return _act(body, apply)


def econ_workforce(body):
    """Permanent teams and HQ share the class transaction and economy clock."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Workforce development unavailable')
        import workforce
        return workforce.act(cfg, st, body)
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
        result=fn(cfg,st,offer,order_id=order_id)
        if result['ok'] and cfg.get('version')==4 and st.get('marketPendingGoods'):
            economy.market_orders.sync(cfg,st)
        return dict(result,kind='order_replace' if replace else 'order')
    return _act(body,apply)


def econ_fulfill_order(body):
    if 'orders' in body:
        return _act(body,lambda cfg,st,cls: economy.market_orders.fulfill_ready(cfg,st,body['orders'])
                    if cfg.get('version')==4 else dict(ok=False,why='Manual orders unavailable'))
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


def econ_customers(body):
    """Manage one recurring customer after authenticating the player's seat."""
    def apply(cfg, st, cls):
        if cfg.get('version') != 4:
            return dict(ok=False, why='Customer contracts unavailable')
        slot = _index(body, 'slot')
        action = body.get('action')
        if action not in ('accept', 'switch', 'release', 'pause', 'resume', 'upgrade', 'downgrade'):
            raise ApiError('Choose a customer contract action')
        customer_id = body.get('customerId')
        contract_id = body.get('contractId')
        if action in ('accept', 'switch'):
            if not isinstance(customer_id, str) or not customer_id or len(customer_id) > 100:
                raise ApiError('customerId is required')
        if action != 'accept':
            if not isinstance(contract_id, str) or not contract_id or len(contract_id) > 100:
                raise ApiError('contractId is required')
        return economy.manage_customer_contract(cfg, st, slot, action,
                                                customer_id=customer_id, contract_id=contract_id)
    return _act(body, apply)


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
        cfg,cls,st,behind=_player_econ(conn,p,s,fast=True)
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
            import quest_engine
            quest_engine.record_action(cfg, st, 'quiz_pass')
        _save_state(conn, p["id"], cfg, st)
        _settled.pop(p["code"], None)
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

def _port_payload(p, s, state, feed, permitted, reason):
    return {'portfolio': port_portfolio.public_state(state),
            'serverTime': time.time(),
            'executionRules': port_portfolio.execution_rules(
                extended_hours=bool(feed['market'].get('extendedHours'))),
            'quotes': feed['quotes'], 'market': feed['market'],
            'canTrade': permitted and feed['market']['status'] == 'open',
            'blockedReason': reason or (feed['market']['message']
                                        if feed['market']['status'] != 'open' else ''),
            'player': {'name': p['name']},
            'session': {'code': p['code'], 'paused': bool(s['paused'])}}


def _port_request(data, action=None):
    # The outer wrapper supplies trusted quotes before taking the class lock.
    # Recheck the seat, class and earned licence before portfolio execution.
    with _db_lock, connect() as conn:
        p, s = _auth(conn, data)
        cfg = econ_config(s)
        town = _load_state(p, cfg, s)
        licensed = economy.gate_open(cfg, town)
        import quest_engine
        # A class without the quest engine is gated exactly as before.
        quest_locked = quest_engine.enabled(cfg) and not quest_engine.has_feature(cfg, town, 'port_trading')
        reason = ('Earn your licence to unlock Port.' if not licensed else
                  'Complete the Network Effect quest to unlock Port.' if quest_locked else
                  'The class is paused.' if s['paused'] else '')
        permitted = not reason
        now = time.time()
        feed = alpaca_market.execution_feed(data['_server_port_feed'], now)
        status = feed['market']['status']
        market_open = True if status == 'open' else False if status == 'closed' else None
        bounds = dict(session_open=feed['market'].get('sessionOpen'),
                      session_close=feed['market'].get('sessionClose'),
                      resume_at=float(s['clock_base']))
        try:
            if action == 'settle' and not p['port_state']:
                return None  # A reset or deleted save wins over an earlier scan.
            state = port_portfolio.load_state(p['port_state'], now=now)
            if action == 'settle' and state['accountId'] != data['_server_port_account_id']:
                return None
            if action == 'order':
                if not permitted:
                    raise ApiError(reason, 409)
                state = port_portfolio.submit_order(state, data, feed['quotes'], now,
                                                    market_open=market_open, **bounds,
                                                    received_at=data['_server_received_at'], defer_execution=True,
                                                    session=feed['market'].get('session') or 'regular')
            elif action == 'cancel':
                if not permitted:
                    raise ApiError(reason, 409)
                # Record cancellation before remote I/O. The worker orders this
                # intent against its next observed event; no request can fill it.
                state = port_portfolio.cancel_order(state, data, {}, now,
                                                    market_open=None, **bounds,
                                                    received_at=data['_server_received_at'])
            elif action == 'settle' and permitted:
                state = port_portfolio.match_orders(state, feed['quotes'], now,
                                                    market_open=market_open, **bounds)
        except port_portfolio.PortError as error:
            raise ApiError(error.message, error.status, {'code': error.code}) from None
        encoded = json.dumps(state, separators=(',', ':'), allow_nan=False)
        if encoded != p['port_state']:
            conn.execute('UPDATE players SET port_state=? WHERE id=?', (encoded, p['id']))
        return _port_payload(p, s, state, feed, permitted, reason)


def port_state(query) -> dict:
    """The signed-in seat's portfolio. Browser demo saves never enter this API."""
    return _port_request(query)


def port_order(body) -> dict:
    """Create a virtual order using server prices and an idempotent request ID."""
    return _port_request(body, 'order')


def port_cancel(body) -> dict:
    """Cancel only an order in this seat's current account generation."""
    return _port_request(body, 'cancel')


def _port_settle(data):
    """Internal worker transition; never registered as an HTTP endpoint."""
    return _port_request(data, 'settle')


def process_pending_portfolios():
    """Settle every eligible saved portfolio on one shared server quote cycle.

    Scanning and provider calls hold no class lock. Each mutation rechecks the
    seat, class and account generation under its usual class lock.
    GET/POST requests cannot accelerate this execution timeline.
    """
    with _db_lock, connect() as conn:
        rows = conn.execute('SELECT p.token,p.port_state FROM players p JOIN sessions s '
                            'ON s.code=p.code WHERE s.active=1 AND s.paused=0 '
                            "AND p.port_state<>''").fetchall()
    work = []
    for row in rows:
        try:
            saved = port_portfolio.load_state(row['port_state'])
            if saved['positions'] or any(order['status'] == 'pending' for order in saved['ledger']['orders']):
                work.append((row['token'], saved['accountId']))
        except port_portfolio.PortError:
            continue  # Invalid saves remain intact for diagnosis through the API.
    if not work:
        return 0
    # Browser refreshes may populate the display cache; execution samples its
    # own fresh batch so students cannot steer fills by refreshing that cache.
    feed = alpaca_market.snapshot(port_portfolio.ALLOWED_SYMBOLS, force=True)
    settled = 0
    for token, account_id in work:
        try:
            _port_settle({'token': token, '_server_port_feed': feed,
                          '_server_port_account_id': account_id})
            settled += 1
        except ApiError:
            continue  # Revocation/kick changes during provider I/O win.
    return settled


def _port_chart_access(data):
    with _db_lock, connect() as conn:
        _auth(conn, data)


def port_chart(query) -> dict:
    """Historical stock prices, reauthorized after provider I/O completes."""
    _port_chart_access(query)
    return query['_server_port_chart']


def _port_with_chart(fn):
    @functools.wraps(fn)
    def wrapped(data):
        _port_chart_access(data)
        values = {}
        for key, default in (('symbol', 'AAPL'), ('range', '1W')):
            value = data.get(key, default)
            if isinstance(value, list):
                value = value[0] if len(value) == 1 else None
            if not isinstance(value, str):
                raise ApiError('Choose a valid stock and chart range.', 400)
            values[key] = value.strip().upper()
        if values['symbol'] not in port_portfolio.ALLOWED_SYMBOLS or values['range'] not in alpaca_market.CHART_RANGES:
            raise ApiError('Choose a valid stock and chart range.', 400)
        chart = alpaca_market.historical_chart(values['symbol'], values['range'])
        # Overwrite any similarly named browser field with the trusted response.
        return fn(dict(data, _server_port_chart=chart))
    return wrapped


_port_execution_lock = threading.RLock()


def _port_execution_locked(fn):
    """Serialize cancellation admission with settlement before class locking.

    The cancellation wrapper captures its trusted receipt only after acquiring
    this lock, then commits the intent before any later execution cycle can
    inspect that account. Provider network calls remain outside this section;
    cancellation uses only the non-blocking display-cache lookup.
    """
    @functools.wraps(fn)
    def wrapped(data):
        with _port_execution_lock:
            return fn(data)
    return wrapped


def _port_with_quotes(fn):
    """Provider I/O must not block classroom actions under the class lock."""
    @functools.wraps(fn)
    def wrapped(data):
        received_at = time.time()
        with _db_lock, connect() as conn:
            _auth(conn, data)
        # Cancellation must reach the ledger without waiting on the provider or
        # on its quote-cache lock; otherwise the worker could fill a later quote.
        feed = (alpaca_market.cached_snapshot(port_portfolio.ALLOWED_SYMBOLS)
                if fn.__name__ == 'port_cancel' else alpaca_market.snapshot(port_portfolio.ALLOWED_SYMBOLS))
        # Always overwrite this private field; a browser cannot supply quotes.
        return fn(dict(data, _server_port_feed=feed, _server_received_at=received_at))
    return wrapped

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


# ------------------------------------------------------------ provisioning ---
# Called by admin.py only; no HTTP route reaches these.

def reset_class(code: str) -> dict:
    """A new game for everyone in the class, under the rules on disk now.

    Every seat keeps its name, PIN and token - browsers stay signed in and
    the codes on the students' cards stay valid - but cash, buildings,
    goods, positions and the class clock start over. The class seed changes
    too, so a running server drops its cached price book for the class.
    """
    cfg = economy.load_config()
    now = time.time()
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            raise ApiError("no class with that code", 404)
        _settled.pop(code, None)
        conn.execute(
            "UPDATE sessions SET econ_config=?, class_seed=?, seed=?, paused=0, clock_base=?,"
            " clock_accum=0, started_at=?, econ_tick=0, pressure='[]', income_per_hour=1,"
            " custom_events='[]' WHERE code=?",
            (json.dumps(cfg, separators=(",", ":")), 1 + secrets.randbelow((1 << 30) - 1),
             secrets.randbelow(1 << 30), now, now, code))
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        cfg = econ_config(s)
        players = conn.execute("SELECT id FROM players WHERE code=?", (code,)).fetchall()
        for p in players:
            st = economy.new_state(cfg, 0, seed=cfg["global"]["seed"] * 48611 + p["id"] * 7 + 5)
            conn.execute("UPDATE players SET cash=?, buildings='{}', port_state='' WHERE id=?", (STARTING_CASH, p["id"]))
            conn.execute("DELETE FROM standings WHERE player_id=?", (p["id"],))   # gains start over too
            _save_state(conn, p["id"], cfg, st)
            conn.execute("DELETE FROM positions WHERE player_id=?", (p["id"],))
        _log(conn, code, None, "admin_reset_class", {"players": len(players), "version": cfg.get("version")})
    return {"code": code, "players": len(players), "version": cfg.get("version")}


def advance_class_clock(code: str, seconds: float, play: bool = False) -> dict:
    """Move a class forward in game time as if every student had kept playing.

    The class clock jumps ahead by `seconds` and every town is replayed
    through the whole span - buildings produce, shops sell, regular
    customers collect, construction finishes - with the offline allowance
    never running out, so nothing is skipped the way an absence is. Seats,
    PINs, tokens, codes, cash and buildings all stay; there is no way back.

    The jump is taken in slices no longer than the offline allowance, each
    in its own transaction: a running server waits for one slice at most,
    and a student's request between two slices is an ordinary visit.

    With `play`, a stand-in (autopilot.py) visits every town at the start
    of each slice and plays it the way a student would - ships orders,
    takes on regulars, buys businesses and upgrades - so the town grows,
    not only its cash. Every town gets its own stable personality.
    """
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ApiError("seconds must be a positive number")
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            raise ApiError("no class with that code", 404)
        _settled.pop(code, None)
        cfg = econ_config(s)
        # Everyone up to date under the ordinary rules first: an absence
        # before the jump stays an absence.
        _class_econ(conn, s)
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        before = int(s["econ_tick"])
        worth_before = {p["id"]: int(p["econ_nw"]) for p in
                        conn.execute("SELECT id, econ_nw FROM players WHERE code=?", (code,))}
    slice_seconds = max(float(cfg["global"]["tick"]),
                        min(4.0 if play else 6.0, float(cfg["runtime"].get("offlineHours", 12))) * 3600.0)
    played = {}
    done = 0.0
    while done < seconds:
        step = min(slice_seconds, seconds - done)
        with _db_lock, connect() as conn:
            s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
            cfg = econ_config(s)
            here = int(s["econ_tick"])
            # Present from here on: the allowance covers the slice, so the
            # replay pays every tick of it.
            for p in conn.execute("SELECT * FROM players WHERE code=? ORDER BY id", (code,)):
                st = _load_state(p, cfg, s)
                changed = False
                if play:
                    visit = autopilot.visit(cfg, st, autopilot.seat_seed(cfg, p["id"]), here)
                    tally = played.setdefault(p["id"], dict(visits=0, orders=0, customers=0, builds=0, upgrades=0, focus=0))
                    if not visit["skipped"]:
                        tally["visits"] += 1
                        for key in ("orders", "customers", "builds", "upgrades", "focus"):
                            tally[key] += visit[key]
                        changed = True
                if int(st.get("lastActiveTick", 0)) < here:
                    st["lastActiveTick"] = here
                    changed = True
                if changed:
                    _save_state(conn, p["id"], cfg, st)
            conn.execute("UPDATE sessions SET clock_accum=clock_accum+? WHERE code=?", (step, code))
            s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
            _class_econ(conn, s)
        done += step
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        after = int(s["econ_tick"])
        players = []
        for p in conn.execute("SELECT * FROM players WHERE code=? ORDER BY name", (code,)):
            st = _load_state(p, cfg, s)
            players.append(dict(name=p["name"], before=worth_before.get(p["id"], 0), after=int(p["econ_nw"]),
                                buildings=len(st["b"]) + len(st.get("queue") or []) + (1 if st.get("build") else 0),
                                regulars=len(st.get("customerContracts", {}).get("active", [])),
                                played=played.get(p["id"])))
        _log(conn, code, None, "admin_advance_clock",
             {"seconds": seconds, "tick_before": before, "tick_after": after, "players": len(players), "play": bool(play)})
    return {"code": code, "label": s["label"], "seconds": seconds, "tick_before": before, "tick_after": after,
            "days": round((after - before) / economy.ticks_per_day(cfg), 2), "play": bool(play), "players": players}


def ensure_class(code, teacher_code, label="", class_size=30) -> dict:
    """A class with GIVEN codes - a roster import. Creates it, or refreshes the
    teacher code, label and size of an existing one. Never touches progress."""
    code = "".join(str(code or "").split()).upper()
    teacher_code = "".join(str(teacher_code or "").split()).upper()
    if not re.fullmatch(r"[A-Z0-9]{4,8}", code) or not re.fullmatch(r"[A-Z0-9]{4,8}", teacher_code):
        raise ApiError("codes are 4 to 8 letters or digits")
    label = " ".join(str(label or "").split())[:40]
    class_size = max(1, min(200, int(class_size or 30)))
    cfg = economy.load_config()
    now = time.time()
    with _db_lock, connect() as conn:
        clash = conn.execute("SELECT code FROM sessions WHERE teacher_code=? AND code<>?",
                             (teacher_code, code)).fetchone()
        if clash is not None:
            raise ApiError(f"teacher code {teacher_code} already belongs to class {clash['code']}", 409)
        s = conn.execute("SELECT code FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            conn.execute(
                "INSERT INTO sessions(code, teacher_token, seed, created_at, paused, clock_base,"
                " clock_accum, class_size, class_seed, started_at, econ_config, teacher_code, label)"
                " VALUES (?,?,?,?,0,?,0,?,?,?,?,?,?)",
                (code, secrets.token_urlsafe(24), secrets.randbelow(1 << 30), now, now, class_size,
                 1 + secrets.randbelow((1 << 30) - 1), now, json.dumps(cfg, separators=(",", ":")),
                 teacher_code, label))
            _log(conn, code, None, "admin_import_class", {"label": label, "class_size": class_size})
        else:
            conn.execute("UPDATE sessions SET teacher_code=?, label=?, class_size=? WHERE code=?",
                         (teacher_code, label, class_size, code))
    return {"code": code, "teacher_code": teacher_code, "created": s is None}


def ensure_seat(code, name, pin) -> dict:
    """A seat with a GIVEN name and PIN - a roster import. Creates it exactly
    as join() would, or sets the PIN of an existing one. Never touches progress."""
    code = "".join(str(code or "").split()).upper()
    name = " ".join(str(name or "").split())[:24].upper()
    pin = str(pin or "").strip()
    if not name:
        raise ApiError("a seat needs a name")
    if not (pin.isdigit() and len(pin) == 4):
        raise ApiError(f"{name}: the PIN must be 4 digits")
    with _db_lock, connect() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE code=?", (code,)).fetchone()
        if s is None:
            raise ApiError("no class with that code", 404)
        p = conn.execute("SELECT id, pin FROM players WHERE code=? AND name=?", (code, name)).fetchone()
        if p is not None:
            if str(p["pin"]) != pin:
                conn.execute("UPDATE players SET pin=? WHERE id=?", (pin, p["id"]))
                _log(conn, code, p["id"], "admin_set_pin", {"name": name})
            return {"code": code, "name": name, "created": False}
        cfg = econ_config(s)
        st = economy.new_state(cfg, econ_tick_now(cfg, s))
        cur = conn.execute(
            "INSERT INTO players(code, name, token, joined_at, cash, pin, econ, econ_nw)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (code, name, secrets.token_urlsafe(24), time.time(), STARTING_CASH, pin,
             json.dumps(st, separators=(",", ":")), int(economy.net_worth(cfg, st))))
        _log(conn, code, cur.lastrowid, "admin_import_seat", {"name": name})
        _settled.pop(code, None)
    return {"code": code, "name": name, "created": True}


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
            conn.execute("UPDATE players SET cash=?, buildings='{}', port_state='' WHERE id=?", (STARTING_CASH, row['id']))
            conn.execute("DELETE FROM standings WHERE player_id=?", (row['id'],))
            _save_state(conn,row['id'],cfg,st)
            conn.execute("DELETE FROM positions WHERE player_id=?", (row["id"],))
            _log(conn, code, row["id"], "reset_player", {"name": name})
            _settled.pop(code, None)
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
            # Reuse the student's authoritative view, including reserved stock
            # and the goods-sold alternative to the delivery licence milestone.
            students[-1].update({key: payload[key] for key in (
                'cash', 'warehouseStored', 'warehouseCap', 'warehouseFillPercent', 'overflowing', 'build')})
            if cfg.get('version') == 4:
                students[-1].update({key: payload[key] for key in (
                    'materials', 'incomePerMinute', 'productionPerMinute', 'customerUnitsSold',
                    'customerUnitsNeeded', 'regularDeliveries', 'townProjects', 'nextStep', 'nextGoal')})
                customers=payload['customerContracts'];active=customers['active']
                offers=payload['contracts']['offers']
                workshop=payload['breakfastEvent']
                students[-1].update(
                    deliveriesCompleted=st['cStats']['done'],
                    readyDeliveries=sum(bool(order['canFulfill']) for order in offers),
                    deliverySlots=len(offers),
                    customerContracts=dict(slots=customers['slots'],active=len(active),
                        supplying=sum(c['status']=='supplying' for c in active),
                        waiting=sum(c['status']=='waiting' for c in active),
                        paused=sum(c['status']=='paused' for c in active),
                        deliveries=customers['deliveries'],earned=customers['earned']),
                    breakfastEvent={key: workshop[key] for key in ('status','locked','stage') if key in workshop})
                if 'operations' in payload:
                    students[-1]['operations']=payload['operations']
                if 'progression' in payload:
                    progression=payload['progression']
                    students[-1]['progression']=dict(enabled=progression['enabled'],
                        knowHow=progression['knowHow'],prestige=progression['prestige'],
                        questsCompleted=sum(q['status']=='done' for q in progression['quests']),
                        questsReady=sum(bool(q['ready']) for q in progression['quests']),
                        researchCompleted=sum(bool(r['owned']) for r in progression['research']),
                        equipmentOwned=sum(e['quantity'] for e in progression['equipment']))
        students.sort(key=lambda p:-p['netWorth'])
        for i,p in enumerate(students): p['rank']=i+1
        result=dict(modelVersion=cfg.get('version',3),code=s['code'],label=s['label'],classSize=max(1,int(s['class_size'])),
                    paused=bool(s['paused']),tick=cls['nextTick'],day=cls['nextTick']/economy.ticks_per_day(cfg),gateTier=cfg['global']['gateTier'],
                    goodSalesNeeded=cfg['gate']['goodSalesNeeded'],students=students,count=len(students),families=cfg['families'],
                    eventDefaults=dict(up=cfg['fun']['eventMagUp'],down=cfg['fun']['eventMagDown'],holdMin=cfg['fun']['eventHoldMin']))
        result['licenceRequirements']=dict(productionLevel=cfg['gate']['levelNeeded'],
            customerLevel=2 if cfg.get('version') == 4 else cfg['global']['a1Mult'],
            deliveries=cfg['gate']['goodSalesNeeded'],buildings=cfg['global']['gateTier'],
            checklistText=cfg['gate']['checklist'])
        if cfg.get('version') == 4:
            result['licenceRequirements']['customerUnits']=100
        return result


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
        with lock:
            try: return fn(data)
            except BaseException:
                # The transaction rolled back with the handler, any class pass
                # inside it too: its rows are not settled after all.
                _settled.pop(code,None);raise
    return wrapped


for _name in ('port_state','port_order','port_cancel','port_chart','_port_chart_access','_port_settle','get_state','econ_state','econ_login','econ_sell','econ_level','econ_auto','econ_expand',
              'econ_upgrade','econ_reserve','econ_processing','econ_fulfill_order','econ_replace_order','econ_commit_order','econ_focus','econ_breakfast',
              'econ_business','econ_progression','econ_workforce','econ_craft','econ_quests','econ_focus_tree',
              'econ_contracts','econ_accept_contract','econ_customers','econ_ticker','econ_quiz','econ_keep','teacher_econ','teacher_event','trade_equity','join','teacher'):
    globals()[_name]=_class_locked(globals()[_name])

for _name in ('port_state', 'port_order', 'port_cancel'):
    globals()[_name] = _port_with_quotes(globals()[_name])

# Outermost wrappers enforce PORT admission -> class -> database lock order.
# In particular, cancellation's receipt is recorded inside this admission lock.
port_cancel = _port_execution_locked(port_cancel)
_port_settle = _port_execution_locked(_port_settle)

port_chart = _port_with_chart(port_chart)
