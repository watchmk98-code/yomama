"""Production expenses and reversible business management.

All cash charges are whole YM and are recorded after a completed batch or an
explicit hire. No running cost is charged for waiting, paused or skipped time.
An instance identity survives slot changes and changes when a shop is rebuilt.
"""
from __future__ import annotations

import math
import workforce


WINDOW_SECONDS = 60
COST_SCALE = 1000000
STATE_KEY = 'businessOperations'
ROLES = (
    dict(id='assistant', name='Production assistant', effect='Basic products +50% base speed'),
    dict(id='specialist', name='Production specialist', effect='Advanced products +75% base speed'),
    dict(id='technician', name='Maintenance technician', effect='Production running costs −50%'),
)


def enabled(cfg):
    return cfg.get('businessDesign', {}).get('enabled') is True


def ensure(cfg, st, new=False):
    if not enabled(cfg):
        return {}
    data = st.setdefault(STATE_KEY, dict(version=1, serial=0, startedTick=st.get('tick', 0),
                                        buckets=[], cooldowns={}, pendingInvestment={},
                                        totalOperatingCosts=0, totalStaffCosts=0, staffHired=0))
    for b in st.get('b', []):
        if not b.get('buildingId'):
            data['serial'] += 1
            b['buildingId'] = 'business-{}'.format(data['serial'])
            b.update(paused=False, staff=None, costRemainder=0, cashInvested=0,
                     costRemainderScale=COST_SCALE,
                     bookValue=cfg['tiers'][b['tier']]['baseCost'] if new else 0,
                     investmentKnown=bool(new))
        b.setdefault('paused', False)
        b.setdefault('staff', None)
        staff = b['staff']
        if isinstance(staff, dict) and staff.get('id') == 'specialist':
            if staff.get('name') == 'Craft specialist':
                staff['name'] = 'Production specialist'
            if staff.get('effect') == 'Recipes +75% base speed':
                staff['effect'] = 'Advanced products +75% base speed'
        b.setdefault('costRemainder', 0)
        if b.get('costRemainderScale', 100) != COST_SCALE:
            # Earlier operating saves stored hundredths of a YM. Keep that
            # exact accrued fraction when upgrades need finer precision.
            b['costRemainder'] = b['costRemainder'] * COST_SCALE // b.get('costRemainderScale', 100)
        b['costRemainderScale'] = COST_SCALE
    return data


def find_slot(cfg, st, building_id):
    if not enabled(cfg) or not isinstance(building_id, str):
        return None
    ensure(cfg, st)
    return next((slot for slot, b in enumerate(st['b']) if b['buildingId'] == building_id), None)


def paused(cfg, b):
    return enabled(cfg) and bool(b.get('paused'))


def active_staff(cfg, b):
    if workforce.enabled(cfg):
        return None
    staff = b.get('staff') if enabled(cfg) else None
    return staff if staff and staff.get('remainingTicks', 0) > 0 else None


def speed_bonus(cfg, b, good):
    staff = active_staff(cfg, b)
    if staff and not paused(cfg, b):
        # Preserve existing shift coverage. Dormant recipe metadata identifies
        # advanced products, but automatic production no longer uses inputs.
        if staff['id'] == 'assistant' and not good.get('inputs'):
            return 50
        if staff['id'] == 'specialist' and good.get('inputs'):
            return 75
    return 0


def base_batch_cost(cfg, good):
    if not enabled(cfg):
        return 0
    # The free starter crop is a permanent way to recover from an empty wallet.
    if good['id'] == 'farm_tomatoes':
        return 0
    return max(0, int(good.get('operatingCost', max(1, math.floor(good['unitPrice'] * good['quantity'] * .18 + .5)))))


def _batch_cost_units(cfg, b, good, st=None):
    rules = cfg.get('businessDesign', {})
    customer_cost = max(0, int(rules.get('customerCostPerLevel', 10)))
    storage_cost = max(0, int(rules.get('storageCostPerLevel', 5)))
    operating_percent = (100 + customer_cost * max(0, b.get('sales', 1) - 1)
                         + storage_cost * max(0, b.get('storage', 1) - 1))
    staff = active_staff(cfg, b)
    staff_percent = 50 if staff and staff['id'] == 'technician' else 100
    discount = workforce.bonuses(cfg,st,b)['efficiency'] if st is not None else 0
    discount_basis_points = max(0,min(2500,round(discount*100)))
    return base_batch_cost(cfg, good) * operating_percent * staff_percent * (10000-discount_basis_points) // 100


def effective_batch_cost(cfg, b, good, st=None):
    """Installed per-batch rate, without rounding or historical cash carry."""
    return _batch_cost_units(cfg, b, good, st) / COST_SCALE


def batch_quote(cfg, b, good, st=None, batches=1):
    remainder = b.get('costRemainder', 0) * COST_SCALE // b.get('costRemainderScale', 100)
    amount = _batch_cost_units(cfg, b, good, st) * batches + remainder
    return amount // COST_SCALE, amount % COST_SCALE


def forecast_cost(cfg, st, slot, rates):
    b = st['b'][slot]
    return sum(rates[g['id']]['production'] / g['quantity'] * effective_batch_cost(cfg, b, g, st)
               for g in cfg['tiers'][st['tierOf'][slot]]['goods'])


def prune(cfg, st, tick=None, clear=False):
    if not enabled(cfg):
        return {}
    data = ensure(cfg, st)
    now = st.get('tick', 0) if tick is None else tick
    if clear:
        data.update(startedTick=now, buckets=[])
    else:
        data['buckets'][:] = [b for b in data['buckets']
                              if 0 <= (now - b['tick']) * cfg['global']['tick'] < WINDOW_SECONDS]
    return data


def charge_batch(cfg, st, b, good, tick, batches=1):
    """Caller has already checked product access and capacity; charge atomically."""
    if not enabled(cfg):
        return True
    cost, remainder = batch_quote(cfg, b, good, st, batches=batches)
    if st['cash'] < cost:
        return False
    st['cash'] -= cost
    b['costRemainder'] = remainder
    b['costRemainderScale'] = COST_SCALE
    data = prune(cfg, st, tick)
    data['totalOperatingCosts'] += cost
    if cost:
        bucket = next((item for item in data['buckets'] if item['tick'] == tick), None)
        if bucket is None:
            bucket = dict(tick=tick, byBuilding={})
            data['buckets'].append(bucket)
        costs = bucket['byBuilding']
        costs[b['buildingId']] = costs.get(b['buildingId'], 0) + cost
    return True


def advance_shifts(cfg, st):
    if not enabled(cfg):
        return
    for b in st['b']:
        staff = active_staff(cfg, b)
        if staff and not paused(cfg, b):
            staff['remainingTicks'] -= 1
            if staff['remainingTicks'] <= 0:
                b['staff'] = None


def record_investment(cfg, st, slot, cash):
    if not enabled(cfg):
        return
    ensure(cfg, st)
    b = st['b'][slot]
    b['cashInvested'] = b.get('cashInvested', 0) + cash
    b['bookValue'] = b.get('bookValue', 0) + cash


def reserve_construction(cfg, st, tier, cash, funded=0):
    if enabled(cfg):
        ensure(cfg, st)['pendingInvestment'][str(tier)] = dict(cash=cash, book=cash + funded)


def complete_construction(cfg, st, slot):
    if not enabled(cfg):
        return
    data = ensure(cfg, st)
    b = st['b'][slot]
    investment = data['pendingInvestment'].pop(str(b['tier']), None)
    if investment is not None:
        b.update(cashInvested=investment['cash'], bookValue=investment['book'], investmentKnown=True)


def cooldown_seconds(cfg, st, tier):
    if not enabled(cfg):
        return 0
    until = ensure(cfg, st)['cooldowns'].get(cfg['tiers'][tier]['id'], 0)
    return max(0, (until - st['tick']) * cfg['global']['tick'])


def salvage_quote(cfg, st, slot):
    ensure(cfg, st)
    b = st['b'][slot]
    tier = cfg['tiers'][st['tierOf'][slot]]
    goods = {g['id'] for g in tier['goods']}
    quantity = sum(st['inventory'].get(gid, 0) for gid in goods)
    why = ''
    if len(st['b']) <= 1 or tier['id'] == 'farm':
        why = 'Keep your starter farm: its tomatoes can always earn recovery cash.'
    elif not b.get('investmentKnown'):
        why = 'This earlier business has no recorded construction investment.'
    elif st.get('build') or st.get('queue'):
        why = 'Wait for construction to finish before closing a business.'
    elif st.get('townProjects', {}).get('completed', 0) < 3 and tier['id'] in ('fish_stall', 'roastery'):
        why = 'Finish your three opening town projects first.'
    elif active_staff(cfg, b):
        why = 'Let this staff shift finish before closing the business.'
    elif any(any(n['goodId'] in goods for n in c['requirements'])
             for c in st.get('customerContracts', {}).get('active', [])):
        why = 'Release regular buyers that use these products first.'
    elif any(o.get('committed') and any(n['goodId'] in goods for n in o['requirements'])
             for o in st.get('offers') or []):
        why = 'Release or deliver saved orders that use these products first.'
    elif quantity:
        why = 'Pause this business and clear its {} stored goods first.'.format(quantity)
    # Regular slots must remain usable after the number of buildings falls.
    remaining_slots = 4 if len(st['b']) - 1 >= 6 else 3 if len(st['b']) - 1 >= 3 else 2
    if not why and any(c['slot'] >= remaining_slots for c in st.get('customerContracts', {}).get('active', [])):
        why = 'Release your highest regular-buyer slot before reducing your town size.'
    invested = b.get('cashInvested', 0)
    return dict(value=invested * 45 // 100, percent=45, cashInvested=invested,
                bookValue=b.get('bookValue', 0), canSalvage=not why, why=why,
                cooldownSeconds=300, affectedBusinesses=[])


def staff_options(cfg, st, slot):
    if workforce.enabled(cfg):
        return []
    import business_progression

    b = st['b'][slot]
    goods = cfg['tiers'][st['tierOf'][slot]]['goods']
    advanced = [good for good in goods if good.get('inputs')]
    unlocked_advanced = [good for good in advanced if business_progression.product_unlocked(cfg, st, good['id'])]
    base_cost = sum(base_batch_cost(cfg, g) * 60 / (g['cycleTicks'] * cfg['global']['tick']) for g in goods)
    options = []
    for role in ROLES:
        cost = max(4, int(math.ceil(base_cost * .9 * (1.25 if role['id'] == 'specialist' else 1))))
        why = 'A staff shift is already active' if active_staff(cfg, b) else (
            'Resume the business before hiring' if paused(cfg, b) else
            'This business has no advanced products' if role['id'] == 'specialist' and not advanced else
            'Complete this business’s signature quest to unlock an advanced product first' if role['id'] == 'specialist' and not unlocked_advanced else
            'Need {} YM more'.format(cost - st['cash']) if cost > st['cash'] else '')
        options.append(dict(role, cost=cost, durationSeconds=180, canHire=not why, why=why))
    return options


def _remap_slots(mapping, removed, retain_removed=False):
    result = {}
    for key, value in mapping.items():
        if isinstance(key, str) and key.isdigit():
            old = int(key)
            if old == removed:
                if retain_removed:
                    result['town'] = result.get('town', 0) + value
                continue
            key = str(old - 1 if old > removed else old)
        result[key] = result.get(key, 0) + value if isinstance(value, (int, float)) else value
    return result


def manage(cfg, st, body):
    if not enabled(cfg):
        return dict(ok=False, why='These operations need the new business rules.')
    slot = find_slot(cfg, st, body.get('buildingId'))
    if slot is None:
        return dict(ok=False, why='This business changed. Refresh and try again.')
    action = body.get('action')
    b = st['b'][slot]
    if action in ('pause', 'resume'):
        b['paused'] = action == 'pause'
        return dict(ok=True, kind='business', action=action, buildingId=b['buildingId'])
    if action == 'hire':
        if workforce.enabled(cfg):
            return dict(ok=False, why='Recruit permanent trainers from Operations → Team')
        option = next((o for o in staff_options(cfg, st, slot) if o['id'] == body.get('staffId')), None)
        if option is None:
            return dict(ok=False, why='Choose a staff role')
        if not option['canHire']:
            return dict(ok=False, why=option['why'])
        st['cash'] -= option['cost']
        b['staff'] = dict(id=option['id'], name=option['name'], effect=option['effect'],
                          remainingTicks=max(1, math.ceil(option['durationSeconds'] / cfg['global']['tick'])))
        data = ensure(cfg, st)
        data['totalStaffCosts'] += option['cost']
        data['staffHired'] += 1
        return dict(ok=True, kind='business', action=action, buildingId=b['buildingId'], cost=option['cost'])
    if action != 'salvage':
        return dict(ok=False, why='Unknown business action')
    quote = salvage_quote(cfg, st, slot)
    if not quote['canSalvage']:
        return dict(ok=False, why=quote['why'])
    tier = cfg['tiers'][st['tierOf'][slot]]
    building_id = b['buildingId']
    st['cash'] += quote['value']
    st['book'] = max(0, st['book'] - quote['bookValue'])
    for good in tier['goods']:
        for key in ('inventory', 'productionWork', 'productionPhase', 'salesWork', 'productionBlocked'):
            st.get(key, {}).pop(good['id'], None)
    st['b'].pop(slot)
    st['tierOf'].pop(slot)
    for key in ('pend', 'unlock', 'recentRetail'):
        if key in st:
            st[key] = _remap_slots(st[key], slot)
    for key in ('recentEarnings', 'recentBusinessActivity'):
        for bucket in st.get(key, {}).get('buckets', []):
            for source, mapping in bucket.get('sources', {}).items():
                bucket['sources'][source] = _remap_slots(mapping, slot, retain_removed=key == 'recentEarnings')
    ensure(cfg, st)['cooldowns'][tier['id']] = st['tick'] + math.ceil(300 / cfg['global']['tick'])
    return dict(ok=True, kind='business', action=action, buildingId=building_id,
                value=quote['value'], cooldownSeconds=300)


def building_payload(cfg, st, slot, income, potential_income, rates):
    if not enabled(cfg):
        return {}
    data = prune(cfg, st)
    b = st['b'][slot]
    expense = sum(bucket['byBuilding'].get(b['buildingId'], 0) for bucket in data['buckets'])
    staff = active_staff(cfg, b)
    potential = forecast_cost(cfg, st, slot, rates)
    return dict(buildingId=b['buildingId'], operatingCostPerMinute=expense,
                profitPerMinute=round(income - expense, 2),
                potentialOperatingCostPerMinute=round(potential, 2),
                potentialProfitPerMinute=round(potential_income - potential, 2), paused=paused(cfg, b),
                staff=dict(id=staff['id'], name=staff['name'], effect=staff['effect'],
                           remainingSeconds=staff['remainingTicks'] * cfg['global']['tick']) if staff else None,
                staffOptions=staff_options(cfg, st, slot), salvage=salvage_quote(cfg, st, slot))


def payload(cfg, st, buildings, income, potential_income):
    if not enabled(cfg):
        return dict(enabled=False)
    data = prune(cfg, st)
    actual = sum(sum(bucket['byBuilding'].values()) for bucket in data['buckets'])
    potential = sum(b['potentialOperatingCostPerMinute'] for b in buildings)
    return dict(enabled=True, windowSeconds=WINDOW_SECONDS,
                observedSeconds=min(WINDOW_SECONDS, max(0, st['tick'] - data['startedTick']) * cfg['global']['tick']),
                operatingCostPerMinute=actual, profitPerMinute=round(income - actual, 2),
                closedOperatingCostPerMinute=actual - sum(b['operatingCostPerMinute'] for b in buildings),
                potentialOperatingCostPerMinute=round(potential, 2),
                potentialProfitPerMinute=round(potential_income - potential, 2),
                totalOperatingCosts=data['totalOperatingCosts'], totalStaffCosts=data['totalStaffCosts'],
                staffHired=data['staffHired'])
