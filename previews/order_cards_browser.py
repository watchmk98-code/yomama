"""Play the three proposed Market cards in an isolated local game.

    .venv/bin/python previews/order_cards_browser.py 3015

The adapter exists only in this process. The normal server, its routes, the
production engine and game.db remain unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import math
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import game_api as A
import order_engine as orders
import production_economy as economy
from previews.order_classes_preview import sample_town
from previews.preview_support import preview_handler, serve, solo_seat


def stocked_town(cfg, cooldown_seconds=60):
    """Six established businesses with real, capacity-bounded sample stock."""
    state = sample_town(cfg, 6, 7)
    state['cash'] = 5000
    state['materials'] = 40
    for slot, building in enumerate(state['b']):
        # Hold the example goods so walk-ins cannot empty the first cards
        # while the player reads. Normal deliveries still consume this stock.
        building['reserve'] = True
        for good in cfg['tiers'][state['tierOf'][slot]]['goods']:
            state['inventory'][good['id']] = economy._good_capacity(cfg, state, slot, good['id'])
    return orders.create_board(cfg, state, cooldown_seconds=cooldown_seconds)


@contextmanager
def preview_runtime():
    """Refresh on save and decorate payloads without changing engine actions."""
    original_save = A._save_state
    original_payload = economy.payload

    def save(conn, player_id, cfg, state):
        if state.get('orderEngine', {}).get('prototype'):
            orders.refresh_board(cfg, state)
        return original_save(conn, player_id, cfg, state)

    def payload(cfg, state, world, session, behind=False):
        prototype = state.get('orderEngine', {}).get('prototype')
        if prototype:
            orders.refresh_board(cfg, state)
        result = original_payload(cfg, state, world, session, behind)
        if not prototype:
            return result
        first, second = result['contracts']['offers'][:2]
        delivery_seconds = first['deliverySeconds']
        first['channelLabel'] = 'Delivery orders'
        first['deliverySeconds'] = delivery_seconds
        first['canReplace'] = not first.get('inTransit', False)
        second['channelLabel'] = second['sectorLabel'] + ' sector'
        if first.get('inTransit'):
            seconds = max(0, first['deliveryUntilTick'] * cfg['global']['tick']
                          - A.econ_clock_seconds(session))
            remaining = math.ceil(seconds)
            first.update(canFulfill=False, canCommit=False, canReplace=False,
                         deliveryRemainingSec=remaining, remainingSec=remaining,
                         progressPercent=round(max(0, 1 - seconds / delivery_seconds) * 100, 1),
                         why='Delivery is on the way. Payment arrives when it finishes.')
        result['orderPreview'] = dict(deliverySeconds=delivery_seconds,
                                      lastDelivery=state['orderEngine'].get('lastDelivery'))
        return result

    A._save_state = save
    economy.payload = payload
    try:
        yield
    finally:
        A._save_state = original_save
        economy.payload = original_payload


def order_action(action):
    """Keep the original API's authentication, class lock and transaction."""
    @A._class_locked
    def handle(body):
        index = A._index(body, 'offerIndex')
        order_id = body.get('orderId')
        if not isinstance(order_id, str) or not order_id or len(order_id) > 100:
            raise A.ApiError('orderId is required')
        intention = action
        if action == 'commit':
            if type(body.get('committed')) is not bool:
                raise A.ApiError('committed must be true or false')
            intention = 'commit' if body['committed'] else 'release'

        def apply(cfg, state, world):
            if not state.get('orderEngine', {}).get('prototype'):
                return dict(ok=False, why='This town is not the order preview')
            result = orders.apply_action(cfg, state, index, intention, order_id)
            if result.get('ok') and result.get('kind') != 'order_dispatch':
                result['kind'] = {'fulfill': 'order', 'replace': 'order_replace',
                                  'commit': 'order_commit'}[action]
            return result

        return A._act(body, apply)
    return handle


def rewrite_page(name, html):
    html = re.sub(r'(<script\s+src=["\'])\./econ\.js(?:\?[^"\']*)?(["\'])',
                  r'\1./previews/order-cards-econ.js\2', html)
    if name == 'marketplace.html':
        html = html.replace('</head>', '<link rel="stylesheet" href="./previews/order-cards-preview.css"></head>')
        html = html.replace('<h1>MARKET</h1>', '<h1>MARKET <span class="order-preview-label">/ ORDER PREVIEW</span></h1>')
    return html


def browser_handler(token):
    base = preview_handler(token, name='ORDER PREVIEW', rewrite=rewrite_page)

    class OrderPreviewHandler(base):
        GAME_POST_ROUTES = dict(base.GAME_POST_ROUTES, **{
            '/api/game/econ/orders/' + action: order_action(action)
            for action in ('fulfill', 'replace', 'commit')
        })

        def do_GET(self):
            if urlparse(self.path).path == '/previews/order-cards-econ.js':
                from previews.order_cards_ui import market_script
                script = market_script((ROOT / 'econ.js').read_text(encoding='utf-8')).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, max-age=0')
                self.send_header('Content-Length', str(len(script)))
                self.end_headers()
                self.wfile.write(script)
                return
            super().do_GET()
    return OrderPreviewHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3015)
    parser.add_argument('--delivery-base-seconds', '--delivery-seconds', '--cooldown-seconds',
                        dest='delivery_seconds', type=int, default=60,
                        help='delivery time at a 300 YM payout; larger payouts take longer')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    if args.delivery_seconds <= 0:
        parser.error('--delivery-base-seconds must be positive')
    cfg = economy.load_config()
    state = stocked_town(cfg, args.delivery_seconds)
    world = economy.new_class(cfg, state['tick'])
    world.update(nextTick=state['tick'], k=max(0, state['tick'] - 1))
    with tempfile.TemporaryDirectory(prefix='yomama-order-cards-') as directory, preview_runtime():
        token = solo_seat(Path(directory) / 'preview.db', 'ORDER PREVIEW')
        with A.connect() as conn:
            player = A._ensure_solo(conn)
            now = time.time()
            conn.execute('UPDATE sessions SET clock_base=?, clock_accum=0, started_at=? WHERE code=?',
                         (now, now, A.SOLO_CODE))
            session = A._session_of(conn, A.SOLO_CODE)
            A._save_state(conn, player['id'], cfg, state)
            A._save_world(conn, session, world)
        print('Temporary sample town; initial orders are stocked and playable.', flush=True)
        serve(args.port, browser_handler(token), 'marketplace.html')


if __name__ == '__main__':
    main()
