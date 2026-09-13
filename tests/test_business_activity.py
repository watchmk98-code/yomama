"""Observed units conserve real outputs and sales through saves and replay."""
from __future__ import annotations

import copy
import json

import pytest

import business_activity as A
import production_economy as E


def town(tiers=(0,)):
    cfg = E.load_config()
    st = E.new_state(cfg, seed=7)
    st['tierOf'] = list(tiers)
    st['b'] = [E._building(tier) for tier in tiers]
    return cfg, st


def replay(cfg, st, count):
    start = st['tick']
    E.advance_class(cfg, E.new_class(cfg), [st], start, start + count)


def view(cfg, st, paused=False):
    return E.payload(cfg, st, E.new_class(cfg), {'paused': paused})


def test_first_minute_counts_completed_goods_and_retail_not_forecasts():
    cfg, st = town()
    initial = view(cfg, st)['buildings'][0]
    assert initial['productionPerMinute'] > 0
    assert initial['activity'] == dict(windowSeconds=60, observedSeconds=0,
        producedUnits=0, soldUnits=0, soldBySource=dict(walkIns=0, regularBuyers=0))
    replay(cfg, st, 4)
    activity = view(cfg, st)['buildings'][0]['activity']
    # Four free tomato batches fund two egg batches. The first honey batch
    # waits for running cash; the installed seven-unit forecast is not output.
    assert activity['producedUnits'] == st['report']['unitsProduced'] == 6
    assert activity['soldUnits'] == st['report']['unitsSold'] > 0
    assert activity['soldBySource']['walkIns'] == activity['soldUnits']
    assert activity['producedUnits'] - activity['soldUnits'] == sum(st['inventory'].values())
    assert activity['observedSeconds'] == 60


def recipe_town():
    cfg, st = town((0, 2))
    st['cash'] = 100  # Isolate ingredient/storage constraints from running cash.
    for tier in cfg['tiers']:
        for good in tier['goods']:
            good['cycleTicks'] = 10000
            if good['id'] == 'roastery_pastries':
                good['cycleTicks'] = 1
                good['quantity'] = 3  # Count all output units, not one completion.
                recipe = good
    for building in st['b']:
        building['reserve'] = True
    return cfg, st, recipe


def test_completed_recipe_counts_outputs_but_never_sells_or_recredits_ingredients():
    cfg, st, recipe = recipe_town()
    st['inventory'] = {need['goodId']: need['quantity'] for need in recipe['inputs']}
    replay(cfg, st, 1)
    shops = view(cfg, st)['buildings']
    assert shops[0]['activity']['producedUnits'] == 0
    assert shops[1]['activity']['producedUnits'] == 3
    assert st['inventory']['roastery_pastries'] == 3
    assert all(st['inventory'][need['goodId']] == 0 for need in recipe['inputs'])
    assert all(shop['activity']['soldUnits'] == 0 for shop in shops)


@pytest.mark.parametrize('blocked', ('ingredient', 'storage', 'paused'))
def test_blocked_or_paused_recipe_does_not_report_an_uncompleted_output(blocked):
    cfg, st, recipe = recipe_town()
    if blocked != 'ingredient':
        st['inventory'] = {need['goodId']: need['quantity'] for need in recipe['inputs']}
    if blocked == 'storage':
        st['inventory'][recipe['id']] = E._good_capacity(cfg, st, 1, recipe['id'])
    if blocked == 'paused':
        st['b'][1]['processing'] = False
    before = copy.deepcopy(st['inventory'])
    replay(cfg, st, 3)
    assert st['inventory'] == before
    assert all(shop['activity']['producedUnits'] == 0 for shop in view(cfg, st)['buildings'])


def test_completed_regular_bundle_counts_direct_producers_and_only_once(monkeypatch):
    cfg, st = town((0, 1, 2))
    customer = ('shared_breakfast', 'Shared breakfast', 'Eggs and pastries', 120,
                (('farm_eggs', 2), ('roastery_pastries', 1)))
    monkeypatch.setattr(E, 'CUSTOMER_CATALOG', E.CUSTOMER_CATALOG + (customer,))
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='shared_breakfast')['ok']
    for _ in range(80):
        replay(cfg, st, 1)
        if st['customerContracts']['deliveries']:
            break
    else:
        pytest.fail('A normal cross-business shipment must complete.')
    shops = view(cfg, st)['buildings']
    assert st['customerContracts']['deliveries'] == 1
    assert [shop['activity']['soldBySource']['regularBuyers'] for shop in shops] == [2, 0, 1]
    assert sum(shop['activity']['soldUnits'] for shop in shops) == sum(
        shop['activity']['soldBySource']['walkIns'] for shop in shops) + 3
    saved = copy.deepcopy(st)
    replay(cfg, st, 0)
    assert view(cfg, st)['buildings'] == shops
    assert st == saved


def test_waiting_and_paused_customers_never_record_an_undelivered_shipment():
    cfg, st = town()
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    contract = st['customerContracts']['active'][0]
    contract['nextDeliveryTick'] = 1
    E._tick_customer_contracts(cfg, st, 1)
    assert A.payload(cfg, st, 1)['byBuilding']['0']['soldUnits'] == 0
    st['inventory']['farm_tomatoes'] = 6
    contract['paused'] = True
    E._tick_customer_contracts(cfg, st, 2)
    assert A.payload(cfg, st, 2)['byBuilding']['0']['soldUnits'] == 0
    assert st['inventory']['farm_tomatoes'] == 6


def test_manual_orders_clearance_and_purchases_do_not_become_operating_unit_sales():
    cfg, st = town()
    replay(cfg, st, 80)
    before = copy.deepcopy(view(cfg, st)['buildings'][0]['activity'])
    order = st['offers'][0]
    assert E.fulfill_order(cfg, st, 0, order['id'])['ok']
    assert E.sell_one(cfg, st, 0)['ok']
    assert E.buy_upgrade(cfg, st, 0, 'sales')['ok']
    assert view(cfg, st)['buildings'][0]['activity'] == before


def test_window_expires_at_exact_sixty_seconds_and_handles_non_divisor_ticks():
    cfg, st = town()
    A.record(cfg, st, 'production', {0: 3}, tick=1)
    A.record(cfg, st, 'walkIns', {0: 2}, tick=4)
    assert A.payload(cfg, st, 4)['byBuilding']['0']['producedUnits'] == 3
    assert A.payload(cfg, st, 5)['byBuilding']['0']['producedUnits'] == 0
    assert A.payload(cfg, st, 5)['byBuilding']['0']['soldUnits'] == 2
    assert A.payload(cfg, st, 8)['byBuilding']['0']['soldUnits'] == 0
    cfg['global']['tick'] = 7
    A.record(cfg, st, 'production', {0: 3}, tick=10)
    assert A.payload(cfg, st, 18)['byBuilding']['0']['producedUnits'] == 3
    assert A.payload(cfg, st, 19)['byBuilding']['0']['producedUnits'] == 0


def test_partial_window_uses_actual_units_without_extrapolating():
    cfg, st = town()
    replay(cfg, st, 1)
    activity = view(cfg, st)['buildings'][0]['activity']
    assert activity['observedSeconds'] == 15
    assert activity['producedUnits'] == 1
    assert activity['soldUnits'] == 0


def test_old_v4_save_starts_empty_instead_of_backfilling_lifetime_counters():
    cfg, st = town()
    replay(cfg, st, 80)
    st.pop(A.STATE_KEY)
    report = copy.deepcopy(st['report'])
    migrated = E.migrate_state(cfg, st)
    assert migrated['report'] == report
    assert view(cfg, migrated)['buildings'][0]['activity'] == dict(windowSeconds=60,
        observedSeconds=0, producedUnits=0, soldUnits=0, soldBySource=dict(walkIns=0, regularBuyers=0))


def test_legacy_migration_starts_observation_at_relocated_clock():
    cfg = E.load_config()
    st = E.legacy.new_state(E.legacy.load_config(), start_tick=100, seed=7)
    migrated = E.migrate_state(cfg, st, tick=500)
    activity = view(cfg, migrated)['buildings'][0]['activity']
    assert migrated['tick'] == 500
    assert activity['observedSeconds'] == activity['producedUnits'] == activity['soldUnits'] == 0


def test_json_reload_and_replay_chunking_preserve_bounded_activity_exactly():
    cfg, continuous = town((0, 1, 2))
    for slot, customer in enumerate(('corner_grocer', 'harbor_bistro', 'copper_cafe')):
        assert E.manage_customer_contract(cfg, continuous, slot, 'accept', customer_id=customer)['ok']
    chunked = E.State(json.loads(json.dumps(continuous)))
    replay(cfg, continuous, 160)
    for count in (1, 3, 9, 27, 40, 80):
        replay(cfg, chunked, count)
        chunked = E.State(json.loads(json.dumps(chunked)))
        assert len(chunked[A.STATE_KEY]['buckets']) <= 4
    assert chunked == continuous
    assert A.payload(cfg, chunked) == A.payload(cfg, continuous)
    assert len(json.dumps(chunked[A.STATE_KEY])) < 2000


def test_offline_skip_clears_window_and_resume_records_only_new_completions():
    cfg, st = town()
    cfg['runtime']['offlineHours'] = .1
    replay(cfg, st, 24)
    assert view(cfg, st)['buildings'][0]['activity']['producedUnits'] > 0
    before = copy.deepcopy(st['inventory']), st['cash']
    replay(cfg, st, 8)
    assert (st['inventory'], st['cash']) == before
    activity = view(cfg, st)['buildings'][0]['activity']
    assert activity['observedSeconds'] == activity['producedUnits'] == activity['soldUnits'] == 0
    st = E.State(json.loads(json.dumps(st)))
    E.on_login(cfg, st)
    produced, sold = st['report']['unitsProduced'], st['report']['unitsSold']
    replay(cfg, st, 1)
    activity = view(cfg, st)['buildings'][0]['activity']
    assert activity['observedSeconds'] == 15
    assert activity['producedUnits'] == st['report']['unitsProduced'] - produced
    assert activity['soldUnits'] == st['report']['unitsSold'] - sold


def test_paused_class_keeps_activity_at_the_frozen_economy_clock():
    cfg, st = town()
    replay(cfg, st, 4)
    activity = view(cfg, st)['buildings'][0]['activity']
    assert view(cfg, st, paused=True)['buildings'][0]['activity'] == activity
    replay(cfg, st, 0)
    assert view(cfg, st, paused=True)['buildings'][0]['activity'] == activity


@pytest.mark.parametrize('source,quantity,slot', [
    ('forecast', 1, 0), ('production', -1, 0), ('walkIns', True, 0),
    ('walkIns', 1.5, 0), ('regularBuyers', 1, 99), ('production', 1, True),
])
def test_invalid_activity_cannot_partially_mutate_history(source, quantity, slot):
    cfg, st = town()
    before = copy.deepcopy(st)
    with pytest.raises(ValueError):
        A.record(cfg, st, source, {slot: quantity}, tick=1)
    assert st == before
