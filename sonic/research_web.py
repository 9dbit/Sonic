"""Read-only public web research for the SONIC owner research agent.

All SONIC egress goes only to fixed HTTPS search/reader hosts. Result URLs are
validated before being passed to Jina Reader, which fetches public sources
outside our network boundary. No arbitrary direct HTTP requests to targets,
browser scripting, cookies, logins, private hosts, or model-selected tools.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
import ipaddress
import json
import re
import time
from urllib.parse import quote, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx


BING_RSS = "https://www.bing.com/search"
JINA_READ = "https://r.jina.ai/"
USER_AGENT = "SONIC-Research-Agent/1.6 (read-only, owner-initiated)"
MAX_SEARCH_BYTES = 128_000
MAX_READ_BYTES = 700_000
MAX_SOURCES = 5
MAX_FETCHES = 3
MAX_SNIPPET = 600
MAX_EXCERPT = 850

STOPWORDS = frozenset({
    "untuk", "dengan", "yang", "dari", "pada", "dalam", "atau", "cari", "carikan",
    "tolong", "tentang", "data", "referensi", "target", "perusahaan", "produk",
    "dan", "apa", "cara", "bagaimana", "seperti", "kita", "saya", "ingin", "terbaru",
    "the", "and", "for", "with", "what", "find", "list", "show", "latest", "best",
    "about", "from", "into", "website", "official", "online", "source", "sources",
})
NO_PRIVATE = (".local", ".localhost", ".internal", ".lan", ".home", ".test", ".invalid", ".onion")
SENSITIVE_QUERY = re.compile(
    r"(?i)\b(?:password|passwd|secret|api[_ -]?key|bearer|private[_ -]?key)\s*[:=]\s*\S+"
    r"|\b(?:sk-[a-z0-9_-]{18,}|gh[pousr]_[a-z0-9]{25,})\b"
)


class ResearchWebError(RuntimeError):
    """Safe, user-displayable research transport failure."""


def public_url(url: str) -> str | None:
    """Strictly public HTTPS targets. No arbitrary IP, port, userinfo or local DNS."""
    if not isinstance(url, str) or not (12 <= len(url) <= 1500):
        return None
    if any(ord(ch) < 32 for ch in url) or any(ch in url for ch in " \r\n\t\\"):
        return None
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme.lower() != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)):
            return None
        host = host.rstrip(".").lower()
        if (host != parsed.hostname.lower() or host.startswith(("-", "."))
                or host.endswith(("-", ".")) or ".." in host or "_" in host):
            return None
        try:
            ipaddress.ip_address(host.strip("[]"))
            return None
        except ValueError:
            pass
        if "." not in host or any(host.endswith(sfx) for sfx in NO_PRIVATE):
            return None
        if not re.fullmatch(r"[a-z0-9.-]{4,253}", host):
            return None
        path = parsed.path or "/"
        return urlunsplit(("https", host, path, parsed.query, ""))
    except (ValueError, AttributeError, UnicodeError):
        return None


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"(?u)\b[\w.-]{3,}\b", text.casefold())
            if token not in STOPWORDS][:16]


def relevance(query: str, title: str, snippet: str) -> int:
    tokens = list(dict.fromkeys(_tokens(query)))
    if not tokens:
        return 1
    a, b = title.casefold(), snippet.casefold()
    return sum(3 if token in a else 1 if token in b else 0 for token in tokens)


def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    if response.status_code != 200:
        raise ResearchWebError("External research provider unavailable")
    total = 0
    buffer = bytearray()
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ResearchWebError("External research content exceeded size limit")
        buffer.extend(chunk)
    return bytes(buffer)


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(11.0, connect=5.0),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=0),
    )


def _decode_rss(raw: bytes) -> list[dict]:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ResearchWebError("Search result XML contains disallowed entities")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ResearchWebError("Search provider returned invalid RSS") from exc
    results = []
    for item in root.findall("./channel/item")[:18]:
        title = " ".join((item.findtext("title") or "").split())[:180]
        snippet = re.sub(r"<[^>]{0,200}>", "", item.findtext("description") or "")
        snippet = " ".join(snippet.split())[:MAX_SNIPPET]
        url = public_url((item.findtext("link") or "").strip())
        if not url or not title:
            continue
        date = None
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (ValueError, TypeError, IndexError):
            pass
        results.append({"title": title, "url": url,
                        "snippet": snippet, "date": date, "publisher": urlsplit(url).hostname})
    return results


def search_rss(query: str) -> list[dict]:
    """Bing's public RSS result surface, no API key and no scraping HTML pages."""
    with _client() as client:
        with client.stream("GET", BING_RSS,
                           params={"format": "rss", "q": query},
                           headers={"Accept": "application/rss+xml, application/xml"}) as response:
            raw = _read_limited(response, MAX_SEARCH_BYTES)
    return _decode_rss(raw)


def expand_queries(query: str, purpose: str) -> list[str]:
    query = " ".join(query.split())[:260]
    if purpose == "targets":
        second = query + " company official business"
    elif purpose == "data":
        second = query + " statistics report official source"
    else:
        second = query + " research source reference"
    return [query, second[:300]]


def pick_sources(query: str, found: list[dict], max_sources: int = MAX_SOURCES) -> list[dict]:
    """Reject irrelevant fallback SERPs, and avoid a single domain flooding results."""
    unique = {}
    for item in found:
        url = public_url(item.get("url", ""))
        if not url:
            continue
        score = relevance(query, item.get("title", ""), item.get("snippet", ""))
        if score < 2:
            continue
        result = {**item, "url": url, "score": score}
        if url not in unique or score > unique[url]["score"]:
            unique[url] = result
    ordered = sorted(unique.values(), key=lambda x: -x["score"])
    result, domain_counts = [], {}
    for item in ordered:
        host = item["publisher"]
        if domain_counts.get(host, 0) >= 2:
            continue
        result.append({k: v for k, v in item.items() if k != "score"})
        domain_counts[host] = domain_counts.get(host, 0) + 1
        if len(result) >= max_sources:
            break
    for index, item in enumerate(result, start=1):
        item["id"] = index
    return result


def page_excerpt(text: str, query: str, limit: int = MAX_EXCERPT) -> str:
    terms = set(_tokens(query))
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not (40 <= len(line) <= 650) or line.startswith(("# ", "![", "[![")):
            continue
        if re.search(r"(?i)^(jump to|sign in|skip to|main menu|cookie policy|privacy policy)", line):
            continue
        score = sum(1 for term in terms if term in line.casefold())
        if score:
            lines.append((score, line))
    if not lines:
        return " ".join(text.split())[:limit]
    best = sorted(lines, key=lambda item: -item[0])[:3]
    return " … ".join(line for _, line in best)[:limit]


def read_public_page(url: str, query: str) -> str | None:
    url = public_url(url)
    if not url:
        return None
    # Only the fixed HTTPS Jina reader endpoint is fetched by Railway. The
    # reader is a third-party recipient of the public source URL, not a local
    # browser. No inbound auth cookies or internal credentials are forwarded.
    with _client() as client:
        with client.stream("GET", JINA_READ + url,
                           headers={"Accept": "application/json", "X-Timeout": "10000"}) as response:
            raw = _read_limited(response, MAX_READ_BYTES)
    try:
        payload = json.loads(raw)
        data = payload.get("data") if isinstance(payload, dict) else None
        content = data.get("content") if isinstance(data, dict) else None
    except (ValueError, TypeError):
        content = None
    return page_excerpt(content, query) if isinstance(content, str) and content.strip() else None


def search_and_read(query: str, purpose: str, *, max_sources: int = MAX_SOURCES) -> dict:
    """Bounded deterministic research pipeline. No LLM may choose new tool calls."""
    if not isinstance(query, str) or not 5 <= len(query.strip()) <= 300:
        raise ResearchWebError("Search query must be 5-300 characters")
    if purpose not in ("targets", "data", "references"):
        raise ResearchWebError("Research focus is invalid")
    if SENSITIVE_QUERY.search(query):
        raise ResearchWebError("Remove credentials from search queries before browsing")
    max_sources = max(1, min(MAX_SOURCES, max_sources))
    trace, found = [], []
    queries = expand_queries(query, purpose)
    for subquery in queries:
        started = time.monotonic()
        try:
            items = search_rss(subquery)
            found.extend(items)
            trace.append({"tool": "web.search", "status": "ok", "found": len(items),
                          "ms": min(30_000, round((time.monotonic() - started) * 1000))})
        except (httpx.HTTPError, ResearchWebError) as exc:
            trace.append({"tool": "web.search", "status": "unavailable", "found": 0,
                          "detail": type(exc).__name__})
    selected = pick_sources(query, found, max_sources)
    if not selected:
        return {"sources": [], "trace": trace, "queries": queries,
                "notice": "No relevant public sources found. Refine keywords or use a dedicated search API."}
    # Reading three public sources in parallel is bounded, with no arbitrary
    # hosts requested directly by this service and no JavaScript execution.
    with ThreadPoolExecutor(max_workers=MAX_FETCHES) as pool:
        future_map = {pool.submit(read_public_page, item["url"], query): item
                      for item in selected[:MAX_FETCHES]}
        for future, item in future_map.items():
            try:
                excerpt = future.result(timeout=15)
                item["excerpt"] = excerpt or item["snippet"]
                item["read"] = bool(excerpt)
                trace.append({"tool": "web.open", "status": "ok" if excerpt else "snippet_only",
                              "source_id": item["id"]})
            except (Exception,) as exc:
                item["excerpt"] = item["snippet"]
                item["read"] = False
                trace.append({"tool": "web.open", "status": "unavailable",
                              "source_id": item["id"], "detail": type(exc).__name__})
    for item in selected[MAX_FETCHES:]:
        item["excerpt"] = item["snippet"]
        item["read"] = False
    return {"sources": selected, "trace": trace, "queries": queries,
            "notice": "Third-party search and reader services may be rate-limited or return incomplete results."}