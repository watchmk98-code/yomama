"""Local preview servers: a playable copy of the game with no class code.

The public server takes no API request without a seat token
(game_api.AUTO_LOGIN is False) and serves no page but join.html and
class.html without that seat's cookie (server.PUBLIC_PAGES). A preview on
127.0.0.1 with a throwaway database gets both back, in three lines:

    from preview_support import solo_seat, preview_handler, serve
    token = solo_seat(tmp_dir / 'preview.db', 'DAY 3 PREVIEW')
    serve(3003, preview_handler(token, 'DAY 3 PREVIEW'))

solo_seat turns AUTO_LOGIN on for this process only and creates the one
SOLO seat; preview_handler serves every page with that seat already signed
in (localStorage seeded before account.js runs, the wall skipped, idle
sign-out off), so the Playwright checks in tests/ui_*.cjs and a browser
opened by hand both work exactly as before the login wall.

Never for the real game.db, and never on a host that is not 127.0.0.1:
solo_seat refuses the first, serve does not offer the second.
"""

from __future__ import annotations

import json
import os
import re
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import game_api as A       # noqa: E402
import server              # noqa: E402

GAME_PAGES = ('buildings.html', 'warehouse.html', 'marketplace.html', 'advanced-hq.html', 'license.html')
_HEAD_RE = re.compile(r'<head[^>]*>', re.IGNORECASE)


def solo_seat(db_path, label='PREVIEW') -> str:
    """Point game_api at a throwaway database, allow tokenless requests and
    return the SOLO seat's token. Refuses the real database."""
    db_path = Path(db_path).expanduser().resolve()
    real = {(ROOT / 'game.db').resolve()}
    if os.environ.get('YOMAMA_DB', '').strip():
        real.add(Path(os.environ['YOMAMA_DB']).expanduser().resolve())
    if db_path in real:
        raise SystemExit('preview_support: refusing to run a preview on the real database ' + str(db_path))
    A.DB_PATH = db_path
    A.SOLO_NAME = label
    A.AUTO_LOGIN = True
    A.init_db()
    with A._db_lock, A.connect() as conn:
        player = A._ensure_solo(conn)
    return player['token']


def seed_script(token, name, code=A.SOLO_CODE) -> str:
    """Inline script that signs the browser in as the seat before any page
    script runs: the same localStorage shape join.html writes, plus the idle
    sign-out switched off so a preview tab left open stays open."""
    session = json.dumps({'token': token, 'name': name, 'code': code})
    return ('<script>/* preview seat */(function(){try{'
            'localStorage.setItem("yomama_session_v1",' + json.dumps(session) + ');'
            '}catch(e){}window.YOMAMA_IDLE_MINUTES=0;})();</script>')


def preview_handler(token, label='', name=None, rewrite=None, code=A.SOLO_CODE):
    """A request handler class: every page is served signed in as the seat.

    label   shown after BUILD on the five game pages, as day3_preview.py does
    rewrite optional callable(page_name, html) -> html for further tweaks
    """
    seed = seed_script(token, name or label or A.SOLO_NAME, code)

    class PreviewHandler(server.NewsProxyHandler):
        def signed_in(self):
            return True                          # the wall is off on this port

        def do_GET(self):
            path = urlparse(self.path).path
            name = path.lstrip('/') or 'index.html'
            page = ROOT / name
            if name.lower().endswith('.html') and server.is_public_path(path) and page.is_file():
                html = page.read_text(encoding='utf-8')
                if label and name in GAME_PAGES:
                    html = html.replace('<h1>BUILD</h1>', '<h1>BUILD <span style="font-size:15px;'
                                        'color:var(--muted)">/ ' + label + '</span></h1>')
                if rewrite:
                    html = rewrite(name, html)
                m = _HEAD_RE.search(html)
                html = (html[:m.end()] + seed + html[m.end():]) if m else seed + html
                data = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, max-age=0')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

    return PreviewHandler


def serve(port, handler_cls, first_page='buildings.html') -> None:
    """Serve on 127.0.0.1 until Ctrl-C."""
    server.SERVER_PORT = int(port)
    httpd = ThreadingHTTPServer(('127.0.0.1', int(port)), handler_cls)
    print('preview: http://127.0.0.1:%d/%s  (database %s)' % (int(port), first_page, A.DB_PATH), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
