"""The three-card prototype keeps delivery accounting and saved offers safe."""
from __future__ import annotations

import copy
import json
import math

import pytest

import business_progression as progression
import order_engine as orders
import production_economy as economy


@pytest.fixture
def town():
    cfg = economy.load_config()
    return cfg, economy.new_state(cfg, seed=71)


def own(cfg, state, *tiers):
    state['tierOf'] = list(tiers)
    state['b'] = [economy._building(tier) for tier in tiers]
    state['businessProgression']['grandfathered'] = [cfg['tiers'][tier]['id'] for tier in tiers]


def stock(board, index):
    for need in board['offers'][index]['requirements']:
        board['inventory'][need['goodId']] = need['quantity']


def only_recipe(monkeypatch, *gids):
    monkeypatch.setattr(orders, 'ORDER_RECIPES', (
        dict(id='review_recipe', name='Review delivery', purpose='A buyer needs these goods.', goods=gids),
    ))


def test_board_creation_preserves_source_config_and_saved_third_terms(town):
    cfg, state = town
    state['offers'][2]['committed'] = True
    state['offers'][2]['savedMarker'] = {'nested': [1, 2]}
    before = copy.deepcopy((cfg, state))
    board = orders.create_board(cfg, state)
    assert (cfg, state) == before
    assert board['offers'][2] == state['offers'][2]
    assert 'classId' not in board['offers'][2]
    board['offers'][2]['savedMarker']['nested'].append(3)
    assert state == before[1]
    assert [p['id'] for p in orders.class_profiles()] == ['cooldown', 'sector', 'standard']
    profiles = orders.class_profiles()
    profiles[0]['label'] = 'changed'
    assert orders.class_profiles()[0]['label'] != 'changed'


@pytest.mark.parametrize('connected', [True, False])
def test_missing_offers_use_exact_existing_initial_third_order(town, connected):
    cfg, state = town
    cfg['businessDesign']['connectedProgression'] = connected
    state['offers'] = None
    state['orderSerial'] = 0
    state['orderRecipeHistory'] = [[], [], []]
    expected = copy.deepcopy(state)
    economy.offer_contracts(cfg, expected, state['tick'])
    board = orders.create_board(cfg, state)
    assert board['offers'][2] == expected['offers'][2]
    assert bool(board['offers'][2].get('project')) is not connected


def test_connected_preview_does_not_migrate_a_saved_legacy_project(town):
    cfg, state = town
    legacy = copy.deepcopy(cfg)
    legacy['businessDesign']['connectedProgression'] = False
    state['offers'][2] = economy._make_order(legacy, state, 2)
    state['offers'][2]['committed'] = True
    saved = copy.deepcopy(state['offers'][2])
    assert saved['project']
    assert orders.create_board(cfg, state)['offers'][2] == saved


def test_delivery_lifecycle_reserves_then_pays_on_arrival_and_survives_reload(town):
    cfg, state = town
    state['offers'][0]['reward'] = 300
    board = orders.create_board(cfg, state, cooldown_seconds=61)
    old = copy.deepcopy(board['offers'][0])
    assert old['deliverySeconds'] == 75
    stock(board, 0)
    before = copy.deepcopy(board)
    receipt = orders.apply_action(cfg, board, 0, 'fulfill', old['id'])
    assert receipt == dict(ok=True, kind='order_dispatch', orderId=old['id'], reward=0, materials=0,
                           durationSeconds=75)
    assert all(board[key] == before[key] for key in
               ('cash', 'materials', 'inventory', 'cStats', 'checklist', 'businessProgression'))
    assert board['offers'][0]['inTransit'] and board['offers'][0]['committed']
    assert board['offers'][0]['id'] == old['id']
    assert board['offers'][0]['requirements'] == old['requirements']
    assert board['offers'][0]['deliveryUntilTick'] == before['tick'] + old['deliverySeconds'] // cfg['global']['tick']
    assert board['orderEngine']['lastDelivery'] is None
    assert orders.cooldown_remaining(cfg, board) == 75
    for blocked in ('fulfill', 'replace', 'commit', 'release'):
        before = copy.deepcopy(board)
        assert not orders.apply_action(cfg, board, 0, blocked, old['id'])['ok']
        assert board == before
    board['tick'] += 4
    orders.refresh_board(cfg, board)
    assert orders.cooldown_remaining(cfg, board) == 15 and board['offers'][0]['inTransit']
    saved = json.loads(json.dumps(board))
    reloaded = orders.create_board(cfg, saved)
    assert reloaded == saved
    board['tick'] += 1
    reloaded['tick'] += 1
    before = copy.deepcopy(board)
    assert not orders.apply_action(cfg, board, 0, 'fulfill', old['id'])['ok']
    assert board == before
    orders.refresh_board(cfg, board)
    orders.refresh_board(cfg, reloaded)
    assert board == reloaded
    assert orders.cooldown_remaining(cfg, board) == 0
    assert not board['offers'][0].get('inTransit')
    assert board['offers'][0]['id'] != old['id']
    assert board['cash'] == before['cash'] + old['reward']
    assert board['cStats']['done'] == before['cStats']['done'] + 1
    assert board['orderEngine']['lastDelivery'] == dict(orderId=old['id'], reward=old['reward'],
                                                       materials=old['materials'], rarity=old['rarity'])
    before = copy.deepcopy(board)
    orders.refresh_board(cfg, board)
    assert board == before
    assert not orders.apply_action(cfg, board, 0, 'fulfill', old['id'])['ok']
    assert board == before


def test_idle_replacement_has_no_delivery_timer_or_payment(town):
    cfg, state = town
    board = orders.create_board(cfg, state)
    before = copy.deepcopy(board)
    assert orders.apply_action(cfg, board, 0, 'replace', board['offers'][0]['id'])['ok']
    assert board['offers'][0]['id'] != before['offers'][0]['id']
    assert not board['offers'][0].get('inTransit')
    assert orders.cooldown_remaining(cfg, board) == 0
    assert all(board[key] == before[key] for key in ('cash', 'inventory', 'cStats', 'orderEngine'))


@pytest.mark.parametrize('refresh', [False, True])
def test_old_waiting_card_migrates_without_paying_or_creating_a_receipt(town, refresh):
    cfg, state = town
    board = orders.create_board(cfg, state)
    board['offers'][0] = dict(id='waiting-old-order', requirements=[], reward=0, materials=0,
                               waiting=True, committed=False, cooldownUntilTick=board['tick'] + 4)
    board['orderEngine']['cooldownUntilTick'] = board['tick'] + 4
    board['orderEngine'].pop('lastDelivery')
    before = copy.deepcopy(board)
    board = orders.refresh_board(cfg, board) if refresh else orders.create_board(cfg, board)
    assert board['offers'][0]['requirements'] and not board['offers'][0].get('waiting')
    assert board['offers'][0]['classLabel'] == 'Delivery orders'
    assert board['orderEngine']['lastDelivery'] is None
    assert orders.cooldown_remaining(cfg, board) == 0
    assert all(board[key] == before[key] for key in ('cash', 'inventory', 'cStats', 'businessProgression'))
    assert orders.create_board(cfg, board) == board


@pytest.mark.parametrize('index', [0, 1, 2])
def test_successful_delivery_debits_inventory_and_pays_once(town, index):
    cfg, state = town
    board = orders.create_board(cfg, state)
    offer = copy.deepcopy(board['offers'][index])
    stock(board, index)
    before = copy.deepcopy(board)
    result = orders.apply_action(cfg, board, index, 'fulfill', offer['id'])
    assert result['ok']
    if index == 0:
        board['tick'] = board['offers'][0]['deliveryUntilTick']
        orders.refresh_board(cfg, board)
    assert board['cash'] == before['cash'] + offer['reward']
    assert board['materials'] == before['materials'] + offer['materials']
    assert board['cStats']['done'] == before['cStats']['done'] + 1
    assert all(board['inventory'][need['goodId']] == 0 for need in offer['requirements'])
    settled = copy.deepcopy(board)
    assert not orders.apply_action(cfg, board, index, 'fulfill', offer['id'])['ok']
    assert board == settled


@pytest.mark.parametrize('index', [0, 1, 2])
def test_missing_stock_stale_and_invalid_actions_leave_everything_unchanged(town, index):
    cfg, state = town
    board = orders.create_board(cfg, state)
    for action, oid in [('fulfill', board['offers'][index]['id']),
                        ('replace', 'stale'), ('commit', 'stale'), ('other', None)]:
        before = copy.deepcopy(board)
        assert not orders.apply_action(cfg, board, index, action, oid)['ok']
        assert board == before


@pytest.mark.parametrize('reserved_by', ['regular', 'order'])
def test_dispatch_requires_unreserved_stock(town, reserved_by):
    cfg, state = town
    board = orders.create_board(cfg, state)
    board['offers'][0]['requirements'] = [dict(goodId='farm_tomatoes', quantity=6)]
    board['inventory']['farm_tomatoes'] = 6
    if reserved_by == 'regular':
        assert economy.manage_customer_contract(cfg, board, 0, 'accept', 'corner_grocer')['ok']
    else:
        board['offers'][1].update(requirements=[dict(goodId='farm_tomatoes', quantity=1)], committed=True)
    before = copy.deepcopy(board)
    result = orders.apply_action(cfg, board, 0, 'fulfill', board['offers'][0]['id'])
    assert not result['ok'] and 'unreserved' in result['why']
    assert board == before


def test_dispatch_checks_shelf_room_even_if_inventory_exceeds_capacity(town):
    cfg, state = town
    board = orders.create_board(cfg, state)
    capacity = economy._good_capacity(cfg, board, 0, 'farm_tomatoes')
    board['offers'][0]['requirements'] = [dict(goodId='farm_tomatoes', quantity=capacity)]
    board['offers'][1].update(requirements=[dict(goodId='farm_tomatoes', quantity=1)], committed=True)
    board['inventory']['farm_tomatoes'] = capacity + 1
    before = copy.deepcopy(board)
    result = orders.apply_action(cfg, board, 0, 'fulfill', board['offers'][0]['id'])
    assert not result['ok'] and 'shelf room' in result['why']
    assert board == before


def test_later_orders_cannot_take_or_over_reserve_in_transit_stock(town):
    cfg, state = town
    board = orders.create_board(cfg, state)
    board['offers'][0]['requirements'] = [dict(goodId='farm_tomatoes', quantity=4)]
    board['offers'][1]['requirements'] = [dict(goodId='farm_tomatoes', quantity=1)]
    board['inventory']['farm_tomatoes'] = 4
    assert orders.apply_action(cfg, board, 0, 'fulfill')['ok']
    for action in ('fulfill', 'commit'):
        before = copy.deepcopy(board)
        assert not orders.apply_action(cfg, board, 1, action)['ok']
        assert board == before
    # Enough additional stock lets a second order save its own goods safely.
    board['inventory']['farm_tomatoes'] += 1
    assert orders.apply_action(cfg, board, 1, 'commit')['ok']
    board['tick'] = board['offers'][0]['deliveryUntilTick']
    orders.refresh_board(cfg, board)
    assert not board['offers'][0].get('inTransit')
    assert board['inventory']['farm_tomatoes'] == 1
    assert orders.apply_action(cfg, board, 1, 'fulfill')['ok']
    assert board['inventory']['farm_tomatoes'] == 0


def test_delivery_stock_stays_reserved_while_other_products_run_independently(town):
    cfg, state = town
    own(cfg, state, 0, 2)
    board = orders.create_board(cfg, state)
    board['offers'][0]['requirements'] = [dict(goodId='farm_eggs', quantity=4)]
    board['inventory'].update(farm_eggs=4, farm_honey=1)
    board['cash'] = 100
    assert orders.apply_action(cfg, board, 0, 'fulfill')['ok']
    goods = economy.catalog(cfg)
    board['b'][0]['paused'] = True
    board['productionWork']['roastery_pastries'] = goods['roastery_pastries']['cycleTicks'] * 100
    economy._produce(cfg, board)
    assert board['inventory']['roastery_pastries'] == 1
    assert board['inventory']['farm_eggs'] == 4
    assert board['inventory']['farm_honey'] == 1
    board['b'][0]['paused'] = False
    assert economy.manage_customer_contract(cfg, board, 0, 'accept', 'sunrise_diner')['ok']
    regular = board['customerContracts']['active'][0]
    economy._tick_customer_contracts(cfg, board, regular['nextDeliveryTick'])
    assert regular['deliveries'] == 0
    board['salesWork']['farm_eggs'] = goods['farm_eggs']['cycleTicks'] * 10000
    economy._retail(cfg, board)
    economy.sell_one(cfg, board, 0)
    assert board['inventory']['farm_eggs'] == 4
    board['tick'] = board['offers'][0]['deliveryUntilTick']
    orders.refresh_board(cfg, board)
    assert board['inventory']['farm_eggs'] == 0
    assert board['orderEngine']['lastDelivery'] is not None


@pytest.mark.parametrize('action', ['fulfill', 'replace', 'commit', 'release'])
def test_third_card_actions_match_existing_engine_exactly(town, action):
    cfg, state = town
    board = orders.create_board(cfg, state)
    stock(board, 2)
    direct = copy.deepcopy(board)
    oid = board['offers'][2]['id']
    if action in ('commit', 'release'):
        expected = economy.commit_order(cfg, direct, 2, oid, action == 'commit')
    else:
        handler = economy.fulfill_order if action == 'fulfill' else economy.replace_order
        expected = handler(cfg, direct, 2, oid)
    assert orders.apply_action(cfg, board, 2, action, oid) == expected
    assert board == direct


def test_sector_rotates_automatically_is_single_sector_and_reproducible(town):
    cfg, state = town
    own(cfg, state, *range(15))
    board = orders.create_board(cfg, state)
    replay = json.loads(json.dumps(board))
    goods = economy.catalog(cfg)
    seen = set()
    for _ in range(45):
        offer = board['offers'][1]
        sector = offer['sectorId']
        seen.add(sector)
        assert {cfg['tiers'][goods[n['goodId']]['tier']]['family'] for n in offer['requirements']} == {sector}
        assert offer['sectorLabel'] == cfg['families'][sector]['name']
        for need in offer['requirements']:
            slot = board['tierOf'].index(goods[need['goodId']]['tier'])
            assert 0 < need['quantity'] <= economy._good_capacity(cfg, board, slot, need['goodId'])
        assert orders.apply_action(cfg, board, 1, 'replace', offer['id'])['ok']
        assert orders.apply_action(cfg, replay, 1, 'replace', offer['id'])['ok']
        assert board == replay
        assert board['offers'][1]['sectorId'] != sector
    assert seen == {'F', 'I', 'E'}


def test_starter_sector_remains_possible_without_forcing_another_sector(town):
    cfg, state = town
    board = orders.create_board(cfg, state)
    for _ in range(8):
        assert board['offers'][1]['sectorId'] == 'F'
        assert orders.apply_action(cfg, board, 1, 'replace')['ok']


def test_sector_needs_only_the_owned_unlocked_product_business(town, monkeypatch):
    cfg, state = town
    own(cfg, state, *range(15))
    goods = economy.catalog(cfg)
    candidate = next(g for g in goods.values() if any(
        cfg['tiers'][goods[n['goodId']]['tier']]['family'] != cfg['tiers'][g['tier']]['family']
        for n in g.get('inputs', [])))
    only_recipe(monkeypatch, candidate['id'])
    assert orders.create_board(cfg, state)['offers'][1]['requirements'][0]['goodId'] == candidate['id']
    own(cfg, state, candidate['tier'])
    assert orders.create_board(cfg, state)['offers'][1]['requirements'][0]['goodId'] == candidate['id']
    own(cfg, state, next(i for i in range(15) if i != candidate['tier']))
    with pytest.raises(ValueError, match='No sector orders'):
        orders.create_board(cfg, state)


def test_sector_keeps_quest_locks_and_rejects_duplicate_or_mixed_sector_bundles(town, monkeypatch):
    cfg, state = town
    own(cfg, state, 0, 2)
    only_recipe(monkeypatch, 'farm_eggs', 'roastery_pastries')
    assert len(orders.create_board(cfg, state)['offers'][1]['requirements']) == 2
    only_recipe(monkeypatch, 'farm_eggs', 'farm_eggs')
    with pytest.raises(ValueError, match='No sector orders'):
        orders.create_board(cfg, state)
    own(cfg, state, 0, 3)
    only_recipe(monkeypatch, 'farm_eggs', 'garage_spare_parts')
    with pytest.raises(ValueError, match='No sector orders'):
        orders.create_board(cfg, state)
    own(cfg, state, 3)
    state['businessProgression']['grandfathered'] = []
    only_recipe(monkeypatch, 'garage_custom_mods')
    with pytest.raises(ValueError, match='No sector orders'):
        orders.create_board(cfg, state)
    progression.ensure(cfg, state)['quests']['garage-signature'] = dict(completed=True)
    assert orders.create_board(cfg, state)['offers'][1]['requirements']
    raw = next(g for g in cfg['tiers'][3]['goods'] if g['id'] == 'garage_spare_parts')
    raw['inputs'] = [dict(goodId='farm_tomatoes', quantity=1)]
    assert orders.create_board(cfg, state)['offers'][1]['requirements']


@pytest.mark.parametrize('rarity_id', ['standard', 'large', 'rare', 'jackpot'])
def test_sector_preserves_live_quantity_cash_and_material_terms(town, monkeypatch, rarity_id):
    cfg, state = town
    only_recipe(monkeypatch, 'farm_tomatoes')
    rarity = copy.deepcopy(next(r for r in economy.ORDER_ROLLS if r['id'] == rarity_id))
    rarity['chance'] = 100
    monkeypatch.setattr(economy, 'ORDER_ROLLS', (rarity,))
    board = orders.create_board(cfg, state)
    offer = board['offers'][1]
    good = economy.catalog(cfg)['farm_tomatoes']
    quantity = math.ceil(max(2, math.ceil(cfg['production']['orderMinutes'][1] * 60
                         / (good['cycleTicks'] * cfg['global']['tick']))) * rarity['quantityPercent'] / 100)
    quantity = min(quantity, economy._good_capacity(cfg, board, 0, good['id']))
    value = quantity * good['unitPrice']
    percent = economy.jsround(110 * rarity['payoutPercent'] / 100)
    assert offer['requirements'] == [dict(goodId=good['id'], quantity=quantity)]
    assert offer['rarity'] == rarity_id and offer['rewardPercent'] == percent
    assert offer['reward'] == economy.jsround(value * percent / 100)
    assert offer['materials'] == 0


@pytest.mark.parametrize('reward, seconds', [(0, 30), (1, 30), (75, 30), (300, 60),
                                            (1200, 120), (4800, 240), (19200, 480)])
def test_delivery_time_scales_with_cash_value_without_an_upper_cap(town, reward, seconds):
    cfg, _ = town
    assert orders.quote_delivery_seconds(cfg, dict(reward=reward)) == seconds


def test_quotes_increase_with_payout_including_rarity_and_round_up_to_ticks(town):
    cfg, _ = town
    rewards = sorted(set(range(0, 5001, 7)) | {
        economy.jsround(300 * rarity['payoutPercent'] / 100) for rarity in economy.ORDER_ROLLS})
    seconds = [orders.quote_delivery_seconds(cfg, dict(reward=reward)) for reward in rewards]
    assert seconds == sorted(seconds)
    assert all(value % cfg['global']['tick'] == 0 for value in seconds)
    for reward, value in zip(rewards, seconds):
        unrounded = max(30, 60 * math.sqrt(reward / 300))
        assert unrounded <= value < unrounded + cfg['global']['tick']
    assert orders.quote_delivery_seconds(cfg, dict(reward=750)) > orders.quote_delivery_seconds(cfg, dict(reward=300))


def test_quote_is_pure_and_uses_final_cash_not_quantity_shelf_or_other_rewards(town):
    cfg, state = town
    offer = copy.deepcopy(state['offers'][0])
    offer['reward'] = 300
    before = copy.deepcopy((cfg, offer))
    assert orders.quote_delivery_seconds(cfg, offer) == 60
    assert (cfg, offer) == before
    offer.update(requirements=[dict(goodId='farm_tomatoes', quantity=999999)],
                 retailValue=999999, materials=999999, rarity='jackpot', rewardPercent=999999)
    cfg['tiers'][0]['capacity'] = 1
    assert orders.quote_delivery_seconds(cfg, offer) == 60


@pytest.mark.parametrize('reward', [None, -1, True, '300', float('nan'), float('inf')])
def test_invalid_cash_quotes_are_rejected(town, reward):
    cfg, _ = town
    with pytest.raises(ValueError, match='cash reward'):
        orders.quote_delivery_seconds(cfg, dict(reward=reward))


def test_each_replacement_and_arrival_saves_its_own_cash_based_quote(town):
    cfg, state = town
    board = orders.create_board(cfg, state)
    quoted = set()
    for _ in range(12):
        offer = copy.deepcopy(board['offers'][0])
        quoted.add(offer['deliverySeconds'])
        assert offer['deliverySeconds'] == orders.quote_delivery_seconds(cfg, offer)
        assert 'deliverySeconds' not in board['offers'][1]
        assert 'deliverySeconds' not in board['offers'][2]
        assert orders.apply_action(cfg, board, 0, 'replace', offer['id'])['ok']
    assert len(quoted) > 1
    stock(board, 0)
    old = copy.deepcopy(board['offers'][0])
    receipt = orders.apply_action(cfg, board, 0, 'fulfill', old['id'])
    assert receipt['durationSeconds'] == old['deliverySeconds']
    assert (board['offers'][0]['deliveryUntilTick'] - board['tick']) * cfg['global']['tick'] == old['deliverySeconds']
    board['tick'] = board['offers'][0]['deliveryUntilTick']
    orders.refresh_board(cfg, board)
    assert board['offers'][0]['id'] != old['id']
    assert board['offers'][0]['deliverySeconds'] == orders.quote_delivery_seconds(cfg, board['offers'][0])


@pytest.mark.parametrize('refresh', [False, True])
def test_old_idle_offer_migrates_using_its_saved_base_duration(town, refresh):
    cfg, state = town
    board = orders.create_board(cfg, state, cooldown_seconds=75)
    board['orderEngine'].pop('deliveryBaseSeconds')
    board['offers'][0].pop('deliverySeconds')
    board['offers'][0]['reward'] = 1200
    before = copy.deepcopy(board)
    migrated = orders.refresh_board(cfg, board) if refresh else orders.create_board(cfg, board, cooldown_seconds=600)
    assert migrated['orderEngine']['deliveryBaseSeconds'] == 75
    assert migrated['offers'][0]['deliverySeconds'] == 150
    assert migrated['offers'][0]['id'] == before['offers'][0]['id']
    assert migrated['offers'][0]['requirements'] == before['offers'][0]['requirements']
    assert migrated['cash'] == before['cash']
    assert orders.create_board(cfg, migrated) == migrated
    snapshot = copy.deepcopy(migrated)
    assert orders.refresh_board(cfg, migrated) == snapshot


@pytest.mark.parametrize('refresh', [False, True])
def test_old_in_transit_offer_keeps_its_original_duration_and_deadline(town, refresh):
    cfg, state = town
    board = orders.create_board(cfg, state, cooldown_seconds=75)
    board['orderEngine'].pop('deliveryBaseSeconds')
    board['offers'][0].pop('deliverySeconds')
    board['offers'][0].update(reward=4800, inTransit=True, committed=True,
                               deliveryUntilTick=board['tick'] + 3)
    stock(board, 0)
    original_tick = board['tick']
    before = copy.deepcopy(board)
    migrated = orders.refresh_board(cfg, board) if refresh else orders.create_board(cfg, board, cooldown_seconds=600)
    assert migrated['offers'][0]['deliverySeconds'] == 75
    assert migrated['offers'][0]['deliveryUntilTick'] == original_tick + 3
    assert orders.cooldown_remaining(cfg, migrated) == 45
    assert migrated['cash'] == before['cash']
    assert orders.create_board(cfg, migrated) == migrated
    migrated['tick'] += 3
    orders.refresh_board(cfg, migrated)
    assert migrated['cash'] == before['cash'] + 4800
    assert migrated['offers'][0]['deliverySeconds'] == orders.quote_delivery_seconds(cfg, migrated['offers'][0], 75)


def test_saved_quote_is_not_repriced_when_offer_or_base_configuration_changes(town):
    cfg, state = town
    state['offers'][0]['reward'] = 300
    board = orders.create_board(cfg, state)
    assert board['offers'][0]['deliverySeconds'] == 60
    board['offers'][0]['reward'] = 4800
    board['orderEngine']['deliveryBaseSeconds'] = 600
    assert orders.create_board(cfg, board, cooldown_seconds=900) == board
    stock(board, 0)
    receipt = orders.apply_action(cfg, board, 0, 'fulfill')
    assert receipt['durationSeconds'] == 60
    deadline = board['offers'][0]['deliveryUntilTick']
    board['orderEngine']['deliveryBaseSeconds'] = 1200
    snapshot = copy.deepcopy(board)
    orders.refresh_board(cfg, board)
    assert board == snapshot and board['offers'][0]['deliveryUntilTick'] == deadline


@pytest.mark.parametrize('duration', [0, -1, True, '60', float('nan'), float('inf')])
def test_invalid_cooldown_never_changes_inputs(town, duration):
    cfg, state = town
    before = copy.deepcopy((cfg, state))
    with pytest.raises(ValueError, match='positive'):
        orders.create_board(cfg, state, cooldown_seconds=duration)
    with pytest.raises(ValueError, match='positive'):
        orders.quote_delivery_seconds(cfg, dict(reward=300), duration)
    assert (cfg, state) == before
