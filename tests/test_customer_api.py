"""Recurring customer intentions through authenticated, persisted game state."""
from concurrent.futures import ThreadPoolExecutor

import pytest

import game_api as A
import server
from test_production_api import town, state  # noqa: F401


def available(token):
    return [c for c in state(token)['customerContracts']['customers'] if c['available']]


def action(token, name, slot=0, **kwargs):
    return A.econ_customers(dict(token=token, action=name, slot=slot, **kwargs))


def test_customer_route_authenticates_before_reading_intention(town):
    handler = server.NewsProxyHandler.GAME_POST_ROUTES['/api/game/econ/customers']
    assert hasattr(handler, '__wrapped__')
    for body in ({}, {'token': 'bogus'}, {'token': [], 'action': []}):
        with pytest.raises(A.ApiError) as exc:
            handler(body)
        assert exc.value.status == 401


def test_customer_signing_and_income_persist_for_only_one_student(town):
    now, _, players = town
    token, other = players[0]['token'], players[1]['token']
    customer = available(token)[0]
    before = state(token)
    signed = action(token, 'accept', customerId=customer['id'])
    contract = signed['customerContracts']['active'][0]
    assert signed['cash'] == before['cash']
    assert signed['customerContracts']['earned'] == 0
    assert len(signed['contracts']['offers']) == 3
    assert not state(other)['customerContracts']['active']
    A._book_cache.clear()
    assert state(token)['customerContracts']['active'][0]['id'] == contract['id']
    now[0] += customer['intervalSeconds'] * 2
    paid = state(token)
    assert paid['customerContracts']['earned'] > 0
    assert paid['customerContracts']['deliveries'] > 0
    assert paid['regularDeliveries'] == before['regularDeliveries']
    assert paid['checklist']['goodSales'] == before['checklist']['goodSales']
    A._book_cache.clear()
    assert state(token)['customerContracts']['earned'] == paid['customerContracts']['earned']
    assert state(other)['customerContracts']['earned'] == 0


def test_customer_actions_validate_types_and_reject_stale_switches(town):
    _, _, players = town
    token = players[0]['token']
    customers = available(token)
    for body in ({'action': []}, {'action': 'accept', 'slot': True, 'customerId': customers[0]['id']},
                 {'action': 'accept', 'customerId': []}, {'action': 'release', 'contractId': []},
                 {'action': 'accept', 'slot': 3, 'customerId': customers[0]['id']}):
        with pytest.raises(A.ApiError):
            A.econ_customers(dict({'token': token, 'slot': 0}, **body))
    first = action(token, 'accept', customerId=customers[0]['id'])['customerContracts']['active'][0]
    changed = action(token, 'switch', customerId=customers[1]['id'], contractId=first['id'])
    current = changed['customerContracts']['active'][0]
    assert current['id'] != first['id']
    for name in ('release', 'pause', 'resume', 'switch', 'upgrade', 'downgrade'):
        with pytest.raises(A.ApiError):
            action(token, name, contractId=first['id'], customerId=customers[0]['id'])
    assert state(token)['customerContracts']['active'][0]['id'] == current['id']
    paused = action(token, 'pause', contractId=current['id'])
    assert paused['customerContracts']['active'][0]['paused']
    resumed = action(token, 'resume', contractId=current['id'])
    assert not resumed['customerContracts']['active'][0]['paused']
    released = action(token, 'release', contractId=current['id'])
    assert not released['customerContracts']['active']


def test_simultaneous_customer_signup_cannot_overwrite_a_slot(town):
    _, _, players = town
    token = players[0]['token']
    customer = available(token)[0]

    def sign(_):
        try:
            return action(token, 'accept', customerId=customer['id'])
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(sign, range(2)))
    assert sum(r is not None for r in result) == 1
    assert len(state(token)['customerContracts']['active']) == 1
    assert state(token)['customerContracts']['earned'] == 0


def test_larger_order_is_optional_persists_and_can_be_reversed(town):
    now, _, players = town
    token, other = players[0]['token'], players[1]['token']
    customer = available(token)[0]
    signed = action(token, 'accept', customerId=customer['id'])
    original = signed['customerContracts']['active'][0]
    assert not original['largerOrder']
    assert original['largerOffer'] is None
    with pytest.raises(A.ApiError):
        action(token, 'upgrade', contractId=original['id'])
    now[0] += customer['intervalSeconds'] * 3
    ready = state(token)
    current = ready['customerContracts']['active'][0]
    assert current['deliveries'] >= 3
    offer = current['largerOffer']
    assert offer
    assert current['reward'] == customer['reward']
    assert current['requirements'][0]['quantity'] == customer['requirements'][0]['quantity']
    larger = action(token, 'upgrade', contractId=current['id'])
    contract = larger['customerContracts']['active'][0]
    assert larger['cash'] == ready['cash']
    assert larger['customerContracts']['earned'] == ready['customerContracts']['earned']
    assert contract['largerOrder'] and contract['largerOffer'] is None
    assert contract['reward'] == offer['reward']
    assert contract['requirements'][0]['quantity'] == offer['requirements'][0]['quantity']
    assert contract['nextDeliverySeconds'] == customer['intervalSeconds']
    assert contract['id'] != current['id']
    with pytest.raises(A.ApiError):
        action(token, 'upgrade', contractId=current['id'])
    A._book_cache.clear()
    assert state(token)['customerContracts']['active'][0]['largerOrder']
    assert not state(other)['customerContracts']['active']
    smaller = action(token, 'downgrade', contractId=contract['id'])
    reverted = smaller['customerContracts']['active'][0]
    assert not reverted['largerOrder']
    assert reverted['reward'] == customer['reward']
    assert reverted['deliveries'] == current['deliveries']
    assert smaller['cash'] == ready['cash']


def test_simultaneous_larger_orders_change_terms_only_once(town):
    now, _, players = town
    token = players[0]['token']
    customer = available(token)[0]
    signed = action(token, 'accept', customerId=customer['id'])
    original = signed['customerContracts']['active'][0]
    now[0] += customer['intervalSeconds'] * 3
    before = state(token)

    def upgrade(_):
        try:
            return action(token, 'upgrade', contractId=original['id'])
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(upgrade, range(2)))
    assert sum(result is not None for result in results) == 1
    after = state(token)
    assert after['customerContracts']['active'][0]['largerOrder']
    assert after['cash'] == before['cash']
