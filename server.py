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
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 3000
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
        super().do_GET()

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


def main() -> None:
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT

    server = ThreadingHTTPServer(("127.0.0.1", port), NewsProxyHandler)
    print(f"Serving {ROOT} at http://127.0.0.1:{port}")
    print(f"Yahoo Finance endpoint: http://127.0.0.1:{port}/api/yahoo-finance-news")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
