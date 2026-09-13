"""Legacy cash-only focus, staff conservation and saved-team contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import workforce as W


def town(count=1):
    cfg = json.loads((Path(__file__).parents[1] / 'config/economy.v4.json').read_text())
    cfg['businessDesign']['enabled'] = True
    cfg['businessDesign']['connectedProgression'] = False
    cfg['workforce'] = dict(enabled=True, hireCooldownSeconds=1800,
                            workerTrainingSeconds=300, trainerTrainingSeconds=600)
    st = dict(tick=0, cash=100000, inventory={'farm_tomatoes': 13},
              b=[dict(tier=i, buildingId='business-{}'.format(i + 1), lv=3, paused=False, staff=None)
                 for i in range(count)], tierOf=list(range(count)),
              businessProgression=dict(quests={}))
    W.ensure(cfg, st)
    return cfg, st


def act(cfg, st, action, slot=0, **kw):
    return W.act(cfg, st, dict(action=action, buildingId=st['b'][slot]['buildingId'], **kw))


def team(st, type_id='farm'):
    return st['workforce']['teams'][type_id]


def recruit(cfg, st, slot=0):
    assert act(cfg, st, 'focus', slot, nodeId='orientation')['ok']
    assert act(cfg, st, 'hire', slot)['ok']


def ticks(cfg, st, seconds):
    assert seconds % cfg['global']['tick'] == 0
    for _ in range(seconds // cfg['global']['tick']):
        W.advance(cfg, st)
        st['tick'] += 1


def test_disabled_snapshots_leave_state_and_old_shift_untouched():
    cfg, st = town()
    del cfg['workforce']
    del st['workforce']
    st['b'][0]['staff'] = dict(id='assistant', remainingTicks=8)
    original = copy.deepcopy(st)
    assert W.ensure(cfg, st) == {}
    W.advance(cfg, st, 1800)
    assert W.bonuses(cfg, st, st['b'][0]) == dict(production=0, customer=0, efficiency=0)
    assert W.payload(cfg, st)['enabled'] is False
    assert not act(cfg, st, 'hire')['ok']
    assert st == original


def test_all_fifteen_buildings_have_usable_focus_trees_without_starter_staff():
    cfg, st = town(15)
    original = copy.deepcopy(st)
    rows = W.payload(cfg, st)['teams']
    assert len(rows) == 15
    assert len({row['typeId'] for row in rows}) == 15
    assert all(len(row['nodes']) == 7 and row['hires'] == row['workers'] == 0 for row in rows)
    assert set(W.THEMES) == {t['id'] for t in cfg['tiers']}
    assert st == original
    for slot in range(15):
        st['cash'] = 10 ** 12
        recruit(cfg, st, slot)
    assert len(st['workforce']['teams']) == 15


def test_training_is_prepaid_permanent_and_never_spends_automatic_cash_or_stock():
    cfg, st = town()
    recruit(cfg, st)
    assert team(st)['hires'] == team(st)['trainers'] == 1
    assert team(st)['workers'] == 0
    cash, inventory = st['cash'], copy.deepcopy(st['inventory'])
    ticks(cfg, st, 300)
    assert team(st)['workers'] == team(st)['allocation']['production'] == 1
    ticks(cfg, st, 10000 // 15 * 15)
    assert team(st)['workers'] == 10
    assert team(st)['trainers'] == 1
    assert team(st)['workerWork'] == 0
    assert st['cash'] == cash
    assert st['inventory'] == inventory


def test_explicit_hires_update_only_payroll_counters_after_validation():
    cfg, st = town()
    st['businessOperations'] = dict(totalStaffCosts=8, staffHired=1, totalOperatingCosts=17)
    operations = st['businessOperations']
    recruit(cfg, st)
    assert st['businessOperations'] is operations
    assert operations == dict(totalStaffCosts=32, staffHired=2, totalOperatingCosts=17)
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hire')['ok']
    assert st == before
    ticks(cfg, st, 300)
    assert operations == dict(totalStaffCosts=32, staffHired=2, totalOperatingCosts=17)


def test_hq_accelerates_training_with_next_tick_start_and_hard_caps():
    cfg, st = town(3)
    recruit(cfg, st)
    assert act(cfg, st, 'hq_upgrade')['ok']
    assert act(cfg, st, 'hq_assign', enabled=True)['ok']
    cash = st['cash']
    ticks(cfg, st, 600)
    assert (team(st)['trainers'], team(st)['workers']) == (2, 2)
    ticks(cfg, st, 600)
    assert (team(st)['trainers'], team(st)['workers']) == (3, 6)
    ticks(cfg, st, 600)
    assert (team(st)['trainers'], team(st)['workers']) == (3, 10)
    assert team(st)['workerWork'] == team(st)['trainerWork'] == 0
    assert st['cash'] == cash
    # A purchased hire creates genuinely new capacity after HQ filled its cap.
    assert act(cfg, st, 'hire')['ok']
    row = W.payload(cfg, st)['teams'][0]
    assert (row['hires'], row['trainers'], row['trainerCap'], row['workerCap']) == (2, 4, 4, 15)
    ticks(cfg, st, 15)
    assert team(st)['workers'] == 10  # No banked training from the old full roster.
    assert team(st)['workerWork'] == 60


def test_individual_pause_freezes_training_but_not_recruitment_class_clock():
    cfg, st = town(3)
    recruit(cfg, st)
    act(cfg, st, 'hq_upgrade')
    act(cfg, st, 'hq_assign', enabled=True)
    ticks(cfg, st, 150)
    original = copy.deepcopy(team(st))
    st['b'][0]['paused'] = True
    ticks(cfg, st, 1800)
    assert team(st) == original
    assert W.payload(cfg, st)['teams'][0]['hire']['remainingSeconds'] == 0
    assert W.payload(cfg, st)['teams'][0]['nextWorkerSeconds'] is None
    # A stopped business can be reorganized without generating a worker.
    assert act(cfg, st, 'hire')['ok']
    assert team(st)['workers'] == 0
    st['b'][0]['paused'] = False
    ticks(cfg, st, 75)
    assert team(st)['workers'] == 1


def test_cooldown_and_team_survive_closure_while_hq_releases_slot():
    cfg, st = town(3)
    recruit(cfg, st)
    act(cfg, st, 'hq_upgrade')
    act(cfg, st, 'hq_assign', enabled=True)
    ticks(cfg, st, 150)
    original = copy.deepcopy(team(st))
    closed = st['b'].pop(0)
    st['tierOf'].pop(0)
    ticks(cfg, st, 300)
    assert team(st) == original
    assert W.payload(cfg, st)['hq']['targets'] == []
    before = copy.deepcopy(st)
    assert not W.act(cfg, st, dict(action='hire', buildingId=closed['buildingId']))['ok']
    assert st == before
    closed['buildingId'] = 'business-rebuilt'
    st['b'].insert(0, closed)
    st['tierOf'].insert(0, 0)
    assert not act(cfg, st, 'hire')['ok']
    assert W.payload(cfg, st)['teams'][0]['hire']['remainingSeconds'] == 1350
    ticks(cfg, st, 1350)
    assert act(cfg, st, 'hire')['ok']


def test_three_hires_use_30_minute_cooldowns_and_increasing_explicit_prices():
    cfg, st = town()
    original_cash = st['cash']
    recruit(cfg, st)
    for count in (2, 3):
        before = copy.deepcopy(st)
        assert not act(cfg, st, 'hire')['ok']
        assert st == before
        ticks(cfg, st, 1800)
        assert act(cfg, st, 'hire')['ok']
        row = W.payload(cfg, st)['teams'][0]
        assert row['workerCap'] == 5 + 5 * count
    assert st['cash'] == original_cash - 24 - 48 - 96
    ticks(cfg, st, 1800)
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hire')['ok']
    assert st == before


def test_shared_allocation_and_new_worker_routing_use_unlocked_branches():
    cfg, st = town()
    recruit(cfg, st)
    ticks(cfg, st, 900)
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'allocate', allocation=dict(production=2, sales=1, efficiency=0))['ok']
    assert st == before
    assert act(cfg, st, 'focus', nodeId='sales')['ok']
    assert act(cfg, st, 'allocate', allocation=dict(production=2, sales=1, efficiency=0), trainingBranch='sales')['ok']
    ticks(cfg, st, 300)
    assert team(st)['allocation'] == dict(production=2, sales=2, efficiency=0)
    assert team(st)['workers'] == 4
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'allocate', allocation=dict(production=4, sales=4, efficiency=0))['ok']
    assert st == before


@pytest.mark.parametrize('allocation,branch', [
    (dict(production=True, sales=0, efficiency=0), 'production'),
    (dict(production=-1, sales=0, efficiency=0), 'production'),
    (dict(production=1.0, sales=0, efficiency=0), 'production'),
    (dict(production='1', sales=0, efficiency=0), 'production'),
    (dict(production=0, sales=0), 'production'),
    (dict(production=0, sales=0, efficiency=0, extra=0), 'production'),
    ([], 'production'),
    (dict(production=0, sales=0, efficiency=0), True),
    (dict(production=0, sales=0, efficiency=0), 'sales'),
])
def test_bad_allocations_and_locked_training_reject_without_mutating(allocation, branch):
    cfg, st = town()
    recruit(cfg, st)
    ticks(cfg, st, 300)
    before = copy.deepcopy(st)
    result = act(cfg, st, 'allocate', allocation=allocation, trainingBranch=branch)
    assert not result['ok']
    assert st == before


def test_focus_prerequisites_use_existing_quests_without_spending_knowhow_or_unlocking_recipes():
    cfg, st = town()
    st['b'][0]['lv'] = 1
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'focus', nodeId='orientation')['ok']
    assert st == before


    st['businessProgression']['quests']['farm-plan'] = dict(completed=True)
    assert act(cfg, st, 'focus', nodeId='orientation')['ok']
    assert act(cfg, st, 'focus', nodeId='production')['ok']
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'focus', nodeId='production-advanced')['ok']
    assert st == before
    st['businessProgression']['quests']['farm-signature'] = dict(completed=True)
    quests = copy.deepcopy(st['businessProgression'])
    assert act(cfg, st, 'focus', nodeId='production-advanced')['ok']
    assert st['businessProgression'] == quests
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'focus', nodeId='production-advanced')['ok']
    assert st == before


def test_focus_payload_distinguishes_structural_unlocks_from_affordability():
    cfg, st = town()
    st['b'][0]['lv'] = 1
    assert not W.payload(cfg, st)['teams'][0]['nodes'][0]['unlocked']
    st['b'][0]['lv'] = 3
    assert act(cfg, st, 'focus', nodeId='orientation')['ok']
    st['cash'] = 0
    nodes = {node['id']: node for node in W.payload(cfg, st)['teams'][0]['nodes']}
    assert nodes['production']['unlocked'] is True
    assert nodes['production']['canBuy'] is False
    assert nodes['production']['why'] == 'Not enough YM'
    assert nodes['production-advanced']['unlocked'] is False


def test_bonus_progression_is_additive_and_one_shared_roster_bounds_effects():
    cfg, st = town()
    recruit(cfg, st)
    ticks(cfg, st, 300)
    assert W.bonuses(cfg, st, st['b'][0])['production'] == 2
    act(cfg, st, 'focus', nodeId='production')
    assert W.bonuses(cfg, st, st['b'][0])['production'] == 2.5
    st['businessProgression']['quests']['farm-signature'] = dict(completed=True)
    for node in ('production-advanced', 'sales', 'sales-advanced', 'efficiency', 'efficiency-advanced'):
        assert act(cfg, st, 'focus', nodeId=node)['ok']
    for _ in range(2):
        ticks(cfg, st, 1800)
        assert act(cfg, st, 'hire')['ok']
    ticks(cfg, st, 3000)
    assert team(st)['workers'] == 20
    for branch, effect, expected in [('production', 'production', 60), ('sales', 'customer', 60), ('efficiency', 'efficiency', 25)]:
        allocation = dict.fromkeys(W.BRANCHES, 0)
        allocation[branch] = 20
        assert act(cfg, st, 'allocate', allocation=allocation)['ok']
        result = W.bonuses(cfg, st, st['b'][0])
        assert result[effect] == expected
        assert sum(result.values()) == expected


def test_hq_capacity_and_budget_and_live_instance_validation_are_atomic():
    cfg, st = town()
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hq_upgrade')['ok']
    assert st == before
    cfg, st = town(3)
    for slot in range(3):
        recruit(cfg, st, slot)
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hq_assign', enabled=True)['ok']
    assert st == before
    initial_cash = st['cash']
    for level, cost in ((1, 300), (2, 900), (3, 2700)):
        assert act(cfg, st, 'hq_upgrade')['ok']
        assert st['workforce']['hq']['level'] == level
        assert act(cfg, st, 'hq_assign', slot=level - 1, enabled=True)['ok']
        assert len(st['workforce']['hq']['targets']) == level
        if level < 3:
            before = copy.deepcopy(st)
            assert not act(cfg, st, 'hq_assign', slot=level, enabled=True)['ok']
            assert st == before
    assert st['cash'] == initial_cash - 3900
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hq_upgrade')['ok']
    assert not act(cfg, st, 'hq_assign', enabled=1)['ok']
    assert not W.act(cfg, st, dict(action='hire', buildingId='farm'))['ok']
    assert st == before
    assert act(cfg, st, 'hq_assign', enabled=False)['ok']
    assert len(st['workforce']['hq']['targets']) == 2


def test_insufficient_money_and_ambiguous_building_reject_without_defaults_or_partial_purchase():
    cfg, st = town()
    del st['workforce']
    st['cash'] = 0
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hire')['ok']
    assert st == before
    assert act(cfg, st, 'focus', nodeId='orientation')['ok']
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hire')['ok']
    assert st == before
    st['cash'] = 1000
    st['b'].append(copy.deepcopy(st['b'][0]))
    before = copy.deepcopy(st)
    assert not act(cfg, st, 'hire')['ok']
    assert st == before


def test_legacy_paid_shift_converts_once_with_no_cash_inventory_or_building_changes():
    cfg, st = town()
    st['b'][0]['staff'] = dict(id='specialist', remainingTicks=2)
    st['b'][0].pop('buildingId')  # Migration must precede legacy instance defaults.
    original_cash, original_stock = st['cash'], copy.deepcopy(st['inventory'])
    W.ensure(cfg, st)
    assert team(st)['hires'] == team(st)['trainers'] == 1
    assert team(st)['workers'] == 0
    assert team(st)['nodes'] == ['orientation']
    assert team(st)['legacyConverted']['role'] == 'specialist'
    assert st['b'][0]['staff'] is None
    assert 'buildingId' not in st['b'][0]
    original = copy.deepcopy(st)
    W.ensure(cfg, st)
    assert st == original
    assert st['cash'] == original_cash and st['inventory'] == original_stock
    cfg, st = town()
    st['b'][0]['staff'] = dict(id='assistant', remainingTicks=0)
    W.ensure(cfg, st)
    assert st['workforce']['teams'] == {}


def test_saved_fractional_progress_and_class_cooldown_replay_identically():
    cfg, st = town(3)
    recruit(cfg, st)
    act(cfg, st, 'hq_upgrade')
    act(cfg, st, 'hq_assign', enabled=True)
    ticks(cfg, st, 675)
    restored = json.loads(json.dumps(st))
    W.ensure(cfg, restored)
    ticks(cfg, st, 1800)
    ticks(cfg, restored, 1800)
    assert restored == st
    assert W.payload(cfg, restored) == W.payload(cfg, st)


def test_reading_bonus_does_not_mutate_state_or_allow_invalid_elapsed_time():
    cfg, st = town()
    recruit(cfg, st)
    original = copy.deepcopy(st)
    for dt in (0, -1, True, '300', float('inf'), float('nan')):
        W.advance(cfg, st, dt)
    W.bonuses(cfg, st, st['b'][0])
    assert st == original
