"""Delivery variety must stay reachable, reproducible, and possible to produce."""
from __future__ import annotations

import collections
import copy
import json

import pytest

import production_economy as E
import business_progression as P
from delivery_recipes import ORDER_RECIPES


def town(cfg, tiers=None):
    state = E.new_state(cfg, seed=31)
    state['tierOf'] = list(range(len(cfg['tiers']))) if tiers is None else list(tiers)
    state['b'] = [E._building(tier) for tier in state['tierOf']]
    # These catalog-coverage fixtures represent established businesses whose
    # complete recipe catalog survives the introduction of business quests.
    # Keep operating expenses enabled; fresh signature locks have separate tests.
    state.pop('businessProgression', None)
    P.ensure(cfg, state, migrating=True)
    state['offers'] = None
    state['orderRecipeHistory'] = [[], [], []]
    E.offer_contracts(cfg, state, state['tick'])
    return state


def force_rarity(monkeypatch, rarity):
    selected = copy.deepcopy(next(r for r in E.ORDER_ROLLS if r['id'] == rarity))
    selected['chance'] = 100
    monkeypatch.setattr(E, 'ORDER_ROLLS', (selected,))


def test_catalog_has_distinct_named_purposeful_bundles_for_every_product():
    goods = E.catalog(E.load_config())
    assert len(ORDER_RECIPES) >= 150
    assert len({r['id'] for r in ORDER_RECIPES}) == len(ORDER_RECIPES)
    assert len({r['name'].casefold() for r in ORDER_RECIPES}) == len(ORDER_RECIPES)
    assert len({frozenset(r['goods']) for r in ORDER_RECIPES}) == len(ORDER_RECIPES), \
        'Renaming the same goods does not add a different delivery recipe.'
    assert set().union(*(set(r['goods']) for r in ORDER_RECIPES)) == set(goods)
    assert {len(r['goods']) for r in ORDER_RECIPES} == {1, 2, 3, 4, 5}
    for recipe in ORDER_RECIPES:
        assert recipe['name'].strip() and len(recipe['purpose'].split()) >= 4
        assert type(recipe['breakfast']) is bool
        selected = set(recipe['goods'])
        assert len(selected) == len(recipe['goods'])
        assert selected <= set(goods)


@pytest.mark.parametrize('rarity,slot', [
    ('standard', 0), ('standard', 1),
    ('large', 0), ('rare', 0), ('jackpot', 0),
])
def test_every_recipe_in_range_stays_reachable_under_its_rarity_cap(monkeypatch, rarity, slot):
    """Weighted deals retire nothing: a job made rare must still be dealt.

    The engine steers the odds by recency, worth and build order, so a bucket
    no longer empties in order. Every recipe it can offer must still arrive,
    and no deal may exceed the authored rarity cap.
    """
    force_rarity(monkeypatch, rarity)
    cfg = E.load_config()
    state = town(cfg)
    authored = next(r for r in E.ORDER_ROLLS if r['id'] == rarity)['items']
    cap = authored or (1 if slot == 0 else 2) + len(state['tierOf'])//4
    # An authored rarity deals exactly its promised size; a standard roll,
    # sized by the town, also reaches one product below it.
    low = cap if authored else max(1, cap - 1)
    expected = {r['id'] for r in ORDER_RECIPES if low <= len(r['goods']) <= cap}
    assert expected
    # The other two cards keep their jobs for this whole run, and the board
    # never shows one job twice, so those two are legitimately out of reach.
    parked = {order['recipeId'] for i, order in enumerate(state['offers'])
              if i != slot and order.get('recipeId')}
    expected -= parked
    seen = set()
    for _ in range(2000):
        order = state['offers'][slot]
        assert low <= len(order['requirements']) <= cap, 'A deal escaped its rarity cap.'
        seen.add(order['recipeId'])
        if expected <= seen:
            break
        assert E.replace_order(cfg, state, slot, order['id'])['ok']
    assert expected <= seen, 'These recipes never arrived: {}'.format(sorted(expected - seen))


def test_a_sparse_town_receives_the_largest_bundle_it_can_supply(monkeypatch):
    """A cap the catalog cannot reach is not widened downwards."""
    force_rarity(monkeypatch, 'jackpot')
    cfg = E.load_config()
    state = town(cfg, [0])
    for _ in range(12):
        order = state['offers'][0]
        assert len(order['requirements']) == 3, 'Only three farm products exist to ask for.'
        assert E.replace_order(cfg, state, 0, order['id'])['ok']


def test_an_outgrown_job_becomes_rare_without_becoming_impossible(monkeypatch):
    """The value floor changes the odds only; nothing leaves the catalog."""
    force_rarity(monkeypatch, 'standard')
    cfg = E.load_config()
    goods = E.catalog(cfg)
    state = town(cfg)
    cap = 1 + len(state['tierOf'])//4
    in_range = [r for r in ORDER_RECIPES if max(1, cap - 1) <= len(r['goods']) <= cap]
    worth = {r['id']: E._recipe_value(cfg, 0, E.ORDER_ROLLS[0], goods, r) for r in in_range}
    cheapest = min(worth, key=worth.get)
    counts = collections.Counter()
    for _ in range(2000):
        order = state['offers'][0]
        counts[order['recipeId']] += 1
        assert E.replace_order(cfg, state, 0, order['id'])['ok']
    assert counts[cheapest], 'An outgrown job must still be reachable.'
    dearest = max(worth, key=worth.get)
    assert counts[dearest] > counts[cheapest], \
        'A job the town has outgrown must be dealt less often than a worthwhile one.'


@pytest.mark.parametrize('tiers', [(0,), (0, 2), (0, 5, 10, 12, 14)])
def test_sparse_towns_only_receive_complete_recipes_they_can_supply(tiers):
    cfg = E.load_config()
    state = town(cfg, tiers)
    goods = E.catalog(cfg)
    recipes = {r['id']: r for r in ORDER_RECIPES}
    money = (state['cash'], state['materials'])
    seen = set()
    for turn in range(180):
        slot = turn % 2
        order = state['offers'][slot]
        recipe = recipes[order['recipeId']]
        requested = {n['goodId'] for n in order['requirements']}
        assert requested == set(recipe['goods']), 'Rarity must never add unrelated goods to a recipe.'
        assert order['name'] == recipe['name'] and order['purpose'] == recipe['purpose']
        assert order['channelLabel']
        for good_id in requested:
            assert goods[good_id]['tier'] in tiers
            assert P.product_unlocked(cfg, state, good_id)
        seen.add(order['recipeId'])
        assert E.replace_order(cfg, state, slot, order['id'])['ok']
    assert len(seen) > 3, 'Even a small town needs more than three permanent delivery choices.'
    assert (state['cash'], state['materials']) == money


def test_dormant_input_chains_do_not_exclude_owned_products(monkeypatch):
    cfg = E.load_config()
    # Existing snapshots retain input metadata for future manual crafting.
    # Even a long chain with a missing former supplier cannot gate automatic goods.
    compute = next(g for t in cfg['tiers'] for g in t['goods'] if g['id'] == 'data_center_compute_hours')
    compute['inputs'] = [dict(goodId='solar_coop_battery_storage', quantity=1)]
    missing_tier = next(i for i, t in enumerate(cfg['tiers']) if t['id'] == 'workshop')
    tiers = [i for i in range(len(cfg['tiers'])) if i != missing_tier]
    force_rarity(monkeypatch, 'standard')
    state = town(cfg, tiers)
    seen = set()
    for _ in range(len(ORDER_RECIPES)):
        order = state['offers'][0]
        seen.update(n['goodId'] for n in order['requirements'])
        E.replace_order(cfg, state, 0, order['id'])
    assert 'uplink_center_satellite_bandwidth' in seen
    assert 'solar_coop_battery_storage' in seen
    assert 'data_center_compute_hours' in seen
    assert 'uplink_center_telemetry' in seen
    assert not seen.intersection(g['id'] for g in cfg['tiers'][missing_tier]['goods'])


def test_opening_a_business_adds_its_orders_without_resetting_saved_cards(monkeypatch):
    force_rarity(monkeypatch, 'standard')
    cfg = E.load_config()
    state = town(cfg, [0])
    for _ in range(12):
        E.replace_order(cfg, state, 0, state['offers'][0]['id'])
    saved_offers = copy.deepcopy(state['offers'])
    state['b'].append(E._building(2))
    state['tierOf'].append(2)
    E.offer_contracts(cfg, state, state['tick'])
    assert state['offers'] == saved_offers
    seen = set()
    for _ in range(15):
        E.replace_order(cfg, state, 0, state['offers'][0]['id'])
        seen.update(n['goodId'] for n in state['offers'][0]['requirements'])
    assert {g['id'] for g in cfg['tiers'][2]['goods']} <= seen


def test_starter_jackpot_uses_a_smaller_complete_recipe(monkeypatch):
    force_rarity(monkeypatch, 'jackpot')
    cfg = E.load_config()
    state = town(cfg, [0])
    farm_goods = {g['id'] for g in cfg['tiers'][0]['goods']}
    recipes = {r['id']: r for r in ORDER_RECIPES}
    for order in state['offers'][:2]:
        assert order['rarity'] == 'jackpot'
        assert {n['goodId'] for n in order['requirements']} == farm_goods
        assert set(recipes[order['recipeId']]['goods']) == farm_goods
        assert order['rewardPercent'] > 250


def test_migration_keeps_saved_orders_cash_inventory_and_adds_history():
    cfg = E.load_config()
    saved = town(cfg)
    saved.pop('orderRecipeHistory')
    # This represents a card saved before named recipes existed.
    for order in saved['offers']:
        for key in ('recipeId', 'purpose', 'channelLabel'):
            order.pop(key, None)
    saved['offers'][0]['committed'] = True
    saved['cash'] = 913
    saved['inventory'] = {'farm_tomatoes': 7}
    offers = copy.deepcopy(saved['offers'])
    migrated = E.migrate_state(cfg, E.State(json.loads(json.dumps(saved))))
    assert migrated['offers'] == offers, 'A migration must honor existing order prices and commitments.'
    assert migrated['cash'] == 913 and migrated['inventory'] == {'farm_tomatoes': 7}
    assert len(migrated['orderRecipeHistory']) == 3
    assert all(isinstance(h, list) for h in migrated['orderRecipeHistory'])
    before = copy.deepcopy(migrated)
    assert E.migrate_state(cfg, migrated) == before
    E.replace_order(cfg, migrated, 0, migrated['offers'][0]['id'])
    assert migrated['offers'][0]['recipeId'] in {r['id'] for r in ORDER_RECIPES}


def test_legacy_nonfood_town_can_trade_while_its_food_project_is_locked():
    cfg = E.load_config()
    cfg['businessDesign'].pop('connectedProgression', None)  # Existing class snapshot.
    old = E.legacy.new_state(E.legacy.load_config())
    old.update(tierOf=[3], b=[dict(tier=3, lv=4, auto=1)], cash=420, pend={})
    migrated = E.migrate_state(cfg, old)
    assert migrated['tierOf'] == [3] and migrated['cash'] == 420
    garage_goods = {g['id'] for g in cfg['tiers'][3]['goods']}
    for _ in range(12):
        order = migrated['offers'][0]
        assert {n['goodId'] for n in order['requirements']} <= garage_goods
        assert E.replace_order(cfg, migrated, 0, order['id'])['ok']
    project = migrated['offers'][2]
    assert project['project']
    assert not E.commit_order(cfg, migrated, 2, project['id'], True)['ok']
    order = migrated['offers'][0]
    for need in order['requirements']:
        migrated['inventory'][need['goodId']] = need['quantity']
    assert E.fulfill_order(cfg, migrated, 0, order['id'])['ok']
    assert migrated.get('regularDeliveries', 0) == 0
    migrated['tierOf'].append(0)
    migrated['b'].append(E._building(0))
    assert E.commit_order(cfg, migrated, 2, project['id'], True)['ok']
    assert {n['goodId'] for n in project['requirements']} <= {g['id'] for g in cfg['tiers'][0]['goods']}


def test_json_replay_preserves_recipe_rotation_without_spending_or_production():
    cfg = E.load_config()
    original = town(cfg)
    reloaded = E.State(json.loads(json.dumps(original)))
    before = (original['cash'], original['materials'], original['tick'], copy.deepcopy(original['inventory']))
    for turn in range(120):
        slot = turn % 2
        reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(reloaded))))
        for state in (original, reloaded):
            assert E.replace_order(cfg, state, slot, state['offers'][slot]['id'])['ok']
        assert original['offers'] == reloaded['offers']
        assert original['orderRecipeHistory'] == reloaded['orderRecipeHistory']
    assert (original['cash'], original['materials'], original['tick'], original['inventory']) == before


def test_committed_multibusiness_order_can_be_produced_and_delivered_atomically(monkeypatch):
    force_rarity(monkeypatch, 'jackpot')
    cfg = E.load_config()
    goods = E.catalog(cfg)
    state = town(cfg)
    # This test isolates reserved-order production with funded operations.
    state['cash'] = 1_000_000
    choices = [r for r in ORDER_RECIPES if len(r['goods']) == 5]
    # Exercise a real catalog bundle spanning several independent businesses.
    # Worth breaks ties: an established town is rarely offered its cheapest
    # jobs, so a retired bundle would take unbounded rerolls to arrive.
    target = max(choices, key=lambda r: (sum(bool(goods[g].get('inputs')) for g in r['goods']),
                                         len({goods[g]['tier'] for g in r['goods']}),
                                         E._recipe_value(cfg, 0, E.ORDER_ROLLS[-1], goods, r)))
    for _ in range(3000):
        order = state['offers'][0]
        if order['recipeId'] == target['id']:
            break
        E.replace_order(cfg, state, 0, order['id'])
    assert order['recipeId'] == target['id']
    assert E.commit_order(cfg, state, 0, order['id'], True)['ok']
    empty = copy.deepcopy(state)
    assert not E.fulfill_order(cfg, state, 0, order['id'])['ok']
    assert state == empty
    for _ in range(2400):
        E._produce(cfg, state)
        E._retail(cfg, state)
        if all(state['inventory'].get(n['goodId'], 0) >= n['quantity'] for n in order['requirements']):
            break
    assert all(state['inventory'].get(n['goodId'], 0) >= n['quantity'] for n in order['requirements']), \
        'Saving the goods must not deadlock the production of another item in the same delivery.'
    inventory = copy.deepcopy(state['inventory'])
    cash = state['cash']
    assert E.fulfill_order(cfg, state, 0, order['id'])['ok']
    assert state['cash'] == cash + order['reward']
    for need in order['requirements']:
        assert state['inventory'][need['goodId']] == inventory[need['goodId']] - need['quantity']
    paid = copy.deepcopy(state)
    assert not E.fulfill_order(cfg, state, 0, order['id'])['ok']
    assert state == paid
