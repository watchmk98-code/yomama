"""Play with every regular customer in a temporary town.

    python3 previews/customer_emotes_preview.py 3088

All businesses are available in this local art preview. The live rules and
saved classes are unchanged; customer shipments still use the real engine.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import game_api as A
import production_economy as E
from preview_support import solo_seat, preview_handler, serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3088)
    args = parser.parse_args()
    cfg = E.load_config()
    st = E.new_state(cfg, seed=7)
    st['b'] = [E._building(tier, lv=3, sales=3, storage=3) for tier in range(len(cfg['tiers']))]
    st['tierOf'] = list(range(len(st['b'])))
    st['unlock'] = {str(slot): 0 for slot in st['tierOf']}
    st['book'] = sum(tier['baseCost'] for tier in cfg['tiers'])
    st['cash'] = 10000
    for slot, tier in enumerate(cfg['tiers']):
        for good in tier['goods']:
            st['inventory'][good['id']] = min(20, E._good_capacity(cfg, st, slot, good['id']))
    E._sync_pools(cfg, st)
    world = E.new_class(cfg, 0)
    world['nextTick'] = 0
    label = 'CUSTOMER EMOTE PREVIEW'
    with tempfile.TemporaryDirectory(prefix='yomama-customer-emotes-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', label)
        with A.connect() as conn:
            player = A._ensure_solo(conn)
            session = A._session_of(conn, A.SOLO_CODE)
            A._save_state(conn, player['id'], cfg, st)
            A._save_world(conn, session, world)
        print('All 17 customers unlocked in a separate temporary town.', flush=True)
        serve(args.port, preview_handler(token, label), first_page='marketplace.html')


if __name__ == '__main__':
    main()
