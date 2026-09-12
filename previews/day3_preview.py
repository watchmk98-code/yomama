"""Run an isolated playable v4 preview without changing game.db.

    python3 previews/day3_preview.py 3001 --fresh
    python3 previews/day3_preview.py 3001
    python3 previews/day3_preview.py 3003 --days 14 --visit-hours 12 --strategy casual

The default Day 3 town uses the documented expansion simulation strategy.
The strategy runs only once here, never in the live game request handlers.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import production_economy as E
import game_api as A
import server


def simulated_town(cfg, days, visit_hours=2, policy='expansion'):
    st = E.new_state(cfg, seed=7)
    end = days * E.ticks_per_day(cfg)
    world = E.new_class(cfg, end)
    if days:
        spec = importlib.util.spec_from_file_location('preview_strategy', ROOT / 'tests/sim_production.py')
        strategy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strategy)
        trace = {'actions': {'deliveries': 0, 'expansions': 0, 'upgrades': 0}}
        interval = round(visit_hours * E.ticks_per_hour(cfg))
        k = 0
        while k < end:
            seconds = k * cfg['global']['tick']
            active = seconds < 600 or k % interval * cfg['global']['tick'] < 300
            if active:
                E.on_login(cfg, st, k)
                E.advance_class(cfg, world, [st], k, k + 1)
                strategy.act(cfg, st, policy, trace)
                k += 1
            else:
                # The exact same replay rules process an unattended interval;
                # no extra bot purchases happen while the player is away.
                stop = min(end, (k // interval + 1) * interval)
                E.advance_class(cfg, world, [st], k, stop)
                k = stop
    st['lastActiveTick'] = end
    st['lastLogin'] = end
    st['reportTick'] = end
    st['reportBaseline'] = dict(st['report'], contractsDone=st['cStats']['done'], contractsFailed=st['cStats']['failed'])
    world['nextTick'] = end
    world['k'] = max(0, end - 1)
    return st, world


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', type=int, nargs='?', default=3001)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--days', type=int, default=3)
    parser.add_argument('--visit-hours', type=int, default=2)
    parser.add_argument('--strategy', choices=('upgrades', 'expansion', 'deliveries', 'casual'), default='expansion')
    args = parser.parse_args()
    if not 1 <= args.days <= 90 or not 1 <= args.visit_hours <= 168:
        parser.error('days must be 1–90 and visit-hours must be 1–168')
    cfg = E.load_config()
    days = 0 if args.fresh else args.days
    label = 'NEW GAME PREVIEW' if args.fresh else 'DAY ' + str(days) + ' PREVIEW'
    st, world = simulated_town(cfg, days, args.visit_hours, args.strategy)
    with tempfile.TemporaryDirectory(prefix='yomama-production-preview-') as directory:
        A.DB_PATH = Path(directory) / 'preview.db'
        A.SOLO_NAME = label
        A.init_db()
        if days:
            with A.connect() as conn:
                player = A._ensure_solo(conn)
                now = time.time()
                conn.execute('UPDATE sessions SET clock_base=?, clock_accum=?, started_at=? WHERE code=?',
                             (now, days * 86400, now - days * 86400, A.SOLO_CODE))
                session = A._session_of(conn, A.SOLO_CODE)
                A._save_state(conn, player['id'], cfg, st)
                A._save_world(conn, session, world)
        snapshot = E.payload(cfg, st, world, {'paused': False})
        snapshot['preview'] = dict(days=days,visitHours=args.visit_hours,strategy=args.strategy,
                                   firstVisitMinutes=10,laterVisitMinutes=5,
                                   deliveriesCompleted=st['cStats']['done'])
        (ROOT / 'previews' / ('fresh-snapshot.json' if args.fresh else 'day-' + str(days) + '-snapshot.json')).write_text(json.dumps(snapshot, indent=2) + '\n')

        class PreviewHandler(server.NewsProxyHandler):
            def do_GET(self):
                name = urlparse(self.path).path.lstrip('/')
                if name in ('buildings.html', 'warehouse.html', 'marketplace.html', 'advanced-hq.html', 'license.html'):
                    html = (ROOT / name).read_text().replace('<h1>BUILD</h1>', '<h1>BUILD <span style="font-size:15px;color:var(--muted)">/ ' + label + '</span></h1>')
                    data = html.encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    super().do_GET()

        server.SERVER_PORT = args.port
        httpd = ThreadingHTTPServer(('127.0.0.1', args.port), PreviewHandler)
        print(label + ': http://127.0.0.1:' + str(args.port) + '/buildings.html', flush=True)
        print('Separate temporary save; your real game is unchanged.', flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()


if __name__ == '__main__':
    main()
