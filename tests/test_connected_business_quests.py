"""Connected quests recognize settled business activity, without another economy."""
import copy
import json

import pytest

import business_progression as P
import production_economy as E


def town(connected=True, all_buildings=False):
    cfg = E.load_config()
    cfg['businessDesign']['connectedProgression'] = connected
    cfg['businessDesign']['researchEnabled'] = True  # these contracts cover the research rules themselves
    st = E.new_state(cfg)
    if all_buildings:
        st['tierOf'] = list(range(len(cfg['tiers'])))
        st['b'] = [E._building(i) for i in st['tierOf']]
    return cfg, st


def row(cfg, st, quest_id):
    return next(q for q in P.payload(cfg, st)['quests'] if q['id'] == quest_id)


def choose(cfg, st, quest_id):
    choice = 'regulars' if quest_id.endswith('-plan') else 'bulk'
    result = P.act(cfg, st, dict(action='quest_plan', questId=quest_id, choice=choice))
    assert result['ok'], result


def observe_goals(cfg, st, quest_id):
    for objective in row(cfg, st, quest_id)['objectives']:
        quantity = max(0, objective['quantity'] - objective['owned'])
        if objective['kind'] == 'produce':
            P.record_production(cfg, st, objective['goodId'], quantity)
        else:
            P.record_sale(cfg, st, [dict(goodId=objective['goodId'], quantity=quantity)], 'orders')


def claim(cfg, st, quest_id):
    result = P.act(cfg, st, dict(action='quest_finish', questId=quest_id))
    assert result['ok'], result


@pytest.mark.parametrize('tier_index', range(15))
def test_each_business_unlocks_then_demonstrates_its_actual_signature(tier_index):
    cfg, st = town(all_buildings=True)
    tier = cfg['tiers'][tier_index]
    first, second = tier['id'] + '-plan', tier['id'] + '-signature'
    signature = tier['goods'][2]['id']
    resources = copy.deepcopy((st['cash'], st['inventory'], st['materials']))
    assert P.product_unlocked(cfg, st, signature) == (tier_index < 3)
    assert not P.act(cfg, st, dict(action='quest_plan', questId=second, choice='bulk'))['ok']
    choose(cfg, st, first)
    assert not row(cfg, st, first)['ready']
    observe_goals(cfg, st, first)
    claim(cfg, st, first)
    assert P.product_unlocked(cfg, st, signature)
    choose(cfg, st, second)
    assert {o['goodId'] for o in row(cfg, st, second)['objectives']} == {signature}
    observe_goals(cfg, st, second)
    claim(cfg, st, second)
    assert (st['cash'], st['inventory'], st['materials']) == resources
    assert st['businessProgression']['prestige'] == st['businessProgression']['prestigeEarned'] == 2
    assert st['businessProgression']['knowHow'] == 2
    assert P.speed_bonus(cfg, st, st['b'][tier_index], tier['goods'][2]) == 5
    saved = copy.deepcopy(st)
    for action in ('quest_finish', 'quest_start', 'quest_reset', 'quest_plan'):
        assert not P.act(cfg, st, dict(action=action, questId=second, choice='bulk'))['ok']
        assert st == saved


def test_inventory_and_practice_requests_cannot_forge_business_activity():
    cfg, st = town()
    st['inventory'] = {g['id']: 1000 for g in cfg['tiers'][0]['goods']}
    choose(cfg, st, 'farm-plan')
    for action in ('quest_batch', 'quest_reset', 'quest_finish'):
        before = copy.deepcopy(st)
        assert not P.act(cfg, st, dict(action=action, questId='farm-plan', recipe='first', ready=True,
                                       objectives=[dict(ready=True)]))['ok']
        assert st == before
    q = row(cfg, st, 'farm-plan')
    assert q['mode'] == 'connected' and not q['stocks'] and not q['recipes']
    assert not q['canReset'] and q['workTotal'] == 0


def test_both_production_and_sales_are_needed_and_sources_share_one_total():
    cfg, st = town()
    choose(cfg, st, 'farm-plan')
    for objective in row(cfg, st, 'farm-plan')['objectives']:
        if objective['kind'] == 'produce':
            P.record_production(cfg, st, objective['goodId'], objective['quantity'])
    assert not row(cfg, st, 'farm-plan')['ready']
    P.record_sale(cfg, st, [dict(goodId='farm_tomatoes', quantity=1)], 'walkIns')
    P.record_sale(cfg, st, [dict(goodId='farm_tomatoes', quantity=1)], 'regularBuyers')
    P.record_sale(cfg, st, [dict(goodId='farm_tomatoes', quantity=1)], 'orders')
    P.record_sale(cfg, st, [dict(goodId='farm_tomatoes', quantity=1)], 'clearance')
    P.record_sale(cfg, st, [dict(goodId='farm_eggs', quantity=2)], 'orders')
    assert row(cfg, st, 'farm-plan')['ready']
    activity = st['businessProgression']['activity']
    assert activity['sold']['farm_tomatoes'] == 4
    assert sum(channel.get('farm_tomatoes', 0) for channel in activity['salesBySource'].values()) == 4
    claim(cfg, st, 'farm-plan')
    assert st['businessProgression']['activity'] == activity


def test_observations_survive_json_migration_and_reading_cannot_repeat_them():
    cfg, st = town()
    choose(cfg, st, 'farm-plan')
    observe_goals(cfg, st, 'farm-plan')
    restored = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    activity = copy.deepcopy(restored['businessProgression']['activity'])
    for _ in range(3):
        P.ensure(cfg, restored, migrating=True)
        assert row(cfg, restored, 'farm-plan')['ready']
        assert restored['businessProgression']['activity'] == activity
    claim(cfg, restored, 'farm-plan')
    after = copy.deepcopy(restored)
    assert not P.act(cfg, restored, dict(action='quest_finish', questId='farm-plan'))['ok']
    assert restored == after


def test_legacy_snapshot_keeps_practice_and_does_not_record_new_counters():
    cfg, st = town(connected=False)
    cfg['businessDesign'].pop('connectedProgression')
    choose(cfg, st, 'farm-plan')
    P.record_production(cfg, st, 'farm_tomatoes', 10)
    P.record_sale(cfg, st, [dict(goodId='farm_tomatoes', quantity=10)], 'orders')
    assert 'activity' not in st['businessProgression']
    assert row(cfg, st, 'farm-plan')['mode'] == 'legacy'
    for recipe in ('first', 'first', 'second', 'second'):
        assert P.act(cfg, st, dict(action='quest_batch', questId='farm-plan', recipe=recipe))['ok']
    claim(cfg, st, 'farm-plan')
    assert st['businessProgression']['prestige'] == 1


def test_started_legacy_quest_keeps_accepted_rules_after_adoption():
    cfg, st = town(connected=False)
    choose(cfg, st, 'farm-plan')
    assert P.act(cfg, st, dict(action='quest_batch', questId='farm-plan', recipe='first'))['ok']
    practice = copy.deepcopy(st['businessProgression']['quests']['farm-plan']['stock'])
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    assert row(cfg, st, 'farm-plan')['mode'] == 'legacy'
    assert st['businessProgression']['quests']['farm-plan']['stock'] == practice
    for recipe in ('first', 'second', 'second'):
        assert P.act(cfg, st, dict(action='quest_batch', questId='farm-plan', recipe=recipe))['ok']
    claim(cfg, st, 'farm-plan')
    assert row(cfg, st, 'farm-signature')['mode'] == 'connected'
    assert st['businessProgression']['prestigeEarned'] == 1


def test_earned_legacy_rewards_and_recipe_access_remain_and_prestige_is_not_doubled():
    cfg, st = town(connected=False, all_buildings=True)
    p = st['businessProgression']
    p['quests'] = {'garage-signature': dict(completed=True, choice='bulk', perkGood='garage_custom_mods')}
    p['prestige'] = 1
    p['knowHow'] = 1
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    assert P.product_unlocked(cfg, st, 'garage_custom_mods')
    assert P.speed_bonus(cfg, st, st['b'][3], cfg['tiers'][3]['goods'][2]) == 5
    assert p['prestigeEarned'] == p['prestige'] == 1
    assert not P.act(cfg, st, dict(action='quest_finish', questId='garage-signature'))['ok']


def test_spending_prestige_preserves_lifetime_expansion_qualification():
    cfg, st = town(all_buildings=True)
    p = st['businessProgression']
    p.update(prestige=1, prestigeEarned=14)
    for building, threshold in P.PRESTIGE_EXPANSIONS:
        ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == building)
        req = P.expansion_requirements(cfg, st, ti)
        assert req['ready']
        assert req['requirements'][0]['owned'] == 14
        assert req['requirements'][0]['quantity'] == threshold
    P.ensure(cfg, st, migrating=True)
    assert p['prestige'] == 1 and p['prestigeEarned'] == 14


def test_equipment_becomes_inactive_without_spending_refunds_or_value_loss():
    cfg, st = town(all_buildings=True)
    p = st['businessProgression']
    p['equipment'] = {e['id']: 1 for e in P.EQUIPMENT}
    value = P.equipment_value(cfg, st)
    resources = copy.deepcopy((st['cash'], st['inventory'], p['equipment']))
    for equipment in P.EQUIPMENT:
        ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == equipment['building'])
        assert P.expansion_requirements(cfg, st, ti)['ready']
        assert P.consume_expansion(cfg, st, ti) == dict(ok=True, consumedValue=0)
        assert not P.act(cfg, st, dict(action='craft', equipmentId=equipment['id']))['ok']
    assert (st['cash'], st['inventory'], p['equipment']) == resources
    assert P.equipment_value(cfg, st) == value
    payload = P.payload(cfg, st)
    assert not payload['equipmentEnabled']
    assert all(e['inactive'] and not e['ready'] and not e['usedFor'] for e in payload['equipment'])
    assert all('equipment' not in r['description'] for r in payload['research'])


def test_explicit_quest_quantity_override_does_not_change_other_objectives():
    cfg, st = town()
    cfg['businessDesign']['connectedQuestTargets'] = {'farm-plan': {'farm_tomatoes': 9, 'farm_eggs': -1}}
    quantities = {o['goodId']: o['quantity'] for o in row(cfg, st, 'farm-plan')['objectives']}
    assert quantities == {'farm_tomatoes': 9, 'farm_eggs': 2}


def test_adopted_practice_reset_and_reload_preserve_accepted_rules():
    cfg, st = town(connected=False)
    choose(cfg, st, 'farm-plan')
    st['businessProgression']['quests']['farm-plan'].pop('mode', None)
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    assert P.act(cfg, st, dict(action='quest_reset', questId='farm-plan'))['ok']
    st = E.State(json.loads(json.dumps(st)))
    P.ensure(cfg, st, migrating=True)
    q = row(cfg, st, 'farm-plan')
    assert q['mode'] == 'legacy' and q['status'] == 'plan'
    choose(cfg, st, 'farm-plan')
    for recipe in ('first', 'first', 'second', 'second'):
        assert P.act(cfg, st, dict(action='quest_batch', questId='farm-plan', recipe=recipe))['ok']
    claim(cfg, st, 'farm-plan')
    assert st['businessProgression']['prestigeEarned'] == 1
    assert st['businessProgression']['activity'] == dict(produced={}, sold={}, salesBySource={})


def test_an_opened_but_unchosen_legacy_quest_preserves_its_mode():
    cfg, st = town(connected=False)
    st['businessProgression']['quests']['farm-plan'] = {}
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    assert row(cfg, st, 'farm-plan')['mode'] == 'legacy'
    choose(cfg, st, 'farm-plan')
    assert row(cfg, st, 'farm-plan')['recipes']


@pytest.mark.parametrize('upgrade,good_id', [('coffee', 'roastery_espresso_shots'), ('pastry', 'roastery_pastries')])
def test_saved_finished_breakfast_keeps_unclaimed_quest_reward_once(upgrade, good_id):
    cfg, st = town(connected=False, all_buildings=True)
    st['businessProgression']['quests']['roastery-plan'] = dict(completed=True)
    st['businessProgression'].update(prestige=1, knowHow=1)
    st['breakfastEvent'] = dict(stage=5, upgrade=upgrade)
    resources = copy.deepcopy((st['cash'], st['inventory'], st['materials']))
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    q = row(cfg, st, 'roastery-signature')
    assert q['mode'] == 'legacy' and q['ready'] and q['linkedEvent'] == 'breakfast'
    assert st['businessProgression']['prestige'] == 1
    claim(cfg, st, 'roastery-signature')
    assert st['businessProgression']['quests']['roastery-signature']['perkGood'] == good_id
    assert st['businessProgression']['prestigeEarned'] == st['businessProgression']['prestige'] == 2
    good = next(g for g in cfg['tiers'][2]['goods'] if g['id'] == good_id)
    assert E.product_speed(cfg, st, st['b'][2], good) == 130
    assert (st['cash'], st['inventory'], st['materials']) == resources
    st = E.State(json.loads(json.dumps(st)))
    P.ensure(cfg, st, migrating=True)
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='quest_finish', questId='roastery-signature'))['ok']
    assert st == before


def test_already_started_breakfast_can_finish_its_promised_qualification_after_adoption():
    cfg, st = town(connected=False, all_buildings=True)
    st['businessProgression']['quests']['roastery-plan'] = dict(completed=True)
    st['breakfastEvent'] = dict(stage=2, upgrade=None)
    cfg['businessDesign']['connectedProgression'] = True
    P.ensure(cfg, st, migrating=True)
    assert row(cfg, st, 'roastery-signature')['mode'] == 'legacy'
    assert not row(cfg, st, 'roastery-signature')['ready']
    st['breakfastEvent'].update(stage=5, upgrade='coffee')
    P.ensure(cfg, st, migrating=True)
    assert row(cfg, st, 'roastery-signature')['ready']
    claim(cfg, st, 'roastery-signature')


def test_new_connected_quest_does_not_link_to_or_accept_isolated_breakfast():
    cfg, st = town(all_buildings=True)
    choose(cfg, st, 'roastery-plan')
    observe_goals(cfg, st, 'roastery-plan')
    claim(cfg, st, 'roastery-plan')
    choose(cfg, st, 'roastery-signature')
    st['breakfastEvent'] = dict(stage=5, upgrade='coffee')
    before = copy.deepcopy(st)
    P.ensure(cfg, st, migrating=True)
    q = row(cfg, st, 'roastery-signature')
    assert q['mode'] == 'connected' and q['linkedEvent'] is None and not q['ready']
    assert not P.act(cfg, st, dict(action='quest_finish', questId='roastery-signature'))['ok']
    assert st == before


def test_completed_records_are_not_renormalized_during_later_validation():
    cfg, st = town(all_buildings=True)
    st['businessProgression']['quests']['garage-signature'] = dict(completed=True)
    before = copy.deepcopy(st)
    assert P.product_unlocked(cfg, st, 'garage_custom_mods')
    P.ensure(cfg, st, migrating=True)
    assert st == before
