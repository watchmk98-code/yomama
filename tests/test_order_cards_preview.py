"""The local browser adapter persists deliveries and pays only on arrival."""
import copy
import json

import pytest

import game_api as A
import order_engine as orders
import production_economy as economy
import server
from previews.order_cards_browser import browser_handler, preview_runtime, stocked_town
from test_access_integration import db, opened  # noqa: F401


@pytest.fixture
def preview(db, monkeypatch):
    clock = {'seconds': 0}
    monkeypatch.setattr(A, 'econ_clock_seconds', lambda session: clock['seconds'])
    session = opened(db, label='ORDER TEST')
    seat = A.join(dict(code=session['code'], name='BUYER', pin='1234'))
    cfg = economy.load_config()
    state = stocked_town(cfg)
    economy.business_operations.ensure(cfg, state)
    for building in state['b']:
        building['paused'] = True
    with A.connect() as conn:
        player = conn.execute('SELECT * FROM players WHERE token=?', (seat['token'],)).fetchone()
        A._save_state(conn, player['id'], cfg, state)
    routes = browser_handler(seat['token']).GAME_POST_ROUTES
    with preview_runtime():
        yield cfg, state, seat, clock, routes


def action(routes, seat, name, index, order_id, **extra):
    return routes['/api/game/econ/orders/' + name](dict(
        token=seat['token'], offerIndex=index, orderId=order_id, **extra))


def test_sample_orders_are_deliverable_without_exceeding_shelf_capacity():
    cfg = economy.load_config()
    state = stocked_town(cfg)
    for slot, tier in enumerate(state['tierOf']):
        for good in cfg['tiers'][tier]['goods']:
            assert state['inventory'][good['id']] <= economy._good_capacity(cfg, state, slot, good['id'])
    payload = economy.payload(cfg, state, economy.new_class(cfg, 0), {'paused': False})
    assert len(payload['contracts']['offers']) == 3
    assert all(order['canFulfill'] for order in payload['contracts']['offers'])


def saved_state(seat):
    with A.connect() as conn:
        return json.loads(conn.execute('SELECT econ FROM players WHERE token=?',
                                       (seat['token'],)).fetchone()['econ'])


def save_state(cfg, seat, state):
    with A.connect() as conn:
        player = conn.execute('SELECT id FROM players WHERE token=?', (seat['token'],)).fetchone()
        A._save_state(conn, player['id'], cfg, state)


def test_browser_delivery_pays_only_on_arrival_counts_smoothly_and_persists(preview):
    cfg, state, seat, clock, routes = preview
    first, _, third = copy.deepcopy(state['offers'])
    result = action(routes, seat, 'fulfill', 0, first['id'])
    outbound = result['contracts']['offers'][0]
    assert result['receipt']['kind'] == 'order_dispatch'
    assert result['receipt']['reward'] == 0
    assert result['cash'] == state['cash']
    assert outbound['id'] == first['id']
    assert outbound['inTransit'] and outbound['committed']
    assert outbound['deliveryRemainingSec'] == 60
    assert outbound['deliverySeconds'] == result['orderPreview']['deliverySeconds'] == 60
    assert not outbound['canFulfill'] and not outbound['canCommit'] and not outbound['canReplace']
    assert not result['orderPreview']['lastDelivery']
    assert saved_state(seat)['inventory'] == state['inventory']
    for name in ('fulfill', 'replace'):
        with pytest.raises(A.ApiError):
            action(routes, seat, name, 0, outbound['id'])
    for committed in (False, True):
        with pytest.raises(A.ApiError):
            action(routes, seat, 'commit', 0, outbound['id'], committed=committed)
    clock['seconds'] = 30.25
    halfway = A.econ_state({'token': seat['token']})
    assert halfway['contracts']['offers'][0]['deliveryRemainingSec'] == 30
    assert halfway['cash'] == state['cash']
    assert saved_state(seat)['offers'][0]['inTransit']
    clock['seconds'] = 59.75
    before = A.econ_state({'token': seat['token']})
    assert before['contracts']['offers'][0]['deliveryRemainingSec'] == 1
    assert before['cash'] == state['cash']
    clock['seconds'] = 61
    completed = A.econ_state({'token': seat['token']})
    ready = completed['contracts']['offers'][0]
    assert completed['cash'] == state['cash'] + first['reward']
    assert completed['materials'] == 0
    assert not ready.get('inTransit') and ready['id'] != outbound['id']
    assert ready['canReplace']
    assert ready['deliverySeconds'] == orders.quote_delivery_seconds(cfg, ready)
    assert completed['orderPreview']['lastDelivery'] == dict(
        orderId=first['id'], reward=first['reward'], materials=first['materials'], rarity=first['rarity'])
    saved = saved_state(seat)
    assert saved['offers'][0]['id'] == ready['id']
    assert saved['offers'][2] == third
    assert saved['cStats']['done'] == state['cStats']['done'] + 1
    for need in first['requirements']:
        gid = need['goodId']
        assert saved['inventory'][gid] == state['inventory'][gid] - need['quantity']
    again = A.econ_state({'token': seat['token']})
    assert again['cash'] == completed['cash']
    assert again['orderPreview']['lastDelivery'] == completed['orderPreview']['lastDelivery']
    assert saved_state(seat)['cStats']['done'] == saved['cStats']['done']
    with pytest.raises(A.ApiError):
        action(routes, seat, 'fulfill', 0, outbound['id'])


def test_outbound_stock_stays_protected_after_reloading(preview):
    cfg, state, seat, clock, routes = preview
    first = state['offers'][0]
    third = state['offers'][2]
    third['requirements'] = copy.deepcopy(first['requirements'])
    for need in first['requirements']:
        state['inventory'][need['goodId']] = need['quantity']
    save_state(cfg, seat, state)
    action(routes, seat, 'fulfill', 0, first['id'])
    reloaded = A.econ_state({'token': seat['token']})
    assert reloaded['contracts']['offers'][0]['inTransit']
    assert not reloaded['contracts']['offers'][2]['canFulfill']
    with pytest.raises(A.ApiError, match='unreserved'):
        action(routes, seat, 'fulfill', 2, third['id'])
    saved = saved_state(seat)
    assert saved['cash'] == state['cash']
    for need in first['requirements']:
        assert saved['inventory'][need['goodId']] == need['quantity']
    clock['seconds'] = 61
    completed = A.econ_state({'token': seat['token']})
    assert completed['cash'] == state['cash'] + first['reward']
    saved = saved_state(seat)
    assert all(saved['inventory'][need['goodId']] == 0 for need in first['requirements'])


def test_idle_delivery_card_replaces_immediately_without_payment(preview):
    cfg, state, seat, clock, routes = preview
    first = state['offers'][0]
    result = action(routes, seat, 'replace', 0, first['id'])
    replacement = result['contracts']['offers'][0]
    assert replacement['id'] != first['id']
    assert not replacement.get('inTransit') and not replacement.get('waiting')
    assert replacement['canReplace']
    assert replacement['deliverySeconds'] == orders.quote_delivery_seconds(cfg, replacement)
    assert result['cash'] == state['cash']
    assert result['receipt']['kind'] == 'order_replace'
    again = action(routes, seat, 'replace', 0, replacement['id'])
    assert again['contracts']['offers'][0]['id'] != replacement['id']


def test_delivery_quote_tracks_each_payout_and_matches_dispatch(preview):
    cfg, state, seat, clock, routes = preview
    offer = A.econ_state({'token': seat['token']})['contracts']['offers'][0]
    quotes = []
    for _ in range(20):
        quotes.append((offer['reward'], offer['deliverySeconds']))
        assert offer['deliverySeconds'] == orders.quote_delivery_seconds(cfg, offer)
        persisted = saved_state(seat)['offers'][0]
        assert persisted['deliverySeconds'] == offer['deliverySeconds']
        offer = action(routes, seat, 'replace', 0, offer['id'])['contracts']['offers'][0]
    ordered = sorted(quotes)
    assert len({duration for _, duration in ordered}) > 1
    assert all(left[1] <= right[1] for left, right in zip(ordered, ordered[1:]))
    response = action(routes, seat, 'fulfill', 0, offer['id'])
    assert response['receipt']['durationSeconds'] == offer['deliverySeconds']
    assert response['contracts']['offers'][0]['deliverySeconds'] == offer['deliverySeconds']
    assert response['contracts']['offers'][0]['deliveryUntilTick'] * cfg['global']['tick'] == offer['deliverySeconds']


def test_sector_changes_and_third_keeps_original_actions_and_api_validation(preview):
    cfg, state, seat, clock, routes = preview
    third = copy.deepcopy(state['offers'][2])
    sector = state['offers'][1]
    replacement = action(routes, seat, 'replace', 1, sector['id'])['contracts']['offers'][1]
    assert replacement['sectorId'] != sector['sectorId']
    committed = action(routes, seat, 'commit', 2, third['id'], committed=True)
    assert committed['contracts']['offers'][2]['committed']
    released = action(routes, seat, 'commit', 2, third['id'], committed=False)
    assert not released['contracts']['offers'][2]['committed']
    delivered = action(routes, seat, 'fulfill', 2, third['id'])
    assert delivered['contracts']['offers'][2]['id'] != third['id']
    assert not delivered['contracts']['offers'][2].get('waiting')
    with pytest.raises(A.ApiError):
        action(routes, seat, 'commit', 0, state['offers'][0]['id'], committed='yes')
    with pytest.raises(A.ApiError) as rejected:
        routes['/api/game/econ/orders/replace'](dict(token='invalid', offerIndex=0, orderId='unknown'))
    assert rejected.value.status == 401
    assert routes is not server.NewsProxyHandler.GAME_POST_ROUTES
    assert server.NewsProxyHandler.GAME_POST_ROUTES['/api/game/econ/orders/fulfill'] is A.econ_fulfill_order
