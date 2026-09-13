"""Focus purchases spend quest Prestige once without revoking earned access."""
import copy
import json

import pytest

import business_progression as P
import production_economy as E
import workforce as W


def town(connected=True):
    cfg = E.load_config()
    cfg['businessDesign']['connectedProgression'] = connected
    st = E.new_state(cfg)
    st['cash'] = 10000
    st['b'][0]['lv'] = 3
    p = st['businessProgression']
    p['prestige'] = 14
    if connected:
        p['prestigeEarned'] = 14
    p['quests']['farm-signature'] = dict(completed=True, perkGood='farm_honey')
    return cfg, st


def command(st, node_id):
    return dict(action='focus', buildingId=st['b'][0]['buildingId'], nodeId=node_id)


def buy(cfg, st, node_id):
    result = W.act(cfg, st, command(st, node_id))
    assert result['ok'], result
    return result


def node(cfg, st, node_id):
    return next(n for n in W.payload(cfg, st)['teams'][0]['nodes'] if n['id'] == node_id)


def test_orientation_costs_neither_cash_nor_prestige():
    cfg, st = town()
    st['cash'] = 0
    st['businessProgression']['prestige'] = 0
    result = buy(cfg, st, 'orientation')
    assert result['cost'] == result['prestigeCost'] == 0
    assert st['cash'] == st['businessProgression']['prestige'] == 0
    assert st['businessProgression']['prestigeEarned'] == 14
    assert not st['businessProgression'].get('prestigeSpent', 0)


@pytest.mark.parametrize('branch', W.BRANCHES)
def test_basic_and_advanced_focus_spend_one_then_two_plus_existing_cash(branch):
    cfg, st = town()
    buy(cfg, st, 'orientation')
    before = st['cash']
    basic = buy(cfg, st, branch)
    advanced = buy(cfg, st, branch + '-advanced')
    base_cash = cfg['tiers'][0]['upgradeBase']
    assert basic['cost'] == base_cash and basic['prestigeCost'] == 1
    assert advanced['cost'] == base_cash * 2 and advanced['prestigeCost'] == 2
    assert st['cash'] == before - base_cash * 3
    assert st['businessProgression']['prestige'] == 11
    assert st['businessProgression']['prestigeSpent'] == 3
    assert st['businessProgression']['prestigeEarned'] == 14
    assert st['workforce']['teams']['farm']['spent'] == base_cash * 3


@pytest.mark.parametrize('cash,prestige,why', [(0, 1, 'YM'), (1000, 0, 'Prestige'), (0, 0, 'Prestige')])
def test_failed_purchase_does_not_commit_any_draft_changes(cash, prestige, why):
    cfg, st = town()
    buy(cfg, st, 'orientation')
    st['cash'] = cash
    st['businessProgression']['prestige'] = prestige
    before = copy.deepcopy(st)
    result = W.act(cfg, st, dict(command(st, 'sales'), prestigeCost=0, cost=0, canBuy=True))
    assert not result['ok'] and why in result['why']
    assert st == before


def test_advanced_focus_requires_its_preceding_focus_and_completed_signature():
    cfg, st = town()
    buy(cfg, st, 'orientation')
    before = copy.deepcopy(st)
    assert not W.act(cfg, st, command(st, 'production-advanced'))['ok']
    assert st == before
    buy(cfg, st, 'production')
    st['businessProgression']['quests'].clear()
    before = copy.deepcopy(st)
    assert not W.act(cfg, st, dict(command(st, 'production-advanced'), completed=True))['ok']
    assert st == before


def test_repeated_purchase_and_reload_never_charge_the_same_node_twice():
    cfg, st = town()
    buy(cfg, st, 'orientation')
    buy(cfg, st, 'sales')
    before = copy.deepcopy(st)
    assert not W.act(cfg, st, command(st, 'sales'))['ok']
    assert st == before
    restored = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    before = copy.deepcopy(restored)
    assert not W.act(cfg, restored, command(restored, 'sales'))['ok']
    assert restored == before
    assert restored['businessProgression']['prestige'] == 13
    assert restored['businessProgression']['prestigeSpent'] == 1
    assert node(cfg, restored, 'sales')['owned']


def test_focus_spending_preserves_expansion_qualification_and_recipe_access():
    cfg, st = town()
    buy(cfg, st, 'orientation')
    for branch in W.BRANCHES:
        buy(cfg, st, branch)
        buy(cfg, st, branch + '-advanced')
    assert st['businessProgression']['prestige'] == 5
    assert st['businessProgression']['prestigeSpent'] == 9
    for building_id, threshold in P.PRESTIGE_EXPANSIONS:
        ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == building_id)
        requirements = P.expansion_requirements(cfg, st, ti)
        assert requirements['ready']
        assert requirements['requirements'][0]['owned'] == 14
    assert P.product_unlocked(cfg, st, 'farm_honey')


def test_first_purchase_initializes_lifetime_history_before_debit():
    cfg, st = town(connected=False)
    buy(cfg, st, 'orientation')
    assert 'prestigeEarned' not in st['businessProgression']
    cfg['businessDesign']['connectedProgression'] = True
    buy(cfg, st, 'efficiency')
    assert st['businessProgression']['prestige'] == 13
    assert st['businessProgression']['prestigeEarned'] == 14
    assert st['businessProgression']['prestigeSpent'] == 1


def test_previously_owned_nodes_are_preserved_without_retroactive_charges():
    cfg, st = town(connected=False)
    for node_id in ('orientation', 'production', 'production-advanced', 'sales'):
        result = buy(cfg, st, node_id)
        assert result['prestigeCost'] == 0
    cfg['businessDesign']['connectedProgression'] = True
    st['businessProgression']['prestige'] = 0
    cash = st['cash']
    team = copy.deepcopy(st['workforce']['teams']['farm'])
    for _ in range(3):
        P.ensure(cfg, st, migrating=True)
        W.ensure(cfg, st)
        rows = W.payload(cfg, st)['teams'][0]['nodes']
        assert {n['id'] for n in rows if n['owned']} == set(team['nodes'])
    assert st['workforce']['teams']['farm'] == team
    assert st['cash'] == cash and st['businessProgression']['prestige'] == 0
    assert not st['businessProgression'].get('prestigeSpent', 0)
    assert node(cfg, st, 'production-advanced')['owned']
    assert not W.act(cfg, st, command(st, 'production-advanced'))['ok']


def test_legacy_snapshot_focus_remains_cash_only():
    cfg, st = town(connected=False)
    cfg['businessDesign'].pop('connectedProgression')
    st['businessProgression']['prestige'] = 0
    buy(cfg, st, 'orientation')
    result = buy(cfg, st, 'sales')
    assert result['prestigeCost'] == 0
    assert st['businessProgression']['prestige'] == 0
    assert not W.payload(cfg, st)['prestigeCostsEnabled']
