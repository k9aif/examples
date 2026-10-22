# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework — k9chat URL fetch
#
# internet_search.py only ever sends the user's message to SearxNG and keeps
# the result snippets -- nothing fetched the page behind a URL the user
# pasted, so "summarize https://..." got a search for that string, not the
# page. This module reads the pages themselves: find http(s) URLs in the
# message, GET each one, reduce the HTML to readable text, and hand it back
# for chat_agent.py's _format_prompt() to label as linked-page content.
#
# Two things a page fetch needs that a search snippet doesn't:
#   - SSRF: the server, not the visitor, makes the request, so a pasted
#     http://10.x / 127.0.0.1 / 169.254.169.254 URL would read the LAN.
#     Every hop (redirects included) must resolve only to public addresses,
#     and the address the socket actually connected to is checked again
#     before the body is read (closes the DNS-rebinding gap between the
#     pre-check and requests' own resolution). Proxy env vars are ignored
#     (trust_env=False) so that peer check sees the real server.
#   - Indirect prompt injection: the page is untrusted text going straight
#     into the prompt. chat.py screens each page through the framework's
#     tool-result guard before it gets here (see _resolve_url_context()).
#
# Stdlib html.parser, not trafilatura/BeautifulSoup -- requirements.txt is
# a constrained freeze and this needs nothing beyond requests.
#
# Fail-open like every other retrieval path in k9chat: a URL that can't be
# fetched comes back as an error entry the model can mention, never an
# exception that breaks the chat turn.

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import requests

log = logging.getLogger("k9chat.url_fetch")

_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>'\""

_TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_USER_AGENT = "Mozilla/5.0 (compatible; K9Chat/1.0; +https://k9x.ai)"


class FetchRefused(Exception):
    """A URL this module won't fetch (bad scheme/port, non-public address)."""


def extract_urls(text: str, max_urls: int = 3) -> List[str]:
    """http(s) URLs in *text*, in order, de-duplicated, trailing sentence
    punctuation stripped ("see https://x.com/a." -> https://x.com/a)."""
    seen, urls = set(), []
    for raw in _URL_RE.findall(text or ""):
        url = raw.rstrip(_TRAILING_PUNCT)
        # Keep a closing paren that belongs to the URL (Wikipedia-style).
        if raw[len(url):].startswith(")") and url.count("(") > url.count(")"):
            url += ")"
        if url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= max_urls:
            break
    return urls


def strip_urls(text: str) -> str:
    """*text* with its URLs removed -- what's left is the actual question."""
    return re.sub(r"\s+", " ", _URL_RE.sub(" ", text or "")).strip()


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def _check_target(url: str, allowed_ports: List[int]) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchRefused(f"scheme '{parts.scheme}' not allowed")
    if not parts.hostname:
        raise FetchRefused("no host in URL")
    if parts.username or parts.password:
        raise FetchRefused("credentials in URL not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in allowed_ports:
        raise FetchRefused(f"port {port} not allowed")
    try:
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchRefused(f"cannot resolve host: {exc}") from exc
    for info in infos:
        ip = info[4][0]
        if not _is_public(ip):
            raise FetchRefused(f"host resolves to non-public address {ip}")


def _peer_ip(resp: requests.Response) -> Optional[str]:
    conn = getattr(resp.raw, "connection", None) or getattr(resp.raw, "_connection", None)
    sock = getattr(conn, "sock", None)
    if sock is None:
        return None
    try:
        return sock.getpeername()[0]
    except OSError:
        return None


class _TextExtractor(HTMLParser):
    """Readable text from HTML: drops scripts/styles/navigation/chrome and
    anything marked hidden (a common place to plant instructions aimed at
    an LLM), keeps <title>, and prefers <main>/<article> when the page has
    one with real content."""

    _SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "canvas",
             "nav", "footer", "header", "aside", "form", "button", "select", "head"}
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}
    _BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "tr",
              "table", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
              "dd", "dt", "figcaption", "br", "hr"}
    _HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._stack: List[bool] = []   # per open element: does it start a skipped subtree
        self._main_depth = 0
        self.all_parts: List[str] = []
        self.main_parts: List[str] = []

    def _hidden(self, tag: str, attrs) -> bool:
        a = {k.lower(): (v or "") for k, v in attrs}
        return (tag in self._SKIP or "hidden" in a or a.get("aria-hidden", "").lower() == "true"
                or bool(self._HIDDEN_STYLE.search(a.get("style", ""))))

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self._VOID:
            if tag in ("br", "hr"):
                self._emit("\n")
            return
        skip = self._hidden(tag, attrs)
        self._stack.append(skip)
        if skip:
            self._skip_depth += 1
        if tag in ("main", "article"):
            self._main_depth += 1
        if tag in self._BLOCK:
            self._emit("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr"):
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self._VOID or not self._stack:
            return
        if self._stack.pop():
            self._skip_depth -= 1
        if tag in ("main", "article") and self._main_depth:
            self._main_depth -= 1
        if tag in self._BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        self._emit(data)

    def _emit(self, s: str) -> None:
        if self._skip_depth:
            return
        self.all_parts.append(s)
        if self._main_depth:
            self.main_parts.append(s)


def _tidy(parts: List[str]) -> str:
    text = "".join(parts)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def html_to_text(html: str) -> tuple[str, str]:
    """(title, text) for an HTML document."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:   # html.parser is lenient, but never let a page break chat
        log.warning("[UrlFetch] HTML parse error: %s", exc)
    main = _tidy(parser.main_parts)
    text = main if len(main) >= 500 else _tidy(parser.all_parts)
    return re.sub(r"\s+", " ", parser.title).strip(), text


def _decode(body: bytes, resp: requests.Response) -> str:
    declared = None
    ctype = resp.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or re.search(
        rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    if m:
        declared = m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)
    for enc in (declared, "utf-8"):
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("cp1252", errors="replace")


def fetch(url: str, *, timeout: float = 8.0, max_bytes: int = 2_000_000,
          max_chars: int = 12_000, max_redirects: int = 3,
          allowed_ports: Optional[List[int]] = None) -> Dict[str, Any]:
    """Fetch one URL. Always returns a dict:
    {"url", "final_url", "title", "text", "ok", "error", "truncated"}."""
    allowed_ports = allowed_ports or [80, 443]
    out: Dict[str, Any] = {"url": url, "final_url": url, "title": "", "text": "",
                           "ok": False, "error": "", "truncated": False}
    session = requests.Session()
    session.trust_env = False   # no env proxies: the peer check must see the real server
    session.headers.update({"User-Agent": _USER_AGENT,
                            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"})
    current = url
    try:
        for _ in range(max_redirects + 1):
            _check_target(current, allowed_ports)
            resp = session.get(current, timeout=timeout, stream=True, allow_redirects=False)
            peer = _peer_ip(resp)
            if peer is not None and not _is_public(peer):
                resp.close()
                raise FetchRefused(f"connected to non-public address {peer}")
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise FetchRefused(f"redirect ({resp.status_code}) without Location")
                current = urljoin(current, location)
                continue
            break
        else:
            raise FetchRefused(f"more than {max_redirects} redirects")

        out["final_url"] = current
        if resp.status_code >= 400:
            resp.close()
            out["error"] = f"HTTP {resp.status_code}"
            return out
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ctype and ctype not in _TEXT_TYPES:
            resp.close()
            out["error"] = f"unsupported content type '{ctype}' (only web pages and plain text)"
            return out

        body = bytearray()
        for chunk in resp.iter_content(65536):
            body.extend(chunk)
            if len(body) >= max_bytes:
                break
        resp.close()
        decoded = _decode(bytes(body), resp)
        if ctype == "text/plain":
            title, text = "", _tidy([decoded])
        else:
            title, text = html_to_text(decoded)
        if not text:
            out["error"] = "page has no readable text (it may need JavaScript to render)"
            return out
        if len(text) > max_chars:
            text, out["truncated"] = text[:max_chars].rsplit(" ", 1)[0], True
        out.update(title=title, text=text, ok=True)
        return out
    except FetchRefused as exc:
        log.warning("[UrlFetch] refused %s: %s", current, exc)
        out["error"] = f"refused: {exc}"
    except requests.RequestException as exc:
        log.warning("[UrlFetch] fetch failed %s: %s", current, exc)
        out["error"] = f"fetch failed: {exc.__class__.__name__}"
    finally:
        session.close()
    return out
