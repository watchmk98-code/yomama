"""Legacy snapshots retain practice recipes and atomic permanent rewards."""
import copy
import json
from collections import Counter

import pytest

import business_progression as P
import business_operations as O
import production_economy as E


def town(all_buildings=False):
    cfg = E.load_config()
    cfg['businessDesign']['connectedProgression'] = False
    cfg['businessDesign']['researchEnabled'] = True  # these contracts cover the research rules themselves
    st = E.new_state(cfg)
    P.ensure(cfg, st)
    if all_buildings:
        st['tierOf'] = list(range(len(cfg['tiers'])))
        st['b'] = [E._building(i) for i in st['tierOf']]
    return cfg, st


def act(cfg, st, action, **body):
    result = P.act(cfg, st, dict(action=action, **body))
    assert result['ok'], result
    return result


def finish_quest(cfg, st, quest_id, choice):
    act(cfg, st, 'quest_plan', questId=quest_id, choice=choice)
    if quest_id.endswith('-plan'):
        batches = [('first', 2), ('second', 2)] if choice == 'regulars' else [('first', 1), ('second', 3)]
    else:
        batches = [('prepare', 3), ('finish', 2)] if choice == 'careful' else [('prepare', 2), ('finish', 2)]
    for recipe, count in batches:
        for _ in range(count):
            act(cfg, st, 'quest_batch', questId=quest_id, recipe=recipe)
    row = next(q for q in P.payload(cfg, st)['quests'] if q['id'] == quest_id)
    assert row['ready'] and all(g['ready'] for g in row['goals'])
    act(cfg, st, 'quest_finish', questId=quest_id)


def test_two_distinct_quests_for_each_business_and_every_choice_attainable():
    for plan, signature in [('regulars', 'careful'), ('special', 'bulk')]:
        cfg, st = town(all_buildings=True)
        st.update(cash=100, inventory={'farm_tomatoes': 13})
        resources = copy.deepcopy((st['cash'], st['inventory']))
        quests = P.payload(cfg, st)['quests']
        assert Counter(q['buildingId'] for q in quests) == {t['id']: 2 for t in cfg['tiers']}
        assert len({q['title'] for q in quests}) == 30
        assert len(set(P.PLAN_PROFILES.values())) >= 12
        for tier in cfg['tiers']:
            finish_quest(cfg, st, tier['id'] + '-plan', plan)
            finish_quest(cfg, st, tier['id'] + '-signature', signature)
            assert P.product_unlocked(cfg, st, tier['goods'][-1]['id'])
        assert st['businessProgression']['knowHow'] == 30
        assert st['businessProgression']['prestige'] == 30
        assert (st['cash'], st['inventory']) == resources
        assert all(q['status'] == 'done' for q in P.payload(cfg, st)['quests'])


def test_plans_require_different_mix_and_preserve_only_chosen_perk():
    cfg, st = town()
    finish_quest(cfg, st, 'farm-plan', 'special')
    goods = cfg['tiers'][0]['goods']
    assert P.speed_bonus(cfg, st, st['b'][0], goods[0]) == 0
    assert P.speed_bonus(cfg, st, st['b'][0], goods[1]) == 5
    assert not st['businessProgression']['quests']['farm-plan'].get('cash')


def test_locked_town_quest_and_prerequisite_cannot_be_forged():
    cfg, st = town()
    for body in [dict(action='quest_plan', questId='garage-plan', choice='regulars', unlocked=True),
                 dict(action='quest_finish', questId='farm-signature', ready=True),
                 dict(action='quest_finish', questId='farm-plan', ready=True),
                 dict(action='quest_batch', questId='farm-plan', recipe='first', stock={'raw': 100}),
                 dict(action='quest_plan', questId=[], choice='regulars')]:
        before = copy.deepcopy(st)
        assert not P.act(cfg, st, body)['ok']
        assert st == before


def test_work_budget_and_recipe_inputs_enforced_and_reset_cannot_mint_rewards():
    cfg, st = town()
    act(cfg, st, 'quest_plan', questId='farm-plan', choice='regulars')
    for _ in range(6):
        act(cfg, st, 'quest_batch', questId='farm-plan', recipe='first')
    for action, args in [('quest_batch', {'recipe': 'second'}), ('quest_finish', {}), ('quest_plan', {'choice': 'special'})]:
        before = copy.deepcopy(st)
        assert not P.act(cfg, st, dict(action=action, questId='farm-plan', **args))['ok']
        assert st == before
    act(cfg, st, 'quest_reset', questId='farm-plan')
    assert st['businessProgression']['knowHow'] == 0
    finish_quest(cfg, st, 'farm-plan', 'regulars')
    finish_quest(cfg, st, 'farm-signature', 'bulk')
    for action in ['quest_finish', 'quest_reset', 'quest_start', 'quest_plan']:
        before = copy.deepcopy(st)
        assert not P.act(cfg, st, dict(action=action, questId='farm-plan', choice='regulars'))['ok']
        assert st == before
    assert st['businessProgression']['knowHow'] == 2


def test_signature_recipe_requires_preparation_before_assembly():
    cfg, st = town()
    finish_quest(cfg, st, 'farm-plan', 'regulars')
    act(cfg, st, 'quest_plan', questId='farm-signature', choice='careful')
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='quest_batch', questId='farm-signature', recipe='finish'))['ok']
    assert st == before
    for _ in range(2):
        act(cfg, st, 'quest_batch', questId='farm-signature', recipe='prepare')
        act(cfg, st, 'quest_batch', questId='farm-signature', recipe='finish')
    assert not P.act(cfg, st, dict(action='quest_finish', questId='farm-signature'))['ok'], 'Careful plan must keep two prepared components.'
    act(cfg, st, 'quest_batch', questId='farm-signature', recipe='prepare')
    act(cfg, st, 'quest_finish', questId='farm-signature')


def test_first_three_businesses_keep_opening_goods_and_new_signature_locks():
    cfg, st = town(all_buildings=True)
    for tier in cfg['tiers'][:3]:
        assert all(P.product_unlocked(cfg, st, g['id']) for g in tier['goods'])
    for tier in cfg['tiers'][3:]:
        assert all(P.product_unlocked(cfg, st, g['id']) for g in tier['goods'][:2])
        assert not P.product_unlocked(cfg, st, tier['goods'][-1]['id'])
    finish_quest(cfg, st, 'garage-plan', 'regulars')
    finish_quest(cfg, st, 'garage-signature', 'careful')
    assert P.product_unlocked(cfg, st, 'garage_custom_mods')


def test_migration_grandfathers_existing_ownership_only_once_and_survives_reload():
    cfg, st = town(all_buildings=True)
    st['tierOf'] = [0, 3]
    st['b'] = [E._building(0), E._building(3)]
    st.pop('businessProgression')
    P.ensure(cfg, st, migrating=True)
    assert P.product_unlocked(cfg, st, 'garage_custom_mods')
    st['tierOf'].append(4)
    st['b'].append(E._building(4))
    reloaded = json.loads(json.dumps(st))
    P.ensure(cfg, reloaded, migrating=True)
    assert not P.product_unlocked(cfg, reloaded, 'workshop_machined_bolts')
    assert reloaded['businessProgression']['grandfathered'] == ['farm', 'garage']
    reloaded['tierOf'] = [0]
    assert P.product_unlocked(cfg, reloaded, 'garage_custom_mods'), 'Salvage must preserve old recipe entitlement.'


def test_new_state_migration_never_bypasses_quest_gate():
    cfg, st = town(all_buildings=True)
    assert st['businessProgression']['grandfathered'] == []
    P.ensure(cfg, st, migrating=True)
    assert not P.product_unlocked(cfg, st, 'garage_custom_mods')


def test_legacy_snapshot_remains_disabled_without_mutation():
    cfg, st = town()
    cfg.pop('businessDesign')
    st.pop('businessProgression')
    before = copy.deepcopy(st)
    P.ensure(cfg, st, migrating=True)
    assert not P.payload(cfg, st)['enabled']
    assert P.product_unlocked(cfg, st, 'garage_custom_mods')
    assert P.speed_bonus(cfg, st, st['b'][0], cfg['tiers'][0]['goods'][0]) == 0
    assert not P.act(cfg, st, dict(action='quest_start', questId='farm-plan'))['ok']
    assert st == before


def test_research_checks_family_cost_prerequisites_and_is_not_replayable():
    cfg, st = town()
    finish_quest(cfg, st, 'farm-plan', 'regulars')
    finish_quest(cfg, st, 'farm-signature', 'careful')
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='research', researchId='food-basics'))['ok']
    assert st == before
    st['cash'] = 10000
    for research_id in ['food-mastery', 'industry-basics']:
        before = copy.deepcopy(st)
        assert not P.act(cfg, st, dict(action='research', researchId=research_id))['ok']
        assert st == before
    act(cfg, st, 'research', researchId='food-basics')
    assert st['cash'] == 9700
    assert st['businessProgression']['knowHow'] == 0
    assert st['businessProgression']['prestige'] == 2, 'Prestige is reputation, never spent.'
    assert P.speed_bonus(cfg, st, st['b'][0], cfg['tiers'][0]['goods'][0]) == 15
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='research', researchId='food-basics'))['ok']
    assert st == before


def test_equipment_consumes_only_free_inventory_and_gate_consumes_exactly_once():
    cfg, st = town(all_buildings=True)
    st['businessProgression']['research'] = ['food-basics']
    st['inventory'] = {'garage_spare_parts': 3, 'workshop_steel_brackets': 2}
    st['offers'] = [dict(id='reserved-work', committed=True, requirements=[dict(goodId='garage_spare_parts', quantity=1)])]
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='craft', equipmentId='preservation-kit'))['ok']
    assert st == before
    st['offers'] = []
    ti = next(i for i, t in enumerate(cfg['tiers']) if t['id'] == 'cannery')
    assert not P.expansion_requirements(cfg, st, ti)['ready']
    act(cfg, st, 'craft', equipmentId='preservation-kit')
    assert st['inventory'] == {'garage_spare_parts': 0, 'workshop_steel_brackets': 0}
    assert P.expansion_requirements(cfg, st, ti)['ready']
    assert P.consume_expansion(cfg, st, ti)['ok']
    before = copy.deepcopy(st)
    assert not P.consume_expansion(cfg, st, ti)['ok']
    assert st == before


def test_every_equipment_dependency_precedes_its_building_and_research_is_affordable_in_knowhow():
    cfg, st = town(all_buildings=True)
    tiers = {t['id']: i for i, t in enumerate(cfg['tiers'])}
    sources = {g['id']: i for i, t in enumerate(cfg['tiers']) for g in t['goods']}
    for e in P.EQUIPMENT:
        assert all(sources[gid] < tiers[e['building']] for gid in e['inputs'])
        assert all(P.product_unlocked(cfg, st, gid) for gid in e['inputs']), 'Equipment sources must not depend on signature quests.'
    assert sum(r['knowHowCost'] for r in P.RESEARCH) <= len(cfg['tiers']) * 2
    assert all(P.expansion_requirements(cfg, st, i)['ready'] for i in range(3))


def test_breakfast_completion_can_earn_roastery_signature_without_replaying_practice():
    cfg, st = town(all_buildings=True)
    finish_quest(cfg, st, 'roastery-plan', 'regulars')
    st['breakfastEvent'] = dict(stage=5, upgrade='coffee')
    q = next(q for q in P.payload(cfg, st)['quests'] if q['id'] == 'roastery-signature')
    assert q['ready'] and q['linkedEvent'] == 'breakfast'
    act(cfg, st, 'quest_finish', questId='roastery-signature')
    assert st['businessProgression']['quests']['roastery-signature']['perkGood'] == 'roastery_espresso_shots'
    before = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='quest_finish', questId='roastery-signature'))['ok']
    assert st == before


def test_crafting_and_installation_preserve_equipment_value_without_cash_salvage_credit():
    cfg, st = town()
    st['tierOf'] = list(range(6))
    st['b'] = [E._building(i) for i in st['tierOf']]
    st['cash'] = 1_000_000
    st['businessProgression']['research'] = ['food-basics']
    st['inventory'] = {'garage_spare_parts': 3, 'workshop_steel_brackets': 2}
    E._sync_pools(cfg, st)
    before = E.net_worth(st)
    act(cfg, st, 'craft', equipmentId='preservation-kit')
    kit_value = 3 * E.catalog(cfg)['garage_spare_parts']['unitPrice'] + 2 * E.catalog(cfg)['workshop_steel_brackets']['unitPrice']
    assert P.equipment_value(cfg, st) == st['businessProgression']['equipmentValue'] == kit_value
    assert E.net_worth(st) == before, 'Crafting changes the form of the asset, not its book value.'
    quote = E.can_expand(cfg, st, 6)
    assert quote['ok'], quote
    result = E.expand(cfg, st, 6, 0)
    assert result['ok'], result
    assert P.equipment_value(cfg, st) == 0
    assert E.net_worth(st) == before, 'Installed equipment moves from kit inventory into building book value.'
    E.finish_build(cfg, st, st['build']['t'])
    building = st['b'][-1]
    assert building['cashInvested'] == quote['cost']
    assert building['bookValue'] == quote['cost'] + kit_value


def prestige_expansion_town(building_id):
    cfg, st = town()
    ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == building_id)
    st['tierOf'] = list(range(ti))
    st['b'] = [E._building(i) for i in st['tierOf']]
    st['cash'] = 1_000_000_000
    # Settle metadata once before checking atomic rejected transactions.
    E.can_expand(cfg, st, ti)
    return cfg, st, ti


@pytest.mark.parametrize('building_id,threshold', P.PRESTIGE_EXPANSIONS)
def test_prestige_construction_requires_earned_reputation_and_keeps_it(building_id, threshold):
    cfg, st, ti = prestige_expansion_town(building_id)
    quest_ids = [tier['id'] + suffix for tier in cfg['tiers'][:ti]
                 for suffix in ('-plan', '-signature')]
    assert len(quest_ids) >= threshold, 'Every qualification must be earnable before the target business opens.'
    for quest_id in quest_ids[:threshold - 1]:
        finish_quest(cfg, st, quest_id, 'regulars' if quest_id.endswith('-plan') else 'careful')
    before = copy.deepcopy(st)
    refusal = E.expand(cfg, st, ti, st['tick'])
    assert not refusal['ok'] and refusal['why'] == 'Need 1 more Prestige'
    assert st == before, 'An unmet qualification must not debit cash, materials, or reputation.'
    need = refusal['requirements'][0]
    assert need['kind'] == need['id'] == 'prestige'
    assert need['quantity'] == threshold and need['owned'] == threshold - 1 and not need['ready']
    quest_id = quest_ids[threshold - 1]
    finish_quest(cfg, st, quest_id, 'regulars' if quest_id.endswith('-plan') else 'careful')
    milestone = next(row for row in P.payload(cfg, st)['prestigeMilestones'] if row['buildingId'] == building_id)
    assert milestone['current'] == threshold and milestone['ready'] and not milestone['owned']
    cash = st['cash']
    result = E.expand(cfg, st, ti, st['tick'])
    assert result['ok'], result
    assert st['cash'] == cash - result['cost']
    assert st['businessProgression']['prestige'] == threshold
    E.finish_build(cfg, st, st['build']['t'])
    assert next(row for row in P.payload(cfg, st)['prestigeMilestones'] if row['buildingId'] == building_id)['owned']
    for _ in range(2):
        assert P.consume_expansion(cfg, st, ti)['ok']
    assert st['businessProgression']['prestige'] == threshold, 'Qualifications must never spend reputation.'


@pytest.mark.parametrize('flag', [None, False])
def test_older_class_snapshots_do_not_gain_prestige_gates_on_json_migration(flag):
    cfg, st, ti = prestige_expansion_town('turbine_field')
    if flag is None:
        cfg['businessDesign'].pop('prestigeExpansion')
    else:
        cfg['businessDesign']['prestigeExpansion'] = flag
    saved_cfg = json.dumps(cfg, sort_keys=True)
    preserved = copy.deepcopy((st['cash'], st['materials'], st['tierOf'], st['businessProgression']))
    st = E.migrate_state(cfg, json.loads(json.dumps(st)))
    assert (st['cash'], st['materials'], st['tierOf'], st['businessProgression']) == preserved
    assert json.dumps(cfg, sort_keys=True) == saved_cfg
    assert P.payload(cfg, st)['prestigeMilestones'] == []
    assert P.expansion_requirements(cfg, st, ti) == dict(ready=True, requirements=[], why='')
    assert E.expand(cfg, st, ti, st['tick'])['ok'], 'An earlier snapshot must retain its cash-only construction.'
    assert st['businessProgression']['prestige'] == 0


def test_prestige_and_earned_quests_survive_closure_rebuild_and_json_reload():
    cfg, st, ti = prestige_expansion_town('turbine_field')
    for tier in cfg['tiers'][:3]:
        finish_quest(cfg, st, tier['id'] + '-plan', 'regulars')
        finish_quest(cfg, st, tier['id'] + '-signature', 'careful')
    assert E.expand(cfg, st, ti, st['tick'])['ok']
    E.finish_build(cfg, st, st['build']['t'])
    finish_quest(cfg, st, 'turbine_field-plan', 'regulars')
    finish_quest(cfg, st, 'turbine_field-signature', 'careful')
    rewards = copy.deepcopy(st['businessProgression'])
    business_id = st['b'][-1]['buildingId']
    closed = O.manage(cfg, st, dict(action='salvage', buildingId=business_id))
    assert closed['ok'], closed
    st = E.migrate_state(cfg, json.loads(json.dumps(st)))
    assert st['businessProgression'] == rewards
    milestone = next(row for row in P.payload(cfg, st)['prestigeMilestones'] if row['buildingId'] == 'turbine_field')
    assert milestone['current'] == 8 and milestone['ready'] and not milestone['owned']
    st['tick'] += 300 // cfg['global']['tick']
    assert E.expand(cfg, st, ti, st['tick'])['ok']
    E.finish_build(cfg, st, st['build']['t'])
    assert st['b'][-1]['buildingId'] != business_id
    assert st['businessProgression'] == rewards
    assert P.product_unlocked(cfg, st, 'turbine_field_green_certificates')
    assert not P.act(cfg, st, dict(action='quest_finish', questId='turbine_field-signature'))['ok']
    assert st['businessProgression'] == rewards, 'Rebuilding must not replay reputation rewards.'


def test_expansion_research_and_equipment_link_to_their_correct_branch():
    cfg, st = town()
    for equipment in P.EQUIPMENT:
        ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == equipment['building'])
        research = next(row for row in P.RESEARCH if row['id'] == equipment['research'])
        for row in P.expansion_requirements(cfg, st, ti)['requirements']:
            assert row['branch'] == research['branch'] and row['researchId'] == research['id']
        card = next(row for row in P.payload(cfg, st)['equipment'] if row['id'] == equipment['id'])
        assert card['branch'] == research['branch'] and card['researchId'] == research['id']
        assert card['buildingId'] == equipment['building']
        assert not card['researchReady']
    st['businessProgression']['research'] = [row['id'] for row in P.RESEARCH]
    assert all(card['researchReady'] and not card['ready'] for card in P.payload(cfg, st)['equipment']), 'Known research must remain distinguishable from missing ingredients.'
