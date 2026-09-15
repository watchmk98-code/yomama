"""Seat-owned portfolios, authoritative execution, and persistence in SQLite."""
import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import game_api as A
import production_economy as E


@pytest.fixture
def port(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'port-test.db')
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A, 'economy', E)
    monkeypatch.setattr(A, '_startup_config', E.load_config())
    now = [2_000_000_000.0]
    monkeypatch.setattr(A.time, 'time', lambda: now[0])
    A._book_cache.clear()
    A.init_db()
    teacher = A.create_session({})
    pin = str(secrets.randbelow(10000)).zfill(4)
    seats = [A.join(dict(code=teacher['code'], name=name, pin=pin)) for name in ('ALICE', 'BOB')]
    for seat in seats:
        set_licence(seat, True)
    provider = {'status': 'open', 'bid': 99.99, 'ask': 100.01, 'age': 0.01, 'calls': 0}

    def snapshot(*_, **__):
        provider['calls'] += 1
        quotes = ({symbol: dict(bid=provider['bid'], ask=provider['ask'], price=100,
                                timestamp=now[0] - provider['age'])
                   for symbol in A.port_portfolio.ALLOWED_SYMBOLS}
                  if provider['status'] in ('open', 'closed') else {})
        return dict(quotes=quotes, market=dict(status=provider['status'], source='test_fixture',
                                               message='Test fixture quotes', asOf=now[0]))
    monkeypatch.setattr(A.alpaca_market, 'snapshot', snapshot)
    return now, teacher, seats, provider, pin


def set_licence(seat, licensed):
    with A.connect() as conn:
        player = A._player_by_token(conn, seat['token'])
        session = A._session_of(conn, player['code'])
        town = A._load_state(player, A.econ_config(session), session)
        town['licenceGrandfathered'] = licensed
        conn.execute('UPDATE players SET econ=? WHERE id=?', (json.dumps(town), player['id']))


def get(seat):
    # Advance one explicit server execution cycle before observing saved state.
    A.process_pending_portfolios()
    return A.port_state({'token': [seat['token']]})


def order(seat, state, **kw):
    return dict(token=seat['token'], accountId=state['portfolio']['accountId'],
                clientOrderId=secrets.token_hex(12), symbol='AAPL', side='buy',
                type='market', quantity=2, **kw)


def test_new_seat_is_empty_and_legacy_wallet_never_imported(port):
    _, _, seats, _, _ = port
    with A.connect() as conn:
        p = A._player_by_token(conn, seats[0]['token'])
        conn.execute('UPDATE players SET cash=123 WHERE id=?', (p['id'],))
        conn.execute('INSERT INTO positions VALUES (?,?,?,?)', (p['id'], 'AAPL', 50, 20))
    state = get(seats[0])
    account = state['portfolio']
    assert account['account']['availableCash'] == 100000
    assert account['positions'] == {}
    assert account['ledger']['orders'] == [] and account['ledger']['fills'] == []
    assert get(seats[1])['portfolio']['accountId'] != account['accountId']
    with A.connect() as conn:
        assert A._player_by_token(conn, seats[0]['token'])['cash'] == 123


def test_buy_sell_rejoin_restart_and_seat_isolation(port):
    now, teacher, seats, _, pin = port
    alice, bob = seats
    first = get(alice)
    request = order(alice, first)
    pending = A.port_order(request)
    assert pending['portfolio']['ledger']['orders'][-1]['status'] == 'pending'
    assert pending['portfolio']['positions'] == {}  # never fill a pre-click quote
    now[0] += 1
    bought = get(alice)['portfolio']
    assert bought['positions']['AAPL']['quantity'] == 2
    assert bought['account']['availableCash'] == pytest.approx(99799.98)
    assert len(bought['ledger']['fills']) == 1
    assert A.port_order(request)['portfolio']['ledger']['orders'] == bought['ledger']['orders']
    sell = order(alice, {'portfolio': bought})
    sell.update(side='sell', quantity=1)
    A.port_order(sell)
    now[0] += 1
    sold = get(alice)['portfolio']
    assert sold['positions']['AAPL']['quantity'] == 1
    assert sold['account']['availableCash'] == pytest.approx(99899.97)
    assert sold['account']['realizedPnl'] == pytest.approx(-0.02)
    A.init_db()  # existing schema and save survive server restart
    rejoin = A.join(dict(code=teacher['code'], name=alice['name'], pin=pin))
    again = get(rejoin)['portfolio']
    assert again == sold
    assert get(bob)['portfolio']['positions'] == {}
    assert get(bob)['portfolio']['account']['availableCash'] == 100000


def test_concurrent_duplicate_and_cash_reservations(port):
    now, _, seats, _, _ = port
    alice = seats[0]
    request = order(alice, get(alice))
    request['quantity'] = 800
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: A.port_order(dict(request)), range(2)))
    assert all(len(r['portfolio']['ledger']['orders']) == 1 for r in results)
    duplicate = dict(request, clientOrderId=secrets.token_hex(12))
    with pytest.raises(A.ApiError):
        A.port_order(duplicate)
    now[0] += 1
    result = get(alice)['portfolio']
    assert result['positions']['AAPL']['quantity'] == 800
    assert len(result['ledger']['fills']) == 1


def test_bogus_auth_never_calls_provider_and_foreign_account_is_rejected(port):
    _, _, seats, provider, _ = port
    for handler in (A.port_state, A.port_order, A.port_cancel):
        with pytest.raises(A.ApiError) as exc:
            handler({'token': 'invalid'})
        assert exc.value.status == 401
    assert provider['calls'] == 0
    request = order(seats[0], get(seats[1]))
    with pytest.raises(A.ApiError) as exc:
        A.port_order(request)
    assert exc.value.status == 409


def test_pause_and_revocation_still_block_licensed_port_trades(port):
    now, teacher, seats, _, _ = port
    request = order(seats[0], get(seats[0]))
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    assert not get(seats[0])['canTrade']
    with pytest.raises(A.ApiError):
        A.port_order(request)
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='resume'))
    assert get(seats[0])['canTrade']
    A.port_order(request)
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET active=0 WHERE code=?', (teacher['code'],))
    for handler in (A.port_state, A.port_order, A.port_cancel):
        with pytest.raises(A.ApiError) as exc:
            handler(request)
        assert exc.value.status == 403


@pytest.mark.parametrize('status', ['unconfigured', 'unavailable', 'closed'])
def test_feed_failure_preserves_progress_and_refuses_orders(port, status):
    _, _, seats, provider, _ = port
    state = get(seats[0])
    provider['status'] = status
    current = get(seats[0])
    assert current['portfolio'] == state['portfolio']
    assert not current['canTrade']
    with pytest.raises(A.ApiError):
        A.port_order(order(seats[0], state))


def test_reset_creates_new_empty_generation_without_recreating_seat(port):
    _, teacher, seats, _, _ = port
    initial = get(seats[0])
    request = order(seats[0], initial)
    A.port_order(request)
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='reset_player', name=seats[0]['name']))
    after = get(seats[0])['portfolio']
    assert after['accountId'] != initial['portfolio']['accountId']
    assert after['account']['availableCash'] == 100000 and not after['ledger']['orders']
    assert seats[0]['token']
    A.reset_class(teacher['code'])
    assert get(seats[0])['portfolio']['accountId'] != after['accountId']


def test_corrupt_server_save_is_not_replaced_with_starting_cash(port):
    _, _, seats, _, _ = port
    with A.connect() as conn:
        conn.execute('UPDATE players SET port_state=? WHERE token=?', ('broken', seats[0]['token']))
    with pytest.raises(A.ApiError):
        get(seats[0])
    with A.connect() as conn:
        assert A._player_by_token(conn, seats[0]['token'])['port_state'] == 'broken'


def saved_portfolio(seat):
    """Inspect persistence without triggering a page request or execution cycle."""
    with A.connect() as conn:
        return json.loads(A._player_by_token(conn, seat['token'])['port_state'])


def test_direct_get_and_new_post_cannot_choose_when_orders_fill(port):
    now, _, seats, provider, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    limit = order(alice, initial)
    limit.update(type='limit', limitPrice=90)
    A.port_order(limit)
    now[0] += 1
    provider.update(bid=89.99, ask=90)
    # The current quote crosses the existing order. Neither repeated GETs nor
    # another HTTP submission is allowed to select an execution tick.
    for _ in range(3):
        read = A.port_state({'token': alice['token']})
        assert read['portfolio']['ledger']['orders'][0]['status'] == 'pending'
    second = A.port_order(order(alice, read))
    assert [item['status'] for item in second['portfolio']['ledger']['orders']] == ['pending', 'pending']
    assert second['portfolio']['ledger']['fills'] == []
    assert second['portfolio']['positions'] == {}
    now[0] += 1
    assert A.process_pending_portfolios() == 1
    saved = saved_portfolio(alice)
    assert [item['status'] for item in saved['ledger']['orders']] == ['filled', 'filled']
    assert saved['positions']['AAPL']['quantity'] == 4


def test_market_expiry_is_settled_by_worker_instead_of_page_refresh(port):
    now, _, seats, _, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    A.port_order(order(alice, initial))
    now[0] += 30
    read = A.port_state({'token': alice['token']})
    assert read['portfolio']['ledger']['orders'][0]['status'] == 'pending'
    assert read['portfolio']['account']['reservedCash'] > 0
    A.process_pending_portfolios()
    saved = saved_portfolio(alice)
    assert saved['ledger']['orders'][0]['status'] == 'expired'
    assert saved['account']['availableCashCents'] == 10000000
    assert saved['account']['reservedCashCents'] == 0


def test_one_server_cycle_fills_offline_students_on_one_shared_feed(port):
    now, _, seats, provider, _ = port
    for seat in seats:
        initial = A.port_state({'token': seat['token']})
        A.port_order(order(seat, initial))
    calls_before = provider['calls']
    now[0] += 1
    # No page requests occur here; both saved accounts participate in the cycle.
    assert A.process_pending_portfolios() == 2
    assert provider['calls'] == calls_before + 1
    records = [saved_portfolio(seat) for seat in seats]
    assert all(state['positions']['AAPL']['quantity'] == 2 for state in records)
    assert records[0]['ledger']['fills'][0]['marketTimestamp'] == records[1]['ledger']['fills'][0]['marketTimestamp']
    assert records[0]['ledger']['fills'][0]['fillPriceCents'] == records[1]['ledger']['fills'][0]['fillPriceCents']


def test_background_stock_fill_does_not_renew_town_offline_activity_or_settle_town(port):
    now, _, seats, provider, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    request = order(alice, initial)
    request.update(type='limit', limitPrice=90)
    A.port_order(request)
    fields = ('econ', 'econ_meta', 'econ_nw', 'cash', 'buildings')
    with A.connect() as conn:
        row = A._player_by_token(conn, alice['token'])
        before = {field: row[field] for field in fields}
        previous_activity = json.loads(row['econ'])['lastActiveTick']
    now[0] += 3600
    provider.update(bid=89.99, ask=90)
    A.process_pending_portfolios()
    with A.connect() as conn:
        row = A._player_by_token(conn, alice['token'])
        after = {field: row[field] for field in fields}
        assert json.loads(row['econ'])['lastActiveTick'] == previous_activity
    assert after == before
    assert saved_portfolio(alice)['ledger']['orders'][0]['status'] == 'filled'


@pytest.mark.parametrize('quote_offset,expected', [(0.5, 'filled'), (1.5, 'canceled')])
def test_cancellation_persists_without_remote_call_and_worker_respects_receipt_order(port, monkeypatch, quote_offset, expected):
    now, _, seats, provider, _ = port
    alice = seats[0]
    started = now[0]
    initial = A.port_state({'token': alice['token']})
    request = order(alice, initial)
    request.update(type='limit', limitPrice=90)
    A.port_order(request)
    remote_snapshot = A.alpaca_market.snapshot
    calls_before = provider['calls']

    def forbidden_remote_call(*_, **__):
        raise AssertionError('Cancellation must be saved before any provider request.')

    monkeypatch.setattr(A.alpaca_market, 'snapshot', forbidden_remote_call)
    now[0] = started + 1
    response = A.port_cancel(dict(token=alice['token'], accountId=initial['portfolio']['accountId'],
                                  clientOrderId=secrets.token_hex(12), orderId=request['clientOrderId'],
                                  _server_received_at=started - 1000))
    assert provider['calls'] == calls_before
    assert response['portfolio']['ledger']['orders'][0]['status'] == 'pending'
    assert saved_portfolio(alice)['ledger']['orders'][0]['cancellationTimestamp'] == started + 1
    monkeypatch.setattr(A.alpaca_market, 'snapshot', remote_snapshot)
    now[0] = started + 2
    provider.update(bid=89.99, ask=90, age=2 - quote_offset)
    A.process_pending_portfolios()
    saved = saved_portfolio(alice)
    assert saved['ledger']['orders'][0]['status'] == expected
    assert saved['account']['reservedCashCents'] == 0


def test_server_receipt_precedes_provider_wait_and_overwrites_client_timestamp(port, monkeypatch):
    now, _, seats, _, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    started = now[0]
    remote_snapshot = A.alpaca_market.snapshot

    def slow_snapshot(*args, **kwargs):
        now[0] += 3
        return remote_snapshot(*args, **kwargs)

    monkeypatch.setattr(A.alpaca_market, 'snapshot', slow_snapshot)
    request = order(alice, initial)
    request.update(_server_received_at=started + 99999, received_at=started - 99999,
                   submittedTimestamp=started - 99999, expiresTimestamp=started + 99999)
    response = A.port_order(request)
    saved = saved_portfolio(alice)['ledger']['orders'][0]
    assert saved['receivedTimestamp'] == saved['submittedTimestamp'] == started
    assert saved['expiresTimestamp'] == started + 30
    assert A.alpaca_market.timestamp(saved['acceptedAt']) == started + 3
    assert response['portfolio']['ledger']['orders'][0]['status'] == 'pending'
    assert response['portfolio']['ledger']['fills'] == []


@pytest.mark.parametrize('change', ['pause', 'reset', 'revoke'])
def test_worker_rechecks_class_and_account_generation_after_provider_fetch(port, monkeypatch, change):
    now, teacher, seats, _, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    A.port_order(order(alice, initial))
    before = saved_portfolio(alice)
    remote_snapshot = A.alpaca_market.snapshot

    def changed_while_fetching(*args, **kwargs):
        if change == 'pause':
            A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
        elif change == 'reset':
            A.teacher(dict(teacher_token=teacher['teacher_token'], action='reset_player', name=alice['name']))
        else:
            with A.connect() as conn:
                conn.execute('UPDATE sessions SET active=0 WHERE code=?', (teacher['code'],))
        return remote_snapshot(*args, **kwargs)

    monkeypatch.setattr(A.alpaca_market, 'snapshot', changed_while_fetching)
    now[0] += 1
    A.process_pending_portfolios()
    if change == 'reset':
        with A.connect() as conn:
            assert A._player_by_token(conn, alice['token'])['port_state'] == ''
    else:
        assert saved_portfolio(alice) == before


def test_cancellation_admission_precedes_worker_settlement_while_cached_display_read_waits(port, monkeypatch):
    now, _, seats, provider, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    request = order(alice, initial)
    request.update(type='limit', limitPrice=90)
    A.port_order(request)
    cached_entered = threading.Event()
    release_cached = threading.Event()
    worker_fetched = threading.Event()
    worker_finished = threading.Event()
    failures = []
    remote_snapshot = A.alpaca_market.snapshot

    def delayed_cached(*_, **__):
        cached_entered.set()
        if not release_cached.wait(3):
            raise AssertionError('The test did not release its cancellation display-read barrier.')
        return dict(quotes={}, market=dict(status='unavailable', source='test_fixture',
                                          message='Display cache unavailable', asOf=now[0]))

    def observed_snapshot(*args, **kwargs):
        feed = remote_snapshot(*args, **kwargs)
        worker_fetched.set()
        return feed

    def submit_cancel():
        try:
            A.port_cancel(dict(token=alice['token'], accountId=initial['portfolio']['accountId'],
                               clientOrderId=secrets.token_hex(12), orderId=request['clientOrderId']))
        except BaseException as error:
            failures.append(error)

    def run_worker():
        try:
            A.process_pending_portfolios()
        except BaseException as error:
            failures.append(error)
        finally:
            worker_finished.set()

    monkeypatch.setattr(A.alpaca_market, 'cached_snapshot', delayed_cached)
    monkeypatch.setattr(A.alpaca_market, 'snapshot', observed_snapshot)
    now[0] += 1
    cancellation_thread = threading.Thread(target=submit_cancel, daemon=True)
    worker_thread = threading.Thread(target=run_worker, daemon=True)
    cancellation_thread.start()
    try:
        assert cached_entered.wait(2)
        now[0] += 1
        provider.update(bid=89.99, ask=90)
        worker_thread.start()
        assert worker_fetched.wait(2)
        # Give the worker a chance to reach settlement while cancellation is
        # admitted but its intent has not yet reached SQLite.
        assert not worker_finished.wait(0.2)
    finally:
        release_cached.set()
        cancellation_thread.join(timeout=3)
        if worker_thread.ident is not None:
            worker_thread.join(timeout=3)
    assert not cancellation_thread.is_alive() and not worker_thread.is_alive()
    assert not failures
    saved = saved_portfolio(alice)
    assert saved['ledger']['orders'][0]['status'] == 'canceled'
    assert saved['ledger']['fills'] == []
    assert saved['account']['availableCashCents'] == 10000000


def test_worker_fetches_new_prices_instead_of_reusing_a_browser_timed_display_cache(port, monkeypatch):
    now, _, seats, _, _ = port
    alice = seats[0]
    initial = A.port_state({'token': alice['token']})
    request = order(alice, initial)
    request.update(type='limit', limitPrice=90)
    A.port_order(request)
    now[0] += 2

    def cached_or_fresh(symbols, force=False):
        price = 101 if force else 89
        at = now[0] - (0.01 if force else 1)
        return dict(quotes={symbol: dict(bid=price, ask=price, price=price, timestamp=at)
                            for symbol in symbols},
                    market=dict(status='open', source='test_fixture',
                                message='Provider freshness fixture', asOf=now[0]))

    monkeypatch.setattr(A.alpaca_market, 'snapshot', cached_or_fresh)
    A.process_pending_portfolios()
    saved = saved_portfolio(alice)
    assert saved['ledger']['orders'][0]['status'] == 'pending'
    assert saved['positions'] == {} and saved['ledger']['fills'] == []
    assert saved['meta']['executionTimestamps']['AAPL'] == now[0] - 0.01


@pytest.fixture
def chart(port, monkeypatch):
    now, _, _, _, _ = port
    calls = []
    payload = {'source': 'alpaca_sip', 'status': 'ok', 'message': 'Historical prices.',
               'bars': [{'time': now[0] - 60, 'value': 101, 'open': 100,
                         'high': 102, 'low': 99, 'close': 101}],
               'asOf': now[0], 'adjustment': 'split', 'session': 'all_available'}

    def history(symbol, range_name):
        calls.append((symbol, range_name))
        return dict(payload, symbol=symbol, range=range_name,
                    timeframe=A.alpaca_market.CHART_RANGES[range_name][0])
    monkeypatch.setattr(A.alpaca_market, 'historical_chart', history)
    return calls, payload


@pytest.mark.parametrize('seat_kind', ['existing', 'future_class'])
def test_unlicensed_seats_can_view_port_but_cannot_trade_until_licensed(port, chart, seat_kind):
    now, _, seats, _, _ = port
    seat = seats[0]
    if seat_kind == 'future_class':
        teacher = A.create_session({})
        seat = A.join(dict(code=teacher['code'], name='NEW STUDENT',
                           pin=str(secrets.randbelow(10000)).zfill(4)))
    set_licence(seat, False)
    initial = A.port_state({'token': seat['token']})
    assert initial['canTrade'] is False
    assert 'licence' in initial['blockedReason']
    assert A.port_chart({'token': seat['token'], 'symbol': 'AAPL', 'range': '1D'})['status'] == 'ok'
    with pytest.raises(A.ApiError, match='licence'):
        A.port_order(order(seat, initial))
    set_licence(seat, True)
    assert get(seat)['canTrade'] is True
    A.port_order(order(seat, initial))
    set_licence(seat, False)
    now[0] += 1
    A.process_pending_portfolios()
    assert saved_portfolio(seat)['positions'] == {}
    set_licence(seat, True)
    now[0] += 1
    A.process_pending_portfolios()
    assert saved_portfolio(seat)['positions']['AAPL']['quantity'] == 2


@pytest.mark.parametrize('range_name,timeframe', [('1d', '1Min'), ('3m', '4Hour'), ('5y', '1Week')])
def test_chart_is_authenticated_and_exposes_true_provider_ohlc_without_account_mutation(port, chart, range_name, timeframe):
    _, _, seats, _, _ = port
    calls, _ = chart
    response = A.port_chart({'token': [seats[0]['token']], 'symbol': ['nvda'], 'range': [range_name]})
    assert calls == [('NVDA', range_name.upper())]
    assert response['symbol'] == 'NVDA' and response['timeframe'] == timeframe
    assert response['bars'][0]['open'] == 100 and response['bars'][0]['value'] == 101
    assert response['source'] == 'alpaca_sip'
    with A.connect() as conn:
        assert A._player_by_token(conn, seats[0]['token'])['port_state'] == ''


def test_bogus_chart_auth_never_calls_provider(port, chart):
    calls, _ = chart
    with pytest.raises(A.ApiError) as error:
        A.port_chart({'token': 'invalid', 'symbol': 'AAPL', 'range': '1D'})
    assert error.value.status == 401
    assert calls == []


@pytest.mark.parametrize('fields', [{'symbol': 'NOTREAL'}, {'range': '10Y'},
                                  {'symbol': ['AAPL', 'MSFT']}, {'range': []},
                                  {'symbol': 1}, {'range': {'type': '1D'}}])
def test_chart_rejects_unknown_stocks_and_ranges_without_network(port, chart, fields):
    _, _, seats, _, _ = port
    calls, _ = chart
    with pytest.raises(A.ApiError) as error:
        A.port_chart(dict(token=seats[0]['token'], **fields))
    assert error.value.status == 400
    assert not calls


def test_unlicensed_chart_remains_readable_while_class_is_paused(port, chart):
    _, teacher, seats, _, _ = port
    calls, _ = chart
    set_licence(seats[0], False)
    query = {'token': seats[0]['token'], 'symbol': 'AAPL', 'range': '1W'}
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    assert A.port_chart(query)['status'] == 'ok'
    assert len(calls) == 1
    with A.connect() as conn:
        player = A._player_by_token(conn, seats[0]['token'])
        session = A._session_of(conn, player['code'])
        cfg = A.econ_config(session)
        town = A._load_state(player, cfg, session)
        assert not E.gate_open(cfg, town)


def test_chart_rechecks_class_access_after_remote_request(port, chart, monkeypatch):
    _, teacher, seats, _, _ = port
    _, payload = chart

    def revoke(*_):
        with A.connect() as conn:
            conn.execute('UPDATE sessions SET active=0 WHERE code=?', (teacher['code'],))
        return payload
    monkeypatch.setattr(A.alpaca_market, 'historical_chart', revoke)
    with pytest.raises(A.ApiError) as error:
        A.port_chart({'token': seats[0]['token']})
    assert error.value.status == 403


def test_chart_remote_request_holds_no_class_or_database_lock(port, chart, monkeypatch):
    _, teacher, seats, _, _ = port
    _, payload = chart
    completed = []
    failures = []
    workers = []

    def history(*_):
        done = threading.Event()
        def pause():
            try:
                A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
            except BaseException as error:
                failures.append(error)
            finally:
                done.set()
        worker = threading.Thread(target=pause, daemon=True)
        workers.append(worker)
        worker.start()
        completed.append(done.wait(2))
        return payload
    monkeypatch.setattr(A.alpaca_market, 'historical_chart', history)
    assert A.port_chart({'token': seats[0]['token']})['status'] == 'ok'
    for worker in workers:
        worker.join(timeout=3)
    assert not failures and completed == [True]


def test_chart_unavailable_response_does_not_accept_injected_browser_prices(port, chart):
    _, _, seats, _, _ = port
    _, payload = chart
    payload.update(status='unconfigured', message='Market data is not connected yet.', bars=[])
    result = A.port_chart({'token': seats[0]['token'], '_server_port_chart': {
        'source': 'fake', 'status': 'ok', 'bars': [{'time': 1, 'value': 99999}]}})
    assert result['status'] == 'unconfigured'
    assert result['bars'] == [] and result['source'] == 'alpaca_sip'
