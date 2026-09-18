# -*- coding: utf-8 -*-
"""신규 바이어 발굴 - 허용된 공식 페이지 수집 (명세 5.2).

지키는 규칙:
  - http/https + 공인 IP 호스트만. 리다이렉트 대상도 다시 검사한다.
  - robots.txt 를 읽어 우리 User-Agent 에게 허용된 경로만 가져온다.
  - 401/403 은 우회하지 않는다. 429 는 Retry-After 를 따르고 제한된 횟수만 재시도한다.
  - 자바스크립트 렌더링이 필요하면 '자동 수집 미지원'으로 남기고 CSV 입력으로 돌린다.
  - 실패해도 기존 성공 데이터를 지우거나 더미로 바꾸지 않는다.

파싱은 JSON-LD(schema.org Product)를 우선한다.
beautifulsoup4 가 설치돼 있지 않아 표준 라이브러리 HTMLParser 로 읽는다.
"""

import hashlib
import json
import re
import time
import urllib.parse
import urllib.robotparser
from html.parser import HTMLParser

import requests

from . import models, pipeline

USER_AGENT = "todo-trade-prospecting/1.0 (+educational prototype; contact: sales team)"
TIMEOUT = 15
MAX_BYTES = 2_000_000
MAX_RETRY = 2
DEFAULT_DELAY = 1.5


class CollectionError(RuntimeError):
    """수집 실패. 메시지를 그대로 실행 기록에 남긴다."""


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

_robots_cache = {}


def robots_allows(url):
    """(허용여부, 설명). robots.txt 를 못 읽으면 보수적으로 막는다."""
    parts = urllib.parse.urlsplit(url)
    root = "{}://{}".format(parts.scheme, parts.netloc)
    if root in _robots_cache:
        parser = _robots_cache[root]
    else:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(root + "/robots.txt")
        try:
            models.validate_collect_url(root + "/robots.txt")
            response = requests.get(root + "/robots.txt", timeout=TIMEOUT,
                                    headers={"User-Agent": USER_AGENT})
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            elif response.status_code in (401, 403):
                _robots_cache[root] = None
                return False, "robots.txt 접근이 차단됐습니다 (HTTP {})".format(response.status_code)
            else:
                parser.parse([])          # 404 등: 제한 없음으로 본다
        except models.UnsafeUrl as exc:
            _robots_cache[root] = None
            return False, str(exc)
        except requests.RequestException as exc:
            _robots_cache[root] = None
            return False, "robots.txt 를 읽지 못했습니다: {}".format(str(exc)[:80])
        _robots_cache[root] = parser

    if parser is None:
        return False, "robots.txt 확인 실패로 수집하지 않습니다."
    if parser.can_fetch(USER_AGENT, url):
        delay = parser.crawl_delay(USER_AGENT)
        return True, "robots.txt 허용{}".format(
            " (crawl-delay {}초)".format(delay) if delay else "")
    return False, "robots.txt 가 이 경로의 수집을 허용하지 않습니다."


def crawl_delay(url):
    parts = urllib.parse.urlsplit(url)
    parser = _robots_cache.get("{}://{}".format(parts.scheme, parts.netloc))
    if parser is None:
        return DEFAULT_DELAY
    try:
        return float(parser.crawl_delay(USER_AGENT) or DEFAULT_DELAY)
    except (TypeError, ValueError):
        return DEFAULT_DELAY


# ---------------------------------------------------------------------------
# 가져오기
# ---------------------------------------------------------------------------

def fetch(url):
    """안전 검사 + robots 확인 후 본문을 가져온다."""
    safe_url = models.validate_collect_url(url)
    allowed, note = robots_allows(safe_url)
    if not allowed:
        raise CollectionError(note)

    attempt = 0
    while True:
        attempt += 1
        try:
            response = requests.get(
                safe_url, timeout=TIMEOUT, allow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        except requests.RequestException as exc:
            raise CollectionError("요청 실패: {}".format(str(exc)[:120])) from exc

        # 리다이렉트는 대상 URL 을 다시 검사한 뒤 따라간다
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            target = response.headers.get("Location")
            if not target:
                raise CollectionError("리다이렉트 대상이 없습니다.")
            safe_url = models.validate_collect_url(urllib.parse.urljoin(safe_url, target))
            allowed, note = robots_allows(safe_url)
            if not allowed:
                raise CollectionError("리다이렉트 대상 " + note)
            if attempt > 5:
                raise CollectionError("리다이렉트가 너무 많습니다.")
            continue

        if response.status_code in (401, 403):
            raise CollectionError(
                "접근 권한이 없습니다 (HTTP {}). 우회하지 않습니다.".format(response.status_code))

        if response.status_code == 429:
            if attempt > MAX_RETRY:
                raise CollectionError("요청이 제한됐습니다 (HTTP 429). 재시도를 중단합니다.")
            wait = response.headers.get("Retry-After")
            try:
                wait = min(float(wait), 30.0)
            except (TypeError, ValueError):
                wait = 5.0
            time.sleep(wait)
            continue

        if response.status_code != 200:
            raise CollectionError("HTTP {} 응답".format(response.status_code))

        content = response.content[:MAX_BYTES]
        return {
            "url": safe_url,
            "text": content.decode(response.encoding or "utf-8", errors="replace"),
            "content_hash": hashlib.sha256(content).hexdigest(),
            "robots_note": note,
        }


# ---------------------------------------------------------------------------
# 파싱 (JSON-LD 우선)
# ---------------------------------------------------------------------------

class _JsonLdReader(HTMLParser):
    """<script type="application/ld+json"> 블록만 모은다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._grab = False
        self._buffer = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and (attrs.get("type") or "").lower() == "application/ld+json":
            self._grab = True
            self._buffer = []
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "script" and self._grab:
            self.blocks.append("".join(self._buffer))
            self._grab = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._grab:
            self._buffer.append(data)
        elif self._in_title:
            self.title += data


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _types(node):
    raw = node.get("@type") or node.get("type") or ""
    if isinstance(raw, list):
        return {str(t).lower() for t in raw}
    return {str(raw).lower()}


def parse_products(html, page_url):
    """JSON-LD Product 를 뽑는다. 없으면 빈 목록 + 사유."""
    reader = _JsonLdReader()
    try:
        reader.feed(html)
    except Exception:                                  # noqa: BLE001
        pass

    nodes = []
    for block in reader.blocks:
        try:
            nodes.append(json.loads(block))
        except ValueError:
            continue

    products = []
    for root in nodes:
        for node in _walk(root):
            if not isinstance(node, dict) or "product" not in _types(node):
                continue

            name = models.clean_text(node.get("name"), 200)
            if not name:
                continue

            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            raw_price = offers.get("price") if isinstance(offers, dict) else None
            currency = (offers.get("priceCurrency") if isinstance(offers, dict) else None)

            price_value, parsed_currency = pipeline.parse_price(
                "{} {}".format(raw_price or "", currency or ""))
            size_value, size_unit = pipeline.parse_size(
                "{} {}".format(name, models.clean_text(node.get("description"), 200)))

            products.append({
                "product_name": name,
                "product_category": pipeline.guess_category(
                    name, node.get("category"), node.get("description")),
                "size_value": size_value,
                "size_unit": size_unit,
                "retail_price": price_value,
                "currency": currency or parsed_currency,
                "raw_price": models.clean_text(raw_price, 40),
                "raw_size": "",
                "source_url": models.clean_text(node.get("url") or page_url, 400),
                "ingredients": [],
                "claims": [],
            })

    note = ""
    if not products:
        if re.search(r"__NEXT_DATA__|window\.__NUXT__|data-reactroot", html):
            note = "자바스크립트로 그리는 페이지라 자동 수집이 되지 않습니다. CSV 입력을 이용하세요."
        else:
            note = "JSON-LD Product 정보를 찾지 못했습니다."
    return products, note, reader.title.strip()


def collect_product_page(url):
    """한 페이지에서 제품 목록을 얻는다. 실패는 CollectionError 로 올린다."""
    page = fetch(url)
    products, note, title = parse_products(page["text"], page["url"])
    return {
        "url": page["url"],
        "content_hash": page["content_hash"],
        "robots_note": page["robots_note"],
        "title": title,
        "products": products,
        "note": note,
    }
