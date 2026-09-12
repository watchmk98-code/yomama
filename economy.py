"""Faithful whole-YM v3 engine. Browser code never calculates the economy.

State is JSON-safe; transient RNG and sale hooks are attributes of State.
Reference-only bot strategies live in tests/sim.py. auto_continue is the
production optimizer used once when an unattended build empties the queue.
"""
from __future__ import annotations
import copy
import json
import math
from array import array
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / 'config/economy.v3.json'

def load_config(path=CONFIG_PATH):
    with open(path, encoding='utf8') as f:
        return json.load(f)


def jsround(x):
    return math.floor(x + 0.5)


class rng:
    def __init__(self, seed):
        self.s = (int(seed) & 0xffffffff) or 1

    def __call__(self):
        s = self.s
        s ^= (s << 13) & 0xffffffff
        s ^= s >> 17
        s ^= (s << 5) & 0xffffffff
        self.s = s & 0xffffffff
        return self.s / 4294967296


def gauss(r):
    u = v = 0
    while u == 0:
        u = r()
    while v == 0:
        v = r()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def ticks_per_day(cfg): return jsround(86400 / cfg['global']['tick'])
def ticks_per_hour(cfg): return jsround(3600 / cfg['global']['tick'])


class State(dict):
    """Runtime hooks are deliberately excluded from serialized engine state."""
    on_sold = None
    on_continue = None

    def random(self):
        r = rng(self.get('rngState', 1))
        value = r()
        self['rngState'] = r.s
        return value


def new_state(cfg, start_tick=0, seed=1):
    return State(cash=0, b=[dict(lv=1, auto=1, tier=0)], tierOf=[0], pend={},
                 book=cfg['tiers'][0]['baseCost'], build=None, queue=[], taxPaid=0,
                 unlock={'0': 0}, gateDay=None, lastLogin=0, catchupUntil=-1,
                 contracts=[], offers=None, cStats=dict(accepted=0, done=0, failed=0, net=0),
                 checklist=dict(lv25=False, auto=False, goodSales=0, quiz=False),
                 keepPercent=None, tick=start_tick, rngState=seed,
                 report=dict(produced=0, overflowSold=0, overflowCost=0, builds=0))


class PriceBook:
    """Append-only float32 streams, with double precision internal OU state."""
    def __init__(self, cfg, class_seed=None):
        self.cfg = cfg
        self.seed = cfg['global']['seed'] if class_seed is None else class_seed
        self.entries = {}

    def at(self, ti, k):
        if k < 0: return 1.0
        if ti not in self.entries:
            self.entries[ti] = [array('f'), rng(self.seed * 1000 + ti + 1), 1.0]
        a, r, m = self.entries[ti]
        g, t = self.cfg['global'], self.cfg['tiers'][ti]
        fam = self.cfg['families'][t['family']]
        if len(a) <= k:
            for _ in range(max(k + 1, len(a) + ticks_per_day(self.cfg)) - len(a)):
                m += g['theta'] * (1 - m) + t['sigma'] * gauss(r)
                m = min(fam['bandMax'], max(fam['bandMin'], m))
                a.append(m)
            self.entries[ti][2] = m
        return a[k]


def price_streams(cfg, ticks):
    book = PriceBook(cfg)
    return [array('f', (book.at(i, k) for k in range(ticks))) for i in range(len(cfg['tiers']))]


def event_schedule(cfg, ticks):
    g, f = cfg['global'], cfg['fun']
    if not f['events']: return []
    r, events = rng(g['seed'] * 7777 + 13), []
    t = jsround(ticks_per_hour(cfg) * f['eventFirstH'])
    families = list(cfg['families'])
    while t < ticks:
        family = families[math.floor(r() * len(families))]
        up = r() < f['eventUpChance']
        mag = (1 + (f['eventMagUp'] - 1) * (f['eventMagBase'] + f['eventMagSpread'] * r()) if up
               else 1 - (1 - f['eventMagDown']) * (f['eventMagBase'] + f['eventMagSpread'] * r()))
        events.append(dict(rumourTick=t-jsround(f['rumourLeadMin']*60/g['tick']), startTick=t,
                           family=family, mag=mag, real=r()<f['rumourTruth'],
                           holdTicks=jsround(f['eventHoldMin']*60/g['tick'])))
        t += jsround(ticks_per_hour(cfg)*f['eventEveryH']*(f['eventIntervalBase']+f['eventIntervalSpread']*r()))
    return events


def event_mult(cfg, ev, fam, k):
    f, tick = cfg['fun'], cfg['global']['tick']
    ramp, decay = jsround(f['eventRampMin']*60/tick), jsround(f['eventDecayMin']*60/tick)
    m = 1
    for e in ev:
        if not e['real'] or e['family'] != fam: continue
        dt = k-e['startTick']
        if dt < 0 or dt > ramp+e['holdTicks']+decay: continue
        w = 1
        if dt < ramp: w = dt/ramp
        elif dt > ramp+e['holdTicks']: w = 1-(dt-ramp-e['holdTicks'])/decay
        m *= 1+(e['mag']-1)*w
    return m


def rumour_now(cfg, ev, k):
    for e in ev:
        if e['rumourTick'] <= k < e['startTick']:
            return dict(family=e['family'], up=e['mag']>1)
    return None


def ms(cfg, lv):
    m = 1
    for milestone in cfg['milestones']:
        if lv >= milestone['lv']: m *= milestone['mult']
    return m


def set_mult(cfg, st, bi):
    f = cfg['fun']
    if not f['setBonus']: return 1
    t, m = cfg['tiers'][st['tierOf'][bi]], 1
    owned = [cfg['tiers'][i] for i in st['tierOf']]
    if sum(x['family']==t['family'] for x in owned) >= f['setSize']: m *= 1+f['setFamilyPct']/100
    if sum(x['row']==t['row'] for x in owned) >= f['setSize']: m *= 1+f['setRowPct']/100
    return m


def bRev(cfg, st, bi):
    b = st['b'][bi]
    return jsround(cfg['tiers'][st['tierOf'][bi]]['rev']*b['lv']*ms(cfg,b['lv'])*b['auto']*set_mult(cfg,st,bi))


def revS(cfg, st): return sum(bRev(cfg, st, i) for i in range(len(st['b'])))


def tax_rate(cfg, y):
    brackets = sorted([dict(above=0, rate=0)]+cfg['tax'], key=lambda b:b['above'])
    tx = 0
    for last, cur in zip(brackets, brackets[1:]):
        if y > last['above']: tx += (min(y,cur['above'])-last['above'])*last['rate']
    last = brackets[-1]
    if y > last['above']: tx += (y-last['above'])*last['rate']
    return tx/y if y>0 else 0


def net(cfg, st, gross):
    tx = jsround(gross*tax_rate(cfg,revS(cfg,st)*ticks_per_day(cfg)))
    st['taxPaid'] += tx
    return jsround(gross)-tx


def expand_options(cfg, st):
    owned = set(st['tierOf']+st['queue']+([st['build']['i']] if st['build'] else []))
    return [i for i in range(len(cfg['tiers'])) if i not in owned][:cfg['global']['frontier']]


def level_cost(cfg, st, bi):
    b = st['b'][bi]
    if b['lv'] >= cfg['global']['maxLevel']: return None
    return jsround(cfg['tiers'][st['tierOf'][bi]]['baseCost']*math.pow(cfg['global']['growth'],b['lv']))


def auto_cost(cfg, st, bi):
    g, b = cfg['global'], st['b'][bi]
    base = cfg['tiers'][st['tierOf'][bi]]['baseCost']
    if b['auto']==1: return jsround(g['a1Cost']*base)
    if b['auto']==g['a1Mult']:
        if g['a2NeedsNextTier'] and bi>=len(st['b'])-1: return None
        return jsround(g['a2Cost']*base)
    return None


def buy_level(cfg, st, bi):
    if not 0 <= bi < len(st['b']): return dict(ok=False,why='unknown building slot')
    c = level_cost(cfg,st,bi)
    if c is None: return dict(ok=False,why='max level')
    if st['cash'] < c: return dict(ok=False,why=f'need {c} YM')
    st['cash'] -= c; st['book'] += c; st['b'][bi]['lv'] += 1
    if st['b'][bi]['lv']>=cfg['gate']['levelNeeded']: st['checklist']['lv25']=True
    return dict(ok=True,cost=c)


def buy_auto(cfg, st, bi):
    if not 0 <= bi < len(st['b']): return dict(ok=False,why='unknown building slot')
    c = auto_cost(cfg,st,bi)
    if c is None: return dict(ok=False,why='not available')
    if st['cash'] < c: return dict(ok=False,why=f'need {c} YM')
    st['cash'] -= c; st['book'] += c
    g = cfg['global']
    st['b'][bi]['auto'] = g['a1Mult'] if st['b'][bi]['auto']==1 else g['a1Mult']*g['a2Mult']
    st['checklist']['auto'] = True
    return dict(ok=True,cost=c)


def can_expand(cfg, st, ti):
    g = cfg['global']; q = len(st['queue'])+bool(st['build'])
    if q >= g['queueDepth']: return dict(ok=False,why='build queue full')
    if q==0 and st['b'][-1]['lv']<g['gradLv']: return dict(ok=False,why=f"newest building must be level {g['gradLv']}")
    opts = expand_options(cfg,st)
    if ti not in opts: return dict(ok=False,why='not on the frontier',frontier=opts)
    c = cfg['tiers'][ti]['baseCost']
    if st['cash']<c: return dict(ok=False,why=f'need {c} YM')
    return dict(ok=True,cost=c)


def expand(cfg, st, ti, tick):
    result = can_expand(cfg,st,ti)
    if not result['ok']: return result
    st['cash'] -= result['cost']; st['book'] += result['cost']
    if st['build'] is None:
        st['build'] = dict(t=tick+jsround(cfg['tiers'][ti]['timerH']*3600/cfg['global']['tick']),i=ti)
    else: st['queue'].append(ti)
    return result


def sold(st, ti, value):
    if st.on_sold: st.on_sold(ti,value)


def sell_one(cfg, st, bi, price, manual=True):
    if not 0 <= bi < len(st['b']): return dict(ok=False,why='unknown building slot')
    v = st['pend'].get(str(bi),0)
    if v<=0: return dict(ok=False,why='nothing to sell')
    gross = jsround(v*price*(1+cfg['fun']['premiumSalePct']/100 if manual else 1))
    n = net(cfg,st,gross); st['cash'] += n; st['pend'][str(bi)] = 0
    if price >= cfg['gate']['goodSalePrice']-1e-6 and price>1: st['checklist']['goodSales'] += 1
    sold(st,st['tierOf'][bi],v)
    return dict(ok=True,gross=gross,net=n,tax=gross-n)


def sell_all(cfg, st, mk=None, k=0, manual=False):
    for bi, ti in enumerate(st['tierOf']):
        v = st['pend'].get(str(bi),0)
        if v<=0: continue
        rum = st.get('rumour')
        if manual and cfg['fun']['botsReact'] and rum and rum['up'] and rum['family']==cfg['tiers'][ti]['family']: continue
        m = mk(ti) if mk else 1
        gross = jsround(v*m*(1+cfg['fun']['premiumSalePct']/100 if manual else 1))
        st['cash'] += net(cfg,st,gross); st['pend'][str(bi)]=0
        sold(st,ti,v)


def auto_continue(cfg, st, tick):
    """One optimizer purchase round required by reference finishBuild.

    No session scheduler or test-bot strategy is used in the server.
    """
    g = cfg['global']
    for _ in range(cfg['runtime']['purchaseGuard']):
        opts = []
        for bi,b in enumerate(st['b']):
            t = cfg['tiers'][st['tierOf'][bi]]
            c = level_cost(cfg,st,bi)
            if c is not None:
                d = t['rev']*(b['lv']+1)*ms(cfg,b['lv']+1)*b['auto']*set_mult(cfg,st,bi)-bRev(cfg,st,bi)
                opts.append(('level',bi,c,d))
            c = auto_cost(cfg,st,bi)
            if c is not None:
                mult = g['a1Mult'] if b['auto']==1 else g['a2Mult']
                opts.append(('auto',bi,c,bRev(cfg,st,bi)*(mult-1)))
        q = len(st['queue'])+bool(st['build'])
        if q<g['queueDepth'] and (q>0 or st['b'][-1]['lv']>=g['gradLv']):
            candidates = expand_options(cfg,st)
            def score(i):
                t = cfg['tiers'][i]
                n = sum(cfg['tiers'][ti]['family']==t['family'] for ti in st['tierOf'])
                bonus = 1+cfg['fun']['setFamilyPct']/100 if n>=cfg['fun']['setSize']-1 and cfg['fun']['setBonus'] else 1
                return t['rev']*bonus*(1+cfg['runtime']['familyProgressWeight']*n)/t['baseCost']
            if candidates:
                ti = max(candidates,key=score)
                opts.append(('expand',ti,cfg['tiers'][ti]['baseCost'],cfg['tiers'][ti]['rev']))
        aff = [o for o in opts if o[2]<=st['cash']]
        if not aff: break
        best = next((o for o in aff if o[0]=='expand'),None) or max(aff,key=lambda o:o[3]/o[2])
        kind, i, c, d = best
        if kind=='expand': expand(cfg,st,i,tick)
        else:
            st['cash']-=c; st['book']+=c
            if kind=='level': st['b'][i]['lv']+=1
            else: st['b'][i]['auto']=g['a1Mult'] if st['b'][i]['auto']==1 else g['a1Mult']*g['a2Mult']


def finish_build(cfg, st, k, DAY=None):
    DAY = DAY or ticks_per_day(cfg)
    i = st['build']['i']
    st['b'].append(dict(lv=1,auto=1,tier=i)); st['tierOf'].append(i); st['build']=None
    st['unlock'][str(len(st['b'])-1)] = k/DAY
    st['report']['builds'] += 1
    if st['gateDay'] is None and len(st['b'])>=cfg['global']['gateTier']: st['gateDay']=k/DAY
    if st['queue']:
        j = st['queue'].pop(0)
        st['build']=dict(t=k+jsround(cfg['tiers'][j]['timerH']*3600/cfg['global']['tick']),i=j)
    elif cfg['global']['autoContinue']:
        sell_all(cfg,st,None,k,False)
        (st.on_continue or auto_continue)(cfg,st,k)


def offer_contracts(cfg, st, k, DAY=None):
    f = cfg['fun']
    if not f['contracts']: return
    st['offers']=[]
    for _ in range(f['contractOffers']):
        bi = math.floor(st.random()*len(st['b'])); rate = bRev(cfg,st,bi)
        if rate<=0: continue
        hours = f['contractTargetH']*(f['contractTargetBase']+f['contractTargetSpread']*st.random())
        # Reference uses a fixed 240 here, even in configs with a different tick.
        target = jsround(rate*hours*f['contractOutputTicksPerHour'])
        rew = f['contractRewardPct']*(f['contractRewardBase']+f['contractRewardSpread']*st.random())/100
        st['offers'].append(dict(bi=bi,target=target,reward=jsround(target*rew),
                                penalty=jsround(target*rew*f['contractPenaltyPct']/f['contractRewardPct']),
                                deadline=k+jsround(f['contractWindowH']*3600/cfg['global']['tick'])))


def accept_contract(cfg, st, offer_idx, k):
    if not st['offers'] or not 0<=offer_idx<len(st['offers']): return dict(ok=False,why='no such offer')
    if len(st['contracts'])>=cfg['fun']['contractSlots']: return dict(ok=False,why='no free slot')
    o = st['offers'].pop(offer_idx)
    st['contracts'].append(dict(o,delivered=0)); st['cStats']['accepted']+=1
    return dict(ok=True,contract=o)


def tick_contracts(cfg, st, k, produced):
    for c in st['contracts']:
        p = produced.get(c['bi'],0); take=min(p,c['target']-c['delivered'])
        if take>0: c['delivered']+=take; produced[c['bi']]=p-take
    for c in st['contracts'][:]:
        if c['delivered']>=c['target']:
            st['cash'] += net(cfg,st,c['target']+c['reward'])
            st['cStats']['done']+=1; st['cStats']['net']+=c['reward']; st['contracts'].remove(c)
        elif k>=c['deadline']:
            st['cash']=max(0,st['cash']-c['penalty'])
            st['cStats']['failed']+=1; st['cStats']['net']-=c['penalty']; st['contracts'].remove(c)


def new_class(cfg, ticks=0, book=None):
    return dict(streams=book or PriceBook(cfg),ev=event_schedule(cfg,ticks),
                pressure=[0.0]*len(cfg['tiers']),incomePerHour=1,k=0)


def class_price(cfg, cls, ti, k):
    fam = cfg['tiers'][ti]['family']
    streams = cls['streams']
    base = streams.at(ti,k) if isinstance(streams,PriceBook) else streams[ti][k]
    m = base*event_mult(cfg,cls['ev'],fam,k)
    f = cfg['fun']
    if f['pressure']:
        depth=cfg['families'][fam]['depth']*cls['incomePerHour']
        m-=min(f['pressureCap'],cls['pressure'][ti]/max(1,depth))
    return max(f['priceMin'],min(f['priceMax'],m))


def class_tick(cfg, cls, players, k):
    f = cfg['fun']; hour=ticks_per_hour(cfg)
    if f['pressure']:
        d=math.pow(0.5,1/(f['pressureHalfLifeMin']*60/cfg['global']['tick']))
        for i in range(len(cls['pressure'])): cls['pressure'][i]*=d
    if k%hour==0: cls['incomePerHour']=max(1,sum(revS(cfg,st) for st in players)*hour)
    cls['k']=k


def bind_sales(cfg, cls, st):
    def on_sold(ti,v):
        if cfg['fun']['pressure']: cls['pressure'][ti]+=v
    st.on_sold=on_sold


def warehouse_cap(cfg, st):
    total=revS(cfg,st); cap=total*cfg['global']['whHours']*ticks_per_hour(cfg)+1
    return [jsround(cap*(bRev(cfg,st,bi)/total if total else 1))+1 for bi in range(len(st['b']))]


def player_tick(cfg, cls, st, k):
    g,f=cfg['global'],cfg['fun']; day=ticks_per_day(cfg)
    st['rumour']=rumour_now(cfg,cls['ev'],k); bind_sales(cfg,cls,st)
    if st['build'] is not None and k>=st['build']['t']: finish_build(cfg,st,k,day)
    if f['contracts'] and k%day==0: offer_contracts(cfg,st,k,day)
    boost=g['catchupMult'] if k<st['catchupUntil'] else 1
    produced={bi:jsround(bRev(cfg,st,bi)*boost) for bi in range(len(st['b']))}
    st['report']['produced']+=sum(produced.values())
    if f['contracts']: tick_contracts(cfg,st,k,produced)
    caps=warehouse_cap(cfg,st)
    for bi in range(len(st['b'])):
        key=str(bi); st['pend'][key]=st['pend'].get(key,0)+produced[bi]
        if st['pend'][key]>caps[bi]:
            ov=st['pend'][key]-caps[bi]; st['pend'][key]=caps[bi]; ti=st['tierOf'][bi]
            price=class_price(cfg,cls,ti,k); gross=jsround(ov*price*(1-g['overflowDisc']))
            st['cash']+=net(cfg,st,gross); sold(st,ti,ov)
            st['report']['overflowSold']+=ov
            st['report']['overflowCost']+=jsround(ov*price)-gross
    st['tick']=k+1


def on_login(cfg, st, k=None):
    k = st['tick'] if k is None else k
    g=cfg['global']; hour=ticks_per_hour(cfg)
    if st['lastLogin']>0 and k-st['lastLogin']>=g['catchupAbsenceH']*hour:
        st['catchupUntil']=k+jsround(g['catchupHours']*hour)
    st['lastLogin']=k


def gate_open(cfg, st):
    c=st['checklist']
    return len(st['b'])>=cfg['global']['gateTier'] and c['lv25'] and c['auto'] and c['goodSales']>=cfg['gate']['goodSalesNeeded'] and c['quiz']


def net_worth(cfg_or_state, st=None):
    st = cfg_or_state if st is None else st
    return st['cash']+sum(st['pend'].values())+st['book']


def advance_class(cfg, cls, players, start, target):
    for k in range(start,target):
        active=[st for st in players if st['tick']<=k]
        class_tick(cfg,cls,active,k)
        for st in active: player_tick(cfg,cls,st,k)
