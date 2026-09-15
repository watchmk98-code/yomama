"""Persistent batch-planning workshop. All time and rewards are server-owned.

Workshop supplies and practice coins are isolated from the town. Completion
grants a chosen roastery recipe improvement, once. Supply
catches up arithmetically when no jobs remain. Existing workshops stay open.
"""
import copy

SUPPLY = {'beans': 15, 'eggs': 30, 'honey': 60}
RECIPES = {
    'coffee': dict(inputs={'beans': 2}, output=2, seconds=30),
    'pastry': dict(inputs={'eggs': 1, 'honey': 1}, output=1, seconds=45),
}
ORDERS = [
    [('first', 'First customers', {'coffee': 2}, 20)],
    [('coffee', 'Coffee crew', {'coffee': 4}, 40),
     ('pastry', 'Sweet tooth', {'pastry': 2}, 60)],
    [('mixed', 'Breakfast for two', {'coffee': 2, 'pastry': 2}, 80)],
    [],
    [('final', 'The breakfast club', {'coffee': 4, 'pastry': 4}, 0)],
    [],
]

SPECIALIZATIONS = {
    'coffee': dict(name='Coffee', townRecipe='Espresso', goodId='roastery_espresso_shots'),
    'pastry': dict(name='Pastry', townRecipe='Pastries', goodId='roastery_pastries'),
}


def _locked(st, cfg):
    """Use completed ownership in the class config, never a browser intention.

    The workshop also runs as a standalone simulation without town ownership.
    A town always needs its configuration to resolve the roastery's tier; a
    missing configuration fails closed rather than assuming a fixed tier index.
    Old started/completed workshops are grandfathered without changing state.
    """
    if st.get('breakfastEvent') is not None:
        return False
    town = st.get('modelVersion') == 4 or 'b' in st or 'tierOf' in st or cfg is not None
    if not town:
        return False
    tiers = (cfg or {}).get('tiers', [])
    return not any(type(ti) is int and 0 <= ti < len(tiers)
                   and tiers[ti].get('id') == 'roastery'
                   for ti in st.get('tierOf', []))


def _description(st, cfg):
    e = st.get('breakfastEvent') or {}
    selected = SPECIALIZATIONS.get(e.get('upgrade'))
    perk = (selected['townRecipe'] + ' +25% of base production speed at your roastery'
            if selected else 'Choose espresso or pastries for +25% of base production speed at your roastery')
    locked = _locked(st, cfg)
    return dict(
        name='Breakfast Club · recipe workshop',
        locked=locked,
        unlockText='Open the roastery to unlock this workshop.' if locked else '',
        purpose='Plan batches with one cooking station and one queued batch. Choose a recipe improvement to bring back to your roastery.',
        suppliesLabel='Workshop supplies',
        coinsLabel='Practice coins',
        suppliesDescription='Separate from town inventory. Ingredients refill up to 12; only batches already started or queued can finish while you are away.',
        coinsDescription='Earned and spent only in this workshop. They never spend or become town cash.',
        reward=0,
        townPerk=perk,
        rewardDescription=('Earned once: ' + perk + '.' if e.get('stage') == 5 else
                           'Complete four orders to earn a permanent recipe improvement: ' + perk + '.'),
        specializations={name: dict(choice,
            townPerk=choice['townRecipe'] + ' +25% of base production speed at your roastery',
            workshopPerk='Double batch output and ingredients; cooking time stays the same.')
            for name, choice in SPECIALIZATIONS.items()},
    )


def recipe(e, name):
    r = copy.deepcopy(RECIPES[name])
    if e['upgrade'] == name:
        r['inputs'] = {k: v * 2 for k, v in r['inputs'].items()}
        r['output'] *= 2
    return r


def enough(e, inputs):
    return all(e['stock'][k] >= v for k, v in inputs.items())


def _start_queued(e, at):
    if e['active'] or not e['queued']:
        return
    name = e['queued']['recipe']
    r = recipe(e, name)
    if enough(e, r['inputs']):
        for k, v in r['inputs'].items():
            e['stock'][k] -= v
        e['active'] = dict(e['queued'], ends=at + r['seconds'], output=r['output'])
        e['queued'] = None


def advance(st, now):
    e = st.get('breakfastEvent')
    if not e or e['stage'] == 5 or now <= e['last']:
        return
    at = e['last']
    while at < now:
        _start_queued(e, at)
        end = min(now, e['active']['ends']) if e['active'] else now
        if e['queued'] and not e['active']:
            end = min(end, e['started'] + ((at - e['started']) // 15 + 1) * 15)
        for key, period in SUPPLY.items():
            added = (end - e['started']) // period - (at - e['started']) // period
            e['stock'][key] = min(12, e['stock'][key] + added)
        at = end
        if e['active'] and e['active']['ends'] <= at:
            job = e['active']
            e['stock'][job['recipe']] += job['output']
            e['active'] = None
        _start_queued(e, at)
    e['last'] = now


def payload(st, now, cfg=None):
    e = st.get('breakfastEvent')
    description = _description(st, cfg)
    if not e:
        return dict(description, status='new')
    p = copy.deepcopy(e)
    p.update(description)
    p['status'] = 'done' if e['stage'] == 5 else 'playing'
    p['elapsed'] = (e.get('finished', now) - e['started'])
    p['orders'] = [dict(id=key, name=name, needs=needs, coins=coins, ready=enough(e, needs))
                   for key, name, needs, coins in ORDERS[e['stage']]]
    p['recipes'] = {name: dict(recipe(e, name), ready=enough(e, recipe(e, name)['inputs']))
                    for name in RECIPES}
    p['supply'] = {k: period - (now - e['started']) % period for k, period in SUPPLY.items()}
    if p['active']:
        p['active']['remaining'] = max(0, p['active']['ends'] - now)
    return p


def act(st, now, body, cfg=None):
    action = body.get('action')
    fail = lambda why: dict(ok=False, why=why)
    if action not in ('start', 'make', 'cancel', 'deliver', 'upgrade'):
        return fail('Unknown event action')
    if action == 'start':
        if 'breakfastEvent' not in st:
            if _locked(st, cfg):
                return fail('Open the roastery to unlock this workshop.')
            st['breakfastEvent'] = dict(started=now, last=now, stage=0, coins=0,
                stock=dict(beans=4, eggs=2, honey=1, coffee=0, pastry=0),
                active=None, queued=None, upgrade=None, serial=0)
        return dict(ok=True, kind='breakfast', message='Recipe workshop is open')
    advance(st, now)
    e = st.get('breakfastEvent')
    if not e or e['stage'] == 5:
        return fail('This event is not running')
    message = ''
    if action == 'make':
        name = body.get('recipe')
        if not isinstance(name, str) or name not in RECIPES:
            return fail('Unknown recipe')
        if e['queued']:
            return fail('Queue full')
        if e['stock'][name] >= 12:
            return fail('Serve your finished stock first')
        e['serial'] += 1
        e['queued'] = dict(id=e['serial'], recipe=name)
        _start_queued(e, now)
        message = 'Added to the kitchen'
    elif action == 'cancel':
        job_id = body.get('jobId')
        if type(job_id) is not int or not e['queued'] or e['queued']['id'] != job_id:
            return fail('That batch is no longer queued')
        e['queued'] = None
        message = 'Queue cleared'
    elif action == 'upgrade':
        name = body.get('recipe')
        if e['stage'] != 3 or not isinstance(name, str) or name not in RECIPES or e['coins'] < 100:
            return fail('Complete the breakfast order first')
        e['coins'] -= 100
        e['upgrade'] = name
        e['stage'] = 4
        message = 'Bigger batches unlocked'
    elif action == 'deliver':
        order = next((o for o in ORDERS[e['stage']] if o[0] == body.get('orderId')), None)
        if not order:
            return fail('That order is no longer available')
        if not enough(e, order[2]):
            return fail('Make the missing goods first')
        for k, v in order[2].items():
            e['stock'][k] -= v
        e['coins'] += order[3]
        e['stage'] += 1
        message = 'Served! +' + str(order[3]) + ' Practice coins'
        if e['stage'] == 5:
            e['coins'] = 0
            e['finished'] = now
            e['active'] = e['queued'] = None
            message = 'Workshop complete! ' + _description(st, cfg)['townPerk']
    return dict(ok=True, kind='breakfast', message=message)
