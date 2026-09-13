"""Permanent workers modify real production without bypassing its constraints."""
from __future__ import annotations

import copy
import json

import pytest

import business_operations as O
import production_economy as E
import workforce as W


def ticks(cfg, st, count):
    for _ in range(count):
        E.player_tick(cfg, {}, st, st['tick'])


def staffed_recipe(type_id, good_id, branch, workers=10):
    """Exercise real recipe effects retained by legacy crew snapshots."""
    cfg = E.load_config()
    cfg['workforce']['populationEnabled'] = False
    cfg['workforce']['workerTrainingSeconds'] = 10**9
    ti, tier = next((i, t) for i, t in enumerate(cfg['tiers']) if t['id'] == type_id)
    good = copy.deepcopy(next(g for g in tier['goods'] if g['id'] == good_id))
    tier['goods'] = [good]
    tier['capacity'] = 100000
    st = E.new_state(cfg)
    st['tierOf'] = [ti]
    st['b'] = [E._building(ti, lv=3)]
    st['b'][0]['reserve'] = True
    st['cash'] = 100000
    # This fixture represents an established business, with earned Prestige for
    # its basic focus and the advanced focus exercised by the maintenance test.
    st['businessProgression'].update(prestige=3, prestigeEarned=3)
    O.ensure(cfg, st)
    bid = st['b'][0]['buildingId']
    for action in (dict(action='focus', nodeId='orientation'), dict(action='hire'),
                   dict(action='focus', nodeId=branch)):
        result = W.act(cfg, st, dict(buildingId=bid, **action))
        assert result['ok'], result
    st['workforce']['teams'][type_id]['workers'] = workers
    allocation = dict.fromkeys(W.BRANCHES, 0)
    allocation[branch] = workers
    assert W.act(cfg, st, dict(action='allocate', buildingId=bid,
                               allocation=allocation, trainingBranch=branch))['ok']
    st['cash'] = 100000
    return cfg, st, good


def without_assignments(st):
    result = copy.deepcopy(st)
    for team in result['workforce']['teams'].values():
        team['allocation'] = dict.fromkeys(W.BRANCHES, 0)
    return result


def assert_integer_wallet_and_stock(st):
    assert type(st['cash']) is int and st['cash'] >= 0
    assert all(type(qty) is int and qty >= 0 for qty in st['inventory'].values())


def test_production_workers_accelerate_pastries_and_consume_every_ingredient():
    cfg, staffed, good = staffed_recipe('roastery', 'roastery_pastries', 'production')
    for need in good['inputs']:
        staffed['inventory'][need['goodId']] = 100
    ordinary = without_assignments(staffed)
    for st in (ordinary, staffed):
        ticks(cfg, st, 40)
    made = staffed['inventory'][good['id']]
    assert made > ordinary['inventory'][good['id']]
    for need in good['inputs']:
        assert staffed['inventory'][need['goodId']] == 100 - made * need['quantity']
        staffed['inventory'][need['goodId']] = 0
    ticks(cfg, staffed, 100)
    assert staffed['inventory'][good['id']] == made
    assert staffed['productionBlocked'][good['id']]['reason'] == 'ingredient'
    assert_integer_wallet_and_stock(staffed)


def test_production_focus_never_unlocks_a_signature_recipe():
    cfg, st, good = staffed_recipe('garage', 'garage_custom_mods', 'production')
    for need in good['inputs']:
        st['inventory'][need['goodId']] = 100
    ticks(cfg, st, 40)
    assert st['inventory'].get(good['id'], 0) == 0
    assert st['productionBlocked'][good['id']]['reason'] == 'quest'
    for need in good['inputs']:
        assert st['inventory'][need['goodId']] == 100


def test_sales_workers_increase_fractional_demand_but_need_real_inventory():
    cfg, staffed, good = staffed_recipe('farm', 'farm_tomatoes', 'sales', workers=3)
    staffed['b'][0]['reserve'] = False
    staffed['inventory'][good['id']] = 1000
    ordinary = without_assignments(staffed)
    for st in (ordinary, staffed):
        for tick in range(200):
            E._retail(cfg, st, tick)
        assert_integer_wallet_and_stock(st)
    assert staffed['report']['unitsSold'] > ordinary['report']['unitsSold']
    # 65% base demand plus 7.5% of that base, accumulated without per-tick loss.
    assert staffed['report']['unitsSold'] == 139
    scarce = copy.deepcopy(staffed)
    scarce['inventory'][good['id']] = 1
    cash = scarce['cash']
    sold = scarce['report']['unitsSold']
    for tick in range(200, 400):
        E._retail(cfg, scarce, tick)
    assert scarce['cash'] == cash + good['unitPrice']
    assert scarce['report']['unitsSold'] == sold + 1
    assert scarce['inventory'][good['id']] == 0
    assert_integer_wallet_and_stock(scarce)


def test_efficiency_accumulates_fractional_batch_savings_across_json_reload():
    cfg, staffed, good = staffed_recipe('farm', 'farm_eggs', 'efficiency', workers=7)
    ordinary = without_assignments(staffed)
    assert O.effective_batch_cost(cfg, staffed['b'][0], good, staffed) == pytest.approx(.93)
    ticks(cfg, ordinary, 200)
    ticks(cfg, staffed, 91)
    staffed = E.migrate_state(cfg, json.loads(json.dumps(staffed)))
    ticks(cfg, staffed, 109)
    made = staffed['inventory'][good['id']]
    assert made == ordinary['inventory'][good['id']] == 150
    assert staffed['cash'] == 100000 - (made * 93 // 100)
    assert ordinary['cash'] == 100000 - made
    assert staffed['b'][0]['costRemainder'] / O.COST_SCALE == pytest.approx(.5)
    assert staffed['businessOperations']['totalOperatingCosts'] == 100000 - staffed['cash']
    assert_integer_wallet_and_stock(staffed)


def test_maintenance_keeps_starter_tomatoes_free():
    cfg, st, good = staffed_recipe('farm', 'farm_tomatoes', 'efficiency')
    st['cash'] = 0
    assert O.effective_batch_cost(cfg, st['b'][0], good, st) == 0
    ticks(cfg, st, 100)
    assert st['inventory'][good['id']] > 0
    assert st['cash'] == 0
    assert st['businessOperations']['totalOperatingCosts'] == 0
    assert_integer_wallet_and_stock(st)


def test_advanced_efficiency_preserves_small_fractions_on_upgraded_businesses():
    cfg, st, good = staffed_recipe('farm', 'farm_eggs', 'efficiency', workers=3)
    st['businessProgression']['quests']['farm-signature'] = dict(completed=True)
    assert W.act(cfg, st, dict(action='focus', buildingId=st['b'][0]['buildingId'],
                               nodeId='efficiency-advanced'))['ok']
    st['b'][0].update(sales=2, auto=2, storage=2)
    st['cash'] = 100000
    # 1 YM * (1 + 10% customer + 5% storage) * (1 - 3 * 1.25%).
    assert O.effective_batch_cost(cfg, st['b'][0], good, st) == pytest.approx(1.106875)
    ticks(cfg, st, 200)
    assert st['inventory'][good['id']] == 150
    assert st['cash'] == 100000 - 166
    assert st['b'][0]['costRemainder'] / O.COST_SCALE == pytest.approx(.03125)
    assert_integer_wallet_and_stock(st)


def training_town():
    cfg = E.load_config()
    # Existing class snapshots keep their original trainer-to-crew rules.
    cfg['workforce']['populationEnabled'] = False
    st = E.new_state(cfg)
    st['cash'] = 100000
    st['b'][0]['lv'] = 3
    bid = st['b'][0]['buildingId']
    assert W.act(cfg, st, dict(action='focus', buildingId=bid, nodeId='orientation'))['ok']
    assert W.act(cfg, st, dict(action='hire', buildingId=bid))['ok']
    return cfg, st


def test_business_pause_freezes_workers_and_hq_trainers():
    cfg, st = training_town()
    st['workforce']['hq'].update(level=1, targets=['farm'])
    st['b'][0]['paused'] = True
    before = copy.deepcopy(st['workforce'])
    ticks(cfg, st, 200)
    assert st['workforce'] == before
    st['b'][0]['paused'] = False
    ticks(cfg, st, 40)
    team = st['workforce']['teams']['farm']
    assert team['workers'] == 2
    assert team['trainers'] == 2


def test_skipped_offline_time_does_not_train_or_bank_future_work():
    cfg, absent = training_town()
    cfg['runtime']['offlineHours'] = 1 / 60
    cfg['workforce']['workerTrainingSeconds'] = 30
    at_cap = copy.deepcopy(absent)
    E.advance_class(cfg, E.new_class(cfg), [at_cap], 0, 4)
    E.advance_class(cfg, E.new_class(cfg), [absent], 0, 400)
    assert absent['workforce'] == at_cap['workforce']
    assert absent['workforce']['teams']['farm']['workers'] == 2
    frozen = copy.deepcopy(absent['workforce'])
    E.advance_class(cfg, E.new_class(cfg), [absent], 400, 500)
    assert absent['workforce'] == frozen
    E.on_login(cfg, absent)
    E.advance_class(cfg, E.new_class(cfg), [absent], 500, 502)
    assert absent['workforce']['teams']['farm']['workers'] == 3


@pytest.mark.parametrize('has_instance_id', [True, False])
def test_active_legacy_shift_migrates_once_without_changing_money_or_goods(has_instance_id):
    cfg = E.load_config()
    legacy_cfg = copy.deepcopy(cfg)
    legacy_cfg.pop('workforce', None)
    st = E.new_state(legacy_cfg)
    st['cash'] = 137
    st['inventory'].update(farm_tomatoes=7, farm_eggs=3, farm_honey=2)
    st['b'][0]['staff'] = dict(id='technician', remainingTicks=8)
    if not has_instance_id:
        del st['b'][0]['buildingId']
    stock = copy.deepcopy(st['inventory'])
    migrated = E.migrate_state(cfg, st)
    team = migrated['workforce']['teams']['farm']
    assert team['hires'] == team['trainers'] == 1
    assert team['workers'] == 0
    assert team['legacyConverted']['role'] == 'technician'
    assert migrated['b'][0]['staff'] is None
    before = copy.deepcopy(migrated['workforce'])
    again = E.migrate_state(cfg, json.loads(json.dumps(migrated)))
    assert again['workforce'] == before
    assert again['cash'] == 137
    assert again['inventory'] == stock
