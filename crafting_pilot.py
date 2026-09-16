"""Opt-in, snapshotted automatic crafting trial. No browser owns game state.

Craft inventory value conserves transferred book value; costMicros independently
tracks ingredient/processing cost for actual sales. Assets depreciate only over
processed, assigned, active game ticks, never skipped offline wall time.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import business_assets
import business_operations
import crafting
import inventory_costs

SCALE = 1_000_000
CONFIG_PATH = Path(__file__).parent / 'config/crafting-pilot.v1.json'
ACTIONS = frozenset(('unlock', 'buy_asset', 'assign_asset', 'unassign_asset'))


def configure(cfg):
    cfg['craftingPilot'] = json.loads(CONFIG_PATH.read_text(encoding='utf8'))
    return cfg


def enabled(cfg):
    return cfg.get('version') == 4 and cfg.get('craftingPilot', {}).get('enabled') is True


def _items(cfg):
    return {p['id']: p for p in cfg.get('craftingPilot', {}).get('items', [])}


def _assets(cfg):
    return {a['id']: a for a in cfg.get('craftingPilot', {}).get('assets', [])}


def _live(cfg, st):
    return {cfg['tiers'][b['tier']]['id']: b for b in st.get('b', [])}


def _achievements(st):
    quests = {key for key, q in st.get('businessProgression', {}).get('quests', {}).items() if q.get('completed')}
    focus = {bid + ':' + node for bid, team in st.get('workforce', {}).get('teams', {}).items() for node in team.get('nodes', [])}
    return quests, focus


def ensure(cfg, st):
    if not enabled(cfg):
        return {}
    crafting.ensure(st)
    business_operations.ensure(cfg, st)
    quests, focus = _achievements(st)
    data = st.setdefault('craftingPilot', {})
    defaults = dict(version=1, unlocked={}, assets={}, work={}, salesWork={}, ordersByBusiness={},
                    ordersTotal=0, cursor=0, lastTick=st.get('tick', 0), costRemainders={}, buckets=[],
                    totals=dict(sales=0, costsMicros=0, made=0, sold=0, depreciation=0, amortization=0),
                    rewards=dict(quests=sorted(quests), focus=sorted(focus), lastVisit=st.get('tick', 0), sequence=0, recent=[]))
    for key, value in defaults.items():
        data.setdefault(key, copy.deepcopy(value))
    for pid in _items(cfg):
        row = st['crafting']['items'].get(pid)
        if row is not None:
            row.setdefault('costMicros', row.get('value', 0) * SCALE)
    return data


def stored_value(st):
    return sum(a.get('bookValue', 0) for a in st.get('craftingPilot', {}).get('assets', {}).values())


def _building(cfg, st, item):
    return _live(cfg, st).get(item['businessId'])


def _active_asset(cfg, st, aid, building):
    saved = st.get('craftingPilot', {}).get('assets', {}).get(aid)
    return bool(building and saved and saved.get('buildingId') == building.get('buildingId') and saved.get('remainingSeconds', 0) > 0)


def _bonuses(cfg, st, item, building):
    result = dict(speedPercent=0, costReductionPercent=0, pricePercent=0, storagePercent=0)
    for aid, asset in _assets(cfg).items():
        if item['id'] in asset['itemIds'] and _active_asset(cfg, st, aid, building):
            for key, value in asset['effects'].items():
                result[key] += value
    result['costReductionPercent'] = min(40, result['costReductionPercent'])
    return result


def _requirements(cfg, st, item):
    data = st['craftingPilot']; unlock = item['unlock']; b = _building(cfg, st, item)
    nodes = st.get('workforce', {}).get('teams', {}).get(item['businessId'], {}).get('nodes', [])
    quests = st.get('businessProgression', {}).get('quests', {})
    rows = [dict(kind='business', label='Open ' + next(t['name'] for t in cfg['tiers'] if t['id'] == item['businessId']), ready=b is not None)]
    rows.extend(dict(kind='quest', label='Complete ' + q.replace('_', ' ').replace('-', ' '), ready=bool(quests.get(q, {}).get('completed'))) for q in unlock['questIds'])
    rows.extend(dict(kind='focus', label='Focus: ' + node.replace('-', ' ').title(), ready=node in nodes) for node in unlock['focusNodes'])
    count = data['ordersByBusiness'].get(item['businessId'], 0)
    if unlock['manualOrders']:
        rows.append(dict(kind='orders', label='Manual orders: ' + str(count) + ' / ' + str(unlock['manualOrders']), ready=count >= unlock['manualOrders']))
    rows.append(dict(kind='cash', label='Unlock: ' + str(unlock['cash']) + ' YM', ready=st['cash'] >= unlock['cash']))
    return rows


def _reason(cfg, st, item, assets_only=False):
    b = _building(cfg, st, item)
    if not b:
        return 'Open this business first'
    if business_operations.paused(cfg, b):
        return 'Business paused'
    if not st['craftingPilot']['unlocked'].get(item['id']):
        return 'Unlock this product first'
    names = {a['id']: a['name'] for a in business_assets.catalog()}
    for aid in item['requiredAssetIds']:
        if not _active_asset(cfg, st, aid, b):
            return 'Assign an active ' + names[aid]
    return ''


def _ingredients(cfg, st, item):
    import production_economy as economy
    goods = economy.catalog(cfg); products = _items(cfg)
    names = {r[0]: r[1] for r in crafting.RECIPES}
    held = economy.protected_stock(cfg, st)
    result = []
    for need in item['ingredients']:
        gid, qty = need['id'], need['quantity']
        if gid in crafting.SUPPLIES:
            good = crafting.SUPPLIES[gid]; pool = st['crafting']['supplies'].get(gid, {})
            owned = pool.get('quantity', 0); reserved = 0; kind = 'supply'; source = 'Basic supplies'
            name = good['name']; price = good['unitPrice']
        elif gid in products:
            pool = st['crafting']['items'].get(gid, {}); owned = pool.get('quantity', 0)
            reserved = 0; kind = 'crafted'; source = 'Automatic crafting'; name = names[gid]; price = products[gid]['sellPrice']
        else:
            good = goods[gid]; owned = st['inventory'].get(gid, 0); reserved = min(owned, held.get(gid, 0))
            kind = 'product'; source = cfg['tiers'][good['tier']]['name']; name = good['name']; price = good['unitPrice']
        available = max(0, owned - reserved); missing = max(0, qty - available)
        result.append(dict(id=gid, name=name, kind=kind, quantity=qty, owned=owned, reserved=reserved,
                           available=available, missing=missing, source=source, unitPrice=price,
                           buyCost=missing * price if kind == 'supply' else 0,
                           canBuy=kind == 'supply' and missing > 0 and st['cash'] >= missing * price))
    return result


def _consume(cfg, st, ingredients):
    import production_economy as economy
    economy._sync_pools(cfg, st)
    before = sum(st['pend'].values()); value = 0; cost = 0
    needs = [dict(goodId=r['id'], quantity=r['quantity']) for r in ingredients if r['kind'] == 'product']
    for row in inventory_costs.consume(cfg, st, needs).values():
        cost += row['costMicros']
    for row in ingredients:
        gid, qty = row['id'], row['quantity']
        if row['kind'] == 'product':
            st['inventory'][gid] -= qty
            continue
        group = 'supplies' if row['kind'] == 'supply' else 'items'
        pool = st['crafting'][group][gid]
        basis = pool['value'] * qty // pool['quantity']
        used_cost = pool.get('costMicros', pool['value'] * SCALE) * qty // pool['quantity']
        pool['quantity'] -= qty; pool['value'] -= basis
        if 'costMicros' in pool:
            pool['costMicros'] -= used_cost
        value += basis; cost += used_cost
    economy._sync_pools(cfg, st)
    return value + before - sum(st['pend'].values()), cost


def _record(cfg, st, tick, identity, **values):
    data = st['craftingPilot']
    cutoff = tick - math.ceil(60 / cfg['global']['tick'])
    data['buckets'][:] = [b for b in data['buckets'] if b['tick'] > cutoff]
    bucket = next((b for b in data['buckets'] if b['tick'] == tick and b['buildingId'] == identity), None)
    if bucket is None:
        bucket = dict(tick=tick, buildingId=identity); data['buckets'].append(bucket)
    for key, value in values.items():
        bucket[key] = bucket.get(key, 0) + value
        data['totals'][key] = data['totals'].get(key, 0) + value


def _capacity(item, b, bonuses):
    return max(1, math.floor(item['storageCap'] * (100 + bonuses['storagePercent'] + 10 * (b.get('storage', 1) - 1)) / 100))


def _price(item, bonuses):
    return max(1, item['sellPrice'] * (100 + bonuses['pricePercent']) // 100)


def _charge_quote(st, item, bonuses):
    micro = item['batchCost'] * (100 - bonuses['costReductionPercent']) * SCALE // 100
    total = micro + st['craftingPilot']['costRemainders'].get(item['id'], 0)
    return total // SCALE, total % SCALE


def tick(cfg, st, tick):
    if not enabled(cfg):
        return
    data = ensure(cfg, st)
    if tick <= data['lastTick']:
        return
    # One processed game tick only: never age assets over skipped offline time.
    seconds = cfg['global']['tick']; data['lastTick'] = tick
    items = list(_items(cfg).values()); by_type = _live(cfg, st)
    for item in items:
        b = by_type.get(item['businessId']); pid = item['id']
        if _reason(cfg, st, item):
            data['work'][pid] = min(data['work'].get(pid, 0), item['batchSeconds'] * 100)
            continue
        bonus = _bonuses(cfg, st, item, b)
        speed = 100 + bonus['speedPercent'] + cfg['production']['speedPerLevel'] * (b.get('lv', 1) - 1)
        data['work'][pid] = min(item['batchSeconds'] * 100, data['work'].get(pid, 0) + seconds * speed)
    # One ready batch per product per sweep, with rotating priority for shared supplies.
    start = data['cursor'] % len(items)
    for item in items[start:] + items[:start]:
        pid = item['id']; b = by_type.get(item['businessId'])
        if _reason(cfg, st, item) or data['work'].get(pid, 0) < item['batchSeconds'] * 100:
            continue
        bonus = _bonuses(cfg, st, item, b)
        if st['crafting']['items'].get(pid, {}).get('quantity', 0) >= _capacity(item, b, bonus):
            continue
        ingredients = _ingredients(cfg, st, item)
        charge, remainder = _charge_quote(st, item, bonus)
        if any(r['missing'] for r in ingredients) or st['cash'] < charge:
            continue
        value, cost = _consume(cfg, st, ingredients)
        st['cash'] -= charge; data['costRemainders'][pid] = remainder
        pool = st['crafting']['items'].setdefault(pid, dict(quantity=0, value=0, costMicros=0))
        pool['quantity'] += 1; pool['value'] += value + charge; pool['costMicros'] += cost + charge * SCALE
        data['work'][pid] -= item['batchSeconds'] * 100
        _record(cfg, st, tick, b['buildingId'], made=1)
        # The next sweep starts after a successful producer. Locked catalog
        # entries must not bias a small number of lines sharing scarce inputs.
        data['cursor'] = (items.index(item) + 1) % len(items)
    # Keep one input batch for each eligible downstream product before retail.
    reserved = {}
    for item in items:
        if not _reason(cfg, st, item):
            for need in item['ingredients']:
                if need['id'] in _items(cfg):
                    reserved[need['id']] = reserved.get(need['id'], 0) + need['quantity']
    for item in items:
        pid = item['id']; b = by_type.get(item['businessId'])
        if not b or business_operations.paused(cfg, b) or b.get('reserve') or not data['unlocked'].get(pid):
            data['salesWork'][pid] = 0
            continue
        pool = st['crafting']['items'].get(pid, {})
        # Demand does not require continued equipment ownership; existing stock can sell.
        bonus = _bonuses(cfg, st, item, b)
        work = data['salesWork'].get(pid, 0) + seconds * (100 + 10 * (b.get('sales', 1) - 1))
        denominator = item['saleSeconds'] * 100
        qty = min(max(0, pool.get('quantity', 0) - reserved.get(pid, 0)), work // denominator)
        data['salesWork'][pid] = work % denominator
        if qty:
            basis = pool['value'] * qty // pool['quantity']; cost = pool['costMicros'] * qty // pool['quantity']
            pool['quantity'] -= qty; pool['value'] -= basis; pool['costMicros'] -= cost
            sale = qty * _price(item, bonus); st['cash'] += sale
            _record(cfg, st, tick, b['buildingId'], sales=sale, costsMicros=cost, sold=qty)
    live_ids = {b['buildingId']: b for b in st['b']}
    for aid, saved in data['assets'].items():
        b = live_ids.get(saved.get('buildingId'))
        if not b:
            saved['buildingId'] = None; saved['assignmentSlot'] = None
            continue
        if business_operations.paused(cfg, b) or saved['remainingSeconds'] <= 0:
            continue
        old = saved['bookValue']
        saved['remainingSeconds'] = max(0, saved['remainingSeconds'] - seconds)
        saved['bookValue'] = saved['purchasePrice'] * saved['remainingSeconds'] // saved['lifeSeconds']
        kind = 'amortization' if aid.endswith('_3') else 'depreciation'
        _record(cfg, st, tick, b['buildingId'], **{kind: old - saved['bookValue']})


def act(cfg, st, body):
    if not enabled(cfg):
        return dict(ok=False, why='Automatic crafting is not enabled for this class')
    if not isinstance(body, dict):
        return dict(ok=False, why='Invalid crafting request')
    request = body.get('requestId'); revision = body.get('revision'); action = body.get('action')
    if not isinstance(request, str) or not crafting.REQUEST_ID.fullmatch(request):
        return dict(ok=False, why='A valid crafting requestId is required')
    if type(revision) is not int or revision < 0:
        return dict(ok=False, why='Crafting revision must be a nonnegative integer')
    if not isinstance(action, str) or action not in ACTIONS:
        return dict(ok=False, why='Unknown crafting action')
    fields = ('itemId',) if action == 'unlock' else ('assetId', 'buildingId', 'assetSlot') if action == 'assign_asset' else ('assetId',)
    if any(key in body and key != 'assetSlot' and not isinstance(body[key], str) for key in fields):
        return dict(ok=False, why='Invalid crafting identifier')
    if action == 'assign_asset' and ('assetSlot' in body and (type(body['assetSlot']) is not int or not 0 <= body['assetSlot'] <= 2)):
        return dict(ok=False, why='Choose a valid asset slot')
    intent = [action] + [body.get(key) for key in fields]
    saved = st.get('crafting', {}); previous = saved.get('lastRequest')
    if previous and previous['requestId'] == request:
        if previous['intent'] == intent and previous['revision'] == revision:
            return dict(copy.deepcopy(previous['receipt']), duplicate=True)
        return dict(ok=False, why='This crafting request has already been used')
    if revision != saved.get('revision', 0):
        return dict(ok=False, why='Crafting changed; refresh and try again')
    working = copy.deepcopy(st); ensure(cfg, working)
    result = _act(cfg, working, body)
    if not result['ok']:
        return result
    working['crafting']['revision'] += 1
    result['revision'] = working['crafting']['revision']
    working['crafting']['lastRequest'] = dict(requestId=request, revision=revision, intent=intent, receipt=copy.deepcopy(result))
    st.clear(); st.update(working)
    return result


def _act(cfg, st, body):
    data = st['craftingPilot']; action = body['action']
    fail = lambda message: dict(ok=False, why=message)
    if action == 'unlock':
        item = _items(cfg).get(body.get('itemId'))
        if not item:
            return fail('Unknown automatic product')
        if data['unlocked'].get(item['id']):
            return fail('Already unlocked')
        missing = next((r for r in _requirements(cfg, st, item) if not r['ready']), None)
        if missing:
            return fail(missing['label'])
        st['cash'] -= item['unlock']['cash']; data['unlocked'][item['id']] = True
        return dict(ok=True, kind='craft_unlock', itemId=item['id'], cost=item['unlock']['cash'])
    aid = body.get('assetId'); spec = _assets(cfg).get(aid)
    if not spec:
        return fail('This asset is a catalog preview')
    saved = data['assets'].get(aid)
    if action == 'buy_asset':
        if saved and saved['remainingSeconds'] > 0:
            return fail('This asset is already owned')
        if st['cash'] < spec['price']:
            return fail('Need ' + str(spec['price']) + ' YM')
        st['cash'] -= spec['price']
        data['assets'][aid] = dict(purchasePrice=spec['price'], bookValue=spec['price'], lifeSeconds=spec['lifeSeconds'],
                                  remainingSeconds=spec['lifeSeconds'], buildingId=saved.get('buildingId') if saved else None,
                                  assignmentSlot=saved.get('assignmentSlot') if saved else None)
        return dict(ok=True, kind='craft_asset_buy', assetId=aid, cost=spec['price'])
    if not saved:
        return fail('Buy this asset first')
    if action == 'unassign_asset':
        saved['buildingId'] = None; saved['assignmentSlot'] = None
        return dict(ok=True, kind='craft_asset_remove', assetId=aid)
    b = next((b for b in st['b'] if b['buildingId'] == body.get('buildingId')), None)
    info = next(a for a in business_assets.catalog() if a['id'] == aid)
    if not b or cfg['tiers'][b['tier']]['id'] != info['businessId']:
        return fail('Choose a compatible open business')
    if business_operations.paused(cfg, b):
        return fail('Resume this business before assigning assets')
    if saved['remainingSeconds'] <= 0:
        return fail('Replace this worn asset first')
    allowed = [2] if info['assetType'] == 'intangible' else [0, 1]
    slot = body.get('assetSlot', next((s for s in allowed if not any(a.get('buildingId') == b['buildingId'] and a.get('assignmentSlot') == s and key != aid for key, a in data['assets'].items())), None))
    if slot not in allowed:
        return fail('Choose an empty compatible asset slot')
    if any(key != aid and a.get('buildingId') == b['buildingId'] and a.get('assignmentSlot') == slot for key, a in data['assets'].items()):
        return fail('Remove the assigned asset from that slot first')
    saved['buildingId'] = b['buildingId']; saved['assignmentSlot'] = slot
    return dict(ok=True, kind='craft_asset_assign', assetId=aid, buildingId=b['buildingId'], assetSlot=slot)


def _award(cfg, st, reason, budget):
    data = st['craftingPilot']['rewards']; sequence = data['sequence'] + 1
    remaining = budget; rewards = []
    for index in range(3):
        choices = sorted(sid for sid, s in crafting.SUPPLIES.items() if s['unitPrice'] <= remaining and sid not in {r['id'] for r in rewards})
        if not choices:
            break
        digest = hashlib.sha256((str(st.get('rngState', 1)) + ':' + str(sequence) + ':' + reason + ':' + str(index)).encode()).digest()
        sid = choices[int.from_bytes(digest[:8], 'big') % len(choices)]; spec = crafting.SUPPLIES[sid]
        quantity = min(5, max(1, remaining // spec['unitPrice'] // (3 - index)))
        value = quantity * spec['unitPrice']; remaining -= value
        crafting._add(st['crafting']['supplies'], sid, quantity, value)
        rewards.append(dict(id=sid, name=spec['name'], quantity=quantity, value=value))
    if rewards:
        data['sequence'] = sequence
        data['recent'].append(dict(id=sequence, reason=reason, tick=st['tick'], items=rewards, value=budget - remaining))
        del data['recent'][:-12]
        st['crafting']['revision'] += 1


def observe_rewards(cfg, st):
    if not enabled(cfg):
        return
    data = ensure(cfg, st); rewards = data['rewards']; spec = cfg['craftingPilot']['rewards']
    quests, focus = _achievements(st)
    for q in sorted(quests - set(rewards['quests'])):
        _award(cfg, st, 'Quest completed', spec['questBudget'])
    for node in sorted(focus - set(rewards['focus'])):
        _award(cfg, st, 'Focus progress', spec['focusBudget'])
    rewards['quests'] = sorted(set(rewards['quests']) | quests)
    rewards['focus'] = sorted(set(rewards['focus']) | focus)


def record_order(cfg, st, requirements):
    if not enabled(cfg):
        return
    import production_economy as economy
    data = ensure(cfg, st); goods = economy.catalog(cfg)
    for bid in {goods[r['goodId']]['buildingId'] for r in requirements}:
        data['ordersByBusiness'][bid] = data['ordersByBusiness'].get(bid, 0) + 1
    data['ordersTotal'] += 1; spec = cfg['craftingPilot']['rewards']
    if data['ordersTotal'] % spec['ordersEvery'] == 0:
        _award(cfg, st, 'Manual-order milestone', spec['orderBudget'])


def visit(cfg, st):
    if not enabled(cfg):
        return
    data = ensure(cfg, st)['rewards']; spec = cfg['craftingPilot']['rewards']
    if (st['tick'] - data['lastVisit']) * cfg['global']['tick'] >= spec['welcomeAbsenceSeconds']:
        _award(cfg, st, 'Welcome back', spec['welcomeBudget'])
    data['lastVisit'] = st['tick']
    observe_rewards(cfg, st)


def _statement(cfg, st, identity=None):
    now = max(st.get('tick', 0), st.get('craftingPilot', {}).get('lastTick', 0))
    rows = [r for r in st.get('craftingPilot', {}).get('buckets', []) if 0 <= (now - r['tick']) * cfg['global']['tick'] < 60 and (identity is None or r['buildingId'] == identity)]
    sales = sum(r.get('sales', 0) for r in rows); costs = sum(r.get('costsMicros', 0) for r in rows) / SCALE
    depreciation = sum(r.get('depreciation', 0) for r in rows); amortization = sum(r.get('amortization', 0) for r in rows)
    return dict(enabled=enabled(cfg), scope='Automatic crafted products', sales=sales, costs=round(costs, 6),
                profit=round(sales - costs, 6), depreciation=depreciation, amortization=amortization,
                netProfit=round(sales - costs - depreciation - amortization, 6),
                made=sum(r.get('made', 0) for r in rows), sold=sum(r.get('sold', 0) for r in rows))


def summary(cfg, st):
    return _statement(cfg, st)


def include_statement(cfg, st, statement, identity=None):
    """Add actual craft sales and asset wear once to the existing shop report."""
    if not enabled(cfg):
        return statement
    craft = _statement(cfg, st, identity)
    result = dict(statement)
    result['crafting'] = craft
    result['sales'] = round(statement['sales'] + craft['sales'], 2)
    result['costs'] = round(statement['costs'] + craft['costs'] + craft['depreciation'] + craft['amortization'], 2)
    result['profit'] = round(result['sales'] - result['costs'], 2)
    result['margin'] = result['profit'] / result['sales'] * 100 if result['sales'] > 0 else None
    result['takeHome'] = statement.get('takeHome', 0) + craft['sales']
    result['productionCosts'] = statement.get('productionCosts', 0) + craft['costs']
    result['scope'] = 'shops_regular_buyers_and_automatic_crafts'
    return result


def building_payload(cfg, st, b):
    if not enabled(cfg):
        return dict(enabled=False)
    result = _statement(cfg, st, b['buildingId'])
    result['assets'] = [dict(assetId=aid, **a) for aid, a in st.get('craftingPilot', {}).get('assets', {}).items() if a.get('buildingId') == b['buildingId']]
    return result


def enrich(cfg, st, payload):
    if not enabled(cfg):
        return payload
    data = ensure(cfg, st); items = _items(cfg); asset_specs = _assets(cfg); live = _live(cfg, st)
    for row in payload['items']:
        item = items.get(row['id'])
        if not item:
            continue
        b = live.get(item['businessId']); bonus = _bonuses(cfg, st, item, b)
        requirements = _requirements(cfg, st, item); ingredients = _ingredients(cfg, st, item)
        reason = _reason(cfg, st, item); unlocked = bool(data['unlocked'].get(item['id']))
        if not reason:
            missing = next((i for i in ingredients if i['missing']), None)
            if missing:
                reason = 'Need ' + missing['name']
            elif st['cash'] < _charge_quote(st, item, bonus)[0]:
                reason = 'Need cash for processing'
            elif row['owned'] >= _capacity(item, b, bonus):
                reason = 'Product storage is full'
        price = _price(item, bonus)
        replacement = sum(r['quantity'] * r['unitPrice'] for r in ingredients) + item['batchCost'] * (100 - bonus['costReductionPercent']) / 100
        row.update(pilot=True, unlocked=unlocked, businessId=item['businessId'], buildingId=b.get('buildingId') if b else None,
                   businessName=next(t['name'] for t in cfg['tiers'] if t['id'] == item['businessId']),
                   unlockRequirements=requirements, unlockCost=item['unlock']['cash'], canUnlock=not unlocked and all(r['ready'] for r in requirements),
                   requiredAssets=[dict(id=aid, name=next(a['name'] for a in business_assets.catalog() if a['id'] == aid), ready=_active_asset(cfg, st, aid, b)) for aid in item['requiredAssetIds']],
                   ingredients=ingredients, batchSeconds=item['batchSeconds'], batchCost=item['batchCost'] * (100 - bonus['costReductionPercent']) / 100,
                   sellPrice=price, expectedMargin=round((price - replacement) / price * 100, 1), storageCap=_capacity(item, b, bonus) if b else item['storageCap'],
                   effectiveBatchSeconds=round(item['batchSeconds'] * 100 / (100 + bonus['speedPercent'] + (cfg['production']['speedPerLevel'] * (b.get('lv', 1) - 1) if b else 0)), 1),
                   progress=min(1, data['work'].get(item['id'], 0) / (item['batchSeconds'] * 100)),
                   pilotStatus='Producing automatically' if not reason else reason, canCraft=False, why=reason)
    for row in payload['businessAssets']:
        spec = asset_specs.get(row['id'])
        if not spec:
            continue
        saved = data['assets'].get(row['id'], {}); usable = saved.get('remainingSeconds', 0) > 0
        row.update(pilot=True, owned=bool(saved), price=spec['price'], canBuy=not usable and st['cash'] >= spec['price'],
                   assignedBuildingId=saved.get('buildingId'), assignmentSlot=saved.get('assignmentSlot'),
                   bookValue=saved.get('bookValue', 0), remainingSeconds=saved.get('remainingSeconds', 0), lifeSeconds=spec['lifeSeconds'],
                   effects=spec['effects'], itemIds=spec['itemIds'], usageNote=spec.get('usageNote', ''), compatibleBuildings=[dict(buildingId=b['buildingId'], name=next(t['name'] for t in cfg['tiers'] if t['id'] == row['businessId'])) for bid, b in live.items() if bid == row['businessId']])
    payload['pilot'] = dict(enabled=True, itemIds=list(items), assetIds=list(asset_specs), summary=summary(cfg, st), rewards=copy.deepcopy(data['rewards']['recent']))
    return payload
