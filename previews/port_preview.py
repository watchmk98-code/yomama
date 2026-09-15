"""Isolated PORT account with a fresh student seat; never uses game.db.

    python3 previews/port_preview.py 3014
    python3 previews/port_preview.py 3014 --fixture-quotes

The optional fixture feed is for repeatable accounting/UI tests only. Without
that option, this preview uses the same Alpaca adapter as the real game.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import game_api as A
from port_worker import PortExecutionWorker
from preview_support import solo_seat, preview_handler, serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3014)
    parser.add_argument('--fixture-quotes', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='yomama-port-preview-') as directory:
        token = solo_seat(Path(directory) / 'port-preview.db', 'PORT TEST PLAYER')
        if args.fixture_quotes:
            def fixture(symbols, **_):
                now = time.time()
                return {'quotes': {symbol: {'bid': 99.99, 'ask': 100.01, 'price': 100,
                                             'timestamp': now - .001}
                                   for symbol in symbols},
                        'market': {'source': 'local_test_fixture', 'status': 'open',
                                   'message': 'TEST FIXTURE · simulated quotes', 'asOf': now,
                                   'maxQuoteAgeSeconds': 10}}
            A.alpaca_market.snapshot = fixture
        print('Isolated PORT preview; temporary saved accounts.', flush=True)
        worker = PortExecutionWorker(A.process_pending_portfolios)
        worker.start()
        try:
            serve(args.port, preview_handler(token, 'PORT TEST PLAYER'))
        finally:
            worker.stop()


if __name__ == '__main__':
    main()
