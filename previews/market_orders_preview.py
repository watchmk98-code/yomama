"""Isolated stocked market for reviewing return visits: python3 previews/market_orders_preview.py 3018."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import game_api as api
import production_economy as economy
from preview_support import solo_seat, preview_handler, serve


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3018
    cfg = economy.load_config()
    st = economy.new_state(cfg, seed=71)
    st['cash'] = 5000
    st['tierOf'] = [0, 1, 2, 3]
    st['b'] = [economy._building(tier, lv=3, storage=2) for tier in st['tierOf']]
    economy.migrate_state(cfg, st)
    economy.market_orders.sync(cfg, st)
    for gid, good in economy.catalog(cfg).items():
        if good['tier'] in st['tierOf']:
            slot = st['tierOf'].index(good['tier'])
            st['inventory'][gid] = economy._good_capacity(cfg, st, slot, gid)
    with tempfile.TemporaryDirectory(prefix='yomama-market-preview-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', 'STOCKED MARKET PREVIEW')
        with api.connect() as conn:
            player = api._ensure_solo(conn)
            api._save_state(conn, player['id'], cfg, st)
        serve(port, preview_handler(token, 'STOCKED MARKET PREVIEW'))


if __name__ == '__main__':
    main()
