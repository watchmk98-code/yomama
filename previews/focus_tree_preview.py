"""Play the global focus tree with a disposable, signed-in town.

    python3 previews/focus_tree_preview.py 3024
    python3 previews/focus_tree_preview.py 3024 --fresh

The showcase has earned the first two focuses through the real start and
completion functions and owns businesses across the connected sectors.
--fresh starts with only the normal opening Farm.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import business_operations
import focus_tree
import game_api as api
import inventory_costs
import production_economy as economy
import workforce
from preview_support import preview_handler, serve, solo_seat


def preview_town(cfg, fresh=False):
    state = economy.new_state(cfg, seed=73)
    if not fresh:
        tiers = {tier['id']: index for index, tier in enumerate(cfg['tiers'])}
        state['tierOf'] = [tiers[name] for name in ('farm', 'roastery', 'cannery', 'workshop', 'solar_coop', 'relay_station', 'freight_terminal', 'data_center')]
        state['b'] = [economy._building(tier) for tier in state['tierOf']]
        business_operations.ensure(cfg, state, new=True)
        workforce.ensure(cfg, state)
        state['cash'] = 12500
        state['book'] = sum(building['bookValue'] for building in state['b'])
        for focus_id in ('secure_harvest', 'reliable_supply'):
            result = focus_tree.act(cfg, state, dict(action='start', focusId=focus_id))
            if not result.get('ok'):
                raise RuntimeError('%s: %s' % (focus_id, result.get('why')))
            target = state['tick'] + focus_tree.duration_ticks(cfg, focus_id)
            focus_tree.advance(cfg, state, target)
            state['tick'] = target
        for slot, building in enumerate(state['b']):
            for good in cfg['tiers'][building['tier']]['goods']:
                state['inventory'][good['id']] = economy._good_capacity(cfg, state, slot, good['id'])
        inventory_costs.migrate(cfg, state)
        economy._sync_pools(cfg, state)
    state['lastActiveTick'] = state['tick']
    state['lastLogin'] = state['tick']
    state['reportTick'] = state['tick']
    world = economy.new_class(cfg, state['tick'])
    world['nextTick'] = state['tick']
    world['k'] = max(0, state['tick'] - 1)
    return state, world


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3024)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--no-serve', action='store_true',
                        help='build the preview town, print its progress, and exit')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a local preview port from 1024 to 65535.')

    cfg = copy.deepcopy(api._startup_config)
    state, world = preview_town(cfg, fresh=args.fresh)
    tree = economy.payload(cfg, state, world, {'paused': False})['focusTree']
    print('Focus Tree: %d/%d focuses complete; branch %s.' %
          (tree['completedCount'], tree['totalNodes'], tree['branch'] or 'undecided'), flush=True)
    if args.no_serve:
        return

    label = 'FOCUS TREE / FRESH' if args.fresh else 'FOCUS TREE'
    with tempfile.TemporaryDirectory(prefix='yomama-focus-tree-') as directory:
        token = solo_seat(Path(directory) / 'preview.db', label)
        with api.connect() as conn:
            player = api._ensure_solo(conn)
            now = time.time()
            elapsed = state['tick'] * cfg['global']['tick']
            conn.execute('UPDATE sessions SET clock_base=?, clock_accum=?, started_at=?, econ_config=? WHERE code=?',
                         (now, elapsed, now - elapsed, json.dumps(cfg), api.SOLO_CODE))
            session = api._session_of(conn, api.SOLO_CODE)
            api._save_state(conn, player['id'], cfg, state)
            api._save_world(conn, session, world)
        print('Disposable local save; ready to connect your businesses.', flush=True)
        serve(args.port, preview_handler(token, label), first_page='focus-tree.html')


if __name__ == '__main__':
    main()
