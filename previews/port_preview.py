"""Isolated PORT account with a fresh student seat; never uses game.db.

    python3 previews/port_preview.py 3014
    python3 previews/port_preview.py 3014 --fixture-quotes
    python3 previews/port_preview.py 3014 --session afterhours

The optional fixture feed is for repeatable accounting/UI tests only. Without
that option, this preview uses the same Alpaca adapter as the real game.
--session places the fixture feed inside one trading session (pre-market,
regular, after-hours or closed); the session label, the countdown and the
open/closed clamp still come from alpaca_market, not from this file.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import game_api as A
from port_worker import PortExecutionWorker
from preview_support import solo_seat, preview_handler, serve


# Hours before/after the moment of the request, as a trading day would sit
# around it: (regular open, regular close, extended open, extended close).
SESSION_WINDOWS = {
    'premarket': (2, 8.5, -1, 14),
    'regular': (-2, 4.5, -7.5, 8.5),
    'afterhours': (-7.5, -0.5, -13, 3.5),
    'closed': (-13.5, -6.5, -19, -2.5),
}


def fixture_feed(session):
    """A simulated feed shaped exactly like the Alpaca adapter's, so the real
    session rules in alpaca_market decide what the terminal shows."""
    extended = session in ('premarket', 'afterhours')

    def fixture(symbols, **_):
        now = time.time()
        opening, closing, session_open, session_close = (
            now + hours * 3600 for hours in SESSION_WINDOWS[session])
        # Extended-hours spreads are wider; the ticket says so, so show it.
        bid, ask = (99.8, 100.2) if extended else (99.99, 100.01)
        return {'quotes': {symbol: {'bid': bid, 'ask': ask, 'price': 100,
                                    'timestamp': now - .001}
                           for symbol in symbols},
                'market': {'source': 'local_test_fixture', 'status': 'open',
                           'message': 'TEST FIXTURE · simulated quotes', 'asOf': now,
                           'maxQuoteAgeSeconds': 10, 'extendedHours': True,
                           'regularOpen': opening, 'regularClose': closing,
                           'sessionOpen': session_open, 'sessionClose': session_close,
                           'nextSessionOpen': now + 8 * 3600}}
    return fixture


def unlock_port(token):
    """PORT sits behind the analyst licence. A preview seat has not earned one,
    so grandfather it in for this throwaway database only."""
    with A._db_lock, A.connect() as conn:
        player = A._player_by_token(conn, token)
        session = A._session_of(conn, player['code'])
        town = A._load_state(player, A.econ_config(session), session)
        town['licenceGrandfathered'] = True
        conn.execute('UPDATE players SET econ=? WHERE id=?', (json.dumps(town), player['id']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3014)
    parser.add_argument('--fixture-quotes', action='store_true')
    parser.add_argument('--session', choices=sorted(SESSION_WINDOWS),
                        help='place the fixture feed in this session (implies --fixture-quotes)')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='yomama-port-preview-') as directory:
        token = solo_seat(Path(directory) / 'port-preview.db', 'PORT TEST PLAYER')
        unlock_port(token)
        if args.fixture_quotes or args.session:
            A.alpaca_market.snapshot = fixture_feed(args.session or 'regular')
            print('TEST FIXTURE quotes · %s session' % (args.session or 'regular'), flush=True)
        print('Isolated PORT preview; temporary saved accounts.', flush=True)
        worker = PortExecutionWorker(A.process_pending_portfolios)
        worker.start()
        try:
            serve(args.port, preview_handler(token, 'PORT TEST PLAYER'))
        finally:
            worker.stop()


if __name__ == '__main__':
    main()
