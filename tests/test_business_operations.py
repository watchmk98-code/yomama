"""Cash conservation, recovery, shift timing and safe closure for new rules."""
from __future__ import annotations

import copy
import json

import pytest

import business_operations as O
import business_progression as P
import earnings
import production_economy as E


def town():
    cfg = E.load_config()
    # These saved-class contracts cover the pre-workforce operations rules.
    # Current permanent teams have separate workforce integration coverage.
    cfg.pop('workforce', None)
    cfg['businessDesign']['enabled'] = True
    st = E.new_state(cfg)
    st['cash'] = 10000
    return cfg, st


def ticks(cfg, st, count):
    for _ in range(count):
        E.player_tick(cfg, {}, st, st['tick'])


def built_fish(cfg, st, grant=False):
    if grant:
        st['townProjects']['grants']['fish_stall'] = 'ready'
    quote = E.expand(cfg, st, 1, st['tick'])
    assert quote['ok'], quote
    E.finish_build(cfg, st, st['build']['t'])
    st['townProjects']['completed'] = 3
    return st['b'][-1]


def act(cfg, st, building, action, **kw):
    return E.manage_business(cfg, st, dict(buildingId=building['buildingId'], action=action, **kw))


def view(cfg, st):
    return E.payload(cfg, st, {}, {'paused': 0})


def test_completed_batches_cost_cash_and_rolling_profit_reconciles():
    cfg, st = town()
    before = st['cash']
    ticks(cfg, st, 4)
    data = view(cfg, st)
    expense = st['businessOperations']['totalOperatingCosts']
    receipts = data['earnings']['totalIncome']
    assert expense > 0
    assert st['cash'] == before + receipts - expense
    assert data['operations']['operatingCostPerMinute'] == expense
    assert data['operations']['profitPerMinute'] == data['earnings']['operatingIncome'] - expense
    assert data['buildings'][0]['operatingCostPerMinute'] == expense


def test_cash_shortage_never_consumes_recipe_inputs_or_creates_debt():
    cfg, st = town()
    st['b'].append(E._building(2))
    st['tierOf'].append(2)
    st['b'][0]['paused'] = True
    st['b'][1]['reserve'] = True
    st['inventory']['roastery_roasted_beans'] = 1
    st['cash'] = 0
    ticks(cfg, st, 8)
    assert st['cash'] == 0
    assert st['inventory']['roastery_roasted_beans'] == 1
    assert st['inventory'].get('roastery_espresso_shots', 0) == 0
    assert st['productionBlocked']['roastery_espresso_shots']['reason'] == 'cash'
    assert st['businessOperations']['totalOperatingCosts'] == 0


def test_empty_wallet_recovers_through_starter_tomatoes():
    cfg, st = town()
    st['cash'] = 0
    ticks(cfg, st, 8)
    assert st['cash'] > 0
    assert st['report']['unitsSold'] > 0
    assert not act(cfg, st, st['b'][0], 'salvage')['ok']


def test_first_sale_clears_stale_cash_shortage_status_when_next_batch_is_affordable():
    cfg, st = town()
    st['cash'] = 0
    ticks(cfg, st, 2)
    assert st['productionBlocked']['farm_eggs']['reason'] == 'cash'
    assert st['cash'] >= cfg['tiers'][0]['goods'][1]['operatingCost']
    assert view(cfg, st)['buildings'][0]['status'] != 'Need cash for production'
    st['cash'] = 0
    assert view(cfg, st)['buildings'][0]['status'] == 'Need cash for production'
    act(cfg, st, st['b'][0], 'pause')
    assert view(cfg, st)['buildings'][0]['status'] == 'Business paused'


def test_paused_or_full_shelves_do_not_charge_running_costs():
    cfg, st = town()
    st['b'][0]['reserve'] = True
    for good in cfg['tiers'][0]['goods']:
        st['inventory'][good['id']] = E._good_capacity(cfg, st, 0, good['id'])
    before = st['cash']
    ticks(cfg, st, 10)
    assert st['cash'] == before and st['businessOperations']['totalOperatingCosts'] == 0
    st['inventory'] = {}
    assert act(cfg, st, st['b'][0], 'pause')['ok']
    ticks(cfg, st, 10)
    assert st['cash'] == before and not st['inventory']
    assert act(cfg, st, st['b'][0], 'resume')['ok']
    ticks(cfg, st, 4)
    assert st['businessOperations']['totalOperatingCosts'] > 0


def test_staff_boosts_real_production_once_and_freezes_with_business_pause():
    cfg, baseline = town()
    hired = copy.deepcopy(baseline)
    for st in (baseline, hired):
        st['b'][0]['reserve'] = True
    before = hired['cash']
    result = act(cfg, hired, hired['b'][0], 'hire', staffId='assistant')
    assert result['ok'] and hired['cash'] == before - result['cost']
    assert not act(cfg, hired, hired['b'][0], 'hire', staffId='assistant')['ok']
    remaining = hired['b'][0]['staff']['remainingTicks']
    act(cfg, hired, hired['b'][0], 'pause')
    ticks(cfg, hired, 8)
    assert hired['b'][0]['staff']['remainingTicks'] == remaining
    act(cfg, hired, hired['b'][0], 'resume')
    ticks(cfg, baseline, remaining)
    ticks(cfg, hired, remaining)
    assert hired['inventory']['farm_tomatoes'] > baseline['inventory']['farm_tomatoes']
    assert hired['b'][0]['staff'] is None
    assert hired['businessOperations']['staffHired'] == 1


def test_technician_halves_completed_batch_costs_with_integer_carry():
    cfg, baseline = town()
    hired = copy.deepcopy(baseline)
    for st in (baseline, hired):
        st['b'][0]['reserve'] = True
    assert act(cfg, hired, hired['b'][0], 'hire', staffId='technician')['ok']
    ticks(cfg, baseline, 8)
    ticks(cfg, hired, 8)
    assert baseline['inventory'] == hired['inventory']
    assert hired['businessOperations']['totalOperatingCosts'] == baseline['businessOperations']['totalOperatingCosts'] // 2
    assert type(hired['cash']) is int


def test_specialist_finishes_more_real_recipes_and_still_consumes_ingredients():
    cfg, baseline = town()
    baseline['b'].append(E._building(2))
    baseline['tierOf'].append(2)
    O.ensure(cfg, baseline)
    baseline['b'][0]['paused'] = True
    baseline['b'][1]['reserve'] = True
    baseline['inventory'].update(farm_eggs=20, farm_honey=20, roastery_roasted_beans=20)
    hired = copy.deepcopy(baseline)
    assert act(cfg, hired, hired['b'][1], 'hire', staffId='specialist')['ok']
    ticks(cfg, baseline, 8)
    ticks(cfg, hired, 8)
    assert hired['inventory']['roastery_pastries'] > baseline['inventory']['roastery_pastries']
    assert hired['inventory']['farm_eggs'] < baseline['inventory']['farm_eggs']
    assert hired['inventory']['farm_honey'] < baseline['inventory']['farm_honey']


def test_specialist_requires_an_unlocked_recipe_before_charging_cash():
    cfg, st = town()
    st['b'].append(E._building(3))
    st['tierOf'].append(3)
    O.ensure(cfg, st)
    b = st['b'][1]
    quote = next(role for role in O.staff_options(cfg, st, 1) if role['id'] == 'specialist')
    assert not quote['canHire'] and 'signature quest' in quote['why']
    before = copy.deepcopy(st)
    result = act(cfg, st, b, 'hire', staffId='specialist')
    assert not result['ok'] and 'signature quest' in result['why']
    assert st == before
    st['businessProgression']['quests']['garage-signature'] = dict(completed=True)
    b['processing'] = False
    paused = copy.deepcopy(st)
    result = act(cfg, st, b, 'hire', staffId='specialist')
    assert not result['ok'] and result['why'] == 'Resume recipes before hiring'
    assert st == paused
    b['processing'] = True
    assert act(cfg, st, b, 'hire', staffId='specialist')['ok']
    assert st['cash'] < before['cash']


def test_business_pause_stops_regular_shipments_and_expenses_until_resumed():
    cfg, st = town()
    assert E.manage_customer_contract(cfg, st, 0, 'accept', 'corner_grocer')['ok']
    st['inventory']['farm_tomatoes'] = 6
    assert act(cfg, st, st['b'][0], 'pause')['ok']
    before = st['cash']
    ticks(cfg, st, 12)
    assert st['cash'] == before
    assert st['customerContracts']['deliveries'] == 0
    assert st['inventory']['farm_tomatoes'] == 6
    assert act(cfg, st, st['b'][0], 'resume')['ok']
    ticks(cfg, st, 1)
    assert st['customerContracts']['deliveries'] == 1


def test_staff_and_costs_do_not_run_during_skipped_offline_time():
    cfg, st = town()
    cfg['runtime']['offlineHours'] = 0
    assert act(cfg, st, st['b'][0], 'hire', staffId='assistant')['ok']
    before = st['cash']
    remaining = st['b'][0]['staff']['remainingTicks']
    E.advance_class(cfg, {}, [st], 0, 1000)
    assert st['cash'] == before
    assert st['b'][0]['staff']['remainingTicks'] == remaining
    assert view(cfg, st)['operations']['operatingCostPerMinute'] == 0


def test_salvage_refunds_only_cash_and_removes_full_book_value():
    for grant in (False, True):
        cfg, st = town()
        b = built_fish(cfg, st, grant=grant)
        assert E.buy_upgrade(cfg, st, 1, 'storage')['ok']
        quote = O.salvage_quote(cfg, st, 1)
        assert quote['canSalvage']
        if grant:
            assert b['cashInvested'] < b['bookValue']
        cash, book = st['cash'], st['book']
        result = act(cfg, st, b, 'salvage')
        assert result['ok']
        assert st['cash'] == cash + quote['cashInvested'] * 45 // 100
        assert st['book'] == book - quote['bookValue']
        assert not E.can_expand(cfg, st, 1)['ok']
        st['tick'] += 300 // cfg['global']['tick']
        assert E.expand(cfg, st, 1, st['tick'])['ok']
        E.finish_build(cfg, st, st['build']['t'])
        assert st['b'][-1]['buildingId'] != b['buildingId']
        assert not act(cfg, st, b, 'pause')['ok']


def test_closure_blocks_stock_regulars_and_committed_dependency_orders():
    cfg, st = town()
    b = built_fish(cfg, st)
    st['inventory']['fish_stall_fresh_catch'] = 1
    assert not act(cfg, st, b, 'salvage')['ok']
    st['inventory'] = {}
    result = E.manage_customer_contract(cfg, st, 0, 'accept', 'harbor_bistro')
    assert result['ok']
    assert not act(cfg, st, b, 'salvage')['ok']
    contract = st['customerContracts']['active'][0]
    E.manage_customer_contract(cfg, st, 0, 'release', contract_id=contract['id'])
    st['offers'][0].update(committed=True, requirements=[dict(goodId='cannery_canned_goods', quantity=1)])
    assert not act(cfg, st, b, 'salvage')['ok']


def test_slot_remap_preserves_other_business_receipts_and_town_totals():
    cfg, st = town()
    b = built_fish(cfg, st)
    assert E.expand(cfg, st, 2, st['tick'])['ok']
    E.finish_build(cfg, st, st['build']['t'])
    earnings.record(cfg, st, 'walkIns', 30, by_building={1: 10, 2: 20})
    E.business_activity.record(cfg, st, 'production', {1: 3, 2: 7})
    O.charge_batch(cfg, st, b, cfg['tiers'][1]['goods'][0], st['tick'])
    assert act(cfg, st, b, 'salvage')['ok']
    data = view(cfg, st)
    assert data['buildings'][1]['id'] == 'roastery'
    assert data['buildings'][1]['earnings']['operatingIncome'] == 20
    assert data['buildings'][1]['activity']['producedUnits'] == 7
    assert data['earnings']['operatingIncome'] == 30
    assert data['earnings']['unattributed']['operatingIncome'] == 10
    assert data['operations']['profitPerMinute'] == 29
    assert data['operations']['closedOperatingCostPerMinute'] == 1


def test_reload_and_migration_preserve_identities_investments_and_shifts():
    cfg, st = town()
    b = built_fish(cfg, st)
    act(cfg, st, b, 'hire', staffId='assistant')
    ticks(cfg, st, 3)
    E.migrate_state(cfg, st)
    restored = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert restored == st
    assert E.migrate_state(cfg, restored) == restored
    ticks(cfg, st, 5)
    ticks(cfg, restored, 5)
    assert restored == st


def test_missing_feature_flag_preserves_legacy_no_expense_rules():
    cfg, st = town()
    cfg.pop('businessDesign')
    st = E.new_state(cfg)
    st['b'][0]['reserve'] = True
    ticks(cfg, st, 8)
    assert st['cash'] == 0
    assert st['inventory']['farm_honey'] == 2
    assert 'businessOperations' not in st
    assert not view(cfg, st)['operations']['enabled']


def test_crafted_equipment_keeps_asset_value_and_is_not_cash_salvage():
    cfg, st = town()
    cfg['businessDesign'].pop('connectedProgression', None)  # Preserve old crafted-asset rules.
    st['cash'] = 1000000
    st['tierOf'] = list(range(6))
    st['b'] = [E._building(tier) for tier in st['tierOf']]
    st['offers'] = []
    st['townProjects']['completed'] = 3
    p = P.ensure(cfg, st)
    p['research'].append('food-basics')
    st['inventory'].update(garage_spare_parts=3, workshop_steel_brackets=2)
    E._sync_pools(cfg, st)
    before = E.net_worth(st)
    assert P.act(cfg, st, dict(action='craft', equipmentId='preservation-kit'))['ok']
    E._sync_pools(cfg, st)
    equipment = st['businessProgression']['equipmentValue']
    assert equipment > 0 and E.net_worth(st) == before
    quote = E.expand(cfg, st, 6, st['tick'])
    assert quote['ok'], quote
    assert st['businessProgression']['equipmentValue'] == 0
    assert E.net_worth(st) == before
    E.finish_build(cfg, st, st['build']['t'])
    b = st['b'][-1]
    assert b['bookValue'] == quote['cost'] + equipment
    assert b['cashInvested'] == quote['cost']
    salvage = O.salvage_quote(cfg, st, len(st['b']) - 1)
    assert salvage['value'] == quote['cost'] * 45 // 100


@pytest.mark.parametrize('kind', ('production', 'sales', 'storage'))
def test_upgrade_preview_and_real_operation_both_include_higher_running_costs(kind):
    cfg, baseline = town()
    upgraded = copy.deepcopy(baseline)
    preview = E.upgrade_preview(cfg, upgraded, 0, kind)
    assert preview['operatingCostScope'] == 'business'
    assert preview['operatingCostAfter'] > preview['operatingCostBefore']
    assert preview['operatingCostDelta'] == pytest.approx(preview['operatingCostAfter'] - preview['operatingCostBefore'])
    assert preview['profitAfter'] == pytest.approx(preview['businessIncomeAfter'] - preview['operatingCostAfter'])
    cash = upgraded['cash']
    purchase = E.buy_upgrade(cfg, upgraded, 0, kind)
    assert purchase['ok'] and upgraded['cash'] == cash - purchase['cost']
    assert upgraded['businessOperations']['totalOperatingCosts'] == 0, 'Buying pays only the displayed upfront fee.'
    shop = view(cfg, upgraded)['buildings'][0]
    assert shop['potentialOperatingCostPerMinute'] == preview['operatingCostAfter']
    assert shop['potentialProfitPerMinute'] == preview['profitAfter']
    for st in (baseline, upgraded):
        st['b'][0]['reserve'] = True
        ticks(cfg, st, 80)
    assert upgraded['businessOperations']['totalOperatingCosts'] > baseline['businessOperations']['totalOperatingCosts']
    assert view(cfg, upgraded)['operations']['operatingCostPerMinute'] > 0


def test_upgraded_running_costs_charge_nothing_while_paused_or_skipped_offline():
    cfg, st = town()
    E.buy_upgrade(cfg, st, 0, 'sales')
    E.buy_upgrade(cfg, st, 0, 'storage')
    act(cfg, st, st['b'][0], 'pause')
    cash = st['cash']
    ticks(cfg, st, 20)
    assert st['cash'] == cash and st['businessOperations']['totalOperatingCosts'] == 0
    assert view(cfg, st)['buildings'][0]['potentialOperatingCostPerMinute'] == 0
    act(cfg, st, st['b'][0], 'resume')
    cfg['runtime']['offlineHours'] = 0
    E.advance_class(cfg, {}, [st], st['tick'], st['tick'] + 100)
    assert st['cash'] == cash and st['businessOperations']['totalOperatingCosts'] == 0


def test_upgrade_cost_fraction_survives_json_chunks_and_technician_discount():
    cfg, continuous = town()
    continuous['b'][0]['sales'] = 2
    continuous['b'][0]['storage'] = 2
    continuous['b'][0]['reserve'] = True
    act(cfg, continuous, continuous['b'][0], 'hire', staffId='technician')
    assert O.effective_batch_cost(cfg, continuous['b'][0], cfg['tiers'][0]['goods'][1]) == .575
    chunked = copy.deepcopy(continuous)
    ticks(cfg, continuous, 32)
    for count in (1, 2, 5, 3, 9, 12):
        ticks(cfg, chunked, count)
        chunked = E.State(json.loads(json.dumps(chunked)))
    assert chunked == continuous
    # Nine paid-basis batches during the discounted 12 ticks, then 15 at full
    # upgraded cost: floor(9 * .575 + 15 * 1.15) = 22 whole YM, with carry.
    assert continuous['businessOperations']['totalOperatingCosts'] == 22
    assert continuous['b'][0]['costRemainder'] == 425 * O.COST_SCALE // 1000
    assert type(continuous['cash']) is int


def test_prior_hundredth_cost_carry_migrates_once_without_changing_its_value():
    cfg, st = town()
    b = st['b'][0]
    b.pop('costRemainderScale')
    b['costRemainder'] = 50
    O.ensure(cfg, st)
    assert b['costRemainder'] == O.COST_SCALE // 2 and b['costRemainderScale'] == O.COST_SCALE
    O.ensure(cfg, st)
    assert b['costRemainder'] == O.COST_SCALE // 2
    quote = O.batch_quote(cfg, b, cfg['tiers'][0]['goods'][1])
    assert quote == (1, O.COST_SCALE // 2)


def test_free_starter_crop_and_legacy_rules_ignore_upgrade_operating_multiplier():
    cfg, st = town()
    st['b'][0].update(sales=12, storage=12)
    st['cash'] = 0
    assert O.effective_batch_cost(cfg, st['b'][0], cfg['tiers'][0]['goods'][0]) == 0
    ticks(cfg, st, 4)
    assert st['cash'] > 0
    cfg.pop('businessDesign')
    assert O.effective_batch_cost(cfg, st['b'][0], cfg['tiers'][0]['goods'][1]) == 0
    before = st['cash']
    st['b'][0]['reserve'] = True
    ticks(cfg, st, 8)
    assert st['cash'] == before


def test_multi_output_recipe_forecast_matches_real_batches_inputs_and_costs():
    cfg, st = town()
    st['b'].append(E._building(1))
    st['tierOf'].append(1)
    O.ensure(cfg, st)
    st['b'][0]['paused'] = True
    st['b'][1]['reserve'] = True
    raw = copy.deepcopy(cfg['tiers'][1]['goods'][0])
    recipe = copy.deepcopy(cfg['tiers'][1]['goods'][2])
    raw.update(quantity=2, cycleTicks=1, operatingCost=1)
    recipe.update(quantity=2, cycleTicks=2, operatingCost=2,
                  inputs=[dict(goodId=raw['id'], quantity=2)])
    cfg['tiers'][1]['goods'] = [raw, recipe]
    rates, regulars = E._flows(cfg, st)
    assert rates[raw['id']]['production'] == 8
    assert rates[recipe['id']]['production'] == 4
    assert regulars['remaining'][raw['id']] == 4, 'Two recipe batches use four raw units per minute.'
    forecast = O.forecast_cost(cfg, st, 1, rates)
    assert forecast == 8, 'Four raw batches cost four; two recipe batches cost four.'
    before = st['cash']
    ticks(cfg, st, 4)
    assert st['inventory'][raw['id']] == 4
    assert st['inventory'][recipe['id']] == 4
    assert st['report']['unitsProduced'] == 12
    assert st['cash'] == before - forecast
    assert st['businessOperations']['totalOperatingCosts'] == forecast
