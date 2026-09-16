"""Permanent, prepaid teams and bounded trainer development for Operations.

Teams belong to a business type, so rebuilding cannot reset recruitment or
replay a focus purchase. Only a live building instance can receive commands.
The caller advances this module once per permitted economy tick, after goods
production. New trainers begin teaching on the following tick; there is no
wall-clock catch-up, automatic purchasing, or generation of ingredients.
"""
from __future__ import annotations

import copy
import math

import worker_population as population


BRANCHES = ('production', 'sales', 'efficiency')
NODE_IDS = ('orientation', 'production', 'production-advanced', 'sales',
            'sales-advanced', 'efficiency', 'efficiency-advanced')
THEMES = {
    'farm': ('Farm Apprenticeship', 'Harvest Practice', 'Apiary Skills', 'Farm Stand', 'Honey Counter', 'Coop Care', 'Hive Maintenance'),
    'fish_stall': ('Harbor Apprenticeship', 'Catch Handling', 'Smokehouse Skills', 'Harbor Counter', 'Smoked Fish Counter', 'Ice Routine', 'Smoker Maintenance'),
    'roastery': ('Counter Apprenticeship', 'Roast Practice', 'Breakfast Brigade', 'Counter Service', 'Breakfast Counter', 'Machine Care', 'Oven Routine'),
    'garage': ('Garage Apprenticeship', 'Repair Practice', 'Custom Shop', 'Service Desk', 'Custom Consultations', 'Tool Care', 'Modification Planning'),
    'workshop': ('Workshop Apprenticeship', 'Cutting and Welding', 'Machining Skills', 'Trade Counter', 'Precision Orders', 'Bench Maintenance', 'Jig Care'),
    'solar_coop': ('Solar Apprenticeship', 'Solar Crew', 'Credit Verification', 'Neighborhood Service', 'Credit Sales', 'Panel Maintenance', 'Verification Routine'),
    'cannery': ('Cannery Apprenticeship', 'Filling Line', 'Preserve Kitchen', 'Pantry Counter', 'Preserve Sales', 'Line Maintenance', 'Preserve Scheduling'),
    'machine_works': ('Machine Apprenticeship', 'Machine Practice', 'Prototype Team', 'Parts Desk', 'Prototype Consultations', 'Machine Care', 'Prototype Planning'),
    'turbine_field': ('Turbine Apprenticeship', 'Turbine Crew', 'Certification Team', 'Capacity Desk', 'Certificate Sales', 'Turbine Maintenance', 'Certification Routine'),
    'generator': ('Power Apprenticeship', 'Dispatch Crew', 'Heat Recovery Team', 'Power Desk', 'Heat Customers', 'Turbine Maintenance', 'Heat-System Care'),
    'relay_station': ('Network Apprenticeship', 'Network Crew', 'Tower Support', 'Subscriber Desk', 'Tower Bookings', 'Radio Maintenance', 'Site Planning'),
    'freight_terminal': ('Freight Apprenticeship', 'Loading Crew', 'Last-Mile Team', 'Cargo Desk', 'Delivery Bookings', 'Handling Routine', 'Route Planning'),
    'data_center': ('Server Apprenticeship', 'Server Crew', 'API Team', 'Hosting Desk', 'API Customers', 'Cooling Maintenance', 'Workload Planning'),
    'solar_array': ('Array Apprenticeship', 'Array Crew', 'Credit Verification', 'Reserve Desk', 'Credit Sales', 'Inverter Maintenance', 'Verification Routine'),
    'uplink_center': ('Uplink Apprenticeship', 'Ground Crew', 'Telemetry Team', 'Contact Desk', 'Mission Customers', 'Antenna Maintenance', 'Mission Scheduling'),
}


def enabled(cfg):
    return (cfg.get('businessDesign', {}).get('enabled') is True
            and cfg.get('workforce', {}).get('enabled') is True)


def _seconds(cfg, key, default):
    value = cfg.get('workforce', {}).get(key, default)
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value > 0 else default


def _now(cfg, st):
    return st.get('tick', 0) * cfg['global']['tick']


def _empty_team():
    return dict(hires=0, trainers=0, workers=0, allocation=dict.fromkeys(BRANCHES, 0),
                trainingBranch='production', nodes=[], workerWork=0, trainerWork=0,
                nextHireAt=0, spent=0)


def _worker_cap(team):
    return 0 if team['hires'] == 0 else 5 + 5 * team['hires']


def _trainer_cap(team):
    return team['hires'] + 2 if team['hires'] else 0


def _live(cfg, st):
    for b in st.get('b', []):
        ti = b.get('tier')
        if type(ti) is int and 0 <= ti < len(cfg['tiers']):
            yield b, cfg['tiers'][ti]


def ensure(cfg, st):
    """Add defaults and convert a paid, active legacy shift exactly once.

Call before legacy management migration, which can clear shifts on buildings
that have no instance id yet. An expired shift creates no permanent staff.
"""
    if not enabled(cfg):
        return {}
    data = st.setdefault('workforce', dict(version=1, teams={}, hq=dict(level=0, targets=[])))
    data.setdefault('version', 1)
    data.setdefault('teams', {})
    data.setdefault('hq', dict(level=0, targets=[]))
    data['hq'].setdefault('level', 0)
    data['hq'].setdefault('targets', [])
    live_types = {tier['id'] for _, tier in _live(cfg, st)}
    # Closed businesses retain their team, but cannot strand an academy slot.
    data['hq']['targets'][:] = [target for target in data['hq']['targets'] if target in live_types]
    for team in data['teams'].values():
        for key, value in _empty_team().items():
            team.setdefault(key, copy.deepcopy(value))
        for branch in BRANCHES:
            team['allocation'].setdefault(branch, 0)
    for b, tier in _live(cfg, st):
        staff = b.get('staff')
        if isinstance(staff, dict) and staff.get('remainingTicks', 0) > 0:
            team = data['teams'].setdefault(tier['id'], _empty_team())
            if not team.get('legacyConverted'):
                if team['hires'] == 0:
                    team.update(hires=1, trainers=1, nextHireAt=_now(cfg, st) + _seconds(cfg, 'hireCooldownSeconds', 1800))
                if 'orientation' not in team['nodes']:
                    team['nodes'].append('orientation')
                team['legacyConverted'] = dict(role=staff.get('id', ''), tick=st.get('tick', 0))
        if staff is not None:
            b['staff'] = None
    if population.enabled(cfg):
        population.ensure(cfg, st)
    return data


def _unlocked(team, branch):
    return ('orientation' if branch == 'production' else branch) in team['nodes']


def advance(cfg, st, dt=None):
    if not enabled(cfg):
        return
    dt = cfg['global']['tick'] if dt is None else dt
    if type(dt) not in (int, float) or not math.isfinite(dt) or dt <= 0:
        return
    data = ensure(cfg, st)
    worker_seconds = _seconds(cfg, 'workerTrainingSeconds', 300)
    trainer_seconds = _seconds(cfg, 'trainerTrainingSeconds', 600)
    supported = set(data['hq']['targets'][:data['hq']['level']])
    for b, tier in _live(cfg, st):
        team = data['teams'].get(tier['id'])
        if not team or b.get('paused') or not team['hires']:
            continue
        # Existing trainers teach this tick; HQ's new graduates teach next tick.
        if not population.enabled(cfg) and team['workers'] < _worker_cap(team):
            team['workerWork'] += dt * team['trainers']
            added = min(_worker_cap(team) - team['workers'], int(team['workerWork'] // worker_seconds))
            team['workers'] += added
            team['workerWork'] -= added * worker_seconds
            branch = team['trainingBranch']
            if added and _unlocked(team, branch):
                team['allocation'][branch] += added
        if not population.enabled(cfg) and team['workers'] >= _worker_cap(team):
            team['workerWork'] = 0
        if tier['id'] in supported and team['trainers'] < _trainer_cap(team):
            team['trainerWork'] += dt
            added = min(_trainer_cap(team) - team['trainers'], int(team['trainerWork'] // trainer_seconds))
            team['trainers'] += added
            team['trainerWork'] -= added * trainer_seconds
        if team['trainers'] >= _trainer_cap(team):
            team['trainerWork'] = 0


def bonuses(cfg, st, b):
    """Additional percentage points of base output/demand; cost discount %."""
    result = dict(production=0, customer=0, efficiency=0)
    if not enabled(cfg) or population.enabled(cfg) or b.get('paused'):
        return result
    ti = b.get('tier')
    if type(ti) is not int or not 0 <= ti < len(cfg['tiers']):
        return result
    team = st.get('workforce', {}).get('teams', {}).get(cfg['tiers'][ti]['id'])
    if not team:
        return result
    owned = team.get('nodes', [])
    allocation = team.get('allocation', {})
    if 'orientation' in owned:
        rate = 3 if 'production-advanced' in owned else 2.5 if 'production' in owned else 2
        result['production'] = allocation.get('production', 0) * rate
    if 'sales' in owned:
        result['customer'] = allocation.get('sales', 0) * (3 if 'sales-advanced' in owned else 2.5)
    if 'efficiency' in owned:
        result['efficiency'] = min(25, allocation.get('efficiency', 0) * (1.25 if 'efficiency-advanced' in owned else 1))
    return result


def _developed(cfg, st, bid):
    """This business has earned its advanced recipe. The quest engine says so
    with a named flag, so the focus tree no longer depends on a quest id; a
    legacy class keeps answering from its signature quest record."""
    import quest_engine
    if quest_engine.enabled(cfg):
        return quest_engine.has_flag(cfg, st, 'business_developed:' + bid)
    return bool(st.get('businessProgression', {}).get('quests', {})
                .get(bid + '-signature', {}).get('completed'))


def _qualified(cfg, st, b, tier):
    if b.get('lv', 1) >= 3:
        return True
    import quest_engine
    if quest_engine.enabled(cfg):
        return _developed(cfg, st, tier['id'])
    return bool(st.get('businessProgression', {}).get('quests', {})
                .get(tier['id'] + '-plan', {}).get('completed'))


def _nodes(cfg, st, b, tier, team):
    fallback = ('Team Induction', 'Production Practice', 'Production Mastery', 'Customer Service',
                'Customer Expertise', 'Equipment Care', 'Maintenance Expertise')
    names = THEMES.get(tier['id'], fallback)
    effects = (
        'Unlock permanent recruitment and production assignments: +2% base speed per worker.',
        'Production workers give +2.5% base speed each across unlocked products.',
        'Production workers give +3% base speed each across unlocked products.',
        'Unlock sales assignments: +2.5% base walk-in demand per worker.',
        'Sales workers give +3% base walk-in demand each; buyers still need stock.',
        'Unlock maintenance assignments: completed-batch costs fall by 1% per worker.',
        'Maintenance workers reduce completed-batch costs by 1.25% each, up to 25%.',
    )
    if population.enabled(cfg):
        effects = ('Unlock specialist recruitment and further focus advancements.',) + (
            'Worker effects are inactive while the population has no gameplay role.',) * 6
    rows = []
    for index, node_id in enumerate(NODE_IDS):
        advanced = node_id.endswith('-advanced')
        branch = node_id.split('-')[0]
        requires = [] if node_id == 'orientation' else [branch if advanced else 'orientation']
        cost = 0 if node_id == 'orientation' else int(math.floor(tier['upgradeBase'] * (2 if advanced else 1) + .5))
        prestige_cost = (0 if node_id == 'orientation' else 2 if advanced else 1) if cfg.get('businessDesign', {}).get('connectedProgression') else 0
        owned = node_id in team['nodes']
        structural_why = ('Reach production level 3 or complete this business’s planning quest' if node_id == 'orientation' and not _qualified(cfg, st, b, tier) else
                          'Complete the preceding focus first' if any(n not in team['nodes'] for n in requires) else
                          'Complete this business’s signature quest' if advanced and not _developed(cfg, st, tier['id']) else '')
        unlocked = owned or not bool(structural_why)
        why = ('Already completed' if owned else structural_why if structural_why else
               'Not enough Prestige' if st.get('businessProgression', {}).get('prestige', 0) < prestige_cost else
               'Not enough YM' if st.get('cash', 0) < cost else '')
        rows.append(dict(id=node_id, name=names[index], branch=branch, requires=requires,
                         owned=owned, unlocked=unlocked, cost=cost, prestigeCost=prestige_cost,
                         canBuy=not bool(why), why=why, effect=effects[index]))
    return rows


def _hire(cfg, st, tier, team):
    remaining = max(0, team['nextHireAt'] - _now(cfg, st))
    cost = int(math.floor(tier['upgradeBase'] * 2 ** team['hires'] + .5))
    why = ('Complete team induction in the focus tree first' if 'orientation' not in team['nodes'] else
           'All three trainer recruitment places are filled' if team['hires'] >= 3 else
           'Recruitment is cooling down' if remaining > 0 else
           'Not enough YM' if st.get('cash', 0) < cost else '')
    return dict(cost=cost, canHire=not bool(why), why=why, remainingSeconds=remaining,
                nextWorkerCap=(0 if population.enabled(cfg) or team['hires'] >= 3 else 10 + 5 * team['hires']))


def _hq(cfg, st, data):
    hq = data['hq']
    level = hq['level']
    cost = 300 * 3 ** level if level < 3 else None
    count = len({tier['id'] for _, tier in _live(cfg, st)})
    why = ('Academy fully developed' if level >= 3 else
           'Own three businesses to establish Advanced HQ' if level == 0 and count < 3 else
           'Not enough YM' if st.get('cash', 0) < cost else '')
    return dict(level=level, programSlots=level, targets=list(hq['targets']),
                upgrade=dict(cost=cost, canBuy=not bool(why), why=why),
                trainerSeconds=_seconds(cfg, 'trainerTrainingSeconds', 600))


def payload(cfg, st):
    if not enabled(cfg):
        return dict(enabled=False, teams=[], hq=None)
    data = ensure(cfg, st)
    worker_seconds = _seconds(cfg, 'workerTrainingSeconds', 300)
    trainer_seconds = _seconds(cfg, 'trainerTrainingSeconds', 600)
    hq = _hq(cfg, st, data)
    rows = []
    for b, tier in _live(cfg, st):
        team = data['teams'].get(tier['id'], _empty_team())
        paused = bool(b.get('paused'))
        supported = tier['id'] in hq['targets'][:hq['programSlots']]
        worker_running = not paused and team['trainers'] > 0 and team['workers'] < _worker_cap(team)
        trainer_running = not paused and supported and team['hires'] > 0 and team['trainers'] < _trainer_cap(team)
        rows.append(dict(buildingId=b.get('buildingId'), typeId=tier['id'], name=tier['name'],
                         hires=team['hires'], trainers=team['trainers'], trainerCap=_trainer_cap(team),
                         workers=team['workers'], workerCap=_worker_cap(team),
                         allocation=dict(team['allocation']), trainingBranch=team['trainingBranch'],
                         workerProgress=team['workerWork'] / worker_seconds,
                         trainerProgress=team['trainerWork'] / trainer_seconds,
                         nextWorkerSeconds=(worker_seconds - team['workerWork']) / team['trainers'] if worker_running else None,
                         nextTrainerSeconds=trainer_seconds - team['trainerWork'] if trainer_running else None,
                         hire=_hire(cfg, st, tier, team), nodes=_nodes(cfg, st, b, tier, team),
                         effects=bonuses(cfg, st, b), paused=paused, hqSupported=supported))
        if population.enabled(cfg):
            rows[-1].update(populationEnabled=True, workers=0, workerCap=0,
                            allocation=dict.fromkeys(BRANCHES, 0), workerProgress=0,
                            nextWorkerSeconds=None)
    return dict(enabled=True, teams=rows, hq=hq,
                population=population.summary(cfg, st),
                prestigeAvailable=st.get('businessProgression', {}).get('prestige', 0),
                prestigeCostsEnabled=bool(cfg.get('businessDesign', {}).get('connectedProgression')),
                recruitmentCooldownSeconds=_seconds(cfg, 'hireCooldownSeconds', 1800),
                workerTrainingSeconds=worker_seconds)


def _reject(why):
    return dict(ok=False, why=why)


def _apply(cfg, st, body):
    data = ensure(cfg, st)
    action = body.get('action')
    if action == 'hq_upgrade':
        quote = _hq(cfg, st, data)['upgrade']
        if not quote['canBuy']:
            return _reject(quote['why'])
        st['cash'] -= quote['cost']
        data['hq']['level'] += 1
        data['hq']['spent'] = data['hq'].get('spent', 0) + quote['cost']
        return dict(ok=True, action=action, cost=quote['cost'], level=data['hq']['level'])
    if action not in ('hire', 'focus', 'allocate', 'hq_assign'):
        return _reject('Choose a workforce action')
    bid = body.get('buildingId')
    matches = [(b, t) for b, t in _live(cfg, st) if isinstance(bid, str) and bid and b.get('buildingId') == bid]
    if len(matches) != 1:
        return _reject('Choose a currently owned business')
    b, tier = matches[0]
    team = data['teams'].setdefault(tier['id'], _empty_team())
    receipt = dict(ok=True, action=action, buildingId=b['buildingId'], typeId=tier['id'])
    if action == 'hire':
        quote = _hire(cfg, st, tier, team)
        if not quote['canHire']:
            return _reject(quote['why'])
        st['cash'] -= quote['cost']
        team['spent'] += quote['cost']
        team['hires'] += 1
        team['trainers'] += 1
        team['nextHireAt'] = _now(cfg, st) + _seconds(cfg, 'hireCooldownSeconds', 1800)
        operations = st.get('businessOperations')
        if isinstance(operations, dict):
            operations['totalStaffCosts'] = operations.get('totalStaffCosts', 0) + quote['cost']
            operations['staffHired'] = operations.get('staffHired', 0) + 1
        receipt.update(cost=quote['cost'], hires=team['hires'])
    elif action == 'focus':
        node = next((n for n in _nodes(cfg, st, b, tier, team) if n['id'] == body.get('nodeId')), None)
        if not node:
            return _reject('Choose a focus in this business’s tree')
        if not node['canBuy']:
            return _reject(node['why'])
        if node['prestigeCost']:
            # Initialize earned history before spending; expansion qualifications
            # use lifetime earnings and survive a focus purchase.
            import business_progression
            progression = business_progression.ensure(cfg, st)
            progression['prestige'] -= node['prestigeCost']
            progression['prestigeSpent'] = progression.get('prestigeSpent', 0) + node['prestigeCost']
        st['cash'] -= node['cost']
        team['spent'] += node['cost']
        team['nodes'].append(node['id'])
        import quest_engine
        quest_engine.record_action(cfg, st, 'focus_node')
        receipt.update(cost=node['cost'], prestigeCost=node['prestigeCost'], nodeId=node['id'])
    elif action == 'allocate':
        if population.enabled(cfg):
            return _reject('Workers have no assignments or gameplay effects yet')
        allocation = body.get('allocation')
        if not isinstance(allocation, dict) or set(allocation) != set(BRANCHES):
            return _reject('Provide production, sales and efficiency worker counts')
        if any(type(count) is not int or count < 0 for count in allocation.values()):
            return _reject('Worker assignments must be non-negative whole numbers')
        if sum(allocation.values()) > team['workers']:
            return _reject('Assign each trained worker only once')
        if any(count and not _unlocked(team, branch) for branch, count in allocation.items()):
            return _reject('Unlock that branch in the focus tree first')
        branch = body.get('trainingBranch', team['trainingBranch'])
        if not isinstance(branch, str) or branch not in BRANCHES or not _unlocked(team, branch):
            return _reject('Choose an unlocked training branch')
        team['allocation'] = dict(allocation)
        team['trainingBranch'] = branch
        receipt.update(allocation=dict(allocation), trainingBranch=branch)
    elif action == 'hq_assign':
        selected = body.get('enabled')
        if type(selected) is not bool:
            return _reject('Choose whether HQ should support this business')
        targets = data['hq']['targets']
        if selected:
            if not team['hires']:
                return _reject('Recruit a permanent trainer at this business first')
            if tier['id'] not in targets:
                if len(targets) >= data['hq']['level']:
                    return _reject('No free HQ programs; release a business or upgrade HQ')
                targets.append(tier['id'])
        elif tier['id'] in targets:
            targets.remove(tier['id'])
        receipt['enabled'] = selected
    return receipt


def act(cfg, st, body):
    """Reject malformed or unaffordable commands without changing any state."""
    if not enabled(cfg):
        return _reject('Permanent teams are not enabled for this class')
    if not isinstance(body, dict):
        return _reject('Choose a workforce action')
    draft = copy.deepcopy(st)
    result = _apply(cfg, draft, body)
    if result['ok']:
        # Keep building references used by the caller valid; actions only edit
        # workforce/cash, plus clearing a legacy shift during initial migration.
        st['cash'] = draft['cash']
        st['workforce'] = draft['workforce']
        if population.enabled(cfg):
            st['workerPopulation'] = draft['workerPopulation']
        if result['action'] == 'focus' and result.get('prestigeCost'):
            st['businessProgression'] = draft['businessProgression']
        if result['action'] == 'hire' and isinstance(st.get('businessOperations'), dict):
            for key in ('totalStaffCosts', 'staffHired'):
                st['businessOperations'][key] = draft['businessOperations'][key]
        for original, updated in zip(st.get('b', []), draft.get('b', [])):
            if original.get('staff') is not None and updated.get('staff') is None:
                original['staff'] = None
        result['kind'] = 'workforce'
        result['message'] = {'hire': 'Permanent trainer recruited. Funded places train automatically.',
                             'focus': 'Business focus completed.',
                             'allocate': 'Worker assignments updated.',
                             'hq_upgrade': 'Advanced HQ academy upgraded.',
                             'hq_assign': 'HQ training programs updated.'}[result['action']]
        if population.enabled(cfg) and result['action'] == 'hire':
            result['message'] = 'HQ specialist recruited. Worker population is unchanged.'
    return result
