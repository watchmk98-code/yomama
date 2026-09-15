"""Business quests, research and retained equipment for the opted-in economy.

Connected quests observe real production and sales. Older class snapshots and
already-started exercises retain their finite practice workshops. Permanent
rewards live outside buildings so closure cannot replay them.
"""
from __future__ import annotations

import copy

import rules_tables


# Each business teaches a concrete constraint before a two-stage recipe exercise.
# The recipe exercise uses practice materials from partners, never locked stock.
QUEST_THEMES = {
    'farm': ('Market Morning', 'Divide a harvest between everyday shoppers and produce boxes.', 'Harvest crates', 'Market slots', 'Pick tomatoes', 'Pack egg boxes', 'Bee Friendly', 'Prepare bee habitat, then collect a signature honey batch.', 'Meadow supplies', 'Bee habitat', 'Plant habitat', 'Collect honey'),
    'fish_stall': ('Before the Ice Melts', 'Fit fresh orders into the ice window; oysters need twice the handling time.', 'Catch crates', 'Ice window', 'Sort fresh catch', 'Prepare oysters', 'Smokehouse Special', 'Prepare a cure before smoking the catch. Keep a starter for the next batch.', 'Fresh practice catch', 'Cured fish', 'Cure the catch', 'Smoke fish'),
    'roastery': ('Morning Rush', 'Split one counter between quick bean orders and slower espresso service.', 'Coffee supplies', 'Counter time', 'Bag roasted beans', 'Pull espresso', 'Breakfast Club', 'Prepare pastry dough, then bake. Completing the original Breakfast Club also qualifies.', 'Practice ingredients', 'Pastry dough', 'Mix dough', 'Bake pastries'),
    'garage': ('Back on the Road', 'Schedule quick repairs around time-consuming replacement-part jobs.', 'Service supplies', 'Workshop time', 'Complete repairs', 'Prepare spare parts', 'Custom Ride', 'Fit a modification kit before assembling a customer’s custom ride.', 'Practice parts', 'Fitted kit', 'Fit the kit', 'Build custom mods'),
    'workshop': ('Measure Twice', 'Choose a cutting plan that fills bracket and frame orders within bench time.', 'Steel blanks', 'Bench time', 'Cut brackets', 'Weld frames', 'Frame the Future', 'Make a machining jig, then turn accurate bolts for another business.', 'Practice steel', 'Machining jig', 'Make the jig', 'Machine bolts'),
    'solar_coop': ('Power the Block', 'Share limited daylight between immediate power and battery charging.', 'Sunlight units', 'Inverter time', 'Supply daytime power', 'Charge batteries', 'After Sunset', 'Store clean power, then verify the displaced emissions for carbon credits.', 'Practice power', 'Stored clean power', 'Store power', 'Verify credits'),
    'cannery': ('Save the Harvest', 'Allocate the filling line between preservation batches and slower sauce runs.', 'Harvest boxes', 'Filling line time', 'Can the harvest', 'Bottle sauce', 'Secret Sauce', 'Prepare a fruit base, then preserve a signature recipe without using all the starter.', 'Practice fruit', 'Prepared fruit base', 'Prepare the base', 'Make preserves'),
    'machine_works': ('Precision Job', 'Balance quick parts against careful tooling on one machine schedule.', 'Metal blanks', 'Machine time', 'Cut CNC parts', 'Make tooling', 'Prototype Pitch', 'Machine test components, then assemble a prototype for a new customer.', 'Practice metal', 'Test components', 'Machine components', 'Assemble prototype'),
    'turbine_field': ('Catch the Wind', 'Use the forecast window to produce power and service capacity commitments.', 'Wind units', 'Forecast window', 'Generate wind power', 'Secure capacity', 'Steady Supply', 'Balance a practice reserve, then certify a reliable clean supply.', 'Practice generation', 'Balanced reserve', 'Balance reserve', 'Certify supply'),
    'generator': ('Peak Hour', 'Share turbine time between efficient baseload and slower peak-power commitments.', 'Fuel units', 'Turbine time', 'Generate baseload', 'Meet peak demand', 'Nothing Wasted', 'Capture waste heat, then prepare usable steam for an industrial neighbor.', 'Practice heat', 'Recovered heat', 'Recover heat', 'Supply steam'),
    'relay_station': ('Dead Zone', 'Allocate radio time to restore broadband and message traffic together.', 'Signal units', 'Radio time', 'Restore bandwidth', 'Route messages', 'Festival Traffic', 'Prepare a supported network zone, then bring a temporary tower site online.', 'Practice network supplies', 'Supported network zone', 'Prepare coverage', 'Activate tower site'),
    'freight_terminal': ('Loading Puzzle', 'Use the loading window for ordinary containers and slower refrigerated cargo.', 'Cargo units', 'Loading window', 'Load containers', 'Load cold cargo', 'Keep It Cool', 'Pack a cold-chain consignment, then schedule its last-mile handoff.', 'Practice cargo', 'Chilled consignments', 'Pack cold cargo', 'Schedule delivery'),
    'data_center': ('Launch Day', 'Share processing time between compute jobs and slower storage provisioning.', 'Server capacity', 'Processing time', 'Run compute jobs', 'Provision storage', 'Cool Under Pressure', 'Prepare cooled capacity, then run API workloads without exhausting the cooling reserve.', 'Practice energy', 'Cooled capacity', 'Prepare cooling', 'Run API workload'),
    'solar_array': ('Panel Plan', 'Allocate inverter time between immediate generation and reserved capacity.', 'Sunlight units', 'Inverter time', 'Generate utility power', 'Reserve capacity', 'Reserve Promise', 'Verify stored generation, then issue credits backed by a clean-power commitment.', 'Practice generation', 'Verified generation', 'Verify reserve', 'Issue credits'),
    'uplink_center': ('Launch Window', 'Fit bandwidth traffic and ground-station bookings into a limited contact window.', 'Signal capacity', 'Contact window', 'Route bandwidth', 'Book ground time', 'Mission Control', 'Synchronize ground support, then receive the mission’s telemetry.', 'Practice mission supplies', 'Ground support', 'Synchronize support', 'Receive telemetry'),
}

# Output, supply cost and station time vary with the business. A cutting job
# produces several brackets; a repair uses more bench time than sorting parts.
PLAN_PROFILES = {
    'farm': ((2, 1, 1), (1, 2, 2)),
    'fish_stall': ((3, 2, 1), (1, 2, 3)),
    'roastery': ((2, 2, 1), (1, 1, 2)),
    'garage': ((1, 1, 2), (2, 2, 1)),
    'workshop': ((4, 2, 1), (1, 3, 3)),
    'solar_coop': ((3, 1, 1), (2, 3, 2)),
    'cannery': ((3, 2, 2), (1, 1, 1)),
    'machine_works': ((2, 3, 1), (1, 2, 3)),
    'turbine_field': ((4, 1, 1), (1, 2, 2)),
    'generator': ((4, 2, 2), (2, 3, 1)),
    'relay_station': ((2, 2, 2), (4, 1, 1)),
    'freight_terminal': ((2, 1, 1), (1, 2, 3)),
    'data_center': ((3, 2, 1), (2, 1, 2)),
    'solar_array': ((5, 2, 1), (2, 3, 2)),
    'uplink_center': ((3, 1, 2), (1, 2, 3)),
}

RESEARCH = (
    dict(id='food-basics', name='Food preparation', branch='Food', family='F', knowHowCost=2, cost=300, requires=[], effect='all', description='Food production +10% of base speed. Unlock preservation equipment.'),
    dict(id='food-mastery', name='Signature kitchen', branch='Food', family='F', knowHowCost=3, cost=3000, requires=['food-basics'], effect='signature', description='Food signature products +10% of base speed.'),
    dict(id='industry-basics', name='Workshop methods', branch='Industry', family='I', knowHowCost=2, cost=1200, requires=[], effect='all', description='Industry production +10% of base speed. Unlock precision equipment.'),
    dict(id='industry-mastery', name='Precision production', branch='Industry', family='I', knowHowCost=3, cost=12000, requires=['industry-basics'], effect='signature', description='Industry signature products +10% of base speed.'),
    dict(id='energy-basics', name='Power systems', branch='Energy / Tech', family='E', knowHowCost=2, cost=3500, requires=[], effect='all', description='Energy and tech production +10% of base speed. Unlock grid equipment.'),
    dict(id='energy-mastery', name='Connected systems', branch='Energy / Tech', family='E', knowHowCost=3, cost=35000, requires=['energy-basics'], effect='signature', description='Energy and tech signature products +10% of base speed. Unlock advanced equipment.'),
)

EQUIPMENT = (
    dict(id='preservation-kit', name='Preservation kit', research='food-basics', building='cannery', inputs={'garage_spare_parts': 3, 'workshop_steel_brackets': 2}),
    dict(id='precision-kit', name='Precision kit', research='industry-basics', building='machine_works', inputs={'workshop_welded_frames': 2, 'garage_spare_parts': 3}),
    dict(id='grid-kit', name='Grid control kit', research='energy-basics', building='generator', inputs={'solar_coop_battery_storage': 2, 'machine_works_tooling': 2}),
    dict(id='freight-kit', name='Freight handling kit', research='industry-basics', building='freight_terminal', inputs={'machine_works_cnc_parts': 2, 'relay_station_bandwidth': 2}),
    dict(id='server-kit', name='Server installation kit', research='energy-mastery', building='data_center', inputs={'machine_works_tooling': 3, 'generator_baseload_power': 2}),
    dict(id='uplink-kit', name='Mission support kit', research='energy-mastery', building='uplink_center', inputs={'data_center_compute_hours': 3, 'solar_array_reserve_capacity': 2}),
)

# Reputation is a permanent qualification, never a construction payment.
# Each threshold can be earned entirely from earlier businesses' quests.
PRESTIGE_EXPANSIONS = (
    ('turbine_field', 6),
    ('relay_station', 10),
    ('solar_array', 14),
)


def enabled(cfg):
    return bool(cfg.get('businessDesign', {}).get('enabled'))


def connected_enabled(cfg):
    return enabled(cfg) and bool(cfg.get('businessDesign', {}).get('connectedProgression'))


RESEARCH_CLOSED = 'Research is closed for testing'


def research_enabled(cfg):
    """Know-how and research are off when the class rules say
    businessDesign.researchEnabled is false: quests pay Prestige only, no
    research can be bought and none applies. Absent means on."""
    return enabled(cfg) and cfg.get('businessDesign', {}).get('researchEnabled', True) is not False


def ensure(cfg, st, migrating=False):
    if not enabled(cfg):
        return None
    p = st.get('businessProgression')
    # A record the normalization below has finished is complete: no code
    # removes its keys, equipmentValue is written last, and connectedVersion
    # marks the connected block done. Running the rest again changes nothing;
    # skipping it matters because this is called ~130 times per player-tick.
    if p is not None and 'equipmentValue' in p and (p.get('connectedVersion') == 1 or not connected_enabled(cfg)):
        return p
    if 'businessProgression' not in st:
        owned = _owned(cfg, st) if migrating else set()
        st['businessProgression'] = dict(version=1, knowHow=0, prestige=0,
            quests={}, research=[], equipment={}, grandfathered=sorted(owned))
    p = st['businessProgression']
    for key, value in dict(version=1, knowHow=0, prestige=0, quests={}, research=[], equipment={}, grandfathered=[]).items():
        if key not in p:   # setdefault(..., deepcopy(...)) would deep-copy on every call; this runs ~90x per player-tick
            p[key] = copy.deepcopy(value)
    if connected_enabled(cfg):
        p.setdefault('prestigeEarned', max(p['prestige'], sum(bool(q.get('completed')) for q in p['quests'].values())))
        p.setdefault('activity', dict(produced={}, sold={}, salesBySource={}))
        for key in ('produced', 'sold', 'salesBySource'):
            p['activity'].setdefault(key, {})
        if p.get('connectedVersion') != 1:
            # Normalize accepted legacy records once, rather than changing them
            # on later read/validation paths. Practice reset keeps this marker.
            for q in p['quests'].values():
                q.setdefault('mode', 'legacy')
            # A workshop already begun carries its promised quest qualification,
            # including a finished Breakfast whose extra quest reward is unclaimed.
            if isinstance(st.get('breakfastEvent'), dict):
                p['quests'].setdefault('roastery-signature', dict(mode='legacy'))
            p['connectedVersion'] = 1
    if 'equipmentValue' not in p:
        goods = _catalog(cfg)
        p['equipmentValue'] = sum(p['equipment'].get(e['id'], 0) *
            sum(goods.get(gid, {}).get('unitPrice', 0) * qty for gid, qty in e['inputs'].items()) for e in EQUIPMENT)
    return p


def record_production(cfg, st, good_id, qty):
    """Observe an actual completed production batch; never create goods/rewards."""
    if not connected_enabled(cfg) or type(qty) is not int or qty <= 0 or good_id not in _catalog(cfg):
        return
    counters = ensure(cfg, st)['activity']['produced']
    counters[good_id] = counters.get(good_id, 0) + qty


def record_sale(cfg, st, requirements, source):
    """Observe settled goods once, called by the owner of each sale transaction.

    Orders, projects, shoppers and regulars share these observations; no second
    stock debit occurs when a quest recognizes the same fulfilled delivery.
    """
    if not connected_enabled(cfg) or not isinstance(source, str):
        return
    activity = ensure(cfg, st)['activity']
    goods = _catalog(cfg)
    for need in requirements:
        gid, qty = need.get('goodId'), need.get('quantity')
        if gid not in goods or type(qty) is not int or qty <= 0:
            continue
        activity['sold'][gid] = activity['sold'].get(gid, 0) + qty
        channel = activity['salesBySource'].setdefault(source, {})
        channel[gid] = channel.get(gid, 0) + qty


def _owned(cfg, st):
    return {cfg['tiers'][ti]['id'] for ti in st.get('tierOf', [])
            if type(ti) is int and 0 <= ti < len(cfg['tiers'])}


def _catalog(cfg):
    return rules_tables.derived(cfg, 'progression_catalog', _build_catalog)


def _build_catalog(cfg):
    return {g['id']: dict(g, buildingId=t['id']) for t in cfg['tiers'] for g in t['goods']}


def _signature_buildings(cfg):
    """Signature (last-listed) product id -> business id. The first business
    listing a product wins, as the scan this table replaces did."""
    table = {}
    for tier in cfg['tiers']:
        if tier['goods']:
            table.setdefault(tier['goods'][-1]['id'], tier['id'])
    return table


def _quest_specs(cfg):
    result = {}
    for tier in cfg['tiers']:
        bid = tier['id']
        theme = QUEST_THEMES.get(bid)
        if not theme or len(tier.get('goods', [])) < 3:
            continue
        goods = tier['goods']
        base = dict(buildingId=bid, buildingName=tier['name'])
        result[bid + '-plan'] = dict(base, id=bid + '-plan', kind='plan', title=theme[0], summary=theme[1],
            rawName=theme[2], workLabel=theme[3], recipeNames=theme[4:6],
            goodNames=[goods[0]['name'], goods[1]['name']], perkIds=[goods[0]['id'], goods[1]['id']], previous=None)
        result[bid + '-signature'] = dict(base, id=bid + '-signature', kind='signature', title=theme[6], summary=theme[7],
            rawName=theme[8], componentName=theme[9], recipeNames=theme[10:12], workLabel='Workshop time',
            goodNames=[goods[1]['name'], goods[2]['name']], perkIds=[goods[1]['id'], goods[2]['id']], previous=bid + '-plan',
            unlockGood=goods[2]['id'], signatureName=goods[2]['name'])
    return result


def product_unlocked(cfg, st, gid):
    if not enabled(cfg):
        return True
    p = ensure(cfg, st)
    bid = rules_tables.derived(cfg, 'signature_buildings', _signature_buildings).get(gid)
    if bid is None or bid in ('farm', 'fish_stall', 'roastery') or bid in p['grandfathered']:
        return True
    return bool(p['quests'].get(bid + '-signature', {}).get('completed') or
                connected_enabled(cfg) and p['quests'].get(bid + '-plan', {}).get('completed'))


def speed_bonus(cfg, st, b, good):
    if not enabled(cfg):
        return 0
    p = ensure(cfg, st)
    ti = b.get('tier')
    if type(ti) is not int or not 0 <= ti < len(cfg['tiers']):
        return 0
    tier = cfg['tiers'][ti]
    bonus = sum(5 for quest in p['quests'].values()
                if quest.get('completed') and quest.get('perkGood') == good['id'])
    for r in RESEARCH if research_enabled(cfg) else ():
        if r['id'] in p['research'] and r['family'] == tier['family']:
            if r['effect'] == 'all' or good['id'] == tier['goods'][-1]['id']:
                bonus += 10
    return bonus


def _research_rows(cfg, st):
    if not research_enabled(cfg):
        return []
    p = ensure(cfg, st)
    names = {r['id']: r['name'] for r in RESEARCH}
    families = {t['family'] for t in cfg['tiers'] if t['id'] in _owned(cfg, st)}
    rows = []
    for r in RESEARCH:
        owned = r['id'] in p['research']
        requires = [dict(id=key, name=names[key], owned=key in p['research']) for key in r['requires']]
        why = ('Already researched' if owned else
               'Open a ' + r['branch'] + ' business first' if r['family'] not in families else
               'Research ' + next((x['name'] for x in requires if not x['owned']), '') if any(not x['owned'] for x in requires) else
               'Need ' + str(r['knowHowCost'] - p['knowHow']) + ' more Know-how' if p['knowHow'] < r['knowHowCost'] else
               'Need ' + str(r['cost'] - st.get('cash', 0)) + ' more YM' if st.get('cash', 0) < r['cost'] else '')
        row = dict(r, requires=requires, owned=owned, ready=not why, why=why)
        if connected_enabled(cfg):
            row['description'] = row['description'].split(' Unlock ')[0]
        rows.append(row)
    return rows


def _available_stock(cfg, st):
    # Deferred import avoids a cycle with the production engine's hooks.
    import production_economy
    held = production_economy.delivery_reservations(cfg, st)
    return {gid: max(0, qty - held.get(gid, 0)) for gid, qty in st.get('inventory', {}).items()}


def _equipment_rows(cfg, st):
    p = ensure(cfg, st)
    goods = _catalog(cfg)
    available = _available_stock(cfg, st)
    tier_names = {t['id']: t['name'] for t in cfg['tiers']}
    research_names = {r['id']: r['name'] for r in RESEARCH}
    research_branches = {r['id']: r['branch'] for r in RESEARCH}
    rows = []
    for e in EQUIPMENT:
        unlocked = e['research'] in p['research']
        inputs = [dict(goodId=gid, name=goods[gid]['name'], quantity=qty,
                       owned=available.get(gid, 0), ready=available.get(gid, 0) >= qty)
                  for gid, qty in e['inputs'].items() if gid in goods]
        missing = next((i for i in inputs if not i['ready']), None)
        inactive = connected_enabled(cfg)
        why = ('Equipment has no functional use yet' if inactive else
               'Research ' + research_names[e['research']] if not unlocked else
               'Need unreserved ' + missing['name'] if missing else '')
        rows.append(dict(id=e['id'], name=e['name'], description=('Stored equipment. No current use.' if inactive else
                         'Construction equipment for ' + tier_names.get(e['building'], e['building']) + '.'),
                         cost=0, quantity=p['equipment'].get(e['id'], 0), inputs=inputs, unlocked=unlocked,
                         buildingId=e['building'], researchId=e['research'], branch=research_branches[e['research']], researchReady=unlocked,
                         inactive=inactive,
                         ready=not why, why=why, usedFor=[] if inactive else [tier_names.get(e['building'], e['building'])]))
    return rows


def _prestige_milestones(cfg, st):
    if not enabled(cfg) or not cfg.get('businessDesign', {}).get('prestigeExpansion', False):
        return []
    p = ensure(cfg, st)
    prestige = p.get('prestigeEarned', p['prestige']) if connected_enabled(cfg) else p['prestige']
    tiers = {tier['id']: tier for tier in cfg['tiers']}
    owned = _owned(cfg, st)
    return [dict(buildingId=bid, name=tiers[bid]['name'], prestigeRequired=threshold,
                 current=prestige, ready=prestige >= threshold, owned=bid in owned)
            for bid, threshold in PRESTIGE_EXPANSIONS if bid in tiers]


def expansion_requirements(cfg, st, ti):
    if not enabled(cfg):
        return dict(ready=True, requirements=[], why='')
    if type(ti) is not int or not 0 <= ti < len(cfg['tiers']):
        return dict(ready=False, requirements=[], why='Unknown business')
    p = ensure(cfg, st)
    bid = cfg['tiers'][ti]['id']
    e = next((e for e in EQUIPMENT if e['building'] == bid), None)
    req = []
    if e is not None and not connected_enabled(cfg):
        r = next(r for r in RESEARCH if r['id'] == e['research'])
        req.extend([
            dict(kind='research', id=r['id'], name=r['name'], quantity=1,
                 owned=int(r['id'] in p['research']), ready=r['id'] in p['research'],
                 researchId=r['id'], branch=r['branch']),
            dict(kind='equipment', id=e['id'], name=e['name'], quantity=1,
                 owned=p['equipment'].get(e['id'], 0), ready=p['equipment'].get(e['id'], 0) >= 1,
                 researchId=r['id'], branch=r['branch']),
        ])
    milestone = next((row for row in _prestige_milestones(cfg, st) if row['buildingId'] == bid), None)
    if milestone is not None:
        req.append(dict(kind='prestige', id='prestige', name='Prestige',
                        quantity=milestone['prestigeRequired'], owned=milestone['current'], ready=milestone['ready'],
                        description=('Lifetime Prestige earned from business quests. Spending Prestige keeps this qualification.'
                                     if connected_enabled(cfg) else 'Earn Prestige by completing business quests. Prestige is kept.')))
    missing = [str(item['quantity'] - item['owned']) + ' more Prestige'
               if item['kind'] == 'prestige' else item['name'] for item in req if not item['ready']]
    return dict(ready=not missing, requirements=req, why='Need ' + ' and '.join(missing) if missing else '')


def equipment_value(cfg, st):
    """Kits retain their component book value while held for construction."""
    if not enabled(cfg):
        return 0
    p = ensure(cfg, st)
    goods = _catalog(cfg)
    value = sum(p['equipment'].get(e['id'], 0) *
                sum(goods.get(gid, {}).get('unitPrice', 0) * qty for gid, qty in e['inputs'].items())
                for e in EQUIPMENT)
    p['equipmentValue'] = value
    return value


def consume_expansion(cfg, st, ti):
    requirements = expansion_requirements(cfg, st, ti)
    if not requirements['ready']:
        return dict(ok=False, why=requirements['why'])
    consumed_value = 0
    if enabled(cfg):
        p = ensure(cfg, st)
        before_value = equipment_value(cfg, st)
        for need in requirements['requirements']:
            if need['kind'] == 'equipment':
                p['equipment'][need['id']] -= need['quantity']
        consumed_value = before_value - equipment_value(cfg, st)
    return dict(ok=True, consumedValue=consumed_value)


def _choices(spec):
    if spec['kind'] == 'plan':
        rows = []
        for index, choice in enumerate(('regulars', 'special')):
            model = _workshop(spec, choice)
            goals = model['goals']
            rows.append(dict(id=choice, name='Everyday customers' if index == 0 else 'Special order',
                description='Deliver ' + str(goals['first']) + ' ' + spec['goodNames'][0] + ' and ' + str(goals['second']) + ' ' + spec['goodNames'][1] + ' in ' + str(model['work']) + ' work units.',
                perk=spec['goodNames'][index] + ' +5% base speed'))
        return rows
    return [dict(id='careful', name='Keep a starter', description='Make 2 finished batches and keep 2 prepared components. 8 work units.', perk=spec['goodNames'][0] + ' +5% base speed'),
            dict(id='bulk', name='Large batch', description='Make 4 finished batches in 6 work units. Larger preparation and assembly batches.', perk=spec['goodNames'][1] + ' +5% base speed')]


def _workshop(spec, choice):
    if spec['kind'] == 'plan':
        special = choice == 'special'
        first, second = PLAN_PROFILES[spec['buildingId']]
        a, b = (1, 3) if special else (2, 2)
        supplies = max(2 * first[1] + 2 * second[1], first[1] + 3 * second[1]) + 1
        return dict(stock={'raw': supplies, 'first': 0, 'second': 0}, work=a * first[2] + b * second[2],
                    goals={'first': a * first[0], 'second': b * second[0]},
                    recipes=[dict(id='first', inputs={'raw': first[1]}, output='first', quantity=first[0], work=first[2]),
                             dict(id='second', inputs={'raw': second[1]}, output='second', quantity=second[0], work=second[2])])
    bulk = choice == 'bulk'
    return dict(stock={'raw': 12 if bulk else 10, 'component': 0, 'finished': 0}, work=6 if bulk else 8,
                goals={'finished': 4} if bulk else {'finished': 2, 'component': 2},
                recipes=[dict(id='prepare', inputs={'raw': 3 if bulk else 2}, output='component', quantity=3 if bulk else 2, work=1),
                         dict(id='finish', inputs={'component': 3 if bulk else 2, 'raw': 1}, output='finished', quantity=2 if bulk else 1, work=2)])


def _labels(spec):
    if spec['kind'] == 'plan':
        return dict(raw=spec['rawName'], first=spec['goodNames'][0], second=spec['goodNames'][1])
    return dict(raw=spec['rawName'], component=spec['componentName'], finished=spec['signatureName'])


def _lock_reason(cfg, st, spec, p):
    if spec['buildingId'] not in _owned(cfg, st):
        return 'Open ' + spec['buildingName'] + ' first'
    if spec['previous'] and not p['quests'].get(spec['previous'], {}).get('completed'):
        previous = _quest_specs(cfg)[spec['previous']]
        return 'Complete ' + previous['title'] + ' first'
    return ''


def _breakfast_qualifies(st, spec):
    return spec['id'] == 'roastery-signature' and st.get('breakfastEvent', {}).get('stage') == 5


def _connected_choices(spec):
    return [dict(id=row['id'], name=row['name'], perk=row['perk'],
                 description='Recognize real production and sales; improve ' + spec['goodNames'][index] + '.')
            for index, row in enumerate(_choices(spec))]


def _connected_objectives(cfg, st, spec):
    tier = next(t for t in cfg['tiers'] if t['id'] == spec['buildingId'])
    if spec['kind'] == 'plan':
        amounts = _workshop(spec, 'regulars')['goals']
        targets = [(tier['goods'][0], amounts['first']), (tier['goods'][1], amounts['second'])]
    else:
        targets = [(tier['goods'][2], 2)]
    overrides = cfg.get('businessDesign', {}).get('connectedQuestTargets', {}).get(spec['id'], {})
    activity = ensure(cfg, st)['activity']
    rows = []
    for good, default in targets:
        quantity = overrides.get(good['id'], default)
        if type(quantity) is not int or quantity < 1:
            quantity = default
        for kind, counter in (('produce', 'produced'), ('sell', 'sold')):
            owned = activity[counter].get(good['id'], 0)
            rows.append(dict(id=kind + ':' + good['id'], kind=kind, goodId=good['id'],
                             name=good['name'], quantity=quantity, owned=owned, ready=owned >= quantity))
    return rows


def _connected_quest_row(cfg, st, spec):
    p = ensure(cfg, st)
    q = p['quests'].get(spec['id'], {})
    why = _lock_reason(cfg, st, spec, p)
    done = bool(q.get('completed'))
    choices = _connected_choices(spec)
    selected = next((c for c in choices if c['id'] == q.get('choice')), None)
    objectives = _connected_objectives(cfg, st, spec)
    tier = next(t for t in cfg['tiers'] if t['id'] == spec['buildingId'])
    reward = _quest_reward(cfg)
    if spec['kind'] == 'plan' and spec['buildingId'] not in ('farm', 'fish_stall', 'roastery'):
        reward += ' · Unlock ' + tier['goods'][2]['name'] + ' recipe'
    reward += ' · ' + (selected['perk'] if selected else 'Choose a recipe for +5% base speed')
    return dict(id=spec['id'], buildingId=spec['buildingId'], buildingName=spec['buildingName'],
                title=spec['title'], summary=('Produce and sell this business’s everyday goods.' if spec['kind'] == 'plan'
                    else 'Produce and sell ' + tier['goods'][2]['name'] + ' through your real business.'),
                mode='connected', status='done' if done else 'locked' if why else 'tracking' if selected else 'plan',
                unlockText=why, rewardText=reward, choices=choices, selectedChoice=q.get('choice'),
                objectives=objectives, stocks=[], recipes=[], goals=[], canReset=False,
                ready=not why and not done and bool(selected) and all(o['ready'] for o in objectives),
                workRemaining=0, workTotal=0, workLabel='',
                suppliesText='Real production and completed sales count automatically. Claiming uses no extra goods.',
                linkedEvent=None,
                relatedText='Your farm supplies eggs and honey for these pastries.' if spec['id'] == 'roastery-signature' else '')


def _quest_row(cfg, st, spec):
    p = ensure(cfg, st)
    q = p['quests'].get(spec['id'], {})
    if connected_enabled(cfg) and q.get('mode') != 'legacy':
        return _connected_quest_row(cfg, st, spec)
    why = _lock_reason(cfg, st, spec, p)
    done = bool(q.get('completed'))
    choices = _choices(spec)
    choice = q.get('choice')
    model = _workshop(spec, choice) if choice else None
    labels = _labels(spec)
    stock = q.get('stock', {})
    recipes, goals = [], []
    if model:
        for index, r in enumerate(model['recipes']):
            missing = next((key for key, qty in r['inputs'].items() if stock.get(key, 0) < qty), None)
            reason = 'Need ' + labels[missing] if missing else 'Not enough work time; reset practice to try another plan' if q.get('work', 0) < r['work'] else ''
            recipes.append(dict(id=r['id'], name=spec['recipeNames'][index], work=r['work'],
                inputs=[dict(id=key, name=labels[key], quantity=qty, owned=stock.get(key, 0)) for key, qty in r['inputs'].items()],
                output=dict(id=r['output'], name=labels[r['output']], quantity=r['quantity']),
                ready=not reason and not done and not why, why=reason))
        goals = [dict(id=key, name=labels[key], quantity=qty, owned=stock.get(key, 0), ready=stock.get(key, 0) >= qty)
                 for key, qty in model['goals'].items()]
    breakfast = _breakfast_qualifies(st, spec)
    ready = not why and not done and (breakfast or bool(goals) and all(g['ready'] for g in goals))
    selected = next((c for c in choices if c['id'] == choice), None)
    reward = _quest_reward(cfg)
    if spec['kind'] == 'signature' and spec['buildingId'] not in ('farm', 'fish_stall', 'roastery'):
        reward += ' · Unlock ' + spec['signatureName']
    reward += ' · ' + (selected['perk'] if selected else 'Choose a recipe for +5% base speed')
    return dict(id=spec['id'], buildingId=spec['buildingId'], buildingName=spec['buildingName'], mode='legacy',
        title=spec['title'], summary=spec['summary'], status='done' if done else 'locked' if why else 'workshop' if choice else 'plan',
        unlockText=why, rewardText=reward, choices=choices, selectedChoice=choice,
        stocks=[dict(id=key, name=labels[key], quantity=value) for key, value in stock.items()],
        recipes=recipes, goals=goals, ready=ready, canReset=bool(choice) and not done and not why,
        workRemaining=q.get('work', 0), workTotal=model['work'] if model else 0, workLabel=spec['workLabel'],
        suppliesText='Practice supplies only. Town stock and cash stay unchanged. Reset practice any time before finishing.',
        linkedEvent='breakfast' if spec['id'] == 'roastery-signature' else None,
        relatedText='Breakfast Club complete: claim this quest reward.' if breakfast else
                    'The original Breakfast Club workshop also completes this quest.' if spec['id'] == 'roastery-signature' else '')


def _quest_reward(cfg):
    return '+1 Know-how · +1 Prestige' if research_enabled(cfg) else '+1 Prestige'


def payload(cfg, st):
    if not enabled(cfg):
        return dict(enabled=False, mode='legacy', equipmentEnabled=False, researchEnabled=False, knowHow=0, prestige=0, prestigeEarned=0,
                    quests=[], research=[], equipment=[], prestigeMilestones=[])
    p = ensure(cfg, st)
    return dict(enabled=True, mode='connected' if connected_enabled(cfg) else 'legacy',
                equipmentEnabled=not connected_enabled(cfg), researchEnabled=research_enabled(cfg),
                knowHow=p['knowHow'] if research_enabled(cfg) else 0, prestige=p['prestige'],
                prestigeEarned=p.get('prestigeEarned', p['prestige']),
                quests=[_quest_row(cfg, st, spec) for spec in _quest_specs(cfg).values()],
                research=_research_rows(cfg, st), equipment=_equipment_rows(cfg, st),
                prestigeMilestones=_prestige_milestones(cfg, st))


def _complete_quest(cfg, st, spec, q):
    p = ensure(cfg, st)
    q['completed'] = True
    q['completedTick'] = st.get('tick', 0)
    p['quests'][spec['id']] = q
    if research_enabled(cfg):
        p['knowHow'] += 1
    p['prestige'] += 1
    if connected_enabled(cfg):
        p['prestigeEarned'] += 1
    return dict(ok=True, kind='quest', message=spec['title'] + ' complete: ' +
                ('+1 Know-how and +1 Prestige' if research_enabled(cfg) else '+1 Prestige'))


def _act_connected_quest(cfg, st, spec, q, body):
    action = body.get('action')
    if action == 'quest_start':
        ensure(cfg, st)['quests'].setdefault(spec['id'], dict(mode='connected'))
        return dict(ok=True, kind='quest', message='Choose a recipe improvement. Real business activity counts automatically.')
    if action == 'quest_plan':
        if q.get('choice'):
            return dict(ok=False, why='Your recipe improvement is already chosen')
        selected = next((i for i, row in enumerate(_connected_choices(spec)) if row['id'] == body.get('choice')), None)
        if selected is None:
            return dict(ok=False, why='Unknown plan')
        ensure(cfg, st)['quests'][spec['id']] = dict(mode='connected', choice=body['choice'], perkGood=spec['perkIds'][selected])
        return dict(ok=True, kind='quest', message='Recipe improvement chosen. Produce and sell the required goods.')
    if action != 'quest_finish':
        return dict(ok=False, why='This quest tracks real production and sales; there are no practice batches to reset')
    row = _connected_quest_row(cfg, st, spec)
    if not row['ready']:
        return dict(ok=False, why='Choose a recipe improvement and complete the real production and sales goals first')
    return _complete_quest(cfg, st, spec, q)


def act(cfg, st, body):
    """Validate against a copy: refusals never spend cash, stock, work or rewards."""
    if not enabled(cfg):
        return dict(ok=False, why='Business quests are not enabled for this class')
    if not isinstance(body, dict):
        return dict(ok=False, why='Invalid progression action')
    working = copy.deepcopy(st)
    ensure(cfg, working)
    result = _act(cfg, working, body)
    if result['ok']:
        st.clear()
        st.update(working)
    return result


def _act(cfg, st, body):
    p = ensure(cfg, st)
    fail = lambda why: dict(ok=False, why=why)
    action = body.get('action')
    if action == 'research':
        if not research_enabled(cfg):
            return fail(RESEARCH_CLOSED)
        row = next((r for r in _research_rows(cfg, st) if r['id'] == body.get('researchId')), None)
        if row is None:
            return fail('Unknown research')
        if not row['ready']:
            return fail(row['why'])
        p['knowHow'] -= row['knowHowCost']
        st['cash'] -= row['cost']
        p['research'].append(row['id'])
        return dict(ok=True, kind='research', message=row['name'] + ' researched')
    if action == 'craft':
        if connected_enabled(cfg):
            return fail('Equipment has no functional use yet')
        row = next((e for e in _equipment_rows(cfg, st) if e['id'] == body.get('equipmentId')), None)
        if row is None:
            return fail('Unknown equipment')
        if not row['ready']:
            return fail(row['why'])
        import inventory_costs
        inventory_costs.consume(cfg, st, row['inputs'])
        for need in row['inputs']:
            st['inventory'][need['goodId']] -= need['quantity']
        p['equipment'][row['id']] = p['equipment'].get(row['id'], 0) + 1
        equipment_value(cfg, st)
        import production_economy
        production_economy._sync_pools(cfg, st)
        return dict(ok=True, kind='craft', message=row['name'] + ' crafted')
    if action not in ('quest_start', 'quest_plan', 'quest_batch', 'quest_finish', 'quest_reset'):
        return fail('Unknown progression action')
    quest_id = body.get('questId')
    if not isinstance(quest_id, str):
        return fail('Unknown quest')
    spec = _quest_specs(cfg).get(quest_id)
    if spec is None:
        return fail('Unknown quest')
    why = _lock_reason(cfg, st, spec, p)
    if why:
        return fail(why)
    q = p['quests'].get(quest_id, {})
    if q.get('completed'):
        return fail('This quest reward has already been earned')
    if connected_enabled(cfg) and q.get('mode') != 'legacy':
        return _act_connected_quest(cfg, st, spec, q, body)
    if action == 'quest_start':
        p['quests'].setdefault(quest_id, dict(mode='legacy'))
        return dict(ok=True, kind='quest', message='Choose your plan')
    if action == 'quest_reset':
        p['quests'][quest_id] = dict(mode='legacy')
        return dict(ok=True, kind='quest', message='Practice reset. Choose a new plan.')
    if action == 'quest_plan':
        if q.get('choice'):
            return fail('Reset practice before changing your plan')
        choice = body.get('choice')
        choices = _choices(spec)
        selected = next((i for i, c in enumerate(choices) if c['id'] == choice), None)
        if selected is None:
            return fail('Unknown plan')
        model = _workshop(spec, choice)
        p['quests'][quest_id] = dict(mode='legacy', choice=choice, stock=copy.deepcopy(model['stock']), work=model['work'], perkGood=spec['perkIds'][selected])
        return dict(ok=True, kind='quest', message='Plan chosen. Make the required batches within the work budget.')
    breakfast = _breakfast_qualifies(st, spec)
    if action == 'quest_finish' and breakfast:
        q.setdefault('perkGood', 'roastery_espresso_shots' if st.get('breakfastEvent', {}).get('upgrade') == 'coffee' else 'roastery_pastries')
    elif not q.get('choice'):
        return fail('Choose a plan first')
    if action == 'quest_batch':
        model = _workshop(spec, q['choice'])
        recipe = next((r for r in model['recipes'] if r['id'] == body.get('recipe')), None)
        if recipe is None:
            return fail('Unknown workshop recipe')
        if q['work'] < recipe['work']:
            return fail('Not enough work time. Reset practice to try a different plan.')
        if any(q['stock'].get(key, 0) < qty for key, qty in recipe['inputs'].items()):
            return fail('Make the required practice ingredients first')
        for key, qty in recipe['inputs'].items():
            q['stock'][key] -= qty
        q['stock'][recipe['output']] += recipe['quantity']
        q['work'] -= recipe['work']
        return dict(ok=True, kind='quest', message='Practice batch completed')
    if not breakfast:
        model = _workshop(spec, q['choice'])
        if not all(q['stock'].get(key, 0) >= qty for key, qty in model['goals'].items()):
            return fail('Finish every practice goal before claiming the reward')
    return _complete_quest(cfg, st, spec, q)
