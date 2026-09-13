"""Group achievements observe settled orders without selling their goods twice."""
from __future__ import annotations

import copy
import json

import production_economy as E
import town_projects as P


def town(connected=True):
    cfg = E.load_config()
    cfg.setdefault('businessDesign', {})['connectedProgression'] = connected
    return cfg, E.new_state(cfg, seed=37)


def own(cfg, st, building_id):
    ti = next(i for i, item in enumerate(cfg['tiers']) if item['id'] == building_id)
    if ti not in st['tierOf']:
        st['tierOf'].append(ti)
        st['b'].append(E._building(ti))
    return ti


def delivery(cfg, st, order_id, **goods):
    return P.record_delivery(cfg, st,
                             [dict(goodId=gid, quantity=quantity) for gid, quantity in goods.items()],
                             order_id)


def test_inventory_never_counts_and_order_progress_is_cumulative_and_idempotent():
    cfg, st = town()
    st['inventory']['farm_tomatoes'] = 600
    before_money = (st['cash'], st['materials'], copy.deepcopy(st['inventory']))
    assert not P.group_payload(cfg, st)['current']['canClaim']
    assert delivery(cfg, st, 'ordinary-a', farm_tomatoes=2)['recorded']
    first = copy.deepcopy(st)
    assert not delivery(cfg, st, 'ordinary-a', farm_tomatoes=2)['recorded']
    assert st == first
    assert not P.check_claim(cfg, st, 'farm_neighbors')['ok']
    assert delivery(cfg, st, 'ordinary-b', farm_tomatoes=20)['ready']
    project = P.group_payload(cfg, st)['current']
    assert project['requirements'] == [dict(goodId='farm_tomatoes', name='Tomatoes', quantity=6,
                                          delivered=6, remaining=0)]
    assert project['progressPercent'] == 100 and project['canClaim']
    assert (st['cash'], st['materials'], st['inventory']) == before_money


def test_mixed_delivery_cannot_precredit_or_replay_into_a_later_project():
    cfg, st = town()
    mixed = dict(farm_tomatoes=6, fish_stall_smoked_fish=2, fish_stall_oysters=4)
    assert delivery(cfg, st, 'mixed-first-stage', **mixed)['ready']
    assert P.claim(cfg, st, 'farm_neighbors')['ok']
    own(cfg, st, 'fish_stall')
    second = P.group_payload(cfg, st)['current']
    assert second['projectId'] == 'harbor_lunch'
    assert all(need['delivered'] == 0 for need in second['requirements'])
    saved = copy.deepcopy(st)
    assert not delivery(cfg, st, 'mixed-first-stage', **mixed)['recorded']
    assert st == saved
    assert delivery(cfg, st, 'new-seafood', fish_stall_smoked_fish=2, fish_stall_oysters=4)['ready']


def test_three_project_claims_preserve_rewards_grants_and_perk_without_second_goods_debit():
    cfg, st = town()
    st['cash'], st['materials'], st['inventory'] = 47, 3, {}
    expected_rewards = [15, 55, 85]
    for index, project in enumerate(P.PROJECTS):
        own(cfg, st, project['building'])
        assert delivery(cfg, st, 'paid-order-' + str(index), **dict(project['goods']))['ready']
        result = P.claim(cfg, st, project['id'])
        assert result['ok'] and result['cashReward'] == expected_rewards[index]
        assert result['grantBuildingId'] == project['grant']
        assert result['completed'] == index + 1
        assert (st['cash'], st['materials'], st['inventory']) == (47, 3, {}), \
            'The engine pays cashReward; neither observation nor claiming reconsumes goods.'
        claimed = copy.deepcopy(st)
        assert not P.claim(cfg, st, project['id'])['ok']
        assert st == claimed, 'A retry must not issue another reward entitlement.'
        if project['grant']:
            ti = next(i for i, item in enumerate(cfg['tiers']) if item['id'] == project['grant'])
            assert P.construction_grant(cfg, st, ti)['fullCost']
            assert P.consume_construction_grant(cfg, st, ti)['ok']
            assert not P.consume_construction_grant(cfg, st, ti)['ok']
    payload = P.group_payload(cfg, st)
    assert payload['current'] is None and payload['completed'] == 3
    assert all(row['completed'] for row in payload['projects'])
    assert st['regularDeliveries'] == 3
    complete = copy.deepcopy(st)
    assert not delivery(cfg, st, 'after-completion', farm_tomatoes=6)['recorded']
    assert st == complete


def test_observation_requires_producers_and_claiming_requires_current_project():
    cfg, st = town()
    delivery(cfg, st, 'opening', farm_tomatoes=6)
    assert P.claim(cfg, st, 'farm_neighbors')['ok']
    waiting = copy.deepcopy(st)
    assert not P.claim(cfg, st, 'cafe_opening')['ok']
    assert st == waiting
    result = delivery(cfg, st, 'before-fish-exists', fish_stall_smoked_fish=2, fish_stall_oysters=4)
    assert not result['recorded'] and 'Open ' in result['why']
    assert P.group_payload(cfg, st)['current']['status'] == 'locked'
    own(cfg, st, 'fish_stall')
    assert not delivery(cfg, st, 'before-fish-exists', fish_stall_smoked_fish=2, fish_stall_oysters=4)['recorded']
    assert not P.check_claim(cfg, st, 'harbor_lunch')['ok']


def test_later_business_purchase_does_not_skip_an_observed_group_project():
    cfg, st = town()
    own(cfg, st, 'fish_stall')
    own(cfg, st, 'roastery')
    assert P.migrate(cfg, st)['completed'] == 0
    assert P.group_payload(cfg, st)['current']['projectId'] == 'farm_neighbors'
    delivery(cfg, st, 'opening-after-purchase', farm_tomatoes=6)
    assert P.claim(cfg, st, 'farm_neighbors')['ok']
    assert st[P.STATE_KEY]['grants']['fish_stall'] == 'used'
    assert P.group_payload(cfg, st)['current']['projectId'] == 'harbor_lunch'


def test_json_reload_keeps_progress_and_migration_does_not_pay_or_rewrite_saved_orders():
    cfg, st = town(False)
    st['offers'] = [dict(id='preserved-project', project=True, requirements=[dict(goodId='farm_tomatoes', quantity=9)],
                         reward=99, materials=2, committed=True)]
    own(cfg, st, 'fish_stall')
    before = copy.deepcopy(st)
    cfg['businessDesign']['connectedProgression'] = True
    data = P.migrate(cfg, st)
    assert data['completed'] == 1 and data['grants']['fish_stall'] == 'used'
    for key in ('offers', 'cash', 'materials', 'inventory', 'b', 'tierOf'):
        assert st[key] == before[key]
    delivery(cfg, st, 'seafood-progress', fish_stall_smoked_fish=1, fish_stall_oysters=2)
    reloaded = json.loads(json.dumps(st))
    assert P.group_payload(cfg, reloaded) == P.group_payload(cfg, st)
    saved = copy.deepcopy(reloaded)
    P.migrate(cfg, reloaded)
    assert reloaded == saved
    assert not delivery(cfg, reloaded, 'seafood-progress', fish_stall_smoked_fish=1, fish_stall_oysters=2)['recorded']
    assert reloaded == saved


def test_legacy_project_settlement_and_completed_perk_cannot_be_claimed_again():
    cfg, st = town()
    original = P.current_order(cfg, st)
    assert P.complete(cfg, st, original['id'])['ok'], 'A preserved fixed project can still settle through its original path.'
    assert not P.claim(cfg, st, 'farm_neighbors')['ok']
    cfg, st = town(False)
    st['regularDeliveries'] = 3
    P.migrate(cfg, st)
    before = copy.deepcopy(st)
    cfg['businessDesign']['connectedProgression'] = True
    assert P.group_payload(cfg, st)['completed'] == 3
    assert not P.claim(cfg, st, 'cafe_opening')['ok']
    for key, value in before.items():
        if key != P.STATE_KEY:
            assert st[key] == value
    assert st[P.STATE_KEY]['grants'] == before[P.STATE_KEY]['grants']


def test_relocated_saved_project_keeps_its_original_settlement_path_exclusive():
    cfg, st = town()
    st['legacyProjectOffer'] = dict(P.current_order(cfg, st), reward=99)
    delivery(cfg, st, 'new-ordinary-order', farm_tomatoes=6)
    before = copy.deepcopy(st)
    assert not P.group_payload(cfg, st)['current']['canClaim']
    assert not P.claim(cfg, st, 'farm_neighbors')['ok']
    assert st == before
    result = P.complete(cfg, st, st['legacyProjectOffer']['id'])
    assert result['ok'] and result['completed'] == 1
    assert not P.claim(cfg, st, 'farm_neighbors')['ok']
    assert st['legacyProjectOffer']['reward'] == 99


def test_receipt_storage_is_bounded_but_contributing_orders_remain_idempotent():
    cfg, st = town()
    delivery(cfg, st, 'mixed-contribution', farm_tomatoes=6, fish_stall_smoked_fish=2, fish_stall_oysters=4)
    for serial in range(P.RECENT_DELIVERY_LIMIT + 20):
        delivery(cfg, st, 'irrelevant-' + str(serial), farm_eggs=2)
    group = st[P.STATE_KEY]['groupProgress']
    assert len(group['seenOrderIds']) == P.RECENT_DELIVERY_LIMIT
    assert group['creditedOrderIds'] == ['mixed-contribution']
    assert 'mixed-contribution' not in group['seenOrderIds']
    assert P.claim(cfg, st, 'farm_neighbors')['ok']
    own(cfg, st, 'fish_stall')
    assert not delivery(cfg, st, 'mixed-contribution', fish_stall_smoked_fish=2, fish_stall_oysters=4)['recorded']
    assert P.group_payload(cfg, st)['current']['progressPercent'] == 0


def test_connected_copy_explains_suppliers_without_relabeling_legacy_projects():
    cfg, st = town()
    rows = P.group_payload(cfg, st)['projects']
    assert 'conglomerate' in rows[0]['purpose']
    assert {supplier['buildingId'] for supplier in rows[2]['suppliers']} == {'farm', 'roastery'}
    assert all('ordinary orders' in row['description'] for row in rows)
    assert P.current_order(cfg, st)['name'] == 'Feed the neighborhood'


def test_legacy_snapshots_and_invalid_events_never_gain_connected_progress():
    cfg, st = town(False)
    before = copy.deepcopy(st)
    assert not delivery(cfg, st, 'not-opted-in', farm_tomatoes=6)['recorded']
    assert P.group_payload(cfg, st)['enabled'] is False
    assert not P.claim(cfg, st, 'farm_neighbors')['ok']
    assert st == before
    cfg, st = town()
    for quantities, order_id in [([dict(goodId='farm_tomatoes', quantity=-1)], 'bad-negative'),
                                 ([dict(goodId='farm_tomatoes', quantity=True)], 'bad-boolean'),
                                 ([dict(goodId='farm_tomatoes', quantity=1.5)], 'bad-fraction'),
                                 ([dict(goodId='farm_tomatoes', quantity=6)], ''),
                                 (None, 'bad-body')]:
        before = copy.deepcopy(st)
        assert not P.record_delivery(cfg, st, quantities, order_id)['ok']
        assert st == before
