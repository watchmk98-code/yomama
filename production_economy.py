"""Authoritative v4 production economy; v3 remains in economy.py as an oracle.

Goods and YM are whole integers. Recipe completion debits inputs atomically;
retail and deliveries debit the same inventory. Fixed-point work survives JSON
reloads. Nothing spends player cash without an explicit purchase action.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import economy as legacy
from economy import *  # Stable public helpers used by the classroom API.

CONFIG_PATH = Path(__file__).parent / 'config/economy.v4.json'

# Free offer rolls; rewards are paid only after the required goods are delivered.
ORDER_ROLLS = (
    dict(id='standard', label='Standard', chance=65, items=0, quantityPercent=100, payoutPercent=100),
    dict(id='large', label='Large order', chance=25, items=3, quantityPercent=150, payoutPercent=130),
    dict(id='rare', label='Rare order', chance=8, items=4, quantityPercent=200, payoutPercent=175),
    dict(id='jackpot', label='Jackpot order', chance=2, items=5, quantityPercent=250, payoutPercent=250),
)


def load_config(path=CONFIG_PATH):
    with open(path, encoding='utf8') as source:
        return json.load(source)


def catalog(cfg):
    return {g['id']:dict(g, tier=i, buildingId=t['id'])
            for i,t in enumerate(cfg['tiers']) for g in t['goods']}


def _valid_slot(st, slot):
    return type(slot) is int and 0 <= slot < len(st['b'])


def _building(tier, lv=1, sales=1, storage=1):
    return dict(tier=tier,lv=lv,auto=sales,sales=sales,storage=storage,reserve=False,processing=True)


def new_state(cfg, start_tick=0, seed=1):
    st=legacy.new_state(cfg,start_tick,seed)
    st.update(modelVersion=4,b=[_building(0)],inventory={},productionWork={},salesWork={},
              materials=0,lastActiveTick=start_tick,orderSerial=0,
              report=dict(produced=0,unitsProduced=0,retailEarned=0,unitsSold=0,
                          overflowSold=0,overflowCost=0,builds=0,offlineTicksSkipped=0))
    offer_contracts(cfg,st,start_tick)
    return st


def migrate_state(cfg, st, tick=None):
    """Retain ownership and money; old monetary pools become cash, never goods.

    An active v3 contract's delivered value had already left its warehouse, so
    reimburse precisely that value, without awarding any unearned reward.
    The API records original JSON and handles clock reset for old snapshots.
    """
    if not isinstance(st,State): st=State(st)
    if st.get('modelVersion')==4:
        return st
    old_gate=legacy.gate_open(legacy.load_config(),st) if st.get('b') else False
    keep=st.get('keepPercent')
    # A saved Keep decision was available only after the previous licence opened.
    old_gate=old_gate or (type(keep) is int and 0<=keep<=100)
    compensation=sum(max(0,int(v)) for v in st.get('pend',{}).values())
    compensation+=sum(max(0,int(c.get('delivered',0))) for c in st.get('contracts',[]))
    st['cash']=max(0,int(st.get('cash',0)))+compensation
    st['book']=max(0,int(st.get('book',0)))
    old_b=st.get('b') or [dict(tier=0,lv=1,auto=1)]
    st.setdefault('tierOf',[b.get('tier',0) for b in old_b])
    st['b']=[_building(ti,min(cfg['production']['maxLevel'],max(1,int(b.get('lv',1)))),
                      min(cfg['production']['maxLevel'],max(1,int(b.get('auto',1))))) for ti,b in zip(st['tierOf'],old_b)]
    st.update(modelVersion=4,inventory={},productionWork={},salesWork={},pend={},materials=0,
              contracts=[],offers=None,orderSerial=0,lastActiveTick=st.get('tick',0),
              migration=dict(fromVersion=3,storedValueCredited=compensation),licenceGrandfathered=old_gate)
    st.setdefault('queue',[]);st.setdefault('build',None)
    st.setdefault('cStats',dict(accepted=0,done=0,failed=0,net=0))
    c=st.setdefault('checklist',{})
    c.update(lv25=bool(c.get('lv25') or any(b['lv']>=cfg['gate']['levelNeeded'] for b in st['b'])),
             auto=bool(c.get('auto') or any(b['sales']>1 for b in st['b'])),
             goodSales=min(cfg['gate']['goodSalesNeeded'],st['cStats'].get('done',0)),quiz=bool(c.get('quiz')))
    st.setdefault('report',{})
    for key in ('produced','unitsProduced','retailEarned','unitsSold','overflowSold','overflowCost','builds','offlineTicksSkipped'):
        st['report'].setdefault(key,0)
    if tick is not None:
        delta=tick-st.get('tick',tick)
        if st.get('build'): st['build']['t']+=delta
        st['tick']=tick;st['lastActiveTick']=tick
    offer_contracts(cfg,st,st.get('tick',0))
    return st


def production_multiplier(cfg,b):
    return 100+cfg['production']['speedPerLevel']*(b['lv']-1)


def product_speed(cfg, st, b, good):
    speed = production_multiplier(cfg, b)
    focus=b.get('focus','balanced')
    if focus=='supply': speed += -25 if good['id']=='farm_tomatoes' else 25
    elif focus in ('coffee','pastry'):
        target='roastery_espresso_shots' if focus=='coffee' else 'roastery_pastries'
        if good.get('inputs'): speed += 50 if good['id']==target else -25
    event = st.get('breakfastEvent', {})
    chosen = {'coffee': 'roastery_espresso_shots', 'pastry': 'roastery_pastries'}.get(event.get('upgrade'))
    if event.get('stage') == 5 and good['id'] == chosen:
        speed += 25
    return speed


def focus_options(cfg,b):
    if cfg['tiers'][b['tier']]['id']=='farm':
        return [('balanced','Mixed farm','Standard output'),('supply','Bakery supplier','Eggs/honey +25% base speed; tomatoes −25%')]
    if cfg['tiers'][b['tier']]['id']=='roastery':
        return [('balanced','Mixed café','Standard output'),('coffee','Coffee counter','Espresso +50% base speed; pastries −25%'),('pastry','Bakehouse','Pastries +50% base speed; espresso −25%')]
    return []


def set_focus(cfg,st,slot,focus):
    if not _valid_slot(st,slot): return dict(ok=False,why='Unknown business')
    b=st['b'][slot]
    if b['lv']<3: return dict(ok=False,why='Reach production level 3 to specialize')
    if focus not in [o[0] for o in focus_options(cfg,b)]: return dict(ok=False,why='Unknown specialty')
    b['focus']=focus
    return dict(ok=True,kind='focus',focus=focus)


def town_income(cfg,st):
    goods=catalog(cfg)
    return sum(r['retail']*goods[gid]['unitPrice'] for gid,r in flow_rates(cfg,st).items())


def upgrade_preview(cfg,st,slot,kind):
    after=copy.deepcopy(st);key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    after['b'][slot][key]+=1
    delta=round(town_income(cfg,after)-town_income(cfg,st),2)
    if kind=='storage':
        message=f'+{_capacity(cfg,after,slot)-_capacity(cfg,st,slot)} spaces · sales unchanged'
    elif delta!=0: message=f'Town sales {delta:+g} YM/min'
    else: message='Sales unchanged · more stock' if kind=='production' else 'Supply limits sales'
    unlocks=kind=='production' and after['b'][slot]['lv']==3 and bool(focus_options(cfg,after['b'][slot]))
    return dict(incomeDelta=delta,consequence=message,unlocksSpecialty=unlocks)


def customer_demand(cfg, st, b):
    base = sales_multiplier(cfg, b)
    if cfg['tiers'][b['tier']]['id'] == 'roastery' and st.get('regularDeliveries', 0) >= 3:
        base = base * 120 // 100
    return base


def order_reservations(st, exclude=None):
    """Committed orders own a bounded amount of stock, in board order."""
    held = {}
    for order in st.get('offers') or []:
        if order.get('committed') and order['id'] != exclude:
            for need in order['requirements']:
                gid = need['goodId']
                held[gid] = held.get(gid, 0) + need['quantity']
    return held


def protected_stock(cfg, st):
    protected = chain_reservations(cfg, st)
    for gid, qty in order_reservations(st).items():
        protected[gid] = protected.get(gid, 0) + qty
    return protected


def sales_multiplier(cfg,b):
    return cfg['production']['customerBasePercent']*(100+cfg['production']['customerPerLevel']*(b['sales']-1))


def _capacity(cfg,st,slot):
    tier=cfg['tiers'][st['tierOf'][slot]]
    return math.floor(tier['capacity']*(1+cfg['production']['storagePerLevel']*(st['b'][slot]['storage']-1)))


def _good_capacity(cfg,st,slot,gid):
    goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    total=_capacity(cfg,st,slot);index=next(i for i,g in enumerate(goods) if g['id']==gid)
    return total//len(goods)+(index<total%len(goods))


def _goods_count(cfg,st,slot):
    return sum(st['inventory'].get(g['id'],0) for g in cfg['tiers'][st['tierOf'][slot]]['goods'])


def _sync_pools(cfg,st):
    st['pend']={str(i):sum(st['inventory'].get(g['id'],0)*g['unitPrice']
                          for g in cfg['tiers'][ti]['goods']) for i,ti in enumerate(st['tierOf'])}


def chain_reservations(cfg,st):
    protected={}
    batches=cfg['production']['chainBufferBatches']
    for slot,ti in enumerate(st['tierOf']):
        if not st['b'][slot].get('processing',True): continue
        for good in cfg['tiers'][ti]['goods']:
            for need in good.get('inputs',[]):
                protected[need['goodId']]=protected.get(need['goodId'],0)+need['quantity']*batches
    return protected


def _produce(cfg,st):
    inv=st['inventory'];pwork=st['productionWork'];made=0;value=0
    held=order_reservations(st)
    st['productionBlocked']={}
    # Tier order is stable and dependency edges always point to an earlier good.
    for slot in sorted(range(len(st['b'])),key=lambda i:st['tierOf'][i]):
        b=st['b'][slot];tier=cfg['tiers'][st['tierOf'][slot]]
        for good in tier['goods']:
            if good.get('inputs') and not b.get('processing',True): continue
            gid=good['id'];denom=good['cycleTicks']*100
            work=pwork.get(gid,0)+product_speed(cfg,st,b,good)
            while work>=denom:
                needs=good.get('inputs',[])
                shortages=[n['goodId'] for n in needs if inv.get(n['goodId'],0)-held.get(n['goodId'],0)<n['quantity']]
                if shortages:
                    st['productionBlocked'][gid]=dict(reason='ingredient',goodId=shortages[0])
                    work=denom;break
                if inv.get(gid,0)+good['quantity']>_good_capacity(cfg,st,slot,gid):
                    st['productionBlocked'][gid]=dict(reason='storage')
                    work=denom;break
                for n in needs: inv[n['goodId']]-=n['quantity']
                inv[gid]=inv.get(gid,0)+good['quantity']
                made+=good['quantity'];value+=good['quantity']*good['unitPrice'];work-=denom
            pwork[gid]=work
    st['report']['produced']+=value;st['report']['unitsProduced']+=made


def _retail(cfg,st):
    inv=st['inventory'];protected=protected_stock(cfg,st);earned=sold=0
    for slot,b in enumerate(st['b']):
        slot_income=0
        for good in cfg['tiers'][st['tierOf'][slot]]['goods']:
            gid=good['id'];denom=good['cycleTicks']*10000
            # Idle demand cannot be banked then cashed in as unlimited customers.
            work=st['salesWork'].get(gid,0)+customer_demand(cfg,st,b)
            if b['reserve']:
                st['salesWork'][gid]=0;continue
            available=max(0,inv.get(gid,0)-protected.get(gid,0))
            take=min(available,work//denom)
            if take:
                inv[gid]-=take;gross=take*good['unitPrice']
                earned+=gross;slot_income+=gross;sold+=take;work-=take*denom
            st['salesWork'][gid]=work%denom
        history=st.setdefault('recentRetail',{}).setdefault(str(slot),[])
        history.append(slot_income)
        del history[:-max(1,round(60/cfg['global']['tick']))]
    st['cash']+=earned
    st['report']['retailEarned']+=earned;st['report']['unitsSold']+=sold


def player_tick(cfg,cls,st,k):
    if st.get('build') is not None and k>=st['build']['t']:
        finish_build(cfg,st,k)
    _produce(cfg,st);_retail(cfg,st);_sync_pools(cfg,st)
    st['tick']=k+1


def class_price(cfg,cls,ti,k): return 1.0

def tax_rate(cfg,y): return 0

def net(cfg,st,gross): return max(0,int(gross))

def set_mult(cfg,st,bi): return 1

def ms(cfg,lv): return 1

def bind_sales(cfg,cls,st): st.on_sold=None

def class_tick(cfg,cls,players,k):
    cls['k']=k
    cls['incomePerHour']=max(1,sum(revS(cfg,s) for s in players)*ticks_per_hour(cfg))


def advance_class(cfg,cls,players,start,target):
    """Independent fixed-price towns replay identically, with a 12h absence cap.

    The API updates lastActiveTick only for the requesting player. Other players'
    polling therefore cannot extend an absent player's earning allowance.
    Construction uses wall time; skipped production is never replayed later.
    """
    allowance=int(cfg['runtime']['offlineHours']*ticks_per_hour(cfg))
    for st in players:
        begin=max(start,st['tick']);stop=min(target,st.get('lastActiveTick',begin)+allowance)
        for k in range(begin,max(begin,stop)): player_tick(cfg,cls,st,k)
        if target>max(begin,stop):
            st['report']['offlineTicksSkipped']+=target-max(begin,stop)
            st['recentRetail']={}
        while st.get('build') and st['build']['t']<target:
            finish_build(cfg,st,st['build']['t'])
        st['tick']=max(st['tick'],target)
        _sync_pools(cfg,st)
    cls['k']=max(0,target-1);cls['nextTick']=target
    cls['incomePerHour']=max(1,sum(revS(cfg,s) for s in players)*ticks_per_hour(cfg))


def on_login(cfg,st,k=None):
    k=st['tick'] if k is None else k
    st['lastLogin']=k;st['lastActiveTick']=k;st['catchupUntil']=-1


def bRev(cfg,st,bi): return jsround(_rate(cfg,st,bi)[1]*cfg['global']['tick']/60)
def revS(cfg,st): return sum(bRev(cfg,st,i) for i in range(len(st['b'])))
def warehouse_cap(cfg,st): return [_capacity(cfg,st,i) for i in range(len(st['b']))]
def net_worth(cfg_or_state,st=None):
    st=cfg_or_state if st is None else st
    return int(st['cash'])+sum(st.get('pend',{}).values())+int(st['book'])


def upgrade_cost(cfg,st,slot,kind):
    if not _valid_slot(st,slot) or kind not in ('production','sales','storage'): return None
    key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    level=st['b'][slot][key]
    if level>=cfg['production']['maxLevel']: return None
    base=cfg['tiers'][st['tierOf'][slot]]['upgradeBase']
    factor=.65 if kind=='storage' else 1
    return max(1,jsround(base*factor*cfg['production']['upgradeGrowth']**(level-1)))


def level_cost(cfg,st,bi): return upgrade_cost(cfg,st,bi,'production')
def auto_cost(cfg,st,bi): return upgrade_cost(cfg,st,bi,'sales')


def buy_upgrade(cfg,st,slot,kind):
    if not _valid_slot(st,slot): return dict(ok=False,why='Unknown business')
    if kind not in ('production','sales','storage'): return dict(ok=False,why='Unknown upgrade')
    cost=upgrade_cost(cfg,st,slot,kind)
    if cost is None: return dict(ok=False,why='Fully upgraded')
    if st['cash']<cost: return dict(ok=False,why=f'Need {cost-st["cash"]} YM more')
    consequence=upgrade_preview(cfg,st,slot,kind)
    key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    st['cash']-=cost;st['book']+=cost;st['b'][slot][key]+=1
    st['b'][slot]['auto']=st['b'][slot]['sales']
    if kind=='production' and st['b'][slot]['lv']>=cfg['gate']['levelNeeded']: st['checklist']['lv25']=True
    if kind=='sales': st['checklist']['auto']=True
    return dict(ok=True,kind='upgrade',upgrade=kind,cost=cost,level=st['b'][slot][key],**consequence)


def buy_level(cfg,st,bi): return buy_upgrade(cfg,st,bi,'production')
def buy_auto(cfg,st,bi): return buy_upgrade(cfg,st,bi,'sales')


def set_reserve(cfg,st,slot,reserve):
    if not _valid_slot(st,slot): return dict(ok=False,why='Unknown business')
    if type(reserve) is not bool: return dict(ok=False,why='Reserve must be true or false')
    st['b'][slot]['reserve']=reserve
    return dict(ok=True,kind='reserve',reserve=reserve)


def sell_one(cfg,st,bi,price=1,manual=True):
    if not _valid_slot(st,bi): return dict(ok=False,why='Unknown business')
    protect=protected_stock(cfg,st);removed=[];value=0;units=0
    for g in cfg['tiers'][st['tierOf'][bi]]['goods']:
        quantity=max(0,st['inventory'].get(g['id'],0)-protect.get(g['id'],0))
        if quantity: removed.append((g['id'],quantity));value+=quantity*g['unitPrice'];units+=quantity
    if not units: return dict(ok=False,why='No spare stock')
    gross=value*cfg['production']['clearStockPercent']//100
    for gid,q in removed: st['inventory'][gid]-=q
    st['cash']+=gross;_sync_pools(cfg,st)
    return dict(ok=True,gross=gross,net=gross,tax=0,quantity=units,discountPercent=100-cfg['production']['clearStockPercent'])


def sell_all(cfg,st,mk=None,k=0,manual=False):
    return [sell_one(cfg,st,i) for i in range(len(st['b']))]


def expand_options(cfg,st):
    taken=set(st['tierOf']+st['queue']+([st['build']['i']] if st.get('build') else []))
    return [i for i in range(len(cfg['tiers'])) if i not in taken][:cfg['global']['frontier']]


def expansion_quote(cfg,st,ti):
    t=cfg['tiers'][ti]
    substitute=cfg['production']['materialCashValue']
    required=math.ceil(t['baseCost']*cfg['production']['materialPremiumPercent']/100/substitute) if t['materialCost'] else 0
    used=min(st['materials'],required)
    missing=required-used
    return dict(baseCost=t['baseCost'],cost=t['baseCost']+missing*substitute,materialUnitValue=substitute,
                materialCost=required,materialsCost=required,materialsUsed=used,materialsMissing=missing)


def can_expand(cfg,st,ti):
    if type(ti) is not int or not 0<=ti<len(cfg['tiers']): return dict(ok=False,why='Unknown business')
    quote=expansion_quote(cfg,st,ti)
    if len(st['queue'])+bool(st.get('build'))>=cfg['global']['queueDepth']:
        return dict(quote,ok=False,why='Construction queue full')
    if ti not in expand_options(cfg,st): return dict(quote,ok=False,why='Choose an available business',frontier=expand_options(cfg,st))
    if st['cash']<quote['cost']: return dict(quote,ok=False,why=f'Need {quote["cost"]-st["cash"]} YM more')
    return dict(quote,ok=True)


def expand(cfg,st,ti,tick):
    result=can_expand(cfg,st,ti)
    if not result['ok']: return result
    st['cash']-=result['cost'];st['book']+=result['cost'];st['materials']-=result['materialsUsed']
    if st.get('build') is None:
        st['build']=dict(i=ti,t=tick+max(1,jsround(cfg['tiers'][ti]['timerH']*3600/cfg['global']['tick'])))
    else: st['queue'].append(ti)
    return result


def finish_build(cfg,st,k,DAY=None):
    ti=st['build']['i'];st['b'].append(_building(ti));st['tierOf'].append(ti);st['build']=None
    st['unlock'][str(len(st['b'])-1)]=k/ticks_per_day(cfg);st['report']['builds']+=1
    if st.get('gateDay') is None and len(st['b'])>=cfg['global']['gateTier']: st['gateDay']=k/ticks_per_day(cfg)
    if st['queue']:
        ti=st['queue'].pop(0)
        st['build']=dict(i=ti,t=k+max(1,jsround(cfg['tiers'][ti]['timerH']*3600/cfg['global']['tick'])))
    _sync_pools(cfg,st)


def auto_continue(cfg,st,tick): return None


def _make_order(cfg,st,index):
    goods=catalog(cfg);owned=set(st['tierOf']);eligible=[]
    for ti in st['tierOf']:
        for g in cfg['tiers'][ti]['goods']:
            if all(goods[n['goodId']]['tier'] in owned for n in g.get('inputs',[])): eligible.append(g)
    serial=st['orderSerial'];st['orderSerial']+=1
    # Independent deterministic randomness: saving/reloading cannot reroll the
    # next offer, and class/player request timing cannot change its rarity.
    digest=hashlib.sha256(f'{st.get("rngState",1)}:{serial}:{index}:order-roll-v1'.encode()).digest()
    roll=int.from_bytes(digest[:8],'big')%100
    rarity=ORDER_ROLLS[-1]
    for candidate in ORDER_ROLLS:
        if roll<candidate['chance']:
            rarity=candidate;break
        roll-=candidate['chance']
    # Unit stride covers every eligible product even when the count shares
    # factors with seven (for example, seven businesses with 21 products).
    offset=(serial+index*3)%len(eligible)
    picks=[eligible[offset]]
    if index>0 and len(eligible)>1: picks.append(eligible[(offset+max(1,len(eligible)//2))%len(eligible)])
    if index == 2:
        ids = ['roastery_espresso_shots', 'roastery_pastries'] if 2 in owned else ['farm_eggs', 'farm_honey']
        regulars = [g for g in eligible if g['id'] in ids]
        if regulars: picks=regulars
    extras=sorted((g for g in eligible if g not in picks),
                  key=lambda g:hashlib.sha256(digest+g['id'].encode()).digest())
    picks+=extras[:max(0,min(len(eligible),rarity['items'])-len(picks))]
    requirements=[];value=0
    for good in picks:
        # Fixed order sizes do not scale with cash; upgrades shorten lead time.
        qty=max(2,math.ceil(cfg['production']['orderMinutes'][index]*60/(good['cycleTicks']*cfg['global']['tick'])))
        qty=math.ceil(qty*rarity['quantityPercent']/100)
        slot=st['tierOf'].index(goods[good['id']]['tier'])
        qty=min(qty,_good_capacity(cfg,st,slot,good['id']))
        requirements.append(dict(goodId=good['id'],quantity=qty));value+=qty*good['unitPrice']
    material_value=cfg['production']['materialCashValue']
    materials=max(1,jsround(value*.25/material_value)) if index == 1 else 0
    reward_percent=jsround([125,110,115][index]*rarity['payoutPercent']/100)
    return dict(id=f'order-{st.get("rngState",1)}-{serial}',name=['Quick cash','Building supplies','Breakfast regulars'][index],
                requirements=requirements,reward=jsround(value*reward_percent/100),materials=materials,
                customer='breakfast' if index == 2 else None,committed=False,
                rarity=rarity['id'],rarityLabel=rarity['label'],rewardPercent=reward_percent,retailValue=value)


def offer_contracts(cfg,st,k,DAY=None):
    st.setdefault('orderSerial',0)
    if st.get('offers') is None: st['offers']=[_make_order(cfg,st,i) for i in range(3)]


def _order_check(st,index,order_id):
    if type(index) is not int or not 0<=index<len(st.get('offers') or []): return dict(ok=False,why='Choose a delivery')
    order=st['offers'][index]
    if order_id is not None and order_id!=order['id']: return dict(ok=False,why='This delivery changed. Try again.')
    return dict(ok=True)


def fulfill_order(cfg,st,offerIndex,order_id=None):
    check=_order_check(st,offerIndex,order_id)
    if not check['ok']: return check
    order=st['offers'][offerIndex];goods=catalog(cfg)
    held=order_reservations(st,exclude=order['id'])
    for need in order['requirements']:
        if st['inventory'].get(need['goodId'],0)-held.get(need['goodId'],0)<need['quantity']:
            return dict(ok=False,why='Need unreserved '+goods[need['goodId']]['name'])
    for need in order['requirements']: st['inventory'][need['goodId']]-=need['quantity']
    st['cash']+=order['reward'];st['materials']+=order['materials']
    st['cStats']['accepted']+=1;st['cStats']['done']+=1
    raw_value=sum(goods[n['goodId']]['unitPrice']*n['quantity'] for n in order['requirements'])
    st['cStats']['net']+=order['reward']-raw_value;st['checklist']['goodSales']=st['cStats']['done']
    if order.get('customer') == 'breakfast':
        st['regularDeliveries']=min(3,st.get('regularDeliveries',0)+1)
    st['offers'][offerIndex]=_make_order(cfg,st,offerIndex);_sync_pools(cfg,st)
    return dict(ok=True,kind='delivery',reward=order['reward'],materials=order['materials'],orderId=order['id'])


def replace_order(cfg,st,offerIndex,order_id=None):
    check=_order_check(st,offerIndex,order_id)
    if not check['ok']: return check
    st['offers'][offerIndex]=_make_order(cfg,st,offerIndex)
    return dict(ok=True,kind='replace_order')


def commit_order(cfg,st,index,order_id,committed):
    check=_order_check(st,index,order_id)
    if not check['ok']: return check
    if type(committed) is not bool: return dict(ok=False,why='committed must be true or false')
    order=st['offers'][index]
    if committed:
        goods=catalog(cfg);held=order_reservations(st,exclude=order_id)
        for need in order['requirements']:
            gid=need['goodId'];slot=st['tierOf'].index(goods[gid]['tier'])
            if held.get(gid,0)+need['quantity']>_good_capacity(cfg,st,slot,gid):
                return dict(ok=False,why='Not enough shelf room for both orders. Release another order or upgrade storage.')
    order['committed']=committed
    return dict(ok=True,kind='order_commit',committed=committed)


def accept_contract(cfg,st,offer_idx,k): return fulfill_order(cfg,st,offer_idx)
def tick_contracts(cfg,st,k,produced): return None

def gate_open(cfg,st):
    if st.get('licenceGrandfathered'): return True
    c=st['checklist']
    experience=st['cStats']['done']>=cfg['gate']['goodSalesNeeded'] or st['report'].get('unitsSold',0)>=100
    return len(st['b'])>=cfg['global']['gateTier'] and c['lv25'] and c['auto'] and experience and c['quiz']


def flow_rates(cfg,st):
    """Sustainable full-store-free flow, including ingredients used downstream.

    This forecast shows the current configuration's capacity; actual income is
    reported separately from completed sales. No income is credited by it.
    """
    pool={};rates={};by_tier={ti:i for i,ti in enumerate(st['tierOf'])}
    for ti in sorted(by_tier):
        b=st['b'][by_tier[ti]]
        for g in cfg['tiers'][ti]['goods']:
            rate=product_speed(cfg,st,b,g)/100*60/(g['cycleTicks']*cfg['global']['tick'])
            if g.get('inputs') and not b.get('processing',True): rate=0
            for need in g.get('inputs',[]): rate=min(rate,pool.get(need['goodId'],0)/need['quantity'])
            for need in g.get('inputs',[]): pool[need['goodId']]=max(0,pool.get(need['goodId'],0)-rate*need['quantity'])
            pool[g['id']]=rate
            rates[g['id']]=dict(production=rate,retail=0)
    for ti,slot in by_tier.items():
        b=st['b'][slot]
        for g in cfg['tiers'][ti]['goods']:
            demand=customer_demand(cfg,st,b)/10000*60/(g['cycleTicks']*cfg['global']['tick'])
            rates[g['id']]['retail']=0 if b['reserve'] else min(pool[g['id']],demand)
    return rates


def _rate(cfg,st,slot,selling=False):
    rates=flow_rates(cfg,st);key='retail' if selling else 'production'
    goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    return (round(sum(rates[g['id']][key] for g in goods),2),
            round(sum(rates[g['id']][key]*g['unitPrice'] for g in goods),2))


def payload(cfg,st,cls,session,behind=False):
    _sync_pools(cfg,st)
    g=cfg['global'];goods=catalog(cfg);rates=flow_rates(cfg,st);protected=protected_stock(cfg,st)
    buildings=[];board=[];inventory=st['inventory']
    for slot,b in enumerate(st['b']):
        ti=st['tierOf'][slot];t=cfg['tiers'][ti];rows=[]
        for good in t['goods']:
            qty=inventory.get(good['id'],0)
            row=dict(goodId=good['id'],name=good['name'],slot=slot,tier=ti,buildingId=t['id'],
                     tierName=t['name'],family=t['family'],quantity=qty,stored=qty,
                     unitPrice=good['unitPrice'],value=qty*good['unitPrice'],price=1,
                     reserved=qty if b['reserve'] else min(qty,protected.get(good['id'],0)),
                     capacity=_good_capacity(cfg,st,slot,good['id']),
                     productionPerMinute=round(rates[good['id']]['production'],2),
                     salesPerMinute=round(rates[good['id']]['retail'],2),
                     customerCapacityPerMinute=round(customer_demand(cfg,st,b)/10000*60/(good['cycleTicks']*g['tick']),2),
                     inputs=[dict(n,name=goods[n['goodId']]['name'],owned=inventory.get(n['goodId'],0),buildingId=goods[n['goodId']]['buildingId']) for n in good.get('inputs',[])])
            rows.append(row);board.append(row)
        production=sum(rates[x['id']]['production'] for x in t['goods'])
        sales=sum(rates[x['id']]['retail'] for x in t['goods'])
        potential_income=sum(rates[x['id']]['retail']*x['unitPrice'] for x in t['goods'])
        income=sum(st.get('recentRetail',{}).get(str(slot),[]))
        recipe_goods=[x for x in t['goods'] if x.get('inputs')]
        recipes=[dict(inputs=[dict(n,name=goods[n['goodId']]['name'],owned=inventory.get(n['goodId'],0),buildingId=goods[n['goodId']]['buildingId']) for n in x['inputs']],
                      output=dict(goodId=x['id'],name=x['name'],quantity=x['quantity']),
                      available=all(inventory.get(n['goodId'],0)>=n['quantity'] for n in x['inputs'])) for x in recipe_goods]
        blocked=[st.get('productionBlocked',{}).get(x['id'],{}) for x in t['goods']]
        missing=[x['goodId'] for x in blocked if x.get('reason')=='ingredient']
        storage=_goods_count(cfg,st,slot);cap=_capacity(cfg,st,slot)
        status='Working'
        if b['reserve']: status='Saving goods'
        elif recipes and not b.get('processing',True): status='Processing paused'
        elif missing: status='Waiting for '+goods[missing[0]]['name']
        elif any(r['quantity']>=r['capacity'] for r in rows): status='Storage full'
        elif any(r['quantity']>max(2,r['reserved']) for r in rows) and sales<production:
            status='More customers needed' if b['sales']<cfg['production']['maxLevel'] else 'Goods ready'
        upgrades={}
        for kind,key in (('production','lv'),('sales','sales'),('storage','storage')):
            cost=upgrade_cost(cfg,st,slot,kind);level=b[key]
            why='Fully upgraded' if cost is None else f'Need {cost-st["cash"]} YM more' if cost>st['cash'] else ''
            if kind=='production': effect=f'{100+cfg["production"]["speedPerLevel"]*level}% base speed'
            elif kind=='sales': effect=f'{100+cfg["production"]["customerPerLevel"]*level}% base customers'
            else: effect=f'{math.floor(t["capacity"]*(1+cfg["production"]["storagePerLevel"]*level))} items'
            upgrades[kind]=dict(level=level,cost=cost,canBuy=cost is not None and cost<=st['cash'],why=why,effect=effect)
            if cost is not None: upgrades[kind].update(upgrade_preview(cfg,st,slot,kind))
        clear_qty=sum(max(0,inventory.get(x['id'],0)-protected.get(x['id'],0)) for x in t['goods'])
        clear_value=sum(max(0,inventory.get(x['id'],0)-protected.get(x['id'],0))*x['unitPrice'] for x in t['goods'])*cfg['production']['clearStockPercent']//100
        item=dict(slot=slot,tier=ti,id=t['id'],name=t['name'],family=t['family'],lv=b['lv'],
                  maxed=upgrades['production']['cost'] is None,auto=b['sales'],autoLabel='Customers '+str(b['sales']),
                  revenuePerTick=jsround(income*g['tick']/60),productionPerMinute=round(production,2),
                  salesPerMinute=round(sales,2),customerCapacityPerMinute=round(sum(r['customerCapacityPerMinute'] for r in rows),2),incomePerMinute=round(income,2),potentialIncomePerMinute=round(potential_income,2),status=status,reserve=b['reserve'],
                  processing=b.get('processing',True),hasRecipes=bool(recipes),
                  upgrades=upgrades,stored=storage,capacity=cap,storedValue=st['pend'][str(slot)],goods=rows,
                  recipe=recipes[-1] if recipes else None,recipes=recipes,price=1,priceTrend='flat',setBadges=[],
                  levelCost=upgrades['production']['cost'],levelPayback=None,autoCost=upgrades['sales']['cost'],autoPayback=None,
                  clearableQuantity=clear_qty,clearStockValue=clear_value)
        item['artLevel']=6 if max(b['lv'],b['sales'],b['storage'])>=6 else 3 if max(b['lv'],b['sales'],b['storage'])>=3 else 1
        item['focus']=b.get('focus','balanced')
        item['focusUnlocked']=b['lv']>=3
        item['focusOptions']=[dict(id=o[0],name=o[1],effect=o[2]) for o in focus_options(cfg,b)]
        item['regularBonus']=20 if t['id']=='roastery' and st.get('regularDeliveries',0)>=3 else 0
        buildings.append(item)
    frontier=[]
    for ti in expand_options(cfg,st):
        t=cfg['tiers'][ti];check=can_expand(cfg,st,ti);quote=expansion_quote(cfg,st,ti)
        frontier.append(dict(quote,tier=ti,id=t['id'],name=t['name'],family=t['family'],
                             baseRevenue=sum(x['unitPrice']/(x['cycleTicks']) for x in t['goods']),
                             productionPerMinute=round(sum(60/(x['cycleTicks']*g['tick']) for x in t['goods']),2),
                             timerH=t['timerH'],affordable=st['cash']>=quote['cost'],canExpand=check['ok'],why=check.get('why','')))
    orders=[]
    for order in st.get('offers') or []:
        held=order_reservations(st,exclude=order['id'])
        requirements=[dict(n,name=goods[n['goodId']]['name'],owned=max(0,inventory.get(n['goodId'],0)-held.get(n['goodId'],0)),
                           buildingId=goods[n['goodId']]['buildingId']) for n in order['requirements']]
        missing=[n for n in requirements if n['owned']<n['quantity']]
        ready=not missing
        target=sum(n['quantity'] for n in requirements);owned=sum(min(n['quantity'],n['owned']) for n in requirements)
        orders.append(dict(order,requirements=requirements,canFulfill=ready,
                           why='' if ready else 'Need '+str(missing[0]['quantity']-missing[0]['owned'])+' '+missing[0]['name'],
                           target=target,delivered=owned,penalty=0,remainingSec=None,progressPercent=round(owned/target*100,1),building=order['name']))
        orders[-1]['replaceRemainingSec']=0  # Also clears cooldowns from older saves.
    build=dict(tier=st['build']['i'],name=cfg['tiers'][st['build']['i']]['name'],remainingSec=max(0,(st['build']['t']-st['tick'])*g['tick'])) if st.get('build') else None
    capacity=sum(b['capacity'] for b in buildings);stored=sum(b['stored'] for b in buildings)
    income=round(sum(b['incomePerMinute'] for b in buildings),2);prod=round(sum(b['productionPerMinute'] for b in buildings),2)
    next_goal='Open '+frontier[0]['name'] if frontier else 'Grow your businesses'
    if len(buildings)==1 and buildings[0]['upgrades']['sales']['level']==1: next_goal='Upgrade customers'
    elif any(o['canFulfill'] for o in orders): next_goal='Delivery ready'
    elif build: next_goal=build['name']+' opening soon'
    newest=buildings[-1]
    return dict(modelVersion=4,tick=st['tick'],tickSeconds=g['tick'],behind=behind,cash=int(st['cash']),
                rulesRevision=2,regularDeliveries=st.get('regularDeliveries',0),regularTarget=3,
                customerUnitsSold=st['report'].get('unitsSold',0),customerUnitsNeeded=100,materialUnitValue=cfg['production']['materialCashValue'],
                netWorth=net_worth(st),book=st['book'],taxPaid=st['taxPaid'],taxRate=0,
                incomePerMinute=income,productionPerMinute=prod,revenuePerTick=jsround(income*g['tick']/60),
                revenuePerDay=jsround(income*1440),materials=st['materials'],buildings=buildings,buildingsOwned=len(buildings),
                frontier=frontier,build=build,queue=[dict(tier=i,name=cfg['tiers'][i]['name']) for i in st['queue']],queueDepth=g['queueDepth'],
                warehouseCap=capacity,warehouseStored=stored,warehouseValue=sum(st['pend'].values()),
                warehouseFillPercent=round(stored/capacity*100,1) if capacity else 0,
                overflowing=any(b['stored']>=b['capacity'] for b in buildings),overflowDisc=1-cfg['production']['clearStockPercent']/100,clearStockPercent=cfg['production']['clearStockPercent'],
                contracts=dict(offers=orders,active=[]),board=board,rumour=None,activeEvents=[],
                checklist=st['checklist'],checklistText=cfg['gate']['checklist'],goodSalesNeeded=cfg['gate']['goodSalesNeeded'],goodSalePrice=cfg['gate']['goodSalePrice'],
                gateTier=g['gateTier'],gateOpen=gate_open(cfg,st),keepPercent=st['keepPercent'],welcomeBackActive=False,
                currency=cfg['currency'],paused=bool(session['paused']),families=cfg['families'],tickerLines=[],
                contractSlots=cfg['fun']['contractSlots'],premiumSalePct=0,maxLevel=g['maxLevel'],gradLevel=1,offlineHours=cfg['runtime']['offlineHours'],
                nextGoal=next_goal,tier=newest['tier'],tierCount=len(cfg['tiers']),buildingName=newest['name'],buildingId=newest['id'],
                level=newest['lv'],auto=newest['auto'],autoLabel=newest['autoLabel'])


def set_processing(cfg,st,slot,enabled):
    if not _valid_slot(st,slot): return dict(ok=False,why='Unknown business')
    if type(enabled) is not bool: return dict(ok=False,why='Processing must be true or false')
    st['b'][slot]['processing']=enabled
    return dict(ok=True,kind='processing',enabled=enabled)
