"""Production economy invariants; runnable with pytest or plain Python.

These tests check accounting and player choices, not whether a game is fun.
The v3 reference/golden tests remain in test_economy.py unchanged.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_economy as E


def config():
    return copy.deepcopy(E.load_config())


def replay(cfg, state, count):
    start = state['tick']
    world = E.new_class(cfg, start + count)
    E.advance_class(cfg, world, [state], start, start + count)
    return state


def goods(cfg):
    return {good['id']: good for tier in cfg['tiers'] for good in tier['goods']}


def building(tier=0):
    return dict(tier=tier, lv=1, auto=1, sales=1, storage=1, reserve=False)


def sole_product(cfg, tier, good):
    """Keep one producer so conservation assertions have no unrelated flows."""
    cfg['tiers'][tier]['goods'] = [copy.deepcopy(good)]
    state = E.new_state(cfg)
    state['b'] = [building(tier)]
    state['tierOf'] = [tier]
    state['inventory'] = {key: 0 for key in goods(cfg)}
    state['productionWork'] = {}
    state['salesWork'] = {}
    return state


def money_and_stock_are_valid(state):
    for field in ('cash', 'book', 'taxPaid'):
        assert type(state[field]) is int and state[field] >= 0, (field, state[field])
    for key, quantity in state['inventory'].items():
        assert type(quantity) is int and quantity >= 0, (key, quantity)
    for field in ('productionWork', 'salesWork'):
        assert all(type(x) is int and x >= 0 for x in state[field].values()), field


def test_first_sale_and_affordable_first_choices():
    cfg = config()
    cfg['businessDesign']['groupProjectsEnabled'] = True
    state = E.new_state(cfg)
    assert state['cash'] == 0 and len(state['b']) == 1
    upgrade_price = E.upgrade_cost(cfg, state, 0, 'production')
    replay(cfg, state, int(60 / cfg['global']['tick']))
    assert state['cash'] > 0, 'A new player should earn a first sale within one minute.'
    replay(cfg, state, int(180 / cfg['global']['tick']) - state['tick'])
    assert state['cash'] >= upgrade_price, 'First upgrade should be affordable within three minutes.'
    # Real ordinary shipments qualify the separate construction achievement.
    # The first tomato order is deliberately preserved from the opening deal.
    while not E.town_projects.check_claim(cfg, state, 'farm_neighbors')['ok']:
        for _ in range(100):
            order = state['offers'][0]
            if any(n['goodId'] == 'farm_tomatoes' for n in order['requirements']):
                break
            assert E.replace_order(cfg, state, 0, order['id'])['ok']
        assert E.commit_order(cfg, state, 0, order['id'], True)['ok']
        while not E.fulfill_order(cfg, state, 0, order['id'])['ok']:
            assert state['tick'] < int(600 / cfg['global']['tick'])
            replay(cfg, state, 1)
    assert E.claim_group_project(cfg, state, 'farm_neighbors')['ok']
    assert E.expansion_quote(cfg, state, 1)['cost'] == 0
    assert E.expand(cfg, state, 1, state['tick'])['ok'], 'The opening delivery should fund a second business within ten minutes.'


def test_catalog_has_resolvable_profitable_recipes_and_finite_upgrade_caps():
    cfg = config()
    catalog = goods(cfg)
    assert len(catalog) == sum(len(tier['goods']) for tier in cfg['tiers']), 'Good IDs must be unique.'
    resolved = set()
    for tier in cfg['tiers']:
        for product in tier['goods']:
            assert type(product['unitPrice']) is int and product['unitPrice'] > 0
            assert type(product['cycleTicks']) is int and product['cycleTicks'] > 0
            costs = 0
            for ingredient in product.get('inputs', []):
                assert ingredient['goodId'] in resolved, 'Chains must be reachable without circular inputs.'
                assert type(ingredient['quantity']) is int and ingredient['quantity'] > 0
                costs += catalog[ingredient['goodId']]['unitPrice'] * ingredient['quantity']
            assert product['unitPrice'] > costs, 'Processing should add value before capacity opportunity costs.'
            resolved.add(product['id'])
    assert 1 < cfg['global']['maxLevel'] <= 50


def test_raw_production_is_conserved_across_automatic_sales():
    cfg = config()
    product = next(g for g in cfg['tiers'][0]['goods'] if not g.get('inputs'))
    state = sole_product(cfg, 0, product)
    ticks = product['cycleTicks'] * 20
    replay(cfg, state, ticks)
    sold, remainder = divmod(state['cash'], product['unitPrice'])
    assert remainder == 0
    assert sold + state['inventory'][product['id']] == 20
    assert 0 < sold < 20, 'Starter demand should sell goods while leaving a manageable surplus.'


def test_customer_fraction_and_upgrades_are_not_rounded_to_one_sale_per_tick():
    cfg = config()
    product = next(g for g in cfg['tiers'][0]['goods'] if not g.get('inputs') and g['cycleTicks'] == 1)
    state = sole_product(cfg, 0, product)
    state['inventory'][product['id']] = 70
    replay(cfg, state, 100)
    assert state['cash'] == 65 * product['unitPrice'], '65% demand must sell exactly 65 units in 100 ticks.'
    upgraded = sole_product(cfg, 0, product)
    upgraded['b'][0].update(lv=12, sales=12, auto=12)
    upgraded['inventory'][product['id']] = 70
    replay(cfg, upgraded, 100)
    expected = (65 * (100 + 35 * 11) * 100) // 10000
    assert upgraded['cash'] == expected * product['unitPrice']
    assert expected > 100, 'Customer upgrades must allow more than one unit per tick.'


def test_reserve_prevents_retail_sales_and_can_be_released():
    cfg = config()
    product = next(g for g in cfg['tiers'][0]['goods'] if not g.get('inputs'))
    state = sole_product(cfg, 0, product)
    assert E.set_reserve(cfg, state, 0, True)['ok']
    replay(cfg, state, product['cycleTicks'] * 12)
    assert state['cash'] == 0 and state['inventory'][product['id']] == 12
    assert E.set_reserve(cfg, state, 0, False)['ok']
    replay(cfg, state, product['cycleTicks'] * 3)
    assert state['cash'] > 0
    money_and_stock_are_valid(state)


def test_former_recipe_produces_without_suppliers_and_never_consumes_their_stock():
    cfg = config()
    owners = {g['id']: i for i, t in enumerate(cfg['tiers']) for g in t['goods']}
    tier, product = next((i, g) for i, t in enumerate(cfg['tiers']) for g in t['goods']
                         if g.get('inputs') and all(owners[n['goodId']] != i for n in g['inputs']))
    state = sole_product(cfg, tier, product)
    state['cash'] = 1000  # Isolate stock conservation from the operating budget.
    state['b'][0]['reserve'] = True
    replay(cfg, state, product['cycleTicks'] * 10)
    assert state['inventory'][product['id']] == 10 * product['quantity']
    for ingredient in product['inputs']:
        state['inventory'][ingredient['goodId']] = ingredient['quantity']
    replay(cfg, state, product['cycleTicks'] * 3)
    assert state['inventory'][product['id']] == 13 * product['quantity']
    for ingredient in product['inputs']:
        assert state['inventory'][ingredient['goodId']] == ingredient['quantity']
    money_and_stock_are_valid(state)


def test_obsolete_processing_toggle_cannot_silently_stop_products():
    cfg = config()
    state = E.new_state(cfg)
    state['b'].append(building(2))
    state['tierOf'].append(2)
    owners = {g['id']: i for i, tier in enumerate(cfg['tiers']) for g in tier['goods']}
    pastry = next(g for g in cfg['tiers'][2]['goods'] if g.get('inputs')
                  and all(owners[n['goodId']] != 2 for n in g['inputs']))
    before=copy.deepcopy(state)
    assert not E.set_processing(cfg, state, 1, False)['ok']
    assert state==before
    assert all(n['goodId'] not in E.chain_reservations(cfg, state) for n in pastry['inputs'])
    state['cash']=1000
    state['b'][1]['processing']=False  # Old saved flag cannot stop new production.
    state['b'][1]['reserve'] = True
    replay(cfg, state, pastry['cycleTicks'] * 3)
    assert state['inventory'].get(pastry['id'], 0) > 0
    money_and_stock_are_valid(state)


def test_flow_forecast_is_independent_of_former_supplier_and_never_credits_cash():
    cfg = config()
    state = E.new_state(cfg)
    state['b'].append(building(2))
    state['tierOf'].append(2)
    state['b'][1]['lv'] = 12
    owners = {g['id']: i for i, tier in enumerate(cfg['tiers']) for g in tier['goods']}
    pastry = next(g for g in cfg['tiers'][2]['goods'] if g.get('inputs')
                  and all(owners[n['goodId']] != 2 for n in g['inputs']))
    scarce = max(pastry['inputs'], key=lambda n: goods(cfg)[n['goodId']]['cycleTicks'])['goodId']
    rates = E.flow_rates(cfg, state)
    assert rates[pastry['id']]['production'] > rates[scarce]['production']
    assert rates[scarce]['retail'] > 0, 'Farm goods remain available for its own customers.'
    cash = state['cash']
    assert E.flow_rates(cfg, state) == rates
    assert state['cash'] == cash, 'A forecast never issues money.'
    state['b'][0]['lv'] += 1
    assert E.flow_rates(cfg, state)[pastry['id']] == rates[pastry['id']]
    assert E.flow_rates(cfg, state)[scarce]['production'] > rates[scarce]['production']


def test_random_actions_preserve_integer_nonnegative_accounting_and_capacities():
    cfg = config()
    state = E.new_state(cfg)
    state['cash'] = 10**8
    rnd = random.Random(412)
    for step in range(2000):
        E.on_login(cfg, state, state['tick'])
        replay(cfg, state, rnd.randint(1, 9))
        slot = rnd.randrange(len(state['b']))
        action = rnd.randrange(7)
        if action == 0:
            E.buy_upgrade(cfg, state, slot, rnd.choice(('production', 'sales', 'storage')))
        elif action == 1:
            E.set_reserve(cfg, state, slot, rnd.choice((True, False)))
        elif action == 2:
            E.set_processing(cfg, state, slot, rnd.choice((True, False)))
        elif action == 3:
            E.sell_one(cfg, state, slot)
        elif action in (4, 5):
            index = rnd.randrange(3)
            order = state['offers'][index]
            operation = E.fulfill_order if action == 4 else E.replace_order
            operation(cfg, state, index, order['id'])
        else:
            frontier = E.expand_options(cfg, state)
            if frontier:
                E.expand(cfg, state, rnd.choice(frontier), state['tick'])
        money_and_stock_are_valid(state)
        assert type(state['materials']) is int and state['materials'] >= 0
        assert len(state['tierOf']) == len(set(state['tierOf']))
        for i, tier in enumerate(state['tierOf']):
            assert sum(state['inventory'].get(g['id'], 0) for g in cfg['tiers'][tier]['goods']) <= E.warehouse_cap(cfg, state)[i]


def test_full_reserved_storage_does_not_permanently_starve_a_product():
    cfg = config()
    state = E.new_state(cfg)
    state['cash'] = 10000  # Reserved stock earns no cash to cover production.
    state['b'][0]['reserve'] = True
    replay(cfg, state, 1200)
    products = cfg['tiers'][0]['goods']
    last = products[-1]['id']
    assert all(state['inventory'].get(g['id'], 0) > 0 for g in products)
    state['inventory'][last] = 0
    replay(cfg, state, 600)
    assert state['inventory'][last] >= 8, 'A full tomato bin must not permanently prevent the honey needed by an order.'
    assert sum(state['inventory'].get(g['id'], 0) for g in products) <= E.warehouse_cap(cfg, state)[0]
    for g in products:
        assert state['productionWork'][g['id']] <= g['cycleTicks'] * 100
    money_and_stock_are_valid(state)


def test_delivery_shortage_is_atomic_and_stale_id_cannot_pay_again():
    cfg = config()
    state = E.new_state(cfg)
    index = 1
    order = copy.deepcopy(state['offers'][index])
    assert len(order['requirements']) >= 2
    for need in order['requirements']:
        state['inventory'][need['goodId']] = need['quantity']
    missing = order['requirements'][-1]
    state['inventory'][missing['goodId']] -= 1
    before = copy.deepcopy(state)
    assert not E.fulfill_order(cfg, state, index, order['id'])['ok']
    assert state == before, 'A failed delivery must not consume partial goods or issue rewards.'
    state['inventory'][missing['goodId']] += 1
    before = copy.deepcopy(state)
    assert E.fulfill_order(cfg, state, index, order['id'])['ok']
    assert state['cash'] == before['cash'] + order['reward']
    assert state['materials'] == before['materials'] + order['materials']
    assert state['cStats']['done'] == before['cStats']['done'] + 1
    assert all(state['inventory'][n['goodId']] == 0 for n in order['requirements'])
    assert state['offers'][index]['id'] != order['id']
    after = copy.deepcopy(state)
    assert not E.fulfill_order(cfg, state, index, order['id'])['ok']
    assert not E.replace_order(cfg, state, index, order['id'])['ok']
    assert state == after
    money_and_stock_are_valid(state)


def test_order_replacement_is_free_and_only_targets_owned_unlocked_products():
    cfg = config()
    state = E.new_state(cfg)
    state['tierOf'] = [0, 5]
    state['b'] = [building(0), building(5)]
    state['offers'] = None
    E.offer_contracts(cfg, state, 0)
    owner = {g['id']: i for i, t in enumerate(cfg['tiers']) for g in t['goods']}
    for iteration in range(60):
        for i, order in enumerate(list(state['offers'][:2])):
            for need in order['requirements']:
                assert owner[need['goodId']] in state['tierOf']
                assert E.business_progression.product_unlocked(cfg,state,need['goodId'])
            old_cash, old_materials = state['cash'], state['materials']
            assert E.replace_order(cfg, state, i, order['id'])['ok']
            assert state['cash'] == old_cash and state['materials'] == old_materials


def test_order_rotation_can_reach_every_owned_product():
    cfg = config()
    state = E.new_state(cfg)
    state['tierOf'] = list(range(7))
    state['b'] = [building(i) for i in state['tierOf']]
    # This catalog-rotation scenario represents an established town whose
    # learned products survive migration; locked-product exclusion is tested
    # separately in the new progression suite.
    state.pop('businessProgression', None)
    state = E.migrate_state(cfg, state)
    state['offers'] = None
    E.offer_contracts(cfg, state, 0)
    expected = {g['id'] for t in cfg['tiers'][:7] for g in t['goods']}
    seen = set()
    for iteration in range(len(expected) * 3):
        order = state['offers'][0]
        seen.update(n['goodId'] for n in order['requirements'])
        assert E.replace_order(cfg, state, 0, order['id'])['ok']
    assert seen == expected, 'Focusing one delivery slot must not trap it in a tiny repeating subset of products.'


def test_bulk_clear_is_discounted_cannot_repeat_and_has_no_ingredient_buffer():
    cfg = config()
    state = E.new_state(cfg)
    state['tierOf'] = [0, 2]
    state['b'] = [building(0), building(2)]
    state['inventory'] = {g['id']: 10 for g in cfg['tiers'][0]['goods']}
    protected = E.chain_reservations(cfg, state)
    assert protected=={}
    expected = sum((10 - protected.get(g['id'], 0)) * g['unitPrice'] for g in cfg['tiers'][0]['goods'])
    receipt = E.sell_one(cfg, state, 0)
    assert receipt['ok'] and receipt['net'] == expected * cfg['production']['clearStockPercent'] // 100
    assert all(state['inventory'][g['id']] == protected.get(g['id'], 0) for g in cfg['tiers'][0]['goods'])
    before = copy.deepcopy(state)
    assert not E.sell_one(cfg, state, 0)['ok']
    assert state == before


def test_no_automatic_upgrade_or_expansion_spending():
    cfg = config()
    state = E.new_state(cfg)
    state['cash'] = 10**8
    original_buildings = copy.deepcopy(state['b'])
    replay(cfg, state, E.ticks_per_hour(cfg))
    assert state['b'] == original_buildings
    assert state['cash'] >= 10**8 and state['build'] is None
    assert E.expand(cfg, state, 1, state['tick'])['ok']
    paid_cash = state['cash']
    old_levels = [(b['lv'], b['sales'], b['storage']) for b in state['b']]
    replay(cfg, state, E.ticks_per_hour(cfg))
    assert len(state['b']) == 2 and state['build'] is None
    assert [(b['lv'], b['sales'], b['storage']) for b in state['b'][:-1]] == old_levels
    assert state['cash'] >= paid_cash and not state.get('queue')


def test_replay_is_identical_across_json_reload_and_chunk_sizes():
    cfg = config()
    continuous = E.new_state(cfg, seed=19)
    continuous['cash'] = 5000
    assert E.expand(cfg, continuous, 1, 0)['ok']
    segmented = E.State(json.loads(json.dumps(continuous)))
    replay(cfg, continuous, 3000)
    rnd = random.Random(8)
    while segmented['tick'] < 3000:
        replay(cfg, segmented, min(rnd.randint(1,117), 3000 - segmented['tick']))
        segmented = E.State(json.loads(json.dumps(segmented)))
    assert continuous == segmented
    money_and_stock_are_valid(continuous)


def test_bad_upgrade_and_reserve_requests_do_not_mutate_state():
    cfg = config()
    state = E.new_state(cfg)
    for slot in (-1, 999, True, '0', None):
        before = copy.deepcopy(state)
        assert not E.buy_upgrade(cfg, state, slot, 'production')['ok']
        assert state == before
        assert not E.set_reserve(cfg, state, slot, True)['ok']
        assert state == before
    before = copy.deepcopy(state)
    assert not E.buy_upgrade(cfg, state, 0, 'unlimited-money')['ok']
    assert state == before
    assert not E.buy_upgrade(cfg, state, 0, 'production')['ok']
    assert state == before


def test_legacy_migration_preserves_owned_value_and_is_idempotent():
    import economy as legacy
    cfg = config()
    old = legacy.new_state(legacy.load_config())
    old.update(cash=1234, book=4567, taxPaid=89, tierOf=[0, 3],
               b=[dict(lv=25, auto=2, tier=0), dict(lv=7, auto=1, tier=3)],
               pend={'0': 123, '1': 456}, tick=100,
               build=dict(t=200, i=4), queue=[5])
    snapshot = copy.deepcopy(old)
    migrated = E.migrate_state(cfg, old)
    assert migrated['modelVersion'] == 4
    assert migrated['cash'] == snapshot['cash'] + sum(snapshot['pend'].values())
    assert migrated['book'] == snapshot['book']
    assert migrated['taxPaid'] == snapshot['taxPaid']
    assert migrated['tierOf'] == snapshot['tierOf']
    assert migrated['build'] == snapshot['build'] and migrated['queue'] == snapshot['queue']
    assert not any(migrated['inventory'].values())
    first = copy.deepcopy(migrated)
    assert E.migrate_state(cfg, migrated) == first
    assert E.migrate_state(cfg, E.State(json.loads(json.dumps(migrated)))) == first
    money_and_stock_are_valid(migrated)


def test_migration_retains_an_already_earned_legacy_trading_licence():
    import economy as legacy
    cfg = config()
    old = legacy.new_state(legacy.load_config())
    old['keepPercent'] = 65
    migrated = E.migrate_state(cfg, old)
    assert migrated['keepPercent'] == 65 and E.gate_open(cfg, migrated)
    for invalid in (None, True, '65', -1, 101):
        old = legacy.new_state(legacy.load_config())
        old['keepPercent'] = invalid
        migrated = E.migrate_state(cfg, old)
        assert not E.gate_open(cfg, migrated), invalid


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    if sys.argv[1:]:
        tests = [(n, f) for n, f in tests if any(p in n for p in sys.argv[1:])]
    failures = 0
    for name, fn in tests:
        started = time.perf_counter()
        try:
            fn()
            print(f'  ok   {name} ({time.perf_counter() - started:.2f}s)')
        except Exception:
            failures += 1
            print(f'  FAIL {name}')
            traceback.print_exc()
    print(f'\n{len(tests) - failures}/{len(tests)} passed')
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
