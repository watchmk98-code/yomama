"""Local margin preview with earned sample stock and a temporary database."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import game_api as api
import production_economy as economy
from previews.order_classes_preview import sample_town
from previews.preview_support import preview_handler, serve, solo_seat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3023)
    parser.add_argument('--businesses', type=int, default=15, choices=range(1, 16))
    args = parser.parse_args()
    cfg = economy.load_config()
    state = sample_town(cfg, args.businesses, 71)
    state['cash'] = 1_000_000
    state['lastActiveTick'] = 0
    # Produce the sample shelves through ordinary game ticks. Then give the
    # statement a real minute of customer receipts; no receipt is invented.
    for building in state['b']:
        building['reserve'] = True
    for _ in range(64):
        economy.player_tick(cfg, {}, state, state['tick'])
    for building in state['b']:
        building['reserve'] = False
    for _ in range(32):
        economy.player_tick(cfg, {}, state, state['tick'])
    state['lastActiveTick'] = state['tick']
    world = economy.new_class(cfg, state['tick'])
    world.update(nextTick=state['tick'], k=state['tick']-1)
    with tempfile.TemporaryDirectory(prefix='yomama-margin-preview-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', 'MARGIN PREVIEW')
        with api.connect() as conn:
            player = api._ensure_solo(conn)
            now = time.time()
            conn.execute('UPDATE sessions SET clock_base=?, clock_accum=?, started_at=? WHERE code=?',
                         (now, state['tick']*cfg['global']['tick'], now, api.SOLO_CODE))
            session = api._session_of(conn, api.SOLO_CODE)
            api._save_state(conn, player['id'], cfg, state)
            api._save_world(conn, session, world)
        serve(args.port, preview_handler(token, name='MARGIN PREVIEW'), 'buildings.html')


if __name__ == '__main__':
    main()
