"""Cash-window conservation, save migration and whole-shipment flow estimates."""
from __future__ import annotations

import copy
import json

import pytest

import earnings as R
import production_economy as E


@pytest.fixture
def town():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=7)
    st['tierOf'] = [0, 1, 2]
    st['b'] = [E._building(ti) for ti in st['tierOf']]
    return cfg, st


def sources_sum(view, source):
    return sum(b['bySource'][source] for b in view['byBuilding'].values()) + view['unattributed']['bySource'][source]


def test_all_receipts_reconcile_but_one_off_cash_never_becomes_operating_income(town):
    cfg, st = town
    before = st['cash']
    payments = [('walkIns', 8, {'0': 8}), ('regularBuyers', 31, {'0': 11, '2': 20}),
                ('orders', 43, {'0': 15, '2': 28}), ('clearance', 9, {'1': 9}), ('events', 5, None)]
    for source, amount, allocation in payments:
        st['cash'] += amount
        R.record(cfg, st, source, amount, tick=1, by_building=allocation)
    st['tick'] = 1
    view = R.payload(cfg, st)
    assert view['totalIncome'] == st['cash'] - before == 96
    assert view['operatingIncome'] == 39
    assert view['oneOffIncome'] == 57
    assert view['byBuilding']['0']['operatingIncome'] == 19
    assert view['byBuilding']['2']['operatingIncome'] == 20
    assert view['unattributed']['bySource']['events'] == 5
    for source in R.SOURCES:
        assert sources_sum(view, source) == view['bySource'][source]


def test_bundle_payment_attributes_direct_goods_not_their_upstream_inputs(town):
    cfg, st = town
    # 2 eggs worth 8 and one pastry worth 20: the pastry's ingredient producers
    # must not also receive its revenue. 35 whole YM split exactly into 10 + 25.
    needs = [dict(goodId='farm_eggs', quantity=2), dict(goodId='roastery_pastries', quantity=1)]
    R.record_goods(cfg, st, 'regularBuyers', 35, needs, tick=1)
    view = R.payload(cfg, st, tick=1)
    assert view['byBuilding']['0']['operatingIncome'] == 10
    assert view['byBuilding']['2']['operatingIncome'] == 25
    assert view['byBuilding']['1']['operatingIncome'] == 0
    assert view['operatingIncome'] == 35
    assert st['cash'] == 0 and not st['inventory'], 'Recording must not make a second payment.'


def test_rounding_and_duplicate_goods_conserve_small_and_large_payments(town):
    cfg, st = town
    needs = [dict(goodId='farm_tomatoes', quantity=1), dict(goodId='farm_tomatoes', quantity=2),
             dict(goodId='fish_stall_fresh_catch', quantity=2)]
    for amount in (1, 3, 7, 1000000001):
        allocation = R.allocate_payment(cfg, st, amount, needs)
        assert sum(allocation.values()) == amount
        assert allocation.get('0', 0) == (amount + 1) // 2
        assert allocation.get('1', 0) == amount // 2
        assert all(type(x) is int and x >= 0 for x in allocation.values())


def test_window_uses_payment_ticks_and_expires_at_exact_sixty_second_boundary(town):
    cfg, st = town
    R.record(cfg, st, 'walkIns', 2, tick=1, by_building={0: 2})
    R.record(cfg, st, 'regularBuyers', 15, tick=4, by_building={0: 15})
    assert R.payload(cfg, st, tick=4)['operatingIncome'] == 17
    assert R.payload(cfg, st, tick=5)['operatingIncome'] == 15
    assert R.payload(cfg, st, tick=8)['operatingIncome'] == 0


def test_non_divisor_tick_length_still_uses_seconds(town):
    cfg, st = town
    cfg['global']['tick'] = 7
    R.record(cfg, st, 'walkIns', 2, tick=1, by_building={0: 2})
    assert R.payload(cfg, st, tick=9)['operatingIncome'] == 2  # 56 seconds old.
    assert R.payload(cfg, st, tick=10)['operatingIncome'] == 0  # 63 seconds old.


def test_many_same_tick_receipts_and_long_replay_keep_a_bounded_persistent_window(town):
    cfg, st = town
    for tick in range(1, 101):
        for _ in range(30):
            R.record(cfg, st, 'walkIns', 1, tick=tick, by_building={0: 1})
        R.record(cfg, st, 'regularBuyers', 15, tick=tick, by_building={0: 15})
        st['tick'] = tick
        st = json.loads(json.dumps(st))
        assert len(st[R.STATE_KEY]['buckets']) <= 4
    view = R.payload(cfg, st)
    assert view['operatingIncome'] == 4 * 45
    assert view['observedSeconds'] == 60
    assert len(json.dumps(st[R.STATE_KEY])) < 1000


def test_old_save_does_not_backfill_lifetime_or_recent_retail_counters(town):
    cfg, st = town
    st['tick'] = 123
    st['cash'] = 900000
    st['recentRetail'] = {'0': [5, 6, 7, 8]}
    st['report'].update(retailEarned=500000, customerEarned=400000)
    st.pop(R.STATE_KEY, None)
    before = copy.deepcopy(st)
    view = R.payload(cfg, st)
    assert view['totalIncome'] == 0 and view['observedSeconds'] == 0
    assert st['cash'] == before['cash'] and st['report'] == before['report']
    R.record(cfg, st, 'regularBuyers', 15, tick=124, by_building={0: 15})
    st = json.loads(json.dumps(st))
    assert R.payload(cfg, st, tick=124)['operatingIncome'] == 15


def test_skipped_offline_production_clears_stale_receipts_without_changing_cash(town):
    cfg, st = town
    R.record(cfg, st, 'regularBuyers', 15, tick=1, by_building={0: 15})
    st['cash'] = 15
    R.prune(cfg, st, tick=2, clear=True)
    assert R.payload(cfg, st, tick=2)['operatingIncome'] == 0
    assert st['cash'] == 15
    assert R.payload(cfg, st, tick=2)['observedSeconds'] == 0
    R.record(cfg, st, 'walkIns', 2, tick=3, by_building={0: 2})
    assert R.payload(cfg, st, tick=3)['operatingIncome'] == 2


@pytest.mark.parametrize('source,amount,allocation', [
    ('invented', 1, {0: 1}), ('walkIns', -1, {0: -1}), ('walkIns', True, {0: 1}),
    ('walkIns', 2, {0: 1}), ('walkIns', 2, None), ('regularBuyers', 2, {30: 2}),
])
def test_bad_receipt_cannot_partially_change_history(town, source, amount, allocation):
    cfg, st = town
    before = copy.deepcopy(st)
    with pytest.raises(ValueError):
        R.record(cfg, st, source, amount, tick=1, by_building=allocation)
    assert st == before


def contract(st, slot, requirements, reward, seconds, paused=False):
    st['customerContracts']['active'].append(dict(id='test-{}'.format(slot), slot=slot,
        requirements=[dict(goodId=gid, quantity=qty) for gid, qty in requirements],
        reward=reward, intervalTicks=seconds // 15, paused=paused))


def test_regular_forecast_matches_initial_farm_channels_without_double_counting(town):
    cfg, st = town
    contract(st, 0, [('farm_tomatoes', 6)], 15, 120)
    contract(st, 1, [('farm_eggs', 4)], 20, 180)
    pool = {'farm_tomatoes': 4.0, 'farm_eggs': 2.0, 'farm_honey': 1.0}
    before = copy.deepcopy(st), copy.deepcopy(pool)
    flow = R.allocate_regular_flow(cfg, st, pool)
    retail = sum(min(flow['remaining'][gid], pool[gid] * .65) * E.catalog(cfg)[gid]['unitPrice'] for gid in pool)
    assert flow['incomePerMinute'] == pytest.approx(15 / 2 + 20 / 3)
    assert retail + flow['incomePerMinute'] == pytest.approx(24.03333333333333)
    for gid in pool:
        assert flow['remaining'][gid] + flow['unitsPerMinute'][gid] == pytest.approx(pool[gid])
    assert sum(flow['byBuilding'].values()) == pytest.approx(flow['incomePerMinute'])
    assert (st, pool) == before


def test_whole_bundle_shortage_limits_every_good_and_the_entire_payment(town):
    cfg, st = town
    contract(st, 0, [('farm_eggs', 4), ('roastery_pastries', 2)], 70, 120)
    pool = {'farm_eggs': 8.0, 'roastery_pastries': .5}
    flow = R.allocate_regular_flow(cfg, st, pool)
    assert flow['incomePerMinute'] == 17.5  # One whole bundle per four minutes.
    assert flow['remaining'] == {'farm_eggs': 7.0, 'roastery_pastries': 0.0}
    assert flow['customers'][0]['expectedIntervalSeconds'] == 240
    assert flow['customers'][0]['supplyLimited']
    assert sum(flow['byBuilding'].values()) == 17.5


def test_larger_regular_can_ship_late_without_forecasting_a_backlog(town):
    cfg, st = town
    contract(st, 0, [('farm_tomatoes', 12)], 33, 120)
    flow = R.allocate_regular_flow(cfg, st, {'farm_tomatoes': 4.0})
    assert flow['customers'][0]['expectedIntervalSeconds'] == 180
    assert flow['incomePerMinute'] == 11
    assert flow['remaining']['farm_tomatoes'] == 0


def test_slot_priority_paused_contracts_and_duplicate_requirements(town):
    cfg, st = town
    contract(st, 2, [('farm_tomatoes', 6)], 15, 120)
    contract(st, 0, [('farm_tomatoes', 6)], 15, 120, paused=True)
    contract(st, 1, [('farm_tomatoes', 3), ('farm_tomatoes', 3)], 15, 120)
    flow = R.allocate_regular_flow(cfg, st, {'farm_tomatoes': 4.0})
    assert [c['slot'] for c in flow['customers']] == [1, 2]
    assert flow['customers'][0]['deliveriesPerMinute'] == .5
    assert flow['customers'][1]['deliveriesPerMinute'] == pytest.approx(1 / 6)
    assert flow['incomePerMinute'] == 10
    assert flow['remaining']['farm_tomatoes'] == 0


def test_missing_one_finished_product_prevents_forecasting_any_bundle_income(town):
    cfg, st = town
    contract(st, 0, [('farm_eggs', 4), ('roastery_pastries', 2)], 70, 120)
    flow = R.allocate_regular_flow(cfg, st, {'farm_eggs': 8.0})
    assert flow['incomePerMinute'] == 0
    assert flow['remaining']['farm_eggs'] == 8
    assert flow['customers'][0]['expectedIntervalSeconds'] is None


def engine_view(cfg, st):
    return E.payload(cfg, st, E.new_class(cfg), {'paused': False})


def engine_replay(cfg, st, count):
    start = st['tick']
    E.advance_class(cfg, E.new_class(cfg), [st], start, start + count)


def test_real_regular_customers_improve_total_forecast_and_all_actual_cash_is_visible():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=7)
    assert E.town_income(cfg, st) == pytest.approx(15.6)
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    assert E.manage_customer_contract(cfg, st, 1, 'accept', customer_id='sunrise_diner')['ok']
    assert E.town_income(cfg, st) == pytest.approx(20.03333333333333)
    assert st['cash'] == 0, 'A forecast must never issue money.'
    changes = []
    witnessed_regular = False
    for _ in range(24):
        before = st['cash']
        costs_before = st['businessOperations']['totalOperatingCosts']
        engine_replay(cfg, st, 1)
        production_cost = st['businessOperations']['totalOperatingCosts'] - costs_before
        changes.append(st['cash'] - before + production_cost)
        view = engine_view(cfg, st)
        receipt = view['earnings']
        assert receipt['totalIncome'] == sum(changes[-4:])
        assert receipt['oneOffIncome'] == 0
        assert view['incomePerMinute'] == view['potentialIncomePerMinute'] == 20.03
        assert sum(b['incomePerMinute'] for b in view['buildings']) == view['incomePerMinute']
        assert view['buildings'][0]['earnings'] == receipt['byBuilding']['0']
        witnessed_regular |= receipt['bySource']['regularBuyers'] > 0
    assert witnessed_regular
    assert st['cash'] + st['businessOperations']['totalOperatingCosts'] == st['report']['retailEarned'] + st['report']['customerEarned']


def test_real_cross_shop_regular_shipment_pays_once_and_attributes_each_producer(town, monkeypatch):
    cfg, st = town
    # Add one possible catalog bundle to exercise a shipment spanning shops.
    # All stock is produced by the normal engine, with the real recipe costs.
    customer = ('shared_breakfast', 'Shared breakfast', 'Eggs and pastries', 120,
                (('farm_eggs', 2), ('roastery_pastries', 1)))
    monkeypatch.setattr(E, 'CUSTOMER_CATALOG', E.CUSTOMER_CATALOG + (customer,))
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='shared_breakfast')['ok']
    for _ in range(80):
        before = st['report']['customerEarned']
        engine_replay(cfg, st, 1)
        if st['report']['customerEarned'] > before:
            break
    else:
        pytest.fail('The cross-shop customer never received its real goods.')
    view = engine_view(cfg, st)
    receipt = view['earnings']
    assert st['customerContracts']['deliveries'] == 1
    assert receipt['bySource']['regularBuyers'] == 25
    assert receipt['byBuilding']['0']['bySource']['regularBuyers'] == 7
    assert receipt['byBuilding']['2']['bySource']['regularBuyers'] == 18
    assert receipt['byBuilding']['1']['bySource']['regularBuyers'] == 0
    assert sum(b['earnings']['operatingIncome'] for b in view['buildings']) == receipt['operatingIncome']
    saved = copy.deepcopy(st)
    engine_replay(cfg, st, 0)
    assert st == saved, 'Repeated reads must not replay a shipment payment.'


def test_real_orders_clearance_and_purchases_remain_separate_from_operating_income():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=7)
    engine_replay(cfg, st, 80)
    before = engine_view(cfg, st)['earnings']
    order = st['offers'][0]
    cash = st['cash']
    delivered = E.fulfill_order(cfg, st, 0, order['id'])
    assert delivered['ok']
    clearance = E.sell_one(cfg, st, 0)
    assert clearance['ok']
    view = engine_view(cfg, st)
    receipt = view['earnings']
    assert receipt['operatingIncome'] == before['operatingIncome']
    assert receipt['bySource']['orders'] == order['reward']
    assert receipt['bySource']['clearance'] == clearance['gross']
    assert receipt['bySource']['events'] == 0
    assert receipt['oneOffIncome'] == st['cash'] - cash
    assert receipt['totalIncome'] == before['totalIncome'] + order['reward'] + clearance['gross']
    cash = st['cash']
    purchase = E.buy_upgrade(cfg, st, 0, 'sales')
    assert purchase['ok']
    assert st['cash'] == cash - purchase['cost']
    assert engine_view(cfg, st)['earnings'] == receipt


def test_real_regular_forecast_changes_production_advice_when_buyer_is_supply_limited():
    cfg = E.load_config()
    st = E.new_state(cfg)
    assert E.upgrade_preview(cfg, st, 0, 'production')['incomeDelta'] == 0
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    engine_replay(cfg, st, 24)
    buyer = st['customerContracts']['active'][0]
    assert buyer['deliveries'] >= 3
    assert E.manage_customer_contract(cfg, st, 0, 'upgrade', contract_id=buyer['id'])['ok']
    preview = E.upgrade_preview(cfg, st, 0, 'production')
    assert preview['incomeDelta'] == pytest.approx(1.84)
    assert preview['consequence'] == 'Est. ongoing income +1.84 YM/min'


def test_real_engine_replay_and_json_chunking_preserve_identical_receipts(town):
    cfg, continuous = town
    for slot, customer in enumerate(('corner_grocer', 'harbor_bistro', 'copper_cafe')):
        assert E.manage_customer_contract(cfg, continuous, slot, 'accept', customer_id=customer)['ok']
    chunked = E.State(json.loads(json.dumps(continuous)))
    engine_replay(cfg, continuous, 160)
    for count in (1, 3, 9, 27, 40, 80):
        engine_replay(cfg, chunked, count)
        chunked = E.State(json.loads(json.dumps(chunked)))
    assert chunked == continuous
    assert engine_view(cfg, chunked) == engine_view(cfg, continuous)
    assert len(chunked[R.STATE_KEY]['buckets']) <= 4


def test_real_offline_cap_clears_window_and_resume_has_only_new_receipts():
    cfg = E.load_config()
    cfg['runtime']['offlineHours'] = .1  # Six minutes, to exercise the same cap cheaply.
    st = E.new_state(cfg)
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')['ok']
    engine_replay(cfg, st, 24)
    assert engine_view(cfg, st)['earnings']['bySource']['regularBuyers'] == 11
    cash = st['cash']
    engine_replay(cfg, st, 8)
    assert st['cash'] == cash
    assert engine_view(cfg, st)['earnings']['totalIncome'] == 0
    assert engine_view(cfg, st)['earnings']['observedSeconds'] == 0
    st = E.State(json.loads(json.dumps(st)))
    E.on_login(cfg, st)
    costs_before = st['businessOperations']['totalOperatingCosts']
    engine_replay(cfg, st, 1)
    production_cost = st['businessOperations']['totalOperatingCosts'] - costs_before
    assert engine_view(cfg, st)['earnings']['totalIncome'] == st['cash'] - cash + production_cost
    assert engine_view(cfg, st)['earnings']['observedSeconds'] == 15


def test_real_migration_starts_observation_at_the_relocated_clock():
    cfg = E.load_config()
    legacy = E.legacy.new_state(E.legacy.load_config(), start_tick=100, seed=7)
    migrated = E.migrate_state(cfg, legacy, tick=500)
    view = engine_view(cfg, migrated)
    assert migrated['tick'] == 500
    assert view['earnings']['observedSeconds'] == 0
    assert view['earnings']['totalIncome'] == 0
