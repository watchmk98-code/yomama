"""Finite project progress and grants must survive retries and existing saves."""
from __future__ import annotations

import copy
import json

import production_economy as E
import town_projects as P


def town():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=37)
    P.migrate(cfg, st)
    return cfg, st


def tier(cfg, building_id):
    return next(i for i, item in enumerate(cfg['tiers']) if item['id'] == building_id)


def own(cfg, st, building_id):
    ti = tier(cfg, building_id)
    st['tierOf'].append(ti)
    st['b'].append(E._building(ti))


def test_fixed_opening_is_independent_of_random_order_state_and_does_not_replace_cards():
    cfg, st = town()
    saved = copy.deepcopy(st['offers'])
    first = P.current_order(cfg, st)
    assert first['project'] and first['requirements'] == [dict(goodId='farm_tomatoes', quantity=6)]
    assert first['reward'] == 15 and first['materials'] == 0
    assert 'rarity' not in first and first['customer'] is None
    st['orderSerial'] += 90
    st['rngState'] = 999
    assert P.current_order(cfg, st) == first
    assert st['offers'] == saved


def test_three_distinct_projects_unlock_specific_grants_and_loyalty_once():
    cfg, st = town()
    st['cash'], st['materials'] = 11, 7
    inventory = copy.deepcopy(st['inventory'])
    first = P.current_order(cfg, st)
    assert P.complete(cfg, st, first['id'])['ok']
    paid = copy.deepcopy(st)
    assert not P.complete(cfg, st, first['id'])['ok']
    assert st == paid
    assert P.construction_grant(cfg, st, tier(cfg, 'fish_stall'))['fullCost']
    assert P.construction_grant(cfg, st, tier(cfg, 'roastery')) is None
    second = P.current_order(cfg, st)
    assert not P.check(cfg, st, second['id'])['ok']
    assert P.project_payload(cfg, st)['status'] == 'locked'
    own(cfg, st, 'fish_stall')
    assert P.check(cfg, st, second['id'])['ok']
    assert P.complete(cfg, st, second['id'])['ok']
    assert P.construction_grant(cfg, st, tier(cfg, 'roastery'))['fullCost']
    own(cfg, st, 'roastery')
    third = P.current_order(cfg, st)
    assert {n['goodId'] for n in third['requirements']} == {'roastery_espresso_shots', 'roastery_pastries'}
    assert P.complete(cfg, st, third['id'])['ok']
    assert P.current_order(cfg, st) is None
    assert P.project_payload(cfg, st)['status'] == 'complete'
    assert st['regularDeliveries'] == 3
    assert (st['cash'], st['materials'], st['inventory']) == (11, 7, inventory), \
        'The engine owns settlement; project progress cannot create cash or consume stock.'


def test_grants_cannot_be_spent_on_other_businesses_or_redeemed_twice():
    cfg, st = town()
    P.complete(cfg, st, P.current_order(cfg, st)['id'])
    before = (st['cash'], st['materials'], copy.deepcopy(st['inventory']))
    fish = tier(cfg, 'fish_stall')
    for invalid in (-1, True, '1', tier(cfg, 'roastery'), tier(cfg, 'garage')):
        assert P.construction_grant(cfg, st, invalid) is None
        assert not P.consume_construction_grant(cfg, st, invalid)['ok']
    assert P.consume_construction_grant(cfg, st, fish)['ok']
    reloaded = json.loads(json.dumps(st))
    P.migrate(cfg, reloaded)
    assert not P.consume_construction_grant(cfg, reloaded, fish)['ok']
    assert (st['cash'], st['materials'], st['inventory']) == before


def test_existing_built_or_queued_assets_advance_without_refunds_or_new_grants():
    cfg, st = town()
    st.pop(P.STATE_KEY)
    st['cash'], st['materials'] = 913, 12
    own(cfg, st, 'fish_stall')
    st['queue'] = [tier(cfg, 'roastery')]
    before = copy.deepcopy(st)
    data = P.migrate(cfg, st)
    assert data['completed'] == 2 and data['grants'] == {'fish_stall': 'used', 'roastery': 'used'}
    assert P.project_payload(cfg, st)['status'] == 'locked', 'Queued is not yet producing.'
    for key, value in before.items():
        assert st[key] == value
    assert P.construction_grant(cfg, st, tier(cfg, 'fish_stall')) is None
    assert P.construction_grant(cfg, st, tier(cfg, 'roastery')) is None


def test_sparse_existing_roastery_does_not_gift_a_missing_fish_stall():
    cfg, st = town()
    st.pop(P.STATE_KEY)
    own(cfg, st, 'roastery')
    data = P.migrate(cfg, st)
    assert data['completed'] == 2
    assert data['grants']['fish_stall'] == 'skipped'
    assert P.construction_grant(cfg, st, tier(cfg, 'fish_stall')) is None


def test_legacy_loyalty_progress_and_committed_offer_are_preserved():
    for credits in (0, 1, 2, 3):
        cfg, st = town()
        st.pop(P.STATE_KEY)
        st['regularDeliveries'] = credits
        st['offers'][2]['committed'] = True
        before = copy.deepcopy(st)
        data = P.migrate(cfg, st)
        assert data['completed'] == credits
        for key, value in before.items():
            assert st[key] == value
        if credits == 3:
            assert P.project_payload(cfg, st)['status'] == 'complete'
            assert P.construction_grant(cfg, st, tier(cfg, 'fish_stall')) is None
        else:
            assert bool(P.construction_grant(cfg, st, tier(cfg, 'fish_stall'))) == (credits >= 1)
        saved = copy.deepcopy(st)
        P.migrate(cfg, st)
        assert st == saved


def test_preserved_legacy_order_can_add_progress_after_initial_migration():
    cfg, st = town()
    st['regularDeliveries'] = 1
    assert P.migrate(cfg, st)['completed'] == 1
    assert P.construction_grant(cfg, st, tier(cfg, 'fish_stall'))
    P.consume_construction_grant(cfg, st, tier(cfg, 'fish_stall'))
    saved = copy.deepcopy(st)
    P.migrate(cfg, st)
    assert st == saved and P.construction_grant(cfg, st, tier(cfg, 'fish_stall')) is None


def test_guide_uses_available_stock_and_serializes_deterministically():
    cfg, st = town()
    order = P.current_order(cfg, st)
    st['offers'][2] = dict(order, committed=True)
    st['inventory'] = {'farm_tomatoes': 10}
    assert P.project_payload(cfg, st)['status'] == 'ready'
    assert P.project_payload(cfg, st, available={'farm_tomatoes': 4})['status'] == 'available'
    assert P.project_payload(cfg, st, available={'farm_tomatoes': 4})['committed']
    saved = json.loads(json.dumps(st))
    assert P.current_order(cfg, saved) == P.current_order(cfg, st)
    assert P.project_payload(cfg, saved) == P.project_payload(cfg, st)


def test_tier_positions_are_looked_up_by_configured_id():
    cfg = E.load_config()
    cfg['tiers'][1], cfg['tiers'][3] = cfg['tiers'][3], cfg['tiers'][1]
    st = dict(tierOf=[0], inventory={}, cash=0, materials=0, queue=[])
    first = P.current_order(cfg, st)
    assert P.complete(cfg, st, first['id'])['ok']
    assert P.construction_grant(cfg, st, 1) is None
    assert P.construction_grant(cfg, st, 3)['buildingId'] == 'fish_stall'


def test_project_bundles_never_reserve_inputs_needed_by_their_own_outputs():
    cfg = E.load_config()
    catalog = E.catalog(cfg)
    for project in P.PROJECTS:
        selected = {gid for gid, qty in project['goods']}
        for gid in selected:
            pending = [n['goodId'] for n in catalog[gid].get('inputs', [])]
            ancestors = set()
            while pending:
                parent = pending.pop()
                if parent in ancestors:
                    continue
                ancestors.add(parent)
                pending.extend(n['goodId'] for n in catalog[parent].get('inputs', []))
            assert not selected.intersection(ancestors)


def test_current_fixed_bundles_fill_under_normal_production_with_project_holds():
    cfg, st = town()
    for project in P.PROJECTS:
        if project['building'] not in {cfg['tiers'][ti]['id'] for ti in st['tierOf']}:
            own(cfg, st, project['building'])
        order = P.current_order(cfg, st)
        st['offers'] = [dict(order, committed=True)]
        for _ in range(16):
            E.player_tick(cfg, E.new_class(cfg), st, st['tick'])
            if all(st['inventory'].get(n['goodId'], 0) >= n['quantity'] for n in order['requirements']):
                break
        assert all(st['inventory'].get(n['goodId'], 0) >= n['quantity'] for n in order['requirements'])
        for need in order['requirements']:
            st['inventory'][need['goodId']] -= need['quantity']
        assert P.complete(cfg, st, order['id'])['ok']
