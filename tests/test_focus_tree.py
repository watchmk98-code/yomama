"""Focus choices persist, complete once, and change the real economy."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import focus_tree as F
import production_economy as E
import quest_engine
import business_progression


@pytest.fixture
def town():
    cfg = E.load_config()
    return cfg, E.new_state(cfg, seed=71)


def own(cfg, st, *ids):
    indices = [next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == key) for key in ids]
    st['tierOf'] = indices
    st['b'] = [E._building(index) for index in indices]


def complete(cfg, st, focus_id):
    result = F.act(cfg, st, dict(action='start', focusId=focus_id))
    assert result['ok'], result
    end = st['focusTree']['active']['endsTick']
    st['tick'] = end
    assert F.advance(cfg, st, end) == focus_id


def trunk(cfg, st):
    complete(cfg, st, 'secure_harvest')
    complete(cfg, st, 'reliable_supply')


def establish_roastery(cfg, st):
    """Meet the commerce milestones through the game's real actions."""
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    slot = next(i for i, b in enumerate(st['b']) if cfg['tiers'][b['tier']]['id'] == 'roastery')
    st['cash'] += 10000
    for _ in range(2):
        assert E.buy_upgrade(cfg, st, slot, 'production')['ok']


def developed_cannery(cfg, st):
    """Fixture: a business whose existing product-line quest was completed."""
    if quest_engine.enabled(cfg):
        tier = next(t for t in cfg['tiers'] if t['id'] == 'cannery')
        quest_engine._grant(cfg, st, dict(type='unlock_recipe', goodId=tier['goods'][-1]['id']))
    else:
        business_progression.ensure(cfg, st)['quests']['cannery-signature'] = dict(completed=True)


def view(cfg, st):
    return E.payload(cfg, st, E.new_class(cfg), dict(paused=False))


def test_old_save_migration_preserves_assets_and_active_deadline(town):
    cfg, st = town
    st.pop('focusTree')
    st['cash'] = 731
    st['inventory']['farm_tomatoes'] = 9
    st['productionWork']['farm_tomatoes'] = 47
    migrated = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))), tick=100)
    assert migrated['cash'] == 731
    assert migrated['inventory']['farm_tomatoes'] == 9
    assert migrated['productionWork']['farm_tomatoes'] == 47
    assert migrated['focusTree'] == dict(version=2, completed={}, active=None, branch=None, voucherRemaining=0)
    assert F.act(cfg, migrated, dict(action='start', focusId='secure_harvest'))['ok']
    active = copy.deepcopy(migrated['focusTree']['active'])
    reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(migrated))), tick=999)
    assert reloaded['focusTree']['active'] == active
    assert F.payload(cfg, reloaded)['active']['remainingTicks'] == F.duration_ticks(cfg)


def test_timed_completion_has_no_client_shortcut_or_repeat(town):
    cfg, st = town
    assert F.act(cfg, st, dict(action='start', focusId='secure_harvest', endsTick=0))['ok']
    active = copy.deepcopy(st['focusTree']['active'])
    assert active['endsTick'] == F.duration_ticks(cfg, 'secure_harvest')
    assert active['endsTick'] * cfg['global']['tick'] == 300
    for body in (dict(action='complete', focusId='secure_harvest'), dict(action='cancel'),
                 dict(action='start', focusId='secure_harvest'), dict(action='start', focusId=['fake'])):
        before = copy.deepcopy(st)
        assert not F.act(cfg, st, body)['ok']
        assert st == before
    assert F.advance(cfg, st, active['endsTick'] - 1) is None
    assert F.advance(cfg, st, 0) is None
    assert st['focusTree']['active'] == active
    assert F.advance(cfg, st, active['endsTick']) == 'secure_harvest'
    after = copy.deepcopy(st)
    assert F.advance(cfg, st, active['endsTick'] + 100) is None
    assert not F.act(cfg, st, dict(action='start', focusId='secure_harvest'))['ok']
    assert st == after


@pytest.mark.parametrize('branch,path,other', [
    ('volume', ('preserve_surplus', 'distribution_network', 'regional_supplier'), 'local_brand'),
    ('premium', ('local_brand', 'breakfast_regulars', 'signature_experience'), 'preserve_surplus'),
])
def test_both_food_routes_remain_open_without_freight(town, branch, path, other):
    cfg, st = town
    own(cfg, st, 'farm', 'roastery', 'cannery')
    establish_roastery(cfg, st)
    assert not F.act(cfg, st, dict(action='start', focusId=path[0]))['ok']
    trunk(cfg, st)
    assert F.act(cfg, st, dict(action='start', focusId=path[0]))['ok']
    assert st['focusTree']['branch'] is None
    blocked = next(node for node in F.payload(cfg, st)['nodes'] if node['id'] == other)
    assert blocked['status'] == 'locked'  # only one active timer
    assert not F.act(cfg, st, dict(action='start', focusId=other))['ok']
    st['tick'] = st['focusTree']['active']['endsTick']
    F.advance(cfg, st, st['tick'])
    for focus_id in path[1:]:
        complete(cfg, st, focus_id)
    complete(cfg, st, 'food_empire')
    payload = F.payload(cfg, st)
    assert payload['completedCount'] == 6
    assert payload['pathNodes'] == payload['totalNodes'] == 17
    assert payload['branch'] is None
    assert payload['active'] is None
    assert F.act(cfg, st, dict(action='start', focusId=other))['ok']


def test_business_prerequisites_remain_server_authoritative(town):
    cfg, st = town
    trunk(cfg, st)
    before = copy.deepcopy(st)
    for focus_id in ('local_brand', 'preserve_surplus', 'food_empire'):
        result = F.act(cfg, st, dict(action='start', focusId=focus_id, owns=['roastery', 'cannery']))
        assert not result['ok']
        assert st == before
    own(cfg, st, 'farm', 'roastery')
    assert F.act(cfg, st, dict(action='start', focusId='local_brand'))['ok']


def test_new_focus_pacing_scales_with_business_progression_and_class_tick(town):
    cfg, st = town
    assert set(F.DURATION_MINUTES) == set(F.BY_ID)
    for tick_seconds in (15, 17, 60):
        cfg['global']['tick'] = tick_seconds
        for node in F.payload(cfg, st)['nodes']:
            target = F.DURATION_MINUTES[node['id']] * 60
            assert target <= node['durationSeconds'] < target + tick_seconds
            assert node['durationTicks'] >= 1
    assert F.DURATION_MINUTES['secure_harvest'] == 5
    assert F.DURATION_MINUTES['local_brand'] == 10
    assert F.DURATION_MINUTES['workshop_foundation'] == 20
    assert F.DURATION_MINUTES['digital_market'] == 90
    assert F.DURATION_MINUTES['connected_economy'] == 120


def test_legacy_active_focus_keeps_deadline_and_reports_its_actual_duration(town):
    cfg, st = town
    old_duration = E.ticks_per_day(cfg)
    st['focusTree']['active'] = dict(id='secure_harvest', startedTick=0, endsTick=old_duration)
    reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    view = F.payload(cfg, reloaded)
    row = next(n for n in view['nodes'] if n['id'] == 'secure_harvest')
    assert view['active']['endsTick'] == old_duration
    assert row['durationSeconds'] == 86400
    reloaded['tick'] = old_duration
    assert F.advance(cfg, reloaded, old_duration) == 'secure_harvest'
    assert F.act(cfg, reloaded, dict(action='start', focusId='reliable_supply'))['ok']
    active = reloaded['focusTree']['active']
    assert (active['endsTick'] - active['startedTick']) * cfg['global']['tick'] == 600


def test_commerce_milestones_use_real_regular_and_upgrade_actions(town):
    cfg, st = town
    own(cfg, st, 'farm', 'roastery')
    trunk(cfg, st)
    complete(cfg, st, 'local_brand')
    assert not F.act(cfg, st, dict(action='start', focusId='breakfast_regulars', regular=True))['ok']
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    complete(cfg, st, 'breakfast_regulars')
    assert not F.act(cfg, st, dict(action='start', focusId='signature_experience', level=3))['ok']
    st['cash'] = 10000
    for _ in range(2):
        assert E.buy_upgrade(cfg, st, 1, 'production')['ok']
    complete(cfg, st, 'signature_experience')


def test_packaging_waits_for_real_product_line_quest_not_disabled_research(town):
    cfg, st = town
    quest_engine.configure(cfg)
    own(cfg, st, 'farm', 'cannery', 'workshop')
    trunk(cfg, st)
    complete(cfg, st, 'preserve_surplus')
    complete(cfg, st, 'workshop_foundation')
    assert not F.act(cfg, st, dict(action='start', focusId='automated_packaging'))['ok']
    assert not business_progression.product_unlocked(cfg, st, 'cannery_preserves')
    # Deliver actual stock through the order settlement path, then claim the
    # existing quest. The focus itself neither grants nor bypasses the recipe.
    needs = [dict(goodId='cannery_canned_goods', quantity=15), dict(goodId='cannery_sauces', quantity=10)]
    for need in needs:
        st['inventory'][need['goodId']] = need['quantity']
    order = dict(id='development-delivery', name='Development delivery', requirements=needs,
                 reward=100, materials=0, customer=None, committed=False)
    st['offers'][0] = order
    assert E.fulfill_order(cfg, st, 0, order['id'])['ok']
    assert quest_engine.act(cfg, st, dict(action='quest_claim', questId='develop:cannery'))['ok']
    assert business_progression.product_unlocked(cfg, st, 'cannery_preserves')
    assert not business_progression.research_enabled(cfg)
    complete(cfg, st, 'automated_packaging')


def test_focus_bonuses_do_not_bypass_prestige_or_unlock_recipes(town):
    cfg, st = town
    quest_engine.configure(cfg)
    own(cfg, st, 'farm', 'workshop', 'solar_coop', 'cannery')
    relay = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == 'relay_station')
    gate = business_progression.expansion_requirements(cfg, st, relay)
    assert not gate['ready']
    complete(cfg, st, 'workshop_foundation')
    complete(cfg, st, 'clean_power')
    complete(cfg, st, 'powered_industry')
    assert business_progression.expansion_requirements(cfg, st, relay) == gate
    assert not business_progression.product_unlocked(cfg, st, 'cannery_preserves')
    assert st['businessProgression']['prestige'] == 0
    assert not F.act(cfg, st, dict(action='start', focusId='smart_grid'))['ok']


def test_v1_branch_migrates_without_losing_timer_rewards_or_completions(town):
    cfg, st = town
    st['focusTree'] = dict(version=1, branch='premium', completed={'local_brand': 10},
                           active=dict(id='breakfast_regulars', startedTick=10, endsTick=100),
                           voucherRemaining=731)
    before = copy.deepcopy(st['focusTree'])
    F.ensure(cfg, st)
    assert st['focusTree']['version'] == 2
    assert st['focusTree']['branch'] is None
    for key in ('completed', 'active', 'voucherRemaining'):
        assert st['focusTree'][key] == before[key]


def test_cross_business_links_require_all_parents_and_actual_ownership(town):
    cfg, st = town
    own(cfg, st, 'farm', 'cannery', 'workshop')
    trunk(cfg, st)
    complete(cfg, st, 'preserve_surplus')
    assert not F.act(cfg, st, dict(action='start', focusId='automated_packaging'))['ok']
    complete(cfg, st, 'workshop_foundation')
    own(cfg, st, 'farm', 'cannery')
    assert not F.act(cfg, st, dict(action='start', focusId='automated_packaging'))['ok']
    own(cfg, st, 'farm', 'cannery', 'workshop')
    developed_cannery(cfg, st)
    complete(cfg, st, 'automated_packaging')
    building = st['b'][1]
    assert F.speed_bonus(cfg, st, building, cfg['tiers'][building['tier']]['goods'][0]) == 15


def test_entire_global_graph_is_reachable_and_new_bonuses_apply_once(town):
    cfg, st = town
    own(cfg, st, *(tier['id'] for tier in cfg['tiers']))
    establish_roastery(cfg, st)
    developed_cannery(cfg, st)
    remaining = set(F.BY_ID)
    while remaining:
        ready = next((node for node in F.payload(cfg, st)['nodes'] if node['canStart']), None)
        assert ready, 'Graph has unreachable prerequisites: %s' % remaining
        complete(cfg, st, ready['id'])
        remaining.remove(ready['id'])
    tree = F.payload(cfg, st)
    assert tree['title'] == 'Focus Tree'
    assert tree['completedCount'] == tree['totalNodes'] == 17
    assert len({(n['column'], n['row']) for n in tree['nodes']}) == 17
    assert all(key in F.BY_ID for n in tree['nodes'] for key in n['requires'] + n['requiresAny'])
    for building in st['b']:
        tier = cfg['tiers'][building['tier']]
        expected = 10 if tier['id'] in ('workshop', 'solar_coop') else 5
        if tier['family'] in ('I', 'E'):
            assert F.speed_bonus(cfg, st, building, tier['goods'][0]) == expected
        assert F.demand_percent(cfg, st, building) == (115 if tier['id'] == 'roastery' else 105)
        assert F.storage_percent(cfg, st, tier) == (145 if tier['id'] == 'farm' else 125 if tier['family'] in ('F', 'I') else 110)
    reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert F.payload(cfg, reloaded)['completedCount'] == 17
    assert not F.act(cfg, reloaded, dict(action='start', focusId='connected_economy'))['ok']


def test_focus_completion_boundary_and_offline_clock(town):
    cfg, st = town
    assert F.act(cfg, st, dict(action='start', focusId='secure_harvest'))['ok']
    deadline = st['focusTree']['active']['endsTick']
    st['tick'] = deadline - 1
    st['lastActiveTick'] = st['tick']
    E.advance_class(cfg, E.new_class(cfg), [st], st['tick'], deadline)
    assert st['focusTree']['completed']['secure_harvest'] == deadline
    assert F.act(cfg, st, dict(action='start', focusId='reliable_supply'))['ok']
    deadline = st['focusTree']['active']['endsTick']
    # No production allowance remains, but development uses the class clock.
    st['lastActiveTick'] = -E.ticks_per_day(cfg)
    E.advance_class(cfg, E.new_class(cfg), [st], st['tick'], deadline)
    assert st['focusTree']['completed']['reliable_supply'] == deadline
    assert st['report']['offlineTicksSkipped'] == F.duration_ticks(cfg, 'reliable_supply')


def test_production_bonus_makes_real_goods_and_storage_matches_quotes(town):
    cfg, st = town
    cfg['production']['sectorRhythms'] = False
    st['cash'] = 100000
    base_capacity = E.warehouse_cap(cfg, st)[0]
    base_speed = E.product_speed(cfg, st, st['b'][0], cfg['tiers'][0]['goods'][0])
    complete(cfg, st, 'secure_harvest')
    good = cfg['tiers'][0]['goods'][0]
    assert E.product_speed(cfg, st, st['b'][0], good) == base_speed + 5
    st['productionWork'][good['id']] = good['cycleTicks'] * 100 - base_speed - 5
    baseline = copy.deepcopy(st)
    baseline['focusTree']['completed'] = {}
    E._produce(cfg, baseline)
    E._produce(cfg, st)
    assert baseline['inventory'].get(good['id'], 0) == 0
    assert st['inventory'][good['id']] == good['quantity']
    complete(cfg, st, 'reliable_supply')
    assert E.warehouse_cap(cfg, st)[0] == int(base_capacity * 1.2)
    payload = view(cfg, st)
    assert payload['buildings'][0]['capacity'] == E.warehouse_cap(cfg, st)[0]
    after = copy.deepcopy(st)
    after['b'][0]['storage'] += 1
    assert payload['buildings'][0]['upgrades']['storage']['effect'] == '{} → {} spaces'.format(
        E.warehouse_cap(cfg, st)[0], E.warehouse_cap(cfg, after)[0])


def test_volume_bonuses_apply_to_real_order_payment_once(town):
    cfg, st = town
    own(cfg, st, 'farm', 'roastery', 'cannery')
    trunk(cfg, st)
    cannery = st['b'][2]
    cannery_good = cfg['tiers'][cannery['tier']]['goods'][0]
    base_speed = E.product_speed(cfg, st, cannery, cannery_good)
    complete(cfg, st, 'preserve_surplus')
    assert E.product_speed(cfg, st, cannery, cannery_good) == base_speed + 10
    complete(cfg, st, 'distribution_network')
    st['offers'][0] = dict(id='focus-delivery', name='Focus delivery', requirements=[dict(goodId='farm_tomatoes', quantity=2)],
                           reward=100, materials=0, customer=None, committed=False)
    st['inventory']['farm_tomatoes'] = 2
    assert view(cfg, st)['contracts']['offers'][0]['reward'] == 108
    assert st['offers'][0]['reward'] == 100
    assert view(cfg, st)['contracts']['offers'][0]['reward'] == 108
    before = st['cash']
    result = E.fulfill_order(cfg, st, 0, 'focus-delivery')
    assert result['ok'] and result['reward'] == 108
    assert st['cash'] - before == 108
    assert st['inventory']['farm_tomatoes'] == 0
    assert not E.fulfill_order(cfg, st, 0, 'focus-delivery')['ok']
    complete(cfg, st, 'regional_supplier')
    assert F.storage_percent(cfg, st, cfg['tiers'][0]) == 135
    assert F.storage_percent(cfg, st, cfg['tiers'][cannery['tier']]) == 115
    industry = next(tier for tier in cfg['tiers'] if tier['family'] == 'I')
    assert F.storage_percent(cfg, st, industry) == 100


def test_premium_regular_quotes_payment_forecast_and_signature_speed(town):
    cfg, st = town
    own(cfg, st, 'farm', 'roastery')
    trunk(cfg, st)
    roastery = st['b'][1]
    demand = E.customer_demand(cfg, st, roastery)
    complete(cfg, st, 'local_brand')
    assert E.customer_demand(cfg, st, roastery) == demand * 110 // 100
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    contract = st['customerContracts']['active'][0]
    original = contract['reward']
    original_income = E._flows(cfg, st)[1]['incomePerMinute']
    complete(cfg, st, 'breakfast_regulars')
    quoted = E.customer_contract_payload(cfg, st)['active'][0]['reward']
    assert quoted == E.jsround(original * 1.08)
    assert contract['reward'] == quoted
    assert E._flows(cfg, st)[1]['incomePerMinute'] == pytest.approx(original_income * quoted / original)
    st['inventory']['farm_tomatoes'] = 6
    before = st['cash']
    E._tick_customer_contracts(cfg, st, contract['nextDeliveryTick'])
    assert st['cash'] - before == quoted
    assert st['customerContracts']['earned'] == quoted
    assert st['inventory']['farm_tomatoes'] == 0
    reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert reloaded['customerContracts']['active'][0]['reward'] == quoted
    foods = [tier for tier in cfg['tiers'] if tier['family'] == 'F']
    before_speeds = {tier['id']: E.product_speed(cfg, st, E._building(cfg['tiers'].index(tier)), tier['goods'][-1]) for tier in foods}
    st['cash'] += 10000
    for _ in range(2):
        assert E.buy_upgrade(cfg, st, 1, 'production')['ok']
    complete(cfg, st, 'signature_experience')
    for tier in foods:
        building = E._building(cfg['tiers'].index(tier))
        assert E.product_speed(cfg, st, building, tier['goods'][-1]) == before_speeds[tier['id']] + 10
        assert F.speed_bonus(cfg, st, building, tier['goods'][0]) == (5 if tier['id'] == 'farm' else 0)


@pytest.mark.parametrize('quests_enabled', [False, True])
def test_capstone_voucher_is_spendable_with_old_or_new_rules_and_never_regranted(quests_enabled):
    cfg = E.load_config()
    if quests_enabled:
        quest_engine.configure(cfg)
    st = E.new_state(cfg, seed=77)
    own(cfg, st, 'farm', 'roastery')
    establish_roastery(cfg, st)
    trunk(cfg, st)
    for focus_id in ('local_brand', 'breakfast_regulars', 'signature_experience', 'food_empire'):
        complete(cfg, st, focus_id)

    def remaining(state):
        return (sum(v['remaining'] for v in state.get('questEngine', {}).get('vouchers', []))
                + state['focusTree']['voucherRemaining'])

    assert remaining(st) == 1000
    st['cash'] = 0
    quote = view(cfg, st)['buildings'][0]['upgrades']['production']
    assert quote['canBuy'] and quote['cashCost'] == 0
    result = E.buy_upgrade(cfg, st, 0, 'production')
    assert result['ok'] and result['voucherPaid'] == result['cost']
    assert st['cash'] == 0
    assert remaining(st) == 1000 - result['cost']
    reloaded = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert F.advance(cfg, reloaded, st['tick'] + E.ticks_per_day(cfg)) is None
    assert not F.act(cfg, reloaded, dict(action='start', focusId='food_empire'))['ok']
    assert remaining(reloaded) == 1000 - result['cost']
