"""Authoritative v4 production economy; v3 remains in economy.py as an oracle.

Goods and YM are whole integers. Each unlocked product is made independently;
retail and deliveries debit the same inventory. Fixed-point work survives JSON
reloads. New-rule operating expenses apply only to completed production.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
from delivery_recipes import ORDER_RECIPES
import business_activity
import business_operations
import business_progression
import business_rhythms
import inventory_costs
import operating_margins
import earnings
import rules_tables
import town_projects
import project_orders
import quest_engine
import workforce
import crafting
import crafting_pilot
import focus_tree
import market_orders
import economy as legacy
from economy import *  # Stable public helpers used by the classroom API.

CONFIG_PATH = Path(__file__).parent / 'config/economy.v4.json'

# Free offer rolls; rewards are paid only after the required goods are delivered.
ORDER_ROLLS = (
    dict(id='standard', label='Standard', chance=40, items=0, quantityPercent=100, payoutPercent=100),
    dict(id='small', label='Small order', chance=15, items=1, quantityPercent=50, payoutPercent=100),
    dict(id='bulk', label='Bulk order', chance=10, items=1, quantityPercent=300, payoutPercent=90),
    dict(id='large', label='Large order', chance=25, items=3, quantityPercent=150, payoutPercent=130),
    dict(id='rare', label='Rare order', chance=8, items=4, quantityPercent=200, payoutPercent=175),
    dict(id='jackpot', label='Jackpot order', chance=2, items=5, quantityPercent=250, payoutPercent=250),
)

# Regular customers buy one small shipment at a time. Terms are deterministic;
# accepting a customer authorizes automatic inventory sales, never cash spending.
# Catalog bundles keep their existing goods, quantities and schedules.
CUSTOMER_RETAIL_PERCENT = 90
CUSTOMER_CATALOG = (
    ('corner_grocer', 'Corner Grocer', 'Small tomato shipments with a quick turnaround.', 120,
     (('farm_tomatoes', 6),)),
    ('sunrise_diner', 'Sunrise Diner', 'A steady egg buyer for your farm.', 180,
     (('farm_eggs', 4),)),
    ('honey_collective', 'Honey Collective', 'Larger payments for slower honey shipments.', 300,
     (('farm_honey', 3),)),
    ('harbor_bistro', 'Harbor Bistro', 'Oysters and smoked fish for the lunch menu.', 240,
     (('fish_stall_oysters', 3), ('fish_stall_smoked_fish', 2))),
    ('copper_cafe', 'Copper Café', 'Regular coffee and pastry shipments from your roastery.', 300,
     (('roastery_espresso_shots', 4), ('roastery_pastries', 2))),
    ('rally_crew', 'Rally Crew', 'Custom mods turn spare parts into a regular payday.', 300,
     (('garage_custom_mods', 3),)),
    ('builders_union', 'Builders Union', 'Frames and machined bolts for local building work.', 360,
     (('workshop_welded_frames', 3), ('workshop_machined_bolts', 2))),
    ('neighborhood_grid', 'Neighborhood Grid', 'Battery storage and credits for local power users.', 360,
     (('solar_coop_battery_storage', 3), ('solar_coop_carbon_credits', 2))),
    ('pantry_network', 'Pantry Network', 'Canned food and preserves from your cannery.', 360,
     (('cannery_canned_goods', 4), ('cannery_preserves', 2))),
    ('inventors_lab', 'Inventors Lab', 'Tooling and prototype shipments for local inventors.', 420,
     (('machine_works_tooling', 3), ('machine_works_prototypes', 2))),
    ('clean_power_group', 'Clean Power Group', 'A regular buyer for wind capacity and certificates.', 420,
     (('turbine_field_capacity_contracts', 3), ('turbine_field_green_certificates', 2))),
    ('district_heating', 'District Heating', 'Peak power and steam heat supplied through your grid.', 420,
     (('generator_peak_power', 3), ('generator_steam_heat', 2))),
    ('mobile_network', 'Mobile Network', 'Tower leases and message services for a mobile network.', 480,
     (('relay_station_sms_traffic', 3), ('relay_station_tower_leases', 2))),
    ('city_couriers', 'City Couriers', 'Cold storage and last-mile delivery for local couriers.', 480,
     (('freight_terminal_cold_storage', 3), ('freight_terminal_last_mile_delivery', 2))),
    ('cloud_studio', 'Cloud Studio', 'Regular cloud storage and API service shipments.', 480,
     (('data_center_cloud_storage', 3), ('data_center_api_calls', 2))),
    ('regional_utility', 'Regional Utility', 'Reserve capacity and renewable credits for a regional utility.', 540,
     (('solar_array_reserve_capacity', 3), ('solar_array_renewable_credits', 2))),
    ('orbital_research', 'Orbital Research', 'Ground time and telemetry services for orbital research.', 540,
     (('uplink_center_ground_time', 3), ('uplink_center_telemetry', 2))),
)


def load_config(path=CONFIG_PATH):
    with open(path, encoding='utf8') as source:
        return json.load(source)


def catalog(cfg):
    return rules_tables.derived(cfg,'catalog',_build_catalog)


def _build_catalog(cfg):
    return {g['id']:dict(g, tier=i, buildingId=t['id'])
            for i,t in enumerate(cfg['tiers']) for g in t['goods']}


def _valid_slot(st, slot):
    return type(slot) is int and 0 <= slot < len(st['b'])


def _building(tier, lv=1, sales=1, storage=1):
    return dict(tier=tier,lv=lv,auto=sales,sales=sales,storage=storage,reserve=False,processing=True)


def new_state(cfg, start_tick=0, seed=1):
    st=legacy.new_state(cfg,start_tick,seed)
    st.update(modelVersion=4,productionMode='independent',b=[_building(0)],inventory={},productionWork={},productionPhase={},salesWork={},
              materials=0,lastActiveTick=start_tick,orderSerial=0,orderRecipeHistory=[[],[],[]],
              report=dict(produced=0,unitsProduced=0,retailEarned=0,unitsSold=0,
                          overflowSold=0,overflowCost=0,builds=0,offlineTicksSkipped=0))
    _customer_defaults(st)
    crafting.ensure(st)
    earnings.ensure(st)
    business_activity.ensure(st)
    business_operations.ensure(cfg,st,new=True)
    operating_margins.ensure(cfg,st)
    inventory_costs.migrate(cfg,st)
    workforce.ensure(cfg,st)
    business_progression.ensure(cfg,st)
    town_projects.default(cfg,st)
    focus_tree.ensure(cfg,st)
    offer_contracts(cfg,st,start_tick)
    _sync_project_offer(cfg,st)
    crafting_pilot.ensure(cfg,st)
    return st


def _independent_production_defaults(st):
    """Retire old recipe pauses and ingredient warnings without touching goods."""
    if st.get('productionMode') == 'independent': return
    for b in st.get('b', []): b['processing'] = True
    st['productionBlocked'] = {gid:reason for gid,reason in st.get('productionBlocked', {}).items()
                               if reason.get('reason') != 'ingredient'}
    st['productionMode'] = 'independent'


def migrate_state(cfg, st, tick=None):
    """Retain ownership and money; old monetary pools become cash, never goods.

    An active v3 contract's delivered value had already left its warehouse, so
    reimburse precisely that value, without awarding any unearned reward.
    The API records original JSON and handles clock reset for old snapshots.
    """
    if not isinstance(st,State): st=State(st)
    st['materials']=0
    for offer in (st.get('offers') or []) + [st.get('goalOffer')]:
        if offer:
            offer['materials']=0
            if offer.get('channelLabel') == 'Building supplies': offer['channelLabel']='Sector delivery'
    crafting.ensure(st)
    st.setdefault('productionPhase',{})
    _independent_production_defaults(st)
    st.setdefault('orderRecipeHistory',[[],[],[]])
    earnings.ensure(st)
    business_activity.ensure(st)
    # Existing v4 towns gain an empty roster without resetting their economy.
    _customer_defaults(st)
    focus_tree.ensure(cfg,st)
    _migrate_customer_rewards(cfg,st)
    if st.get('modelVersion')==4:
        workforce.ensure(cfg,st)
        business_operations.ensure(cfg,st)
        operating_margins.ensure(cfg,st)
        inventory_costs.migrate(cfg,st)
        business_progression.ensure(cfg,st,migrating=True)
        town_projects.migrate(cfg,st)
        _sync_project_offer(cfg,st)
        crafting_pilot.ensure(cfg,st)
        market_orders.defaults(cfg,st)
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
    workforce.ensure(cfg,st)
    business_operations.ensure(cfg,st)
    business_progression.ensure(cfg,st,migrating=True)
    operating_margins.prune(cfg,st,clear=True)
    inventory_costs.migrate(cfg,st)
    offer_contracts(cfg,st,st.get('tick',0))
    _sync_project_offer(cfg,st)
    crafting_pilot.ensure(cfg,st)
    focus_tree.ensure(cfg,st)
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
    speed += business_operations.speed_bonus(cfg,b,good)
    speed += business_progression.speed_bonus(cfg,st,b,good)
    speed += workforce.bonuses(cfg,st,b)['production']
    speed += focus_tree.speed_bonus(cfg,st,b,good)
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


def _current_sales_flows(cfg,st):
    """Sales possible under today's saved-stock choices, not all-output value.

    A finite saved order stops walk-ins buying its goods until its target is
    stocked. More output can shorten that wait without increasing current
    shop sales. Installed capacity remains available separately in ``_flows``.
    """
    rates,regulars=_flows(cfg,st)
    saved=order_reservations(st)
    regular_stock=_customer_reservations(cfg,st)
    for gid,quantity in saved.items():
        if gid in rates and st['inventory'].get(gid,0)-regular_stock.get(gid,0)<quantity:
            rates[gid]['retail']=0
    return rates,regulars


def _current_sales_income(cfg,st):
    goods=catalog(cfg);rates,regulars=_current_sales_flows(cfg,st)
    return sum(r['retail']*goods[gid]['unitPrice'] for gid,r in rates.items())+regulars['incomePerMinute']


def _upgrade_capacity(cfg,st,slot,kind):
    """Installed capacity, before shelf space or the cash budget limits it."""
    if kind=='storage': return _capacity(cfg,st,slot)
    b=st['b'][slot];goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    if kind=='production':
        rate=sum(product_speed(cfg,st,b,good)/100*good['quantity']*60/
                 (good['cycleTicks']*cfg['global']['tick']) for good in goods
                 if business_progression.product_unlocked(cfg,st,good['id']))
    else:
        rate=sum(customer_demand(cfg,st,b)/10000*60/
                 (good['cycleTicks']*cfg['global']['tick']) for good in goods)
    return round(rate,2)


def _optimized_production_income(cfg,st,slot):
    """Retail value of installed output with enough buyers.

    This isolated production potential assumes the business is running, all
    unlocked products can run, and every output can be sold. It does not
    forecast current sales, deduct production costs or credit any cash.
    """
    b=dict(st['b'][slot],paused=False)
    goods=cfg['tiers'][st['tierOf'][slot]]['goods']
    return sum(product_speed(cfg,st,b,good)/100*good['quantity']*60/
               (good['cycleTicks']*cfg['global']['tick'])*good['unitPrice']
               for good in goods if business_progression.product_unlocked(cfg,st,good['id']))


def upgrade_preview(cfg,st,slot,kind):
    after=copy.deepcopy(st);key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    after['b'][slot][key]+=1
    before_capacity=_upgrade_capacity(cfg,st,slot,kind)
    after_capacity=_upgrade_capacity(cfg,after,slot,kind)
    unit={'production':'goods/min','sales':'walk-ins/min','storage':'spaces'}[kind]
    income_before=round(_current_sales_income(cfg,st),2)
    income_after=round(_current_sales_income(cfg,after),2)
    delta=round(income_after-income_before,2)
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
        elif any(order_reservations(st).get(good['id'],0)>st['inventory'].get(good['id'],0)-_customer_reservations(cfg,st).get(good['id'],0) for good in goods):
            message='Goods are saved for an order · extra output helps fill it sooner'
        else: message='Customer demand limits income · extra output goes to stock'
    unlocks=kind=='production' and after['b'][slot]['lv']==3 and bool(focus_options(cfg,after['b'][slot]))
    result=dict(incomeBefore=income_before,incomeAfter=income_after,
                incomeDelta=delta,consequence=message,unlocksSpecialty=unlocks,
                capacityBefore=before_capacity,capacityAfter=after_capacity,capacityUnit=unit,
                effect=f'{before_capacity:g} → {after_capacity:g} {unit}')
    if kind=='production':
        optimized_before=round(_optimized_production_income(cfg,st,slot),2)
        optimized_after=round(_optimized_production_income(cfg,after,slot),2)
        result.update(optimizedIncomeBefore=optimized_before,optimizedIncomeAfter=optimized_after,
                      optimizedIncomeDelta=round(optimized_after-optimized_before,2))
    if business_operations.enabled(cfg):
        before_rates,before_regulars=_current_sales_flows(cfg,st)
        after_rates,after_regulars=_current_sales_flows(cfg,after)
        goods=cfg['tiers'][st['tierOf'][slot]]['goods']
        before_sales=sum(before_rates[g['id']]['retail']*g['unitPrice'] for g in goods)+before_regulars['byBuilding'].get(str(slot),0)
        after_sales=sum(after_rates[g['id']]['retail']*g['unitPrice'] for g in goods)+after_regulars['byBuilding'].get(str(slot),0)
        before_cost=business_operations.forecast_cost(cfg,st,slot,before_rates)
        after_cost=business_operations.forecast_cost(cfg,after,slot,after_rates)
        before_profit=before_sales-before_cost
        after_profit=after_sales-after_cost
        result.update(operatingCostScope='business',
                      businessIncomeBefore=round(before_sales,2),businessIncomeAfter=round(after_sales,2),
                      operatingCostBefore=round(before_cost,2),operatingCostAfter=round(after_cost,2),
                      operatingCostDelta=round(after_cost-before_cost,2),
                      profitBefore=round(before_profit,2),profitAfter=round(after_profit,2),
                      profitDelta=round(after_profit-before_profit,2))
        if operating_margins.enabled(cfg):
            before_statement=operating_margins.statement(cfg,st,slot,before_rates,before_sales,before_cost)
            after_statement=operating_margins.statement(cfg,after,slot,after_rates,after_sales,after_cost)
            result['operatingStatement']=dict(
                before=dict(sales=before_statement['potentialSales'],costs=before_statement['potentialCosts'],
                            profit=before_statement['potentialProfit']),
                after=dict(sales=after_statement['potentialSales'],costs=after_statement['potentialCosts'],
                           profit=after_statement['potentialProfit']))
    return result


def customer_demand(cfg, st, b):
    base = sales_multiplier(cfg, b)
    base += cfg['production']['customerBasePercent'] * workforce.bonuses(cfg,st,b)['customer']
    if cfg['tiers'][b['tier']]['id'] == 'roastery' and st.get('regularDeliveries', 0) >= 3:
        base = base * 120 // 100
    return base * focus_tree.demand_percent(cfg,st,b) // 100


def order_reservations(st, exclude=None, in_transit_only=False):
    """Committed orders own a bounded amount of stock, in board order."""
    held = {}
    orders = list(st.get('offers') or [])
    if st.get('goalOffer'):
        orders.append(st['goalOffer'])
    if st.get('legacyProjectOffer'):
        orders.append(st['legacyProjectOffer'])
    for order in orders:
        if (order.get('committed') and order['id'] != exclude
                and (not in_transit_only or order.get('inTransit'))):
            for need in order['requirements']:
                gid = need['goodId']
                held[gid] = held.get(gid, 0) + need['quantity']
    return held


def _held_stock(cfg,st):
    """Committed orders are protected from walk-in sales."""
    return order_reservations(st)


def protected_stock(cfg, st, held=None, plan=None):
    """Stock walk-ins may not sell. A tick that already holds this moment's
    _held_stock and _customer_stock_plan passes them in instead of redoing them."""
    if held is None: held=_held_stock(cfg,st)
    if plan is None: plan=_customer_stock_plan(cfg,st)
    protected=dict(held)
    for gid, qty in _regular_production_targets(cfg,st,plan[0]).items():
        protected[gid] = protected.get(gid, 0) + qty
    return protected


def sales_multiplier(cfg,b):
    return cfg['production']['customerBasePercent']*(100+cfg['production']['customerPerLevel']*(b['sales']-1))


def _capacity(cfg,st,slot):
    tier=cfg['tiers'][st['tierOf'][slot]]
    return math.floor(tier['capacity']*(1+cfg['production']['storagePerLevel']*(st['b'][slot]['storage']-1))
                      *focus_tree.storage_percent(cfg,st,tier)/100)


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
    """Compatibility helper: automatic production no longer reserves inputs."""
    return {}


def _produce(cfg,st,tick=None):
    inv=st['inventory'];pwork=st['productionWork'];made=0;value=0;by_building={}
    st['productionBlocked']={}
    # Keep a stable processing order when the shared cash budget is limited.
    for slot in sorted(range(len(st['b'])),key=lambda i:st['tierOf'][i]):
        b=st['b'][slot];tier=cfg['tiers'][st['tierOf'][slot]]
        if business_operations.paused(cfg,b): continue
        for good in tier['goods']:
            if not business_progression.product_unlocked(cfg,st,good['id']):
                st['productionBlocked'][good['id']]=dict(reason='quest');continue
            if business_rhythms.delay_tick(cfg,st,b,good): continue
            gid=good['id'];base_work=good['cycleTicks']*100
            multiplier=business_rhythms.batch_multiplier(cfg,b)
            work=pwork.get(gid,0)+product_speed(cfg,st,b,good)
            while work>=base_work:
                room=_good_capacity(cfg,st,slot,gid)-inv.get(gid,0)
                batches=min(multiplier,max(0,room//good['quantity']))
                if not batches:
                    st['productionBlocked'][gid]=dict(reason='storage')
                    work=min(work,base_work*multiplier);break
                if (batches>1 and business_operations.enabled(cfg)
                        and business_operations.batch_quote(cfg,b,good,st,batches=batches)[0]>st['cash']):
                    batches=1  # A small budget must not make an otherwise viable shop stall.
                required_work=base_work*batches
                if work<required_work: break
                cash_before=st['cash']
                if not business_operations.charge_batch(cfg,st,b,good,st.get('tick',0) if tick is None else tick,batches=batches):
                    st['productionBlocked'][gid]=dict(reason='cash')
                    work=min(work,base_work*multiplier);break
                quantity=good['quantity']*batches
                inventory_costs.produce(cfg,st,gid,quantity,cash_before-st['cash'])
                inv[gid]=inv.get(gid,0)+quantity
                business_progression.record_production(cfg,st,gid,quantity)
                made+=quantity;value+=quantity*good['unitPrice'];work-=required_work
                by_building[slot]=by_building.get(slot,0)+quantity
            pwork[gid]=work
    st['report']['produced']+=value;st['report']['unitsProduced']+=made
    business_activity.record(cfg,st,'production',by_building,tick=tick)


def _retail(cfg,st,tick=None,protected=None):
    inv=st['inventory'];earned=sold=0;by_building={};units_by_building={}
    delivered=[];costed={}
    if protected is None: protected=protected_stock(cfg,st)
    for slot,b in enumerate(st['b']):
        slot_income=0
        # Demand and closure are per business; no sale below changes them.
        demand=customer_demand(cfg,st,b);closed=b['reserve'] or business_operations.paused(cfg,b)
        for good in cfg['tiers'][st['tierOf'][slot]]['goods']:
            gid=good['id'];denom=good['cycleTicks']*10000
            # Idle demand cannot be banked then cashed in as unlimited customers.
            work=st['salesWork'].get(gid,0)+demand
            if closed:
                st['salesWork'][gid]=0;continue
            available=max(0,inv.get(gid,0)-protected.get(gid,0))
            take=min(available,int(work//denom))
            if take:
                costs=inventory_costs.consume(cfg,st,[dict(goodId=gid,quantity=take)])
                for identity,row in costs.items():
                    target=costed.setdefault(identity,dict(costMicros=0,estimated=False))
                    target['costMicros']+=row['costMicros']
                    target['estimated']=target['estimated'] or row['estimated']
                inv[gid]-=take;gross=take*good['unitPrice']
                delivered.append(dict(goodId=gid,quantity=take))
                business_progression.record_sale(cfg,st,[dict(goodId=gid,quantity=take)],'walkIns')
                earned+=gross;slot_income+=gross;sold+=take;work-=take*denom
                units_by_building[slot]=units_by_building.get(slot,0)+take
            st['salesWork'][gid]=work%denom
        by_building[slot]=slot_income
        history=st.setdefault('recentRetail',{}).setdefault(str(slot),[])
        history.append(slot_income)
        del history[:-max(1,round(60/cfg['global']['tick']))]
    st['report']['retailEarned']+=earned;st['report']['unitsSold']+=sold
    operating_margins.pay(cfg,st,'walkIns',earned,delivered,tick=tick,costed=costed)
    business_activity.record(cfg,st,'walkIns',units_by_building,tick=tick)


def player_tick(cfg,cls,st,k):
    workforce.ensure(cfg,st)
    business_operations.ensure(cfg,st)
    if st.get('build') is not None and k>=st['build']['t']:
        finish_build(cfg,st,k)
    _produce(cfg,st,k+1)
    # Committed orders and paused businesses stay as they are
    # while regulars ship and walk-ins buy, so both read them once.
    held=_held_stock(cfg,st);paused_goods=_paused_goods(cfg,st)
    plan=_tick_customer_contracts(cfg,st,k+1,paused_goods=paused_goods)
    crafting_pilot.tick(cfg,st,k+1)
    _retail(cfg,st,k+1,protected_stock(cfg,st,held,plan));_sync_pools(cfg,st)
    business_operations.advance_shifts(cfg,st)
    workforce.advance(cfg,st)
    st['tick']=k+1
    focus_tree.advance(cfg,st,st['tick'])


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
    with rules_tables.pinned(cfg):
        _advance_class(cfg,cls,players,start,target)


def _advance_class(cfg,cls,players,start,target):
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
            business_operations.prune(cfg,st,tick=target,clear=True)
            operating_margins.prune(cfg,st,tick=target,clear=True)
            # Production beyond the absence cap is never paid or caught up.
            # Preserve the interval remaining at the cap for the next visit.
            for contract in st.get('customerContracts',{}).get('active',[]):
                contract['nextDeliveryTick']+=skipped
        while st.get('build') and st['build']['t']<target:
            finish_build(cfg,st,st['build']['t'])
        st['tick']=max(st['tick'],target)
        focus_tree.advance(cfg,st,st['tick'])
        _sync_pools(cfg,st)
    cls['k']=max(0,target-1);cls['nextTick']=target
    cls['incomePerHour']=max(1,sum(revS(cfg,s) for s in players)*ticks_per_hour(cfg))


def on_login(cfg,st,k=None):
    k=st['tick'] if k is None else k
    st['lastLogin']=k;st['lastActiveTick']=k;st['catchupUntil']=-1
    market_orders.sync(cfg,st)


def bRev(cfg,st,bi): return jsround(_rate(cfg,st,bi)[1]*cfg['global']['tick']/60)
def revS(cfg,st): return sum(bRev(cfg,st,i) for i in range(len(st['b'])))
def warehouse_cap(cfg,st): return [_capacity(cfg,st,i) for i in range(len(st['b']))]
def net_worth(cfg_or_state,st=None):
    st=cfg_or_state if st is None else st
    return (int(st['cash'])+sum(st.get('pend',{}).values())+int(st['book'])
            +int(st.get('businessProgression',{}).get('equipmentValue',0))
            +crafting.stored_value(st)+crafting_pilot.stored_value(st))


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
    cover=quest_engine.voucher_cover(cfg,st,cost)
    cover+=focus_tree.voucher_cover(st,cost-cover)
    if st['cash']<cost-cover: return dict(ok=False,why=f'Need {cost-cover-st["cash"]} YM more')
    consequence=upgrade_preview(cfg,st,slot,kind)
    key={'production':'lv','sales':'sales','storage':'storage'}[kind]
    payable,covered=quest_engine.apply_voucher(cfg,st,cost)
    payable,focus_covered=focus_tree.apply_voucher(st,payable)
    covered+=focus_covered
    st['cash']-=payable;st['book']+=cost;st['b'][slot][key]+=1
    quest_engine.record_action(cfg,st,'upgrade')
    business_operations.record_investment(cfg,st,slot,cost)
    st['b'][slot]['auto']=st['b'][slot]['sales']
    if kind=='production' and st['b'][slot]['lv']>=cfg['gate']['levelNeeded']: st['checklist']['lv25']=True
    if kind=='sales': st['checklist']['auto']=True
    return dict(ok=True,kind='upgrade',upgrade=kind,cost=cost,voucherPaid=covered,level=st['b'][slot][key],**consequence)


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
    costed=inventory_costs.consume(cfg,st,[dict(goodId=gid,quantity=q) for gid,q in removed])
    for gid,q in removed: st['inventory'][gid]-=q
    business_progression.record_sale(cfg,st,[dict(goodId=gid,quantity=q) for gid,q in removed],'clearance')
    operating_margins.pay(cfg,st,'clearance',gross,costed=costed,requirements=
                          [dict(goodId=gid,quantity=q) for gid,q in removed])
    _sync_pools(cfg,st)
    return dict(ok=True,gross=gross,net=gross,tax=0,quantity=units,discountPercent=100-cfg['production']['clearStockPercent'])


def sell_all(cfg,st,mk=None,k=0,manual=False):
    return [sell_one(cfg,st,i) for i in range(len(st['b']))]


def expand_options(cfg,st):
    taken=set(st['tierOf']+st['queue']+([st['build']['i']] if st.get('build') else []))
    return [i for i in range(len(cfg['tiers'])) if i not in taken][:cfg['global']['frontier']]


def expansion_quote(cfg,st,ti):
    t=cfg['tiers'][ti]
    # Retired material fields stay zero for older clients and class snapshots.
    substitute=required=used=missing=0
    full_cost=t['baseCost']
    grant=town_projects.construction_grant(cfg,st,ti) or quest_engine.building_grant(cfg,st,t['id'])
    result=dict(baseCost=t['baseCost'],cost=0 if grant else full_cost,materialUnitValue=substitute,
                materialCost=required,materialsCost=required,materialsUsed=0 if grant else used,
                materialsMissing=0 if grant else missing,constructionGrant=grant,
                fundedValue=t['baseCost']+required*substitute if grant else 0)
    if business_operations.enabled(cfg):
        requirements=business_progression.expansion_requirements(cfg,st,ti)
        result.update(requirements=requirements['requirements'],requirementsReady=requirements['ready'],
                      requirementWhy=requirements.get('why',''),rebuildRemainingSeconds=business_operations.cooldown_seconds(cfg,st,ti))
    return result


def can_expand(cfg,st,ti):
    if type(ti) is not int or not 0<=ti<len(cfg['tiers']): return dict(ok=False,why='Unknown business')
    quote=expansion_quote(cfg,st,ti)
    if len(st['queue'])+bool(st.get('build'))>=cfg['global']['queueDepth']:
        return dict(quote,ok=False,why='Construction queue full')
    if ti not in expand_options(cfg,st): return dict(quote,ok=False,why='Choose an available business',frontier=expand_options(cfg,st))
    if quote.get('rebuildRemainingSeconds',0):
        return dict(quote,ok=False,why='Rebuild available in {}s'.format(quote['rebuildRemainingSeconds']))
    if not quote.get('requirementsReady',True): return dict(quote,ok=False,why=quote['requirementWhy'])
    if st['cash']<quote['cost']: return dict(quote,ok=False,why=f'Need {quote["cost"]-st["cash"]} YM more')
    return dict(quote,ok=True)


def expand(cfg,st,ti,tick):
    result=can_expand(cfg,st,ti)
    if not result['ok']: return result
    progression=business_progression.consume_expansion(cfg,st,ti)
    if not progression['ok']: return progression
    if result.get('constructionGrant'):
        claimed=town_projects.consume_construction_grant(cfg,st,ti)
        if not claimed['ok'] and not quest_engine.consume_building_grant(cfg,st,cfg['tiers'][ti]['id']): return claimed
    installed_non_cash=result.get('fundedValue',0)+progression.get('consumedValue',0)
    st['cash']-=result['cost'];st['book']+=result['cost']+installed_non_cash
    business_operations.reserve_construction(cfg,st,ti,result['cost'],installed_non_cash)
    if st.get('build') is None:
        st['build']=dict(i=ti,t=tick+max(1,jsround(cfg['tiers'][ti]['timerH']*3600/cfg['global']['tick'])))
    else: st['queue'].append(ti)
    quest_engine.record_action(cfg,st,'open_business')
    return result


def finish_build(cfg,st,k,DAY=None):
    ti=st['build']['i'];st['b'].append(_building(ti));st['tierOf'].append(ti);st['build']=None
    business_operations.complete_construction(cfg,st,len(st['b'])-1)
    st['unlock'][str(len(st['b'])-1)]=k/ticks_per_day(cfg);st['report']['builds']+=1
    if st.get('gateDay') is None and len(st['b'])>=cfg['global']['gateTier']: st['gateDay']=k/ticks_per_day(cfg)
    if st['queue']:
        ti=st['queue'].pop(0)
        st['build']=dict(i=ti,t=k+max(1,jsround(cfg['tiers'][ti]['timerH']*3600/cfg['global']['tick'])))
    _sync_pools(cfg,st)
    market_orders.sync(cfg,st)


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


def _customer_reward(cfg,requirements,st=None):
    """Discount the whole shipment, including larger orders, to whole YM."""
    goods=catalog(cfg)
    retail=sum(goods[n['goodId']]['unitPrice']*n['quantity'] for n in requirements)
    reward=jsround(retail*CUSTOMER_RETAIL_PERCENT/100)
    # Whole-YM rounding must not erase the discount on small bundles.
    reward=min(retail-1,max(1,reward)) if retail>1 else retail
    return focus_tree.regular_reward(st,reward) if st is not None else reward


def _migrate_customer_rewards(cfg,st):
    """Reprice future shipments in place; past earnings and schedules stay put."""
    for contract in st['customerContracts']['active']:
        contract['reward']=_customer_reward(cfg,contract['requirements'],st)


def _customer_catalog(cfg,st):
    goods=catalog(cfg);owned=set(st['tierOf']);customers=[]

    for customer_id,name,description,seconds,needs in CUSTOMER_CATALOG:
        # Small test/preview configurations may contain only some products.
        if any(gid not in goods for gid,qty in needs): continue
        required={gid for gid,qty in needs}
        missing=sorted({goods[gid]['tier'] for gid in required}-owned)
        locked=next((goods[gid] for gid in required if not business_progression.product_unlocked(cfg,st,gid)),None)
        requirements=[dict(goodId=gid,name=goods[gid]['name'],buildingId=goods[gid]['buildingId'],quantity=qty)
                      for gid,qty in needs]
        customers.append(dict(id=customer_id,name=name,description=description,available=not missing and locked is None,
                              unlockText='Open '+', '.join(cfg['tiers'][ti]['name'] for ti in missing) if missing else
                              'Complete the product quest for '+locked['name'] if locked else '',
                              requirements=requirements,reward=_customer_reward(cfg,requirements,st),
                              intervalSeconds=seconds))
    return customers


def _paused_goods(cfg,st):
    """Products of paused businesses; their regulars wait."""
    if not business_operations.enabled(cfg): return frozenset()
    return {good['id'] for slot,b in enumerate(st['b']) if business_operations.paused(cfg,b)
            for good in cfg['tiers'][st['tierOf'][slot]]['goods']}


def _customer_business_paused(cfg,st,contract,paused_goods=None):
    if paused_goods is None: paused_goods=_paused_goods(cfg,st)
    return any(need['goodId'] in paused_goods for need in contract['requirements'])


def _customer_stock_plan(cfg,st,transit=None,paused_goods=None):
    """Give each regular's next shipment first claim on available shelf space.

    Earlier customer slots claim first. Only goods already dispatched are
    unavailable; idle manual commitments cannot displace
    regulars. Targets protect newly produced stock as well as current stock.
    """
    active=st.get('customerContracts',{}).get('active',[])
    if not active: return {},{}
    goods=catalog(cfg)
    protected=order_reservations(st,in_transit_only=True) if transit is None else transit
    if paused_goods is None: paused_goods=_paused_goods(cfg,st)
    totals={};assigned={};by_tier={ti:i for i,ti in enumerate(st['tierOf'])}
    for contract in sorted(active,key=lambda c:c['slot']):
        stock={};assigned[contract['id']]=stock
        if contract['paused'] or _customer_business_paused(cfg,st,contract,paused_goods): continue
        for need in contract['requirements']:
            gid=need['goodId'];slot=by_tier[goods[gid]['tier']]
            prior=protected.get(gid,0)+totals.get(gid,0)
            target=min(need['quantity'],max(0,_good_capacity(cfg,st,slot,gid)-prior))
            stock[gid]=min(target,max(0,st['inventory'].get(gid,0)-prior))
            totals[gid]=totals.get(gid,0)+target
    return totals,assigned


def _customer_reservations(cfg,st):
    return _customer_stock_plan(cfg,st)[0]


def _regular_production_targets(cfg,st,direct=None):
    """Save only the finished goods in each regular's next shipment."""
    return dict(_customer_reservations(cfg,st) if direct is None else direct)


def delivery_reservations(cfg,st,exclude=None):
    """Manual deliveries use stock left after regulars and other saved orders."""
    if any(o['id']==exclude and o.get('inTransit') for o in st.get('offers') or []):
        # These goods were dispatched already; new buyers cannot recall them.
        return order_reservations(st,exclude=exclude,in_transit_only=True)
    held=order_reservations(st,exclude=exclude)
    for gid,qty in _regular_production_targets(cfg,st).items():
        held[gid]=held.get(gid,0)+qty
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
        _freeze_selling_terms(cfg,st,replacement)
        if current is not None: data['active'].remove(current)
        data['active'].append(replacement)
        data['active'].sort(key=lambda c:c['slot'])
        if action=='accept': quest_engine.record_action(cfg,st,'set_regular')
        return dict(ok=True,kind='customer_contract',action=action,contractId=replacement['id'])
    if action in ('upgrade','downgrade'):
        larger=action=='upgrade'
        requirements=[dict(goodId=n['goodId'],quantity=n['quantity']*(2 if larger else 1))
                      for n in customer['requirements']]
        data['serial']+=1
        current.update(id='regular-{}-{}'.format(st.get('rngState',1),data['serial']),largerOrder=larger,
                       reward=_customer_reward(cfg,requirements,st),requirements=requirements,
                       nextDeliveryTick=st['tick']+current['intervalTicks'])
        current.pop('sellingTerms',None)
        _freeze_selling_terms(cfg,st,current)
        if larger: quest_engine.record_action(cfg,st,'upgrade_regular')
        return dict(ok=True,kind='customer_contract',action=action,contractId=current['id'])
    if action=='release': data['active'].remove(current)
    elif action=='pause': current['paused']=True
    elif current['paused']:
        current['paused']=False
        current['nextDeliveryTick']=st['tick']+current['intervalTicks']
    return dict(ok=True,kind='customer_contract',action=action,contractId=contract_id)


def _tick_customer_contracts(cfg,st,tick,transit=None,paused_goods=None):
    """Ship every due regular whose shipment is saved up. Returns the stock
    plan still valid afterwards - None once a delivery changed the stock - so
    the same tick's walk-in sales can reuse it instead of redoing it."""
    if focus_tree.has(st,'breakfast_regulars'): _migrate_customer_rewards(cfg,st)
    data=st.get('customerContracts',{})
    active=sorted(data.get('active',[]),key=lambda c:c['slot'])
    if not active: return None
    if transit is None: transit=order_reservations(st,in_transit_only=True)
    if paused_goods is None: paused_goods=_paused_goods(cfg,st)
    plan=None
    for contract in active:
        if contract['paused'] or _customer_business_paused(cfg,st,contract,paused_goods) or tick<contract['nextDeliveryTick']: continue
        # A regular that is skipped changes nothing the plan reads; a delivery does.
        if plan is None: plan=_customer_stock_plan(cfg,st,transit,paused_goods)
        stock=plan[1].get(contract['id'],{})
        if any(stock.get(n['goodId'],0)<n['quantity'] for n in contract['requirements']): continue
        _freeze_selling_terms(cfg,st,contract)
        # Debit every item together; shortages never receive partial payments.
        costed=inventory_costs.consume(cfg,st,contract['requirements'])
        for need in contract['requirements']: st['inventory'][need['goodId']]-=need['quantity']
        operating_margins.pay(cfg,st,'regularBuyers',contract['reward'],contract['requirements'],costed=costed,
                              tick=tick,terms=contract.get('sellingTerms'))
        business_activity.record_regular_shipment(cfg,st,contract['requirements'],tick=tick)
        business_progression.record_sale(cfg,st,contract['requirements'],'regularBuyers')
        contract['deliveries']+=1;contract['earned']+=contract['reward']
        data['deliveries']+=1;data['earned']+=contract['reward']
        st['report']['customerEarned']+=contract['reward']
        st['report']['customerDeliveries']+=1
        data['history'][contract['customerId']]=dict(deliveries=contract['deliveries'],earned=contract['earned'])
        # A late shipment starts a new full interval; there is no missed backlog.
        contract['nextDeliveryTick']=tick+contract['intervalTicks']
        plan=None
    return plan


def customer_contract_payload(cfg,st):
    if focus_tree.has(st,'breakfast_regulars'): _migrate_customer_rewards(cfg,st)
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
        if _customer_business_paused(cfg,st,contract):
            status='paused';status_text='A supplying business is paused · resume it to ship'
        larger=contract.get('largerOrder',False);offer=None
        if not larger and contract['deliveries']>=3 and contract['customerId'] in by_id:
            base=by_id[contract['customerId']]
            larger_requirements=[dict(n,quantity=n['quantity']*2) for n in base['requirements']]
            offer=dict(reward=_customer_reward(cfg,larger_requirements,st),intervalSeconds=contract['intervalSeconds'],
                       requirements=larger_requirements)
        active.append(dict(slot=contract['slot'],id=contract['id'],customerId=contract['customerId'],
                           name=contract['name'],paused=contract['paused'],deliveries=contract['deliveries'],
                           earned=contract['earned'],reward=contract['reward'],intervalSeconds=contract['intervalSeconds'],
                           nextDeliverySeconds=remaining,requirements=requirements,status=status,statusText=status_text,
                           largerOrder=larger,largerOffer=offer))
    return dict(slots=slots,maxSlots=4,nextUnlock=dict(buildings=3,slots=3) if slots==2 else dict(buildings=6,slots=4) if slots==3 else None,
                earned=data.get('earned',0),deliveries=data.get('deliveries',0),customers=customers,active=active)


def _order_recipe(cfg,st,index,rarity,digest,goods,target_tier=None):
    """Deal a complete job the town can produce, with a saved rotation per slot.

    Eligibility follows owned businesses and unlocked products.
    Recipes are authored bundles: larger rolls never pad them with random goods.
    """
    owned=set(st['tierOf'])
    def can_make(gid):
        return gid in goods and goods[gid]['tier'] in owned and business_progression.product_unlocked(cfg,st,gid)
    eligible=[r for r in ORDER_RECIPES if all(can_make(gid) for gid in r['goods'])]
    if target_tier is not None:
        eligible=[r for r in eligible if any(goods[gid]['tier']==target_tier for gid in r['goods'])]
    if index==2 and not business_progression.connected_enabled(cfg):
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
    order=town_projects.current_order(cfg,st) or dict(
        id='town-project-complete',name='Town projects complete',project=True,completed=True,
        requirements=[],reward=0,materials=0,customer=None,committed=False,
        purpose='Your opening projects are complete.',channelLabel='Town projects')
    if order['requirements']: _freeze_selling_terms(cfg,st,order)
    return order


def _sync_project_offer(cfg,st):
    offers=st.get('offers') or []
    if business_progression.connected_enabled(cfg):
        if not town_projects.connected(cfg):
            st.pop('goalOffer',None)
            st.pop('legacyProjectOffer',None)
            return
        if len(offers)>2 and offers[2].get('project'):
            # A saved fixed delivery retains its exact terms outside the three
            # active containers. Already completed cards promise no more reward.
            current=town_projects.current_order(cfg,st)
            if current and offers[2]['id']==current['id']:
                st.setdefault('legacyProjectOffer',copy.deepcopy(offers[2]))
            offers[2]=_make_order(cfg,st,2)
        goal=project_orders.sync(cfg,st,can_make=lambda gid: business_progression.product_unlocked(cfg,st,gid))
        if goal: _freeze_selling_terms(cfg,st,goal)
        return
    if len(offers)>2 and offers[2].get('project'):
        current=_project_order(cfg,st)
        if offers[2]['id']!=current['id']: offers[2]=current


def _make_order(cfg,st,index,target_tier=None):
    if index==2 and town_projects.enabled(cfg) and not business_progression.connected_enabled(cfg): return _project_order(cfg,st)
    goods=catalog(cfg)
    if target_tier is None: target_tier=market_orders.pending_tier(cfg,st)
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
    recipe=_order_recipe(cfg,st,index,rarity,digest,goods,target_tier)
    picks=[goods[gid] for gid in recipe['goods']]
    requirements=[];value=0
    for good in picks:
        # Normal rolls keep fixed sizes. Bulk rolls can clear existing spare
        # stock without changing their rarity, product rotation or unit price.
        qty=max(2,math.ceil(cfg['production']['orderMinutes'][index]*60/(good['cycleTicks']*cfg['global']['tick'])))
        qty=math.ceil(qty*rarity['quantityPercent']/100)
        if rarity['id']=='bulk':
            previous=(st.get('offers') or [])[index:index+1]
            held=delivery_reservations(cfg,st,exclude=previous[0]['id'] if previous else None)
            qty=max(qty,st['inventory'].get(good['id'],0)-held.get(good['id'],0))
        slot=st['tierOf'].index(goods[good['id']]['tier'])
        qty=min(qty,_good_capacity(cfg,st,slot,good['id']))
        requirements.append(dict(goodId=good['id'],quantity=qty));value+=qty*good['unitPrice']
    materials=0
    reward_percent=jsround([125,110,115][index]*rarity['payoutPercent']/100)
    breakfast=index==2 and recipe['breakfast'] and not business_progression.connected_enabled(cfg)
    order=dict(id=f'order-{st.get("rngState",1)}-{serial}',name=recipe['name'],recipeId=recipe['id'],purpose=recipe['purpose'],
                channelLabel=['Quick cash','Sector delivery','Product deliveries' if business_progression.connected_enabled(cfg) else 'Breakfast regulars' if breakfast else 'Town deliveries'][index],
                requirements=requirements,reward=jsround(value*reward_percent/100),materials=materials,
                customer='breakfast' if breakfast else None,committed=False,
                rarity=rarity['id'],rarityLabel=rarity['label'],rewardPercent=reward_percent,retailValue=value)
    _freeze_selling_terms(cfg,st,order)
    return order


def _freeze_selling_terms(cfg,st,order):
    """Freeze invoice expenses without changing the promised take-home reward."""
    # A newly authored/replaced requirement list needs its own terms; existing
    # quotes remain frozen when only the world's current tariff changes.
    quoted=set(order.get('sellingTerms',{}).get('feeMicrosByGood',{}))
    requested={need['goodId'] for need in order['requirements']}
    if operating_margins.enabled(cfg) and (not order.get('sellingTerms') or quoted!=requested):
        # Project previews can name a future producer. Freeze product tariffs
        # without allocating a payment to buildings the player does not own yet.
        fees=operating_margins.tariffs(cfg)
        order['sellingTerms']=dict(feeMicrosByGood={gid:fees[gid] for gid in requested})


def offer_contracts(cfg,st,k,DAY=None):
    st.setdefault('orderSerial',0)
    if st.get('offers') is None: st['offers']=[_make_order(cfg,st,i) for i in range(3)]
    market_orders.defaults(cfg,st)


def _order_at(st,index):
    if index==3: return st.get('goalOffer')
    offers=st.get('offers') or []
    return offers[index] if type(index) is int and 0<=index<min(3,len(offers)) else None


def _order_check(st,index,order_id):
    if type(index) is not int or not _order_at(st,index): return dict(ok=False,why='Choose a delivery')
    order=_order_at(st,index)
    if order_id is not None and order_id!=order['id']: return dict(ok=False,why='This delivery changed. Try again.')
    return dict(ok=True)


def fulfill_order(cfg,st,offerIndex,order_id=None):
    check=_order_check(st,offerIndex,order_id)
    if not check['ok']: return check
    order=_order_at(st,offerIndex)
    result=_settle_order(cfg,st,order)
    if result['ok']:
        if offerIndex==3:
            st.pop('goalOffer',None)
        else:
            st['offers'][offerIndex]=_make_order(cfg,st,offerIndex)
        _sync_project_offer(cfg,st)
        _sync_pools(cfg,st)
    return result


def _settle_order(cfg,st,order):
    """One debit and payment, followed by observations of that same delivery."""
    goods=catalog(cfg)
    if order.get('goalOrder'):
        access=project_orders.check(cfg,st,order)
        if not access['ok']: return access
    if order.get('project'):
        access=town_projects.check(cfg,st,order['id'])
        if not access['ok']: return access
    held=delivery_reservations(cfg,st,exclude=order['id'])
    for need in order['requirements']:
        if st['inventory'].get(need['goodId'],0)-held.get(need['goodId'],0)<need['quantity']:
            return dict(ok=False,why='Need unreserved '+goods[need['goodId']]['name'])
    _freeze_selling_terms(cfg,st,order)
    costed=inventory_costs.consume(cfg,st,order['requirements'])
    for need in order['requirements']: st['inventory'][need['goodId']]-=need['quantity']
    reward=focus_tree.order_reward(st,order['reward'])
    order['reward'],boosted=quest_engine.apply_boost(cfg,st,'order_payout',reward)
    operating_margins.pay(cfg,st,'orders',order['reward'],order['requirements'],costed=costed,
                          terms=order.get('sellingTerms'))
    order['materials']=0  # Ignore rewards embedded in pre-removal saves.
    business_progression.record_sale(cfg,st,order['requirements'],'orders')
    if not order.get('project'):
        town_projects.record_delivery(cfg,st,order['requirements'],order['id'])
    st['cStats']['accepted']+=1;st['cStats']['done']+=1
    crafting_pilot.record_order(cfg,st,order['requirements'])
    quest_engine.record_order(cfg,st)
    raw_value=sum(goods[n['goodId']]['unitPrice']*n['quantity'] for n in order['requirements'])
    st['cStats']['net']+=order['reward']-raw_value;st['checklist']['goodSales']=st['cStats']['done']
    if order.get('customer') == 'breakfast':
        st['regularDeliveries']=min(3,st.get('regularDeliveries',0)+1)
    project_result=town_projects.complete(cfg,st,order['id']) if order.get('project') else {}
    return dict(ok=True,kind='delivery',reward=order['reward'],boostMultiplier=boosted,materials=order['materials'],orderId=order['id'],
                projectReward=project_result.get('rewardText',''))


def fulfill_legacy_project(cfg,st,order_id):
    order=st.get('legacyProjectOffer')
    if not business_progression.connected_enabled(cfg) or not order or order.get('id')!=order_id:
        return dict(ok=False,why='This saved project delivery is no longer available')
    result=_settle_order(cfg,st,order)
    if result['ok']:
        st.pop('legacyProjectOffer',None)
        _sync_project_offer(cfg,st)
        _sync_pools(cfg,st)
    return result


def claim_group_project(cfg,st,project_id):
    if st.get('legacyProjectOffer'):
        return dict(ok=False,why='Finish your saved project delivery first')
    result=town_projects.claim(cfg,st,project_id)
    if result['ok']:
        st['cash']+=result['cashReward']
        earnings.record(cfg,st,'events',result['cashReward'])
        # Claiming completes this goal; any leftover goal-only allocation is
        # released. The player's three ordinary saved orders stay untouched.
        st.pop('goalOffer',None)
        _sync_project_offer(cfg,st)
    return result


def replace_order(cfg,st,offerIndex,order_id=None):
    check=_order_check(st,offerIndex,order_id)
    if not check['ok']: return check
    if _order_at(st,offerIndex).get('project') or _order_at(st,offerIndex).get('goalOrder'):
        return dict(ok=False,why='This goal order stays available. Save goods and deliver to advance.')
    st['offers'][offerIndex]=_make_order(cfg,st,offerIndex)
    return dict(ok=True,kind='replace_order')


def _commit_room(cfg,st,order):
    goods=catalog(cfg);held=order_reservations(st,exclude=order['id'])
    for gid,qty in _customer_reservations(cfg,st).items():
        held[gid]=held.get(gid,0)+qty
    for need in order['requirements']:
        gid=need['goodId'];tier=goods[gid]['tier']
        if tier not in st['tierOf']:
            return dict(ok=False,why='Open '+cfg['tiers'][tier]['name']+' first')
        slot=st['tierOf'].index(tier)
        if held.get(gid,0)+need['quantity']>_good_capacity(cfg,st,slot,gid):
            return dict(ok=False,why='Not enough shelf room for saved orders and regular buyers. Release an order, pause a buyer, or upgrade storage.')
    return dict(ok=True)


def commit_order(cfg,st,index,order_id,committed):
    check=_order_check(st,index,order_id)
    if not check['ok']: return check
    if type(committed) is not bool: return dict(ok=False,why='committed must be true or false')
    order=_order_at(st,index)
    if committed and order.get('goalOrder'):
        access=project_orders.check(cfg,st,order)
        if not access['ok']: return access
    if committed and order.get('project'):
        access=town_projects.check(cfg,st,order['id'])
        if not access['ok']: return access
    if committed:
        room=_commit_room(cfg,st,order)
        if not room['ok']: return room
        _freeze_selling_terms(cfg,st,order)
    order['committed']=committed
    if not committed and order.get('goalOrder'):
        _sync_project_offer(cfg,st)
    return dict(ok=True,kind='order_commit',committed=committed)


def accept_contract(cfg,st,offer_idx,k): return fulfill_order(cfg,st,offer_idx)
def tick_contracts(cfg,st,k,produced): return None

def gate_open(cfg,st):
    if st.get('licenceGrandfathered'): return True
    c=st['checklist']
    experience=st['cStats']['done']>=cfg['gate']['goodSalesNeeded'] or st['report'].get('unitsSold',0)>=100
    return len(st['b'])>=cfg['global']['gateTier'] and c['lv25'] and c['auto'] and experience and c['quiz']


def _flows(cfg,st):
    """Independent production capacity allocated to regulars, then walk-ins.

    This forecast shows the current configuration's capacity; actual income is
    reported separately from completed sales. No income is credited by it.
    """
    if focus_tree.has(st,'breakfast_regulars'): _migrate_customer_rewards(cfg,st)
    capacities={};by_tier={ti:i for i,ti in enumerate(st['tierOf'])}
    for ti in sorted(by_tier):
        b=st['b'][by_tier[ti]]
        for g in cfg['tiers'][ti]['goods']:
            rate=product_speed(cfg,st,b,g)/100*60/(g['cycleTicks']*cfg['global']['tick'])
            if business_operations.paused(cfg,b) or not business_progression.product_unlocked(cfg,st,g['id']): rate=0
            capacities[g['id']]=rate*g['quantity']
    regulars=earnings.allocate_regular_flow(cfg,st,capacities)
    rates={gid:dict(production=rate,retail=0) for gid,rate in capacities.items()}
    for ti,slot in by_tier.items():
        b=st['b'][slot]
        for g in cfg['tiers'][ti]['goods']:
            rates[g['id']]['regulars']=regulars['unitsPerMinute'].get(g['id'],0)
            demand=customer_demand(cfg,st,b)/10000*60/(g['cycleTicks']*cfg['global']['tick'])
            rates[g['id']]['retail']=0 if b['reserve'] or business_operations.paused(cfg,b) else min(regulars['remaining'][g['id']],demand)
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
    needed={need['goodId'] for need in order['requirements']}
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


def group_opening_step(group,frontier,build):
    if not group.get('enabled'):
        return None
    if build:
        return dict(title=build['name']+' is being built',
                    detail=str(build['remainingSec'])+'s remaining. Your other businesses keep working.')
    funded=next((item for item in frontier if item.get('constructionGrant')),None)
    if funded:
        return dict(title='Your '+funded['name']+' is fully funded',
                    detail='The group project earned this construction grant.',
                    action='expand:'+str(funded['tier']),actionLabel='Build with grant',disabled=not funded['canExpand'])
    if group.get('legacyDelivery'):
        return dict(title='Finish your saved project delivery',
                    detail='Its original goods and rewards are preserved.',
                    href='./buildings.html#group-projects',actionLabel='View saved delivery')
    current=group.get('current')
    if not current:
        return None
    return dict(title='Group project '+str(group['completed']+1)+'/'+str(group['total'])+' · '+current['title'],
                detail=('Ready to claim. ' if current['canClaim'] else current['why']+'. ')+current['rewardText']+'.',
                action='group_project_claim:'+current['projectId'] if current['canClaim'] else None,
                href=None if current['canClaim'] else './marketplace.html',
                actionLabel='Claim group reward' if current['canClaim'] else 'View orders')


def _order_supply(cfg,st,order,session):
    """Facts for a bounded, read-only supply estimate; no economy replay."""
    goods=catalog(cfg);saved=order_reservations(st,exclude=order['id'])
    transit=order_reservations(st,exclude=order['id'],in_transit_only=True)
    regular_stock=_customer_reservations(cfg,st)
    slots={tier:slot for slot,tier in enumerate(st['tierOf'])}
    rows={}
    for need in order['requirements']:
        gid=need['goodId'];good=goods[gid];slot=slots.get(good['tier'])
        row=dict(name=good['name'],stored=st['inventory'].get(gid,0),
                 savedReserved=saved.get(gid,0),regularReserved=regular_stock.get(gid,0),
                 inTransitReserved=transit.get(gid,0),producerOwned=slot is not None,
                 unlocked=business_progression.product_unlocked(cfg,st,gid),
                 cycleTicks=good['cycleTicks'],quantity=good['quantity'],
                 work=st['productionWork'].get(gid,0))
        if slot is not None:
            b=st['b'][slot];tier=cfg['tiers'][good['tier']]
            phase=0
            if business_rhythms.enabled(cfg) and tier['family']=='E':
                index=next(i for i,g in enumerate(tier['goods']) if g['id']==gid)
                phase=st.get('productionPhase',{}).get(gid,min(index,max(0,good['cycleTicks']-1)))
            row.update(capacity=_good_capacity(cfg,st,slot,gid),speed=product_speed(cfg,st,b,good),
                       batchMultiplier=business_rhythms.batch_multiplier(cfg,b),delayTicks=phase,
                       batchCost=business_operations.effective_batch_cost(cfg,b,good,st)
                                 if business_operations.enabled(cfg) else 0,
                       nextBatchCost=business_operations.batch_quote(cfg,b,good,st)[0]
                                 if business_operations.enabled(cfg) else 0,
                       paused=business_operations.paused(cfg,b))
        rows[gid]=row
    regulars=[dict(name=c['name'],requirements=c['requirements'],
                   nextTicks=max(0,c['nextDeliveryTick']-st['tick']),intervalTicks=c['intervalTicks'])
              for c in sorted(st.get('customerContracts',{}).get('active',[]),key=lambda c:c['slot'])
              if not c['paused'] and not _customer_business_paused(cfg,st,c)]
    return dict(tickSeconds=cfg['global']['tick'],cash=st['cash'],paused=bool(session['paused']),
                goods=rows,regulars=regulars)


def payload(cfg,st,cls,session,behind=False):
    business_operations.ensure(cfg,st)
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
                     inputs=[])
            rows.append(row);board.append(row)
            if business_rhythms.enabled(cfg):
                multiplier=business_rhythms.batch_multiplier(cfg,b)
                speed=product_speed(cfg,st,b,good)
                row['productionBatch']=dict(quantity=good['quantity']*multiplier,
                    averageSeconds=round(good['cycleTicks']*g['tick']*multiplier*100/speed,2) if speed>0 else None)
            if business_operations.enabled(cfg):
                locked=not business_progression.product_unlocked(cfg,st,good['id'])
                row.update(locked=locked,unlockText='Complete this business’s second quest to unlock' if locked else '',
                           operatingCostPerBatch=business_operations.effective_batch_cost(cfg,b,good,st))
        production=sum(rates[x['id']]['production'] for x in t['goods'])
        sales=sum(rates[x['id']]['retail'] for x in t['goods'])
        potential_income=sum(rates[x['id']]['retail']*x['unitPrice'] for x in t['goods'])+regular_flow['byBuilding'].get(str(slot),0)
        shop_receipts=receipts['byBuilding'][str(slot)]
        # Income/min is the installed earning rate, so purchases update it in
        # this response. Completed payments remain in the earnings receipt.
        income=potential_income
        storage=_goods_count(cfg,st,slot);cap=_capacity(cfg,st,slot)
        status='Working'
        if b['reserve']: status='Saving goods'
        elif any(r['quantity']>=r['capacity'] for r in rows): status='Storage full'
        elif any(r['quantity']>max(2,r['reserved']) for r in rows) and sales<production:
            status='More customers needed' if b['sales']<cfg['production']['maxLevel'] else 'Goods ready'
        if business_operations.paused(cfg,b): status='Business paused'
        elif any(st.get('productionBlocked',{}).get(good['id'],{}).get('reason')=='cash'
                 and business_operations.batch_quote(cfg,b,good,st)[0]>st['cash'] for good in t['goods']):
            status='Need cash for production'
        upgrades={}
        for kind,key in (('production','lv'),('sales','sales'),('storage','storage')):
            cost=upgrade_cost(cfg,st,slot,kind);level=b[key]
            covered=quest_engine.voucher_cover(cfg,st,cost) if cost is not None else 0
            covered+=focus_tree.voucher_cover(st,cost-covered) if cost is not None else 0
            payable=cost-covered if cost is not None else None
            why='Fully upgraded' if cost is None else f'Need {payable-st["cash"]} YM more' if payable>st['cash'] else ''
            if kind=='production': effect=f'{100+cfg["production"]["speedPerLevel"]*level}% base speed'
            elif kind=='sales': effect=f'{100+cfg["production"]["customerPerLevel"]*level}% base customers'
            else: effect=f'{math.floor(t["capacity"]*(1+cfg["production"]["storagePerLevel"]*level)*focus_tree.storage_percent(cfg,st,t)/100)} items'
            upgrades[kind]=dict(level=level,cost=cost,cashCost=payable,voucherPaid=covered,
                                canBuy=payable is not None and payable<=st['cash'],why=why,effect=effect)
            if cost is not None: upgrades[kind].update(upgrade_preview(cfg,st,slot,kind))
        clear_qty=sum(max(0,inventory.get(x['id'],0)-protected.get(x['id'],0)) for x in t['goods'])
        clear_value=sum(max(0,inventory.get(x['id'],0)-protected.get(x['id'],0))*x['unitPrice'] for x in t['goods'])*cfg['production']['clearStockPercent']//100
        item=dict(earnings=shop_receipts,activity=activity['byBuilding'][str(slot)],slot=slot,tier=ti,id=t['id'],name=t['name'],family=t['family'],lv=b['lv'],
                  maxed=upgrades['production']['cost'] is None,auto=b['sales'],autoLabel='Customers '+str(b['sales']),
                  revenuePerTick=jsround(income*g['tick']/60),productionPerMinute=round(production,2),
                  productionCapacityPerMinute=_upgrade_capacity(cfg,st,slot,'production'),
                  salesPerMinute=round(sales,2),customerCapacityPerMinute=_upgrade_capacity(cfg,st,slot,'sales'),incomePerMinute=round(income,2),potentialIncomePerMinute=round(potential_income,2),status=status,reserve=b['reserve'],
                  processing=True,hasRecipes=False,
                  upgrades=upgrades,stored=storage,capacity=cap,storedValue=st['pend'][str(slot)],goods=rows,
                  recipe=None,recipes=[],price=1,priceTrend='flat',setBadges=[],
                  levelCost=upgrades['production']['cost'],levelPayback=None,autoCost=upgrades['sales']['cost'],autoPayback=None,
                  clearableQuantity=clear_qty,clearStockValue=clear_value)
        art_level=max(b['lv'],b['sales'],b['storage'])
        item['productionRhythm']=business_rhythms.profile(cfg,b)
        item['artLevel']=6 if art_level>=6 else min(3,art_level)
        item['focus']=b.get('focus','balanced')
        item['focusUnlocked']=b['lv']>=3
        item['focusOptions']=[dict(id=o[0],name=o[1],effect=o[2]) for o in focus_options(cfg,b)]
        item['regularBonus']=20 if t['id']=='roastery' and st.get('regularDeliveries',0)>=3 else 0
        item.update(business_operations.building_payload(cfg,st,slot,shop_receipts['operatingIncome'],potential_income,rates))
        if crafting_pilot.enabled(cfg):
            item['craftingPilot']=crafting_pilot.building_payload(cfg,st,b)
        if operating_margins.enabled(cfg):
            item['operatingStatement']=operating_margins.statement(
                cfg,st,slot,rates,potential_income,item.get('potentialOperatingCostPerMinute',0))
            item['operatingStatement']=crafting_pilot.include_statement(cfg,st,item['operatingStatement'],b['buildingId'])
        cost=item.get('operatingCostPerMinute',0)
        item['recentCashflow']=dict(sales=shop_receipts['operatingIncome'],costs=cost,
                                    net=shop_receipts['operatingIncome']-cost,
                                    observedSeconds=receipts['observedSeconds'])
        saved=order_reservations(st)
        item['savingForOrders']=b['reserve'] or any(saved.get(good['id'],0)>0 for good in t['goods'])
        buildings.append(item)
    frontier=[]
    for ti in expand_options(cfg,st):
        t=cfg['tiers'][ti];check=can_expand(cfg,st,ti);quote=expansion_quote(cfg,st,ti)
        frontier.append(dict(quote,tier=ti,id=t['id'],name=t['name'],family=t['family'],
                             baseRevenue=sum(x['unitPrice']/(x['cycleTicks']) for x in t['goods']),
                             productionPerMinute=round(sum(60/(x['cycleTicks']*g['tick']) for x in t['goods']),2),
                             timerH=t['timerH'],affordable=st['cash']>=quote['cost'],canExpand=check['ok'],why=check.get('why','')))
    orders=[]
    group_projects_enabled=town_projects.connected(cfg)
    saved_legacy=st.get('legacyProjectOffer') if group_projects_enabled else None
    saved_goal=st.get('goalOffer') if group_projects_enabled else None
    visible_orders=list(st.get('offers') or [])+([saved_goal] if saved_goal else [])+([saved_legacy] if saved_legacy else [])
    for order in visible_orders:
        order=dict(order,reward=focus_tree.order_reward(st,order['reward']))
        if order.get('rewardPercent'):
            order['rewardPercent']=focus_tree.order_reward(st,order['rewardPercent'])
        held=delivery_reservations(cfg,st,exclude=order['id'])
        requirements=[dict(n,name=goods[n['goodId']]['name'],owned=max(0,inventory.get(n['goodId'],0)-held.get(n['goodId'],0)),
                           buildingId=goods[n['goodId']]['buildingId']) for n in order['requirements']]
        missing=[n for n in requirements if n['owned']<n['quantity']]
        access=(town_projects.check(cfg,st,order['id']) if order.get('project') else
                project_orders.check(cfg,st,order) if order.get('goalOrder') else dict(ok=True))
        ready=not missing and access['ok']
        room=_commit_room(cfg,st,order) if access['ok'] else access
        target=sum(n['quantity'] for n in requirements);owned=sum(min(n['quantity'],n['owned']) for n in requirements)
        orders.append(dict(order,requirements=requirements,canFulfill=ready,locked=not access['ok'],
                           canCommit=room['ok'],commitWhy=room.get('why',''),
                           why=access.get('why','') if not access['ok'] else '' if ready else 'Need '+str(missing[0]['quantity']-missing[0]['owned'])+' '+missing[0]['name'],
                           target=target,delivered=owned,penalty=0,remainingSec=None,progressPercent=round(owned/target*100,1) if target else 100,building=order['name']))
        if order.get('project') and order.get('projectId'):
            project_spec=next((p for p in town_projects.PROJECTS if p['id']==order['projectId']),None)
            if project_spec: orders[-1]['buildingId']=project_spec['building']
        orders[-1]['supplyConflicts']=_project_supply_conflicts(cfg,st,order)
        orders[-1]['replaceRemainingSec']=0  # Also clears cooldowns from older saves.
        orders[-1].update(project_orders.estimate(cfg,st,order,_order_supply(cfg,st,order,session)))
    legacy_delivery=orders.pop() if saved_legacy else None
    goal_delivery=orders.pop() if saved_goal else None
    if goal_delivery: goal_delivery['offerIndex']=3
    build=dict(tier=st['build']['i'],name=cfg['tiers'][st['build']['i']]['name'],remainingSec=max(0,(st['build']['t']-st['tick'])*g['tick'])) if st.get('build') else None
    capacity=sum(b['capacity'] for b in buildings);stored=sum(b['stored'] for b in buildings)
    income=round(town_income(cfg,st),2);prod=round(sum(b['productionPerMinute'] for b in buildings),2)
    project_order=next((o for o in orders if o.get('project')),None)
    available={n['goodId']:n['owned'] for n in project_order['requirements']} if project_order else {}
    project_held=delivery_reservations(cfg,st)
    project_stock={gid:max(0,quantity-project_held.get(gid,0)) for gid,quantity in inventory.items()}
    project=town_projects.project_payload(cfg,st,available,project_stock)
    group=town_projects.group_payload(cfg,st)
    if legacy_delivery:
        group['legacyDelivery']=legacy_delivery
    step=(group_opening_step(group,frontier,build) if business_progression.connected_enabled(cfg)
          else opening_step(cfg,st,project,project_order,frontier,build))
    next_goal=step['title'] if step else 'Grow your conglomerate' if business_progression.connected_enabled(cfg) else 'Grow your businesses'
    newest=buildings[-1]
    operations=business_operations.payload(cfg,st,buildings,receipts['operatingIncome'],town_income(cfg,st))
    costs=operations.get('operatingCostPerMinute',0)
    cashflow=dict(sales=receipts['operatingIncome'],costs=costs,net=receipts['operatingIncome']-costs,
                  observedSeconds=receipts['observedSeconds'])
    return dict(modelVersion=4,productionMode='independent',sectorRhythms=business_rhythms.payload(cfg),tick=st['tick'],tickSeconds=g['tick'],behind=behind,cash=int(st['cash']),
                operations=operations,recentCashflow=cashflow,goalOrder=goal_delivery,
                operatingStatement=crafting_pilot.include_statement(cfg,st,operating_margins.town_statement(cfg,st,buildings)),
                progression=business_progression.payload(cfg,st),
                quests=quest_engine.payload(cfg,st),
                focusTree=focus_tree.payload(cfg,st),
                workforce=workforce.payload(cfg,st),
                crafting=crafting.payload(cfg,st),
                rulesRevision=4 if business_progression.connected_enabled(cfg) else 3,
                connectedProgression=business_progression.connected_enabled(cfg),groupProjects=group,
                townProjects=project,nextStep=step,earnings=receipts,potentialIncomePerMinute=round(town_income(cfg,st),2),regularDeliveries=st.get('regularDeliveries',0),regularTarget=3,
                customerContracts=customer_contract_payload(cfg,st),
                customerUnitsSold=st['report'].get('unitsSold',0),customerUnitsNeeded=100,materialUnitValue=0,
                netWorth=net_worth(st),book=st['book'],taxPaid=st['taxPaid'],taxRate=0,
                incomePerMinute=income,productionPerMinute=prod,revenuePerTick=jsround(income*g['tick']/60),
                revenuePerDay=jsround(town_income(cfg,st)*1440),materials=0,buildings=buildings,buildingsOwned=len(buildings),
                frontier=frontier,build=build,queue=[dict(tier=i,name=cfg['tiers'][i]['name']) for i in st['queue']],queueDepth=g['queueDepth'],
                warehouseCap=capacity,warehouseStored=stored,warehouseValue=sum(st['pend'].values()),
                warehouseFillPercent=round(stored/capacity*100,1) if capacity else 0,
                overflowing=any(b['stored']>=b['capacity'] for b in buildings),overflowDisc=1-cfg['production']['clearStockPercent']/100,clearStockPercent=cfg['production']['clearStockPercent'],
                contracts=dict(offers=orders,active=[],rolls=[dict(id=r['id'],label=r['label'],chance=r['chance']) for r in ORDER_ROLLS]),board=board,rumour=None,activeEvents=[],
                checklist=st['checklist'],checklistText=cfg['gate']['checklist'],goodSalesNeeded=cfg['gate']['goodSalesNeeded'],goodSalePrice=cfg['gate']['goodSalePrice'],
                gateTier=g['gateTier'],gateOpen=gate_open(cfg,st),keepPercent=st['keepPercent'],welcomeBackActive=False,
                currency=cfg['currency'],paused=bool(session['paused']),families=cfg['families'],tickerLines=[],
                contractSlots=cfg['fun']['contractSlots'],premiumSalePct=0,maxLevel=g['maxLevel'],gradLevel=1,offlineHours=cfg['runtime']['offlineHours'],
                nextGoal=next_goal,tier=newest['tier'],tierCount=len(cfg['tiers']),buildingName=newest['name'],buildingId=newest['id'],
                level=newest['lv'],auto=newest['auto'],autoLabel=newest['autoLabel'])


def set_processing(cfg,st,slot,enabled):
    if not _valid_slot(st,slot): return dict(ok=False,why='Unknown business')
    if type(enabled) is not bool: return dict(ok=False,why='Processing must be true or false')
    return dict(ok=False,why='Products are made independently. Use the business Pause control to stop production.')


def business_slot(cfg,st,building_id):
    return business_operations.find_slot(cfg,st,building_id)


def manage_business(cfg,st,body):
    if not isinstance(body,dict): return dict(ok=False,why='Choose a business action')
    result=business_operations.manage(cfg,st,body)
    if result['ok'] and body.get('action')=='salvage':
        # Uncommitted offers are replaceable; deal only still-producible goods.
        # Committed jobs and regular buyers were protected by the quote checks.
        for index,order in enumerate(st.get('offers') or []):
            if not order.get('committed') and not order.get('project'):
                st['offers'][index]=_make_order(cfg,st,index)
        _sync_pools(cfg,st)
    return result
