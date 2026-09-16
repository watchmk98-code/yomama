"""The login wall: no page is served to a browser without a live seat cookie."""
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import pytest
import game_api as A
import admin
import server
from test_access_integration import db, opened, admin_do   # noqa: F401  (fixture + helpers)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Quiet(server.NewsProxyHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(db):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    opener = urllib.request.build_opener(NoRedirect())

    def get(path, cookie=None, method="GET"):
        """(status, Location, headers)"""
        req = urllib.request.Request(base + path, method=method, headers={"Cookie": cookie} if cookie else {})
        try:
            with opener.open(req, timeout=5) as r:
                r.read()                       # drain, or the server logs a broken pipe
                return r.status, r.headers.get("Location"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Location"), dict(e.headers)
    yield get
    srv.shutdown()
    srv.server_close()


def seat(db):
    c = opened(db)
    return c, A.join(dict(code=c["code"], name="ALICE", pin="1234"))["token"]


def test_every_page_but_the_login_screens_needs_a_seat(site):
    for path, want in (("/", 302), ("/index.html", 302), ("/buildings.html", 302), ("/teach.html", 302),
                       ("/classroom-sim.html", 302), ("/join.html", 200), ("/class.html", 200),
                       ("/styles.css", 200), ("/account.js", 200), ("/api/game/hostinfo", 200)):
        assert site(path)[0] == want, path
    status, location, _ = site("/buildings.html?tab=market")
    assert (status, location) == (302, "/join.html?next=%2Fbuildings.html%3Ftab%3Dmarket")
    assert site("/")[1] == "/join.html?next=%2F"
    assert site("/index.html", method="HEAD")[0] == 302


def test_a_live_seat_cookie_opens_the_site_and_dies_with_the_seat(site, db):
    c, token = seat(db)
    good = "yomama_session=" + token
    assert site("/index.html", good)[0] == 200
    assert site("/buildings.html?x=1", good)[0] == 200
    for bad in ("yomama_session=nope", "yomama_session=", "other=" + token, "garbage;;=;;",
                "yomama_session=" + token[:-1], "yomama_session=<script>alert(1)</script>"):
        assert site("/index.html", bad)[0] == 302, bad
    admin_do(db, admin.revoke_class, c["code"])
    assert site("/index.html", good)[0] == 302            # revoked class: out
    admin_do(db, admin.restore_class, c["code"])
    assert site("/index.html", good)[0] == 200
    admin_do(db, admin.kick, c["code"], "ALICE")
    assert site("/index.html", good)[0] == 302            # kicked: out


def test_our_cookie_is_read_next_to_cookies_python_dislikes(site, db):
    # Cookies are per host, not per port: on a LAN machine any other app may
    # have set one with spaces, JSON, a bare name or non-ASCII in it.
    _, token = seat(db)
    for header in ("weird=a b c; yomama_session=" + token,
                   "yomama_session=" + token + '; json={"a":1}',
                   "bare; yomama_session=" + token,
                   "utf=ç; yomama_session=" + token,
                   'yomama_session="' + token + '"',
                   "  yomama_session = " + token + " ; x=y",
                   "yomama_session=" + token + "; yomama_session=other"):
        assert site("/index.html", header)[0] == 200, header


def test_pages_behind_the_wall_are_never_cached(site, db):
    _, token = seat(db)
    for path in ("/index.html", "/buildings.html", "/"):
        _, _, headers = site(path, "yomama_session=" + token)
        assert "no-store" in headers.get("Cache-Control", ""), path
        assert headers.get("Vary") == "Cookie", path
    _, _, headers = site("/index.html")                 # the redirect itself too
    assert "no-store" in headers.get("Cache-Control", "")
    # Assets are the opposite case: public, heavy, and the same for everyone, so
    # they say how long a browser may keep them. A versioned url is one exact
    # file for ever; an unversioned one is rechecked in minutes.
    _, _, headers = site("/styles.css")
    assert headers.get("Cache-Control") == "public, max-age=300"
    _, _, headers = site("/styles.css?v=20260916")
    assert headers.get("Cache-Control") == "public, max-age=31536000, immutable"
    _, _, headers = site("/assets/game-art/ui/workers.svg")
    assert "no-store" not in headers.get("Cache-Control", "")
    assert "Vary" not in headers


def test_spelling_tricks_do_not_slip_past_the_gate(site):
    for path in ("/INDEX.HTML", "/index.html?", "//index.html", "/index%2Ehtml", "/./index.html", "/Join.html/../index.html"):
        assert site(path)[0] in (302, 404), path
