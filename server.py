#!/usr/bin/env python3
"""Static file server with a tiny Yahoo Finance RSS proxy for the NEWS desk."""

from __future__ import annotations

import email.utils
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

import game_api
import access


ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 3000
SERVER_PORT = DEFAULT_PORT
YAHOO_FINANCE_RSS_URL = "https://finance.yahoo.com/news/rssindex"
YAHOO_FINANCE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 codex-news-proxy"
)

TV_FX_CANDIDATES: dict[str, list[str]] = {
    "USDTRY": ["FX_IDC:USDTRY", "OANDA:USDTRY", "FOREXCOM:USDTRY", "FX:USDTRY"],
    "EURTRY": ["FX_IDC:EURTRY", "OANDA:EURTRY", "FOREXCOM:EURTRY", "FX:EURTRY"],
    "EURUSD": ["FX_IDC:EURUSD", "OANDA:EURUSD", "FOREXCOM:EURUSD", "FX:EURUSD"],
}
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
NAMESPACES = {"media": "http://search.yahoo.com/mrss/"}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = html.unescape(value)
    normalized = TAG_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def normalize_timestamp(raw_value: str | None) -> str:
    value = clean_text(raw_value)
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def derive_category_from_link(link: str) -> str:
    path_parts = [
        part.replace("-", " ").upper()
        for part in urlparse(link).path.split("/")
        if part
    ]
    if not path_parts:
        return "MARKETS"
    bucket: list[str] = []
    for part in path_parts:
        if part == "ARTICLES":
            break
        bucket.append(part)
        if len(bucket) == 2:
            break
    return " / ".join(bucket) if bucket else "MARKETS"


def fetch_fx_quote(pair: str) -> dict[str, object] | None:
    candidates = TV_FX_CANDIDATES.get(pair.upper(), [])
    for symbol in candidates:
        try:
            qs = urlencode({"symbol": symbol, "fields": "close,change,change_abs"})
            req = Request(
                f"https://scanner.tradingview.com/symbol?{qs}",
                headers={
                    "User-Agent": YAHOO_FINANCE_USER_AGENT,
                    "Origin": "https://www.tradingview.com",
                    "Referer": "https://www.tradingview.com/",
                },
            )
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            if not isinstance(data, dict):
                continue
            if str(data.get("code", "")).lower() == "symbol_not_exists":
                continue
            close = data.get("close")
            if close is None:
                continue
            change = data.get("change") or data.get("change_abs") or 0
            return {"close": float(close), "change": float(change), "symbol": symbol}
        except Exception:
            continue
    return None


def fetch_yahoo_finance_news(limit: int = 24) -> dict[str, object]:
    request = Request(
        YAHOO_FINANCE_RSS_URL,
        headers={
            "User-Agent": YAHOO_FINANCE_USER_AGENT,
            "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        },
    )
    with urlopen(request, timeout=12) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Yahoo Finance RSS payload is missing a channel node.")

    items: list[dict[str, str]] = []
    for index, item in enumerate(channel.findall("item")[:limit]):
        link = clean_text(item.findtext("link"))
        source_node = item.find("source")
        media_node = item.find("media:content", NAMESPACES)
        items.append(
            {
                "id": clean_text(item.findtext("guid")) or f"item-{index}",
                "title": clean_text(item.findtext("title")),
                "link": link,
                "published_at": normalize_timestamp(item.findtext("pubDate")),
                "source": clean_text(source_node.text if source_node is not None else ""),
                "source_url": clean_text(source_node.get("url") if source_node is not None else ""),
                "summary": clean_text(item.findtext("description")),
                "image_url": clean_text(media_node.get("url") if media_node is not None else ""),
                "category": derive_category_from_link(link),
            }
        )

    return {
        "feed_title": clean_text(channel.findtext("title")) or "Yahoo Finance",
        "feed_link": clean_text(channel.findtext("link")) or "https://finance.yahoo.com/",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ttl_minutes": 5,
        "items": items,
    }


# Only these file types are ever served. SimpleHTTPRequestHandler otherwise
# hands out the whole working directory - which here includes game.db (student
# names, session tokens, the teacher token), the .git history and the backup
# zips. Everything not listed is 404, so adding a new secret to the folder
# cannot silently publish it.
PUBLIC_SUFFIXES = frozenset({
    ".html", ".css", ".js", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".ttf", ".woff", ".woff2", ".otf",
    ".wav", ".mp3", ".ogg", ".mp4", ".webm",
})


def is_public_path(url_path: str) -> bool:
    """True when this request may be served off disk."""
    path = unquote(url_path.split("?", 1)[0].split("#", 1)[0])

    if path in ("", "/"):
        return True                      # the root maps to index.html

    if path.endswith("/"):
        return False                     # never list a directory

    parts = [p for p in path.split("/") if p]
    for part in parts:
        if part.startswith("."):
            return False                 # .git, .env, .DS_Store, dotfiles
        if part in ("..",):
            return False

    suffix = Path(parts[-1]).suffix.lower()
    if suffix not in PUBLIC_SUFFIXES:
        return False

    # the resolved file must still sit inside the project folder
    try:
        target = (ROOT / Path(*parts)).resolve()
        target.relative_to(ROOT.resolve())
    except (ValueError, OSError):
        return False
    return True


class NewsProxyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/yahoo-finance-news":
            self.handle_yahoo_finance_news(parsed.query)
            return
        if parsed.path == "/api/fx-quote":
            self.handle_fx_quote(parsed.query)
            return
        if parsed.path.startswith("/api/game/"):
            self.handle_game_get(parsed)
            return
        if not is_public_path(parsed.path):
            self.send_error(404, "Not Found")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if not is_public_path(urlparse(self.path).path):
            self.send_error(404, "Not Found")
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/game/"):
            self.send_error(404, "Not Found")
            return
        self.handle_game_post(parsed)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    GAME_GET_ROUTES = {
        "/api/game/state": game_api.get_state,
        "/api/game/buildings": game_api.load_buildings,
        "/api/game/econ/state": game_api.econ_state,
        "/api/game/econ/contracts": game_api.econ_contracts,
        "/api/game/econ/ticker": game_api.econ_ticker,
        "/api/game/econ/quiz": game_api.econ_quiz_questions,
        "/api/game/teacher/econ": game_api.teacher_econ,
    }
    # No route opens a class: admin.py does that, off the web.
    GAME_POST_ROUTES = {
        "/api/game/join": game_api.join,
        "/api/game/equity": game_api.trade_equity,
        "/api/game/buildings": game_api.save_buildings,
        "/api/game/teacher": game_api.teacher,
        "/api/game/teacher/login": game_api.teacher_login,
        "/api/game/econ/login": game_api.econ_login,
        "/api/game/econ/sell": game_api.econ_sell,
        "/api/game/econ/level": game_api.econ_level,
        "/api/game/econ/auto": game_api.econ_auto,
        "/api/game/econ/upgrade": game_api.econ_upgrade,
        "/api/game/econ/reserve": game_api.econ_reserve,
        "/api/game/econ/processing": game_api.econ_processing,
        "/api/game/econ/event/breakfast": game_api.econ_breakfast,
        "/api/game/econ/orders/fulfill": game_api.econ_fulfill_order,
        "/api/game/econ/orders/replace": game_api.econ_replace_order,
        "/api/game/econ/orders/commit": game_api.econ_commit_order,
        "/api/game/econ/focus": game_api.econ_focus,
        "/api/game/econ/graduate": game_api.econ_graduate,
        "/api/game/econ/expand": game_api.econ_expand,
        "/api/game/econ/contracts/accept": game_api.econ_accept_contract,
        "/api/game/teacher/event": game_api.teacher_event,
        "/api/game/econ/quiz": game_api.econ_quiz,
        "/api/game/econ/keep": game_api.econ_keep,
    }

    def handle_game_get(self, parsed) -> None:
        if parsed.path == "/api/game/hostinfo":
            lan_ip = detect_lan_ip()
            self.send_json(200, {
                "lan_ip": lan_ip,
                "port": SERVER_PORT,
                "join_url": f"http://{lan_ip}:{SERVER_PORT}/join.html",
                "reachable": lan_ip != "127.0.0.1",
            })
            return
        handler = self.GAME_GET_ROUTES.get(parsed.path)
        if handler is None:
            self.send_json(404, {"error": "unknown endpoint"})
            return
        self.run_game_handler(handler, parse_qs(parsed.query))

    def handle_game_post(self, parsed) -> None:
        handler = self.GAME_POST_ROUTES.get(parsed.path)
        if handler is None:
            self.send_json(404, {"error": "unknown endpoint"})
            return
        # The two endpoints that take a code from a stranger get a budget of
        # wrong answers per address, so nobody can guess their way into a class.
        limiter = access.LOGIN_LIMITS.get(parsed.path)
        ip = access.client_ip(self.headers, self.client_address[0]) if limiter else ""
        if limiter and limiter.blocked(ip):
            self.send_json(429, {"error": "too many wrong codes from this address; "
                                          "try again in ten minutes"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 1_000_000:
            self.send_json(413, {"error": "payload too large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json(400, {"error": f"invalid JSON body: {exc}"})
            return
        self.run_game_handler(handler, body,
                              on_reject=(lambda: limiter.hit(ip)) if limiter else None)

    def run_game_handler(self, handler, payload, on_reject=None) -> None:
        try:
            self.send_json(200, handler(payload))
        except game_api.ApiError as exc:
            if on_reject and exc.status in (401, 403, 404, 409):   # a wrong code, name or PIN
                on_reject()
            self.send_json(exc.status, {"error": exc.message, **exc.details})
        except Exception as exc:  # noqa: BLE001 - never take the class server down
            self.log_error("game api failure: %r", exc)
            self.send_json(500, {"error": "internal error"})

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_fx_quote(self, query_string: str) -> None:
        params = parse_qs(query_string)
        pair = params.get("pair", ["USDTRY"])[0].upper()

        quote = fetch_fx_quote(pair)

        if quote is None:
            body = json.dumps({"error": "quote_unavailable"}).encode("utf-8")
            status = 502
        else:
            body = json.dumps(quote).encode("utf-8")
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_yahoo_finance_news(self, query_string: str) -> None:
        params = parse_qs(query_string)
        try:
            limit = int(params.get("limit", ["24"])[0])
        except ValueError:
            limit = 24
        limit = max(1, min(limit, 40))

        try:
            payload = fetch_yahoo_finance_news(limit)
        except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError) as exc:
            body = json.dumps(
                {
                    "error": "yahoo_finance_feed_unavailable",
                    "detail": str(exc),
                }
            ).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def detect_lan_ip() -> str:
    """Best-effort local address students on the same wifi can reach."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))       # no packets sent; just picks the route
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def main() -> None:
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT

    game_api.init_db()

    global SERVER_PORT
    SERVER_PORT = port

    server = ThreadingHTTPServer(("0.0.0.0", port), NewsProxyHandler)
    lan_ip = detect_lan_ip()
    print(f"Serving {ROOT}")
    print(f"  this machine : http://127.0.0.1:{port}/index.html")
    print(f"  students use : http://{lan_ip}:{port}/index.html")
    print(f"  teacher       : http://{lan_ip}:{port}/teach.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
