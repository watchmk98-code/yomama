"""Small, persistent cooking event. All time and rewards are server-owned.

Event supplies and coins are isolated from the town. Only completion grants
town materials, once. Supply catches up arithmetically when no jobs remain.
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


def payload(st, now):
    e = st.get('breakfastEvent')
    if not e:
        return dict(status='new', reward=5)
    p = copy.deepcopy(e)
    p['status'] = 'done' if e['stage'] == 5 else 'playing'
    p['reward'] = 5
    p['townPerk'] = ('Espresso' if e.get('upgrade') == 'coffee' else 'Pastries') + ' +25% base production speed at your roastery'
    p['elapsed'] = (e.get('finished', now) - e['started'])
    p['orders'] = [dict(id=key, name=name, needs=needs, coins=coins, ready=enough(e, needs))
                   for key, name, needs, coins in ORDERS[e['stage']]]
    p['recipes'] = {name: dict(recipe(e, name), ready=enough(e, recipe(e, name)['inputs']))
                    for name in RECIPES}
    p['supply'] = {k: period - (now - e['started']) % period for k, period in SUPPLY.items()}
    if p['active']:
        p['active']['remaining'] = max(0, p['active']['ends'] - now)
    return p


def act(st, now, body):
    action = body.get('action')
    fail = lambda why: dict(ok=False, why=why)
    if action not in ('start', 'make', 'cancel', 'deliver', 'upgrade'):
        return fail('Unknown event action')
    if action == 'start':
        if 'breakfastEvent' not in st:
            st['breakfastEvent'] = dict(started=now, last=now, stage=0, coins=0,
                stock=dict(beans=4, eggs=2, honey=1, coffee=0, pastry=0),
                active=None, queued=None, upgrade=None, serial=0)
        return dict(ok=True, kind='breakfast', message='Breakfast is open')
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
        message = 'Served! +' + str(order[3]) + ' event coins'
        if e['stage'] == 5:
            st['materials'] += 5
            e['coins'] = 0
            e['finished'] = now
            e['active'] = e['queued'] = None
            message = 'Breakfast complete! +5 materials and a permanent roastery recipe upgrade'
    return dict(ok=True, kind='breakfast', message=message)
