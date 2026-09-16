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
    name = next(tier['name'] for tier in cfg['tiers'] if tier['id'] == 'garage')
    assert garage['title'] == 'Develop ' + name
    assert [o['counter'] for o in garage['objectives']] == ['sell:garage_repairs', 'sell:garage_spare_parts']
    assert dict(type='unlock_recipe', goodId='garage_custom_mods') in garage['rewards']


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
        for reward in quest['rewards']:
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
