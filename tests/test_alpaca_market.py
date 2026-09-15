"""Provider boundaries use mocked responses, never a funded Alpaca account."""
import copy
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
import alpaca_market as M


@pytest.fixture
def feed(monkeypatch):
    monkeypatch.setenv('APCA_API_KEY_ID', 'test-only-key')
    monkeypatch.setenv('APCA_API_SECRET_KEY', 'test-only-secret')
    monkeypatch.delenv('APCA_API_BASE_URL', raising=False)
    now = [M.timestamp('2026-09-15T14:00:00Z')]
    monkeypatch.setattr(M.time, 'time', lambda: now[0])
    M._cache.clear()
    M._calendar_cache.clear()
    M._chart_cache.clear()
    calls = []
    values = {'open': True, 'bid': 100.01, 'ask': 100.03, 'age': 0}

    def request(url, headers):
        calls.append(url)
        iso = datetime.fromtimestamp(now[0], timezone.utc).isoformat()
        if url.endswith('/clock'):
            return {'is_open': values['open'], 'timestamp': iso}
        if '/calendar?' in url:
            day = datetime.fromtimestamp(now[0], M._new_york).date().isoformat()
            return [{'date': day, 'open': '09:30', 'close': '16:00'}]
        at = datetime.fromtimestamp(now[0] - values['age'], timezone.utc).isoformat()
        return {'quotes': {'AAPL': {'bp': values['bid'], 'ap': values['ask'], 't': at}}}
    monkeypatch.setattr(M, '_request', request)
    return now, calls, values


def test_sip_only_batched_and_cached_with_immutable_response(feed):
    now, calls, _ = feed
    first = M.snapshot(['MSFT', 'AAPL'])
    assert first['market']['status'] == 'open'
    assert first['quotes']['AAPL']['price'] == pytest.approx(100.02)
    assert calls[0] == 'https://paper-api.alpaca.markets/v2/clock'
    assert '/calendar?' in calls[1]
    assert 'feed=sip' in calls[2] and 'symbols=AAPL%2CMSFT' in calls[2]
    first['quotes']['AAPL']['ask'] = 1
    assert M.snapshot(['AAPL', 'MSFT'])['quotes']['AAPL']['ask'] == 100.03
    assert len(calls) == 3
    now[0] += 3
    M.snapshot(['AAPL', 'MSFT'])
    assert len(calls) == 5


def test_no_credentials_means_no_prices_or_provider_calls(feed, monkeypatch):
    _, calls, _ = feed
    monkeypatch.delenv('APCA_API_SECRET_KEY')
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'unconfigured'
    assert result['quotes'] == {} and not calls


def test_clock_host_cannot_redirect_credentials_to_custom_server(feed, monkeypatch):
    _, calls, _ = feed
    monkeypatch.setenv('APCA_API_BASE_URL', 'https://example.invalid')
    assert M.snapshot(['AAPL'])['market']['status'] == 'unconfigured'
    assert not calls


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1, 0])
def test_bad_quotes_are_excluded(feed, bad):
    _, _, values = feed
    values['bid'] = bad
    assert M.snapshot(['AAPL'])['quotes'] == {}


def test_crossed_quotes_and_future_quotes_are_excluded(feed):
    _, _, values = feed
    values['bid'] = 101
    assert M.snapshot(['AAPL'])['quotes'] == {}
    values.update(bid=100, age=-20)
    assert M.snapshot(['AAPL'], force=True)['quotes'] == {}


def test_closed_market_still_has_display_quotes(feed):
    _, _, values = feed
    values['open'] = False
    values['age'] = 3600
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'closed'
    assert result['quotes']['AAPL']['timestamp'] == M.timestamp('2026-09-15T14:00:00Z') - 3600


@pytest.mark.parametrize('error', [URLError('secret-provider-detail'),
                                  HTTPError('secret-url', 403, 'secret', {}, None)],
                         ids=['network', 'forbidden'])
def test_provider_errors_never_leak_details_or_fallback_prices(feed, monkeypatch, error):
    def fail(*_):
        raise error
    monkeypatch.setattr(M, '_request', fail)
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'unavailable' and not result['quotes']
    assert 'secret' not in str(result)


def test_nanosecond_timestamp_and_missing_timezone():
    assert M.timestamp('2026-09-15T14:00:00.123456789Z') == pytest.approx(
        datetime(2026, 9, 15, 14, 0, 0, 123456, timezone.utc).timestamp())
    with pytest.raises(ValueError):
        M.timestamp('2026-09-15T14:00:00')


def history_bar(at, close=101, **changes):
    row = {'t': at, 'o': close - 0.5, 'h': close + 1, 'l': close - 1, 'c': close, 'v': 1000}
    row.update(changes)
    return row


@pytest.fixture
def history(feed, monkeypatch):
    now, _, _ = feed
    now[0] = M.timestamp('2026-09-13T12:00:00Z')  # Sunday, market is closed.
    calls = []
    replies = [{'bars': {'AAPL': [history_bar('2026-09-10T19:55:00Z'),
                                history_bar('2026-09-11T19:55:00Z', 102),
                                history_bar('2026-09-12T00:00:00Z', 103)]},
                'next_page_token': None}]

    def request(url, headers, **_):
        calls.append(url)
        return copy.deepcopy(replies[min(len(calls) - 1, len(replies) - 1)])

    monkeypatch.setattr(M, '_request', request)
    return now, calls, replies


def test_history_uses_true_sip_ohlc_and_latest_new_york_day_on_weekend(history):
    _, calls, _ = history
    result = M.historical_chart('AAPL', '1D')
    assert result['status'] == 'ok'
    assert result['source'] == 'alpaca_sip'
    assert result['timeframe'] == '1Min'
    assert result['adjustment'] == 'split'
    assert result['session'] == 'all_available'
    # Saturday UTC midnight still belongs to Friday in New York.
    assert [bar['value'] for bar in result['bars']] == [102, 103]
    assert result['bars'][0] == {'time': M.timestamp('2026-09-11T19:55:00Z'),
                                'value': 102, 'open': 101.5, 'high': 103, 'low': 101,
                                'close': 102, 'volume': 1000}
    query = parse_qs(urlsplit(calls[0]).query)
    assert urlsplit(calls[0]).path == '/v2/stocks/bars'
    assert query['feed'] == ['sip'] and query['symbols'] == ['AAPL']
    assert query['adjustment'] == ['split'] and query['timeframe'] == ['1Min']


@pytest.mark.parametrize('range_name,timeframe,days', [
    ('1D', '1Min', 7), ('1W', '30Min', 7), ('1M', '1Hour', 31),
    ('3M', '4Hour', 91), ('1Y', '1Day', 366), ('5Y', '1Week', 1827)])
def test_history_ranges_are_bounded_and_use_correct_aggregation(history, range_name, timeframe, days):
    now, calls, _ = history
    M.historical_chart('AAPL', range_name)
    query = parse_qs(urlsplit(calls[0]).query)
    assert query['timeframe'] == [timeframe]
    assert M.timestamp(query['start'][0]) == now[0] - days * 86400
    assert M.timestamp(query['end'][0]) == now[0]
    assert query['limit'] == ['10000']


@pytest.mark.parametrize('range_name,cache_seconds', [('1W', 30), ('3M', 60), ('5Y', 60)])
def test_history_cache_is_immutable_and_expires(history, range_name, cache_seconds):
    now, calls, _ = history
    first = M.historical_chart('AAPL', range_name)
    first['bars'][0]['value'] = 1
    now[0] += cache_seconds - 1
    second = M.historical_chart('AAPL', range_name)
    assert second['bars'][0]['value'] == 101
    assert len(calls) == 1
    now[0] += 1
    M.historical_chart('AAPL', range_name)
    assert len(calls) == 2


def test_history_follows_pagination_sorts_and_deduplicates(history):
    _, calls, replies = history
    replies[:] = [
        {'bars': {'AAPL': [history_bar('2026-09-11T20:00:00Z', 102)]}, 'next_page_token': 'next-page'},
        {'bars': {'AAPL': [history_bar('2026-09-11T19:55:00Z', 101), history_bar('2026-09-11T20:00:00Z', 102)]}, 'next_page_token': None},
    ]
    result = M.historical_chart('AAPL', '1W')
    assert [bar['close'] for bar in result['bars']] == [101, 102]
    assert parse_qs(urlsplit(calls[1]).query)['page_token'] == ['next-page']


def test_history_repeated_pagination_token_fails_without_partial_chart(history):
    _, calls, replies = history
    replies[:] = [{'bars': {'AAPL': [history_bar('2026-09-11T19:55:00Z')]}, 'next_page_token': 'loop'}]
    result = M.historical_chart('AAPL', '1W')
    assert result['status'] == 'unavailable'
    assert result['bars'] == []
    assert len(calls) == 2


def test_history_page_limit_fails_without_unbounded_requests(history):
    _, calls, replies = history
    replies[:] = [{'bars': {'AAPL': []}, 'next_page_token': 'page-%d' % index} for index in range(10)]
    result = M.historical_chart('AAPL', '1Y')
    assert result['status'] == 'unavailable' and result['bars'] == []
    assert len(calls) == M.MAX_CHART_PAGES


@pytest.mark.parametrize('bad', [
    {'c': float('nan')}, {'o': None}, {'h': 99}, {'l': 103}, {'c': True},
    {'c': -1}, {'h': float('inf')}, {'t': '2026-09-20T00:00:00Z'}, {'t': '2020-01-01T00:00:00Z'},
])
def test_history_rejects_invalid_ohlc_and_out_of_range_bars(history, bad):
    _, _, replies = history
    replies[:] = [{'bars': {'AAPL': [history_bar('2026-09-11T19:55:00Z', **bad)]}}]
    result = M.historical_chart('AAPL', '1W')
    assert result['status'] == 'empty' and result['bars'] == []


def test_history_no_credentials_or_data_never_synthesizes_prices(history, monkeypatch):
    _, calls, replies = history
    monkeypatch.delenv('APCA_API_SECRET_KEY')
    result = M.historical_chart('AAPL', '1D')
    assert result['status'] == 'unconfigured' and result['bars'] == []
    assert not calls
    monkeypatch.setenv('APCA_API_SECRET_KEY', 'test-only-secret')
    replies[:] = [{'bars': {}}]
    result = M.historical_chart('AAPL', '1D')
    assert result['status'] == 'empty' and result['bars'] == []


def test_history_provider_failures_do_not_leak_credentials_or_details(history, monkeypatch):
    def fail(*_, **__):
        raise HTTPError('secret-url', 403, 'secret-provider-message', {}, None)
    monkeypatch.setattr(M, '_request', fail)
    result = M.historical_chart('AAPL', '1D')
    assert result['status'] == 'unavailable' and result['bars'] == []
    assert 'secret' not in str(result)


def test_history_network_io_does_not_hold_live_quote_or_chart_cache_lock(history, monkeypatch):
    def request(*_, **__):
        assert M._lock.acquire(blocking=False)
        M._lock.release()
        assert M._chart_lock.acquire(blocking=False)
        M._chart_lock.release()
        return {'bars': {}}
    monkeypatch.setattr(M, '_request', request)
    assert M.historical_chart('AAPL', '1D')['status'] == 'empty'


def test_four_hour_history_completes_more_than_three_short_provider_pages(history):
    _, calls, replies = history
    dates = ['2026-06-20', '2026-07-01', '2026-07-20', '2026-08-01', '2026-08-20', '2026-09-11']
    replies[:] = [{'bars': {'AAPL': [history_bar(day + 'T16:00:00Z', 100 + index)]},
                  'next_page_token': 'short-page-%d' % index if index < len(dates) - 1 else None}
                 for index, day in enumerate(dates)]
    result = M.historical_chart('AAPL', '3M')
    assert result['status'] == 'ok'
    assert result['timeframe'] == '4Hour'
    assert [point['close'] for point in result['bars']] == [100, 101, 102, 103, 104, 105]
    assert len(calls) == 6


def test_four_hour_history_stops_when_total_request_budget_is_exhausted(history, monkeypatch):
    elapsed = [0.0]
    timeouts = []
    monkeypatch.setattr(M.time, 'monotonic', lambda: elapsed[0])

    def slow_pages(url, headers, timeout):
        timeouts.append(timeout)
        elapsed[0] += 3
        return {'bars': {'AAPL': [history_bar('2026-09-11T16:00:00Z')]},
                'next_page_token': 'next-%d' % len(timeouts)}

    monkeypatch.setattr(M, '_request', slow_pages)
    result = M.historical_chart('AAPL', '3M')
    assert result['status'] == 'unavailable' and result['bars'] == []
    assert timeouts == [4, 4, 3]
    assert elapsed[0] == M.CHART_REQUEST_BUDGET_SECONDS


def test_regular_market_request_keeps_four_second_timeout(monkeypatch):
    timeouts = []

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self, _):
            return b'{}'

    class Opener:
        def open(self, request, timeout):
            timeouts.append(timeout)
            return Response()

    monkeypatch.setattr(M, '_opener', Opener())
    assert M._request('https://paper-api.alpaca.markets/v2/clock', {}) == {}
    assert timeouts == [4]


def test_cached_open_clock_cannot_trade_after_closing_boundary(feed, monkeypatch):
    now, calls, _ = feed
    original = M._request
    def request(url, headers):
        result = original(url, headers)
        if url.endswith('/clock'):
            result['next_close'] = datetime.fromtimestamp(now[0] + 1, timezone.utc).isoformat()
        return result
    monkeypatch.setattr(M, '_request', request)
    assert M.snapshot(['AAPL'])['market']['status'] == 'open'
    now[0] += 1.1
    assert M.snapshot(['AAPL'])['market']['status'] == 'closed'
    assert len(calls) == 3  # closure enforced even during the quote-cache window


def test_slow_quote_response_crossing_close_is_closed(feed, monkeypatch):
    now, _, _ = feed
    original = M._request
    def request(url, headers):
        result = original(url, headers)
        if url.endswith('/clock'):
            result['next_close'] = datetime.fromtimestamp(now[0] + 1, timezone.utc).isoformat()
        else:
            now[0] += 2
        return result
    monkeypatch.setattr(M, '_request', request)
    assert M.snapshot(['AAPL'])['market']['status'] == 'closed'


def override_calendar(monkeypatch, rows):
    """Keep the normal mock clock/quotes while replacing the calendar reply."""
    original = M._request

    def request(url, headers):
        result = original(url, headers)
        return copy.deepcopy(rows) if '/calendar?' in url else result

    monkeypatch.setattr(M, '_request', request)


@pytest.mark.parametrize('at,status', [
    ('2026-09-15T13:29:59Z', 'closed'),
    ('2026-09-15T13:30:00Z', 'open'),
    ('2026-09-15T19:59:59Z', 'open'),
    ('2026-09-15T20:00:00Z', 'closed'),
    ('2026-09-15T21:00:00Z', 'closed'),
])
def test_regular_session_opens_inclusively_and_closes_exclusively(feed, at, status):
    now, calls, values = feed
    now[0] = M.timestamp(at)
    # Even a clock claiming "open" cannot authorize pre/post-market execution.
    values['open'] = True
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == status
    assert result['market']['sessionOpen'] == M.timestamp('2026-09-15T13:30:00Z')
    assert result['market']['sessionClose'] == M.timestamp('2026-09-15T20:00:00Z')
    query = parse_qs(urlsplit(next(url for url in calls if '/calendar?' in url)).query)
    assert query == {'start': ['2026-09-15'], 'end': ['2026-09-15']}


@pytest.mark.parametrize('claims_open,expected_status', [(False, 'closed'), (True, 'unavailable')])
def test_empty_holiday_calendar_never_authorizes_execution(feed, monkeypatch, claims_open, expected_status):
    now, _, values = feed
    now[0] = M.timestamp('2026-07-03T15:00:00Z')
    values['open'] = claims_open
    override_calendar(monkeypatch, [])
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == expected_status
    if claims_open:
        assert result['quotes'] == {}
    else:
        assert result['market']['sessionOpen'] is None
        assert result['market']['sessionClose'] is None
        assert result['quotes']['AAPL']['price'] > 0  # Display is distinct from execution.


def test_early_close_calendar_boundary_applies_to_cached_quotes(feed, monkeypatch):
    now, calls, _ = feed
    now[0] = M.timestamp('2026-11-27T17:59:59Z')
    override_calendar(monkeypatch, [{'date': '2026-11-27', 'open': '09:30', 'close': '13:00'}])
    opening = M.snapshot(['AAPL'])
    assert opening['market']['status'] == 'open'
    assert opening['market']['sessionClose'] == M.timestamp('2026-11-27T18:00:00Z')
    assert opening['market']['nextClose'] is None
    now[0] += 1
    assert M.snapshot(['AAPL'])['market']['status'] == 'closed'
    assert M.cached_snapshot(['AAPL'])['market']['status'] == 'closed'
    assert len(calls) == 3, 'Cached quotes must honor the early close without another provider call'
    assert opening['market']['status'] == 'open', 'Revalidation must not mutate previously returned data'


@pytest.mark.parametrize('day,open_utc,close_utc', [
    ('2026-03-06', '14:30', '21:00'),
    ('2026-03-09', '13:30', '20:00'),
    ('2026-10-30', '13:30', '20:00'),
    ('2026-11-02', '14:30', '21:00'),
])
def test_calendar_hours_follow_new_york_daylight_saving_time(feed, day, open_utc, close_utc):
    now, _, _ = feed
    now[0] = M.timestamp(day + 'T16:00:00Z')
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'open'
    assert result['market']['sessionOpen'] == M.timestamp(day + 'T' + open_utc + ':00Z')
    assert result['market']['sessionClose'] == M.timestamp(day + 'T' + close_utc + ':00Z')
    assert result['market']['sessionClose'] - result['market']['sessionOpen'] == 6.5 * 3600


def test_calendar_query_uses_exchange_date_before_utc_midnight_rollover(feed):
    now, calls, values = feed
    now[0] = M.timestamp('2026-09-16T00:30:00Z')
    values['open'] = False
    result = M.snapshot(['AAPL'])
    query = parse_qs(urlsplit(next(url for url in calls if '/calendar?' in url)).query)
    assert query == {'start': ['2026-09-15'], 'end': ['2026-09-15']}
    assert result['market']['sessionClose'] == M.timestamp('2026-09-15T20:00:00Z')
    assert result['market']['status'] == 'closed'


@pytest.mark.parametrize('rows', [
    None,
    {},
    [None],
    [{'date': '2026-09-14', 'open': '09:30', 'close': '16:00'}],
    [{'date': '2026-09-15', 'close': '16:00'}],
    [{'date': '2026-09-15', 'open': '09:30'}],
    [{'date': '2026-09-15', 'open': None, 'close': '16:00'}],
    [{'date': '2026-09-15', 'open': 'not-a-time', 'close': '16:00'}],
    [{'date': '2026-09-15', 'open': '09:99', 'close': '16:00'}],
    [{'date': '2026-09-15', 'open': '09:30', 'close': '25:00'}],
    [{'date': '2026-09-15', 'open': '16:00', 'close': '09:30'}],
    [{'date': '2026-09-15', 'open': '09:30', 'close': '09:30'}],
    [{'date': '2026-09-15', 'open': '09:30', 'close': '16:00'}] * 2,
], ids=['missing', 'wrong-container', 'missing-row', 'wrong-date', 'missing-open',
        'missing-close', 'null-open', 'invalid-time', 'invalid-minute', 'invalid-hour',
        'reversed-session', 'empty-session', 'duplicate-session'])
def test_malformed_or_missing_calendar_fails_closed(feed, monkeypatch, rows):
    _, calls, _ = feed
    override_calendar(monkeypatch, rows)
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'unavailable'
    assert result['quotes'] == {}
    assert not any('/quotes/' in url for url in calls), 'An invalid calendar stops before requesting execution quotes'


def test_calendar_accepts_seconds_without_changing_session_bounds(feed, monkeypatch):
    override_calendar(monkeypatch, [{'date': '2026-09-15', 'open': '09:30:00', 'close': '16:00:00'}])
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'open'
    assert result['market']['sessionOpen'] == M.timestamp('2026-09-15T13:30:00Z')
    assert result['market']['sessionClose'] == M.timestamp('2026-09-15T20:00:00Z')


def test_execution_feed_rechecks_regular_close_after_waiting_for_class_lock(feed):
    now, calls, _ = feed
    now[0] = M.timestamp('2026-09-15T19:59:50Z')
    original = M.snapshot(['AAPL'])
    assert original['market']['status'] == 'open'
    # A callback can wait for a class lock after fetching valid quotes.
    at_close = M.execution_feed(original, now=M.timestamp('2026-09-15T20:00:00Z'))
    assert at_close['market']['status'] == 'closed'
    assert original['market']['status'] == 'open'
    assert len(calls) == 3


def test_execution_feed_discards_quotes_when_clock_ages_during_lock_wait(feed):
    now, _, _ = feed
    original = M.snapshot(['AAPL'])
    stale = M.execution_feed(original, now=now[0] + 31)
    assert stale['market']['status'] == 'unavailable'
    assert stale['quotes'] == {}
    assert original['market']['status'] == 'open'
    assert original['quotes']['AAPL']['price'] > 0


@pytest.mark.parametrize('field', ['sessionOpen', 'sessionClose'])
def test_execution_feed_rejects_a_sip_snapshot_without_calendar_bounds(feed, field):
    original = M.snapshot(['AAPL'])
    original['market'].pop(field)
    result = M.execution_feed(original)
    assert result['market']['status'] == 'unavailable'
    assert result['quotes'] == {}


def test_stale_provider_clock_cannot_get_fresh_execution_quotes(feed, monkeypatch):
    now, calls, _ = feed
    original = M._request

    def request(url, headers):
        result = original(url, headers)
        if url.endswith('/clock'):
            result['timestamp'] = datetime.fromtimestamp(now[0] - 31, timezone.utc).isoformat()
        return result

    monkeypatch.setattr(M, '_request', request)
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'unavailable'
    assert result['quotes'] == {}
    assert len(calls) == 1


def test_slow_provider_cycle_discards_a_clock_that_aged_during_fetch(feed, monkeypatch):
    now, _, _ = feed
    original = M._request

    def request(url, headers):
        result = original(url, headers)
        if '/quotes/' in url:
            now[0] += 31
        return result

    monkeypatch.setattr(M, '_request', request)
    result = M.snapshot(['AAPL'])
    assert result['market']['status'] == 'unavailable'
    assert result['quotes'] == {}
    # Cache insertion happens after the slow request; its apparent freshness
    # must not make the original exchange clock valid again.
    assert M.cached_snapshot(['AAPL'])['market']['status'] == 'unavailable'


def test_regular_close_rechecked_in_both_cached_snapshot_paths(feed):
    now, calls, _ = feed
    now[0] = M.timestamp('2026-09-15T19:59:59.500000Z')
    assert M.snapshot(['AAPL'])['market']['status'] == 'open'
    now[0] += 0.5
    assert M.cached_snapshot(['AAPL'])['market']['status'] == 'closed'
    assert M.snapshot(['AAPL'])['market']['status'] == 'closed'
    assert len(calls) == 3
