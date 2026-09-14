"""Regular throughput claims finished goods before walk-in sales."""
from __future__ import annotations

import copy

import pytest

import production_economy as E


@pytest.fixture
def town(monkeypatch):
    cfg = E.load_config()
    st = E.new_state(cfg, seed=83)
    st['tierOf'] = [0, 2]
    st['b'] = [E._building(ti) for ti in st['tierOf']]
    capacities = {}
    monkeypatch.setattr(E, 'product_speed', lambda cfg, st, b, good:
        capacities.get(good['id'], 0) * 100 * good['cycleTicks'] * cfg['global']['tick'] / 60 / good['quantity'])
    monkeypatch.setattr(E, 'customer_demand', lambda *args: 10 ** 9)
    monkeypatch.setattr(E.business_progression, 'product_unlocked', lambda *args: True)
    return cfg, st, capacities


def buyer(st, slot, needs, reward=60, seconds=60):
    contract = dict(id='flow-buyer-{}'.format(slot), slot=slot, paused=False,
                    requirements=[dict(goodId=gid, quantity=qty) for gid, qty in needs],
                    reward=reward, intervalTicks=seconds // 15)
    st['customerContracts']['active'].append(contract)
    return contract


def test_regular_claims_only_its_product_and_other_business_runs_independently(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=4, farm_honey=4, roastery_pastries=4)
    buyer(st, 0, [('farm_eggs', 6)], reward=22, seconds=120)
    rates, regulars = E._flows(cfg, st)
    assert rates['farm_eggs']['regulars'] == 3
    assert rates['roastery_pastries']['production'] == 4
    assert rates['farm_eggs']['retail'] == 1
    assert regulars['incomePerMinute'] == 11


def test_whole_bundle_bottleneck_reserves_only_deliverable_finished_goods(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=8, farm_honey=0, roastery_pastries=1)
    buyer(st, 0, [('farm_eggs', 4), ('roastery_pastries', 2)], reward=70)
    rates, regulars = E._flows(cfg, st)
    assert regulars['customers'][0]['deliveriesPerMinute'] == .5
    assert regulars['incomePerMinute'] == 35
    assert rates['farm_eggs']['regulars'] == 2
    assert rates['farm_eggs']['retail'] == 6
    assert rates['roastery_pastries']['production'] == 1
    # Every available egg is delivered to one regular or sold once to a walk-in.
    assert rates['farm_eggs']['production'] == sum((
        rates['farm_eggs']['regulars'], rates['farm_eggs']['retail']))
    assert sum(regulars['byBuilding'].values()) == regulars['incomePerMinute']


def test_earlier_regular_slot_wins_shared_finished_product_capacity(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=4, farm_honey=4, roastery_pastries=4)
    raw = buyer(st, 0, [('farm_eggs', 6)])
    cooked = buyer(st, 1, [('farm_eggs', 2)])
    _, regulars = E._flows(cfg, st)
    assert [c['deliveriesPerMinute'] for c in regulars['customers']] == pytest.approx([2 / 3, 0])
    raw['slot'], cooked['slot'] = 1, 0
    _, regulars = E._flows(cfg, st)
    assert [c['deliveriesPerMinute'] for c in regulars['customers']] == pytest.approx([1, 1 / 3])
    cooked['paused'] = True
    _, regulars = E._flows(cfg, st)
    assert [c['id'] for c in regulars['customers']] == [raw['id']]
    assert regulars['customers'][0]['deliveriesPerMinute'] == pytest.approx(2 / 3)


def test_missing_finished_product_prevents_partial_bundle_income(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=4, farm_honey=4, roastery_pastries=0)
    buyer(st, 0, [('farm_eggs', 2), ('roastery_pastries', 1)])
    rates, regulars = E._flows(cfg, st)
    assert regulars['incomePerMinute'] == 0
    assert rates['farm_eggs']['regulars'] == 0
    assert rates['farm_eggs']['retail'] == 4
    assert rates['roastery_pastries']['production'] == 0


def test_batch_output_quantity_is_counted_once_without_using_old_inputs(town):
    cfg, st, capacities = town
    pastry = next(g for g in cfg['tiers'][2]['goods'] if g['id'] == 'roastery_pastries')
    pastry['quantity'] = 2
    pastry['inputs'] = [dict(goodId='farm_eggs', quantity=3), dict(goodId='farm_honey', quantity=1)]
    capacities.update(farm_eggs=6, farm_honey=2, roastery_pastries=8)
    buyer(st, 0, [('roastery_pastries', 4)])
    rates, regulars = E._flows(cfg, st)
    assert regulars['customers'][0]['deliveriesPerMinute'] == 1
    assert rates['roastery_pastries']['production'] == 8
    assert rates['roastery_pastries']['regulars'] == 4
    assert rates['roastery_pastries']['retail'] == 4
    assert rates['farm_eggs']['retail'] == 6
    assert rates['farm_honey']['retail'] == 2


def test_same_business_products_are_independent_and_only_business_pause_stops_them(town):
    cfg, st, capacities = town
    capacities.update(roastery_roasted_beans=2, roastery_espresso_shots=8)
    buyer(st, 0, [('roastery_espresso_shots', 4)])
    rates, regulars = E._flows(cfg, st)
    assert regulars['customers'][0]['deliveriesPerMinute'] == 1
    assert rates['roastery_roasted_beans']['production'] == 2
    assert rates['roastery_roasted_beans']['retail'] == 2
    assert rates['roastery_espresso_shots']['regulars'] == 4
    st['b'][1]['processing'] = False
    _, regulars = E._flows(cfg, st)
    assert regulars['incomePerMinute'] == 60
    st['b'][1]['paused'] = True
    _, regulars = E._flows(cfg, st)
    assert regulars['incomePerMinute'] == 0


def test_forecast_does_not_mutate_cash_inventory_or_contracts(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=8, farm_honey=4, roastery_pastries=4)
    buyer(st, 0, [('farm_eggs', 4), ('roastery_pastries', 2)])
    st['cash'] = 123
    st['inventory'] = {'farm_eggs': 17}
    before = copy.deepcopy((cfg, st))
    E._flows(cfg, st)
    assert (cfg, st) == before


def test_no_regulars_leaves_each_product_available_for_walk_ins(town):
    cfg, st, capacities = town
    capacities.update(farm_eggs=8, farm_honey=2, roastery_pastries=4)
    rates, regulars = E._flows(cfg, st)
    assert regulars['incomePerMinute'] == 0
    assert rates['roastery_pastries']['production'] == 4
    assert rates['farm_eggs']['retail'] == 8
    assert rates['farm_honey']['retail'] == 2


@pytest.mark.parametrize('own_recipe', [False, True])
def test_partial_catalog_produces_owned_goods_without_former_ingredients(town, own_recipe):
    cfg, st, capacities = town
    cfg['tiers'][0]['goods'] = [g for g in cfg['tiers'][0]['goods'] if g['id'] != 'farm_eggs']
    capacities.update(farm_tomatoes=4, farm_honey=4, roastery_pastries=4)
    if own_recipe:
        buyer(st, 0, [('roastery_pastries', 2)])
    else:
        st['tierOf'] = [0]
        st['b'] = [E._building(0)]
    rates, regulars = E._flows(cfg, st)
    assert rates['farm_tomatoes']['production'] == 4
    assert rates['farm_tomatoes']['retail'] == 4
    assert regulars['incomePerMinute'] == (60 if own_recipe else 0)
    if own_recipe:
        assert rates['roastery_pastries']['production'] == 4
        assert rates['roastery_pastries']['retail'] == 2
