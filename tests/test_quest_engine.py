"""Quests observe real activity, grant each reward once, and stay off by default."""
from __future__ import annotations

import copy
import json

import production_economy as economy
import quest_engine as quests


def town(businesses=1):
    cfg = quests.configure(economy.load_config())
    state = economy.new_state(cfg, seed=59)
    state['cash'] = 0
    state['tierOf'] = list(range(businesses))
    state['b'] = [economy._building(tier) for tier in state['tierOf']]
    quests.ensure(cfg, state)
    return cfg, state


def claim(cfg, state, quest_id):
    return quests.act(cfg, state, dict(action='quest_claim', questId=quest_id))


def row(cfg, state, quest_id):
    return next((r for r in quests.payload(cfg, state)['quests'] if r['id'] == quest_id), None)


def row_for(cfg, state, quest_id):
    """The row whether or not it is currently visible, for daily assertions."""
    return quests._row(cfg, state, quests.quests(cfg)[quest_id])


# ------------------------------------------------------------------ defaults

def test_default_rules_leave_quests_off_and_state_untouched():
    cfg = economy.load_config()
    state = economy.new_state(cfg, seed=59)
    assert not quests.enabled(cfg)
    before = copy.deepcopy(state)
    quests.ensure(cfg, state)
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=5)], 'orders')
    quests.record_action(cfg, state, 'upgrade')
    assert not claim(cfg, state, 'first-crop')['ok']
    assert quests.payload(cfg, state) == dict(enabled=False, quests=[], boosts=[],
                                              vouchers=[], features=[], recent=[])
    assert state == before


def test_configuration_survives_a_class_snapshot():
    cfg = economy.load_config()
    original = copy.deepcopy(cfg)
    assert quests.configure(cfg) is cfg and quests.enabled(cfg)
    assert quests.enabled(json.loads(json.dumps(cfg)))
    assert not quests.enabled(original)


# ---------------------------------------------------------------- definitions

def test_template_expands_to_one_quest_per_business_but_not_the_opening_three():
    cfg, _ = town()
    table = quests.quests(cfg)
    template = {qid for qid in table if qid.startswith('develop:')}
    assert len(template) == 12
    assert 'develop:farm' not in table and 'develop:garage' in table
    garage = table['develop:garage']
    # The rewards are generated from the tier so they cannot drift...
    assert dict(type='unlock_recipe', goodId='garage_custom_mods') in garage['rewards']
    assert dict(type='flag', name='business_developed:garage') in garage['rewards']
    # ...while the half a player reads is authored per business.
    assert garage['title'] == 'Back on the Road'
    assert [o['counter'] for o in garage['objectives']] == ['sell:garage_repairs', 'sell:garage_spare_parts']


def test_each_business_gets_its_own_quest_rather_than_twelve_of_the_same():
    cfg, _ = town()
    rows = [q for q in quests.quests(cfg).values() if q['id'].startswith('develop:')]
    assert len(rows) == 12
    for field in ('title', 'summary', 'teaches'):
        values = [q[field] for q in rows]
        assert len(set(values)) == 12, 'duplicate %s across develop quests' % field
    # Not all twelve ask the same thing: some want goods made, not sold.
    counters = {o['counter'].split(':')[0] for q in rows for o in q['objectives']}
    assert counters == {'sell', 'produce'}
    for quest in rows:
        building = quest['buildingId']
        for objective in quest['objectives']:
            assert objective['counter'].split(':', 1)[1].startswith(building), \
                '%s asks for a good from another business' % quest['id']


def test_every_reference_in_the_content_resolves():
    cfg, _ = town()
    goods = {g['id'] for t in cfg['tiers'] for g in t['goods']}
    businesses = {t['id'] for t in cfg['tiers']}
    table = quests.quests(cfg)
    for quest in table.values():
        for dependency in quest.get('appear', {}).get('afterQuests', ()):
            assert dependency in table, quest['id']
        owns = quest.get('appear', {}).get('ownsBusiness')
        assert owns is None or owns in businesses, quest['id']
        for objective in quest['objectives']:
            counter = objective.get('counter', '')
            if counter.startswith('sell:') and ':' not in counter[5:] and counter != 'sell:any':
                assert counter[5:] in goods, quest['id']
        branches = list(quest.get('rewards', ()))
        for choice in quest.get('choices', ()):
            assert choice.get('id') and choice.get('label'), quest['id']
            branches.extend(choice.get('rewards', ()))
        assert branches, quest['id']
        for reward in branches:
            if 'goodId' in reward:
                assert reward['goodId'] in goods, quest['id']
            if reward['type'] == 'grant_building':
                assert reward['businessId'] in businesses, quest['id']


# ---------------------------------------------------------------- observation

def test_sales_count_once_across_every_counter_a_quest_can_watch():
    cfg, state = town()
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=4)], 'orders')
    counters = state['questEngine']['counters']
    assert counters['sell:farm_tomatoes'] == 4
    assert counters['sell:business:farm'] == 4
    assert counters['sell:any'] == 4
    assert counters['sell:source:orders'] == 4
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=1)], 'walkIns')
    assert counters['sell:any'] == 5 and counters['sell:source:orders'] == 4


def test_observation_refuses_unknown_goods_and_nonsense_quantities():
    cfg, state = town()
    quests.record_sale(cfg, state, [dict(goodId='not_a_good', quantity=5)], 'orders')
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=-3)], 'orders')
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=1.5)], 'orders')
    quests.record_production(cfg, state, 'farm_tomatoes', 0)
    quests.record_action(cfg, state, 'upgrade', 0)
    assert state['questEngine']['counters'] == {}


# -------------------------------------------------------------------- claims

def test_a_quest_is_claimable_only_once_its_real_goals_are_met():
    cfg, state = town()
    assert row(cfg, state, 'first-crop')['status'] == 'available'
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=4)], 'walkIns')
    assert row(cfg, state, 'first-crop')['status'] == 'tracking'
    assert not claim(cfg, state, 'first-crop')['ok']
    assert state['cash'] == 0
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=6)], 'walkIns')
    assert row(cfg, state, 'first-crop')['ready']
    assert claim(cfg, state, 'first-crop')['ok']
    assert state['cash'] == 40
    assert row(cfg, state, 'first-crop')['status'] == 'done'


def test_a_reward_is_never_granted_twice():
    cfg, state = town()
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=10)], 'walkIns')
    assert claim(cfg, state, 'first-crop')['ok']
    before = copy.deepcopy(state)
    assert not claim(cfg, state, 'first-crop')['ok']
    assert state == before


def test_a_refused_claim_changes_nothing():
    cfg, state = town()
    before = copy.deepcopy(state)
    for body in (dict(action='quest_claim', questId='no-such-quest'),
                 dict(action='nonsense', questId='first-crop'),
                 dict(action='quest_claim', questId='first-crop'), 'not a dict'):
        assert not quests.act(cfg, state, body)['ok']
    assert state == before


def test_hidden_quests_stay_out_of_the_payload_until_their_conditions_hold():
    cfg, state = town()
    assert row(cfg, state, 'harbour-lunch') is None
    assert row(cfg, state, 'develop:garage') is None
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=10)], 'walkIns')
    claim(cfg, state, 'first-crop')
    quests.record_sale(cfg, state, [dict(goodId='farm_eggs', quantity=15)], 'walkIns')
    quests.record_sale(cfg, state, [dict(goodId='farm_honey', quantity=8)], 'walkIns')
    claim(cfg, state, 'three-crops')
    quests.record_order(cfg, state)
    quests.record_order(cfg, state)
    quests.record_order(cfg, state)
    assert claim(cfg, state, 'first-delivery')['ok']
    # The fish stall is earned by the group project, not by this quest.
    assert not quests.building_grant(cfg, state, 'fish_stall')
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=6)], 'orders')
    assert claim(cfg, state, 'group-farm-supply')['ok']
    assert quests.building_grant(cfg, state, 'fish_stall')
    assert row(cfg, state, 'harbour-lunch') is None      # still needs the stall built
    state['tierOf'] = [0, 1]
    state['b'] = [economy._building(0), economy._building(1)]
    assert row(cfg, state, 'harbour-lunch')['status'] == 'available'


# ------------------------------------------------------------------- rewards

def test_a_building_grant_is_consumed_once():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='grant_building', businessId='fish_stall'))
    quests._grant(cfg, state, dict(type='grant_building', businessId='fish_stall'))
    assert state['questEngine']['grants'] == ['fish_stall']
    assert quests.consume_building_grant(cfg, state, 'fish_stall')
    assert not quests.consume_building_grant(cfg, state, 'fish_stall')


def test_a_recipe_unlock_opens_exactly_one_advanced_product():
    cfg, state = town()
    assert not quests.product_unlocked(cfg, state, 'garage_custom_mods')
    assert quests.product_unlocked(cfg, state, 'garage_repairs')      # ordinary line
    assert quests.product_unlocked(cfg, state, 'roastery_pastries')   # opening three
    quests._grant(cfg, state, dict(type='unlock_recipe', goodId='garage_custom_mods'))
    assert quests.product_unlocked(cfg, state, 'garage_custom_mods')
    assert not quests.product_unlocked(cfg, state, 'workshop_machined_bolts')


def test_speed_perks_accumulate_per_good():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='speed_perk', goodId='farm_honey', percent=5))
    quests._grant(cfg, state, dict(type='speed_perk', goodId='farm_honey', percent=5))
    assert quests.speed_bonus(cfg, state, 'farm_honey') == 10
    assert quests.speed_bonus(cfg, state, 'farm_eggs') == 0


# -------------------------------------------------------------------- boosts

def test_a_boost_multiplies_real_payouts_and_spends_one_charge_each_time():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='boost', metric='order_payout', multiplier=2, charges=3))
    assert quests.apply_boost(cfg, state, 'order_payout', 50) == (100, 2)
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (20, 2)
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (20, 2)
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (10, 0)


def test_a_boost_is_not_spent_on_a_worthless_sale_or_another_metric():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='boost', metric='order_payout', multiplier=2, charges=1))
    assert quests.apply_boost(cfg, state, 'order_payout', 0) == (0, 0)
    assert quests.apply_boost(cfg, state, 'production_output', 80) == (80, 0)
    assert quests.apply_boost(cfg, state, 'not_a_metric', 80) == (80, 0)
    assert quests.apply_boost(cfg, state, 'order_payout', 80) == (160, 2)


def test_boosts_queue_instead_of_compounding():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='boost', metric='order_payout', multiplier=2, charges=1))
    quests._grant(cfg, state, dict(type='boost', metric='order_payout', multiplier=3, charges=1))
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (20, 2)
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (30, 3)
    assert quests.apply_boost(cfg, state, 'order_payout', 10) == (10, 0)


# ------------------------------------------------------------------ vouchers

def test_a_voucher_pays_down_one_upgrade_and_keeps_its_change():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='upgrade_voucher', amount=500))
    assert quests.apply_voucher(cfg, state, 200) == (0, 200)
    assert quests.apply_voucher(cfg, state, 400) == (100, 300)
    assert quests.apply_voucher(cfg, state, 50) == (50, 0)


def test_a_voucher_never_pays_more_than_the_cost():
    cfg, state = town()
    quests._grant(cfg, state, dict(type='upgrade_voucher', amount=500))
    assert quests.apply_voucher(cfg, state, 100) == (0, 100)
    assert state['questEngine']['vouchers'][0]['remaining'] == 400


# ------------------------------------------------------- choices and dailies

def test_a_choice_quest_grants_only_the_branch_that_was_picked():
    cfg, state = town()
    quest = quests.quests(cfg)['cafe-opening']
    data = quests.ensure(cfg, state)
    for objective in quest['objectives']:
        data['counters'][objective['counter']] = objective['target']
    for dependency in quest['appear'].get('afterQuests', ()):
        data['completed'][dependency] = dict(tick=0)
    state['tierOf'] = [0, 1, 2]
    state['b'] = [economy._building(t) for t in state['tierOf']]
    cash = state['cash']
    assert quests.act(cfg, state, dict(action='quest_claim', questId='cafe-opening'))['ok'] is False
    assert quests.act(cfg, state, dict(action='quest_claim', questId='cafe-opening',
                                       choiceId='perk'))['ok']
    assert state['cash'] == cash                                  # cash branch not taken
    assert quests.speed_bonus(cfg, state, 'roastery_pastries') == 10
    # act() commits by replacing the state, so the pre-claim handle is stale.
    assert quests.ensure(cfg, state)['choices']['cafe-opening'] == 'perk'


def test_an_unknown_choice_is_refused_and_changes_nothing():
    cfg, state = town()
    quest = quests.quests(cfg)['cafe-opening']
    data = quests.ensure(cfg, state)
    for objective in quest['objectives']:
        data['counters'][objective['counter']] = objective['target']
    for dependency in quest['appear'].get('afterQuests', ()):
        data['completed'][dependency] = dict(tick=0)
    before = copy.deepcopy(state)
    assert not quests.act(cfg, state, dict(action='quest_claim', questId='cafe-opening',
                                           choiceId='not-a-branch'))['ok']
    assert state == before


def test_a_scoped_objective_ignores_everything_earned_before_it_armed():
    cfg, state = town(businesses=3)
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=500)], 'walkIns')
    row = row_for(cfg, state, 'daily-sales')
    assert row['objectives'][0]['owned'] == 0, 'a lifetime total must not complete a daily'
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=100)], 'walkIns')
    assert row_for(cfg, state, 'daily-sales')['ready']


def test_a_daily_re_arms_the_next_day_with_a_larger_target():
    cfg, state = town(businesses=3)
    base = row_for(cfg, state, 'daily-sales')['objectives'][0]['quantity']
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=base)], 'walkIns')
    assert claim(cfg, state, 'daily-sales')['ok']
    waiting = row_for(cfg, state, 'daily-sales')
    assert waiting['status'] == 'waiting' and waiting['waitSeconds'] > 0
    assert not claim(cfg, state, 'daily-sales')['ok'], 'one outstanding daily at a time'
    state['tick'] += quests.ticks_per_day(cfg)
    tomorrow = row_for(cfg, state, 'daily-sales')
    assert tomorrow['status'] != 'waiting' and tomorrow['day'] == 2
    assert tomorrow['objectives'][0]['quantity'] > base
    assert tomorrow['objectives'][0]['owned'] == 0, 'yesterday must not count toward today'


def test_a_daily_reward_grows_with_its_target():
    cfg, state = town(businesses=3)
    for day in range(2):
        target = row_for(cfg, state, 'daily-sales')['objectives'][0]['quantity']
        quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=target)], 'walkIns')
        before = state['cash']
        assert claim(cfg, state, 'daily-sales')['ok']
        paid = state['cash'] - before
        state['tick'] += quests.ticks_per_day(cfg)
        if day == 0:
            first = paid
    assert paid > first, 'day two should pay more than day one'


def test_absence_does_not_stack_daily_rewards():
    """Four days away must leave one daily waiting, not four. Banking sales
    before the break must not pre-complete it either: the round re-arms from
    the counters as they stand, so today's work is today's."""
    cfg, state = town(businesses=3)
    target = row_for(cfg, state, 'daily-sales')['objectives'][0]['quantity']
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=target * 10)], 'walkIns')
    assert claim(cfg, state, 'daily-sales')['ok']

    state['tick'] += quests.ticks_per_day(cfg) * 4          # four days away
    today = row_for(cfg, state, 'daily-sales')
    assert today['status'] != 'waiting' and today['day'] == 2
    assert today['objectives'][0]['owned'] == 0
    assert not claim(cfg, state, 'daily-sales')['ok'], 'sales banked before the break do not count'

    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=today['objectives'][0]['quantity'])], 'walkIns')
    assert claim(cfg, state, 'daily-sales')['ok']
    assert not claim(cfg, state, 'daily-sales')['ok'], 'still only one daily per day'


def test_every_live_check_in_the_content_is_one_the_engine_implements():
    cfg, _ = town()
    known = set(quests.LIVE_CHECKS) | {'own:businesses', 'businesses_at_level'}
    for quest in quests.quests(cfg).values():
        for objective in quest['objectives']:
            if objective.get('kind') == 'state':
                check = objective['check']
                assert check in known or check.startswith(('level:', 'unlocked:')), \
                    '%s wants %s' % (quest['id'], check)



# ------------------------------------------------------------ group projects

def test_group_projects_count_order_deliveries_and_not_shop_sales():
    """The opening projects were always about deliveries. A walk-in sale of the
    same good must not advance them."""
    cfg, state = town()
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=20)], 'walkIns')
    assert row_for(cfg, state, 'group-farm-supply')['objectives'][0]['owned'] == 0
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=6)], 'orders')
    assert row_for(cfg, state, 'group-farm-supply')['ready']


def test_group_projects_run_in_order_and_grant_each_building_once():
    cfg, state = town()
    assert row(cfg, state, 'group-seafood') is None          # locked behind the first
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=6)], 'orders')
    assert claim(cfg, state, 'group-farm-supply')['ok']
    assert quests.consume_building_grant(cfg, state, 'fish_stall')
    assert not quests.consume_building_grant(cfg, state, 'fish_stall')
    assert row(cfg, state, 'group-seafood') is not None


def test_the_cafe_project_opens_regular_buyers():
    cfg, state = town()
    data = quests.ensure(cfg, state)
    for dependency in ('group-farm-supply', 'group-seafood'):
        data['completed'][dependency] = dict(tick=0)
    quests.record_sale(cfg, state, [dict(goodId='roastery_espresso_shots', quantity=4),
                                    dict(goodId='roastery_pastries', quantity=2)], 'orders')
    assert state.get('regularDeliveries', 0) < 3
    assert claim(cfg, state, 'group-cafe')['ok']
    assert state['regularDeliveries'] >= 3


def test_only_the_group_projects_hand_out_buildings():
    """Two systems must never fund the same business."""
    cfg, _ = town()
    granting = {q['id'] for q in quests.quests(cfg).values()
                for r in q.get('rewards', ()) if r.get('type') == 'grant_building'}
    assert granting == {'group-farm-supply', 'group-seafood'}


def test_group_projects_are_group_scale_not_filed_under_one_business():
    cfg, _ = town()
    for qid in ('group-farm-supply', 'group-seafood', 'group-cafe'):
        assert quests.quests(cfg)[qid]['buildingId'] is None, qid
