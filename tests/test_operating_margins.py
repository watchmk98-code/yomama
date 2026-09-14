"""Invoices change accounting without changing cash, goods or saved rewards."""
from __future__ import annotations

import copy
import json

import pytest

import business_operations as operations
import earnings
import operating_margins as margins
import order_engine as orders
import production_economy as economy
from previews.playtest_operating_margins import economic_state, prepare, run_pair


@pytest.mark.parametrize('source', ('walkIns', 'regularBuyers', 'orders', 'clearance'))
def test_each_source_pays_from_proceeds_and_conserves_fractional_fees(source):
    cfg, state = prepare(True, [0, 1])
    state['cash'] = 0
    requirements = [dict(goodId='farm_tomatoes', quantity=2),
                    dict(goodId='fish_stall_fresh_catch', quantity=3)]
    original = copy.deepcopy(state)
    quote = margins.quote(cfg, state, 17, requirements, source=source)
    assert state == original, 'A quote must never initialize history or issue cash.'
    paid_fees = 0
    for number in range(7):
        receipt = margins.pay(cfg, state, source, 17, requirements, terms=quote['terms'])
        assert receipt['grossSales'] - receipt['sellingCosts'] == 17
        assert sum(row['takeHome'] for row in receipt['byBuilding'].values()) == 17
        paid_fees += receipt['sellingCosts']
        assert state['cash'] == 17 * (number + 1)
        state = economy.State(json.loads(json.dumps(state)))
    raw = 7 * sum(quote['terms']['feeMicrosByGood'][need['goodId']] * need['quantity'] for need in requirements)
    carry = sum(values.get(source, 0) for values in state['operatingMargins']['remainders'].values())
    assert paid_fees * margins.FEE_SCALE + carry == raw
    assert earnings.payload(cfg, state)['bySource'][source] == 119
    assert state['inventory'] == original['inventory'], 'The sale caller owns the single inventory debit.'
    assert [b['costRemainder'] for b in state['b']] == [b['costRemainder'] for b in original['b']]
    assert all(values.get(other, 0) == 0 for values in state['operatingMargins']['remainders'].values()
               for other in earnings.SOURCES if other != source)


def test_fixed_tariffs_ignore_upgrades_staff_and_reward_but_respect_stable_config():
    cfg, state = prepare(True, [0, 3])
    requirement = [dict(goodId='garage_repairs', quantity=1)]
    original = margins.tariffs(cfg)
    for building in state['b']:
        building.update(lv=12, sales=12, storage=12,
                        staff=dict(id='technician', remainingTicks=20))
    cheap = margins.quote(cfg, state, 1, requirement)
    jackpot = margins.quote(cfg, state, 100_000, requirement)
    assert cheap['sellingCosts'] == jackpot['sellingCosts']
    assert margins.tariffs(cfg) == original
    cfg['operatingMargins']['targets']['garage'] = 24
    changed = margins.tariffs(cfg)
    assert changed['garage_repairs'] < original['garage_repairs']
    assert changed['farm_tomatoes'] == original['farm_tomatoes']


def test_all_products_match_the_reference_sold_unit_target_without_forcing_current_profit():
    cfg, state = prepare(True, list(range(15)))
    quantity = margins.FEE_SCALE
    for tier in cfg['tiers']:
        for good in tier['goods']:
            requirements = [dict(goodId=good['id'], quantity=quantity)]
            net = good['unitPrice'] * quantity
            invoice = margins.quote(cfg, state, net, requirements)
            production = operations.base_batch_cost(cfg, good) / good['quantity'] * quantity
            realized = (invoice['grossSales'] - invoice['sellingCosts'] - production) / invoice['grossSales'] * 100
            assert realized == pytest.approx(margins.target_margin(cfg, tier['id']), abs=0.00001)
    rates = economy.flow_rates(cfg, state)
    before = margins.statement(cfg, state, 3, rates, 100, 10)
    overproducing = margins.statement(cfg, state, 3, rates, 100, 150)
    assert before['potentialProfit'] == 90
    assert overproducing['potentialProfit'] == -50
    assert overproducing['potentialMargin'] < 0
    assert overproducing['potentialMargin'] != overproducing['targetMarginPercent']


def test_frozen_raw_tariffs_survive_config_changes_and_reload():
    cfg, state = prepare(True, [0])
    requirement = [dict(goodId='farm_tomatoes', quantity=1)]
    terms = margins.quote(cfg, state, 2, requirement)['terms']
    margins.pay(cfg, state, 'walkIns', 2, requirement, terms=terms)
    expected = margins.quote(cfg, state, 2, requirement, source='walkIns', terms=terms)
    state = economy.State(json.loads(json.dumps(state)))
    cfg['operatingMargins']['targets']['farm'] = 25
    assert margins.quote(cfg, state, 2, requirement)['terms'] != terms
    paid = margins.pay(cfg, state, 'walkIns', 2, requirement, terms=terms)
    assert paid == expected


def test_regular_forecast_keeps_accepted_tariffs_when_new_walkin_tariffs_change():
    cfg, state = prepare(True, [0])
    assert economy.manage_customer_contract(cfg, state, 0, 'accept', 'corner_grocer')['ok']
    contract = state['customerContracts']['active'][0]
    frozen = copy.deepcopy(contract['sellingTerms']['feeMicrosByGood'])
    rates, flow = economy._flows(cfg, state)
    income = economy.town_income(cfg, state)
    cost = operations.forecast_cost(cfg, state, 0, rates)
    before = margins.statement(cfg, state, 0, rates, income, cost)
    cfg['operatingMargins']['targets']['farm'] = 30
    state = economy.State(json.loads(json.dumps(state)))
    after = margins.statement(cfg, state, 0, rates, income, cost)
    current = margins.tariffs(cfg)
    walkin_fees = sum(row['retail'] * current[gid] / margins.FEE_SCALE for gid, row in rates.items())
    regular_fees = sum(frozen[need['goodId']] * need['quantity'] / margins.FEE_SCALE
                       for need in contract['requirements']) * flow['customers'][0]['deliveriesPerMinute']
    assert after['potentialSellingCosts'] == pytest.approx(walkin_fees + regular_fees, abs=0.005)
    repriced_regular_fees = sum(row.get('regulars', 0) * current[gid] / margins.FEE_SCALE for gid, row in rates.items())
    assert regular_fees != pytest.approx(repriced_regular_fees)
    assert after['potentialProfit'] == before['potentialProfit']


def test_forecast_preserves_existing_profit_before_rounding_individual_components():
    cfg, state = prepare(True, list(range(15)))
    for slot, buyer in enumerate(('copper_cafe', 'rally_crew', 'builders_union', 'neighborhood_grid')):
        assert economy.manage_customer_contract(cfg, state, slot, 'accept', buyer)['ok']
    for building in state['b']:
        building.update(lv=2, sales=2, storage=1)
    rates, regulars = economy._flows(cfg, state)
    for slot, building in enumerate(state['b']):
        income = sum(rates[g['id']]['retail'] * g['unitPrice'] for g in cfg['tiers'][building['tier']]['goods'])
        income += regulars['byBuilding'].get(str(slot), 0)
        cost = operations.forecast_cost(cfg, state, slot, rates)
        old = operations.building_payload(cfg, state, slot, 0, income, rates)
        view = margins.statement(cfg, state, slot, rates, income, cost)
        assert view['potentialProfit'] == old['potentialProfitPerMinute']
        assert round(view['potentialSales'] - view['potentialCosts'], 2) == view['potentialProfit']
        assert view['potentialProductionCosts'] == cost


def test_missing_old_flag_migrates_without_inventing_previous_invoices():
    cfg, state = prepare(False, [0])
    state['tick'] = 25
    state['cash'] = 120
    state['productionWork']['farm_eggs'] = 150
    earnings.record(cfg, state, 'walkIns', 8, by_building={0: 8})
    cfg.pop('operatingMargins')
    state.pop('operatingMargins', None)
    old = economic_state(state)
    migrated = economy.migrate_state(cfg, state)
    assert margins.enabled(cfg)
    assert economic_state(migrated) == old
    assert migrated['operatingMargins']['buckets'] == []
    assert migrated['operatingMargins']['totals']['grossSales'] == 0
    view = margins.statement(cfg, migrated, 0, economy.flow_rates(cfg, migrated), 15.6, 3)
    assert view['sales'] == 8 and view['sellingCosts'] == 0
    reloaded = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(migrated))))
    assert reloaded == migrated


def test_recent_window_expires_without_losing_cumulative_totals_or_fractional_carry():
    cfg, state = prepare(True, [0])
    requirement = [dict(goodId='farm_tomatoes', quantity=1)]
    for tick in range(1, 30):
        margins.pay(cfg, state, 'walkIns', 2, requirement, tick=tick)
        state['tick'] = tick
        assert len(state['operatingMargins']['buckets']) <= 4
    data = copy.deepcopy(state['operatingMargins'])
    state['tick'] += 4
    margins.prune(cfg, state)
    assert state['operatingMargins']['buckets'] == []
    assert state['operatingMargins']['totals'] == data['totals']
    assert state['operatingMargins']['remainders'] == data['remainders']
    margins.pay(cfg, state, 'orders', 20, requirement)
    totals = copy.deepcopy(state['operatingMargins']['totals'])
    margins.prune(cfg, state, tick=100, clear=True)
    assert state['operatingMargins']['buckets'] == []
    assert state['operatingMargins']['totals'] == totals


def test_removed_business_receipts_and_production_costs_still_reconcile_at_town_level():
    cfg, state = prepare(True, [0, 3])
    building = state['b'][1]
    building.update(investmentKnown=True, cashInvested=100, bookValue=100)
    requirement = [dict(goodId='garage_repairs', quantity=1)]
    receipt = margins.pay(cfg, state, 'walkIns', 12, requirement)
    good = cfg['tiers'][3]['goods'][0]
    assert operations.charge_batch(cfg, state, building, good, state['tick'])
    fee = receipt['sellingCosts']
    identity = building['buildingId']
    result = operations.manage(cfg, state, dict(buildingId=identity, action='salvage'))
    assert result['ok'], result
    town = margins.town_statement(cfg, state)
    assert town['sales'] == 12 + fee
    assert town['costs'] == 1 + fee
    assert town['profit'] == town['unattributed']['profit'] == 11
    assert town['unattributed']['sellingCosts'] == fee
    assert identity not in state['operatingMargins']['remainders']


def test_prototype_dispatch_freezes_invoice_and_completes_exactly_once():
    cfg, state = prepare(True, [0])
    board = orders.create_board(cfg, state)
    offer = board['offers'][0]
    for need in offer['requirements']:
        board['inventory'][need['goodId']] = need['quantity']
    opening = board['cash']
    assert orders.apply_action(cfg, board, 0, 'fulfill', offer['id'])['ok']
    assert board['cash'] == opening
    dispatched = board['offers'][0]
    expected = margins.quote(cfg, board, dispatched['reward'], dispatched['requirements'],
                             source='orders', terms=dispatched['sellingTerms'])
    board = orders.create_board(cfg, json.loads(json.dumps(board)))
    cfg['operatingMargins']['targets']['farm'] = 30
    board['tick'] = dispatched['deliveryUntilTick']
    orders.refresh_board(cfg, board)
    assert board['cash'] == opening + dispatched['reward']
    assert board['operatingMargins']['bySource']['orders']['grossSales'] == expected['grossSales']
    complete = copy.deepcopy(board)
    orders.refresh_board(cfg, board)
    assert board == complete
    assert not orders.apply_action(cfg, board, 0, 'fulfill', dispatched['id'])['ok']
    assert board == complete


@pytest.mark.parametrize('connected', (False, True))
def test_fixed_project_and_goal_invoices_are_frozen_before_saving_and_reload(connected):
    cfg = economy.load_config()
    cfg['businessDesign']['connectedProgression'] = connected
    state = economy.new_state(cfg, seed=71)
    economy._sync_project_offer(cfg, state)
    index = 3 if connected else 2
    order = state['goalOffer'] if connected else state['offers'][2]
    terms = copy.deepcopy(order['sellingTerms'])
    assert economy.commit_order(cfg, state, index, order['id'], True)['ok']
    cfg['operatingMargins']['targets']['farm'] = 30
    state = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(state))))
    saved = state['goalOffer'] if connected else state['offers'][2]
    assert saved['sellingTerms'] == terms
    for need in saved['requirements']:
        state['inventory'][need['goodId']] = need['quantity']
    expected = margins.quote(cfg, state, saved['reward'], saved['requirements'], source='orders', terms=terms)
    cash = state['cash']
    assert economy.fulfill_order(cfg, state, index, saved['id'])['ok']
    assert state['cash'] == cash + saved['reward']
    assert state['operatingMargins']['bySource']['orders']['grossSales'] == expected['grossSales']


@pytest.mark.parametrize('condition', ('paused', 'full', 'cash-empty'))
def test_blocked_production_does_not_create_sales_or_invoice_charges(condition):
    cfg, state = prepare(True, [3])
    building = state['b'][0]
    building['reserve'] = True
    if condition == 'paused':
        building['paused'] = True
    elif condition == 'full':
        for good in cfg['tiers'][3]['goods']:
            state['inventory'][good['id']] = economy._good_capacity(cfg, state, 0, good['id'])
    else:
        state['cash'] = 0
    cash, stock = state['cash'], copy.deepcopy(state['inventory'])
    for _ in range(8):
        economy.player_tick(cfg, {}, state, state['tick'])
    assert state['cash'] == cash and state['inventory'] == stock
    assert state['operatingMargins']['totals'] == dict(takeHome=0, grossSales=0, sellingCosts=0)
    rates = economy.flow_rates(cfg, state)
    view = margins.statement(cfg, state, 0, rates, 0, operations.forecast_cost(cfg, state, 0, rates))
    assert view['sales'] == 0 and view['margin'] is None and view['potentialMargin'] is None


@pytest.mark.parametrize('spec', [
    dict(tiers=[0], fresh=True, policy='regulars-manual'),
    dict(tiers=list(range(6)), policy='regulars-manual'),
    dict(tiers=list(range(15)), level='max', policy='regulars-manual', warm_ticks=16),
])
def test_real_ticks_preserve_all_economic_state_actions_and_affordability(spec):
    result = run_pair(ticks=32, **spec)
    assert result['identicalGameplay']
    assert result['baseline']['netCash'] == result['changed']['netCash']
