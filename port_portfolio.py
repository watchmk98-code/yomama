"""Seat-owned virtual PORT accounts. No network, browser state or brokerage orders.

Persistence uses integer cents. Public responses retain the paper terminal's
dollar fields so its rendering helpers can display server-owned accounts.
All transitions return copies; callers persist them inside their seat/class lock.
"""
from __future__ import annotations

import copy
import json
import math
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP


ALLOWED_SYMBOLS = (
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "AMD", "META", "TSLA",
    "AVGO", "ADBE", "NFLX", "INTC", "CSCO", "QCOM", "AMAT", "MU",
    "TXN", "BKNG", "PDD", "INTU",
)
STARTING_CASH_CENTS = 10_000_000
MAX_QUOTE_AGE_SECONDS = 10.0
MARKET_ORDER_TIMEOUT_SECONDS = 30.0
MAX_OPEN_ORDERS = 100
MAX_QUANTITY = 1_000_000
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class PortError(Exception):
    def __init__(self, status, message, code="invalid_order"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def _now(value):
    value = time.time() if value is None else value
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("now must be a finite Unix timestamp")
    return float(value)


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _cents(value, rounding=ROUND_HALF_UP):
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("price must be positive")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number > 1_000_000:
            raise ValueError("price must be positive and at most $1,000,000")
        result = int((number * 100).quantize(Decimal("1"), rounding=rounding))
        if result < 1:
            raise ValueError("price must be at least one cent")
        return result
    except InvalidOperation:
        raise ValueError("price must be positive")


def new_state(now=None, account_id=None):
    stamp = _iso(_now(now))
    return {
        "version": 1,
        "accountId": account_id or uuid.uuid4().hex,
        "account": {
            "startingCashCents": STARTING_CASH_CENTS,
            "availableCashCents": STARTING_CASH_CENTS,
            "reservedCashCents": 0,
            "realizedPnlCents": 0,
        },
        "positions": {},
        "ledger": {
            "orders": [], "fills": [],
            "cashEvents": [{"type": "starting_cash", "amountCents": STARTING_CASH_CENTS, "createdAt": stamp}],
        },
        "requests": {},
        "meta": {"createdAt": stamp, "updatedAt": stamp, "revision": 0,
                 "executionTimestamps": {}},
    }


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _valid_timestamp(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and
            0 <= value < 253402300800 and math.isfinite(value))


def _validate_state(state):
    """Reject malformed saves rather than silently replacing student progress."""
    try:
        if not isinstance(state, dict) or state["version"] != 1 or not isinstance(state["accountId"], str) or not state["accountId"]:
            raise ValueError("Invalid account identity")
        account = state["account"]
        for key in ("startingCashCents", "availableCashCents", "reservedCashCents"):
            if not _integer(account[key]):
                raise ValueError("Invalid account balance")
        if type(account["realizedPnlCents"]) is not int:
            raise ValueError("Invalid realized P&L")
        positions = state["positions"]
        ledger = state["ledger"]
        if not isinstance(positions, dict) or not isinstance(state["requests"], dict):
            raise ValueError("Invalid account records")
        if not all(isinstance(ledger[key], list) for key in ("orders", "fills", "cashEvents")):
            raise ValueError("Invalid ledger")
        if not _integer(state["meta"]["revision"]):
            raise ValueError("Invalid revision")
        watermarks = state["meta"].get("executionTimestamps", {})
        if not isinstance(watermarks, dict) or any(
                symbol not in ALLOWED_SYMBOLS or not _valid_timestamp(stamp)
                for symbol, stamp in watermarks.items()):
            raise ValueError("Invalid execution timestamps")
        for symbol, position in positions.items():
            if symbol not in ALLOWED_SYMBOLS or not _integer(position["quantity"], 1) or not _integer(position["totalCostCents"], 1) or not _integer(position["marketPriceCents"], 1):
                raise ValueError("Invalid holding")
        reserved = 0
        reserved_shares = {}
        ids = set()
        for order in ledger["orders"]:
            if order["id"] in ids or order["symbol"] not in ALLOWED_SYMBOLS or order["side"] not in ("buy", "sell") or order["type"] not in ("market", "limit") or not _integer(order["quantity"], 1):
                raise ValueError("Invalid order")
            ids.add(order["id"])
            if order["status"] not in ("pending", "filled", "canceled", "rejected", "expired") or not _integer(order["reservedAmountCents"]):
                raise ValueError("Invalid order status")
            if not _valid_timestamp(order["submittedTimestamp"]) or any(
                    key in order and not _valid_timestamp(order[key])
                    for key in ("receivedTimestamp", "cancellationTimestamp", "expiresTimestamp")):
                raise ValueError("Invalid order timestamp")
            if order["status"] == "pending":
                reserved += order["reservedAmountCents"]
                if order["side"] == "sell":
                    reserved_shares[order["symbol"]] = reserved_shares.get(order["symbol"], 0) + order["quantity"]
            elif order["reservedAmountCents"]:
                raise ValueError("Finished order retains a reservation")
        if reserved != account["reservedCashCents"]:
            raise ValueError("Invalid cash reservations")
        if any(quantity > positions.get(symbol, {}).get("quantity", 0) for symbol, quantity in reserved_shares.items()):
            raise ValueError("Invalid share reservations")
        # Cost-basis conservation catches accidental money creation and loss.
        assets = account["availableCashCents"] + account["reservedCashCents"] + sum(p["totalCostCents"] for p in positions.values())
        if assets != account["startingCashCents"] + account["realizedPnlCents"]:
            raise ValueError("Portfolio accounting does not balance")
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PortError(503, "Your saved PORT account could not be read. No progress was replaced.", "invalid_portfolio")


def load_state(raw, now=None):
    if raw is None or raw == "":
        return new_state(now)
    try:
        state = json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    except (ValueError, TypeError):
        raise PortError(503, "Your saved PORT account could not be read. No progress was replaced.", "invalid_portfolio")
    _validate_state(state)
    _migrate_execution_fields(state)
    return state


def _migrate_execution_fields(state):
    """Add execution metadata to existing version-one saves without resetting them."""
    state["meta"].setdefault("executionTimestamps", {})
    for order in state["ledger"]["orders"]:
        received = order["submittedTimestamp"]
        order.setdefault("receivedTimestamp", received)
        order.setdefault("receivedAt", _iso(received))
        if order["type"] == "market":
            deadline = order.setdefault("expiresTimestamp", received + MARKET_ORDER_TIMEOUT_SECONDS)
            order.setdefault("expiresAt", _iso(deadline))


def execution_rules(server_poll_seconds=2):
    """Public rules for the terminal; prices and deadlines use real UTC time."""
    return {
        "clock": "real_time", "timeZone": "America/New_York", "session": "regular",
        "regularOpen": "09:30", "regularClose": "16:00", "calendar": "alpaca",
        "holidaysAndEarlyCloses": True,
        "serverPollSeconds": server_poll_seconds,
        "matching": "server_poll", "pollIntervalSeconds": server_poll_seconds,
        "timezone": "America/New_York",
        "maxQuoteAgeSeconds": MAX_QUOTE_AGE_SECONDS,
        "marketOrderTimeoutSeconds": MARKET_ORDER_TIMEOUT_SECONDS,
        "marketOrdersExpireAtClose": True, "limitTimeInForce": "gtc",
        "buyPrice": "ask", "sellPrice": "bid", "wholeSharesOnly": True,
        "shortSelling": False, "ordersContinueOffline": True,
        "pauseStopsFills": True, "deadlinesContinueDuringPause": True,
        "resumeRequiresFreshQuote": True,
        "execution": "first_observed_eligible_quote_after_receipt",
        "cancellation": "receipt_time_ordered_with_market_events",
    }


def _fresh_quote(quote, now):
    if not isinstance(quote, dict):
        return None
    stamp = quote.get("timestamp")
    if isinstance(stamp, bool) or not isinstance(stamp, (float, int)) or stamp < 0 or stamp > now or not math.isfinite(stamp) or now - stamp > MAX_QUOTE_AGE_SECONDS:
        return None
    try:
        if Decimal(str(quote.get("bid"))) > Decimal(str(quote.get("ask"))):
            return None
        bid = _cents(quote.get("bid"), ROUND_FLOOR)
        ask = _cents(quote.get("ask"), ROUND_CEILING)
        try:
            mark = _cents(quote.get("price"))
        except ValueError:
            mark = (bid + ask + 1) // 2
    except (ValueError, TypeError, InvalidOperation):
        return None
    return {"bid": bid, "ask": ask, "price": mark, "timestamp": float(stamp)}


def _request(state, body, action, fingerprint):
    if not isinstance(body, dict) or body.get("accountId") != state["accountId"]:
        raise PortError(409, "Your PORT account changed. Refresh before placing another order.", "account_changed")
    request_id = body.get("clientOrderId")
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise PortError(400, "A valid clientOrderId is required.", "invalid_request_id")
    previous = state["requests"].get(request_id)
    record = {"action": action, "fingerprint": fingerprint}
    if previous is not None and previous != record:
        raise PortError(409, "This request ID was already used for a different order.", "idempotency_conflict")
    return request_id, record, previous is not None


def _normalize_order(body):
    if not isinstance(body, dict):
        raise PortError(400, "An order is required.")
    symbol = body.get("symbol")
    if not isinstance(symbol, str) or symbol.strip().upper() not in ALLOWED_SYMBOLS:
        raise PortError(400, "Choose a stock from the PORT watchlist.", "invalid_symbol")
    side, order_type = body.get("side"), body.get("type")
    if side not in ("buy", "sell") or order_type not in ("market", "limit"):
        raise PortError(400, "Choose buy or sell and market or limit.")
    quantity = body.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not 1 <= quantity <= MAX_QUANTITY or not math.isfinite(quantity) or quantity != int(quantity):
        raise PortError(400, "Shares must be a positive whole number.", "invalid_quantity")
    limit = None
    if order_type == "limit":
        try:
            limit = _cents(body.get("limitPrice"))
            if Decimal(str(body.get("limitPrice"))) * 100 != limit:
                raise ValueError("Limit must use cents")
        except (ValueError, InvalidOperation):
            raise PortError(400, "Enter a positive limit price with at most two decimal places.", "invalid_limit")
    return {"symbol": symbol.strip().upper(), "side": side, "type": order_type, "quantity": int(quantity), "limitPriceCents": limit}


def _touch(state, now):
    state["meta"]["revision"] += 1
    state["meta"]["updatedAt"] = _iso(now)


def _event(state, order, event_type, amount, now):
    state["ledger"]["cashEvents"].append({"type": event_type, "orderId": order["id"], "amountCents": amount, "createdAt": _iso(now)})


def _release(state, order, now):
    reserved = order["reservedAmountCents"]
    if reserved:
        state["account"]["reservedCashCents"] -= reserved
        state["account"]["availableCashCents"] += reserved
        _event(state, order, "cash_released", reserved, now)
        order["reservedAmountCents"] = 0


def _finish(state, order, status, now, reason=None):
    _release(state, order, now)
    order["status"] = status
    order["updatedAt"] = _iso(now)
    if status == "canceled":
        order["canceledAt"] = _iso(now)
    if reason:
        order["reason"] = reason


def _fill(state, order, quote, now):
    account = state["account"]
    symbol, quantity = order["symbol"], order["quantity"]
    price = quote["ask"] if order["side"] == "buy" else quote["bid"]
    amount = quantity * price
    position = state["positions"].get(symbol)
    realized = 0
    if order["side"] == "buy":
        if amount > account["availableCashCents"] + order["reservedAmountCents"]:
            _finish(state, order, "rejected", now, "The new market price exceeds available cash.")
            return
        _release(state, order, now)
        account["availableCashCents"] -= amount
        if position is None:
            position = {"quantity": 0, "totalCostCents": 0, "openedAt": _iso(now)}
            state["positions"][symbol] = position
        position["quantity"] += quantity
        position["totalCostCents"] += amount
        _event(state, order, "buy_fill", -amount, now)
    else:
        # Pending sells reserve shares; prior validated transitions preserve this.
        if position is None or position["quantity"] < quantity:
            _finish(state, order, "rejected", now, "The shares are no longer available.")
            return
        basis = (2 * position["totalCostCents"] * quantity + position["quantity"]) // (2 * position["quantity"])
        realized = amount - basis
        account["availableCashCents"] += amount
        account["realizedPnlCents"] += realized
        position["quantity"] -= quantity
        position["totalCostCents"] -= basis
        _event(state, order, "sell_fill", amount, now)
        if position["quantity"] == 0:
            del state["positions"][symbol]
    if position["quantity"]:
        position.update({"marketPriceCents": quote["price"], "updatedAt": _iso(now), "lastMarkedAt": _iso(quote["timestamp"]), "lastMarkedTimestamp": quote["timestamp"]})
    order.update({"status": "filled", "filledAt": _iso(now), "updatedAt": _iso(now), "fillPriceCents": price, "reservedAmountCents": 0})
    state["ledger"]["fills"].append({
        "id": "fill_" + order["id"], "orderId": order["id"], "symbol": symbol,
        "side": order["side"], "quantity": quantity, "fillPriceCents": price,
        "grossAmountCents": amount, "realizedPnlCents": realized,
        "createdAt": _iso(now), "marketTimestamp": quote["timestamp"],
    })


def _match(state, quotes, now, market_open, session_open=None, session_close=None, resume_at=None):
    quotes = quotes if isinstance(quotes, dict) else {}
    _migrate_execution_fields(state)
    watermarks = state["meta"]["executionTimestamps"]
    eligible = {}
    # One accepted snapshot can serve all pending orders for that symbol. Record
    # its timestamp after evaluating the orders, including non-crossing limits.
    if market_open is True:
        lower_bound = max(value for value in (session_open, resume_at, 0) if value is not None)
        for symbol, raw in quotes.items():
            if symbol not in ALLOWED_SYMBOLS:
                continue
            quote = _fresh_quote(raw, now)
            if quote and quote["timestamp"] >= max(lower_bound, watermarks.get(symbol, 0)) and (
                    session_close is None or quote["timestamp"] < session_close):
                eligible[symbol] = quote
    for order in state["ledger"]["orders"]:
        if order["status"] != "pending":
            continue
        quote = eligible.get(order["symbol"])
        cancel_at = order.get("cancellationTimestamp")
        if order["type"] == "market" and (now >= order["expiresTimestamp"] or market_open is False):
            _finish(state, order, "expired", now, "No eligible fresh price arrived in time. Please submit again.")
            continue
        if cancel_at is not None and (market_open is False or (quote and quote["timestamp"] >= cancel_at)):
            _finish(state, order, "canceled", now)
            continue
        if market_open is not True or quote is None or quote["timestamp"] < order["submittedTimestamp"]:
            continue
        price = quote["ask"] if order["side"] == "buy" else quote["bid"]
        if order["type"] == "limit" and ((order["side"] == "buy" and price > order["limitPriceCents"]) or (order["side"] == "sell" and price < order["limitPriceCents"])):
            continue
        _fill(state, order, quote, now)
    for symbol, position in state["positions"].items():
        quote = eligible.get(symbol)
        if quote and quote["timestamp"] >= position.get("lastMarkedTimestamp", 0):
            position.update({"marketPriceCents": quote["price"], "lastMarkedAt": _iso(quote["timestamp"]), "lastMarkedTimestamp": quote["timestamp"]})
    for symbol, quote in eligible.items():
        watermarks[symbol] = quote["timestamp"]


def match_orders(state, quotes, now=None, market_open=True, *, session_open=None, session_close=None, resume_at=None):
    """Process only fresh, post-submission events while the exchange is open."""
    now = _now(now)
    _validate_state(state)
    result = copy.deepcopy(state)
    _match(result, quotes, now, market_open, session_open, session_close, resume_at)
    if result != state:
        _touch(result, now)
    _validate_state(result)
    return result


def submit_order(state, body, quotes, now=None, market_open=True, *, received_at=None,
                 session_open=None, session_close=None, resume_at=None, defer_execution=False):
    now = _now(now)
    _validate_state(state)
    normalized = _normalize_order(body)
    request_id, record, replay = _request(state, body, "submit", normalized)
    if replay:
        return copy.deepcopy(state)
    received_at = now if received_at is None else _now(received_at)
    if received_at > now:
        raise PortError(400, "The order receipt time is invalid.", "invalid_receipt")
    if market_open is False or (session_open is not None and received_at < session_open) or (
            session_close is not None and (received_at >= session_close or now >= session_close)):
        raise PortError(409, "The stock market is closed. Place orders during regular market hours.", "market_closed")
    if market_open is not True:
        raise PortError(503, "The market status is temporarily unavailable. Please try again shortly.", "market_unavailable")
    quote = _fresh_quote((quotes or {}).get(normalized["symbol"]), now)
    if quote is None:
        raise PortError(503, "A fresh market quote is not available. Please try again shortly.", "quote_unavailable")
    result = copy.deepcopy(state)
    _migrate_execution_fields(result)
    if not defer_execution:
        _match(result, quotes, now, market_open, session_open, session_close, resume_at)
    pending = [order for order in result["ledger"]["orders"] if order["status"] == "pending"]
    if len(pending) >= MAX_OPEN_ORDERS:
        raise PortError(409, "Cancel an open order before placing another.", "too_many_orders")
    reference = quote["ask"] if normalized["side"] == "buy" else quote["bid"]
    reservation = 0
    if normalized["side"] == "buy":
        reservation = normalized["quantity"] * (normalized["limitPriceCents"] if normalized["type"] == "limit" else reference)
        if reservation > result["account"]["availableCashCents"]:
            raise PortError(409, "Not enough available PORT cash for this order.", "insufficient_cash")
    else:
        reserved_shares = sum(order["quantity"] for order in pending if order["side"] == "sell" and order["symbol"] == normalized["symbol"])
        held = result["positions"].get(normalized["symbol"], {}).get("quantity", 0)
        if normalized["quantity"] > held - reserved_shares:
            raise PortError(409, "Not enough unreserved shares for this sell order.", "insufficient_shares")
    order = dict(normalized, id=request_id, status="pending", referencePriceCents=reference,
                 reservedAmountCents=reservation, createdAt=_iso(received_at), submittedAt=_iso(received_at),
                 submittedTimestamp=received_at, receivedTimestamp=received_at,
                 receivedAt=_iso(received_at), acceptedAt=_iso(now), updatedAt=_iso(now), session="regular",
                 timeInForce="gtc" if normalized["type"] == "limit" else "day")
    if normalized["type"] == "market":
        deadline = received_at + MARKET_ORDER_TIMEOUT_SECONDS
        if session_close is not None:
            deadline = min(deadline, session_close)
        order.update(expiresTimestamp=deadline, expiresAt=_iso(deadline))
    result["account"]["availableCashCents"] -= reservation
    result["account"]["reservedCashCents"] += reservation
    result["ledger"]["orders"].append(order)
    result["requests"][request_id] = record
    if reservation:
        _event(result, order, "cash_reserved", reservation, now)
    if not defer_execution:
        _match(result, quotes, now, market_open, session_open, session_close, resume_at)
    _touch(result, now)
    _validate_state(result)
    return result


def cancel_order(state, body, quotes, now=None, market_open=True, *, received_at=None,
                 session_open=None, session_close=None, resume_at=None):
    now = _now(now)
    _validate_state(state)
    order_id = body.get("orderId") if isinstance(body, dict) else None
    if not isinstance(order_id, str) or not _REQUEST_ID.fullmatch(order_id):
        raise PortError(400, "A valid orderId is required.")
    request_id, record, replay = _request(state, body, "cancel", {"orderId": order_id})
    if replay:
        return copy.deepcopy(state)
    received_at = now if received_at is None else _now(received_at)
    if received_at > now:
        raise PortError(400, "The cancellation receipt time is invalid.", "invalid_receipt")
    result = copy.deepcopy(state)
    order = next((item for item in result["ledger"]["orders"] if item["id"] == order_id), None)
    if order is None:
        raise PortError(404, "That order does not belong to this PORT account.", "order_not_found")
    if order["status"] != "pending":
        raise PortError(409, "That order has already finished.", "order_finished")
    # Until an event reaches this timestamp, an earlier eligible fill wins.
    if "cancellationTimestamp" not in order:
        order["cancellationTimestamp"] = received_at
        order["cancellationRequestedAt"] = _iso(received_at)
        order["cancellationAcceptedAt"] = _iso(now)
    result["requests"][request_id] = record
    _match(result, quotes, now, market_open, session_open, session_close, resume_at)
    _touch(result, now)
    _validate_state(result)
    return result


def public_state(state):
    """Convert persisted cents into the terminal's read-only dollar view."""
    _validate_state(state)
    result = {"version": "server-port-1", "accountId": state["accountId"], "account": {},
              "positions": {}, "ledger": {}, "meta": copy.deepcopy(state["meta"])}
    result["account"] = {key[:-5]: value / 100 for key, value in state["account"].items()}
    for symbol, holding in state["positions"].items():
        quantity = holding["quantity"]
        total = holding["totalCostCents"]
        market = holding["marketPriceCents"] * quantity
        reserved = sum(order["quantity"] for order in state["ledger"]["orders"] if order["status"] == "pending" and order["side"] == "sell" and order["symbol"] == symbol)
        result["positions"][symbol] = {
            "symbol": symbol, "quantity": quantity, "reservedQuantity": reserved,
            "availableQuantity": quantity - reserved, "totalCost": total / 100,
            "avgCost": total / quantity / 100, "marketPrice": holding["marketPriceCents"] / 100,
            "marketValue": market / 100, "unrealizedPnl": (market - total) / 100,
            "openedAt": holding["openedAt"], "updatedAt": holding["updatedAt"],
            "lastMarkedAt": holding.get("lastMarkedAt"),
        }
    for key in ("orders", "fills", "cashEvents"):
        result["ledger"][key] = []
        for record in state["ledger"][key]:
            public = {}
            for field, value in record.items():
                if field.endswith("Cents"):
                    public[field[:-5]] = None if value is None else value / 100
                elif field not in ("submittedTimestamp", "cancellationTimestamp"):
                    public[field] = copy.deepcopy(value)
            result["ledger"][key].append(public)
    return result
