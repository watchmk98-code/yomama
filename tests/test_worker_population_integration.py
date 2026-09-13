"""Real business growth updates a count without staffing requirements."""
from __future__ import annotations
import copy
import json
import business_operations as O
import production_economy as E
import worker_population as P


def test_growth_follows_finished_construction_and_survives_real_closure():
    cfg = E.load_config()
    cfg['workforce'].pop('populationFixedTotal', None)  # growth rules under test
    st = E.new_state(cfg)
    st['cash'] = 1000000
    for kind in ('sales','storage'):
        assert E.buy_upgrade(cfg,st,0,kind)['ok']
        assert P.summary(cfg,st)['total'] == 5
    assert E.buy_upgrade(cfg,st,0,'production')['ok']
    assert P.summary(cfg,st)['total'] == 6
    assert E.expand(cfg,st,1,st['tick'])['ok']
    assert P.summary(cfg,st)['total'] == 6
    E.finish_build(cfg,st,st['build']['t'])
    assert P.summary(cfg,st)['total'] == 11
    st['townProjects']['completed'] = 3
    assert O.manage(cfg,st,dict(action='salvage',buildingId=st['b'][1]['buildingId']))['ok']
    assert P.summary(cfg,st)['total'] == 11
    st['tick'] += 300 // cfg['global']['tick']
    assert E.expand(cfg,st,1,st['tick'])['ok']
    E.finish_build(cfg,st,st['build']['t'])
    assert P.summary(cfg,st)['total'] == 11
    before = copy.deepcopy(st['workerPopulation'])
    for _ in range(3):
        st = E.migrate_state(cfg,json.loads(json.dumps(st)))
        assert st['workerPopulation'] == before


def test_population_neither_blocks_empty_businesses_nor_grows_with_elapsed_time():
    cfg = E.load_config()
    cfg['workforce'].pop('populationFixedTotal', None)  # growth rules under test
    st = E.new_state(cfg)
    st['workerPopulation']['total'] = 0
    for _ in range(40):
        E.player_tick(cfg,{},st,st['tick'])
    assert st['report']['unitsProduced'] > 0
    assert st['workerPopulation']['total'] == 0
