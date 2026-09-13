"""The population is visible, persistent and deliberately has no economy role."""
from __future__ import annotations
import copy
import json
import pytest
import production_economy as E
import workforce as W
import worker_population as P


def company():
    cfg = E.load_config()
    cfg['workforce'].pop('populationFixedTotal', None)  # growth rules under test; the pin is a class setting
    st = E.new_state(cfg)
    st['cash'] = 100000
    return cfg, st


def test_growth_counts_ownership_and_new_levels_once_without_spending():
    cfg, st = company()
    assert P.summary(cfg, st)['total'] == 5
    money, goods = st['cash'], copy.deepcopy(st['inventory'])
    st['b'][0]['lv'] = 3
    assert P.summary(cfg, st)['total'] == 7
    st['b'].append(E._building(1))
    assert P.summary(cfg, st)['total'] == 12
    st['b'].pop()
    st['b'].append(E._building(1))
    st['b'][0]['lv'] = 1
    assert P.summary(cfg, st)['total'] == 12
    st['b'][0]['lv'] = 4
    assert P.summary(cfg, st)['total'] == 13
    for _ in range(3):
        st = json.loads(json.dumps(st))
        assert P.summary(cfg, st)['total'] == 13
    assert (st['cash'], st['inventory']) == (money, goods)


@pytest.mark.parametrize('legacy_count', [2, 25])
def test_migration_preserves_people_once_before_business_ids_exist(legacy_count):
    cfg, st = company()
    del st['workerPopulation']
    del st['b'][0]['buildingId']
    st['workforce']['teams'] = {'farm': dict(W._empty_team(), workers=legacy_count),
                                'fish_stall': dict(W._empty_team(), workers=3)}
    P.ensure(cfg, st)
    assert st['workerPopulation']['total'] == max(5, legacy_count + 3)
    st['b'][0]['buildingId'] = 'rebuilt'
    st['workforce']['teams']['farm']['workers'] = 999
    P.ensure(cfg, st)
    assert st['workerPopulation']['total'] == max(5, legacy_count + 3)


def test_population_and_legacy_assignments_do_not_affect_real_economy():
    cfg, ordinary = company()
    many = copy.deepcopy(ordinary)
    many['workerPopulation']['total'] = 1000000
    many['workforce']['teams']['farm'] = dict(W._empty_team(), workers=20,
        nodes=list(W.NODE_IDS), allocation=dict(production=20,sales=20,efficiency=20))
    for _ in range(80):
        for st in (ordinary, many):
            E.player_tick(cfg, {}, st, st['tick'])
    for key in ('cash','inventory','productionWork','salesWork','report','businessProgression'):
        assert many[key] == ordinary[key], key
    assert W.bonuses(cfg, many, many['b'][0]) == dict(production=0,customer=0,efficiency=0)
    assert not any(type(v) is not int for v in many['productionWork'].values())
    assert 'expertise' not in many['workforce']['teams']['farm']


def test_population_cannot_be_assigned_even_with_all_focuses_owned():
    cfg, st = company()
    st['workforce']['teams']['farm'] = dict(W._empty_team(), nodes=list(W.NODE_IDS))
    before = copy.deepcopy(st)
    for amount in (0, 1, 5):
        result = W.act(cfg, st, dict(action='allocate', buildingId=st['b'][0]['buildingId'],
                       allocation=dict(production=amount,sales=0,efficiency=0)))
        assert not result['ok']
        assert st == before


def test_hq_specialists_remain_separate_without_creating_people_or_expertise():
    cfg, st = company()
    st['workforce']['teams']['farm'] = dict(W._empty_team(), hires=1,trainers=1,nodes=['orientation'])
    st['workforce']['hq'].update(level=1,targets=['farm'])
    before = copy.deepcopy(st['workerPopulation'])
    W.advance(cfg, st, 1800)
    team = st['workforce']['teams']['farm']
    assert team['trainers'] == 3
    assert team['workers'] == 0
    assert 'expertise' not in team
    assert st['workerPopulation'] == before


def test_old_snapshots_keep_population_disabled():
    cfg, st = company()
    cfg['workforce'].pop('populationEnabled')
    before = copy.deepcopy(st)
    assert P.ensure(cfg, st) == {}
    assert not P.summary(cfg, st)['enabled']
    assert st == before
