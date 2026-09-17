"""Opening guidance follows real saved stock, settled cash and persisted goals."""
from __future__ import annotations

import copy
import json

import production_economy as E


def town():
    cfg = E.load_config()
    cfg['businessDesign']['connectedProgression'] = True
    cfg['businessDesign']['groupProjectsEnabled'] = True
    return cfg, E.new_state(cfg, seed=293)


def view(cfg, st):
    return E.payload(cfg, st, E.new_class(cfg), {'paused': False})


def replay(cfg, st, ticks):
    start = st['tick']
    E.advance_class(cfg, E.new_class(cfg), [st], start, start + ticks)


def ordinary(st, index, order_id, requirements, reward):
    st['offers'][index] = dict(id=order_id, name='Neighborhood delivery',
                              requirements=[dict(goodId=gid, quantity=qty)
                                            for gid, qty in requirements.items()],
                              reward=reward, materials=0, committed=False)
    return st['offers'][index]


def test_first_goal_uses_real_production_and_pays_delivery_and_claim_once_each():
    cfg, st = town()
    random_offers = copy.deepcopy(st['offers'])
    initial = view(cfg, st)
    offer = initial['goalOrder']
    assert offer['offerIndex'] == 3 and len(initial['contracts']['offers']) == 3
    assert offer['requirements'][0]['quantity'] == 6 and not offer['canFulfill']
    assert offer['etaSeconds'] is None and offer['etaIfSavedSeconds'] == 90
    assert E.commit_order(cfg, st, 3, offer['id'], True)['ok']
    assert E.order_reservations(st)['farm_tomatoes'] == 6
    assert view(cfg, st)['goalOrder']['etaSeconds'] == 90
    assert not E.fulfill_order(cfg, st, 3, offer['id'])['ok']
    replay(cfg, st, 6)
    ready = view(cfg, st)
    assert ready['goalOrder']['canFulfill'] and ready['goalOrder']['etaSeconds'] == 0
    assert st['inventory']['farm_tomatoes'] == 6 and st['cash'] == 0
    assert E.fulfill_order(cfg, st, 3, offer['id'])['ok']
    delivered = view(cfg, st)
    assert st['inventory']['farm_tomatoes'] == 0 and st['cash'] == 15
    assert delivered['goalOrder'] is None
    assert delivered['groupProjects']['current']['canClaim']
    assert delivered['earnings']['bySource']['orders'] == 15
    assert delivered['earnings']['bySource']['events'] == 0
    inventory = copy.deepcopy(st['inventory'])
    assert E.claim_group_project(cfg, st, 'farm_neighbors')['ok']
    claimed = view(cfg, st)
    assert st['cash'] == 30 and st['inventory'] == inventory
    assert claimed['earnings']['bySource']['orders'] == 15
    assert claimed['earnings']['bySource']['events'] == 15
    assert st['cStats']['done'] == 1 and st['offers'] == random_offers
    saved = copy.deepcopy(st)
    assert not E.fulfill_order(cfg, st, 3, offer['id'])['ok']
    assert not E.claim_group_project(cfg, st, 'farm_neighbors')['ok']
    assert st == saved, 'Retrying either transaction must not pay or consume twice.'


def test_saved_goal_terms_survive_another_delivery_then_release_resizes_and_rejects_stale_id():
    cfg, st = town()
    short = ordinary(st, 0, 'small-neighborhood-delivery', {'farm_tomatoes': 2}, 5)
    unchanged = copy.deepcopy(st['offers'][1:])
    goal = copy.deepcopy(st['goalOffer'])
    assert E.commit_order(cfg, st, 0, short['id'], True)['ok']
    assert E.commit_order(cfg, st, 3, goal['id'], True)['ok']
    replay(cfg, st, 8)
    assert E.fulfill_order(cfg, st, 0, short['id'])['ok']
    current = view(cfg, st)['goalOrder']
    assert current['id'] == goal['id'] and current['requirements'][0]['quantity'] == 6
    assert current['reward'] == goal['reward']
    assert view(cfg, st)['groupProjects']['current']['requirements'][0]['delivered'] == 2
    assert st['offers'][1:] == unchanged
    assert E.commit_order(cfg, st, 3, goal['id'], False)['ok']
    resized = view(cfg, st)['goalOrder']
    assert resized['requirements'][0]['quantity'] == 4 and resized['reward'] == 10
    assert resized['id'] != goal['id']
    saved = copy.deepcopy(st)
    assert not E.fulfill_order(cfg, st, 3, goal['id'])['ok']
    assert not E.commit_order(cfg, st, 3, goal['id'], True)['ok']
    assert st == saved
    cash = st['cash']
    assert E.fulfill_order(cfg, st, 3, resized['id'])['ok']
    assert st['cash'] == cash + 10 and st['inventory']['farm_tomatoes'] == 2


def test_other_delivery_cannot_spend_goods_already_saved_for_the_goal():
    cfg, st = town()
    other = ordinary(st, 0, 'same-goods-another-buyer', {'farm_tomatoes': 6}, 15)
    goal_id = st['goalOffer']['id']
    assert E.commit_order(cfg, st, 3, goal_id, True)['ok']
    replay(cfg, st, 6)
    frozen = copy.deepcopy(st)
    assert not E.fulfill_order(cfg, st, 0, other['id'])['ok']
    assert st == frozen and st['inventory']['farm_tomatoes'] == 6
    assert E.fulfill_order(cfg, st, 3, goal_id)['ok']
    assert st['inventory']['farm_tomatoes'] == 0 and st['offers'][0] == other


def test_claim_releases_leftover_goal_allocation_and_preserves_other_saved_orders():
    cfg, st = town()
    other = ordinary(st, 0, 'ordinary-completes-goal', {'farm_tomatoes': 6}, 15)
    eggs = ordinary(st, 1, 'keep-this-egg-order', {'farm_eggs': 2}, 10)
    assert E.commit_order(cfg, st, 0, other['id'], True)['ok']
    assert E.commit_order(cfg, st, 1, eggs['id'], True)['ok']
    assert E.commit_order(cfg, st, 3, st['goalOffer']['id'], True)['ok']
    replay(cfg, st, 12)
    assert E.fulfill_order(cfg, st, 0, other['id'])['ok']
    assert view(cfg, st)['groupProjects']['current']['canClaim']
    assert st['goalOffer']['committed'] and st['inventory']['farm_tomatoes'] == 6
    random_offers = copy.deepcopy(st['offers'])
    cash, inventory = st['cash'], copy.deepcopy(st['inventory'])
    assert E.claim_group_project(cfg, st, 'farm_neighbors')['ok']
    assert st['cash'] == cash + 15 and st['inventory'] == inventory
    assert st.get('goalOffer') is None and st['offers'] == random_offers
    assert E.order_reservations(st) == {'farm_eggs': 2}


def test_all_three_goal_deliveries_are_achievable_with_the_normal_engine_and_grants():
    cfg, st = town()
    random_offers = copy.deepcopy(st['offers'])
    goals = [('farm_neighbors', {'farm_tomatoes': 6}, 'fish_stall'),
             ('harbor_lunch', {'fish_stall_smoked_fish': 2, 'fish_stall_oysters': 4}, 'roastery'),
             ('cafe_opening', {'roastery_espresso_shots': 4, 'roastery_pastries': 2}, None)]
    for project_id, quantities, next_business in goals:
        offer = view(cfg, st)['goalOrder']
        assert offer and offer['projectId'] == project_id
        assert {row['goodId']: row['quantity'] for row in offer['requirements']} == quantities
        assert E.commit_order(cfg, st, 3, offer['id'], True)['ok']
        for _ in range(80):
            if view(cfg, st)['goalOrder']['canFulfill']:
                break
            replay(cfg, st, 1)
        assert view(cfg, st)['goalOrder']['canFulfill'], 'The small offer must finish at normal speed.'
        cash = st['cash']
        assert E.fulfill_order(cfg, st, 3, offer['id'])['ok']
        assert st['cash'] == cash + offer['reward']
        cash, inventory = st['cash'], copy.deepcopy(st['inventory'])
        claim = E.claim_group_project(cfg, st, project_id)
        assert claim['ok'] and st['cash'] == cash + claim['cashReward']
        assert st['inventory'] == inventory and st['offers'] == random_offers
        if next_business:
            waiting = view(cfg, st)
            assert waiting['goalOrder'] is None
            tier = next(i for i, row in enumerate(cfg['tiers']) if row['id'] == next_business)
            before = st['cash'], st['materials']
            assert E.expand(cfg, st, tier, st['tick'])['ok']
            assert (st['cash'], st['materials']) == before
            replay(cfg, st, st['build']['t'] - st['tick'] + 1)
            # Completing construction can introduce that business's offers;
            # claiming the next project must still leave those offers alone.
            random_offers = copy.deepcopy(st['offers'])
    final = view(cfg, st)
    assert final['groupProjects']['completed'] == 3 and final['goalOrder'] is None
    assert st['cStats']['done'] == 3 and st['regularDeliveries'] == 3


def test_existing_save_migrates_in_place_without_rewriting_money_inventory_or_random_offers():
    cfg, st = town()
    st.pop('goalOffer')
    st.pop('goalOrderSerial')
    st['cash'] = 47
    st['inventory'].update(farm_tomatoes=3, farm_eggs=2)
    st['offers'][0]['committed'] = True
    original = copy.deepcopy(st)
    restored = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert restored['cash'] == original['cash']
    assert restored['inventory'] == original['inventory']
    assert restored['offers'] == original['offers']
    assert restored['orderSerial'] == original['orderSerial']
    assert restored['orderRecipeHistory'] == original['orderRecipeHistory']
    assert restored['goalOffer']['requirements'] == [dict(goodId='farm_tomatoes', quantity=6)]
    saved_offer = copy.deepcopy(restored['goalOffer'])
    restored = E.migrate_state(cfg, E.State(json.loads(json.dumps(restored))))
    assert restored['goalOffer'] == saved_offer and restored['cash'] == 47
    assert restored['townProjects']['groupProgress']['delivered'] == {}


def test_saving_goods_reports_actual_cash_loss_separately_from_positive_installed_potential():
    cfg, st = town()
    st['cash'] = 100
    all_goods = {good['id']: 20 for good in cfg['tiers'][0]['goods']}
    stockpile = ordinary(st, 0, 'saving-opening-stock', all_goods, 350)
    assert E.commit_order(cfg, st, 0, stockpile['id'], True)['ok']
    before = st['cash']
    replay(cfg, st, 4)
    payload = view(cfg, st)
    flow = payload['recentCashflow']
    assert flow['observedSeconds'] == 60
    assert flow['sales'] == 0 and flow['costs'] == 3
    assert flow['net'] == st['cash'] - before == -3
    assert payload['operations']['potentialProfitPerMinute'] > 0
    assert payload['potentialIncomePerMinute'] > 0
    business = payload['buildings'][0]
    assert business['savingForOrders'] and business['recentCashflow'] == flow
    preview = business['upgrades']['production']
    assert preview['incomeDelta'] == 0 and preview['optimizedIncomeDelta'] > 0
    assert preview['profitDelta'] < 0 and 'saved for an order' in preview['consequence']
    frozen_tick, frozen_stock = st['tick'], copy.deepcopy(st['inventory'])
    purchase = E.buy_upgrade(cfg, st, 0, 'production')
    assert purchase['ok'] and purchase['incomeDelta'] == 0
    assert st['tick'] == frozen_tick and st['inventory'] == frozen_stock
    assert view(cfg, st)['recentCashflow'] == flow, 'Buying capacity does not rewrite completed cash movements.'


def test_customer_limited_production_purchase_reports_zero_extra_sales_and_higher_running_cost():
    cfg, st = town()
    st['cash'] = 100
    before = view(cfg, st)
    preview = before['buildings'][0]['upgrades']['production']
    assert preview['incomeDelta'] == 0 and preview['optimizedIncomeDelta'] == 6
    assert preview['operatingCostDelta'] > 0 and preview['profitDelta'] < 0
    assert 'Customer demand limits income' in preview['consequence']
    purchased = E.buy_upgrade(cfg, st, 0, 'production')
    after = view(cfg, st)
    assert purchased['ok'] and purchased['incomeDelta'] == 0
    assert after['incomePerMinute'] == before['incomePerMinute']
    assert after['buildings'][0]['productionCapacityPerMinute'] > before['buildings'][0]['productionCapacityPerMinute']
    assert after['operations']['potentialProfitPerMinute'] < before['operations']['potentialProfitPerMinute']
