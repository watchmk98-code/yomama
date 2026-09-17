"""Market catch-up actions respect stock, reservations and submitted order IDs."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import game_api as api
import market_orders as market
import production_economy as economy
from test_production_api import town, state, edit  # noqa: F401


def rows(st):
    return [dict(offerIndex=i, orderId=o['id']) for i, o in enumerate(st['offers'])]


def own(st, tier):
    st['tierOf'].append(tier)
    st['b'].append(economy._building(tier))


def test_new_business_introduces_relevant_order_without_changing_saved_or_ready():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    st['offers'][0]['committed'] = True
    for n in st['offers'][1]['requirements']:
        st['inventory'][n['goodId']] = 500
    saved = copy.deepcopy(st['offers'][:2])
    # Keep the third card waiting while the first two are protected.
    st['offers'][2]['requirements'] = [dict(goodId='farm_tomatoes', quantity=1000)]
    own(st, 2)
    market.sync(cfg, st)
    assert st['offers'][:2] == saved
    assert any(n['goodId'].startswith('roastery_') for n in st['offers'][2]['requirements'])
    before = copy.deepcopy(st)
    market.sync(cfg, st)
    assert st == before


def test_pending_new_business_survives_reload_and_finds_room_later():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    for o in st['offers']: o['committed'] = True
    before = copy.deepcopy(st['offers'])
    own(st, 3)
    market.sync(cfg, st)
    assert st['offers'] == before and st['marketPendingGoods']
    st = economy.migrate_state(cfg, json.loads(json.dumps(st)))
    st['offers'][1]['committed'] = False
    market.sync(cfg, st)
    assert any(n['goodId'].startswith('garage_') for n in st['offers'][1]['requirements'])
    assert st['offers'][0] == before[0] and st['offers'][2] == before[2]


def test_completed_construction_introduces_orders_through_the_engine():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    st['build'] = dict(i=2, t=1)
    economy.finish_build(cfg, st, 1)
    assert any(n['goodId'].startswith('roastery_') for o in st['offers'] for n in o['requirements'])


def test_new_business_gets_next_freed_card_when_whole_board_was_ready():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    for o in st['offers']:
        for n in o['requirements']: st['inventory'][n['goodId']] = 200
    before = copy.deepcopy(st['offers'])
    st['build'] = dict(i=2, t=1)
    economy.finish_build(cfg, st, 1)
    assert st['offers'] == before and st['marketPendingGoods']
    assert economy.fulfill_order(cfg, st, 0, before[0]['id'])['ok']
    assert any(n['goodId'].startswith('roastery_') for n in st['offers'][0]['requirements'])
    assert st['offers'][1:] == before[1:]


def test_old_saves_keep_terms_and_multiple_new_businesses_get_distinct_cards():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    st.pop('marketKnownGoods'); st.pop('marketPendingGoods')
    before = copy.deepcopy(st['offers'])
    st = economy.migrate_state(cfg, st)
    assert st['offers'] == before
    own(st, 1); own(st, 2)
    market.sync(cfg, st)
    gids = {n['goodId'] for o in st['offers'] for n in o['requirements']}
    assert any(g.startswith('fish_stall_') for g in gids)
    assert any(g.startswith('roastery_') for g in gids)


def test_competing_ready_cards_never_double_spend_or_deliver_replacements():
    cfg = economy.load_config(); st = economy.new_state(cfg)
    for o in st['offers']:
        o['requirements'] = [dict(goodId='farm_tomatoes', quantity=8)]
    st['inventory']['farm_tomatoes'] = 8
    result = market.fulfill_ready(cfg, st, rows(st))
    assert result['delivered'] == 1 and result['skipped'] == 2
    assert st['cStats']['done'] == 1 and st['inventory']['farm_tomatoes'] == 0


@pytest.mark.parametrize('invalid', [None, [], [{}], [dict(offerIndex=True, orderId='x')]])
def test_bad_selections_do_not_mutate_state(invalid):
    cfg = economy.load_config(); st = economy.new_state(cfg); before = copy.deepcopy(st)
    assert not market.fulfill_ready(cfg, st, invalid)['ok']
    assert st == before


def test_batch_api_is_authenticated_persisted_and_duplicate_safe(town):
    _, _, players = town; token = players[0]['token']
    with pytest.raises(api.ApiError) as exc:
        api.econ_fulfill_order(dict(token='bogus', orders=[]))
    assert exc.value.status in (401, 403, 404)
    def prepare(cfg, st):
        st['inventory']['farm_tomatoes'] = 24
        for offer in st['offers']:
            offer['requirements'] = [dict(goodId='farm_tomatoes', quantity=8)]
    edit(token, prepare)
    first = state(token)
    selected = [dict(offerIndex=i, orderId=o['id']) for i, o in enumerate(first['contracts']['offers'])]
    def deliver(_):
        try: return api.econ_fulfill_order(dict(token=token, orders=selected))
        except api.ApiError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(deliver, range(2)))
    assert sum(r is not None for r in replies) == 1
    assert next(g['quantity'] for g in state(token)['board'] if g['goodId']=='farm_tomatoes') == 0


def bulk_tomatoes(monkeypatch):
    from test_order_variants import force_variant, tomato_jobs
    force_variant(monkeypatch, 'bulk')
    tomato_jobs(monkeypatch)
    cfg = economy.load_config()
    cfg['production']['orderMinutes'] = [1, 1, 1]
    return cfg, economy.new_state(cfg)


def test_bulk_roll_sizes_to_surplus_and_honors_other_saved_orders(monkeypatch):
    cfg, st = bulk_tomatoes(monkeypatch)
    st['inventory']['farm_tomatoes'] = 50
    st['offers'][0].update(requirements=[dict(goodId='farm_tomatoes', quantity=10)], committed=True)
    saved = copy.deepcopy(st['offers'][0])
    assert economy.replace_order(cfg, st, 1, st['offers'][1]['id'])['ok']
    offer = st['offers'][1]
    assert offer['rarity'] == 'bulk' and offer['rewardPercent'] == 99
    assert offer['requirements'] == [dict(goodId='farm_tomatoes', quantity=40)]
    assert not offer['committed']
    assert st['offers'][0] == saved
    cash = st['cash']
    assert economy.fulfill_order(cfg, st, 1, offer['id'])['ok']
    assert st['inventory']['farm_tomatoes'] == 10
    assert st['cash'] == cash+offer['reward']


def test_bulk_roll_keeps_regular_supplies_and_preserves_saved_terms(monkeypatch):
    cfg, st = bulk_tomatoes(monkeypatch)
    assert economy.manage_customer_contract(cfg, st, 0, 'accept', 'corner_grocer')['ok']
    st['cash'] = 10000
    st['inventory']['farm_tomatoes'] = 50
    assert economy.replace_order(cfg, st, 0, st['offers'][0]['id'])['ok']
    offer = st['offers'][0]
    assert offer['requirements'] == [dict(goodId='farm_tomatoes', quantity=44)]
    assert economy.commit_order(cfg, st, 0, offer['id'], True)['ok']
    saved = copy.deepcopy(offer)
    economy.advance_class(cfg, economy.new_class(cfg, 40), [st], 0, 40)
    st = economy.migrate_state(cfg, json.loads(json.dumps(st)))
    economy.on_login(cfg, st)
    assert st['offers'][0] == saved
    assert st['customerContracts']['deliveries'] > 0


def test_bulk_roll_remains_capped_by_storage(monkeypatch):
    cfg, st = bulk_tomatoes(monkeypatch)
    st['inventory']['farm_tomatoes'] = 10000
    assert economy.replace_order(cfg, st, 0, st['offers'][0]['id'])['ok']
    assert st['offers'][0]['requirements'][0]['quantity'] == economy._good_capacity(cfg, st, 0, 'farm_tomatoes')
