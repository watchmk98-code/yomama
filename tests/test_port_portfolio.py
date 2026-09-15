"""Financial and timing invariants for the server-owned virtual portfolio."""
import copy
import json

import pytest

import port_portfolio as port


NOW = 1_800_000_000.0


def account():
    return port.new_state(NOW, account_id="test_port_account")


def quotes(at=NOW, bid=99.99, ask=100.01, price=100.0, symbol="AAPL"):
    return {symbol: {"bid": bid, "ask": ask, "price": price, "timestamp": at}}


def order(state, request_id="buy_1", **overrides):
    body = {"accountId": state["accountId"], "clientOrderId": request_id,
            "symbol": "AAPL", "side": "buy", "type": "market", "quantity": 10}
    body.update(overrides)
    return body


def cancel(state, order_id="buy_1", request_id="cancel_1"):
    return {"accountId": state["accountId"], "clientOrderId": request_id, "orderId": order_id}


def assert_balanced(state):
    cash = state["account"]
    basis = sum(p["totalCostCents"] for p in state["positions"].values())
    assert cash["availableCashCents"] + cash["reservedCashCents"] + basis == cash["startingCashCents"] + cash["realizedPnlCents"]
    assert cash["availableCashCents"] >= 0
    assert cash["reservedCashCents"] == sum(o["reservedAmountCents"] for o in state["ledger"]["orders"] if o["status"] == "pending")


def buy(state=None, quantity=10, at=NOW, price=100.0, request_id="buy_1"):
    state = account() if state is None else state
    return port.submit_order(state, order(state, request_id, quantity=quantity), quotes(at, price, price, price), now=at)


def test_new_account_has_only_starting_cash_and_no_demo_or_legacy_holdings():
    state = account()
    public = port.public_state(state)
    assert public["account"] == {"startingCash": 100000.0, "availableCash": 100000.0, "reservedCash": 0.0, "realizedPnl": 0.0}
    assert public["positions"] == {}
    assert public["ledger"]["orders"] == []
    assert public["ledger"]["fills"] == []
    assert port.new_state(NOW)["accountId"] != port.new_state(NOW)["accountId"]
    assert_balanced(state)


def test_market_order_waits_for_event_at_or_after_server_submission():
    original = account()
    pending = port.submit_order(original, order(original), quotes(NOW - 0.1), NOW)
    assert original == account(), "The caller's persisted state must remain untouched"
    assert pending["positions"] == {}
    assert pending["account"]["reservedCashCents"] == 100010
    assert pending["ledger"]["orders"][0]["status"] == "pending"
    unchanged = port.match_orders(pending, quotes(NOW - 0.001, ask=90), NOW + 1)
    assert unchanged == pending
    filled = port.match_orders(pending, quotes(NOW, bid=99.99, ask=100.02), NOW + 1)
    assert filled["positions"]["AAPL"]["quantity"] == 10
    assert filled["positions"]["AAPL"]["totalCostCents"] == 100020
    assert filled["ledger"]["fills"][0]["marketTimestamp"] == NOW
    assert filled["account"]["reservedCashCents"] == 0
    assert_balanced(filled)


def test_market_buy_uses_ask_sell_uses_bid_and_round_trip_money_is_conserved():
    state = account()
    state = port.submit_order(state, order(state), quotes(), NOW)
    assert state["account"]["availableCashCents"] == 9_899_990
    assert state["positions"]["AAPL"]["totalCostCents"] == 100010
    state = port.submit_order(state, order(state, "sell_1", side="sell"), quotes(NOW + 1, 110.02, 110.05, 110.03), NOW + 1)
    assert state["positions"] == {}
    assert state["account"]["availableCashCents"] == 10_010_010
    assert state["account"]["realizedPnlCents"] == 10010
    assert [f["fillPriceCents"] for f in state["ledger"]["fills"]] == [10001, 11002]
    assert_balanced(state)


def test_partial_sales_allocate_integer_cost_basis_without_rounding_drift():
    state = buy(quantity=1, price=100.01)
    state = buy(state, quantity=2, price=100.0, at=NOW + 1, request_id="buy_2")
    realized = 0
    for index in range(3):
        state = port.submit_order(state, order(state, "sell_%d" % index, side="sell", quantity=1), quotes(NOW + 2 + index, 101, 101, 101), NOW + 2 + index)
        assert_balanced(state)
        realized += state["ledger"]["fills"][-1]["realizedPnlCents"]
    assert state["positions"] == {}
    assert state["account"]["realizedPnlCents"] == realized == 299
    assert state["account"]["availableCashCents"] == 10_000_299


def test_limit_reservation_cancel_release_and_retry_survive_serialization():
    state = account()
    request = order(state, type="limit", limitPrice=90, quantity=100)
    state = port.submit_order(state, request, quotes(), NOW)
    assert state["account"]["reservedCashCents"] == 900000
    assert state["account"]["availableCashCents"] == 9100000
    cancellation = cancel(state)
    state = port.cancel_order(state, cancellation, quotes(NOW + 1), NOW + 1)
    assert state["ledger"]["orders"][0]["status"] == "canceled"
    assert state["account"]["availableCashCents"] == 10000000
    assert state["account"]["reservedCashCents"] == 0
    state = port.load_state(json.dumps(state))
    assert port.cancel_order(state, cancellation, {}, NOW + 2) == state
    assert port.submit_order(state, request, {}, NOW + 2, market_open=False) == state
    assert_balanced(state)


def test_limit_fill_obeys_bid_ask_boundary_and_releases_price_improvement():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=100, quantity=2), quotes(), NOW)
    assert not state["positions"], "Last price at limit cannot fill a buy when ask is above limit"
    state = port.match_orders(state, quotes(NOW + 1, 98.99, 99, 99), NOW + 1)
    assert state["positions"]["AAPL"]["totalCostCents"] == 19800
    assert state["account"]["availableCashCents"] == 9980200
    assert state["account"]["reservedCashCents"] == 0
    state = port.submit_order(state, order(state, "sell_limit", side="sell", type="limit", limitPrice=101, quantity=2), quotes(NOW + 2, 100.99, 101.01, 101), NOW + 2)
    assert state["ledger"]["orders"][-1]["status"] == "pending"
    state = port.match_orders(state, quotes(NOW + 3, 101, 101.01, 101), NOW + 3)
    assert state["ledger"]["orders"][-1]["status"] == "filled"
    assert_balanced(state)


def test_pending_buy_reservations_prevent_overspending():
    state = account()
    state = port.submit_order(state, order(state, quantity=900, type="limit", limitPrice=100), quotes(), NOW)
    with pytest.raises(port.PortError) as err:
        port.submit_order(state, order(state, "buy_2", quantity=101, type="limit", limitPrice=100), quotes(), NOW)
    assert err.value.code == "insufficient_cash"
    assert_balanced(state)


def test_pending_sells_reserve_shares_across_orders():
    state = buy(quantity=10)
    state = port.submit_order(state, order(state, "sell_1", side="sell", type="limit", limitPrice=110, quantity=7), quotes(NOW + 1), NOW + 1)
    with pytest.raises(port.PortError) as err:
        port.submit_order(state, order(state, "sell_2", side="sell", quantity=4), quotes(NOW + 2), NOW + 2)
    assert err.value.code == "insufficient_shares"
    public = port.public_state(state)["positions"]["AAPL"]
    assert public["reservedQuantity"] == 7
    assert public["availableQuantity"] == 3
    state = port.cancel_order(state, cancel(state, "sell_1"), quotes(NOW + 2), NOW + 2)
    state = port.submit_order(state, order(state, "sell_2", side="sell", quantity=10), quotes(NOW + 3), NOW + 3)
    assert not state["positions"]
    assert_balanced(state)


def test_market_jump_cannot_spend_cash_reserved_for_another_order():
    state = account()
    state = port.submit_order(state, order(state, "limit_1", quantity=900, type="limit", limitPrice=100), quotes(), NOW)
    state = port.submit_order(state, order(state, "buy_2", quantity=99), quotes(NOW), NOW + 0.1)
    state = port.match_orders(state, quotes(NOW + 1, 110, 110, 110), NOW + 1)
    assert state["ledger"]["orders"][1]["status"] == "rejected"
    assert state["account"]["availableCashCents"] == 1000000
    assert state["account"]["reservedCashCents"] == 9000000
    assert_balanced(state)


def test_market_timeout_releases_reservation_and_never_fills_later():
    state = account()
    state = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW)
    state = port.match_orders(state, {}, NOW + 31)
    assert state["ledger"]["orders"][0]["status"] == "expired"
    assert state["account"]["availableCashCents"] == 10000000
    later = port.match_orders(state, quotes(NOW + 32), NOW + 32)
    assert later["ledger"] == state["ledger"]
    assert later["positions"] == state["positions"]
    assert later["account"] == state["account"]
    assert_balanced(state)


def test_cancellation_cannot_outrun_an_earlier_eligible_fill():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    # At cancellation time the server knows a qualifying event from one second earlier.
    state = port.cancel_order(state, cancel(state), quotes(NOW + 1, 89, 90, 90), NOW + 2)
    assert state["ledger"]["orders"][0]["status"] == "filled"
    assert state["positions"]["AAPL"]["quantity"] == 10
    assert_balanced(state)


def test_cancellation_waits_for_market_timestamp_and_beats_later_fill():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    state = port.cancel_order(state, cancel(state), {}, NOW + 1)
    assert state["ledger"]["orders"][0]["status"] == "pending"
    assert state["ledger"]["orders"][0]["cancellationTimestamp"] == NOW + 1
    state = port.match_orders(state, quotes(NOW + 2, 89, 90, 90), NOW + 2)
    assert state["ledger"]["orders"][0]["status"] == "canceled"
    assert not state["positions"]
    assert_balanced(state)


def test_closed_market_rejects_new_orders_but_allows_cancellation():
    state = account()
    with pytest.raises(port.PortError) as err:
        port.submit_order(state, order(state), quotes(), NOW, market_open=False)
    assert err.value.code == "market_closed"
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    state = port.match_orders(state, quotes(NOW + 1, 89, 90, 90), NOW + 1, market_open=False)
    assert state["ledger"]["orders"][0]["status"] == "pending"
    state = port.cancel_order(state, cancel(state), {}, NOW + 2, market_open=False)
    assert state["ledger"]["orders"][0]["status"] == "canceled"


def test_idempotent_market_retry_cannot_duplicate_a_fill_even_after_price_changes():
    state = account()
    request = order(state)
    state = port.submit_order(state, request, quotes(), NOW)
    state = port.load_state(json.dumps(state))
    assert port.submit_order(state, request, quotes(NOW + 1, 110, 110, 110), NOW + 1) == state
    assert len(state["ledger"]["fills"]) == 1
    request["quantity"] = 11
    with pytest.raises(port.PortError) as err:
        port.submit_order(state, request, quotes(), NOW)
    assert err.value.status == 409
    assert err.value.code == "idempotency_conflict"


def test_request_id_is_not_reusable_between_submit_and_cancel():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    with pytest.raises(port.PortError) as err:
        port.cancel_order(state, cancel(state, request_id="buy_1"), quotes(), NOW)
    assert err.value.code == "idempotency_conflict"


def test_account_identity_prevents_old_retry_from_spending_reset_account():
    original = account()
    fresh = port.new_state(NOW + 1)
    with pytest.raises(port.PortError) as err:
        port.submit_order(fresh, order(original), quotes(NOW + 1), NOW + 1)
    assert err.value.code == "account_changed"
    assert fresh["account"]["availableCashCents"] == 10000000


@pytest.mark.parametrize("quantity", [0, -1, 1.1, float("nan"), float("inf"), True, None, "2", {}, [], 1000001, 10 ** 1000])
def test_invalid_quantities_never_change_account(quantity):
    state = account()
    with pytest.raises(port.PortError):
        port.submit_order(state, order(state, quantity=quantity), quotes(), NOW)
    assert state == account()


@pytest.mark.parametrize("limit", [0, -1, 1.001, float("nan"), float("inf"), True, None, {}, [], 1000001])
def test_invalid_limits_are_rejected(limit):
    state = account()
    with pytest.raises(port.PortError):
        port.submit_order(state, order(state, type="limit", limitPrice=limit), quotes(), NOW)


@pytest.mark.parametrize("changes", [{"symbol": "FAKE"}, {"symbol": ["AAPL"]}, {"side": "short"}, {"type": "stop"}, {"clientOrderId": "a/b"}, {"clientOrderId": ""}])
def test_invalid_order_fields_are_rejected(changes):
    state = account()
    with pytest.raises(port.PortError):
        port.submit_order(state, order(state, **changes), quotes(), NOW)


@pytest.mark.parametrize("bad_quote", [None, {}, {"bid": 100, "ask": 99, "timestamp": NOW}, {"bid": 100, "ask": 101, "timestamp": NOW - 10.001}, {"bid": 100, "ask": 101, "timestamp": NOW + 0.001}, {"bid": 100, "ask": 101, "timestamp": float("nan")}, {"bid": 0, "ask": 101, "timestamp": NOW}, {"bid": 100, "ask": float("nan"), "timestamp": NOW}])
def test_unavailable_stale_future_and_invalid_quotes_fail_closed(bad_quote):
    state = account()
    with pytest.raises(port.PortError) as err:
        port.submit_order(state, order(state), {"AAPL": bad_quote}, NOW)
    assert err.value.code == "quote_unavailable"
    assert state == account()


def test_stale_quote_cannot_fill_or_reprice_a_holding():
    state = buy()
    state = port.submit_order(state, order(state, "sell_1", side="sell", type="limit", limitPrice=110), quotes(NOW + 1), NOW + 1)
    assert port.match_orders(state, quotes(NOW + 2, 110, 111, 110), NOW + 20) == state


def test_subcent_quotes_are_rounded_conservatively_to_cents():
    state = account()
    state = port.submit_order(state, order(state, quantity=1), quotes(NOW, 100.001, 100.009, 100.005), NOW)
    assert state["ledger"]["fills"][0]["fillPriceCents"] == 10001
    state = port.submit_order(state, order(state, "sell_1", side="sell", quantity=1), quotes(NOW + 1, 100.001, 100.009, 100.005), NOW + 1)
    assert state["ledger"]["fills"][1]["fillPriceCents"] == 10000
    assert state["account"]["realizedPnlCents"] == -1


def test_public_payload_is_a_copy_and_exposes_dollars_and_complete_history():
    state = buy()
    public = port.public_state(state)
    assert public["positions"]["AAPL"]["totalCost"] == 1000
    assert public["positions"]["AAPL"]["avgCost"] == 100
    assert public["positions"]["AAPL"]["marketValue"] == 1000
    assert public["ledger"]["orders"][0]["fillPrice"] == 100
    assert public["ledger"]["fills"][0]["grossAmount"] == 1000
    assert "requests" not in public
    public["account"]["availableCash"] = 999999
    public["ledger"]["orders"][0]["quantity"] = 9999
    assert state["account"]["availableCashCents"] == 9900000
    assert state["ledger"]["orders"][0]["quantity"] == 10


@pytest.mark.parametrize("raw", ["{invalid", "null", "{}", "[]", {"version": "0.1.0", "account": {"availableCash": 100000}}, {"cash": 2500, "positions": {"AAPL": 100}}])
def test_corrupted_or_demo_or_legacy_data_never_silently_resets_progress(raw):
    with pytest.raises(port.PortError) as err:
        port.load_state(raw)
    assert err.value.code == "invalid_portfolio"


def test_load_detects_unbalanced_cash_and_preserves_input():
    state = buy()
    state["account"]["availableCashCents"] += 1
    original = copy.deepcopy(state)
    with pytest.raises(port.PortError):
        port.load_state(state)
    assert state == original


def test_only_absent_state_creates_new_portfolio():
    assert port.load_state(None, NOW)["positions"] == {}
    assert port.load_state("", NOW)["account"]["startingCashCents"] == 10000000
    with pytest.raises(port.PortError):
        port.load_state({})


def test_processing_delay_uses_original_receipt_for_fill_eligibility_and_deadline():
    state = account()
    result = port.submit_order(state, order(state), quotes(NOW + 2), NOW + 3,
                               received_at=NOW, session_open=NOW - 100, session_close=NOW + 100)
    placed = result["ledger"]["orders"][0]
    assert placed["status"] == "filled"
    assert placed["submittedTimestamp"] == placed["receivedTimestamp"] == NOW
    assert placed["expiresTimestamp"] == NOW + 30
    assert placed["acceptedAt"] != placed["receivedAt"]
    assert result["ledger"]["fills"][0]["marketTimestamp"] == NOW + 2
    assert_balanced(result)
    pending = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW + 3, received_at=NOW)
    assert pending["ledger"]["orders"][0]["status"] == "pending"
    assert pending["ledger"]["orders"][0]["expiresTimestamp"] == NOW + 30


@pytest.mark.parametrize("quote_offset,expected", [(0.5, "filled"), (1, "canceled"), (1.5, "canceled")])
def test_cancellation_is_ordered_at_receipt_instead_of_after_provider_call(quote_offset, expected):
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    result = port.cancel_order(state, cancel(state), quotes(NOW + quote_offset, 89, 90, 90),
                               NOW + 2, received_at=NOW + 1)
    placed = result["ledger"]["orders"][0]
    assert placed["status"] == expected
    assert placed["cancellationTimestamp"] == NOW + 1
    assert placed["cancellationRequestedAt"] != placed["cancellationAcceptedAt"]
    assert_balanced(result)


def test_limit_cannot_use_premarket_quote_at_regular_session_open():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    opening = NOW + 100
    before_open = port.match_orders(state, quotes(opening - 0.1, 89, 90, 90), opening,
                                    session_open=opening, session_close=opening + 100)
    assert before_open["ledger"]["orders"][0]["status"] == "pending"
    opened = port.match_orders(before_open, quotes(opening, 89, 90, 90), opening,
                               session_open=opening, session_close=opening + 100)
    assert opened["ledger"]["orders"][0]["status"] == "filled"
    assert_balanced(opened)


@pytest.mark.parametrize("offset", [0, 0.1])
def test_limit_cannot_fill_at_or_after_regular_session_close(offset):
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    closing = NOW + 5
    result = port.match_orders(state, quotes(closing + offset, 89, 90, 90), closing + offset,
                               session_open=NOW - 10, session_close=closing)
    assert result["ledger"]["orders"][0]["status"] == "pending"
    assert not result["positions"]


def test_resume_cutoff_excludes_paused_period_quotes():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    result = port.match_orders(state, quotes(NOW + 1, 89, 90, 90), NOW + 2, resume_at=NOW + 2)
    assert result["ledger"]["orders"][0]["status"] == "pending"
    result = port.match_orders(result, quotes(NOW + 2, 89, 90, 90), NOW + 2, resume_at=NOW + 2)
    assert result["ledger"]["orders"][0]["status"] == "filled"
    assert_balanced(result)


def test_receipt_before_open_and_processing_after_close_cannot_submit_new_orders():
    state = account()
    with pytest.raises(port.PortError) as before:
        port.submit_order(state, order(state), quotes(NOW + 1), NOW + 1,
                          received_at=NOW, session_open=NOW + 0.5)
    assert before.value.code == "market_closed"
    with pytest.raises(port.PortError) as after:
        port.submit_order(state, order(state), quotes(NOW + 1), NOW + 1,
                          received_at=NOW, session_close=NOW + 0.5)
    assert after.value.code == "market_closed"


def test_market_deadline_is_earlier_of_thirty_seconds_and_creation_session_close():
    state = account()
    state = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW,
                              session_open=NOW - 100, session_close=NOW + 5)
    assert state["ledger"]["orders"][0]["expiresTimestamp"] == NOW + 5
    expired = port.match_orders(state, quotes(NOW + 5), NOW + 5, market_open=None)
    assert expired["ledger"]["orders"][0]["status"] == "expired"
    assert expired["account"]["reservedCashCents"] == 0
    assert_balanced(expired)


def test_thirty_second_deadline_is_exclusive_for_market_fills():
    state = account()
    state = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW)
    result = port.match_orders(state, quotes(NOW + 30), NOW + 30)
    assert result["ledger"]["orders"][0]["status"] == "expired"
    assert not result["positions"]
    assert_balanced(result)


def test_confirmed_close_expires_markets_but_preserves_gtc_limits():
    state = account()
    state = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW)
    state = port.submit_order(state, order(state, "limit_1", type="limit", limitPrice=90), quotes(NOW - 0.1), NOW)
    result = port.match_orders(state, {}, NOW + 1, market_open=False)
    assert [item["status"] for item in result["ledger"]["orders"]] == ["expired", "pending"]
    assert result["account"]["reservedCashCents"] == 90000
    assert_balanced(result)


def test_real_market_deadline_still_expires_after_a_class_pause():
    state = account()
    state = port.submit_order(state, order(state), quotes(NOW - 0.1), NOW)
    # The API leaves this state untouched during the pause, then resumes here.
    result = port.match_orders(state, quotes(NOW + 31), NOW + 31, resume_at=NOW + 31)
    assert result["ledger"]["orders"][0]["status"] == "expired"
    assert not result["positions"]


def test_non_crossing_quote_advances_watermark_and_rejects_later_arriving_older_snapshot():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    state = port.match_orders(state, quotes(NOW + 2, 101, 102, 101), NOW + 2)
    assert state["meta"]["executionTimestamps"]["AAPL"] == NOW + 2
    older = port.match_orders(state, quotes(NOW + 1, 89, 90, 90), NOW + 3)
    assert older == state
    newer = port.match_orders(older, quotes(NOW + 3, 89, 90, 90), NOW + 3)
    assert newer["ledger"]["orders"][0]["status"] == "filled"
    assert_balanced(newer)


def test_one_fresh_event_can_fill_all_eligible_orders_without_watermark_interference():
    state = account()
    state = port.submit_order(state, order(state, type="limit", limitPrice=90), quotes(), NOW)
    state = port.submit_order(state, order(state, "buy_2", type="limit", limitPrice=90), quotes(), NOW)
    result = port.match_orders(state, quotes(NOW + 1, 89, 90, 90), NOW + 1)
    assert [item["status"] for item in result["ledger"]["orders"]] == ["filled", "filled"]
    assert result["positions"]["AAPL"]["quantity"] == 20
    assert result["meta"]["executionTimestamps"]["AAPL"] == NOW + 1
    assert_balanced(result)


def test_unknown_market_never_fills_marks_or_completes_cancellation():
    state = buy()
    state = port.submit_order(state, order(state, "buy_2", type="limit", limitPrice=90), quotes(NOW), NOW + 1)
    state = port.cancel_order(state, cancel(state, "buy_2"), {}, NOW + 1, market_open=None)
    result = port.match_orders(state, quotes(NOW + 2, 89, 90, 90), NOW + 2, market_open=None)
    assert result == state
    assert result["positions"]["AAPL"]["marketPriceCents"] == 10000
    assert result["ledger"]["orders"][-1]["status"] == "pending"


def test_unknown_market_rejects_new_orders_but_accepts_idempotent_retries():
    state = account()
    request = order(state)
    with pytest.raises(port.PortError) as error:
        port.submit_order(state, request, quotes(), NOW, market_open=None)
    assert error.value.status == 503 and error.value.code == "market_unavailable"
    state = port.submit_order(state, request, quotes(), NOW)
    assert port.submit_order(state, request, {}, NOW + 1, market_open=None) == state


def test_old_version_one_save_gains_execution_fields_without_losing_cash_or_history():
    state = buy()
    state = port.submit_order(state, order(state, "buy_2"), quotes(NOW), NOW + 1)
    state["meta"].pop("executionTimestamps")
    for item in state["ledger"]["orders"]:
        for key in ("receivedAt", "receivedTimestamp", "expiresAt", "expiresTimestamp"):
            item.pop(key, None)
    old_cash = copy.deepcopy(state["account"])
    old_positions = copy.deepcopy(state["positions"])
    old_fills = copy.deepcopy(state["ledger"]["fills"])
    migrated = port.load_state(json.dumps(state))
    assert migrated["meta"]["executionTimestamps"] == {}
    assert migrated["account"] == old_cash and migrated["positions"] == old_positions
    assert migrated["ledger"]["fills"] == old_fills
    assert migrated["ledger"]["orders"][-1]["expiresTimestamp"] == NOW + 31
    assert port.load_state(json.dumps(migrated)) == migrated
    assert_balanced(migrated)


def test_execution_rules_describe_real_time_regular_session_and_offline_processing():
    rules = port.execution_rules(server_poll_seconds=2)
    assert rules["clock"] == "real_time" and rules["session"] == "regular"
    assert rules["timeZone"] == "America/New_York"
    assert rules["marketOrderTimeoutSeconds"] == 30
    assert rules["marketOrdersExpireAtClose"] is True
    assert rules["ordersContinueOffline"] is True
    assert rules["deadlinesContinueDuringPause"] is True
    assert rules["serverPollSeconds"] == 2
    assert rules["pollIntervalSeconds"] == 2 and rules["matching"] == "server_poll"
    assert rules["timezone"] == "America/New_York"


def test_http_submission_can_reserve_without_selecting_execution_timing():
    state = account()
    first = order(state, type="limit", limitPrice=90)
    state = port.submit_order(state, first, quotes(), NOW, defer_execution=True)
    second = order(state, "buy_2")
    pending = port.submit_order(state, second, quotes(NOW + 1, 89, 90, 90), NOW + 1,
                                received_at=NOW + 0.5, defer_execution=True)
    assert [item["status"] for item in pending["ledger"]["orders"]] == ["pending", "pending"]
    assert pending["positions"] == {} and pending["ledger"]["fills"] == []
    assert pending["account"]["reservedCashCents"] == 180000
    assert pending["meta"]["executionTimestamps"] == {}
    settled = port.match_orders(pending, quotes(NOW + 2, 89, 90, 90), NOW + 2)
    assert [item["status"] for item in settled["ledger"]["orders"]] == ["filled", "filled"]
    assert settled["positions"]["AAPL"]["quantity"] == 20
    assert_balanced(settled)


@pytest.mark.parametrize("field", ["submittedTimestamp", "cancellationTimestamp", "expiresTimestamp"])
def test_corrupted_execution_timestamps_fail_closed_instead_of_crashing_migration(field):
    state = buy()
    state["ledger"]["orders"][0][field] = float("nan")
    with pytest.raises(port.PortError) as error:
        port.load_state(state)
    assert error.value.code == "invalid_portfolio"
