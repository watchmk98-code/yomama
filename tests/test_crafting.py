"""Crafting spends real resources once, preserves value and respects promises."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import crafting as C
import game_api as A
import production_economy as E


def town(all_buildings=False):
    cfg = E.load_config()
    st = E.new_state(cfg, seed=19)
    st['cash'] = 10000
    if all_buildings:
        st['tierOf'] = list(range(len(cfg['tiers'])))
        st['b'] = [E._building(ti) for ti in st['tierOf']]
    return cfg, st


def body(st, **kwargs):
    revision = st['crafting']['revision']
    return dict(requestId='craft-test-' + str(revision), revision=revision, **kwargs)


def buy(cfg, st, supply_id, quantity):
    result = C.act(cfg, st, body(st, action='buy_supply', supplyId=supply_id, quantity=quantity))
    assert result['ok'], result
    return result


def recipe(item_id):
    return next(row for row in C.RECIPES if row[0] == item_id)


def stock(cfg, st, item_id):
    for gid, quantity in recipe(item_id)[2]:
        if gid in C.SUPPLIES:
            buy(cfg, st, gid, quantity)
        else:
            st['inventory'][gid] = st['inventory'].get(gid, 0) + quantity
    E._sync_pools(cfg, st)


def test_catalog_has_30_items_uses_all_businesses_and_all_12_supplies():
    cfg, st = town(all_buildings=True)
    products = E.catalog(cfg)
    assert len(C.RECIPES) == len({r[0] for r in C.RECIPES}) == 30
    assert len(C.SUPPLIES) == 12
    used = {gid for _, _, needs in C.RECIPES for gid, _ in needs}
    assert used <= set(products) | set(C.SUPPLIES)
    assert used & set(C.SUPPLIES) == set(C.SUPPLIES)
    assert {products[gid]['buildingId'] for gid in used if gid in products} == {t['id'] for t in cfg['tiers']}
    assert all(2 <= len(needs) <= 5 and all(type(q) is int and 1 <= q <= 4 for _, q in needs)
               for _, _, needs in C.RECIPES)
    rows = C.payload(cfg, st)['items']
    assert [r['iconIndex'] for r in rows] == list(range(30))
    assert all(not r['canCraft'] and r['owned'] == 0 for r in rows)
    kinds = {n['id']: n['kind'] for row in rows for n in row['ingredients']}
    assert kinds['solar_coop_daytime_kwh'] == 'energy'
    assert kinds['uplink_center_telemetry'] == 'service'


@pytest.mark.parametrize('item_id', [row[0] for row in C.RECIPES])
def test_every_recipe_consumes_once_and_conserves_net_worth(item_id):
    cfg, st = town(all_buildings=True)
    stock(cfg, st, item_id)
    before_worth = E.net_worth(cfg, st)
    cash, report, progression = st['cash'], copy.deepcopy(st['report']), copy.deepcopy(st['businessProgression'])
    request = body(st, itemId=item_id)
    assert C.act(cfg, st, request)['ok']
    assert E.net_worth(cfg, st) == before_worth
    assert st['cash'] == cash
    assert st['report'] == report
    assert st['businessProgression'] == progression
    assert st['crafting']['items'][item_id]['quantity'] == 1
    for gid, _ in recipe(item_id)[2]:
        assert (st['crafting']['supplies'][gid]['quantity'] if gid in C.SUPPLIES else st['inventory'][gid]) == 0
    saved = json.loads(json.dumps(st))
    retry = C.act(cfg, saved, request)
    assert retry['ok'] and retry['duplicate']
    assert saved == st
    assert E.net_worth(cfg, saved) == before_worth


def test_supply_purchase_transfers_cash_value_and_older_retry_cannot_spend_again():
    cfg, st = town()
    before = E.net_worth(cfg, st)
    request = body(st, action='buy_supply', supplyId='wooden_boards', quantity=3)
    result = C.act(cfg, st, request)
    assert result['ok'] and result['cost'] == 18
    assert st['cash'] == 9982
    assert E.net_worth(cfg, st) == before
    assert C.act(cfg, st, request)['duplicate']
    buy(cfg, st, 'fiber_bundles', 1)
    snapshot = copy.deepcopy(st)
    assert not C.act(cfg, st, request)['ok']
    assert st == snapshot
    assert E.net_worth(cfg, st) == before


@pytest.mark.parametrize('kwargs', [
    dict(action='buy_supply', supplyId='cash', quantity=1),
    dict(action='buy_supply', supplyId=[], quantity=1),
    dict(action='buy_supply', supplyId='wooden_boards', quantity=True),
    dict(action='buy_supply', supplyId='wooden_boards', quantity=-1),
    dict(action='buy_supply', supplyId='wooden_boards', quantity=1.5),
    dict(action='buy_supply', supplyId='wooden_boards', quantity=101),
    dict(action='sell', itemId='fish_trap'),
    dict(itemId=['fish_trap']),
    dict(itemId='fish_trap', quantity=2),
    dict(itemId='fish_trap', requestId=''),
    dict(itemId='fish_trap', revision=True),
])
def test_invalid_or_forged_requests_do_not_change_state(kwargs):
    cfg, st = town()
    before = copy.deepcopy(st)
    request = body(st, itemId='fish_trap')
    request.update(kwargs)
    assert not C.act(cfg, st, request)['ok']
    assert st == before


def test_insufficient_supply_cash_and_recipe_stock_have_no_partial_debit():
    cfg, st = town()
    st['cash'] = 0
    before = copy.deepcopy(st)
    assert not C.act(cfg, st, body(st, action='buy_supply', supplyId='wooden_boards', quantity=1))['ok']
    assert st == before
    st['cash'] = 100
    buy(cfg, st, 'fiber_bundles', 3)
    before = copy.deepcopy(st)
    assert not C.act(cfg, st, body(st, itemId='fish_trap', ingredients={'wooden_boards': 10}, canCraft=True))['ok']
    assert st == before


def test_regular_and_committed_order_stock_cannot_be_used_for_crafting():
    cfg, st = town()
    st['businessProgression']['grandfathered'] = ['farm']
    assert E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='sunrise_diner')['ok']
    stock(cfg, st, 'farm_breakfast_basket')
    st['inventory']['farm_eggs'] = 5
    st['offers'][0] = dict(id='saved-tomatoes', committed=True,
                          requirements=[dict(goodId='farm_tomatoes', quantity=2)])
    E._sync_pools(cfg, st)
    row = next(r for r in C.payload(cfg, st)['items'] if r['id'] == 'farm_breakfast_basket')
    ingredients = {r['id']: r for r in row['ingredients']}
    assert ingredients['farm_eggs']['reserved'] == 4
    assert ingredients['farm_eggs']['available'] == 1
    assert ingredients['farm_tomatoes']['reserved'] == 2
    assert not row['canCraft']
    before = copy.deepcopy(st)
    assert not C.act(cfg, st, body(st, itemId=row['id']))['ok']
    assert st == before
    st['inventory']['farm_eggs'] += 1
    st['inventory']['farm_tomatoes'] += 2
    assert C.act(cfg, st, body(st, itemId=row['id']))['ok']
    assert st['inventory']['farm_eggs'] == 4
    assert st['inventory']['farm_tomatoes'] == 2


def test_old_saves_gain_empty_storage_and_crafted_objects_survive_migration():
    cfg, st = town()
    st.pop('crafting')
    old_worth = E.net_worth(cfg, st)
    migrated = E.migrate_state(cfg, json.loads(json.dumps(st)))
    assert migrated['crafting'] == dict(items={}, supplies={}, revision=0, lastRequest=None)
    assert E.net_worth(cfg, migrated) == old_worth
    stock(cfg, migrated, 'fish_trap')
    assert C.act(cfg, migrated, body(migrated, itemId='fish_trap'))['ok']
    saved = copy.deepcopy(migrated['crafting'])
    migrated = E.migrate_state(cfg, json.loads(json.dumps(migrated)))
    assert migrated['crafting'] == saved


@pytest.fixture
def api_town(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'crafting.db')
    monkeypatch.setattr(A, '_startup_config', E.load_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A.time, 'time', lambda: 2000000000.0)
    A._book_cache.clear()
    A._settled.clear()
    A.init_db()
    teacher = A.create_session({})
    players = [A.join(dict(code=teacher['code'], name=name, pin='1234')) for name in ('CRAFTER', 'NEIGHBOR')]
    token = players[0]['token']
    with A.connect() as conn:
        player = A._player_by_token(conn, token)
        session = A._session_of(conn, player['code'])
        cfg = A.econ_config(session)
        st = A._load_state(player, cfg, session)
        st['cash'] = 1000
        stock(cfg, st, 'fish_trap')
        A._save_state(conn, player['id'], cfg, st)
    return teacher, players, body(st, itemId='fish_trap', token=token)


def test_api_persists_isolates_and_serializes_duplicate_requests(api_town):
    _, players, request = api_town
    before = A.econ_state(dict(token=players[0]['token']))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: A.econ_craft(request), range(2)))
    assert sum(bool(r['receipt'].get('duplicate')) for r in results) == 1
    after = A.econ_state(dict(token=players[0]['token']))
    assert after['crafting']['totalOwned'] == 1
    assert after['cash'] == before['cash']
    assert after['netWorth'] == before['netWorth']
    assert A.econ_state(dict(token=players[1]['token']))['crafting']['totalOwned'] == 0
    A._book_cache.clear()
    assert A.econ_state(dict(token=players[0]['token']))['crafting']['totalOwned'] == 1
    assert A.get_state(dict(token=players[0]['token']))['econ']['crafting']['totalOwned'] == 1


def test_api_rejects_paused_and_invalid_auth_before_any_crafting(api_town):
    teacher, players, request = api_town
    with pytest.raises(A.ApiError) as error:
        A.econ_craft(dict(request, token='invalid'))
    assert error.value.status in (401, 403, 404)
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    with pytest.raises(A.ApiError) as error:
        A.econ_craft(request)
    assert error.value.status == 409
    assert A.econ_state(dict(token=players[0]['token']))['crafting']['totalOwned'] == 0
