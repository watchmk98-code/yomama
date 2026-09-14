"""Sector timing changes cadence while preserving rates and saved obligations."""
from __future__ import annotations

import copy
import json

import pytest

import business_operations as operations
import order_engine as orders
import production_economy as economy


def town(tiers, enabled=True, unlock=True):
    cfg = economy.load_config()
    cfg['production']['sectorRhythms'] = enabled
    state = economy.new_state(cfg, seed=71)
    state['cash'] = 1_000_000
    state['tierOf'] = list(tiers)
    state['b'] = [economy._building(tier, storage=12) for tier in tiers]
    for building in state['b']:
        building['reserve'] = True
    if unlock:
        state['businessProgression']['grandfathered'] = [cfg['tiers'][tier]['id'] for tier in tiers]
    operations.ensure(cfg, state)
    return cfg, state


def produce(cfg, state, count):
    pattern = []
    for _ in range(count):
        before = state['report']['unitsProduced']
        economy._produce(cfg, state)
        pattern.append(state['report']['unitsProduced'] - before)
        state['tick'] += 1
    return pattern


@pytest.mark.parametrize('tier,expected', [
    (0, [1, 2, 1, 3, 1, 2, 1, 3]),
    (3, [0, 2, 0, 4, 0, 2, 0, 6]),
    (5, [1, 1, 2, 1, 2, 2, 2, 1]),
])
def test_sector_patterns_use_existing_product_rates(tier, expected):
    cfg, state = town([tier])
    assert produce(cfg, state, 8) == expected


def test_all_fifteen_businesses_keep_output_and_exact_cost_after_energy_warmup():
    for tier in range(15):
        cfg, changed = town([tier])
        baseline_cfg, baseline = town([tier], enabled=False)
        measurements = []
        for rules, state in ((cfg, changed), (baseline_cfg, baseline)):
            produce(rules, state, 16)
            stock = copy.deepcopy(state['inventory'])
            cash = state['cash']
            costs = state['businessOperations']['totalOperatingCosts']
            carry = state['b'][0]['costRemainder']
            produce(rules, state, 64)
            made = {gid: quantity - stock.get(gid, 0) for gid, quantity in state['inventory'].items()}
            spent = costs - state['businessOperations']['totalOperatingCosts']
            assert state['cash'] - cash == spent
            exact_cost = -spent * operations.COST_SCALE + state['b'][0]['costRemainder'] - carry
            measurements.append((made, exact_cost))
        assert measurements[0] == measurements[1], cfg['tiers'][tier]['id']


def test_industry_can_finish_a_saved_order_at_an_odd_shelf_limit():
    cfg, state = town([3])
    state['b'][0]['storage'] = 1
    cfg['tiers'][3]['capacity'] = 15
    gid = 'garage_repairs'
    state['inventory'][gid] = 4
    offer = state['offers'][0]
    offer.update(requirements=[dict(goodId=gid, quantity=5)], reward=25, materials=0)
    assert economy.commit_order(cfg, state, 0, offer['id'], True)['ok']
    state['productionWork'][gid] = 100
    cash = state['cash']
    produce(cfg, state, 1)
    assert state['inventory'][gid] == 5
    assert state['cash'] == cash - 1
    assert economy.fulfill_order(cfg, state, 0, offer['id'])['ok']
    assert state['inventory'][gid] == 0


def test_industry_can_produce_one_affordable_unit_without_debt():
    cfg, state = town([3])
    state['b'][0]['storage'] = 1
    state['cash'] = 1
    state['productionWork']['garage_repairs'] = 100
    produce(cfg, state, 1)
    assert state['inventory'] == {'garage_repairs': 1}
    assert state['cash'] == 0
    assert state['businessOperations']['totalOperatingCosts'] == 1


def test_group_cost_is_scaled_before_rounding_carry_and_charges_once():
    cfg, state = town([3])
    building = state['b'][0]
    building.update(sales=2, storage=2, costRemainder=operations.COST_SCALE // 2)
    good = cfg['tiers'][3]['goods'][0]
    assert operations.batch_quote(cfg, building, good, state, batches=2) == (
        2, operations.COST_SCALE * 8 // 10)
    single = copy.deepcopy(state)
    assert operations.charge_batch(cfg, state, building, good, 0, batches=2)
    for _ in range(2):
        assert operations.charge_batch(cfg, single, single['b'][0], good, 0)
    assert state['cash'] == single['cash']
    assert building['costRemainder'] == single['b'][0]['costRemainder']
    assert state['businessOperations']['totalOperatingCosts'] == 2


def test_energy_warmup_freezes_for_paused_or_quest_locked_products():
    cfg, state = town([5], unlock=False)
    gid = 'solar_coop_carbon_credits'
    produce(cfg, state, 2)
    assert gid not in state['productionPhase']
    assert state['productionBlocked'][gid]['reason'] == 'quest'
    state['b'][0]['paused'] = True
    saved = (copy.deepcopy(state['productionPhase']), copy.deepcopy(state['productionWork']))
    produce(cfg, state, 4)
    assert (state['productionPhase'], state['productionWork']) == saved
    state['b'][0]['paused'] = False
    state['businessProgression']['quests']['solar_coop-plan'] = dict(completed=True)
    produce(cfg, state, 1)
    assert state['productionPhase'][gid] == 1
    assert state['inventory'].get(gid, 0) == 0


def test_old_earned_work_and_phase_survive_migration_and_json_reload():
    cfg, state = town([5])
    state.pop('productionPhase', None)
    state['productionWork'] = {'solar_coop_battery_storage': 150,
                               'solar_coop_carbon_credits': 350}
    state['b'][0]['costRemainder'] = 425_000
    state['offers'][0]['committed'] = True
    before = copy.deepcopy(state)
    state = economy.migrate_state(cfg, state)
    assert state['productionWork'] == before['productionWork']
    assert state['cash'] == before['cash'] and state['inventory'] == before['inventory']
    assert state['offers'] == before['offers']
    assert state['b'][0]['costRemainder'] == before['b'][0]['costRemainder']
    produce(cfg, state, 1)
    replay = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(state))))
    assert replay == state
    for _ in range(16):
        produce(cfg, state, 1)
        produce(cfg, replay, 1)
        replay = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(replay))))
        assert replay == state


def test_snapshot_without_rhythm_flag_enables_cadence_without_resetting_work():
    cfg, state = town([3])
    cfg['production'].pop('sectorRhythms')
    state.pop('productionPhase', None)
    state['b'][0]['storage'] = 1
    state['cash'] = 100
    state['productionWork']['garage_repairs'] = 50
    saved_offers = copy.deepcopy(state['offers'])
    state = economy.migrate_state(cfg, state)
    assert state['cash'] == 100 and state['productionWork']['garage_repairs'] == 50
    assert state['offers'] == saved_offers
    assert produce(cfg, state, 1) == [0]
    assert state['productionWork']['garage_repairs'] == 150
    assert produce(cfg, state, 1) == [2]
    assert state['inventory']['garage_repairs'] == 2 and state['cash'] == 98


def test_disabled_operating_costs_keep_industry_batching_with_an_empty_wallet():
    cfg, state = town([3])
    cfg.pop('businessDesign')
    state['cash'] = 0
    assert produce(cfg, state, 8) == [0, 2, 0, 4, 0, 2, 0, 6]
    assert state['cash'] == 0
    assert state['businessOperations']['totalOperatingCosts'] == 0


def test_forecasts_prices_demand_and_normal_or_sector_offers_are_unchanged():
    cfg, state = town(range(15))
    baseline_cfg, baseline = town(range(15), enabled=False)
    for candidate in (state, baseline):
        for building in candidate['b']:
            building['reserve'] = False
    for rules, candidate in ((cfg, state), (baseline_cfg, baseline)):
        assert economy.manage_customer_contract(rules, candidate, 0, 'accept', 'corner_grocer')['ok']
    fields = ('incomePerMinute', 'productionCapacityPerMinute', 'customerCapacityPerMinute',
              'productionPerMinute', 'potentialOperatingCostPerMinute', 'potentialProfitPerMinute')
    payloads = [economy.payload(rules, candidate, {}, {'paused': False})
                for rules, candidate in ((cfg, state), (baseline_cfg, baseline))]
    for first, second in zip(*(payload['buildings'] for payload in payloads)):
        assert {field: first[field] for field in fields} == {field: second[field] for field in fields}
        assert [good['unitPrice'] for good in first['goods']] == [good['unitPrice'] for good in second['goods']]
    for turn in range(18):
        index = turn % 3
        for rules, candidate in ((cfg, state), (baseline_cfg, baseline)):
            assert economy.replace_order(rules, candidate, index, candidate['offers'][index]['id'])['ok']
        assert state['offers'] == baseline['offers']
    changed = orders.create_board(cfg, state)
    original = orders.create_board(baseline_cfg, baseline)
    for _ in range(12):
        assert changed['offers'] == original['offers']
        assert orders.apply_action(cfg, changed, 1, 'replace')['ok']
        assert orders.apply_action(baseline_cfg, original, 1, 'replace')['ok']
