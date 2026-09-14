"""Run a temporary crafting showroom, separate from every real class/save.

    python3 previews/craft_preview.py 4130
    python3 previews/craft_preview.py 4130 --fresh

The showroom grants products and cash, but crafting supplies must be purchased.
Use --fresh to inspect ordinary new-player availability instead.
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
    parser.add_argument('port', type=int, nargs='?', default=4130)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--cash', type=int, default=250000, help='Showroom cash for trying advanced crafts (ignored with --fresh).')
    args = parser.parse_args()
    label = 'CRAFT PREVIEW'
    with tempfile.TemporaryDirectory(prefix='yomama-craft-preview-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', label)
        if not args.fresh:
            with A.connect() as conn:
                player = A._ensure_solo(conn)
                session = A._session_of(conn, player['code'])
                cfg = A.econ_config(session)
                st = A._load_state(player, cfg, session)
                st['tierOf'] = list(range(len(cfg['tiers'])))
                st['b'] = [E._building(i) for i in st['tierOf']]
                st['cash'] = max(0, args.cash)
                st['inventory'] = {g['id']: 40 for t in cfg['tiers'] for g in t['goods']}
                st['book'] = sum(t['baseCost'] for t in cfg['tiers'])
                st = E.migrate_state(cfg, st)
                # Preserve the sample inventory while browsing. This pauses
                # each business, not the class or the crafting controls.
                for business in st['b']:
                    business['paused'] = True
                    business['reserve'] = True
                A._save_state(conn, player['id'], cfg, st)
        serve(args.port, preview_handler(token, label), first_page='craft.html')


if __name__ == '__main__':
    main()
