"""Small and bulk offers must stay useful, payable, and safe across reloads."""
from __future__ import annotations

import copy
import json

import pytest

import business_progression as progression
import order_engine as orders
import production_economy as economy


def force_variant(monkeypatch, name):
    selected = copy.deepcopy(next(row for row in economy.ORDER_ROLLS if row['id'] == name))
    selected['chance'] = 100
    monkeypatch.setattr(economy, 'ORDER_ROLLS', (selected,))


def make_town(cfg, tiers=(0,)):
    state = economy.new_state(cfg, seed=71)
    state['tierOf'] = list(tiers)
    state['b'] = [economy._building(tier) for tier in tiers]
    # Keep quest locks: owning a business alone must not unlock its signature.
    state['offers'] = None
    state['orderRecipeHistory'] = [[], [], []]
    economy.offer_contracts(cfg, state, state['tick'])
    return state


def tomato_jobs(monkeypatch):
    recipe = dict(id='variant_tomatoes', name='Tomato delivery',
                  purpose='The kitchen needs fresh tomatoes.',
                  goods=('farm_tomatoes',), breakfast=True)
    monkeypatch.setattr(economy, 'ORDER_RECIPES', (recipe,))
    monkeypatch.setattr(orders, 'ORDER_RECIPES', (recipe,))


def offer_state(cfg, state, route):
    if route == 'sector':
        return orders.create_board(cfg, state), 1
    return state, route


@pytest.mark.parametrize('variant,quantity,cash,percent,materials', [
    ('small', 4, (10, 9, 9), (125, 110, 115), 1),
    ('bulk', 24, (54, 48, 50), (113, 99, 104), 6),
])
@pytest.mark.parametrize('route', [0, 1, 2, 'sector'])
def test_single_product_terms_and_actual_payment(monkeypatch, variant, quantity,
                                                cash, percent, materials, route):
    force_variant(monkeypatch, variant)
    tomato_jobs(monkeypatch)
    cfg = economy.load_config()
    # At four tomatoes per minute, a two-minute job starts with eight units.
    # Small asks for four; bulk asks for twenty-four at a lower unit price.
    cfg['production']['orderMinutes'] = [2, 2, 2]
    cfg['production']['materialCashValue'] = 2
    state, index = offer_state(cfg, make_town(cfg), route)
    offer = copy.deepcopy(state['offers'][index])
    assert offer['rarity'] == variant
    assert offer['requirements'] == [dict(goodId='farm_tomatoes', quantity=quantity)]
    assert offer['rewardPercent'] == percent[index]
    assert offer['reward'] == cash[index]
    assert offer['materials'] == (materials if index == 1 else 0)
    if route == 'sector':
        assert offer['sectorId'] == 'F'
    state['inventory']['farm_tomatoes'] = quantity
    before = (state['cash'], state['materials'], state['cStats']['done'])
    result = (orders.apply_action(cfg, state, index, 'fulfill', offer['id'])
              if route == 'sector' else economy.fulfill_order(cfg, state, index, offer['id']))
    assert result['ok']
    assert state['inventory']['farm_tomatoes'] == 0
    assert state['cash'] == before[0] + cash[index]
    assert state['materials'] == before[1] + offer['materials']
    assert state['cStats']['done'] == before[2] + 1


@pytest.mark.parametrize('variant,minutes,expected', [
    ('small', 2, 4), ('bulk', 2, 5), ('small', .01, 1),
])
@pytest.mark.parametrize('route', [0, 'sector'])
def test_shelf_cap_and_smallest_order_stay_deliverable(monkeypatch, variant,
                                                     minutes, expected, route):
    force_variant(monkeypatch, variant)
    tomato_jobs(monkeypatch)
    cfg = economy.load_config()
    cfg['tiers'][0]['capacity'] = 15  # Five shelf spaces per farm product.
    cfg['production']['orderMinutes'] = [minutes] * 3
    state, index = offer_state(cfg, make_town(cfg), route)
    offer = state['offers'][index]
    assert offer['requirements'] == [dict(goodId='farm_tomatoes', quantity=expected)]
    assert economy.commit_order(cfg, state, index, offer['id'], True)['ok']
    state['inventory']['farm_tomatoes'] = expected
    assert economy._settle_order(cfg, state, offer)['ok']


@pytest.mark.parametrize('variant', ['small', 'bulk'])
@pytest.mark.parametrize('tiers', [(0,), (3,), (0, 5, 10, 12, 14)])
@pytest.mark.parametrize('preview', [False, True])
def test_fresh_and_sparse_towns_get_one_producible_product(monkeypatch, variant,
                                                         tiers, preview):
    force_variant(monkeypatch, variant)
    cfg = economy.load_config()
    state = make_town(cfg, tiers)
    if preview:
        state = orders.create_board(cfg, state)
    goods = economy.catalog(cfg)
    seen = set()

    def check_product(gid):
        assert goods[gid]['tier'] in tiers
        assert progression.product_unlocked(cfg, state, gid)

    for turn in range(24):
        index = 1 if preview else turn % 3
        offer = state['offers'][index]
        assert offer['rarity'] == variant
        assert len(offer['requirements']) == 1
        need = offer['requirements'][0]
        gid = need['goodId']
        seen.add(gid)
        check_product(gid)
        slot = state['tierOf'].index(goods[gid]['tier'])
        assert 1 <= need['quantity'] <= economy._good_capacity(cfg, state, slot, gid)
        if preview:
            assert cfg['tiers'][goods[gid]['tier']]['family'] == offer['sectorId']
            result = orders.apply_action(cfg, state, index, 'replace', offer['id'])
        else:
            result = economy.replace_order(cfg, state, index, offer['id'])
        assert result['ok']
    assert len(seen) >= 2


@pytest.mark.parametrize('variant', ['small', 'bulk'])
@pytest.mark.parametrize('preview', [False, True])
def test_variant_rerolls_replay_without_spending_stock_or_cash(monkeypatch, variant, preview):
    force_variant(monkeypatch, variant)
    cfg = economy.load_config()
    original = make_town(cfg, (0, 3, 5))
    if preview:
        original = orders.create_board(cfg, original)
    original['inventory']['farm_tomatoes'] = 5
    replay = json.loads(json.dumps(original))
    before = (original['cash'], original['materials'], copy.deepcopy(original['inventory']),
              original['tick'], copy.deepcopy(original['cStats']))
    for turn in range(18):
        index = turn % 3
        replay = (orders.create_board(cfg, json.loads(json.dumps(replay))) if preview else
                  economy.migrate_state(cfg, economy.State(json.loads(json.dumps(replay)))))
        for state in (original, replay):
            result = (orders.apply_action(cfg, state, index, 'replace', state['offers'][index]['id'])
                      if preview else economy.replace_order(cfg, state, index, state['offers'][index]['id']))
            assert result['ok']
            assert state['offers'][index]['rarity'] == variant
        assert original['offers'] == replay['offers']
        assert original['orderRecipeHistory'] == replay['orderRecipeHistory']
    assert (original['cash'], original['materials'], original['inventory'],
            original['tick'], original['cStats']) == before


@pytest.mark.parametrize('variant', ['small', 'bulk'])
def test_new_rolls_preserve_existing_saved_offers(monkeypatch, variant):
    cfg = economy.load_config()
    with monkeypatch.context() as old_rules:
        force_variant(old_rules, 'large')
        state = make_town(cfg)
    state['offers'][0]['committed'] = True
    saved = copy.deepcopy(state['offers'])
    force_variant(monkeypatch, variant)
    migrated = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(state))))
    economy.offer_contracts(cfg, migrated, migrated['tick'])
    assert migrated['offers'] == saved
    assert economy.replace_order(cfg, migrated, 1, saved[1]['id'])['ok']
    assert migrated['offers'][1]['rarity'] == variant
    assert migrated['offers'][0] == saved[0] and migrated['offers'][2] == saved[2]


@pytest.mark.parametrize('variant', ['small', 'bulk'])
def test_new_rolls_preserve_dispatched_goods_price_and_arrival(monkeypatch, variant):
    cfg = economy.load_config()
    with monkeypatch.context() as old_rules:
        force_variant(old_rules, 'large')
        tomato_jobs(old_rules)
        state = orders.create_board(cfg, make_town(cfg))
        offer = state['offers'][0]
        for need in offer['requirements']:
            state['inventory'][need['goodId']] = need['quantity']
        assert orders.apply_action(cfg, state, 0, 'fulfill', offer['id'])['ok']
    saved = copy.deepcopy(state['offers'])
    force_variant(monkeypatch, variant)
    reloaded = orders.create_board(cfg, json.loads(json.dumps(state)), cooldown_seconds=600)
    assert reloaded['offers'] == saved
    assert reloaded['cash'] == state['cash']
    assert not orders.apply_action(cfg, reloaded, 0, 'replace', saved[0]['id'])['ok']
    reloaded['tick'] = saved[0]['deliveryUntilTick']
    orders.refresh_board(cfg, reloaded)
    assert reloaded['cash'] == state['cash'] + saved[0]['reward']
    assert reloaded['offers'][0]['rarity'] == variant
    assert reloaded['offers'][1:] == saved[1:]
    assert reloaded['inventory']['farm_tomatoes'] == 0
    settled = copy.deepcopy(reloaded)
    orders.refresh_board(cfg, reloaded)
    assert reloaded == settled
