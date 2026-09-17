"""Play the quest engine on a disposable local save.

    python3 previews/quests_preview.py 3012            # a town partway through
    python3 previews/quests_preview.py 3012 --fresh    # a brand-new town

The showcase town owns six businesses, has claimed the opening quests through
real production and sales, carries active boosts, and has
several quests sitting ready to claim. --fresh starts at First Crop with nothing
earned. Operations and Port are locked until their quests are claimed, so both
feature locks are visible. Every run uses a disposable database and leaves the
default economy config alone.
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
import game_api as api
import inventory_costs
import production_economy as economy
import quest_engine as quests
import workforce
from preview_support import preview_handler, serve, solo_seat


BUSINESSES = ('farm', 'fish_stall', 'roastery', 'garage', 'workshop', 'solar_coop')


def _claim(cfg, state, quest_id, choice=None):
    body = dict(action='quest_claim', questId=quest_id)
    if choice:
        body['choiceId'] = choice
    result = quests.act(cfg, state, body)
    if not result['ok']:
        raise RuntimeError('%s: %s' % (quest_id, result['why']))
    return result


def preview_town(cfg, fresh=False):
    """A preview fixture only. Production and sales run on the real engine and
    the quests below are claimed through the real claim path."""
    state = economy.new_state(cfg, seed=71)
    tiers = {tier['id']: index for index, tier in enumerate(cfg['tiers'])}
    owned = BUSINESSES[:1] if fresh else BUSINESSES
    state['tierOf'] = [tiers[business] for business in owned]
    state['b'] = [economy._building(tier) for tier in state['tierOf']]
    state['cash'] = 2_000 if fresh else 250_000
    operations.ensure(cfg, state, new=True)
    state['book'] = sum(building['bookValue'] for building in state['b'])
    workforce.ensure(cfg, state)
    for slot, building in enumerate(state['b']):
        for good in cfg['tiers'][building['tier']]['goods']:
            state['inventory'][good['id']] = economy._good_capacity(cfg, state, slot, good['id'])
    inventory_costs.migrate(cfg, state)
    economy._sync_pools(cfg, state)
    quests.ensure(cfg, state)

    if fresh:
        return _settle(cfg, state)

    # Real minutes of real trading, so every counter below was actually earned.
    for tick in range(1, 900):
        state['tick'] = tick
        economy._produce(cfg, state, tick)
        economy._retail(cfg, state, tick)

    # Manual order deliveries need a player; the preview stands in for one.
    for _ in range(14):
        quests.record_order(cfg, state)
    quests.record_action(cfg, state, 'upgrade', 3)
    quests.record_action(cfg, state, 'open_business', 5)
    quests.record_action(cfg, state, 'set_regular', 2)

    quests.record_action(cfg, state, 'quiz_pass')
    quests.record_action(cfg, state, 'craft_unlock')
    quests.record_action(cfg, state, 'craft_sale', 14)
    for quest_id in ('first-crop', 'room-to-grow', 'three-crops', 'first-delivery',
                     'harbour-lunch', 'pass-the-quiz'):
        _claim(cfg, state, quest_id)
    _claim(cfg, state, 'cafe-opening', choice='perk')   # a choice already taken
    _claim(cfg, state, 'standing-order')
    _claim(cfg, state, 'four-doors-open')
    # Clearance sales leave 'Clear the Shelves' ready, so its three reward
    # buttons are on screen: a choice the player has not made yet.
    quests.record_sale(cfg, state, [dict(goodId='farm_tomatoes', quantity=40)], 'clearance')
    return _settle(cfg, state)


def _settle(cfg, state):
    world = economy.new_class(cfg, 0)
    state['lastActiveTick'] = state['tick']
    state['lastLogin'] = state['tick']
    world['nextTick'] = state['tick']
    world['k'] = max(0, state['tick'] - 1)
    return state, world


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3012)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--no-serve', action='store_true',
                        help='build the save, print a summary and exit')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a local preview port from 1024 to 65535.')

    cfg = quests.configure(economy.load_config())
    api._startup_config = copy.deepcopy(cfg)
    state, world = preview_town(cfg, fresh=args.fresh)
    payload = quests.payload(cfg, state)
    label = 'QUESTS / FRESH' if args.fresh else 'QUESTS / CHAPTER 2'
    print('%d of %d quests complete; %d visible' % (payload['completed'], payload['total'], len(payload['quests'])))
    for row in payload['quests']:
        print('  [%-9s] %-22s %s' % (row['status'], row['id'],
              ' '.join('%d/%d' % (o['owned'], o['quantity']) for o in row['objectives']) or '-'))
    print('  boosts:', payload['boosts'], '| vouchers:', payload['vouchers'], '| features:', payload['features'])
    if args.no_serve:
        return

    with tempfile.TemporaryDirectory(prefix='yomama-quests-') as directory:
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
        print('Quest engine preview; disposable local save.', flush=True)
        serve(args.port, preview_handler(token, label), first_page='buildings.html')


if __name__ == '__main__':
    main()
