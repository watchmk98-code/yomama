"""Goal-sized ordinary offers and honest, non-mutating supply estimates."""
from __future__ import annotations

import copy
import json

import pytest

import production_economy as E
import project_orders as G
import town_projects as P


def town():
    cfg = E.load_config()
    cfg['businessDesign']['connectedProgression'] = True
    cfg['businessDesign']['groupProjectsEnabled'] = True
    return cfg, E.new_state(cfg, seed=193)


def own(cfg, st, building):
    tier = next(i for i, item in enumerate(cfg['tiers']) if item['id'] == building)
    if tier not in st['tierOf']:
        st['tierOf'].append(tier)
        st['b'].append(E._building(tier))


def progress(cfg, st, order_id, **goods):
    return P.record_delivery(cfg, st,
                             [dict(goodId=gid, quantity=qty) for gid, qty in goods.items()], order_id)


def test_first_small_offer_preserves_random_cards_cash_and_history_and_reload():
    cfg, st = town()
    st.pop(G.GOAL_KEY, None)
    before = copy.deepcopy(st)
    offer = G.sync(cfg, st)
    assert offer['requirements'] == [dict(goodId='farm_tomatoes', quantity=6)]
    assert offer['goalOrder'] and not offer.get('project')
    assert offer['reward'] == 15 and offer['materials'] == 0 and offer['customer'] is None
    assert {k: v for k, v in st.items() if k not in (G.GOAL_KEY, G.SERIAL_KEY)} == {
        k: v for k, v in before.items() if k not in (G.GOAL_KEY, G.SERIAL_KEY)}
    frozen = copy.deepcopy(st)
    reloaded = json.loads(json.dumps(st))
    assert G.sync(cfg, st) == G.sync(cfg, reloaded) == offer
    assert st == frozen and G.check(cfg, st, offer)['ok']


def test_progress_requotes_only_uncommitted_offer_and_rejects_old_identity():
    cfg, st = town()
    previous = copy.deepcopy(G.sync(cfg, st))
    assert progress(cfg, st, 'ordinary-partial', farm_tomatoes=2)['recorded']
    assert not G.check(cfg, st, previous)['ok']
    current = G.sync(cfg, st)
    assert current['requirements'] == [dict(goodId='farm_tomatoes', quantity=4)]
    assert current['reward'] == 10 and current['id'] != previous['id']
    assert G.check(cfg, st, current)['ok'] and not G.check(cfg, st, previous)['ok']


def test_saved_goal_terms_remain_until_released_and_resize_then():
    cfg, st = town()
    saved = G.sync(cfg, st)
    saved['committed'] = True
    frozen = copy.deepcopy(saved)
    progress(cfg, st, 'ordinary-while-saved', farm_tomatoes=2)
    assert G.sync(cfg, st) == frozen and G.check(cfg, st, saved)['ok']
    saved['committed'] = False
    resized = G.sync(cfg, st)
    assert resized['requirements'][0]['quantity'] == 4 and resized['id'] != saved['id']


def test_each_stage_only_requests_outstanding_goods_and_waits_for_its_producer():
    cfg, st = town()
    expected = [dict(farm_tomatoes=6), dict(fish_stall_smoked_fish=2, fish_stall_oysters=4),
                dict(roastery_espresso_shots=4, roastery_pastries=2)]
    for index, project in enumerate(P.PROJECTS):
        if index:
            assert G.sync(cfg, st) is None
        own(cfg, st, project['building'])
        offer = G.sync(cfg, st)
        assert {row['goodId']: row['quantity'] for row in offer['requirements']} == expected[index]
        assert progress(cfg, st, 'ordinary-stage-' + str(index), **expected[index])['ready']
        assert G.sync(cfg, st) is None, 'Ready goals must offer the reward claim, not another delivery.'
        assert P.claim(cfg, st, project['id'])['ok']
    assert G.sync(cfg, st) is None and st[P.STATE_KEY]['completed'] == 3


def test_goal_offer_never_replaces_a_legacy_saved_delivery_or_appears_for_disabled_rules():
    cfg, st = town()
    original = copy.deepcopy(st['offers'])
    st['legacyProjectOffer'] = dict(id='saved-earlier-project', committed=True)
    assert G.sync(cfg, st) is None and st['offers'] == original
    st.pop('legacyProjectOffer')
    assert G.sync(cfg, st, can_make=lambda gid: False) is None
    cfg['businessDesign']['connectedProgression'] = False
    assert G.sync(cfg, st) is None


def test_empty_or_changed_terms_are_rejected_without_rewards():
    cfg, st = town()
    offer = G.sync(cfg, st)
    tampered = copy.deepcopy(offer)
    tampered['reward'] *= 100
    assert not G.check(cfg, st, tampered)['ok']
    offer['requirements'] = []
    offer['committed'] = True
    assert not G.check(cfg, st, offer)['ok']


def forecast_fixture(committed=False):
    cfg = dict(global_unused=True)
    cfg['global'] = dict(tick=15)
    st = dict(cash=100, inventory=dict(crop=0), tick=17)
    order = dict(id='test-offer', committed=committed,
                 requirements=[dict(goodId='crop', quantity=6)])
    row = dict(name='Tomatoes', stored=0, savedReserved=0, regularReserved=0,
               capacity=30, speed=100, work=0, cycleTicks=1, quantity=1,
               batchMultiplier=1, delayTicks=0, batchCost=0,
               paused=False, unlocked=True, producerOwned=True)
    supply = dict(tickSeconds=15, cash=100, goods=dict(crop=row), regulars=[])
    return cfg, st, order, supply


def test_estimate_requires_saving_and_never_changes_live_state_or_descriptors():
    cfg, st, order, supply = forecast_fixture()
    before = copy.deepcopy((cfg, st, order, supply))
    result = G.estimate(cfg, st, order, supply)
    assert result['etaSeconds'] is None and result['etaIfSavedSeconds'] == 90
    assert result['etaLabel'] == 'If saved: about 2 min'
    assert (cfg, st, order, supply) == before
    order['committed'] = True
    saved = G.estimate(cfg, st, order, supply)
    assert saved['etaSeconds'] == 90 and saved['etaIfSavedSeconds'] is None


def test_estimate_uses_existing_goods_work_startup_phase_and_batch_cadence():
    cfg, st, order, supply = forecast_fixture(committed=True)
    row = supply['goods']['crop']
    row.update(stored=2, work=150, cycleTicks=2, batchMultiplier=2, delayTicks=1)
    # Two batches finish at tick four; two more finish at tick eight.
    assert G.estimate(cfg, st, order, supply)['etaSeconds'] == 120
    row['stored'] = 6
    ready = G.estimate(cfg, st, order, supply)
    assert ready['etaSeconds'] == 0 and ready['etaStatus'] == 'ready'


@pytest.mark.parametrize('change,status', [
    ({'producerOwned': False}, 'locked'), ({'unlocked': False}, 'locked'),
    ({'paused': True}, 'paused'), ({'speed': 0}, 'stopped'),
    ({'capacity': 6, 'savedReserved': 1}, 'storage'),
    ({'batchCost': 101}, 'cash'),
    ({'capacity': 6, 'stored': 5, 'quantity': 2}, 'storage'),
])
def test_blocked_supply_has_actionable_reason_and_no_invented_countdown(change, status):
    cfg, st, order, supply = forecast_fixture(committed=True)
    supply['goods']['crop'].update(change)
    result = G.estimate(cfg, st, order, supply)
    assert result['etaStatus'] == status and result['etaReason']
    assert result['etaSeconds'] is None and result['etaIfSavedSeconds'] is None


def test_class_pause_and_insufficient_cash_for_full_order_have_no_eta():
    cfg, st, order, supply = forecast_fixture(committed=True)
    supply['paused'] = True
    assert G.estimate(cfg, st, order, supply)['etaStatus'] == 'paused'
    supply['paused'] = False
    supply['cash'] = 5
    supply['goods']['crop']['batchCost'] = 1
    assert G.estimate(cfg, st, order, supply)['etaStatus'] == 'cash'


def test_regular_shipments_and_other_saved_orders_delay_supply():
    cfg, st, order, supply = forecast_fixture(committed=True)
    supply['goods']['crop'].update(savedReserved=2, regularReserved=2)
    supply['regulars'] = [dict(name='Grocer', requirements=[dict(goodId='crop', quantity=2)],
                               nextTicks=4, intervalTicks=4)]
    # Ten goods are needed on shelf, and the grocer removes two each four ticks.
    result = G.estimate(cfg, st, order, supply)
    assert result['etaSeconds'] == 18 * 15
    assert 'regular buyers' in result['etaReason']


def test_a_regular_using_all_production_has_no_false_timer():
    cfg, st, order, supply = forecast_fixture(committed=True)
    supply['goods']['crop']['regularReserved'] = 2
    supply['regulars'] = [dict(name='Grocer', requirements=[dict(goodId='crop', quantity=2)],
                               nextTicks=2, intervalTicks=2)]
    result = G.estimate(cfg, st, order, supply)
    assert result['etaSeconds'] is None and result['etaStatus'] == 'regulars'
    assert 'Pause a regular buyer' in result['etaReason']


def test_dispatched_stock_is_not_reused_by_regulars():
    cfg, st, order, supply = forecast_fixture(committed=True)
    supply['goods']['crop'].update(stored=6, savedReserved=6, inTransitReserved=6,
                                  regularReserved=2)
    supply['regulars'] = [dict(name='Grocer', requirements=[dict(goodId='crop', quantity=2)],
                               nextTicks=1, intervalTicks=30)]
    assert G.estimate(cfg, st, order, supply)['etaSeconds'] == 10 * 15


def test_regular_shipment_can_free_room_for_a_batch_that_cannot_fit_yet():
    cfg, st, order, supply = forecast_fixture(committed=True)
    order['requirements'][0]['quantity'] = 3
    supply['goods']['crop'].update(stored=5, capacity=6, regularReserved=3, quantity=2)
    supply['regulars'] = [dict(name='Grocer', requirements=[dict(goodId='crop', quantity=3)],
                               nextTicks=1, intervalTicks=30)]
    # Work earned during the full-shelf tick is retained, so both batches finish next tick.
    assert G.estimate(cfg, st, order, supply)['etaSeconds'] == 2 * 15
