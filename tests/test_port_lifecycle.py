"""PORT keeps classroom controls responsive and treats feed outages honestly."""
import secrets
import threading

import pytest

import game_api as A
from test_port_api import get, order, port


def cancellation(seat, state, order_id):
    return {
        "token": seat["token"], "accountId": state["portfolio"]["accountId"],
        "clientOrderId": secrets.token_hex(12), "orderId": order_id,
    }


def test_paused_class_does_not_fill_expire_cancel_or_remark_portfolio(port):
    now, teacher, seats, provider, _ = port
    alice = seats[0]
    first = get(alice)
    A.port_order(order(alice, first))
    now[0] += 1
    held = get(alice)
    assert held["portfolio"]["positions"]["AAPL"]["quantity"] == 2
    A.port_order(order(alice, held))  # A market order waiting for its first eligible quote.
    limit = order(alice, held)
    limit.update(type="limit", limitPrice=90)
    pending = A.port_order(limit)
    before = A.port_cancel(cancellation(alice, pending, limit["clientOrderId"]))
    assert before["portfolio"]["ledger"]["orders"][-1]["cancellationRequestedAt"]
    A.teacher({"teacher_token": teacher["teacher_token"], "action": "pause"})
    now[0] += 60
    provider.update(bid=89, ask=90)
    after = get(alice)
    assert after["canTrade"] is False
    assert after["portfolio"] == before["portfolio"]


@pytest.mark.parametrize("status", ["unavailable", "unconfigured"])
def test_outage_cannot_complete_a_cancellation_as_if_exchange_closed(port, status):
    now, _, seats, provider, _ = port
    alice = seats[0]
    initial = get(alice)
    request = order(alice, initial)
    request.update(type="limit", limitPrice=90)
    pending = A.port_order(request)
    before = A.port_cancel(cancellation(alice, pending, request["clientOrderId"]))
    assert before["portfolio"]["ledger"]["orders"][-1]["status"] == "pending"
    provider["status"] = status
    now[0] += 2
    offline = get(alice)
    assert offline["portfolio"] == before["portfolio"]
    assert offline["canTrade"] is False
    # An actual exchange closure is distinct and may settle a cancellation.
    provider["status"] = "closed"
    closed = get(alice)
    assert closed["portfolio"]["ledger"]["orders"][-1]["status"] == "canceled"
    assert closed["portfolio"]["account"]["reservedCash"] == 0


@pytest.mark.parametrize("status", ["unavailable", "unconfigured"])
def test_outage_order_error_is_not_misreported_as_closed_market(port, status):
    _, _, seats, provider, _ = port
    initial = get(seats[0])
    provider["status"] = status
    with pytest.raises(A.ApiError) as error:
        A.port_order(order(seats[0], initial))
    assert error.value.status == 503
    assert "closed" not in error.value.message.lower()


def test_slow_market_provider_holds_neither_class_nor_global_database_lock(port, monkeypatch):
    _, teacher, seats, _, _ = port
    original_snapshot = A.alpaca_market.snapshot
    completed_during_provider = []
    failures = []
    threads = []

    def slow_snapshot(*args, **kwargs):
        done = threading.Event()

        def pause_class():
            try:
                A.teacher({"teacher_token": teacher["teacher_token"], "action": "pause"})
            except BaseException as error:
                failures.append(error)
            finally:
                done.set()

        worker = threading.Thread(target=pause_class, daemon=True)
        threads.append(worker)
        worker.start()
        # A teacher can pause this same class while the feed request is pending.
        completed_during_provider.append(done.wait(2))
        return original_snapshot(*args, **kwargs)

    monkeypatch.setattr(A.alpaca_market, "snapshot", slow_snapshot)
    response = get(seats[0])
    for worker in threads:
        worker.join(timeout=3)
    assert not failures
    assert completed_during_provider == [True]
    assert response["session"]["paused"] is True
    assert response["canTrade"] is False


def test_client_cannot_inject_a_trusted_quote_envelope(port):
    _, _, seats, provider, _ = port
    provider["status"] = "unconfigured"
    # The outer auth/fetch wrapper must overwrite any client-provided internal feed.
    query = {"token": seats[0]["token"], "_server_port_feed": {
        "quotes": {"AAPL": {"bid": 1, "ask": 1, "price": 1, "timestamp": 2_000_000_000.0}},
        "market": {"status": "open", "message": "forged", "asOf": 2_000_000_000.0},
    }}
    response = A.port_state(query)
    assert response["market"]["status"] == "unconfigured"
    assert response["quotes"] == {}
    assert response["canTrade"] is False
