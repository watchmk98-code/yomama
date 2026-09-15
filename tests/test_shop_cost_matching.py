"""Sale-matched reporting cannot charge manual orders to shop customers."""
import copy
import json

import pytest
import inventory_costs as costs
import operating_margins as margins
import production_economy as E


def setup():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=17)
    st['cash'] = 1000
    return cfg, st


def produce(cfg, st, quantity, cost, gid='farm_eggs'):
    st['cash'] -= cost
    costs.produce(cfg, st, gid, quantity, cost)
    st['inventory'][gid] = st['inventory'].get(gid, 0) + quantity


def sell(cfg, st, quantity, reward, source, gid='farm_eggs'):
    needs = [dict(goodId=gid, quantity=quantity)]
    basis = costs.consume(cfg, st, needs)
    st['inventory'][gid] -= quantity
    return margins.pay(cfg, st, source, reward, needs, costed=basis)


def test_unsold_goods_and_manual_orders_do_not_change_shop_result():
    cfg, st = setup()
    produce(cfg, st, 10, 20)
    assert margins.town_statement(cfg, st)['costs'] == 0
    invoice = sell(cfg, st, 4, 40, 'walkIns')
    before = margins.town_statement(cfg, st)
    assert before['sales'] == invoice['grossSales']
    assert before['productionCosts'] == 8
    assert before['profit'] == 32
    assert before['margin'] == pytest.approx(32 / invoice['grossSales'] * 100)
    # Both producing more stock and delivering an order must leave shop results alone.
    produce(cfg, st, 4, 8)
    sell(cfg, st, 5, 100, 'orders')
    after = margins.town_statement(cfg, st)
    for key in ('sales', 'costs', 'productionCosts', 'sellingCosts', 'profit', 'margin'):
        assert after[key] == before[key]
    assert after['bySource']['orders']['productionCosts'] == 10
    assert after['bySource']['orders']['profit'] == 90
    assert st['inventory']['farm_eggs'] == 5
    assert st['inventoryCosts']['goods']['farm_eggs']['costMicros'] == 10 * costs.SCALE
    assert st['cash'] == 1112


def test_weighted_average_is_saved_and_never_repriced_on_upgrade():
    cfg, st = setup()
    produce(cfg, st, 4, 8)
    produce(cfg, st, 6, 24)
    st['b'][0].update(sales=12, storage=12)
    st = E.migrate_state(cfg, json.loads(json.dumps(st)))
    sell(cfg, st, 3, 40, 'regularBuyers')
    view = margins.town_statement(cfg, st)
    assert view['productionCosts'] == pytest.approx(9.6)
    assert view['profit'] == pytest.approx(30.4)
    assert not view['estimatedCostBasis']
    sell(cfg, st, 7, 50, 'orders')
    assert margins.town_statement(cfg, st)['bySource']['orders']['productionCosts'] == pytest.approx(22.4)
    assert st['inventoryCosts']['goods']['farm_eggs']['costMicros'] == 0


def test_real_production_is_carried_and_retail_releases_only_its_share():
    cfg, st = setup()
    for good in cfg['tiers'][0]['goods']:
        st['productionWork'][good['id']] = good['cycleTicks'] * 100
    before_cash = st['cash']
    E._produce(cfg, st)
    paid = before_cash - st['cash']
    assert paid > 0
    assert sum(p['costMicros'] for p in st['inventoryCosts']['goods'].values()) == paid * costs.SCALE
    assert margins.town_statement(cfg, st)['productionCosts'] == 0
    for good in cfg['tiers'][0]['goods']:
        st['salesWork'][good['id']] = good['cycleTicks'] * 10000
    E._retail(cfg, st, protected={})
    statement = margins.town_statement(cfg, st)
    remaining = sum(p['costMicros'] for p in st['inventoryCosts']['goods'].values()) / costs.SCALE
    assert statement['productionCosts'] + remaining == pytest.approx(paid)
    assert statement['profit'] == pytest.approx(statement['takeHome'] - statement['productionCosts'])


def test_engine_order_settlement_consumes_cost_without_shop_expense():
    cfg, st = setup()
    produce(cfg, st, 10, 20)
    order = st['offers'][1]
    order.update(requirements=[dict(goodId='farm_eggs', quantity=3)], reward=40)
    # Re-freeze the order terms after changing the fixture's requested goods.
    order.pop('sellingTerms', None)
    assert E.fulfill_order(cfg, st, 1, order['id'])['ok']
    view = margins.town_statement(cfg, st)
    assert view['sales'] == view['costs'] == view['profit'] == 0
    assert view['margin'] is None
    assert view['bySource']['orders']['productionCosts'] == 6
    assert view['bySource']['orders']['profit'] == 34


def test_legacy_stock_estimate_is_explicit_and_migration_is_idempotent():
    cfg, st = setup()
    st.pop('inventoryCosts', None)
    st['inventory'] = {'farm_eggs': 6}
    st['operatingMargins'].pop('costMatchingVersion')
    before = copy.deepcopy(st)
    migrated = E.migrate_state(cfg, st)
    for key in ('cash', 'inventory', 'book', 'tick', 'b'):
        assert migrated[key] == before[key]
    assert migrated['inventoryCosts']['openingEstimates']['farm_eggs']['quantity'] == 6
    assert margins.town_statement(cfg, migrated)['sales'] == 0
    assert E.migrate_state(cfg, copy.deepcopy(migrated)) == migrated
    sell(cfg, migrated, 1, 10, 'walkIns')
    assert margins.town_statement(cfg, migrated)['estimatedCostBasis']


def test_clearance_and_non_sale_consumption_cannot_leak_into_shop_costs():
    cfg, st = setup()
    produce(cfg, st, 10, 20)
    costs.consume(cfg, st, [dict(goodId='farm_eggs', quantity=2)])
    st['inventory']['farm_eggs'] -= 2
    assert E.sell_one(cfg, st, 0)['ok']
    view = margins.town_statement(cfg, st)
    assert view['costs'] == view['profit'] == 0
    assert view['bySource']['clearance']['productionCosts'] == 16
    assert st['inventoryCosts']['goods']['farm_eggs']['costMicros'] == 0


def test_fractional_cost_conservation_expiry_and_rejected_consumption():
    cfg, st = setup()
    produce(cfg, st, 3, 1)
    before = copy.deepcopy(st)
    with pytest.raises(ValueError):
        costs.consume(cfg, st, [dict(goodId='farm_eggs', quantity=4)])
    assert st == before
    for _ in range(3):
        sell(cfg, st, 1, 10, 'walkIns')
    view = margins.town_statement(cfg, st)
    assert view['productionCosts'] == 1
    st['tick'] += 4
    view = margins.town_statement(cfg, st)
    assert view['sales'] == view['costs'] == view['profit'] == 0
    assert view['margin'] is None
