"""Isolated economy-design preview; never reads or changes the developer save.

    python3 previews/business_design_preview.py 3011
    python3 previews/business_design_preview.py 3012 --all-buildings

The second mode grants a sample town for exploring every business's controls.
Quest progress remains fresh. All changes disappear when this process stops.
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
import business_operations
from preview_support import solo_seat, preview_handler, serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3011)
    parser.add_argument('--all-buildings', action='store_true')
    args = parser.parse_args()
    label = 'BUSINESS DESIGN PREVIEW'
    with tempfile.TemporaryDirectory(prefix='yomama-business-design-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', label)
        if args.all_buildings:
            with A.connect() as conn:
                player = A._ensure_solo(conn)
                session = A._session_of(conn, player['code'])
                cfg = A.econ_config(session)
                st = A._load_state(player, cfg, session)
                st['b'] = [E._building(ti, lv=3, sales=2) for ti in range(len(cfg['tiers']))]
                st['tierOf'] = list(range(len(cfg['tiers'])))
                st['cash'] = 25000
                st['materials'] = 20
                st['inventory'] = {good['id']: 6 for tier in cfg['tiers'] for good in tier['goods']}
                st['book'] = sum(tier['baseCost'] for tier in cfg['tiers'])
                st = E.migrate_state(cfg, st)
                # Sample investment records make the closure review usable;
                # these values exist only in this explicitly granted preview.
                business_operations.ensure(cfg, st)
                for business in st['b']:
                    value = cfg['tiers'][business['tier']]['baseCost']
                    business.update(cashInvested=value, bookValue=value, investmentKnown=True)
                st['offers'] = None
                E.offer_contracts(cfg, st, st['tick'])
                A._save_state(conn, player['id'], cfg, st)
        serve(args.port, preview_handler(token, label))


if __name__ == '__main__':
    main()
