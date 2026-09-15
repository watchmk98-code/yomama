"""Connected objectives follow actual engine settlements and class transactions."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import business_progression as P
import game_api as A
import production_economy as E
import town_projects as G
from test_production_api import town, state, edit  # noqa: F401


def connected_config():
    cfg = E.load_config()
    cfg['businessDesign']['groupProjectsEnabled'] = True
    return cfg


def ticks(cfg, st, count):
    for _ in range(count):
        E.player_tick(cfg, {}, st, st['tick'])


def quest(cfg, st, quest_id='farm-plan'):
    return next(q for q in P.payload(cfg, st)['quests'] if q['id'] == quest_id)


def test_actual_production_and_shopping_complete_quest_without_spending_stock_twice():
    cfg = connected_config()
    st = E.new_state(cfg)
    assert P.act(cfg, st, dict(action='quest_plan', questId='farm-plan', choice='regulars'))['ok']
    assert not quest(cfg, st)['ready']
    ticks(cfg, st, 120)
    assert quest(cfg, st)['ready']
    before = copy.deepcopy((st['cash'], st['inventory']))
    assert P.act(cfg, st, dict(action='quest_finish', questId='farm-plan'))['ok']
    assert (st['cash'], st['inventory']) == before
    assert st['businessProgression']['prestige'] == 1
    saved = copy.deepcopy(st)
    assert not P.act(cfg, st, dict(action='quest_finish', questId='farm-plan'))['ok']
    assert st == saved


def test_failed_delivery_does_not_credit_quests_or_group_then_one_payment_counts_for_both():
    cfg = connected_config()
    st = E.new_state(cfg)
    st['offers'][0] = dict(id='integration-order', name='Tomato delivery', requirements=[
        dict(goodId='farm_tomatoes', quantity=6)], reward=19, materials=0, committed=False)
    before = copy.deepcopy(st)
    assert not E.fulfill_order(cfg, st, 0, 'integration-order')['ok']
    assert st == before
    assert E.commit_order(cfg, st, 0, 'integration-order', True)['ok']
    ticks(cfg, st, 100)
    inventory, cash = copy.deepcopy(st['inventory']), st['cash']
    assert E.fulfill_order(cfg, st, 0, 'integration-order')['ok']
    assert st['inventory']['farm_tomatoes'] == inventory['farm_tomatoes'] - 6
    assert st['cash'] == cash + 19
    assert st['businessProgression']['activity']['salesBySource']['orders']['farm_tomatoes'] == 6
    assert G.group_payload(cfg, st)['current']['canClaim']
    inventory, cash = copy.deepcopy(st['inventory']), st['cash']
    result = E.claim_group_project(cfg, st, 'farm_neighbors')
    assert result['ok'] and st['cash'] == cash + result['cashReward']
    assert st['inventory'] == inventory
    before = copy.deepcopy(st)
    assert not E.claim_group_project(cfg, st, 'farm_neighbors')['ok']
    assert not E.fulfill_order(cfg, st, 0, 'integration-order')['ok']
    assert st == before


@pytest.mark.parametrize('channel', ['regularBuyers', 'clearance'])
def test_automatic_buyers_and_clearance_count_sales_but_not_group_order_deliveries(channel):
    cfg = connected_config()
    st = E.new_state(cfg)
    if channel == 'regularBuyers':
        assert E.manage_customer_contract(cfg, st, 0, 'accept', 'corner_grocer')['ok']
        ticks(cfg, st, 100)
    else:
        st['b'][0]['reserve'] = True
        ticks(cfg, st, 100)
        st['b'][0]['reserve'] = False
        assert E.sell_one(cfg, st, 0)['ok']
    assert st['businessProgression']['activity']['salesBySource'][channel]['farm_tomatoes'] > 0
    assert not G.group_payload(cfg, st)['current']['canClaim']
    assert G.group_payload(cfg, st)['current']['requirements'][0]['delivered'] == 0


def test_forecasts_and_saved_inventory_do_not_invent_activity():
    cfg = connected_config()
    st = E.new_state(cfg)
    st['inventory'] = {g['id']: 100 for g in cfg['tiers'][0]['goods']}
    for _ in range(3):
        E.payload(cfg, st, E.new_class(cfg), {'paused': False})
        E.flow_rates(cfg, st)
    assert st['businessProgression']['activity'] == dict(produced={}, sold={}, salesBySource={})
    assert not quest(cfg, st)['ready']


def test_disabled_business_design_does_not_partially_enable_group_tracking():
    cfg = connected_config()
    cfg['businessDesign']['enabled'] = False
    st = E.new_state(cfg)
    assert st['offers'][2]['project']
    assert not G.group_payload(cfg, st)['enabled']
    G.record_delivery(cfg, st, [dict(goodId='farm_tomatoes', quantity=6)], 'disabled-order')
    assert 'groupProgress' not in st['townProjects']
    assert 'businessProgression' not in st


def test_legacy_fixed_delivery_migrates_outside_three_active_containers_and_keeps_terms():
    legacy = connected_config()
    legacy['businessDesign'].pop('connectedProgression')
    st = E.new_state(legacy)
    saved = copy.deepcopy(st['offers'][2])
    assert E.commit_order(legacy, st, 2, saved['id'], True)['ok']
    saved['committed'] = True
    cfg = connected_config()
    st = E.migrate_state(cfg, st)
    assert len(st['offers']) == 3 and not any(o.get('project') for o in st['offers'])
    assert st['legacyProjectOffer'] == saved
    assert E.order_reservations(st)['farm_tomatoes'] == 6
    ticks(cfg, st, 100)
    view = E.payload(cfg, st, E.new_class(cfg), {'paused': False})
    assert view['groupProjects']['legacyDelivery']['canFulfill']
    cash, stock = st['cash'], st['inventory']['farm_tomatoes']
    assert E.fulfill_legacy_project(cfg, st, saved['id'])['ok']
    assert st['cash'] == cash + saved['reward']
    assert st['inventory']['farm_tomatoes'] == stock - 6
    assert 'legacyProjectOffer' not in st
    assert st['townProjects']['completed'] == 1
    before = copy.deepcopy(st)
    assert not E.fulfill_legacy_project(cfg, st, saved['id'])['ok']
    assert st == before
    assert E.migrate_state(cfg, E.State(json.loads(json.dumps(st)))) == st


def test_new_board_has_three_rerollable_product_orders_without_legacy_loyalty_credit():
    cfg = connected_config()
    st = E.new_state(cfg)
    for index in range(3):
        order = st['offers'][index]
        assert not order.get('project') and order['customer'] is None
        assert E.replace_order(cfg, st, index, order['id'])['ok']
    order = st['offers'][2]
    st['inventory'].update({n['goodId']: n['quantity'] for n in order['requirements']})
    assert E.fulfill_order(cfg, st, 2, order['id'])['ok']
    assert not st.get('regularDeliveries')


def test_api_simultaneous_quest_claims_award_one_prestige_and_persist(town):
    now, _, players = town
    token, other = [p['token'] for p in players]
    A.econ_progression(dict(token=token, action='quest_plan', questId='farm-plan', choice='regulars'))
    now[0] += 600
    A._book_cache.clear()
    assert next(q for q in state(token)['progression']['quests'] if q['id'] == 'farm-plan')['ready']
    def finish(_):
        try:
            return A.econ_progression(dict(token=token, action='quest_finish', questId='farm-plan'))
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, range(2)))
    assert sum(r is not None for r in results) == 1
    A._book_cache.clear()
    assert state(token)['progression']['prestige'] == 1
    assert state(other)['progression']['prestige'] == 0


def test_api_simultaneous_focus_purchases_share_scarce_prestige_across_branches(town):
    _, _, players = town
    token, other = [p['token'] for p in players]
    def prepare(cfg, st):
        st['cash'] = 10000
        st['b'][0]['lv'] = 3
        st['businessProgression'].update(prestige=1, prestigeEarned=1)
    edit(token, prepare)
    identity = state(token)['buildings'][0]['buildingId']
    before = A.econ_workforce(dict(token=token, action='focus', buildingId=identity, nodeId='orientation'))
    def buy(node):
        try:
            return A.econ_workforce(dict(token=token, action='focus', buildingId=identity, nodeId=node))
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(buy, ('production', 'sales')))
    assert sum(r is not None for r in results) == 1
    A._book_cache.clear()
    after = state(token)
    assert after['progression']['prestige'] == 0 and after['progression']['prestigeEarned'] == 1
    assert sum(n['owned'] for n in after['workforce']['teams'][0]['nodes']) == 2
    cost = next(n['cost'] for n in before['workforce']['teams'][0]['nodes'] if n['id'] == 'production')
    assert after['cash'] == before['cash'] - cost
    assert state(other)['progression']['prestige'] == 0


def test_api_group_claim_is_unavailable_and_other_seat_is_unchanged(town):
    _, _, players = town
    token, other = [p['token'] for p in players]
    def prepare(cfg, st):
        st['offers'][0] = dict(id='api-group-order', name='Tomatoes', requirements=[
            dict(goodId='farm_tomatoes', quantity=6)], reward=15, materials=0, committed=True)
        ticks(cfg, st, 100)
        assert E.fulfill_order(cfg, st, 0, 'api-group-order')['ok']
    edit(token, prepare)
    before = state(token)
    def claim(_):
        try:
            return A.econ_progression(dict(token=token, action='group_project_claim', projectId='farm_neighbors'))
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert all(r is None for r in results)
    A._book_cache.clear()
    after = state(token)
    assert after['cash'] == before['cash']
    assert not after['groupProjects']['enabled']
    assert not state(other)['groupProjects']['enabled']
    assert len(after['contracts']['offers']) == 3
