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
from delivery_recipes import ORDER_RECIPES
import business_activity
import earnings
import town_projects
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

# Regular customers buy one small shipment at a time. Terms are deterministic;
# accepting a customer authorizes automatic inventory sales, never cash spending.
# Bundles never combine a recipe with its own ingredients.
CUSTOMER_CATALOG = (
    ('corner_grocer', 'Corner Grocer', 'Small tomato shipments with a quick turnaround.', 120,
     (('farm_tomatoes', 6),)),
    ('sunrise_diner', 'Sunrise Diner', 'A steady egg buyer for your farm.', 180,
     (('farm_eggs', 4),)),
    ('honey_collective', 'Honey Collective', 'Larger payments for slower honey shipments.', 300,
     (('farm_honey', 3),)),
    ('harbor_bistro', 'Harbor Bistro', 'Oysters and smoked fish for the lunch menu.', 240,
     (('fish_stall_oysters', 3), ('fish_stall_smoked_fish', 2))),
    ('copper_cafe', 'Copper Café', 'Coffee and pastries keep your farm and roastery busy.', 300,
     (('roastery_espresso_shots', 4), ('roastery_pastries', 2))),
    ('rally_crew', 'Rally Crew', 'Custom mods turn spare parts into a regular payday.', 300,
     (('garage_custom_mods', 3),)),
    ('builders_union', 'Builders Union', 'Frames and machined bolts for local building work.', 360,
     (('workshop_welded_frames', 3), ('workshop_machined_bolts', 2))),
    ('neighborhood_grid', 'Neighborhood Grid', 'Battery storage and credits for local power users.', 360,
     (('solar_coop_battery_storage', 3), ('solar_coop_carbon_credits', 2))),
    ('pantry_network', 'Pantry Network', 'Canned food connects your farm, fish stall and cannery.', 360,
     (('cannery_canned_goods', 4), ('cannery_preserves', 2))),
    ('inventors_lab', 'Inventors Lab', 'Prototypes bring your workshop and garage together.', 420,
     (('machine_works_tooling', 3), ('machine_works_prototypes', 2))),
    ('clean_power_group', 'Clean Power Group', 'A regular buyer for wind capacity and certificates.', 420,
     (('turbine_field_capacity_contracts', 3), ('turbine_field_green_certificates', 2))),
    ('district_heating', 'District Heating', 'Peak power and steam heat supplied through your grid.', 420,
     (('generator_peak_power', 3), ('generator_steam_heat', 2))),
    ('mobile_network', 'Mobile Network', 'Tower leases and messages need reliable power.', 480,
     (('relay_station_sms_traffic', 3), ('relay_station_tower_leases', 2))),
    ('city_couriers', 'City Couriers', 'Delivery work depends on parts and communications.', 480,
     (('freight_terminal_cold_storage', 3), ('freight_terminal_last_mile_delivery', 2))),
    ('cloud_studio', 'Cloud Studio', 'Storage and API calls put your power and network to work.', 480,
     (('data_center_cloud_storage', 3), ('data_center_api_calls', 2))),
    ('regional_utility', 'Regional Utility', 'Reserve capacity and credits connect your energy businesses.', 540,
     (('solar_array_reserve_capacity', 3), ('solar_array_renewable_credits', 2))),
    ('orbital_research', 'Orbital Research', 'Ground time and telemetry draw on your whole technology chain.', 540,
     (('uplink_center_ground_time', 3), ('uplink_center_telemetry', 2))),
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
              materials=0,lastActiveTick=start_tick,orderSerial=0,orderRecipeHistory=[[],[],[]],
              report=dict(produced=0,unitsProduced=0,retailEarned=0,unitsSold=0,
                          overflowSold=0,overflowCost=0,builds=0,offlineTicksSkipped=0))
    _customer_defaults(st)
    earnings.ensure(st)
    business_activity.ensure(st)
    town_projects.default(cfg,st)
    offer_contracts(cfg,st,start_tick)
    return st


def migrate_state(cfg, st, tick=None):
    """Retain ownership and money; old monetary pools become cash, never goods.

    An active v3 contract's delivered value had already left its warehouse, so
    reimburse precisely that value, without awarding any unearned reward.
    The API records original JSON and handles clock reset for old snapshots.
    """
    if not isinstance(st,State): st=State(st)
    st.setdefault('orderRecipeHistory',[[],[],[]])
    earnings.ensure(st)
    business_activity.ensure(st)
    # Existing v4 towns gain an empty roster without resetting their economy.
    _customer_defaults(st)
    if st.get('modelVersion')==4:
        town_projects.migrate(cfg,st)
        _sync_project_offer(cfg,st)
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
    for key in ('produced','unitsProduced','retailEarned','unitsSold','overflowSold','overflowCost','builds','offlineTicksSkipped','customerEarned','customerDeliveries'):
        st['report'].setdefault(key,0)
    if tick is not None:
        delta=tick-st.get('tick',tick)
        if st.get('build'): st['build']['t']+=delta
        st['tick']=tick;st['lastActiveTick']=tick
    earnings.prune(cfg,st,clear=True)
    business_activity.prune(cfg,st,clear=True)
    town_projects.migrate(cfg,st)
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
    goods=catalog(cfg);rates,regulars=_flows(cfg,st)
    return sum(r['retail']*goods[gid]['unitPrice'] for gid,r in rates.items())+regulars['incomePerMinute']


def _upgrade_capacity(cfg,st,slot,kind):
    """Installed capacity, before stock, ingredients or reservations limit it."""
    if kind=='storage': return _capacity(cfg,st,slot)
    b=st['b'][slot];goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    if kind=='production':
        rate=sum(product_speed(cfg,st,b,good)/100*good['quantity']*60/
                 (good['cycleTicks']*cfg['global']['tick']) for good in goods)
    else:
        rate=sum(customer_demand(cfg,st,b)/10000*60/
                 (good['cycleTicks']*cfg['global']['tick']) for good in goods)
    return round(rate,2)


def upgrade_preview(cfg,st,slot,kind):
    after=copy.deepcopy(st);key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    after['b'][slot][key]+=1
    before_capacity=_upgrade_capacity(cfg,st,slot,kind)
    after_capacity=_upgrade_capacity(cfg,after,slot,kind)
    unit={'production':'goods/min','sales':'walk-ins/min','storage':'spaces'}[kind]
    delta=round(town_income(cfg,after)-town_income(cfg,st),2)
    if kind=='storage':
        message=f'+{_capacity(cfg,after,slot)-_capacity(cfg,st,slot)} spaces · income unchanged'
    elif delta!=0: message=f'Est. ongoing income {delta:+g} YM/min'
    else:
        b=st['b'][slot];goods=cfg['tiers'][st['tierOf'][slot]]['goods']
        if kind=='sales':
            message=('Walk-in sales paused · release saved goods to use more customers' if b['reserve']
                     else 'Supply limits income · produce more goods')
        elif any(st['inventory'].get(good['id'],0)+good['quantity']>_good_capacity(cfg,st,slot,good['id']) for good in goods):
            message='Some shelves are full · sell goods to use extra capacity'
        elif not b.get('processing',True) and any(good.get('inputs') for good in goods):
            message='Processing paused · resume recipes to use extra capacity'
        elif any(st.get('productionBlocked',{}).get(good['id'],{}).get('reason')=='ingredient' for good in goods):
            message='Ingredients limit output · supply the recipes'
        else: message='Customer demand limits income · extra output goes to stock'
    unlocks=kind=='production' and after['b'][slot]['lv']==3 and bool(focus_options(cfg,after['b'][slot]))
    return dict(incomeDelta=delta,consequence=message,unlocksSpecialty=unlocks,
                capacityBefore=before_capacity,capacityAfter=after_capacity,capacityUnit=unit,
                effect=f'{before_capacity:g} → {after_capacity:g} {unit}')


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
    for gid, qty in _customer_reservations(cfg, st).items():
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


def _produce(cfg,st,tick=None):
    inv=st['inventory'];pwork=st['productionWork'];made=0;value=0;by_building={}
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
                by_building[slot]=by_building.get(slot,0)+good['quantity']
            pwork[gid]=work
    st['report']['produced']+=value;st['report']['unitsProduced']+=made
    business_activity.record(cfg,st,'production',by_building,tick=tick)


def _retail(cfg,st,tick=None):
    inv=st['inventory'];protected=protected_stock(cfg,st);earned=sold=0;by_building={};units_by_building={}
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
                units_by_building[slot]=units_by_building.get(slot,0)+take
            st['salesWork'][gid]=work%denom
        by_building[slot]=slot_income
        history=st.setdefault('recentRetail',{}).setdefault(str(slot),[])
        history.append(slot_income)
        del history[:-max(1,round(60/cfg['global']['tick']))]
    st['cash']+=earned
    st['report']['retailEarned']+=earned;st['report']['unitsSold']+=sold
    earnings.record(cfg,st,'walkIns',earned,tick=tick,by_building=by_building)
    business_activity.record(cfg,st,'walkIns',units_by_building,tick=tick)


def player_tick(cfg,cls,st,k):
    if st.get('build') is not None and k>=st['build']['t']:
        finish_build(cfg,st,k)
    _produce(cfg,st,k+1);_tick_customer_contracts(cfg,st,k+1);_retail(cfg,st,k+1);_sync_pools(cfg,st)
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
            skipped=target-max(begin,stop)
            st['report']['offlineTicksSkipped']+=skipped
            st['recentRetail']={}
            earnings.prune(cfg,st,tick=target,clear=True)
            business_activity.prune(cfg,st,tick=target,clear=True)
            # Production beyond the absence cap is never paid or caught up.
            # Preserve the interval remaining at the cap for the next visit.
            for contract in st.get('customerContracts',{}).get('active',[]):
                contract['nextDeliveryTick']+=skipped
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
    earnings.record(cfg,st,'clearance',gross,by_building={bi:gross})
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
    full_cost=t['baseCost']+missing*substitute
    grant=town_projects.construction_grant(cfg,st,ti)
    return dict(baseCost=t['baseCost'],cost=0 if grant else full_cost,materialUnitValue=substitute,
                materialCost=required,materialsCost=required,materialsUsed=0 if grant else used,
                materialsMissing=0 if grant else missing,constructionGrant=grant,
                fundedValue=t['baseCost']+required*substitute if grant else 0)


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
    if result.get('constructionGrant'):
        claimed=town_projects.consume_construction_grant(cfg,st,ti)
        if not claimed['ok']: return claimed
    st['cash']-=result['cost'];st['book']+=result['cost']+result.get('fundedValue',0);st['materials']-=result['materialsUsed']
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


def _customer_defaults(st):
    customers=st.setdefault('customerContracts',{})
    for key,value in (('serial',0),('earned',0),('deliveries',0),('active',[]),('history',{})):
        customers.setdefault(key,value)
    for contract in customers['active']:
        contract.setdefault('largerOrder',False)
    report=st.setdefault('report',{})
    report.setdefault('customerEarned',0)
    report.setdefault('customerDeliveries',0)
    return customers


def _customer_slots(st):
    return 4 if len(st['b'])>=6 else 3 if len(st['b'])>=3 else 2


def _customer_catalog(cfg,st):
    goods=catalog(cfg);owned=set(st['tierOf']);customers=[]

    def dependencies(gid,seen):
        if gid in seen: return
        seen.add(gid)
        for need in goods[gid].get('inputs',[]): dependencies(need['goodId'],seen)

    for customer_id,name,description,seconds,needs in CUSTOMER_CATALOG:
        # Small test/preview configurations may contain only some products.
        if any(gid not in goods for gid,qty in needs): continue
        required=set()
        for gid,qty in needs: dependencies(gid,required)
        missing=sorted({goods[gid]['tier'] for gid in required}-owned)
        requirements=[dict(goodId=gid,name=goods[gid]['name'],buildingId=goods[gid]['buildingId'],quantity=qty)
                      for gid,qty in needs]
        customers.append(dict(id=customer_id,name=name,description=description,available=not missing,
                              unlockText='Open '+', '.join(cfg['tiers'][ti]['name'] for ti in missing) if missing else '',
                              requirements=requirements,reward=jsround(sum(goods[gid]['unitPrice']*qty for gid,qty in needs)*1.25),
                              intervalSeconds=seconds))
    return customers


def _customer_stock_plan(cfg,st):
    """Reserve one shipment per regular, after manual orders and recipe buffers.

    Earlier slots have first claim, but reservations never exceed shelf space.
    These holds protect against sales only: recipes can use them, so a regular
    asking for an ingredient cannot deadlock a customer's finished product.
    """
    active=st.get('customerContracts',{}).get('active',[])
    if not active: return {},{}
    goods=catalog(cfg);protected=chain_reservations(cfg,st)
    for gid,qty in order_reservations(st).items(): protected[gid]=protected.get(gid,0)+qty
    totals={};assigned={};by_tier={ti:i for i,ti in enumerate(st['tierOf'])}
    for contract in sorted(active,key=lambda c:c['slot']):
        stock={};assigned[contract['id']]=stock
        if contract['paused']: continue
        for need in contract['requirements']:
            gid=need['goodId'];slot=by_tier[goods[gid]['tier']]
            prior=protected.get(gid,0)+totals.get(gid,0)
            target=min(need['quantity'],max(0,_good_capacity(cfg,st,slot,gid)-prior))
            stock[gid]=min(target,max(0,st['inventory'].get(gid,0)-prior))
            totals[gid]=totals.get(gid,0)+target
    return totals,assigned


def _customer_reservations(cfg,st):
    return _customer_stock_plan(cfg,st)[0]


def delivery_reservations(cfg,st,exclude=None):
    """Manual commitments have priority; other deliveries respect regular stock."""
    held=order_reservations(st,exclude=exclude)
    for stock in _customer_stock_plan(cfg,st)[1].values():
        for gid,qty in stock.items(): held[gid]=held.get(gid,0)+qty
    return held


def manage_customer_contract(cfg,st,slot,action,customer_id=None,contract_id=None):
    """Manage automatic regular sales; existing contracts require their exact ID."""
    if type(slot) is not int or not 0<=slot<_customer_slots(st):
        return dict(ok=False,why='This customer slot is not open')
    if not isinstance(action,str) or action not in ('accept','switch','release','pause','resume','upgrade','downgrade'):
        return dict(ok=False,why='Unknown customer action')
    data=st.get('customerContracts',{})
    active=data.get('active',[])
    current=next((c for c in active if c['slot']==slot),None)
    if action=='accept':
        if current is not None: return dict(ok=False,why='This slot already has a customer')
    elif current is None or not isinstance(contract_id,str) or current['id']!=contract_id:
        return dict(ok=False,why='This customer changed. Refresh and try again.')
    customer=None
    if action in ('accept','switch'):
        customer=next((c for c in _customer_catalog(cfg,st) if c['id']==customer_id),None)
        if customer is None: return dict(ok=False,why='Choose a customer')
        if not customer['available']: return dict(ok=False,why=customer['unlockText'])
        if any(c['customerId']==customer_id for c in active):
            return dict(ok=False,why='This customer already has a slot')
    elif action in ('upgrade','downgrade'):
        if action=='upgrade' and current.get('largerOrder',False):
            return dict(ok=False,why='This customer already has the larger order')
        if action=='upgrade' and current['deliveries']<3:
            return dict(ok=False,why='Larger orders become available after three deliveries')
        if action=='downgrade' and not current.get('largerOrder',False):
            return dict(ok=False,why='This customer already has the smaller order')
        customer=next((c for c in _customer_catalog(cfg,st) if c['id']==current['customerId']),None)
        if customer is None: return dict(ok=False,why='This customer is no longer available')
    data=_customer_defaults(st)
    if action in ('accept','switch'):
        interval=max(1,math.ceil(customer['intervalSeconds']/cfg['global']['tick']))
        data['serial']+=1
        history=data['history'].get(customer_id,{})
        replacement=dict(slot=slot,id='regular-{}-{}'.format(st.get('rngState',1),data['serial']),
                         customerId=customer_id,name=customer['name'],paused=False,largerOrder=False,
                         deliveries=history.get('deliveries',0),earned=history.get('earned',0),
                         reward=customer['reward'],intervalTicks=interval,
                         intervalSeconds=interval*cfg['global']['tick'],nextDeliveryTick=st['tick']+interval,
                         requirements=[dict(goodId=n['goodId'],quantity=n['quantity']) for n in customer['requirements']])
        if current is not None: data['active'].remove(current)
        data['active'].append(replacement)
        data['active'].sort(key=lambda c:c['slot'])
        return dict(ok=True,kind='customer_contract',action=action,contractId=replacement['id'])
    if action in ('upgrade','downgrade'):
        larger=action=='upgrade'
        data['serial']+=1
        current.update(id='regular-{}-{}'.format(st.get('rngState',1),data['serial']),largerOrder=larger,
                       reward=jsround(customer['reward']*2.2) if larger else customer['reward'],
                       requirements=[dict(goodId=n['goodId'],quantity=n['quantity']*(2 if larger else 1))
                                     for n in customer['requirements']],
                       nextDeliveryTick=st['tick']+current['intervalTicks'])
        return dict(ok=True,kind='customer_contract',action=action,contractId=current['id'])
    if action=='release': data['active'].remove(current)
    elif action=='pause': current['paused']=True
    elif current['paused']:
        current['paused']=False
        current['nextDeliveryTick']=st['tick']+current['intervalTicks']
    return dict(ok=True,kind='customer_contract',action=action,contractId=contract_id)


def _tick_customer_contracts(cfg,st,tick):
    data=st.get('customerContracts',{})
    for contract in sorted(data.get('active',[]),key=lambda c:c['slot']):
        if contract['paused'] or tick<contract['nextDeliveryTick']: continue
        stock=_customer_stock_plan(cfg,st)[1].get(contract['id'],{})
        if any(stock.get(n['goodId'],0)<n['quantity'] for n in contract['requirements']): continue
        # Debit every item together; shortages never receive partial payments.
        for need in contract['requirements']: st['inventory'][need['goodId']]-=need['quantity']
        st['cash']+=contract['reward']
        earnings.record_goods(cfg,st,'regularBuyers',contract['reward'],contract['requirements'],tick=tick)
        business_activity.record_regular_shipment(cfg,st,contract['requirements'],tick=tick)
        contract['deliveries']+=1;contract['earned']+=contract['reward']
        data['deliveries']+=1;data['earned']+=contract['reward']
        st['report']['customerEarned']+=contract['reward']
        st['report']['customerDeliveries']+=1
        data['history'][contract['customerId']]=dict(deliveries=contract['deliveries'],earned=contract['earned'])
        # A late shipment starts a new full interval; there is no missed backlog.
        contract['nextDeliveryTick']=tick+contract['intervalTicks']


def customer_contract_payload(cfg,st):
    data=st.get('customerContracts',{});goods=catalog(cfg);slots=_customer_slots(st)
    customers=_customer_catalog(cfg,st);by_id={c['id']:c for c in customers}
    assigned=_customer_stock_plan(cfg,st)[1];active=[]
    for contract in sorted(data.get('active',[]),key=lambda c:c['slot']):
        stock=assigned.get(contract['id'],{})
        requirements=[dict(n,name=goods[n['goodId']]['name'],buildingId=goods[n['goodId']]['buildingId'],
                           owned=stock.get(n['goodId'],0),reserved=stock.get(n['goodId'],0))
                      for n in contract['requirements']]
        missing=[n for n in requirements if n['owned']<n['quantity']]
        remaining=max(0,(contract['nextDeliveryTick']-st['tick'])*cfg['global']['tick'])
        status='paused' if contract['paused'] else 'waiting' if remaining==0 and missing else 'supplying'
        status_text='Paused · goods released' if contract['paused'] else (
            'Waiting for {} {}'.format(missing[0]['quantity']-missing[0]['owned'],missing[0]['name']) if status=='waiting'
            else 'Stock ready · ships automatically' if not missing else 'Saving the next shipment')
        larger=contract.get('largerOrder',False);offer=None
        if not larger and contract['deliveries']>=3 and contract['customerId'] in by_id:
            base=by_id[contract['customerId']]
            offer=dict(reward=jsround(base['reward']*2.2),intervalSeconds=contract['intervalSeconds'],
                       requirements=[dict(n,quantity=n['quantity']*2) for n in base['requirements']])
        active.append(dict(slot=contract['slot'],id=contract['id'],customerId=contract['customerId'],
                           name=contract['name'],paused=contract['paused'],deliveries=contract['deliveries'],
                           earned=contract['earned'],reward=contract['reward'],intervalSeconds=contract['intervalSeconds'],
                           nextDeliverySeconds=remaining,requirements=requirements,status=status,statusText=status_text,
                           largerOrder=larger,largerOffer=offer))
    return dict(slots=slots,maxSlots=4,nextUnlock=dict(buildings=3,slots=3) if slots==2 else dict(buildings=6,slots=4) if slots==3 else None,
                earned=data.get('earned',0),deliveries=data.get('deliveries',0),customers=customers,active=active)


def _order_recipe(cfg,st,index,rarity,digest,goods):
    """Deal a complete job the town can produce, with a saved rotation per slot.

    Eligibility follows the whole supply chain, including suppliers of inputs.
    Recipes are authored bundles: larger rolls never pad them with random goods.
    """
    owned=set(st['tierOf']);producible={}
    def can_make(gid,visiting=frozenset()):
        if gid in producible: return producible[gid]
        if gid in visiting or gid not in goods or goods[gid]['tier'] not in owned: return False
        producible[gid]=all(can_make(n['goodId'],visiting|{gid}) for n in goods[gid].get('inputs',[]))
        return producible[gid]
    eligible=[r for r in ORDER_RECIPES if all(can_make(gid) for gid in r['goods'])]
    if index==2:
        # Legacy migrations can preserve a town with only an industrial
        # business. Give it ordinary jobs until it can supply breakfast food.
        eligible=[r for r in eligible if r['breakfast']] or eligible
    target=rarity['items'] or (1 if index==0 else 2)
    size=max(len(r['goods']) for r in eligible if len(r['goods'])<=target)
    candidates=[r for r in eligible if len(r['goods'])==size]
    history=st.setdefault('orderRecipeHistory',[[],[],[]])[index]
    # Deal every unseen recipe of this size before recycling the oldest one.
    # Prefer distinct cards among unseen jobs, but a parked card must never
    # make its recipe unreachable through another slot's New Order button.
    on_board={o.get('recipeId') for o in st.get('offers') or []}
    seen=set(history)
    unseen=[r for r in candidates if r['id'] not in seen]
    if unseen:
        unseen=[r for r in unseen if r['id'] not in on_board] or unseen
        recipe=unseen[int.from_bytes(digest[8:16],'big')%len(unseen)]
    else:
        rank={rid:i for i,rid in enumerate(history)}
        recipe=min(candidates,key=lambda r:rank[r['id']])
    # A starter's first cash job teaches one fast, raw product.
    if st['orderSerial']==1 and index==0:
        recipe=next((r for r in candidates if r['goods']==('farm_tomatoes',)),recipe)
    if recipe['id'] in seen: history.remove(recipe['id'])
    history.append(recipe['id'])
    del history[:-len(ORDER_RECIPES)]
    return recipe


def _project_order(cfg,st):
    return town_projects.current_order(cfg,st) or dict(
        id='town-project-complete',name='Town projects complete',project=True,completed=True,
        requirements=[],reward=0,materials=0,customer=None,committed=False,
        purpose='Your opening projects are complete.',channelLabel='Town projects')


def _sync_project_offer(cfg,st):
    offers=st.get('offers') or []
    if len(offers)>2 and offers[2].get('project'):
        current=_project_order(cfg,st)
        if offers[2]['id']!=current['id']: offers[2]=current


def _make_order(cfg,st,index):
    if index==2 and town_projects.enabled(cfg): return _project_order(cfg,st)
    goods=catalog(cfg)
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
    recipe=_order_recipe(cfg,st,index,rarity,digest,goods)
    picks=[goods[gid] for gid in recipe['goods']]
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
    breakfast=index==2 and recipe['breakfast']
    return dict(id=f'order-{st.get("rngState",1)}-{serial}',name=recipe['name'],recipeId=recipe['id'],purpose=recipe['purpose'],
                channelLabel=['Quick cash','Building supplies','Breakfast regulars' if breakfast else 'Town deliveries'][index],
                requirements=requirements,reward=jsround(value*reward_percent/100),materials=materials,
                customer='breakfast' if breakfast else None,committed=False,
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
    if order.get('project'):
        access=town_projects.check(cfg,st,order['id'])
        if not access['ok']: return access
    held=delivery_reservations(cfg,st,exclude=order['id'])
    for need in order['requirements']:
        if st['inventory'].get(need['goodId'],0)-held.get(need['goodId'],0)<need['quantity']:
            return dict(ok=False,why='Need unreserved '+goods[need['goodId']]['name'])
    for need in order['requirements']: st['inventory'][need['goodId']]-=need['quantity']
    st['cash']+=order['reward'];st['materials']+=order['materials']
    earnings.record_goods(cfg,st,'orders',order['reward'],order['requirements'])
    st['cStats']['accepted']+=1;st['cStats']['done']+=1
    raw_value=sum(goods[n['goodId']]['unitPrice']*n['quantity'] for n in order['requirements'])
    st['cStats']['net']+=order['reward']-raw_value;st['checklist']['goodSales']=st['cStats']['done']
    if order.get('customer') == 'breakfast':
        st['regularDeliveries']=min(3,st.get('regularDeliveries',0)+1)
    project_result=town_projects.complete(cfg,st,order['id']) if order.get('project') else {}
    st['offers'][offerIndex]=_make_order(cfg,st,offerIndex);_sync_pools(cfg,st)
    return dict(ok=True,kind='delivery',reward=order['reward'],materials=order['materials'],orderId=order['id'],
                projectReward=project_result.get('rewardText',''))


def replace_order(cfg,st,offerIndex,order_id=None):
    check=_order_check(st,offerIndex,order_id)
    if not check['ok']: return check
    if st['offers'][offerIndex].get('project'): return dict(ok=False,why='Town projects are fixed goals. Save goods and deliver to advance.')
    st['offers'][offerIndex]=_make_order(cfg,st,offerIndex)
    return dict(ok=True,kind='replace_order')


def _commit_room(cfg,st,order):
    goods=catalog(cfg);held=order_reservations(st,exclude=order['id'])
    for need in order['requirements']:
        gid=need['goodId'];tier=goods[gid]['tier']
        if tier not in st['tierOf']:
            return dict(ok=False,why='Open '+cfg['tiers'][tier]['name']+' first')
        slot=st['tierOf'].index(tier)
        if held.get(gid,0)+need['quantity']>_good_capacity(cfg,st,slot,gid):
            return dict(ok=False,why='Not enough shelf room for both orders. Release another order or upgrade storage.')
    return dict(ok=True)


def commit_order(cfg,st,index,order_id,committed):
    check=_order_check(st,index,order_id)
    if not check['ok']: return check
    if type(committed) is not bool: return dict(ok=False,why='committed must be true or false')
    order=st['offers'][index]
    if committed and order.get('project'):
        access=town_projects.check(cfg,st,order['id'])
        if not access['ok']: return access
    if committed:
        room=_commit_room(cfg,st,order)
        if not room['ok']: return room
    order['committed']=committed
    return dict(ok=True,kind='order_commit',committed=committed)


def accept_contract(cfg,st,offer_idx,k): return fulfill_order(cfg,st,offer_idx)
def tick_contracts(cfg,st,k,produced): return None

def gate_open(cfg,st):
    if st.get('licenceGrandfathered'): return True
    c=st['checklist']
    experience=st['cStats']['done']>=cfg['gate']['goodSalesNeeded'] or st['report'].get('unitsSold',0)>=100
    return len(st['b'])>=cfg['global']['gateTier'] and c['lv25'] and c['auto'] and experience and c['quiz']


def _flows(cfg,st):
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
    regulars=earnings.allocate_regular_flow(cfg,st,pool)
    pool=regulars['remaining']
    for ti,slot in by_tier.items():
        b=st['b'][slot]
        for g in cfg['tiers'][ti]['goods']:
            rates[g['id']]['regulars']=regulars['unitsPerMinute'].get(g['id'],0)
            demand=customer_demand(cfg,st,b)/10000*60/(g['cycleTicks']*cfg['global']['tick'])
            rates[g['id']]['retail']=0 if b['reserve'] else min(pool[g['id']],demand)
    return rates,regulars


def flow_rates(cfg,st):
    return _flows(cfg,st)[0]


def _rate(cfg,st,slot,selling=False):
    rates=flow_rates(cfg,st);key='retail' if selling else 'production'
    goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    return (round(sum(rates[g['id']][key] for g in goods),2),
            round(sum(rates[g['id']][key]*g['unitPrice'] for g in goods),2))


def _project_supply_conflicts(cfg,st,order):
    if not order or not order.get('project') or order.get('completed'): return []
    goods=catalog(cfg);needed=set()
    def include(gid):
        if gid in needed: return
        needed.add(gid)
        for ingredient in goods[gid].get('inputs',[]): include(ingredient['goodId'])
    for need in order['requirements']: include(need['goodId'])
    return [other['name'] for other in st.get('offers') or []
            if other['id']!=order['id'] and other.get('committed')
            and any(need['goodId'] in needed for need in other['requirements'])]


def opening_step(cfg,st,project,order,frontier,build):
    if not town_projects.enabled(cfg) or project['completed']>=3: return None
    count=project['completed']
    if build:
        return dict(title=build['name']+' is being built',
                    detail='Projects '+str(count)+'/3 · '+str(build['remainingSec'])+'s remaining. Other businesses keep earning.')
    funded=next((item for item in frontier if item.get('constructionGrant')),None)
    if funded:
        return dict(title='Your '+funded['name']+' is fully funded',
                    detail='Projects '+str(count)+'/3 · This grant pays construction only. Upgrades cannot spend it.',
                    action='expand:'+str(funded['tier']),actionLabel='Build with grant',disabled=not funded['canExpand'])
    if order is None:
        return dict(title='Finish or replace your saved delivery',
                    detail='Your earlier delivery is preserved. The next card starts your town project.',
                    href='./marketplace.html',actionLabel='View saved delivery')
    if order.get('locked'):
        return dict(title=order['why'],detail=project['description'])
    if not order['canFulfill'] and not order.get('canCommit',True):
        return dict(title='Make room for your town project',
                    detail='Other saved orders fill the shelf. Finish or release one in Market, then save the project goods.',
                    href='./marketplace.html#town-project',actionLabel='Review saved goods')
    conflicts=order.get('supplyConflicts',[])
    if conflicts and not order['canFulfill']:
        return dict(title='Your project shares saved supplies',
                    detail=conflicts[0]+' also needs these supplies. Release it in Market to finish your project sooner.',
                    href='./marketplace.html#town-project',actionLabel='Review saved goods')
    return dict(title='Project '+str(count+1)+'/3 · '+project['title'],
                detail=('Ready to deliver. ' if order['canFulfill'] else
                        'Goods are being saved. ' if order.get('committed') else 'Save the project goods in Market. ')+project['rewardText']+'.',
                href='./marketplace.html#town-project',actionLabel='View project')


def payload(cfg,st,cls,session,behind=False):
    _sync_project_offer(cfg,st)
    _sync_pools(cfg,st)
    g=cfg['global'];goods=catalog(cfg);rates,regular_flow=_flows(cfg,st);protected=protected_stock(cfg,st)
    receipts=earnings.payload(cfg,st)
    activity=business_activity.payload(cfg,st)
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
        potential_income=sum(rates[x['id']]['retail']*x['unitPrice'] for x in t['goods'])+regular_flow['byBuilding'].get(str(slot),0)
        shop_receipts=receipts['byBuilding'][str(slot)]
        income=shop_receipts['operatingIncome']
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
        item=dict(earnings=shop_receipts,activity=activity['byBuilding'][str(slot)],slot=slot,tier=ti,id=t['id'],name=t['name'],family=t['family'],lv=b['lv'],
                  maxed=upgrades['production']['cost'] is None,auto=b['sales'],autoLabel='Customers '+str(b['sales']),
                  revenuePerTick=jsround(income*g['tick']/60),productionPerMinute=round(production,2),
                  productionCapacityPerMinute=_upgrade_capacity(cfg,st,slot,'production'),
                  salesPerMinute=round(sales,2),customerCapacityPerMinute=_upgrade_capacity(cfg,st,slot,'sales'),incomePerMinute=round(income,2),potentialIncomePerMinute=round(potential_income,2),status=status,reserve=b['reserve'],
                  processing=b.get('processing',True),hasRecipes=bool(recipes),
                  upgrades=upgrades,stored=storage,capacity=cap,storedValue=st['pend'][str(slot)],goods=rows,
                  recipe=recipes[-1] if recipes else None,recipes=recipes,price=1,priceTrend='flat',setBadges=[],
                  levelCost=upgrades['production']['cost'],levelPayback=None,autoCost=upgrades['sales']['cost'],autoPayback=None,
                  clearableQuantity=clear_qty,clearStockValue=clear_value)
        art_level=max(b['lv'],b['sales'],b['storage'])
        item['artLevel']=6 if art_level>=6 else min(3,art_level)
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
        held=delivery_reservations(cfg,st,exclude=order['id'])
        requirements=[dict(n,name=goods[n['goodId']]['name'],owned=max(0,inventory.get(n['goodId'],0)-held.get(n['goodId'],0)),
                           buildingId=goods[n['goodId']]['buildingId']) for n in order['requirements']]
        missing=[n for n in requirements if n['owned']<n['quantity']]
        access=town_projects.check(cfg,st,order['id']) if order.get('project') else dict(ok=True)
        ready=not missing and access['ok']
        room=_commit_room(cfg,st,order) if access['ok'] else access
        target=sum(n['quantity'] for n in requirements);owned=sum(min(n['quantity'],n['owned']) for n in requirements)
        orders.append(dict(order,requirements=requirements,canFulfill=ready,locked=not access['ok'],
                           canCommit=room['ok'],commitWhy=room.get('why',''),
                           why=access.get('why','') if not access['ok'] else '' if ready else 'Need '+str(missing[0]['quantity']-missing[0]['owned'])+' '+missing[0]['name'],
                           target=target,delivered=owned,penalty=0,remainingSec=None,progressPercent=round(owned/target*100,1) if target else 100,building=order['name']))
        orders[-1]['supplyConflicts']=_project_supply_conflicts(cfg,st,order)
        orders[-1]['replaceRemainingSec']=0  # Also clears cooldowns from older saves.
    build=dict(tier=st['build']['i'],name=cfg['tiers'][st['build']['i']]['name'],remainingSec=max(0,(st['build']['t']-st['tick'])*g['tick'])) if st.get('build') else None
    capacity=sum(b['capacity'] for b in buildings);stored=sum(b['stored'] for b in buildings)
    income=round(sum(b['incomePerMinute'] for b in buildings),2);prod=round(sum(b['productionPerMinute'] for b in buildings),2)
    project_order=next((o for o in orders if o.get('project')),None)
    available={n['goodId']:n['owned'] for n in project_order['requirements']} if project_order else {}
    project=town_projects.project_payload(cfg,st,available)
    step=opening_step(cfg,st,project,project_order,frontier,build)
    next_goal=step['title'] if step else 'Grow your businesses'
    newest=buildings[-1]
    return dict(modelVersion=4,tick=st['tick'],tickSeconds=g['tick'],behind=behind,cash=int(st['cash']),
                rulesRevision=3,townProjects=project,nextStep=step,earnings=receipts,potentialIncomePerMinute=round(town_income(cfg,st),2),regularDeliveries=st.get('regularDeliveries',0),regularTarget=3,
                customerContracts=customer_contract_payload(cfg,st),
                customerUnitsSold=st['report'].get('unitsSold',0),customerUnitsNeeded=100,materialUnitValue=cfg['production']['materialCashValue'],
                netWorth=net_worth(st),book=st['book'],taxPaid=st['taxPaid'],taxRate=0,
                incomePerMinute=income,productionPerMinute=prod,revenuePerTick=jsround(income*g['tick']/60),
                revenuePerDay=jsround(town_income(cfg,st)*1440),materials=st['materials'],buildings=buildings,buildingsOwned=len(buildings),
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
