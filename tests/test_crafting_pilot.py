"""The optional crafting trial spends once and turns real inputs into real sales."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

import business_operations as operations
import crafting as crafting
import crafting_pilot as pilot
import inventory_costs
import production_economy as economy


PILOT_ITEMS = {
    'farm_breakfast_basket', 'seafood_picnic_box', 'smoked_fish_gift_box',
    'coffee_gift_set', 'honey_glazed_pastries', 'wooden_crate', 'seedling_tray',
    'toolbox', 'wheeled_cart', 'battery_pack', 'folding_electric_scooter',
    'electric_cargo_tricycle', 'tomato_chutney', 'honey_spread_jars', 'pantry_hamper',
}


def town():
    cfg = pilot.configure(economy.load_config())
    state = economy.new_state(cfg, seed=59)
    state['cash'] = 10_000_000
    state['tierOf'] = list(range(len(cfg['tiers'])))
    state['b'] = [economy._building(tier) for tier in state['tierOf']]
    state['businessProgression']['grandfathered'] = [tier['id'] for tier in cfg['tiers']]
    operations.ensure(cfg, state)
    pilot.ensure(cfg, state)
    return cfg, state


def request(state, **fields):
    revision = state['crafting']['revision']
    return dict(requestId='pilot-test-{}'.format(revision), revision=revision, **fields)


def action(cfg, state, **fields):
    result = pilot.act(cfg, state, request(state, **fields))
    assert result['ok'], result
    return result


def worth(cfg, state):
    economy._sync_pools(cfg, state)
    return economy.net_worth(cfg, state)


def test_default_rules_leave_trial_off_and_legacy_state_untouched():
    cfg = economy.load_config()
    state = economy.new_state(cfg, seed=59)
    assert not pilot.enabled(cfg)
    before = copy.deepcopy(state)
    pilot.ensure(cfg, state)
    pilot.tick(cfg, state, state['tick'] + 1)
    payload = crafting.payload(cfg, state)
    original_payload = copy.deepcopy(payload)
    pilot.enrich(cfg, state, payload)
    assert payload == original_payload
    assert not pilot.act(cfg, state, request(state, action='buy_asset', assetId='asset_fish_stall_1'))['ok']
    assert state == before


def test_trial_configuration_survives_a_class_snapshot_without_changing_default_rules():
    cfg = economy.load_config()
    original = copy.deepcopy(cfg)
    configured = pilot.configure(cfg)
    assert configured is cfg and pilot.enabled(cfg)
    assert pilot.enabled(json.loads(json.dumps(cfg)))
    assert not pilot.enabled(original)
    assert economy.load_config() == original
    assert cfg['tiers'] == original['tiers'], 'Ordinary business goods keep their existing rules.'


def test_old_items_supplies_and_request_receipt_survive_trial_migration():
    cfg, state = town()
    state['crafting'].update(
        items={'fish_trap': dict(quantity=2, value=48), 'battery_pack': dict(quantity=1, value=90)},
        supplies={'wooden_boards': dict(quantity=7, value=42)},
        revision=7,
        lastRequest=dict(requestId='old-crafting-receipt', revision=6,
                         intent=['buy_supply', 'wooden_boards', 7],
                         receipt=dict(ok=True, kind='craft_supply', cost=42, revision=7)),
    )
    old_crafting = copy.deepcopy(state['crafting'])
    old_worth = worth(cfg, state)
    migrated = economy.migrate_state(cfg, json.loads(json.dumps(state)))
    pilot.ensure(cfg, migrated)
    for key in ('supplies', 'revision', 'lastRequest'):
        assert migrated['crafting'][key] == old_crafting[key]
    for item_id, row in old_crafting['items'].items():
        assert {key: migrated['crafting']['items'][item_id][key] for key in row} == row
    assert migrated['crafting']['items']['battery_pack']['costMicros'] == 90 * pilot.SCALE
    assert worth(cfg, migrated) == old_worth
    once = copy.deepcopy(migrated)
    pilot.ensure(cfg, migrated)
    assert migrated == once


def test_buying_an_asset_transfers_cash_into_book_value_without_minting_wealth():
    cfg, state = town()
    before_worth, before_cash = worth(cfg, state), state['cash']
    before_craft = copy.deepcopy((state['crafting']['items'], state['crafting']['supplies']))
    action(cfg, state, action='buy_asset', assetId='asset_fish_stall_1')
    paid = before_cash - state['cash']
    assert paid > 0
    assert pilot.stored_value(state) == paid
    assert worth(cfg, state) == before_worth
    assert (state['crafting']['items'], state['crafting']['supplies']) == before_craft


def test_asset_request_retries_and_conflicting_replays_never_purchase_twice():
    cfg, state = town()
    body = request(state, action='buy_asset', assetId='asset_fish_stall_1')
    result = pilot.act(cfg, state, body)
    assert result['ok'], result
    once = copy.deepcopy(state)
    duplicate = pilot.act(cfg, state, body)
    assert duplicate['ok'] and duplicate['duplicate']
    assert state == once
    conflicting = dict(body, assetId='asset_workshop_1')
    assert not pilot.act(cfg, state, conflicting)['ok']
    assert state == once


def test_supply_purchase_makes_an_older_asset_request_stale():
    cfg, state = town()
    body = request(state, action='buy_asset', assetId='asset_fish_stall_1')
    assert pilot.act(cfg, state, body)['ok']
    supply = request(state, action='buy_supply', supplyId='wooden_boards', quantity=1)
    assert crafting.act(cfg, state, supply)['ok']
    once = copy.deepcopy(state)
    assert not pilot.act(cfg, state, body)['ok']
    assert state == once


@pytest.mark.parametrize('fields', [
    dict(action=[]),
    dict(action='buy_asset', assetId='does-not-exist'),
    dict(action='buy_asset', assetId=[]),
    dict(action='buy_asset', assetId='asset_fish_stall_1', revision=True),
    dict(action='buy_asset', assetId='asset_fish_stall_1', revision=-1),
    dict(action='buy_asset', assetId='asset_fish_stall_1', requestId=''),
    dict(action='buy_asset', assetId='asset_fish_stall_1', revision=999_999),
    dict(action='unlock', itemId='does-not-exist'),
    dict(action='unlock', itemId=[]),
    dict(action='assign_asset', assetId='asset_fish_stall_1', buildingId='removed-instance', assetSlot=0),
    dict(action='unassign_asset', buildingId='removed-instance', assetSlot=0),
    dict(action='sell', itemId='battery_pack'),
])
def test_bad_trial_requests_cannot_partially_change_state(fields):
    cfg, state = town()
    body = request(state)
    body.update(fields)
    before = copy.deepcopy(state)
    assert not pilot.act(cfg, state, body)['ok']
    assert state == before


def test_asset_purchase_with_no_cash_has_no_partial_debit_or_ownership():
    cfg, state = town()
    state['cash'] = 0
    before = copy.deepcopy(state)
    assert not pilot.act(cfg, state, request(state, action='buy_asset', assetId='asset_fish_stall_1'))['ok']
    assert state == before


def building_identity(cfg, state, business_id):
    return next(building['buildingId'] for building in state['b']
                if cfg['tiers'][building['tier']]['id'] == business_id)


def product(cfg, item_id):
    return next(item for item in cfg['craftingPilot']['items'] if item['id'] == item_id)


def ready(cfg, state, *item_ids):
    """Grant completed milestones, then use real unlock and acquisition actions."""
    wanted_assets = set()
    for item_id in item_ids:
        item = product(cfg, item_id)
        business = item['businessId']
        unlock = item['unlock']
        state['craftingPilot']['ordersByBusiness'][business] = max(
            state['craftingPilot']['ordersByBusiness'].get(business, 0), unlock.get('manualOrders', 0))
        for quest_id in unlock.get('questIds', []):
            state['businessProgression']['quests'][quest_id] = dict(completed=True)
        team = state['workforce']['teams'].setdefault(business, {})
        team.setdefault('nodes', [])
        for node in unlock.get('focusNodes', []):
            if node not in team['nodes']:
                team['nodes'].append(node)
        action(cfg, state, action='unlock', itemId=item_id)
        wanted_assets.update(item.get('requiredAssetIds', []))
    for asset_id in sorted(wanted_assets):
        action(cfg, state, action='buy_asset', assetId=asset_id)
        business, slot = asset_id[len('asset_'):].rsplit('_', 1)
        action(cfg, state, action='assign_asset', assetId=asset_id,
               buildingId=building_identity(cfg, state, business), assetSlot=int(slot) - 1)


def stock(cfg, state, item_id, batches=1):
    """Cost input stock conservatively at its ordinary sale or purchase value."""
    goods = economy.catalog(cfg)
    for ingredient in product(cfg, item_id)['ingredients']:
        gid, quantity = ingredient['id'], ingredient['quantity'] * batches
        if gid in crafting.SUPPLIES:
            pool = state['crafting']['supplies'].setdefault(gid, dict(quantity=0, value=0))
            pool['quantity'] += quantity
            pool['value'] += quantity * crafting.SUPPLIES[gid]['unitPrice']
        elif gid in goods:
            inventory_costs.produce(cfg, state, gid, quantity, goods[gid]['unitPrice'] * quantity)
            state['inventory'][gid] = state['inventory'].get(gid, 0) + quantity
        else:
            pool = state['crafting']['items'].setdefault(gid, dict(quantity=0, value=0))
            pool['quantity'] += quantity
            pool['value'] += quantity * product(cfg, gid)['sellPrice']
    economy._sync_pools(cfg, state)


def run_ticks(cfg, state, count):
    for _ in range(count):
        tick = state['tick'] + 1
        pilot.tick(cfg, state, tick)
        state['tick'] = tick


def quantity(state, item_id):
    return state['crafting']['items'].get(item_id, {}).get('quantity', 0)


def resources(state):
    return copy.deepcopy((state['cash'], state['inventory'], state['crafting']['items'],
                          state['crafting']['supplies']))


def test_assignment_and_unassignment_transfer_no_cash_or_book_value():
    cfg, state = town()
    action(cfg, state, action='buy_asset', assetId='asset_fish_stall_1')
    identity = building_identity(cfg, state, 'fish_stall')
    before_cash, before_worth = state['cash'], worth(cfg, state)
    before_asset_value = pilot.stored_value(state)
    action(cfg, state, action='assign_asset', assetId='asset_fish_stall_1',
           buildingId=identity, assetSlot=0)
    assert state['cash'] == before_cash and worth(cfg, state) == before_worth
    assert pilot.stored_value(state) == before_asset_value
    action(cfg, state, action='unassign_asset', assetId='asset_fish_stall_1',
           buildingId=identity, assetSlot=0)
    assert state['cash'] == before_cash and worth(cfg, state) == before_worth
    assert pilot.stored_value(state) == before_asset_value


@pytest.mark.parametrize('business_id, asset_slot', [
    ('roastery', 0), ('fish_stall', 2), ('fish_stall', -1), ('fish_stall', 3),
    ('fish_stall', True), ('fish_stall', '0'),
])
def test_owned_asset_cannot_be_assigned_to_the_wrong_business_or_slot(business_id, asset_slot):
    cfg, state = town()
    action(cfg, state, action='buy_asset', assetId='asset_fish_stall_1')
    before = copy.deepcopy(state)
    body = request(state, action='assign_asset', assetId='asset_fish_stall_1',
                   buildingId=building_identity(cfg, state, business_id), assetSlot=asset_slot)
    assert not pilot.act(cfg, state, body)['ok']
    assert state == before


def test_an_unowned_asset_cannot_be_installed_in_a_real_business():
    cfg, state = town()
    before = copy.deepcopy(state)
    body = request(state, action='assign_asset', assetId='asset_fish_stall_1',
                   buildingId=building_identity(cfg, state, 'fish_stall'), assetSlot=0)
    assert not pilot.act(cfg, state, body)['ok']
    assert state == before


def test_multiple_unlocked_products_run_together_without_product_selection():
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket', 'coffee_gift_set')
    for building in state['b']:
        building['reserve'] = True
    stock(cfg, state, 'farm_breakfast_basket', 3)
    stock(cfg, state, 'coffee_gift_set', 3)
    before = worth(cfg, state)
    run_ticks(cfg, state, 30)
    assert quantity(state, 'farm_breakfast_basket') == 3
    assert quantity(state, 'coffee_gift_set') == 3
    assert worth(cfg, state) == before, 'Making stock transfers value; selling it realizes the markup.'


@pytest.mark.parametrize('shortage', ['cash', 'supply', 'base_good'])
def test_blocked_batch_has_no_partial_resource_debits(shortage):
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket')
    stock(cfg, state, 'farm_breakfast_basket')
    if shortage == 'cash':
        state['cash'] = 0
    elif shortage == 'supply':
        state['crafting']['supplies']['packaging'].update(quantity=0, value=0)
    else:
        state['inventory']['farm_eggs'] = 1
    before = resources(state)
    run_ticks(cfg, state, 30)
    assert resources(state) == before
    assert quantity(state, 'farm_breakfast_basket') == 0


def test_committed_base_order_stock_is_protected_from_automatic_crafting():
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket')
    stock(cfg, state, 'farm_breakfast_basket')
    state['offers'][0] = dict(id='promised-farm-eggs', committed=True,
                              requirements=[dict(goodId='farm_eggs', quantity=1)])
    before = resources(state)
    run_ticks(cfg, state, 30)
    assert resources(state) == before
    assert quantity(state, 'farm_breakfast_basket') == 0


def test_input_shortages_cannot_bank_many_completed_batches():
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket')
    state['b'][0]['reserve'] = True
    run_ticks(cfg, state, 100)
    stock(cfg, state, 'farm_breakfast_basket', 50)
    run_ticks(cfg, state, 1)
    assert quantity(state, 'farm_breakfast_basket') <= 1


def test_empty_shelves_cannot_bank_unlimited_customer_demand():
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket')
    run_ticks(cfg, state, 100)
    state['crafting']['items']['farm_breakfast_basket'] = dict(quantity=50, value=1350)
    before_cash = state['cash']
    run_ticks(cfg, state, 1)
    assert quantity(state, 'farm_breakfast_basket') >= 49
    assert state['cash'] - before_cash <= product(cfg, 'farm_breakfast_basket')['sellPrice']


def test_ready_products_share_a_limited_common_input_fairly():
    cfg, state = town()
    candidates = ('wooden_crate', 'seedling_tray')
    for item_id in candidates:
        product(cfg, item_id).update(ingredients=[dict(id='packaging', quantity=1)],
                                     batchSeconds=cfg['global']['tick'], batchCost=1,
                                     requiredAssetIds=[], storageCap=100)
    ready(cfg, state, *candidates)
    for building in state['b']:
        building['reserve'] = True
    for _ in range(20):
        stock(cfg, state, candidates[0])
        run_ticks(cfg, state, 1)
    left, right = (quantity(state, item_id) for item_id in candidates)
    assert left > 0 and right > 0
    assert abs(left - right) <= 1, 'The scheduling cursor rotates among ready competitors.'


def test_replaying_the_same_tick_cannot_produce_sell_or_age_assets_twice():
    cfg, state = town()
    ready(cfg, state, 'seafood_picnic_box')
    stock(cfg, state, 'seafood_picnic_box', 5)
    run_ticks(cfg, state, 20)
    before = copy.deepcopy(state)
    pilot.tick(cfg, state, state['tick'])
    assert state == before


def test_paused_business_cannot_make_or_sell_premium_products():
    cfg, state = town()
    ready(cfg, state, 'farm_breakfast_basket')
    stock(cfg, state, 'farm_breakfast_basket', 5)
    state['crafting']['items']['farm_breakfast_basket'] = dict(quantity=3, value=81, costMicros=81 * pilot.SCALE)
    state['b'][0]['paused'] = True
    before = resources(state)
    run_ticks(cfg, state, 30)
    assert resources(state) == before


@pytest.mark.parametrize('item_id', sorted(PILOT_ITEMS))
def test_each_trial_recipe_makes_real_sales_with_positive_costed_margin(item_id):
    cfg, state = town()
    ready(cfg, state, item_id)
    stock(cfg, state, item_id)
    before_cash = state['cash']
    before_worth = worth(cfg, state)
    item = product(cfg, item_id)
    deadline = (item['batchSeconds'] + item['saleSeconds']) // cfg['global']['tick'] + 3
    for _ in range(deadline):
        run_ticks(cfg, state, 1)
        if state['craftingPilot']['totals']['sold']:
            break
    totals = state['craftingPilot']['totals']
    assert totals['made'] == 1 and totals['sold'] == 1
    assert quantity(state, item_id) == 0
    costs = totals['costsMicros'] / pilot.SCALE
    assert 0 < costs < totals['sales']
    assert (totals['sales'] - costs) / totals['sales'] >= .20
    assert state['cash'] > before_cash, 'Actual buyers must pay into the wallet.'
    statement = pilot.summary(cfg, state)
    assert statement['sales'] == totals['sales']
    assert statement['costs'] == costs
    depreciation = totals['depreciation'] + totals['amortization']
    assert worth(cfg, state) - before_worth == pytest.approx(totals['sales'] - costs - depreciation)


def test_scooter_reserves_two_packs_then_consumes_them_without_loose_cell_double_charge():
    cfg, state = town()
    ready(cfg, state, 'battery_pack', 'folding_electric_scooter')
    scooter = product(cfg, 'folding_electric_scooter')
    assert {'id': 'battery_pack', 'quantity': 2} in scooter['ingredients']
    assert 'battery_cells' not in {need['id'] for need in scooter['ingredients']}
    stock(cfg, state, 'folding_electric_scooter')
    before_value = state['crafting']['items']['battery_pack']['value']
    # Slow the downstream recipe so ordinary battery demand has time to arrive.
    run_ticks(cfg, state, product(cfg, 'battery_pack')['saleSeconds'] // cfg['global']['tick'] + 1)
    assert quantity(state, 'battery_pack') == 2
    assert state['crafting']['items']['battery_pack']['value'] == before_value
    assert state['craftingPilot']['totals']['sold'] == 0
    run_ticks(cfg, state, scooter['batchSeconds'] // cfg['global']['tick'])
    assert quantity(state, 'battery_pack') == 0
    assert state['crafting']['items']['battery_pack']['value'] == 0
    assert state['crafting']['items']['battery_pack']['costMicros'] == 0
    assert state['craftingPilot']['totals']['made'] == 1
    assert state['craftingPilot']['totals']['sold'] == 1


def test_required_asset_expiry_blocks_new_batches_and_never_goes_negative():
    cfg, state = town()
    spec = next(a for a in cfg['craftingPilot']['assets'] if a['id'] == 'asset_fish_stall_1')
    spec['lifeSeconds'] = 2 * cfg['global']['tick']
    ready(cfg, state, 'seafood_picnic_box')
    stock(cfg, state, 'seafood_picnic_box', 5)
    before = resources(state)
    run_ticks(cfg, state, 40)
    asset = state['craftingPilot']['assets']['asset_fish_stall_1']
    assert asset['remainingSeconds'] == 0 and asset['bookValue'] == 0
    assert quantity(state, 'seafood_picnic_box') == 0
    assert resources(state) == before
    snapshot = copy.deepcopy(state)
    body = request(state, action='assign_asset', assetId='asset_fish_stall_1',
                   buildingId=building_identity(cfg, state, 'fish_stall'), assetSlot=0)
    assert not pilot.act(cfg, state, body)['ok']
    assert state == snapshot


def test_assets_do_not_age_across_ticks_the_offline_allowance_skips():
    cfg, state = town()
    spec = next(a for a in cfg['craftingPilot']['assets'] if a['id'] == 'asset_fish_stall_1')
    spec['lifeSeconds'] = 300
    cfg['runtime']['offlineHours'] = 1 / 60
    action(cfg, state, action='buy_asset', assetId=spec['id'])
    action(cfg, state, action='assign_asset', assetId=spec['id'],
           buildingId=building_identity(cfg, state, 'fish_stall'), assetSlot=0)
    cls = {}
    economy.advance_class(cfg, cls, [state], 0, 10_000)
    assert state['report']['offlineTicksSkipped'] > 0
    asset = state['craftingPilot']['assets'][spec['id']]
    assert asset['remainingSeconds'] == 240
    economy.on_login(cfg, state)
    economy.advance_class(cfg, cls, [state], 10_000, 10_001)
    assert asset['remainingSeconds'] == 225


def test_salvaged_building_identity_does_not_automatically_reassign_its_asset():
    cfg, state = town()
    ready(cfg, state, 'seafood_picnic_box')
    stock(cfg, state, 'seafood_picnic_box', 3)
    fish_tier = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == 'fish_stall')
    position = next(i for i, building in enumerate(state['b']) if building['tier'] == fish_tier)
    old_identity = state['b'][position]['buildingId']
    # Simulate the identity change at salvage/rebuild; all actual asset behavior is public.
    state['b'][position] = economy._building(fish_tier)
    operations.ensure(cfg, state)
    assert state['b'][position]['buildingId'] != old_identity
    run_ticks(cfg, state, 40)
    assert quantity(state, 'seafood_picnic_box') == 0
    asset = state['craftingPilot']['assets']['asset_fish_stall_1']
    assert asset['buildingId'] is None
    assert asset['assignmentSlot'] is None
    assert asset['remainingSeconds'] == asset['lifeSeconds']


def test_shop_and_town_statements_include_actual_craft_sales_costs_and_wear_once():
    cfg, state = town()
    # A short fixture lifespan makes depreciation visible within this minute.
    next(a for a in cfg['craftingPilot']['assets'] if a['id'] == 'asset_fish_stall_1')['lifeSeconds'] = 600
    wanted = ('farm_breakfast_basket', 'coffee_gift_set', 'seafood_picnic_box')
    ready(cfg, state, *wanted)
    for item_id in wanted:
        stock(cfg, state, item_id)
    run_ticks(cfg, state, 10)
    craft = pilot.summary(cfg, state)
    assert craft['sales'] > 0 and craft['depreciation'] > 0
    expected_costs = craft['costs'] + craft['depreciation'] + craft['amortization']
    first = economy.payload(cfg, state, {}, {'paused': False})
    second = economy.payload(cfg, state, {}, {'paused': False})
    for data in (first, second):
        statement = data['operatingStatement']
        assert statement['sales'] == craft['sales']
        assert statement['costs'] == pytest.approx(expected_costs)
        assert statement['profit'] == pytest.approx(craft['sales'] - expected_costs)
        assert sum(building['operatingStatement']['sales'] for building in data['buildings']) == statement['sales']
        assert sum(building['operatingStatement']['costs'] for building in data['buildings']) == pytest.approx(statement['costs'])
    assert first['netWorth'] == second['netWorth']


@pytest.mark.parametrize('fresh', [False, True])
def test_preview_solo_snapshot_really_enables_the_trial_before_serving(monkeypatch, fresh):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'previews'))
    import crafting_pilot_preview as preview
    api = preview.api
    for name in ('DB_PATH', 'AUTO_LOGIN', 'SOLO_NAME', '_startup_config'):
        monkeypatch.setattr(api, name, getattr(api, name))
    for name in ('_book_cache', '_settled'):
        monkeypatch.setattr(api, name, {})
    monkeypatch.setattr(sys, 'argv', ['crafting_pilot_preview.py', '3011'] + (['--fresh'] if fresh else []))
    seen = []

    def inspect_before_serving(port, handler, first_page):
        # The preview's AUTO_LOGIN process permits this tokenless local call.
        data = api.econ_state({})
        products = [row for row in data['crafting']['items'] if row.get('pilot')]
        assert len(products) == 15
        assert sum(row['unlocked'] for row in products) == (0 if fresh else 3)
        assert sum(row['canUnlock'] for row in products) == (0 if fresh else 12)
        assert first_page == 'craft.html'
        seen.append(True)

    monkeypatch.setattr(preview, 'serve', inspect_before_serving)
    preview.main()
    assert seen == [True]


@pytest.mark.parametrize('item_id', sorted(PILOT_ITEMS))
def test_enabled_trial_products_reject_the_old_manual_batch_action(item_id):
    cfg, state = town()
    before = copy.deepcopy(state)
    result = crafting.act(cfg, state, request(state, action='craft', itemId=item_id))
    assert not result['ok'] and 'auto' in result['why'].lower()
    assert state == before
