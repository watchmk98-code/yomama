"""Play the isolated 15-product automatic crafting trial.

    python3 previews/crafting_pilot_preview.py 3011
    python3 previews/crafting_pilot_preview.py 3011 --fresh

The showcase has six producers plus their Machine Works supplier, funded stock,
completed unlock milestones, and three running products. --fresh keeps the
supplied businesses but starts with blank milestones, no unlocks and no assets.
Every run uses a disposable database; the default economy config is unchanged.
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

import business_operations as operations
import crafting
import crafting_pilot as pilot
import game_api as api
import inventory_costs
import production_economy as economy
import workforce
from preview_support import preview_handler, serve, solo_seat


BUSINESSES = ('farm', 'fish_stall', 'roastery', 'garage', 'workshop', 'cannery', 'machine_works')
INITIAL_PRODUCTS = ('farm_breakfast_basket', 'seafood_picnic_box', 'battery_pack')


def _action(cfg, state, **fields):
    revision = state['crafting']['revision']
    result = pilot.act(cfg, state, dict(requestId='preview-pilot-{}'.format(revision),
                                      revision=revision, **fields))
    if not result['ok']:
        raise RuntimeError(result['why'])
    return result


def preview_town(cfg, fresh=False):
    """Build only a preview fixture; production and sales use the real engine."""
    state = economy.new_state(cfg, seed=71)
    tiers = {tier['id']: index for index, tier in enumerate(cfg['tiers'])}
    state['tierOf'] = [tiers[business] for business in BUSINESSES]
    state['b'] = [economy._building(tier) for tier in state['tierOf']]
    state['cash'] = 125_000
    operations.ensure(cfg, state, new=True)
    state['book'] = sum(building['bookValue'] for building in state['b'])
    state['businessProgression']['grandfathered'] = list(BUSINESSES)
    workforce.ensure(cfg, state)

    for slot, building in enumerate(state['b']):
        for good in cfg['tiers'][building['tier']]['goods']:
            state['inventory'][good['id']] = economy._good_capacity(cfg, state, slot, good['id'])
    inventory_costs.migrate(cfg, state)
    economy._sync_pools(cfg, state)

    supplies = {need['id'] for item in cfg['craftingPilot']['items']
                for need in item['ingredients'] if need['id'] in crafting.SUPPLIES}
    for supply_id in sorted(supplies):
        crafting._add(state['crafting']['supplies'], supply_id, 100,
                      crafting.SUPPLIES[supply_id]['unitPrice'] * 100)

    if not fresh:
        for item in cfg['craftingPilot']['items']:
            for quest_id in item['unlock']['questIds']:
                state['businessProgression']['quests'][quest_id] = dict(completed=True)
            team = state['workforce']['teams'].setdefault(item['businessId'], workforce._empty_team())
            for node in item['unlock']['focusNodes']:
                if node not in team['nodes']:
                    team['nodes'].append(node)
        # Completed preview history is the baseline, not a retroactive reward.
        state.pop('craftingPilot', None)
        data = pilot.ensure(cfg, state)
        data['ordersByBusiness'] = dict.fromkeys(BUSINESSES, 8)
        data['ordersTotal'] = 8
        state['cStats']['done'] = 8
        state['checklist']['goodSales'] = 8
        for item_id in INITIAL_PRODUCTS:
            _action(cfg, state, action='unlock', itemId=item_id)
        for asset_id in ('asset_fish_stall_1', 'asset_garage_2'):
            _action(cfg, state, action='buy_asset', assetId=asset_id)
            business, ordinal = asset_id[len('asset_'):].rsplit('_', 1)
            building = next(building for building in state['b']
                            if cfg['tiers'][building['tier']]['id'] == business)
            _action(cfg, state, action='assign_asset', assetId=asset_id,
                    buildingId=building['buildingId'], assetSlot=int(ordinal) - 1)

    world = economy.new_class(cfg, 0)
    if not fresh:
        # Three real minutes give the running lines their first actual sales.
        economy.advance_class(cfg, world, [state], 0, 180 // cfg['global']['tick'])
    state['lastActiveTick'] = state['tick']
    state['lastLogin'] = state['tick']
    world['nextTick'] = state['tick']
    world['k'] = max(0, state['tick'] - 1)
    return state, world


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3011)
    parser.add_argument('--fresh', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a local preview port from 1024 to 65535.')

    cfg = pilot.configure(economy.load_config())
    # Keep API fallbacks on the same trial config; the SOLO helper initializes
    # its own ordinary snapshot, which is replaced explicitly below.
    api._startup_config = copy.deepcopy(cfg)
    state, world = preview_town(cfg, fresh=args.fresh)
    label = 'CRAFT TRIAL / FRESH' if args.fresh else 'CRAFT TRIAL / 15 PRODUCTS'
    with tempfile.TemporaryDirectory(prefix='yomama-crafting-pilot-') as directory:
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
        print('15-product crafting trial; disposable local save.', flush=True)
        serve(args.port, preview_handler(token, label), first_page='craft.html')


if __name__ == '__main__':
    main()
