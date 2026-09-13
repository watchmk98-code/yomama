"""Rules for the testing period: research and Know-how are closed, the worker
head count is pinned. Both are class settings in config/economy.v4.json, so
a class gets them at reset and keeps them until its rules are re-stamped."""
import json
from pathlib import Path

import business_progression as P
import production_economy as E
import worker_population as W

ROOT = Path(__file__).resolve().parents[1]


def town(**design):
    cfg = E.load_config()
    cfg['businessDesign'].update(design)
    st = E.new_state(cfg)
    st['cash'] = 1000000
    P.ensure(cfg, st)
    return cfg, st


def test_shipped_rules_close_research_and_pin_workers():
    cfg = json.loads((ROOT / 'config' / 'economy.v4.json').read_text())
    assert cfg['businessDesign']['researchEnabled'] is False
    assert cfg['workforce']['populationFixedTotal'] == 104


def test_research_is_closed_unreachable_and_ineffective():
    cfg, st = town()
    assert not P.research_enabled(cfg)
    payload = P.payload(cfg, st)
    assert payload['researchEnabled'] is False
    assert payload['research'] == []
    assert payload['knowHow'] == 0
    assert all('Know-how' not in q['rewardText'] for q in payload['quests'])
    result = P.act(cfg, st, dict(action='research', researchId='food-basics'))
    assert result == dict(ok=False, why=P.RESEARCH_CLOSED)
    # Even a smuggled research entry in a save changes nothing.
    st['businessProgression']['research'].append('food-basics')
    st['businessProgression']['knowHow'] = 5
    tier = cfg['tiers'][st['b'][0]['tier']]
    assert P.speed_bonus(cfg, st, st['b'][0], tier['goods'][0]) == 0
    assert P.payload(cfg, st)['knowHow'] == 0


def test_completed_quest_pays_prestige_only_while_research_is_closed():
    cfg, st = town()
    p = st['businessProgression']
    spec = next(iter(P._quest_specs(cfg).values()))
    result = P._complete_quest(cfg, st, spec, {})
    assert result['ok'] and 'Know-how' not in result['message']
    assert p['prestige'] == 1 and p['knowHow'] == 0


def test_research_rule_defaults_on_for_older_stamped_rules():
    cfg, st = town()
    cfg['businessDesign'].pop('researchEnabled')
    assert P.research_enabled(cfg)
    assert P.payload(cfg, st)['research']
    cfg['businessDesign']['researchEnabled'] = True
    result = P._complete_quest(cfg, st, next(iter(P._quest_specs(cfg).values())), {})
    assert 'Know-how' in result['message'] and st['businessProgression']['knowHow'] == 1


def test_worker_head_count_is_pinned_but_growth_is_still_recorded():
    cfg, st = town()
    assert W.summary(cfg, st)['total'] == 104
    st['tierOf'] = list(range(6))
    st['b'] = [E._building(i) for i in st['tierOf']]
    assert W.summary(cfg, st)['total'] == 104
    assert st['workerPopulation']['total'] > 5
    cfg['workforce'].pop('populationFixedTotal')
    assert W.summary(cfg, st)['total'] == st['workerPopulation']['total']
    cfg['workforce']['populationFixedTotal'] = 0
    assert W.summary(cfg, st)['total'] == st['workerPopulation']['total']
