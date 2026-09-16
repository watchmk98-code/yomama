"""Read-only Alpaca SIP quotes for PORT. No brokerage orders are sent.

Credentials belong in the server environment, never in browser assets. Prices
are deliberately absent when credentials or the provider are unavailable.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_QUOTE_AGE_SECONDS = 10
QUOTE_CACHE_SECONDS = 2
_lock = threading.Lock()
_cache = {}
_calendar_cache = {}
CHART_RANGES = {'1D': ('1Min', 7, 30), '1W': ('30Min', 7, 30),
                '1M': ('1Hour', 31, 60), '3M': ('4Hour', 91, 60),
                '1Y': ('1Day', 366, 60), '5Y': ('1Week', 1827, 60)}
EXTENDED_PREMARKET_OPEN = '04:00'
EXTENDED_LAST_CLOSE = '20:00'
EXTENDED_AFTER_HOURS_SECONDS = 4 * 3600
SESSION_MESSAGES = {'premarket': 'Pre-market · live SIP quotes · virtual trades',
                    'regular': 'Live SIP quotes · virtual trades',
                    'afterhours': 'After hours · live SIP quotes · virtual trades'}
MAX_CHART_PAGES = 3
MAX_FOUR_HOUR_CHART_PAGES = 8
CHART_REQUEST_BUDGET_SECONDS = 9.0
MAX_CHART_ROWS = 10000
_chart_lock = threading.Lock()
_chart_cache = {}
_new_york = ZoneInfo('America/New_York')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = build_opener(_NoRedirect())


def timestamp(value):
    """Parse Alpaca's timezone-aware, nanosecond ISO timestamps on Python 3.9."""
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp needs a timezone')
    return parsed.timestamp()


def _request(url, headers, timeout=4):
    request = Request(url, headers=headers, method='GET')
    with _opener.open(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('response too large')
    result = json.loads(raw)
    if not isinstance(result, (dict, list)):
        raise ValueError('invalid response')
    return result


def _result(status, message, quotes=None, **extra):
    return {'quotes': quotes or {}, 'market': dict(
        source='alpaca_sip', status=status, message=message, asOf=time.time(),
        maxQuoteAgeSeconds=MAX_QUOTE_AGE_SECONDS, **extra)}


def extended_hours_enabled():
    """Pre-market and after-hours execution. Set PORT_EXTENDED_HOURS=0 for
    regular hours only; no code change is needed either way."""
    return os.environ.get('PORT_EXTENDED_HOURS', '1').strip().lower() not in ('0', 'false', 'off', 'no')


def _exchange_time(day, clock):
    return datetime.fromisoformat(day + 'T' + clock).replace(tzinfo=_new_york).timestamp()


def _extended_bounds(day, regular_open, regular_close):
    """US extended hours around one calendar row.

    Pre-market starts at 04:00 ET and after-hours runs four hours past the
    close, never beyond 20:00 ET. Early closes shorten both windows exactly as
    the exchanges do: a 13:00 ET close trades until 17:00 ET. The times are
    derived here rather than read from optional calendar fields, so a provider
    response cannot widen the tradable window.
    """
    if regular_open is None or regular_close is None:
        return None, None
    opening = min(_exchange_time(day, EXTENDED_PREMARKET_OPEN), regular_open)
    closing = max(regular_close, min(regular_close + EXTENDED_AFTER_HOURS_SECONDS,
                                     _exchange_time(day, EXTENDED_LAST_CLOSE)))
    return opening, closing


def _session_bounds(base, headers, clock_time):
    """The exchange day's regular window and the wider extended-hours window."""
    day = datetime.fromtimestamp(clock_time, _new_york).date().isoformat()
    key = (base, headers['APCA-API-KEY-ID'], day)
    cached = _calendar_cache.get(key)
    if cached and 0 <= time.time() - cached[0] < 3600:
        return cached[1]
    rows = _request(base + '/v2/calendar?' + urlencode({'start': day, 'end': day}), headers)
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError('invalid market calendar')
    bounds = (None, None, None, None)
    if rows:
        row = rows[0]
        if not isinstance(row, dict) or row.get('date') != day:
            raise ValueError('invalid calendar date')
        values = []
        for field in ('open', 'close'):
            value = row.get(field)
            if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?', value):
                raise ValueError('invalid calendar hours')
            values.append(_exchange_time(day, value))
        if values[0] >= values[1]:
            raise ValueError('invalid calendar session')
        bounds = tuple(values) + _extended_bounds(day, values[0], values[1])
    if len(_calendar_cache) >= 10:
        _calendar_cache.clear()
    _calendar_cache[key] = (time.time(), bounds)
    return bounds


def _next_session_open(next_open, extended):
    """When trading next becomes possible, so a closed market counts down to
    the pre-market open rather than to the later regular open."""
    try:
        opening = timestamp(next_open)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if not extended:
        return opening
    day = datetime.fromtimestamp(opening, _new_york).date().isoformat()
    return min(opening, _exchange_time(day, EXTENDED_PREMARKET_OPEN))


def _session_label(now, market):
    """Which session `now` falls in. Display only; execution uses the bounds."""
    if market['status'] == 'closed':
        return 'closed'
    if market['status'] != 'open':
        return None
    opening, closing = market.get('regularOpen'), market.get('regularClose')
    if opening is None or closing is None:
        return 'regular'
    return 'premarket' if now < opening else 'regular' if now < closing else 'afterhours'


def execution_feed(feed, now=None):
    """Revalidate exchange time after network/class-lock waits, fail closed."""
    result = copy.deepcopy(feed)
    market = result['market']
    now = time.time() if now is None else now
    try:
        clock_time = market.get('clockTimestamp')
        if clock_time is not None and abs(now - clock_time) > 30:
            raise ValueError('stale market clock')
        if market['status'] == 'open':
            session_open, session_close = market.get('sessionOpen'), market.get('sessionClose')
            # All production SIP snapshots carry calendar bounds. Fixtures may
            # omit them, so isolated tests can use a deliberate simulated clock.
            if market.get('source') == 'alpaca_sip' and (session_open is None or session_close is None):
                raise ValueError('missing calendar session')
            # The clock's next close ends the regular session only. With
            # extended hours on, the calendar-derived bounds above are the
            # tradable window and after-hours trading continues past it.
            if ((session_open is not None and now < session_open) or
                    (session_close is not None and now >= session_close) or
                    (not market.get('extendedHours') and market.get('nextClose')
                     and now >= timestamp(market['nextClose']))):
                market.update(status='closed', message='US stock market closed.')
        market['session'] = _session_label(now, market)
        if market['status'] == 'open' and market.get('source') == 'alpaca_sip':
            market['message'] = SESSION_MESSAGES[market['session']]
    except (TypeError, ValueError, OverflowError):
        market.update(status='unavailable', message='Market time is temporarily unavailable.')
        result['quotes'] = {}
    if market['status'] not in ('open', 'closed'):
        result['quotes'] = {}
    return result


def cached_snapshot(symbols):
    """Non-blocking cached display data for acknowledging cancellation intent."""
    fallback = _result('unavailable', 'Market data is refreshing.')
    if not _lock.acquire(blocking=False):
        return fallback
    try:
        key = (tuple(sorted(set(symbols))), os.environ.get('APCA_API_KEY_ID', '').strip(),
               os.environ.get('APCA_API_SECRET_KEY', '').strip(),
               os.environ.get('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets').rstrip('/'))
        cached = _cache.get(key)
        if cached and 0 <= time.time() - cached[0] < QUOTE_CACHE_SECONDS:
            return execution_feed(cached[1])
        return fallback
    finally:
        _lock.release()


def _daily_change(record, price, quote_time):
    """Compare the displayed SIP midpoint with the prior trading day's close.

    Before today's first daily bar, dailyBar can still be yesterday's bar.
    Select by New York date so premarket, weekends and holidays use the right
    baseline; absent or invalid bars leave the change unavailable.
    """
    quote_day = datetime.fromtimestamp(quote_time, _new_york).date()
    closes = []
    for name in ('dailyBar', 'prevDailyBar'):
        bar = record.get(name)
        if not isinstance(bar, dict):
            continue
        try:
            close = float(bar['c'])
            day = datetime.fromtimestamp(timestamp(bar['t']), _new_york).date()
            if math.isfinite(close) and close > 0 and day < quote_day:
                closes.append((day, close))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
    if not closes:
        return None
    close = max(closes)[1]
    change = (price / close - 1) * 100
    return change if math.isfinite(change) else None


def snapshot(symbols, force=False):
    """A shared, short-lived quote snapshot; callers must still check quote age.

    This first portfolio milestone uses batched REST quotes. A streaming adapter
    can replace it without changing accounts or order accounting.
    """
    symbols = tuple(sorted(set(symbols)))
    if not symbols or len(symbols) > 100 or any(
            not isinstance(s, str) or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,11}', s)
            for s in symbols):
        return _result('unavailable', 'The stock list is unavailable.')
    key = os.environ.get('APCA_API_KEY_ID', '').strip()
    secret = os.environ.get('APCA_API_SECRET_KEY', '').strip()
    if not key or not secret:
        return _result('unconfigured', 'Market data is not connected yet.')
    base = os.environ.get('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets').rstrip('/')
    if base not in ('https://paper-api.alpaca.markets', 'https://api.alpaca.markets'):
        return _result('unconfigured', 'The market data connection needs configuration.')
    headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret,
               'Accept': 'application/json'}
    cache_key = (symbols, key, secret, base)
    with _lock:
        now = time.time()
        cached = _cache.get(cache_key)
        if not force and cached and 0 <= now - cached[0] < QUOTE_CACHE_SECONDS:
            return execution_feed(cached[1])
        try:
            # Check the actual exchange calendar, including holidays and early
            # closes. A fresh clock per snapshot avoids trading past a close.
            clock = _request(base + '/v2/clock', headers)
            if not isinstance(clock, dict) or not isinstance(clock.get('is_open'), bool):
                raise ValueError('invalid market clock')
            clock_time = timestamp(clock.get('timestamp'))
            if abs(now - clock_time) > 30:
                raise ValueError('stale market clock')
            regular_open, regular_close, extended_open, extended_close = _session_bounds(
                base, headers, clock_time)
            extended = extended_hours_enabled()
            session_open, session_close = ((extended_open, extended_close) if extended
                                           else (regular_open, regular_close))
            if clock['is_open'] and (session_open is None or session_close is None):
                raise ValueError('market open without a calendar session')
            raw = _request('https://data.alpaca.markets/v2/stocks/snapshots?' +
                           urlencode({'symbols': ','.join(symbols), 'feed': 'sip'}), headers)
            records = raw if isinstance(raw, dict) else None
            if not isinstance(records, dict):
                raise ValueError('invalid quotes')
            quotes = {}
            for symbol in symbols:
                record = records.get(symbol)
                row = record.get('latestQuote') if isinstance(record, dict) else None
                if not isinstance(row, dict):
                    continue
                try:
                    bid, ask = float(row['bp']), float(row['ap'])
                    at = timestamp(row['t'])
                    if not all(math.isfinite(x) and x > 0 for x in (bid, ask, at)) or bid > ask:
                        continue
                    if at > time.time() + 1:
                        continue
                    quotes[symbol] = {'bid': bid, 'ask': ask, 'price': (bid + ask) / 2,
                                      'timestamp': at, 'source': 'alpaca_sip',
                                      'change': _daily_change(record, (bid + ask) / 2, at)}
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            trading = bool(clock['is_open']) or (session_open is not None
                                                 and session_open <= clock_time < session_close)
            status = 'open' if trading else 'closed'
            message = SESSION_MESSAGES['regular'] if trading else 'US stock market closed.'
            result = execution_feed(_result(status, message, quotes, nextOpen=clock.get('next_open'),
                                            nextClose=clock.get('next_close'), clockTimestamp=clock_time,
                                            nextSessionOpen=_next_session_open(clock.get('next_open'), extended),
                                            sessionOpen=session_open, sessionClose=session_close,
                                            regularOpen=regular_open, regularClose=regular_close,
                                            extendedHours=extended))
        except HTTPError as error:
            # Never forward provider response bodies, URLs, or credentials.
            message = ('Market data credentials or SIP access need checking.'
                       if error.code in (401, 403) else 'Market data is temporarily unavailable.')
            result = _result('unavailable', message)
        except (URLError, OSError, ValueError, TypeError, OverflowError):
            result = _result('unavailable', 'Market data is temporarily unavailable.')
        _cache.clear()
        _cache[cache_key] = (time.time(), result)
        return copy.deepcopy(result)


def _chart_result(symbol, range_name, status, message, bars=None):
    return {'symbol': symbol, 'range': range_name, 'source': 'alpaca_sip',
            'status': status, 'message': message, 'bars': bars or [],
            'timeframe': CHART_RANGES[range_name][0], 'asOf': time.time(),
            'adjustment': 'split', 'session': 'all_available'}


def historical_chart(symbol, range_name, force=False):
    """Actual SIP bar closes, including available extended-hours activity.

    The API layer restricts symbols to PORT's stock list. These fixed intervals
    bound the provider request; absent history never becomes invented prices.
    Cache access has its own short lock, so charts do not block live quotes.
    """
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,11}', symbol):
        raise ValueError('invalid chart symbol')
    if range_name not in CHART_RANGES:
        raise ValueError('invalid chart range')
    key = os.environ.get('APCA_API_KEY_ID', '').strip()
    secret = os.environ.get('APCA_API_SECRET_KEY', '').strip()
    if not key or not secret:
        return _chart_result(symbol, range_name, 'unconfigured', 'Market data is not connected yet.')
    timeframe, days, cache_seconds = CHART_RANGES[range_name]
    cache_key = (symbol, range_name, key, secret)
    now = time.time()
    with _chart_lock:
        cached = _chart_cache.get(cache_key)
        if not force and cached and 0 <= now - cached[0] < cache_seconds:
            return copy.deepcopy(cached[1])
    headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret,
               'Accept': 'application/json'}
    start = now - days * 86400
    params = {'symbols': symbol, 'timeframe': timeframe, 'feed': 'sip',
              'adjustment': 'split', 'currency': 'USD', 'sort': 'asc',
              'start': datetime.fromtimestamp(start, timezone.utc).isoformat(),
              'end': datetime.fromtimestamp(now, timezone.utc).isoformat(),
              'limit': MAX_CHART_ROWS}
    try:
        bars = {}
        seen_tokens = set()
        total_rows = 0
        # Alpaca can return short aggregate pages even with limit=10000. The
        # 91-day 4Hour window needs more than three pages for actively traded
        # stocks; preserve the smaller page cap for the other intervals.
        max_pages = MAX_FOUR_HOUR_CHART_PAGES if timeframe == '4Hour' else MAX_CHART_PAGES
        deadline = time.monotonic() + CHART_REQUEST_BUDGET_SECONDS
        for page in range(max_pages):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('historical request budget exhausted')
            raw = _request('https://data.alpaca.markets/v2/stocks/bars?' + urlencode(params), headers,
                           timeout=min(4, remaining))
            if time.monotonic() > deadline:
                raise TimeoutError('historical request budget exhausted')
            records = raw.get('bars') if isinstance(raw, dict) else None
            if not isinstance(records, dict):
                raise ValueError('invalid historical bars')
            rows = records.get(symbol, [])
            if not isinstance(rows, list):
                raise ValueError('invalid historical bars')
            total_rows += len(rows)
            if total_rows > MAX_CHART_ROWS:
                raise ValueError('too many historical bars')
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    at = timestamp(row.get('t'))
                    prices = {field: float(row[key]) for field, key in
                              (('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c'))}
                    if any(isinstance(row[key], bool) for key in ('o', 'h', 'l', 'c')) or any(
                            not math.isfinite(value) or value <= 0 for value in prices.values()) or not start <= at <= now:
                        continue
                    if prices['low'] > min(prices['open'], prices['close']) or prices['high'] < max(prices['open'], prices['close']) or prices['low'] > prices['high']:
                        continue
                    point = dict(prices, time=at, value=prices['close'])
                    volume = row.get('v')
                    if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0 <= volume <= 10 ** 15 and math.isfinite(volume):
                        point['volume'] = volume
                    bars[at] = point
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            token = raw.get('next_page_token')
            if token is None or token == '':
                break
            if not isinstance(token, str) or len(token) > 4096 or token in seen_tokens or page == max_pages - 1 or total_rows >= MAX_CHART_ROWS:
                raise ValueError('historical pagination limit reached')
            seen_tokens.add(token)
            params['page_token'] = token
        points = [bars[at] for at in sorted(bars)]
        if range_name == '1D' and points:
            latest_day = datetime.fromtimestamp(points[-1]['time'], _new_york).date()
            points = [point for point in points
                      if datetime.fromtimestamp(point['time'], _new_york).date() == latest_day]
        result = _chart_result(symbol, range_name, 'ok' if points else 'empty',
                               'Alpaca SIP historical prices.' if points else 'No market history is available for this range.', points)
    except HTTPError as error:
        message = ('Market data credentials or SIP access need checking.'
                   if error.code in (401, 403) else 'Market history is temporarily unavailable.')
        result = _chart_result(symbol, range_name, 'unavailable', message)
    except (URLError, OSError, ValueError, TypeError, OverflowError):
        result = _chart_result(symbol, range_name, 'unavailable', 'Market history is temporarily unavailable.')
    with _chart_lock:
        # At most one cached result per stock/range for the current account, plus
        # room during credential rotation; no client-selected dates grow this.
        while len(_chart_cache) >= 100 and cache_key not in _chart_cache:
            oldest = min(_chart_cache, key=lambda item: _chart_cache[item][0])
            del _chart_cache[oldest]
        _chart_cache[cache_key] = (time.time(), result)
    return copy.deepcopy(result)
